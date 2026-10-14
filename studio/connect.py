"""Shri Tools Connect: a small, stable API for n8n (or any tool that can send HTTP requests).

  GET  /api/connect/health                      is Shri Tools up, is it busy
  GET  /api/connect/options                     seasons, characters, styles, languages (ids and names)
  POST /api/connect/videos                      make a video from an idea (the story AI writes it) or from ready scenes
  GET  /api/connect/videos                      the latest videos
  GET  /api/connect/videos/{id}                 state, progress, file links, YouTube texts
  POST /api/connect/videos/{id}/approve         pictures checked: make the videos (only when approve_pictures was on)
  POST /api/connect/videos/{id}/retry           run the unfinished steps again (each step skips finished work)
  POST /api/connect/videos/{id}/cancel          stop it
  GET  /api/connect/videos/{id}/files/{name}    final | short | subtitles | thumb1 | thumb2 | thumb3 (binary)
  GET  /api/connect/n8n-workflow                a ready n8n workflow for this laptop (import it in n8n)

If Settings has an API key, every call needs the header  X-Api-Key: <key>  (or ?key=<key>).
When a video finishes, fails or waits for picture approval, Shri Tools POSTs the same JSON as GET /videos/{id} to the
video's callback_url (if given), so n8n can use a Webhook node instead of polling.
"""
import json, os, re, threading, urllib.request

from aiohttp import web

import store

FILES = {"final": "final.mp4", "short": "short1.mp4", "short2": "short2.mp4", "short3": "short3.mp4", "subtitles": "subtitles.srt",
         "thumb1": "thumb1.jpg", "thumb2": "thumb2.jpg", "thumb3": "thumb3.jpg"}
ALL_STEPS = ["sheets", "pictures", "clips", "check", "final", "publish"]
srv = None  # the server module (set by setup), for its queue helpers


def ok(data, status=200):
    return web.json_response(data, status=status, dumps=lambda o: json.dumps(o, ensure_ascii=False))


def bad(msg, status=400):
    return web.json_response({"error": msg}, status=status)


def is_local(request):
    return (request.remote or "") in ("127.0.0.1", "::1", "localhost")


@web.middleware
async def guard(request, handler):
    """API key for /api/connect/*; everything else (the app itself) only from this laptop."""
    path = request.path
    if path.startswith("/api/connect/"):
        key = store.settings().get("api_key") or ""
        given = request.headers.get("X-Api-Key") or request.query.get("key") or ""
        if key and given != key and path != "/api/connect/health":
            return bad("wrong or missing API key (header X-Api-Key)", 401)
        if not key and not is_local(request):
            return bad("set an API key in Shri Tools > Connect before calling from another computer", 403)
    elif not is_local(request):
        return bad("the Shri Tools app only opens on this laptop; other tools use /api/connect/", 403)
    return await handler(request)


def base_url(request):
    return f"{request.scheme}://{request.host}"


def language_code(value):
    v = (value or "en").strip().lower()
    for code, L in store.LANGUAGES.items():
        if v in (code, L["name"].lower(), L["native"]):
            return code
    return None


def video_view(p, base):
    pid = p["id"]
    d = store.folder("project", pid)
    st = store.status(pid)
    q = [t for t in store.queue() if t.get("project") == pid and t["state"] in ("waiting", "running")]
    state = st.get("state", "draft")
    if q and q[0]["state"] == "waiting" and state != "running":
        state = "waiting"
    pub = store.publish(pid)
    files = {k: f"{base}/api/connect/videos/{pid}/files/{k}" for k, f in FILES.items()
             if os.path.exists(os.path.join(d, "output", f))}
    season = store.load("season", p["season_id"]) if p.get("season_id") else None
    lang = store.LANGUAGES[store.language(p)]
    return {
        "id": pid, "title": p["title"], "kind": p.get("kind"), "style": p.get("style"),
        "language": store.language(p), "language_name": lang["name"],
        "season": {"id": season["id"], "title": season["title"]} if season else None, "episode": p.get("episode"),
        "state": state, "label": st.get("label", ""), "stage": st.get("stage"), "error": st.get("error"),
        "progress": {"done": st.get("done"), "total": st.get("total")}, "eta_min": st.get("eta_min"),
        "scenes": len(p.get("scenes", [])), "lines": sum(1 for s in p.get("scenes", []) if s.get("kind") == "talk"),
        "final_seconds": st.get("final_seconds"), "files": files,
        "publish": {k: pub.get(k) for k in ("titles", "description", "tags", "hashtags", "short_title",
                                            "short_description") if pub.get(k)},
        "status_url": f"{base}/api/connect/videos/{pid}", "open_in_app": f"{base}/#/p/{pid}/storyboard",
        "log": (st.get("log") or [])[-5:], "updated": st.get("updated") or p.get("updated"),
    }


def pick_cast(entries, season):
    """Cast from names, ids or {name, look, voice} objects (new characters are made); default: the season's cast."""
    if not entries:
        return list((season or {}).get("cast", [])), []
    chars = store.all_of("character")
    out, unknown = [], []
    for e in entries:
        if isinstance(e, dict):
            name = (e.get("name") or "").strip()
            c = next((c for c in chars if c["name"].lower() == name.lower()), None)
            if not c and name:
                c = store.new_character(name, e.get("look", ""), e.get("voice", ""), e.get("style", ""),
                                        e.get("pronoun", "he"), (season or {}).get("id"))
            if c:
                out.append(c["id"])
            continue
        e = str(e).strip().lstrip("@")
        c = next((c for c in chars if e in (c["id"], c["name"]) or e.lower() in (c["name"].lower(),
                  store.tag(c["name"]).lstrip("@").lower())), None)
        (out.append(c["id"]) if c else unknown.append(e))
    return out, unknown


def clean_scenes(scenes):
    out = []
    for i, s in enumerate(scenes, 1):
        s = {k: (str(s.get(k) or "")).strip() for k in srv.SCENE_KEYS}
        s["id"] = s["id"] or f"s{i:03d}"
        s["kind"] = "talk" if s["kind"] == "talk" and s["line"] else "action"
        out.append(s)
    return out


def queue_steps(pid, steps, then_approve=False):
    t = {"kind": "project", "project": pid, "steps": steps, "connect": True}
    if then_approve:
        t["then_approve"] = True
    t = store.add_task(t)
    store.set_status(pid, state="waiting", label="Waiting in the queue" if srv.running["task"] else "Starting",
                     error=None)
    return t


# ---------- handlers ----------
async def health(request):
    h = await srv.health(request)
    data = json.loads(h.body)
    return ok({"ok": True, "app": "Shri Tools", "version": srv.VERSION, **data})


async def options(request):
    return ok({
        "seasons": [{"id": s["id"], "title": s["title"], "style": s.get("style"), "cast": s.get("cast", []),
                     "episodes": len(s.get("episodes", []))} for s in store.all_of("season")],
        "characters": [{"id": c["id"], "name": c["name"], "tag": store.tag(c["name"]), "style": c.get("style")}
                       for c in store.all_of("character")],
        "styles": {k: v["name"] for k, v in store.STYLES.items()},
        "languages": {k: {"name": v["name"], "native": v["native"]} for k, v in store.LANGUAGES.items()},
    })


async def create(request):
    try:
        b = await request.json()
    except Exception:
        return bad("send a JSON body")
    if b.get("kind") == "music":  # a music video: song settings, singers by name or id
        lang = language_code(b.get("language") or "en")
        if not lang:
            return bad(f"language must be one of {', '.join(store.LANGUAGES)} (code or name)")
        singers, unknown = pick_cast(b.get("singers") or b.get("cast"), None)
        if unknown:
            return bad(f"unknown characters: {', '.join(unknown)}")
        if not (b.get("idea") or b.get("lyrics")):
            return bad("send idea (what the song is about) or lyrics")
        p = srv.create_music({**b, "language": lang, "singers": singers,
                              "approve_pictures": bool(b.get("approve_pictures", False))})
        p.setdefault("options", {}).update(callback_url=(b.get("callback_url") or "").strip(),
                                           connect_base=base_url(request))
        store.save("project", p)
        return ok({"video": video_view(p, base_url(request))}, 201)
    scenes = b.get("scenes") or []
    idea = (b.get("idea") or b.get("prompt") or "").strip()
    if not idea and not scenes:
        return bad("send an idea (the story AI writes the scenes) or scenes")
    season = None
    if b.get("season_id"):
        season = store.load("season", b["season_id"])
        if not season:
            return bad("no season with that season_id (see GET /api/connect/options)", 404)
    elif b.get("season"):
        season = next((s for s in store.all_of("season") if s["title"].lower() == str(b["season"]).strip().lower()),
                      None)
        if not season:
            return bad(f"no season called '{b['season']}' (see GET /api/connect/options)", 404)
    style = b.get("style") or (season or {}).get("style") or "pixar"
    if style not in store.STYLES:
        return bad(f"style must be one of {', '.join(store.STYLES)}")
    lang = language_code(b.get("language") or "en")
    if not lang:
        return bad(f"language must be one of {', '.join(store.LANGUAGES)} (code or name)")
    cast, unknown = pick_cast(b.get("cast"), season)
    if unknown:
        return bad(f"unknown characters: {', '.join(unknown)} (send {{name, look, voice}} to make new ones)")
    approve = bool(b.get("approve_pictures", False))
    p = store.new_project((b.get("title") or "").strip() or "Untitled video", b.get("kind", "episode"), style,
                          season and season["id"], cast, idea, int(b.get("scenes_wanted") or 18),
                          {"approve_pictures": approve, "music": bool(b.get("music")),
                           "music_prompt": b.get("music_prompt", ""),
                           "callback_url": (b.get("callback_url") or "").strip(), "connect_base": base_url(request)})
    p["language"] = lang
    prefix = b.get("style_prefix") or ((season or {}).get("style_prefix") if style == (season or {}).get("style") else None)
    if prefix:
        p["style_prefix"] = prefix
    for k in ("hook_text", "logline"):
        if b.get(k):
            p[k] = b[k]
    if scenes:
        p["scenes"] = clean_scenes(scenes)
    store.save("project", p)
    steps = ([] if scenes else ["write"]) + (["sheets", "pictures"] if approve else ALL_STEPS)
    queue_steps(p["id"], steps, then_approve=approve)
    return ok({"video": video_view(p, base_url(request))}, 201)


async def listing(request):
    base = base_url(request)
    return ok({"videos": [video_view(p, base) for p in store.all_of("project")[:30]]})


def load_or_404(request):
    p = store.load("project", request.match_info["id"])
    if not p:
        raise web.HTTPNotFound(text=json.dumps({"error": "no video with that id"}), content_type="application/json")
    return p


async def get_video(request):
    return ok({"video": video_view(load_or_404(request), base_url(request))})


async def approve(request):
    p = load_or_404(request)
    if not p.get("scenes"):
        return bad("this video has no scenes yet")
    queue_steps(p["id"], ["clips", "check", "final", "publish"])
    return ok({"video": video_view(store.load("project", p["id"]), base_url(request))})


async def retry(request):
    p = load_or_404(request)
    steps = ([] if p.get("scenes") else ["write"]) + ALL_STEPS
    queue_steps(p["id"], steps)
    return ok({"video": video_view(store.load("project", p["id"]), base_url(request))})


async def cancel(request):
    p = load_or_404(request)
    await srv.cancel_project(request)
    return ok({"video": video_view(store.load("project", p["id"]), base_url(request))})


async def file(request):
    p = load_or_404(request)
    name = request.match_info["name"]
    if name not in FILES:
        return bad(f"file must be one of {', '.join(FILES)}")
    path = os.path.join(store.folder("project", p["id"]), "output", FILES[name])
    if not os.path.exists(path):
        return bad(f"{name} is not made yet", 404)
    nice = store.safe_name(p["title"]) + ("" if name == "final" else f" - {name}") + os.path.splitext(path)[1]
    return web.FileResponse(path, headers={"Content-Disposition": f'attachment; filename="{nice}"'})


async def n8n_workflow(request):
    path = os.path.join(store.ROOT, "n8n", "shritub_connect_workflow.json")
    text = open(path, encoding="utf-8").read().replace("http://127.0.0.1:7880", base_url(request))
    key = store.settings().get("api_key") or ""
    text = text.replace('"value": "PUT-YOUR-API-KEY-HERE-OR-LEAVE-EMPTY"', json.dumps({"value": key})[1:-1])
    return web.Response(text=text, content_type="application/json",
                        headers={"Content-Disposition": 'attachment; filename="Shri Tools Connect - n8n workflow.json"'})


async def new_key(request):
    """App-only (not under /api/connect): make a new API key or clear it."""
    import secrets
    b = {}
    try:
        b = await request.json()
    except Exception:
        pass
    key = "" if b.get("clear") else "stb_" + secrets.token_urlsafe(24)
    store.save_settings({"api_key": key})
    return ok({"api_key": key})


# ---------- callbacks ----------
def notify(task):
    """Called by the queue runner when a task stops: tell the video's callback_url (n8n Webhook node)."""
    if not task or not task.get("project"):
        return
    p = store.load("project", task["project"])
    url = ((p or {}).get("options") or {}).get("callback_url")
    if not url or not re.match(r"https?://", url):
        return
    st = store.status(p["id"]).get("state")
    if st not in ("done", "failed", "cancelled", "approve"):
        return
    body = json.dumps({"event": f"video.{st}", "video": video_view(p, p["options"].get("connect_base") or
                                                                    f"http://127.0.0.1:{srv.PORT}")},
                      ensure_ascii=False).encode()

    def send():
        for attempt in range(3):
            try:
                req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
                urllib.request.urlopen(req, timeout=30).read(1)
                print(f"callback sent: {p['id']} {st} -> {url}", flush=True)
                return
            except Exception as e:
                print(f"callback failed ({attempt + 1}/3): {e}", flush=True)
                import time
                time.sleep(20)
    threading.Thread(target=send, daemon=True).start()


def setup(app, server_module):
    global srv
    srv = server_module
    app.middlewares.append(guard)
    r = app.router
    r.add_get("/api/connect/health", health)
    r.add_get("/api/connect/options", options)
    r.add_get("/api/connect/videos", listing)
    r.add_post("/api/connect/videos", create)
    r.add_get("/api/connect/videos/{id}", get_video)
    r.add_post("/api/connect/videos/{id}/approve", approve)
    r.add_post("/api/connect/videos/{id}/retry", retry)
    r.add_post("/api/connect/videos/{id}/cancel", cancel)
    r.add_get("/api/connect/videos/{id}/files/{name}", file)
    r.add_get("/api/connect/n8n-workflow", n8n_workflow)
    r.add_post("/api/settings/api-key", new_key)

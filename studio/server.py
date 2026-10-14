"""Shri Tools studio: the app's local server (UI + API) at http://127.0.0.1:7880 - works fully offline.
  <ComfyUI portable>\\python_embeded\\python.exe studio\\server.py   (or double-click "Shri Tools.bat")
Heavy work (pictures, H3 videos, checks, Shorts) runs in worker.py, one task at a time, from library\\queue.json.
"""
import asyncio, io, json, math, os, re, shutil, subprocess, sys, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import store  # noqa: E402
import connect  # noqa: E402
import telebot  # noqa: E402
import automate  # noqa: E402
from aiohttp import web  # noqa: E402

PORT = 7880
VERSION = "1.3"
WEB = os.path.join(HERE, "web")
CFG = store.CFG
IMG_EXT = {".png", ".jpg", ".jpeg", ".webp"}
NO_WINDOW = 0x08000000
running = {"task": None, "proc": None}


# ---------- helpers ----------
def ok(data=None, **kw):
    return web.json_response(data if data is not None else {"ok": True, **kw}, dumps=lambda o: json.dumps(o, ensure_ascii=False))


def bad(msg, code=400):
    return web.json_response({"error": msg}, status=code)


def mtime(path):
    try:
        return int(os.path.getmtime(path))
    except OSError:
        return 0


def pid_alive(pid):
    try:
        import psutil
        return psutil.pid_exists(pid)
    except ImportError:
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, text=True).stdout
        return str(pid) in out


def ping(url, timeout=1.5):
    try:
        urllib.request.urlopen(url, timeout=timeout).read(64)
        return True
    except Exception:
        return False


async def body(request):
    try:
        return await request.json()
    except Exception:
        return {}


# ---------- views of stored objects ----------
def character_view(c):
    cdir = store.folder("character", c["id"])
    c = dict(c)
    c["tag"] = store.tag(c["name"])
    c["pictures"] = {v: f"characters/{c['id']}/{f}?v={mtime(os.path.join(cdir, f))}"
                     for v, f in (c.get("views") or {}).items() if os.path.exists(os.path.join(cdir, f))}
    c["photo_urls"] = [f"characters/{c['id']}/photos/{f}" for f in c.get("photos", [])]
    c["job"] = store.read_json(os.path.join(cdir, "status.json"), {}) or {}
    waiting = [t for t in store.queue() if t.get("character") == c["id"] and t["state"] in ("waiting", "running")]
    if waiting:
        c["job"] = {"state": waiting[0]["state"]}
    return c


def project_summary(p):
    d = store.folder("project", p["id"])
    st = store.status(p["id"])
    cover = None
    for f in ("output/thumb1.jpg",) + tuple(f"pictures/{s['id']}.png" for s in p.get("scenes", [])[:3]):
        if os.path.exists(os.path.join(d, f)):
            cover = f"projects/{p['id']}/{f}?v={mtime(os.path.join(d, f))}"
            break
    q = [t for t in store.queue() if t.get("project") == p["id"] and t["state"] in ("waiting", "running")]
    return {"id": p["id"], "title": p["title"], "kind": p.get("kind"), "style": p.get("style"),
            "season_id": p.get("season_id"), "episode": p.get("episode"), "scenes": len(p.get("scenes", [])),
            "lines": sum(1 for s in p.get("scenes", []) if s.get("kind") == "talk"),
            "state": "waiting" if q and q[0]["state"] == "waiting" and st.get("state") != "running" else st.get("state", "draft"),
            "label": st.get("label", ""), "cover": cover, "final": os.path.exists(os.path.join(d, "output", "final.mp4")),
            "updated": p.get("updated", ""), "imported": p.get("imported", False)}


def project_view(p):
    d = store.folder("project", p["id"])
    res = store.results(p["id"])
    files = {}
    for s in p.get("scenes", []):
        files[s["id"]] = {"picture": mtime(os.path.join(d, "pictures", s["id"] + ".png")),
                          "clip": mtime(os.path.join(d, "clips", s["id"] + ".mp4"))}
    out = {}
    for f in ["final.mp4", "short1.mp4", "short2.mp4", "short3.mp4", "subtitles.srt", "thumb1.jpg", "thumb2.jpg", "thumb3.jpg",
              "song.wav"]:
        out[f] = mtime(os.path.join(d, "output", f))
    q = [t for t in store.queue() if t.get("project") == p["id"] and t["state"] in ("waiting", "running")]
    chars = [character_view(c) for c in (store.load("character", cid) for cid in p.get("cast", [])) if c]
    season = store.load("season", p["season_id"]) if p.get("season_id") else None
    return {"project": p, "status": store.status(p["id"]), "results": res, "files": files, "outputs": out,
            "publish": store.publish(p["id"]), "queue": q, "cast": chars,
            "season": {"id": season["id"], "title": season["title"]} if season else None,
            "styles": {k: v["name"] for k, v in store.STYLES.items()},
            "languages": {k: f"{v['name']} ({v['native']})" if k != "en" else v["name"] for k, v in store.LANGUAGES.items()}}


# ---------- pages and files ----------
async def index(request):
    """The app page; app.js / app.css get their change time in the URL, so a browser never runs an old version."""
    html = open(os.path.join(WEB, "index.html"), encoding="utf-8").read()
    for f in ("app.js", "app.css"):
        html = html.replace(f"/web/{f}\"", f"/web/{f}?v={mtime(os.path.join(WEB, f))}\"")
    return web.Response(text=html, content_type="text/html", headers={"Cache-Control": "no-store"})


async def lib_file(request):
    rel = request.match_info["path"]
    full = os.path.abspath(os.path.join(store.LIB, rel))
    if not full.startswith(os.path.abspath(store.LIB) + os.sep) or not os.path.isfile(full):
        raise web.HTTPNotFound()
    return web.FileResponse(full, headers={"Cache-Control": "no-cache"})


async def download(request):
    """Same file, saved by the browser with a proper name."""
    rel = request.match_info["path"]
    full = os.path.abspath(os.path.join(store.LIB, rel))
    if not full.startswith(os.path.abspath(store.LIB) + os.sep) or not os.path.isfile(full):
        raise web.HTTPNotFound()
    name = request.query.get("name") or os.path.basename(full)
    name = re.sub(r'[\\/:*?"<>|]', "_", name)
    return web.FileResponse(full, headers={"Content-Disposition": f'attachment; filename="{name}"'})


# ---------- health / settings ----------
async def health(request):
    loop = asyncio.get_running_loop()
    comfy, ollama = await asyncio.gather(
        loop.run_in_executor(None, ping, CFG["comfy_url"] + "/system_stats"),
        loop.run_in_executor(None, ping, store.settings()["ollama_url"] + "/api/version"))
    t = running["task"]
    label = ""
    if t and t.get("project"):
        p = store.load("project", t["project"])
        label = (p or {}).get("title", "") + " - " + store.status(t["project"]).get("label", "")
    elif t and t.get("character"):
        c = store.load("character", t["character"])
        label = f"Character pictures: {(c or {}).get('name', '')}"
    waiting = sum(1 for x in store.queue() if x["state"] == "waiting")
    usage = shutil.disk_usage(store.ROOT)
    build = max(mtime(os.path.join(WEB, f)) for f in ("index.html", "app.js", "app.css", "logo.svg", "icon.svg"))
    return ok({"comfy": comfy, "ollama": ollama, "busy": bool(t), "job": label, "waiting": waiting,
               "disk_free_gb": round(usage.free / 1e9, 1), "build": build, "version": VERSION})


SYSTEM = {"t": 0, "data": None}


def read_system():
    """GPU (nvidia-smi), RAM, memory commit (RAM + page file), CPU, disk and battery - for the Queue page."""
    import psutil
    gpu = None
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=name,utilization.gpu,temperature.gpu,memory.used,memory.total,"
                              "power.draw,clocks.sm", "--format=csv,noheader,nounits"], capture_output=True, text=True,
                             timeout=8, creationflags=NO_WINDOW).stdout.strip().splitlines()[0].split(", ")
        num = lambda x: float(x) if re.match(r"^[\d.]+$", x.strip()) else None
        gpu = {"name": out[0], "load": num(out[1]), "temp": num(out[2]), "vram_used": num(out[3]),
               "vram_total": num(out[4]), "power": num(out[5]), "clock": num(out[6])}
    except Exception:
        pass
    vm, sw = psutil.virtual_memory(), psutil.swap_memory()
    disk = shutil.disk_usage(store.ROOT)
    bat = psutil.sensors_battery()
    return {"gpu": gpu, "cpu": psutil.cpu_percent(interval=0.3), "cores": psutil.cpu_count(),
            "ram_used": round(vm.used / 2 ** 30, 1), "ram_total": round(vm.total / 2 ** 30, 1),
            "commit_used": round((vm.used + sw.used) / 2 ** 30, 1), "commit_total": round((vm.total + sw.total) / 2 ** 30, 1),
            "disk_free": round(disk.free / 1e9, 1), "disk_total": round(disk.total / 1e9, 1),
            "battery": {"percent": bat.percent, "plugged": bat.power_plugged} if bat else None, "time": store.now()}


async def system(request):
    if time.time() - SYSTEM["t"] > 2 or not SYSTEM["data"]:
        SYSTEM["data"] = await asyncio.get_running_loop().run_in_executor(None, read_system)
        SYSTEM["t"] = time.time()
    return ok(SYSTEM["data"])


async def get_settings(request):
    s = store.settings()
    return ok({"settings": s, "styles": {k: {"name": v["name"], "prefix": v["prefix"]} for k, v in store.STYLES.items()},
               "languages": {k: {"name": v["name"], "native": v["native"]} for k, v in store.LANGUAGES.items()},
               "version": VERSION})


async def patch_settings(request):
    return ok({"settings": store.save_settings(await body(request))})


async def ollama_models(request):
    try:
        with urllib.request.urlopen(store.settings()["ollama_url"] + "/api/tags", timeout=3) as r:
            return ok({"models": [m["name"] for m in json.loads(r.read())["models"]]})
    except Exception:
        return ok({"models": []})


# ---------- characters ----------
async def list_characters(request):
    return ok({"characters": [character_view(c) for c in store.all_of("character")]})


async def add_character(request):
    b = await body(request)
    if not (b.get("name") or "").strip():
        return bad("give the character a name")
    c = store.new_character(b["name"], b.get("look", ""), b.get("voice", ""), b.get("style", ""),
                            b.get("pronoun", "he"), b.get("season_id"))
    return ok({"character": character_view(c)})


async def get_character(request):
    c = store.load("character", request.match_info["id"])
    return ok({"character": character_view(c)}) if c else bad("not found", 404)


async def patch_character(request):
    c = store.load("character", request.match_info["id"])
    if not c:
        return bad("not found", 404)
    b = await body(request)
    for k in ("name", "look", "voice", "style", "pronoun", "season_id"):
        if k in b:
            c[k] = b[k]
    return ok({"character": character_view(store.save("character", c))})


async def delete_character(request):
    store.to_trash("character", request.match_info["id"])
    return ok()


async def upload_images(request, keep_one=False):
    out = []
    reader = await request.multipart()
    async for part in reader:
        if not part.filename:
            continue
        ext = os.path.splitext(part.filename)[1].lower()
        if ext not in IMG_EXT:
            continue
        data = await part.read(decode=False)
        out.append((part.filename, ext, bytes(data)))
        if keep_one:
            break
    return out


async def character_photos(request):
    c = store.load("character", request.match_info["id"])
    if not c:
        return bad("not found", 404)
    pdir = os.path.join(store.folder("character", c["id"]), "photos")
    os.makedirs(pdir, exist_ok=True)
    for name, ext, data in await upload_images(request):
        fn = f"photo{len(c['photos']) + 1}_{int(time.time())}{ext}"
        open(os.path.join(pdir, fn), "wb").write(data)
        c["photos"].append(fn)
    return ok({"character": character_view(store.save("character", c))})


async def character_picture(request):
    """Use your own picture as the character's full-body (front) or face picture."""
    c = store.load("character", request.match_info["id"])
    if not c:
        return bad("not found", 404)
    view = request.query.get("view", "front")
    if view not in ("front", "face"):
        return bad("view must be front or face")
    files = await upload_images(request, keep_one=True)
    if not files:
        return bad("no picture received")
    from PIL import Image
    Image.open(io.BytesIO(files[0][2])).convert("RGB").save(os.path.join(store.folder("character", c["id"]), view + ".png"))
    c.setdefault("views", {})[view] = view + ".png"
    return ok({"character": character_view(store.save("character", c))})


async def character_make(request):
    c = store.load("character", request.match_info["id"])
    if not c:
        return bad("not found", 404)
    b = await body(request)
    store.update_json(os.path.join(store.folder("character", c["id"]), "status.json"), state="waiting", error=None)
    store.add_task({"kind": "sheet", "character": c["id"], "force": bool(b.get("force"))})
    return ok({"character": character_view(c)})


# ---------- seasons ----------
async def list_seasons(request):
    out = []
    for s in store.all_of("season"):
        eps = [project_summary(p) for p in (store.load("project", e) for e in s.get("episodes", [])) if p]
        out.append({**s, "episode_list": eps})
    return ok({"seasons": out})


async def add_season(request):
    b = await body(request)
    if not (b.get("title") or "").strip():
        return bad("give the season a title")
    return ok({"season": store.new_season(b["title"], b.get("style", "pixar"), b.get("cast", []), b.get("about", ""))})


async def get_season(request):
    s = store.load("season", request.match_info["id"])
    if not s:
        return bad("not found", 404)
    eps = [project_summary(p) for p in (store.load("project", e) for e in s.get("episodes", [])) if p]
    cast = [character_view(c) for c in (store.load("character", cid) for cid in s.get("cast", [])) if c]
    return ok({"season": s, "episodes": eps, "cast": cast})


async def patch_season(request):
    s = store.load("season", request.match_info["id"])
    if not s:
        return bad("not found", 404)
    b = await body(request)
    for k in ("title", "style", "cast", "about"):
        if k in b:
            s[k] = b[k]
    return ok({"season": store.save("season", s)})


async def season_ideas(request):
    """10 ideas for the next episodes (runs between GPU jobs: the story AI needs the graphics card's memory)."""
    s = store.load("season", request.match_info["id"])
    if not s:
        return bad("not found", 404)
    q = store.queue()
    t = {"kind": "ideas", "season": s["id"], "id": time.strftime("%Y%m%d%H%M%S-") + f"{len(q):03d}", "state": "waiting",
         "added": store.now()}
    first = next((i for i, x in enumerate(q) if x["state"] == "waiting"), len(q))
    q.insert(first, t)  # before the long video jobs that wait
    store.save_queue(q)
    return ok({"task": t})


async def delete_season(request):
    store.to_trash("season", request.match_info["id"])
    return ok()


# ---------- projects ----------
async def list_projects(request):
    return ok({"projects": [project_summary(p) for p in store.all_of("project")]})


async def add_project(request):
    b = await body(request)
    title = (b.get("title") or "").strip() or "Untitled video"
    season = store.load("season", b["season_id"]) if b.get("season_id") else None
    style = b.get("style") or (season or {}).get("style") or "pixar"
    cast = b.get("cast") or (season or {}).get("cast") or []
    p = store.new_project(title, b.get("kind", "episode"), style, season and season["id"], cast, b.get("idea", ""),
                          int(b.get("scenes_wanted") or 18), b.get("options"))
    if b.get("language") in store.LANGUAGES:
        p["language"] = b["language"]
        store.save("project", p)
    prefix = b.get("style_prefix") or ((season or {}).get("style_prefix") if style == (season or {}).get("style") else None)
    if prefix:  # a season keeps its own exact style words (e.g. SHRI's cinematic look)
        p["style_prefix"] = prefix
        store.save("project", p)
    if b.get("write") and p["idea"]:
        store.add_task({"kind": "project", "project": p["id"], "steps": ["write"]})
        store.set_status(p["id"], state="waiting", label="Waiting to write the story")
    return ok({"project": p})


async def get_project(request):
    p = store.load("project", request.match_info["id"])
    return ok(project_view(p)) if p else bad("not found", 404)


async def patch_project(request):
    p = store.load("project", request.match_info["id"])
    if not p:
        return bad("not found", 404)
    b = await body(request)
    for k in ("title", "idea", "cast", "style", "style_prefix", "scenes_wanted", "logline", "short_scenes", "kind",
              "hook_text", "plot", "language", "looks", "music"):
        if k in b:
            p[k] = b[k]
    if "style" in b and "style_prefix" not in b and b["style"] in store.STYLES:
        p["style_prefix"] = store.STYLES[b["style"]]["prefix"]
    if "options" in b:
        p.setdefault("options", {}).update(b["options"])
    return ok({"project": store.save("project", p)})


SCENE_KEYS = ("id", "kind", "picture", "action", "speaker", "line", "line_en", "language", "tone", "sounds", "camera",
              "start", "end")


async def put_scenes(request):
    p = store.load("project", request.match_info["id"])
    if not p:
        return bad("not found", 404)
    b = await body(request)
    scenes = []
    for s in b.get("scenes", []):
        s = {k: (s.get(k) or "").strip() if isinstance(s.get(k), str) or s.get(k) is None else s[k] for k in SCENE_KEYS}
        if not s["id"]:
            s["id"] = store.next_scene_id({"scenes": p["scenes"] + scenes})
        s["kind"] = s["kind"] if s["kind"] in ("talk", "sing") else "action"
        scenes.append(s)
    p["scenes"] = scenes
    return ok({"project": store.save("project", p)})


async def delete_project(request):
    pid = request.match_info["id"]
    p = store.load("project", pid)
    if p and p.get("season_id"):
        s = store.load("season", p["season_id"])
        if s and pid in s["episodes"]:
            s["episodes"].remove(pid)
            store.save("season", s)
    store.to_trash("project", pid)
    return ok()


async def patch_publish(request):
    pid = request.match_info["id"]
    if not store.load("project", pid):
        return bad("not found", 404)
    b = await body(request)
    pub = store.publish(pid)
    for k in ("titles", "title_choice", "description", "tags", "hashtags", "thumbnail_choice", "short_title",
              "short_description", "checklist"):
        if k in b:
            pub[k] = b[k]
    store.write_json(store.pfile(pid, "publish.json"), pub)
    return ok({"publish": pub})


ACTIONS = {
    "write": ["write"],
    "sheets": ["sheets"],
    "approve": ["clips", "check", "final", "publish"],
    "videos": ["clips", "check"],
    "check": ["check"],
    "final": ["final"],
    "publish": ["publish"],
    "short": ["publish"],
    "finish": ["final", "publish"],
}


async def run_project(request):
    pid = request.match_info["id"]
    p = store.load("project", pid)
    if not p:
        return bad("not found", 404)
    b = await body(request)
    action, scenes = b.get("action"), b.get("scenes") or []
    if action != "write" and not p["scenes"] and not (p.get("kind") == "music" and action in ("build", "song", "plan")):
        return bad("this video has no scenes yet - write the story first")
    task = {"kind": "project", "project": pid}
    if p.get("kind") == "music" and action in ("build", "song", "plan"):
        first = {"build": ["song", "plan"], "song": ["song", "plan"], "plan": ["plan"]}[action]
        if action == "song":  # another take of the song: new seed, same lyrics
            p.setdefault("music", {})["take"] = int(p["music"].get("take", 0)) + 1
            store.save("project", p)
        if action == "build" and os.path.exists(os.path.join(store.folder("project", pid), "output", "song.wav")):
            first = [] if p.get("scenes") else ["plan"]  # keep a song you already have
        if p.get("options", {}).get("approve_pictures", True) or action != "build":
            task.update(steps=first + ["sheets", "pictures"], then_approve=True)
        else:
            task.update(steps=first + ["sheets", "pictures", "clips", "final", "publish"])
    elif action == "build":
        if p.get("options", {}).get("approve_pictures", True):
            task.update(steps=["sheets", "pictures"], then_approve=True)
        else:
            task.update(steps=["sheets", "pictures", "clips", "check", "final", "publish"])
    elif action == "pictures":
        d = store.folder("project", pid)
        has_clip = any(os.path.exists(os.path.join(d, "clips", s + ".mp4")) for s in scenes)
        task.update(steps=["sheets", "pictures"] + (["clips", "check"] if has_clip else []), scenes=scenes)

    elif action in ACTIONS:
        task["steps"] = ACTIONS[action]
        if scenes and action in ("videos", "check"):
            task["scenes"] = scenes
        if action == "publish":
            task.update(texts=bool(b.get("texts")), thumbs=bool(b.get("thumbs")))
        if action == "short" and scenes:
            p["short_scenes"] = scenes
            store.save("project", p)
    else:
        return bad("unknown action")
    if action in ("pictures", "videos") and store.status(pid).get("state") == "approve":
        task["then_approve"] = True  # still checking pictures: stay in that state afterwards
    t = store.add_task(task)
    if not running["task"]:
        store.set_status(pid, state="waiting", label="Starting")
    else:
        store.set_status(pid, state="waiting", label="Waiting in the queue")
    return ok({"task": t})


async def dub_project(request):
    """The same episode in another language: pictures and action clips are reused, the lines are translated and only
    the talking clips are made again."""
    src = store.load("project", request.match_info["id"])
    if not src:
        return bad("not found", 404)
    b = await body(request)
    p = create_dub(src, b.get("language"))
    return ok({"project": p}) if isinstance(p, dict) else bad(p)


def create_dub(src, lang):
    """A copy of src in language lang (pictures and action clips reused). Returns the project or an error text."""
    if lang not in store.LANGUAGES or lang == store.language(src):
        return "choose a different language"
    if src.get("kind") == "music":
        return "for a song in another language make a new music video (the song itself changes)"
    if not src.get("scenes"):
        return "this video has no scenes yet"
    L = store.LANGUAGES[lang]
    p = store.new_project(f"{src['title']} ({L['name']})", src.get("kind", "episode"), src["style"], None,
                          src.get("cast", []), src.get("idea", ""), src.get("scenes_wanted", 18),
                          {**src.get("options", {}), "approve_pictures": False})
    for k in ("style_prefix", "looks", "logline", "plot", "hook_text"):
        if src.get(k):
            p[k] = src[k]
    p.update(language=lang, dub_of=src["id"], scenes=json.loads(json.dumps(src["scenes"])))
    for s in p["scenes"]:
        s.pop("language", None)
    store.save("project", p)
    sd, dd = store.folder("project", src["id"]), store.folder("project", p["id"])
    res = store.results(src["id"])
    for s in p["scenes"]:
        pic = os.path.join(sd, "pictures", s["id"] + ".png")
        if os.path.exists(pic):
            shutil.copy(pic, os.path.join(dd, "pictures", s["id"] + ".png"))
        clip = os.path.join(sd, "clips", s["id"] + ".mp4")
        if s["kind"] != "talk" and os.path.exists(clip):  # action shots have no words: same clip in every language
            shutil.copy(clip, os.path.join(dd, "clips", s["id"] + ".mp4"))
            if s["id"] in res:
                store.set_result(p["id"], s["id"], **{k: v for k, v in res[s["id"]].items() if k != "picture_prompt"})
    store.add_task({"kind": "project", "project": p["id"], "steps": ["translate", "clips", "check", "final", "publish"]})
    store.set_status(p["id"], state="waiting", label="Waiting in the queue" if running["task"] else "Starting")
    return p


async def cancel_project(request):
    pid = request.match_info["id"]
    q = store.queue()
    for t in q:
        if t.get("project") == pid and t["state"] == "waiting":
            t["state"] = "cancelled"
    store.save_queue(q)
    if running["task"] and running["task"].get("project") == pid:
        stop_running()
    store.set_status(pid, state="cancelled", label="Stopped")
    return ok()


# ---------- music videos ----------
async def music_options(request):
    import musicvideo
    return ok({"genres": {k: v[0] for k, v in musicvideo.MUSIC_STYLES.items()},
               "vocals": {"female": "Female", "male": "Male", "duet": "Duet (male + female)", "child": "Child",
                          "choir": "Choir", "none": "Instrumental (no singing)"},
               "styles": {k: v["name"] for k, v in store.STYLES.items()}})


async def add_music(request):
    """A new music video: song settings + video style + singer(s); then Build makes the song, plan and pictures."""
    return ok({"project": create_music(await body(request))})


def create_music(b):
    lang = b.get("language") if b.get("language") in store.LANGUAGES else "en"
    style = b.get("style") if b.get("style") in store.STYLES else "pixar"
    singers = [c for c in (b.get("singers") or []) if store.load("character", c)]
    new = b.get("new_singer") or {}
    if (new.get("name") or "").strip():
        c = store.new_character(new["name"], new.get("look", ""), new.get("voice", ""), style, new.get("pronoun", "she"))
        singers.append(c["id"])
    secs = max(20, min(240, float(b.get("seconds") or 60)))
    p = store.new_project((b.get("title") or "").strip() or "Untitled song", "music", style, None, singers,
                          b.get("idea", ""), math.ceil(secs / 5.1667),
                          {"approve_pictures": bool(b.get("approve_pictures", True)), "music": False})
    p["language"] = lang
    p["music"] = {"genre": b.get("genre") or "pop", "vocal": b.get("vocal") or "female", "mood": b.get("mood", ""),
                  "setting": b.get("setting", ""), "seconds": secs, "lyrics": (b.get("lyrics") or "").strip(),
                  "caption": (b.get("caption") or "").strip(), "singers": singers, "take": 0}
    store.save("project", p)
    if b.get("build", True):
        steps = ["song", "plan", "sheets", "pictures"]
        t = {"kind": "project", "project": p["id"], "steps": steps, "then_approve": True}
        if not p["options"]["approve_pictures"]:
            t = {"kind": "project", "project": p["id"], "steps": steps + ["clips", "final", "publish"]}
        store.add_task(t)
        store.set_status(p["id"], state="waiting", label="Waiting in the queue" if running["task"] else "Starting")
    return p


# ---------- phone alerts (Telegram) ----------
def telegram(text, token=None, chat=None):
    st = store.settings()
    token, chat = token or st.get("telegram_token"), chat or st.get("telegram_chat_id")
    if not token or not chat:
        return False
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage",
                                 data=json.dumps({"chat_id": chat, "text": text}).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read()).get("ok", False)


def notify_phone(t):
    """Telegram: ready / failed / pictures to check (with a picture), see telebot.py."""
    telebot.notify(t)


async def llm_test(request):
    """Story AI test: one tiny JSON question to the chosen provider (with the settings sent from the form)."""
    b = await body(request)
    st = {**store.settings(), **{k: v for k, v in b.items() if k in store.DEFAULT_SETTINGS}}
    schema = {"type": "object", "properties": {"ok": {"type": "boolean"}, "hello": {"type": "string"}},
              "required": ["ok", "hello"]}
    msgs = [{"role": "user", "content": "Reply as JSON: ok = true, hello = a 3-word greeting for a cartoon studio."}]
    t0 = time.time()
    try:
        if (st.get("llm_provider") or "ollama") == "ollama":  # only check it is there: generating now would load the
            with urllib.request.urlopen(st["ollama_url"] + "/api/tags", timeout=5) as r:  # model onto a busy GPU
                names = [m["name"] for m in json.loads(r.read()).get("models", [])]
            if st.get("story_model") not in names:
                return bad(f"Ollama runs, but {st.get('story_model')} is not pulled: ollama pull {st.get('story_model')}")
            out = {"ok": True, "hello": f"Ollama ready with {st.get('story_model')}"}
        else:
            import llm
            out = await asyncio.get_running_loop().run_in_executor(
                None, lambda: llm.ask(st["llm_provider"], msgs, schema, st, timeout=120))
        return ok({"ok": True, "answer": out, "seconds": round(time.time() - t0, 1)})
    except Exception as e:
        return bad(str(e)[:400])


async def telegram_test(request):
    b = await body(request)
    try:
        sent = await asyncio.get_running_loop().run_in_executor(
            None, lambda: telegram("✅ Shri Tools is connected. You will get a message when a video is ready.",
                                   b.get("token"), b.get("chat_id")))
        return ok({"sent": sent}) if sent else bad("Telegram did not accept it - check the token and chat id")
    except Exception as e:
        return bad(f"Telegram: {e}")


async def telegram_chat(request):
    """Find your chat id: send any message to your bot first, then this reads it from the bot's updates."""
    b = await body(request)
    token = b.get("token") or store.settings().get("telegram_token")
    if not token:
        return bad("paste the bot token first")
    if telebot.seen_chats():  # the bot is already listening: it remembered who wrote to it
        return ok({"chats": telebot.seen_chats()})
    try:
        with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/getUpdates", timeout=20) as r:
            ups = json.loads(r.read()).get("result", [])
    except Exception as e:
        return bad(f"Telegram: {e}")
    chats = []
    for u in ups:
        c = (u.get("message") or u.get("channel_post") or {}).get("chat") or {}
        if c.get("id") and c["id"] not in [x["id"] for x in chats]:
            chats.append({"id": c["id"], "name": c.get("first_name") or c.get("title") or c.get("username") or ""})
    return ok({"chats": chats}) if chats else bad("no messages yet - send any message to your bot, then try again")


# ---------- queue ----------
async def get_queue(request):
    q = store.queue()[-60:]
    for t in q:
        if t.get("project"):
            p = store.load("project", t["project"])
            t["title"] = (p or {}).get("title", "(deleted)")
        elif t.get("character"):
            c = store.load("character", t["character"])
            t["title"] = "Character pictures: " + (c or {}).get("name", "(deleted)")
        elif t.get("season"):
            s = store.load("season", t["season"])
            t["title"] = "Episode ideas: " + (s or {}).get("title", "(deleted)")
    return ok({"queue": list(reversed(q))})


async def cancel_task(request):
    tid = request.match_info["id"]
    q = store.queue()
    for t in q:
        if t["id"] == tid and t["state"] == "waiting":
            t["state"] = "cancelled"
    store.save_queue(q)
    if running["task"] and running["task"]["id"] == tid:
        stop_running()
    return ok()


def stop_running():
    t, proc = running["task"], running["proc"]
    pid = t.get("pid") if t else None
    if pid:
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, creationflags=NO_WINDOW)
    for path, data in (("/interrupt", {}), ("/queue", {"clear": True})):
        try:
            urllib.request.urlopen(urllib.request.Request(CFG["comfy_url"] + path, data=json.dumps(data).encode(),
                                                          headers={"Content-Type": "application/json"}), timeout=5)
        except Exception:
            pass
    if t:
        store.set_task(t["id"], state="cancelled", finished=store.now())
        if t.get("project"):
            store.set_status(t["project"], state="cancelled", label="Stopped")
        if t.get("character"):
            store.update_json(os.path.join(store.folder("character", t["character"]), "status.json"), state="cancelled")
    running.update(task=None, proc=None)


async def open_folder(request):
    b = await body(request)
    where = b.get("path", "")
    full = os.path.abspath(os.path.join(store.LIB, where)) if where != "output" else os.path.join(store.ROOT, "output")
    if not full.startswith(os.path.abspath(store.ROOT)):
        return bad("not allowed")
    if os.path.isfile(full):
        subprocess.Popen(["explorer", "/select,", full])
    elif os.path.isdir(full):
        os.startfile(full)
    else:
        return bad("not found", 404)
    return ok()


async def start_comfy(request):
    sys.path.insert(0, os.path.join(store.ROOT, "engine"))
    from talk_clip import ensure_comfy
    loop = asyncio.get_running_loop()
    loop.run_in_executor(None, ensure_comfy, CFG["comfy_url"])
    return ok()


# ---------- the queue runner ----------
def start_task(t):
    log = open(os.path.join(store.LIB, "logs", f"task_{t['id']}.log"), "a", encoding="utf-8")
    env = dict(os.environ, HF_HUB_OFFLINE="1", PYTHONIOENCODING="utf-8")
    proc = subprocess.Popen([CFG["comfy_python"], "-u", os.path.join(HERE, "worker.py"), t["id"]], stdout=log,
                            stderr=subprocess.STDOUT, cwd=store.ROOT, env=env, creationflags=NO_WINDOW)
    store.set_task(t["id"], state="running", pid=proc.pid, started=store.now())
    t.update(state="running", pid=proc.pid)
    running.update(task=t, proc=proc)


def finish_task(code):
    t = running["task"]
    state = {0: "done", 2: "cancelled"}.get(code, "failed")
    store.set_task(t["id"], state=state, finished=store.now(), code=code)
    if t.get("project") and state == "failed":
        st = store.status(t["project"])
        if st.get("state") not in ("failed", "cancelled"):
            store.set_status(t["project"], state="failed", label="Failed", error=st.get("error") or "the worker stopped")
    running.update(task=None, proc=None)
    connect.notify(t)  # n8n: the video's callback_url hears that it is done / failed / waiting for approval
    notify_phone(t)    # Telegram: your phone hears it too (if set in Settings)


async def runner(app):
    os.makedirs(os.path.join(store.LIB, "logs"), exist_ok=True)
    # after a restart or power cut: adopt a worker that still runs, else run its task again (steps resume)
    q = store.queue()
    for t in q:
        if t["state"] == "running":
            if t.get("pid") and pid_alive(t["pid"]):
                running.update(task=t, proc=None)
            else:
                t["state"] = "waiting"
    store.save_queue(q)
    while True:
        try:
            t = running["task"]
            if t:
                proc = running["proc"]
                if proc is not None:
                    code = proc.poll()
                    if code is not None:
                        finish_task(code)
                elif not pid_alive(t["pid"]):
                    st = store.status(t["project"]).get("state") if t.get("project") else "done"
                    finish_task(0 if st in ("done", "approve") else 1)
            if time.time() - SCHED["t"] > 30:  # automations: once a minute is plenty
                SCHED["t"] = time.time()
                run_automations()
            if not running["task"]:
                now = time.strftime("%Y-%m-%d %H:%M")
                nxt = next((x for x in store.queue() if x["state"] == "waiting" and (x.get("start_at") or "") <= now), None)
                if nxt:
                    start_task(nxt)
        except Exception as e:
            print("runner:", e, flush=True)
        await asyncio.sleep(2)


SCHED = {"t": 0}


def run_automations():
    items = automate.schedules()
    changed = False
    for s in items:
        if not automate.due(s):
            continue
        s["last_run"] = time.strftime("%Y-%m-%d")
        changed = True
        try:
            r = automate.fire(s, log=lambda m: print(m, flush=True))
            if isinstance(r, dict) and r.get("dub"):
                src = store.load("project", r["dub"])
                r = create_dub(src, r["language"]) if src else None
            if isinstance(r, dict):
                s["last_project"] = r["id"]
                if all(telebot.settings()):
                    import threading
                    threading.Thread(target=telebot.send, daemon=True,
                                     args=(f"⏰ Automation '{s.get('name')}': started {r['title']}",)).start()
        except Exception as e:
            print("automation failed:", e, flush=True)
            s["last_error"] = str(e)[:300]
    if changed:
        automate.save(items)


async def get_schedules(request):
    items = automate.schedules()
    for s in items:
        s["next_run"] = automate.next_run(s) if s.get("enabled", True) else ""
        season = store.load("season", s.get("season_id")) or {}
        s["season_title"] = season.get("title", "(deleted)")
        s["ideas_left"] = sum(1 for x in season.get("ideas", []) if not x.get("used"))
    return ok({"schedules": items})


async def save_schedule(request):
    try:
        return ok({"schedule": automate.upsert(await body(request))})
    except (ValueError, TypeError) as e:
        return bad(str(e))


async def delete_schedule(request):
    automate.save([x for x in automate.schedules() if x["id"] != request.match_info["id"]])
    return ok()


async def run_schedule_now(request):
    s = next((x for x in automate.schedules() if x["id"] == request.match_info["id"]), None)
    if not s:
        return bad("not found", 404)
    r = automate.fire(s)
    if isinstance(r, dict) and r.get("dub"):
        src = store.load("project", r["dub"])
        r = create_dub(src, r["language"]) if src else None
    return ok({"project": r}) if isinstance(r, dict) else bad(r or "nothing to do right now")


async def task_start_at(request):
    """Start a waiting job at a set time ("" = as soon as the GPU is free)."""
    b = await body(request)
    at = (b.get("start_at") or "").replace("T", " ")[:16]
    q = store.queue()
    for t in q:
        if t["id"] == request.match_info["id"] and t["state"] == "waiting":
            t["start_at"] = at
    store.save_queue(q)
    return ok({"start_at": at})


async def on_start(app):
    app["runner"] = asyncio.create_task(runner(app))
    telebot.start(sys.modules[__name__])  # your phone: alerts + commands (only when a bot token is set)


def make_app():
    app = web.Application(client_max_size=200 * 1024 * 1024)
    r = app.router
    r.add_get("/", index)
    r.add_static("/web/", WEB)
    r.add_get("/lib/{path:.+}", lib_file)
    r.add_get("/download/{path:.+}", download)
    r.add_get("/api/health", health)
    r.add_get("/api/system", system)
    r.add_get("/api/settings", get_settings)
    r.add_patch("/api/settings", patch_settings)
    r.add_get("/api/ollama/models", ollama_models)
    r.add_get("/api/characters", list_characters)
    r.add_post("/api/characters", add_character)
    r.add_get("/api/characters/{id}", get_character)
    r.add_patch("/api/characters/{id}", patch_character)
    r.add_delete("/api/characters/{id}", delete_character)
    r.add_post("/api/characters/{id}/photos", character_photos)
    r.add_post("/api/characters/{id}/picture", character_picture)
    r.add_post("/api/characters/{id}/make", character_make)
    r.add_get("/api/seasons", list_seasons)
    r.add_post("/api/seasons", add_season)
    r.add_get("/api/seasons/{id}", get_season)
    r.add_patch("/api/seasons/{id}", patch_season)
    r.add_delete("/api/seasons/{id}", delete_season)
    r.add_post("/api/seasons/{id}/ideas", season_ideas)
    r.add_get("/api/projects", list_projects)
    r.add_post("/api/projects", add_project)
    r.add_get("/api/projects/{id}", get_project)
    r.add_patch("/api/projects/{id}", patch_project)
    r.add_delete("/api/projects/{id}", delete_project)
    r.add_put("/api/projects/{id}/scenes", put_scenes)
    r.add_patch("/api/projects/{id}/publish", patch_publish)
    r.add_post("/api/projects/{id}/run", run_project)
    r.add_post("/api/projects/{id}/cancel", cancel_project)
    r.add_post("/api/projects/{id}/dub", dub_project)
    r.add_get("/api/music/options", music_options)
    r.add_post("/api/settings/telegram-test", telegram_test)
    r.add_post("/api/settings/llm-test", llm_test)
    r.add_post("/api/settings/telegram-chat", telegram_chat)
    r.add_post("/api/music", add_music)
    r.add_get("/api/queue", get_queue)
    r.add_post("/api/queue/{id}/cancel", cancel_task)
    r.add_post("/api/queue/{id}/start_at", task_start_at)
    r.add_get("/api/schedules", get_schedules)
    r.add_post("/api/schedules", save_schedule)
    r.add_delete("/api/schedules/{id}", delete_schedule)
    r.add_post("/api/schedules/{id}/run", run_schedule_now)
    r.add_post("/api/open", open_folder)
    r.add_post("/api/comfy/start", start_comfy)
    connect.setup(app, sys.modules[__name__])  # Shri Tools Connect: the API for n8n
    app.on_startup.append(on_start)
    return app


if __name__ == "__main__":
    for sub in ("characters", "seasons", "projects", "logs"):
        os.makedirs(os.path.join(store.LIB, sub), exist_ok=True)
    if sys.stdout is None:  # started with pythonw (no console): keep a log file instead
        sys.stdout = sys.stderr = open(os.path.join(store.LIB, "logs", "server.log"), "a", encoding="utf-8", buffering=1)
    print(f"Shri Tools studio: http://127.0.0.1:{PORT}", flush=True)
    st = store.settings()
    # other computers (n8n in Docker or on another PC) only with an API key; the app pages stay local either way
    host = "0.0.0.0" if st.get("api_network") and st.get("api_key") else "127.0.0.1"
    web.run_app(make_app(), host=host, port=PORT, print=None)

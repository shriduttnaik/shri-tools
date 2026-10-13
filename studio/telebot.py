"""Shri Tools on your phone: a Telegram bot (your own, made with @BotFather) that tells you when videos are ready and takes
commands. It asks Telegram for new messages itself (long polling), so no tunnel is needed and the laptop stays closed to
the internet. It only answers the chat id saved in Settings; everyone else is ignored.

  /status   what is running now (+ GPU load and temperature)
  /videos   the latest videos with their numbers
  /approve N   pictures of video N are OK: make the videos
  /pictures N  the pictures of video N as one image
  /short N     the 9:16 Short of video N (or its thumbnail if too big)
  /make idea   a new episode of your latest season from a one-line idea (stops at the pictures for /approve)
  /stop N      stop video N
"""
import json, os, threading, time, urllib.request, uuid

import store

STATE = os.path.join(store.LIB, "telegram.json")
srv = None


def settings():
    st = store.settings()
    return st.get("telegram_token") or "", str(st.get("telegram_chat_id") or "")


def call(method, token, data=None, files=None, timeout=40):
    url = f"https://api.telegram.org/bot{token}/{method}"
    if files:  # multipart: a photo or a video
        boundary = uuid.uuid4().hex
        body = b""
        for k, v in (data or {}).items():
            body += f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
        for k, (name, blob, ctype) in files.items():
            body += (f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"; filename="{name}"\r\n'
                     f"Content-Type: {ctype}\r\n\r\n").encode() + blob + b"\r\n"
        body += f"--{boundary}--\r\n".encode()
        req = urllib.request.Request(url, data=body, headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    else:
        req = urllib.request.Request(url, data=json.dumps(data or {}).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def send(text, photo=None, video=None):
    token, chat = settings()
    if not token or not chat:
        return False
    if photo and os.path.exists(photo):
        return call("sendPhoto", token, {"chat_id": chat, "caption": text[:1000]},
                    {"photo": (os.path.basename(photo), open(photo, "rb").read(), "image/jpeg")}, timeout=120).get("ok")
    if video and os.path.exists(video):
        return call("sendVideo", token, {"chat_id": chat, "caption": text[:1000], "supports_streaming": "true"},
                    {"video": (os.path.basename(video), open(video, "rb").read(), "video/mp4")}, timeout=600).get("ok")
    return call("sendMessage", token, {"chat_id": chat, "text": text}).get("ok")


# ---------- videos by number ----------
def videos():
    return sorted(store.all_of("project"), key=lambda p: p.get("created", ""), reverse=True)


def by_number(arg):
    try:
        n = int(arg.strip())
        return videos()[n - 1]
    except Exception:
        return None


def contact_sheet(p):
    from PIL import Image, ImageDraw, ImageFont
    d = store.folder("project", p["id"])
    pics = [os.path.join(d, "pictures", s["id"] + ".png") for s in p.get("scenes", [])]
    pics = [x for x in pics if os.path.exists(x)]
    if not pics:
        return None
    cols = 4
    rows = (len(pics) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * 400, rows * 225), "black")
    font = ImageFont.truetype(os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "arialbd.ttf"), 24)
    for k, f in enumerate(pics):
        im = Image.open(f).convert("RGB").resize((400, 225))
        ImageDraw.Draw(im).text((8, 4), str(k + 1), font=font, fill="yellow", stroke_width=3, stroke_fill="black")
        sheet.paste(im, ((k % cols) * 400, (k // cols) * 225))
    out = os.path.join(d, "output", "telegram_pictures.jpg")
    sheet.save(out, quality=80)
    return out


# ---------- what the bot says when a job stops ----------
def notify(t):
    if not t or not t.get("project") or not all(settings()):
        return
    p = store.load("project", t["project"])
    st = store.status(t["project"])
    if not p or st.get("state") not in ("done", "failed", "approve"):
        return
    n = next((i + 1 for i, x in enumerate(videos()) if x["id"] == p["id"]), "?")
    d = store.folder("project", p["id"])

    def go():
        try:
            if st["state"] == "done":
                thumb = os.path.join(d, "output", "thumb1.jpg")
                send(f"✅ {p['title']} is ready" + (f" ({st.get('final_seconds')} s)" if st.get("final_seconds") else "")
                     + f".\n/short {n} - get the Short", photo=thumb)
            elif st["state"] == "approve":
                send(f"🖼 {p['title']} (video {n}): the pictures are ready.\n/approve {n} - make the videos\n"
                     "or fix pictures in Shri Tools first.", photo=contact_sheet(p))
            else:
                send(f"❌ {p['title']} (video {n}) stopped: {(st.get('error') or 'see the Build tab')[:300]}")
        except Exception as e:
            print("telegram notify:", e, flush=True)
    threading.Thread(target=go, daemon=True).start()


# ---------- commands ----------
def handle(text):
    cmd, _, arg = text.strip().partition(" ")
    cmd = cmd.lower().split("@")[0]
    if cmd in ("/start", "/help"):
        return send(__doc__.split("\n\n", 1)[1].strip())
    if cmd == "/status":
        t = srv.running["task"]
        label = "idle - nothing running"
        if t and t.get("project"):
            p = store.load("project", t["project"]) or {}
            st = store.status(t["project"])
            label = f"{p.get('title', '')}: {st.get('label', '')}" + (f" (about {st['eta_min']} min left)" if st.get("eta_min") else "")
        waiting = sum(1 for x in store.queue() if x["state"] == "waiting")
        try:
            g = srv.read_system().get("gpu") or {}
            gpu = f"\nGPU {g.get('load', '-'):.0f}% · {g.get('temp', '-'):.0f}°C" if g.get("load") is not None else ""
        except Exception:
            gpu = ""
        return send(f"▶ {label}\n{waiting} waiting in the queue{gpu}")
    if cmd == "/videos":
        rows = [f"{i + 1}. {p['title']} - {store.status(p['id']).get('label') or store.status(p['id']).get('state', 'draft')}"
                for i, p in enumerate(videos()[:10])]
        return send("\n".join(rows) or "no videos yet")
    if cmd in ("/approve", "/pictures", "/short", "/stop"):
        p = by_number(arg)
        if not p:
            return send(f"which video? e.g. {cmd} 1 (see /videos)")
        d = store.folder("project", p["id"])
        if cmd == "/pictures":
            sheet = contact_sheet(p)
            return send(f"🖼 {p['title']}", photo=sheet) if sheet else send("no pictures yet")
        if cmd == "/short":
            short = os.path.join(d, "output", "short1.mp4")
            if os.path.exists(short) and os.path.getsize(short) < 49e6:
                return send(f"📱 {p['title']} - Short", video=short)
            thumb = os.path.join(d, "output", "thumb1.jpg")
            return send(f"{p['title']}: the Short is not made yet or is too big for Telegram (50 MB).", photo=thumb)
        if cmd == "/stop":
            q = store.queue()
            for t in q:
                if t.get("project") == p["id"] and t["state"] == "waiting":
                    t["state"] = "cancelled"
            store.save_queue(q)
            if srv.running["task"] and srv.running["task"].get("project") == p["id"]:
                srv.stop_running()
            store.set_status(p["id"], state="cancelled", label="Stopped")
            return send(f"⏹ {p['title']} stopped")
        if store.status(p["id"]).get("state") != "approve":
            return send(f"{p['title']} is not waiting for picture approval ({store.status(p['id']).get('label', '')})")
        store.add_task({"kind": "project", "project": p["id"], "steps": ["clips", "check", "final", "publish"]})
        store.set_status(p["id"], state="waiting", label="Waiting in the queue")
        return send(f"🎬 {p['title']}: making the videos. I will tell you when it is ready.")
    if cmd == "/make":
        if len(arg.split()) < 4:
            return send("tell me the idea in a sentence, e.g. /make Tuntun meets the vegetable seller and learns to say thank you")
        seasons = store.all_of("season")
        season = seasons[0] if seasons else None
        p = store.new_project("Untitled video", "episode" if season else "video", (season or {}).get("style", "pixar"),
                              season and season["id"], (season or {}).get("cast", []), arg.strip(), 18,
                              {"approve_pictures": True})
        if season and season.get("style_prefix"):
            p["style_prefix"] = season["style_prefix"]
            store.save("project", p)
        store.add_task({"kind": "project", "project": p["id"], "steps": ["write", "sheets", "pictures"], "then_approve": True})
        store.set_status(p["id"], state="waiting", label="Waiting in the queue")
        return send(f"✍ New episode{' of ' + season['title'] if season else ''}: the story AI writes it, then the pictures "
                    "are drawn. I will send them to you for /approve.")
    return send("I know /status, /videos, /approve N, /pictures N, /short N, /make idea, /stop N")


def loop():
    """Long polling: ask Telegram for new messages (25 s wait each time). Only your chat gets answers."""
    state = store.read_json(STATE, {}) or {}
    while True:
        token, chat = settings()
        if not token:
            time.sleep(15)
            continue
        try:
            r = call("getUpdates", token, {"offset": state.get("offset", 0), "timeout": 25}, timeout=40)
            for u in r.get("result", []):
                state["offset"] = u["update_id"] + 1
                m = u.get("message") or {}
                c = m.get("chat") or {}
                seen = state.setdefault("chats", [])
                if c.get("id") and c["id"] not in [x["id"] for x in seen]:  # for "Find my chat id" in Settings
                    seen.append({"id": c["id"], "name": c.get("first_name") or c.get("title") or ""})
                if chat and str(c.get("id")) == chat and (m.get("text") or "").startswith("/"):
                    try:
                        handle(m["text"])
                    except Exception as e:
                        send(f"⚠ {e}")
            store.write_json(STATE, state)
        except Exception as e:
            print("telegram poll:", str(e)[:200], flush=True)
            time.sleep(20)


def start(server_module):
    global srv
    srv = server_module
    threading.Thread(target=loop, daemon=True).start()


def seen_chats():
    return (store.read_json(STATE, {}) or {}).get("chats", [])

"""Shri Tools library: characters, seasons, projects and the job queue, stored as JSON files in the library folder.

library\\characters\\<id>\\character.json  (+ face.png, front.png, photos\\)
library\\seasons\\<id>\\season.json
library\\projects\\<id>\\project.json  what you write/edit (story, scenes, options)
                     status.json   what the worker is doing (stage, progress, log)
                     results.json  per scene: picture/clip versions, check result
                     publish.json  titles, description, tags, thumbnails, shorts
                     pictures\\ clips\\ versions\\ output\\
library\\queue.json, library\\settings.json, library\\trash\\
"""
import json, os, re, shutil, time

STUDIO = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(STUDIO)
LIB = os.path.join(ROOT, "library")
if not os.path.exists(os.path.join(ROOT, "config.json")):
    raise SystemExit("config.json is missing: copy config.example.json to config.json and set your paths "
                     "(see docs/SETUP.md)")
with open(os.path.join(ROOT, "config.json"), encoding="utf-8") as _f:
    CFG = json.load(_f)

STYLES = {
    "cinematic": {
        "name": "Realistic cinematic",
        "prefix": "cinematic photoreal film still, real people, natural skin texture, dramatic natural light, warm "
                  "orange and teal color grade, anamorphic lens, shallow depth of field, subtle film grain, ultra "
                  "detailed, no text, no watermark",
        "h3": "a realistic, cinematic live-action film",
    },
    "pixar": {
        "name": "3D Pixar cartoon",
        "prefix": "3D Pixar style animated movie still, cute stylized cartoon characters with big expressive eyes, "
                  "smooth rounded shapes, soft subsurface lighting, vibrant warm colors, bright and colorful, soft "
                  "global illumination, cinematic depth of field, high quality 3D render, no text",
        "h3": "a 3D animated Pixar-style cartoon film",
    },
    "anime": {
        "name": "Anime",
        "prefix": "anime film still, hand-drawn 2D animation, clean line art, soft cel shading, painted backgrounds, "
                  "vivid colors, expressive faces, high quality, no text",
        "h3": "a hand-drawn 2D anime film",
    },
    "storybook": {
        "name": "Storybook",
        "prefix": "children's storybook illustration, soft watercolor and gouache, gentle pastel colors, rounded "
                  "friendly characters, warm cozy light, paper texture, no text",
        "h3": "an animated children's storybook illustration",
    },
    "neon": {
        "name": "Neon music video",
        "prefix": "neon-lit music video still, glowing pink, purple and cyan neon lights, night city reflections on wet "
                  "streets, light haze, high contrast, vibrant, cinematic, no text",
        "h3": "a stylish neon-lit music video",
    },
    "retro": {
        "name": "Retro Bollywood",
        "prefix": "1990s Bollywood film song still, warm saturated film colors, soft glow, dreamy backlight, film grain, "
                  "dramatic studio lighting, no text",
        "h3": "a retro 1990s Bollywood film song",
    },
    "comic": {
        "name": "Comic book",
        "prefix": "animated comic book art, bold ink outlines, halftone shading, vivid flat colors, dynamic angles, no text",
        "h3": "an animated comic book",
    },
    "clay": {
        "name": "Claymation",
        "prefix": "stop-motion claymation film still, handmade plasticine characters with fingerprint texture, "
                  "miniature handmade sets, soft studio light, shallow depth of field, no text",
        "h3": "a stop-motion claymation film",
    },
}

# Spoken language of a video (project "language", a scene may override it). "h3" is the language name inside H3's
# dialogue tag <d>[Hindi] ...</d>; "whisper" is the language the quality check listens for (Whisper has no Konkani:
# Marathi is the closest Devanagari language it knows).
LANGUAGES = {
    "en": {"name": "English", "native": "English", "h3": "English", "whisper": "en"},
    "hi": {"name": "Hindi", "native": "हिन्दी", "h3": "Hindi", "whisper": "hi"},
    "kn": {"name": "Kannada", "native": "ಕನ್ನಡ", "h3": "Kannada", "whisper": "kn"},
    "kok": {"name": "Konkani", "native": "कोंकणी", "h3": "Konkani", "whisper": "mr"},
    "mr": {"name": "Marathi", "native": "मराठी", "h3": "Marathi", "whisper": "mr"},
    "ta": {"name": "Tamil", "native": "தமிழ்", "h3": "Tamil", "whisper": "ta"},
    "te": {"name": "Telugu", "native": "తెలుగు", "h3": "Telugu", "whisper": "te"},
    "ml": {"name": "Malayalam", "native": "മലയാളം", "h3": "Malayalam", "whisper": "ml"},
    "bn": {"name": "Bengali", "native": "বাংলা", "h3": "Bengali", "whisper": "bn"},
    "gu": {"name": "Gujarati", "native": "ગુજરાતી", "h3": "Gujarati", "whisper": "gu"},
    "pa": {"name": "Punjabi", "native": "ਪੰਜਾਬੀ", "h3": "Punjabi", "whisper": "pa"},
    "ur": {"name": "Urdu", "native": "اردو", "h3": "Urdu", "whisper": "ur"},
}


def language(p, s=None):
    """Language code of a scene (its own, else the project's, else English)."""
    code = ((s or {}).get("language") or (p or {}).get("language") or "en").strip()
    return code if code in LANGUAGES else "en"


DEFAULT_SETTINGS = {
    "story_model": "gpt-oss:20b",
    "api_key": "",  # Shri Tools Connect (n8n): empty = no key needed (the server only listens on this laptop)
    "llm_provider": "ollama",  # story AI: ollama (this laptop) | claude | openai | gemini | compat (OpenAI-compatible)
    "llm_model": "",           # cloud model name (empty = the provider's default)
    "anthropic_api_key": "", "openai_api_key": "", "gemini_api_key": "",
    "compat_base_url": "", "compat_api_key": "",
    "api_network": False,  # True + an API key: n8n on another computer / in Docker may call /api/connect/
    "ollama_url": "http://127.0.0.1:11434",
    "clip_sizes": [[864, 480], [736, 416]],
    "picture_size": [1024, 576],
    "picture_check": True,        # a vision AI checks every picture (extra / doubled people, wrong action) and
    "picture_check_tries": 2,     # draws a failed one again up to this many times
    "vision_model": "qwen2.5vl:7b",  # Ollama vision model for the picture check (a cloud story AI is used if set)
    "qc_rounds": 2,
    "level": 0.08,
    "xfade": 0.3,
    "music_volume": 0.3,
    "short_max_seconds": 58,
    "shorts_count": 3,  # Shorts per video: the hook Short, the ending, the best middle moment
    "ai_disclosure": "Made with AI: pictures, acting, voices and sounds are AI-generated.",
    "brand_intro": False,     # optional: 2 s waving-flag SHRI TOOLS intro before the final video
    "brand_end": False,       # optional: 3 s end card with the logo and brand_end_text
    "brand_watermark": False, # optional: small logo in the corner of the whole video
    "brand_end_text": "SUBSCRIBE FOR THE NEXT EPISODE",
    "telegram_token": "",     # phone alerts: your own Telegram bot's token (from @BotFather)
    "telegram_chat_id": "",   # ... and your chat id
}


def now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def slug(text, n=40):
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return s[:n].strip("-") or "untitled"


def new_id(title):
    return time.strftime("%Y%m%d-%H%M%S-") + slug(title, 30)


def safe_name(text):
    return "".join(c if c.isalnum() or c in " -_" else "_" for c in text).strip() or "video"


def read_json(path, default=None):
    for attempt in range(6):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return default
        except (PermissionError, json.JSONDecodeError):
            if attempt == 5:
                return default
            time.sleep(0.15)


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
    for attempt in range(20):  # a reader may hold the file for a moment on Windows
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            time.sleep(0.1)
    raise PermissionError(f"could not write {path}")


def update_json(path, **kw):
    d = read_json(path, {}) or {}
    d.update(kw)
    write_json(path, d)
    return d


# ---------- generic folders ----------
FOLDERS = {"character": "characters", "season": "seasons", "project": "projects"}


def folder(kind, oid):
    return os.path.join(LIB, FOLDERS[kind], oid)


def main_file(kind, oid):
    return os.path.join(folder(kind, oid), kind + ".json")


def load(kind, oid):
    if not oid or not re.fullmatch(r"[\w.-]+", oid):
        return None
    return read_json(main_file(kind, oid))


def save(kind, obj):
    obj["updated"] = now()
    write_json(main_file(kind, obj["id"]), obj)
    return obj


def all_of(kind):
    base = os.path.join(LIB, FOLDERS[kind])
    out = []
    if os.path.isdir(base):
        for oid in os.listdir(base):
            o = read_json(os.path.join(base, oid, kind + ".json"))
            if o:
                out.append(o)
    return sorted(out, key=lambda o: o.get("updated", ""), reverse=True)


def to_trash(kind, oid):
    src = folder(kind, oid)
    if os.path.isdir(src):
        dst = os.path.join(LIB, "trash", f"{FOLDERS[kind]}-{oid}-{time.strftime('%Y%m%d%H%M%S')}")
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.move(src, dst)


# ---------- settings ----------
def settings():
    s = dict(DEFAULT_SETTINGS)
    s.update(read_json(os.path.join(LIB, "settings.json"), {}) or {})
    return s


def save_settings(changes):
    s = read_json(os.path.join(LIB, "settings.json"), {}) or {}
    s.update({k: v for k, v in changes.items() if k in DEFAULT_SETTINGS})
    write_json(os.path.join(LIB, "settings.json"), s)
    return settings()


# ---------- characters ----------
def new_character(name, look="", voice="", style="", pronoun="he", season_id=None):
    c = {"id": new_id(name), "name": name.strip(), "look": look.strip(), "voice": voice.strip(), "style": style,
         "pronoun": pronoun, "season_id": season_id, "photos": [], "views": {}, "created": now()}
    os.makedirs(folder("character", c["id"]), exist_ok=True)
    return save("character", c)


def tag(name):
    """@Name tag used in scene texts (no spaces)."""
    return "@" + re.sub(r"\W+", "", name)


# ---------- seasons ----------
def new_season(title, style="pixar", cast=(), about=""):
    s = {"id": new_id(title), "title": title.strip(), "style": style, "cast": list(cast), "about": about,
         "episodes": [], "created": now()}
    os.makedirs(folder("season", s["id"]), exist_ok=True)
    return save("season", s)


# ---------- projects ----------
def new_project(title, kind="episode", style="pixar", season_id=None, cast=(), idea="", scenes_wanted=18, options=None):
    p = {"id": new_id(title), "title": title.strip(), "kind": kind, "style": style,
         "style_prefix": STYLES.get(style, STYLES["pixar"])["prefix"], "season_id": season_id, "episode": None,
         "cast": list(cast), "idea": idea, "logline": "", "scenes_wanted": int(scenes_wanted), "scenes": [],
         "language": "en",
         "options": {"approve_pictures": True, "music": False, "music_prompt": "", **(options or {})},
         "created": now()}
    for sub in ("pictures", "clips", "versions", "output"):
        os.makedirs(os.path.join(folder("project", p["id"]), sub), exist_ok=True)
    if season_id:
        s = load("season", season_id)
        if s:
            s["episodes"].append(p["id"])
            p["episode"] = len(s["episodes"])
            save("season", s)
    return save("project", p)


def pfile(pid, name):
    return os.path.join(folder("project", pid), name)


def status(pid):
    return read_json(pfile(pid, "status.json"), {}) or {}


def set_status(pid, **kw):
    return update_json(pfile(pid, "status.json"), **kw, updated=now())


def results(pid):
    return read_json(pfile(pid, "results.json"), {}) or {}


def set_result(pid, sid, **kw):
    r = results(pid)
    r.setdefault(sid, {}).update(kw)
    write_json(pfile(pid, "results.json"), r)


def publish(pid):
    return read_json(pfile(pid, "publish.json"), {}) or {}


def next_scene_id(p):
    nums = [int(s["id"][1:]) for s in p["scenes"] if re.fullmatch(r"s\d+", s.get("id", ""))]
    return f"s{(max(nums) if nums else 0) + 1:03d}"


# ---------- queue ----------
QUEUE = os.path.join(LIB, "queue.json")


def queue():
    return read_json(QUEUE, []) or []


def save_queue(q):
    write_json(QUEUE, q)


def add_task(task):
    q = queue()
    task.update(id=time.strftime("%Y%m%d%H%M%S") + f"-{len(q) % 1000:03d}", state="waiting", added=now())
    q.append(task)
    save_queue(q)
    return task


def set_task(tid, **kw):
    q = queue()
    for t in q:
        if t["id"] == tid:
            t.update(kw)
    save_queue(q)

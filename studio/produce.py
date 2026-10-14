"""Shri Tools production steps, run by worker.py one task at a time (ComfyUI's python).

sheets    character pictures (front + face) with FLUX.2 Klein, from a description or from photos
write     the story (scenes) with the local Ollama model
pictures  first frame of every scene (Klein, character pictures as references)
clips     one MiniMax H3 clip per scene: acting, lip sync, voices and sounds all from H3 itself
check     quality gate (engine\\scene_qc.py): right line, English only, no invented talking, not silent;
          failed clips are made again with a new seed, every try is kept and the best one wins
final     the clips joined (engine\\assemble.py): 0.3 s crossfades, each clip keeps its own sound, levelled
publish   titles, description, tags, thumbnails, subtitles (.srt) and a vertical Short with captions
Every step skips what is already done, so a stopped or crashed task simply runs again.
"""
import json, os, re, shutil, subprocess, sys, time, urllib.error, wave, zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import store  # noqa: E402
import musicvideo as music  # noqa: E402  (the music video steps; not the MusicGen script in engine)

ENGINE = os.path.join(store.ROOT, "engine")
sys.path.insert(0, ENGINE)
from talk_clip import COMFY_DIR, call, ensure_comfy, stop_comfy, build as h3_graph  # noqa: E402

CFG = store.CFG
PY = CFG["comfy_python"]
FFMPEG = CFG["ffmpeg"]
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"  # draws Indian-script text
KLEIN_UNET, KLEIN_TE, KLEIN_VAE = "flux-2-klein-4b-fp8.safetensors", "qwen_3_4b.safetensors", "flux2-vae.safetensors"
H3_FRAMES, FPS = 124, 24

# ---- MiniMax H3 acting prompt (wrapper v4: the text that made SHRI Episode 2 pass every check) ----
HEAD = ("For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.\n\n"
        "integrated_multimodal_description: [Shot 1] A scene from {look}, in exactly the same visual style as "
        "<Picture 1>: ")
KEEP = (" Their faces, bodies, clothes and colors, the composition and the setting of <Picture 1> are preserved, "
        "and the camera moves gently and smoothly.")
TALK = (" The characters shown in <Picture 1> come alive and act out exactly what is described, with expressive faces "
        "and body language. The speaking character opens the mouth and speaks the line, lips, mouth and jaw moving "
        "precisely in sync with every syllable, and the mouth closes when the line ends. The line is spoken in clear, "
        "natural {lang}. Apart from this one line nobody says anything, and the people in the background do not talk."
        + KEEP + "\n\noverall_soundscape: The spoken line in clear {lang}, natural and close to the microphone, with "
        "quiet sound effects and ambience that match the actions and the setting{extra}. No other voices, no other "
        "speech, no other language, no crowd chatter.\n\nnon_diegetic_music: N/A")
SILENT = (" Everything shown in <Picture 1> comes alive and moves exactly as described, with natural body language. "
          "This shot has no dialogue: nobody speaks, talks or shouts, the people in the background do not talk, all "
          "mouths stay closed." + KEEP + "\n\noverall_soundscape: Clear, rich, clearly audible sound effects and "
          "ambience that match every action and the setting, exactly the sounds described{extra}. No human voices, "
          "no speech in any language.\n\nnon_diegetic_music: N/A")
DASHES = {0x2010: "-", 0x2011: "-", 0x2012: "-", 0x2013: "-", 0x00a0: " ", 0x202f: " "}  # story model's odd hyphens
INDIC_TEXT = re.compile(r"[؀-ۿऀ-෿]")  # Urdu, Devanagari ... Malayalam scripts
ARABIC_TEXT = re.compile(r"[؀-ۿ]")
BAD_SOUND_WORDS = re.compile(r"\b(silence|silent|silently|quiet|quietly|hush|tense|standoff)\b", re.I)


def run(args, **kw):
    return subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", **kw)


def seconds(path):
    import av
    c = av.open(path)
    v = c.streams.video[0]
    d = float(v.duration * v.time_base) if v.duration else c.duration / 1e6
    c.close()
    return d


def seed_for(*parts):
    return zlib.crc32("|".join(map(str, parts)).encode()) % 2_000_000_000


class Cancelled(Exception):
    pass


class Producer:
    def __init__(self, task):
        self.task = task
        self.pid = task.get("project")
        self.st = store.settings()
        self.p = store.load("project", self.pid) if self.pid else None
        self.dir = store.folder("project", self.pid) if self.pid else None
        self.comfy_used_for = None  # "klein" / "h3": H3 needs a clean ComfyUI after pictures

    # ---------- bookkeeping ----------
    def log(self, msg):
        line = time.strftime("%H:%M:%S ") + msg
        print(line, flush=True)
        if self.dir:
            with open(os.path.join(self.dir, "log.txt"), "a", encoding="utf-8") as f:
                f.write(time.strftime("%Y-%m-%d ") + line + "\n")
            s = store.status(self.pid)
            store.set_status(self.pid, log=(s.get("log") or [])[-60:] + [line])

    def status(self, **kw):
        if self.pid:
            store.set_status(self.pid, **kw)

    def reload(self):
        self.p = store.load("project", self.pid)
        return self.p

    def chars(self):
        out = []
        for cid in self.p.get("cast", []):
            c = store.load("character", cid)
            if c:
                out.append(c)
        return out

    def look(self, c):
        """The character's look in this video: the project's own costume for it ("looks": {character id: text},
        e.g. a night episode without sunglasses), else the character card's look."""
        return ((self.p or {}).get("looks") or {}).get(c["id"]) or c.get("look") or ""

    def path(self, sub, name):
        return os.path.join(self.dir, sub, name)

    def targets(self, need):
        """Scenes this task works on: the task's own list (forced), else every scene still missing the file."""
        ids = self.task.get("scenes")
        if ids:
            return [s for s in self.p["scenes"] if s["id"] in ids]
        return [s for s in self.p["scenes"] if not os.path.exists(need(s))]

    # ---------- ComfyUI ----------
    def comfy(self, graph, out_noext, use):
        """Queue a graph, wait, copy the result to out_noext + ext. Restarts ComfyUI after an out-of-memory crash."""
        server = CFG["comfy_url"]
        if self.comfy_used_for and self.comfy_used_for != use:
            stop_comfy(server)  # free the other model family completely (4 GB GPU, 24 GB RAM)
        self.comfy_used_for = use
        for attempt in range(1, 4):
            ensure_comfy(server)
            try:
                pid = call(server + "/prompt", {"prompt": graph})["prompt_id"]
            except urllib.error.HTTPError as e:
                raise RuntimeError("ComfyUI refused the job: " + e.read().decode("utf-8", "replace")[:1500])
            except OSError:
                time.sleep(10)
                continue
            while True:
                time.sleep(5)
                try:
                    h = call(f"{server}/history/{pid}").get(pid)
                except OSError:
                    h = "crashed"
                    break
                if not h:
                    continue
                stt = h.get("status", {})
                if stt.get("status_str") == "error":
                    msgs = json.dumps(stt.get("messages"))[-1500:]
                    if "interrupt" in msgs.lower():
                        raise Cancelled()
                    raise RuntimeError("ComfyUI error: " + msgs)
                for node in h.get("outputs", {}).values():
                    for key in ("images", "videos", "gifs", "audio"):
                        for f in node.get(key, []):
                            src = os.path.join(COMFY_DIR, "output", f.get("subfolder", ""), f["filename"])
                            dst = out_noext + os.path.splitext(f["filename"])[1]
                            os.makedirs(os.path.dirname(dst), exist_ok=True)
                            shutil.copy(src, dst)
                            return dst
                raise RuntimeError("ComfyUI finished without an output")
            self.log(f"ComfyUI stopped (probably out of memory) - restarting it (try {attempt})")
            stop_comfy(server)
            time.sleep(15)
        return None

    def to_input(self, src, name):
        dst = os.path.join(COMFY_DIR, "input", name)
        shutil.copy(src, dst)
        return name

    def klein_graph(self, prompt, refs, w, h, seed, prefix):
        g = {
            "1": {"class_type": "UNETLoader", "inputs": {"unet_name": KLEIN_UNET, "weight_dtype": "default"}},
            "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": KLEIN_TE, "type": "flux2", "device": "default"}},
            "3": {"class_type": "VAELoader", "inputs": {"vae_name": KLEIN_VAE}},
            "4": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["2", 0]}},
            "5": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["4", 0]}},
        }
        pos, neg = ["4", 0], ["5", 0]
        for i, name in enumerate(refs):  # every reference picture becomes a reference latent (image 1, 2, ...)
            n = 10 + i * 10
            g[str(n)] = {"class_type": "LoadImage", "inputs": {"image": name}}
            g[str(n + 1)] = {"class_type": "ImageScaleToTotalPixels", "inputs": {
                "upscale_method": "lanczos", "megapixels": 1, "resolution_steps": 1, "image": [str(n), 0]}}
            g[str(n + 2)] = {"class_type": "VAEEncode", "inputs": {"pixels": [str(n + 1), 0], "vae": ["3", 0]}}
            g[str(n + 3)] = {"class_type": "ReferenceLatent", "inputs": {"conditioning": pos, "latent": [str(n + 2), 0]}}
            g[str(n + 4)] = {"class_type": "ReferenceLatent", "inputs": {"conditioning": neg, "latent": [str(n + 2), 0]}}
            pos, neg = [str(n + 3), 0], [str(n + 4), 0]
        g.update({
            "6": {"class_type": "CFGGuider", "inputs": {"cfg": 1, "model": ["1", 0], "positive": pos, "negative": neg}},
            "7": {"class_type": "EmptyFlux2LatentImage", "inputs": {"width": w, "height": h, "batch_size": 1}},
            "8": {"class_type": "Flux2Scheduler", "inputs": {"steps": 4, "width": w, "height": h}},
            "9": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
            "90": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
            "91": {"class_type": "SamplerCustomAdvanced", "inputs": {
                "noise": ["9", 0], "guider": ["6", 0], "sampler": ["90", 0], "sigmas": ["8", 0], "latent_image": ["7", 0]}},
            "92": {"class_type": "VAEDecode", "inputs": {"samples": ["91", 0], "vae": ["3", 0]}},
            "93": {"class_type": "SaveImage", "inputs": {"filename_prefix": prefix, "images": ["92", 0]}},
        })
        return g

    # ---------- characters ----------
    def make_sheet(self, cid, force=False):
        c = store.load("character", cid)
        cdir = store.folder("character", cid)
        style = store.STYLES.get(c.get("style") or (self.p or {}).get("style") or "pixar", store.STYLES["pixar"])
        prefix = (self.p or {}).get("style_prefix") if self.p and not c.get("style") else style["prefix"]
        views = dict(c.get("views") or {})
        seed = c.get("seed") or seed_for(cid)
        if force:
            seed = seed_for(cid, time.time())
            for v in ("front", "face"):
                old = os.path.join(cdir, v + ".png")
                if os.path.exists(old):
                    os.makedirs(os.path.join(cdir, "old"), exist_ok=True)
                    shutil.move(old, os.path.join(cdir, "old", f"{v}_{int(time.time())}.png"))
                views.pop(v, None)
        photos = [os.path.join(cdir, "photos", f) for f in c.get("photos", [])]
        photos = [p for p in photos if os.path.exists(p)][:3]
        who = (f"the person from the reference photos as {c['name']}, keeping their exact face, {c['look']}" if photos
               else f"{c['name']}, {c['look']}")
        if "front" not in views:
            self.log(f"{c['name']}: full-body character picture")
            refs = [self.to_input(p, f"stb_{cid[:24]}_photo{i}{os.path.splitext(p)[1]}") for i, p in enumerate(photos)]
            prompt = (f"{prefix}. Character design reference of {who}. Full body from head to feet, standing straight, "
                      "facing the camera, arms relaxed, friendly neutral expression, plain light grey studio background, "
                      "even soft light, one character only")
            if not self.comfy(self.klein_graph(prompt, refs, 768, 1024, seed, f"shritub/{cid}_front"),
                              os.path.join(cdir, "front"), "klein"):
                raise RuntimeError("no character picture (ComfyUI kept crashing)")
            views["front"] = "front.png"
        if "face" not in views:
            self.log(f"{c['name']}: close-up face picture")
            ref = self.to_input(os.path.join(cdir, "front.png"), f"stb_{cid[:24]}_front.png")
            refs = [ref] + [self.to_input(p, f"stb_{cid[:24]}_photo{i}{os.path.splitext(p)[1]}")
                            for i, p in enumerate(photos[:1])]
            prompt = (f"{prefix}. Close-up portrait of exactly the same character as in image 1, {c['name']}, "
                      f"{c['look']}. Head and shoulders, facing the camera, warm friendly expression, plain light grey "
                      "studio background, even soft light, one character only")
            if not self.comfy(self.klein_graph(prompt, refs, 832, 832, seed + 1, f"shritub/{cid}_face"),
                              os.path.join(cdir, "face"), "klein"):
                raise RuntimeError("no face picture (ComfyUI kept crashing)")
            views["face"] = "face.png"
        c = store.load("character", cid)
        c.update(views=views, seed=seed)
        store.save("character", c)

    def step_sheets(self):
        for c in self.chars():
            if not {"front", "face"} <= set(c.get("views") or {}):
                self.status(stage="sheets", label=f"Character pictures: {c['name']}")
                self.make_sheet(c["id"])

    # ---------- story ----------
    def step_write(self):
        import writer
        self.status(stage="write", label="Writing the story (local AI, a few minutes)")
        stop_comfy(CFG["comfy_url"])  # the story model needs the memory
        chars = self.chars()
        prev, theme = [], ""
        if self.p.get("season_id"):
            season = store.load("season", self.p["season_id"]) or {}
            theme = season.get("about", "")
            for oid in season.get("episodes", []):
                if oid == self.pid:
                    break
                o = store.load("project", oid)
                if o:
                    prev.append(f"{o['title']}: {o.get('logline') or o.get('idea', '')[:200]}")
        self.log(f"writing {self.p['scenes_wanted']} scenes with {self.st['story_model']}")
        t0 = time.time()
        out = writer.write_story(self.p, chars, prev, theme)
        names = {store.tag(c["name"]).lower(): store.tag(c["name"]) for c in chars}
        by_name = {c["name"].lower(): c["name"] for c in chars}

        def fix(t):  # every cast name as its @Tag (the tag is what puts the character picture into the scene)
            t = (t or "").translate(DASHES)
            t = re.sub(r"@(\w+)", lambda m: names.get("@" + m.group(1).lower(), "@" + m.group(1)), t or "")
            for c in chars:
                t = re.sub(rf"(?<![@\w]){re.escape(c['name'])}(?:'s)?\b",
                           lambda m: store.tag(c["name"]) + m.group(0)[len(c["name"]):], t)
            return t
        scenes = []
        for i, s in enumerate(out.get("scenes", []), 1):
            kind = "talk" if s.get("kind") == "talk" and (s.get("line") or "").strip() else "action"
            sounds = BAD_SOUND_WORDS.sub("", s.get("sounds") or "").strip(" ,.")
            spk = (s.get("speaker") or "").lstrip("@").strip()
            picture = fix(s.get("picture"))
            if kind == "talk" and spk:  # the proven talking shot: one face filling the frame
                tagname = store.tag(by_name.get(spk.lower(), spk))
                if not re.search(rf"close-up of {re.escape(tagname)}", picture, re.I):
                    rest = re.sub(rf"^\s*(tight\s+)?(head-and-shoulders\s+)?close-?up(\s+of)?\s*,?\s*({re.escape(tagname)})?\s*,?\s*"
                                  r"(his |her |their )?(face filling (the )?frame)?\s*,?\s*", "", picture, flags=re.I)
                    picture = f"tight head-and-shoulders close-up of {tagname}, face filling the frame, {rest}".rstrip(", ")
            scenes.append({
                "id": f"s{i:03d}", "kind": kind, "picture": picture, "action": fix(s.get("action")),
                "speaker": by_name.get(spk.lower(), spk) if kind == "talk" else "",
                "line": (s.get("line") or "").strip().strip('"\u201c\u201d') if kind == "talk" else "",
                "line_en": (s.get("line_en") or "").strip().strip('"\u201c\u201d')
                if kind == "talk" and store.language(self.p) != "en" else "",
                "tone": (s.get("tone") or "says").strip() if kind == "talk" else "", "sounds": sounds,
                "camera": fix(s.get("camera"))})
        if not scenes:
            raise RuntimeError("the story model returned no scenes - try again or write the scenes yourself")
        p = self.reload()
        p["scenes"] = scenes
        p["logline"] = out.get("logline", "")
        p["plot"] = out.get("plot", "")
        p["hook_text"] = (out.get("hook_text") or "").translate(DASHES).strip()
        if not p.get("title") or p["title"].lower().startswith("untitled"):
            p["title"] = out.get("title") or p["title"]
        p["story_title_suggestion"] = out.get("title", "")
        store.save("project", p)
        self.p = p
        self.log(f"story ready: {len(scenes)} scenes in {(time.time() - t0) / 60:.1f} min")

    # ---------- pictures ----------
    def picture_prompt(self, s, chars):
        by_tag = {store.tag(c["name"]).lower(): c for c in chars}
        used = []

        def sub(m):
            c = by_tag.get("@" + m.group(1).lower())
            if not c:
                return m.group(1)
            if c not in used:
                used.append(c)
            return f"{c['name']} ({self.look(c)})" if self.look(c) else c["name"]
        text = re.sub(r"@(\w+)", sub, s["picture"])
        if s["kind"] == "talk" and s.get("speaker"):
            c = next((c for c in chars if c["name"].lower() == s["speaker"].lower()), None)
            if c and c not in used:
                used.insert(0, c)
        refs = []
        for c in used[:3]:
            v = c.get("views") or {}
            pick = ("face" if s["kind"] == "talk" else "front")
            f = v.get(pick) or v.get("front") or v.get("face")
            if f and os.path.exists(os.path.join(store.folder("character", c["id"]), f)):
                refs.append((c, os.path.join(store.folder("character", c["id"]), f)))
        if refs:
            text += ". " + " ".join(f"{c['name']} looks exactly like the character in image {i + 1}."
                                    for i, (c, _) in enumerate(refs))
        elif not used:  # in cartoon styles Klein likes to give objects faces (a paper boat with eyes)
            text += ". No characters or creatures in this shot; objects are ordinary objects with no faces or eyes."
        return f"{self.p['style_prefix']}. {text}", [r[1] for r in refs]

    def step_pictures(self):
        todo = self.targets(lambda s: self.path("pictures", s["id"] + ".png"))
        chars = self.chars()
        w, h = self.st["picture_size"]
        for n, s in enumerate(todo, 1):
            self.status(stage="pictures", label=f"Pictures {n}/{len(todo)}", done=n - 1, total=len(todo))
            out = self.path("pictures", s["id"] + ".png")
            if os.path.exists(out):
                shutil.move(out, self.path("versions", f"{s['id']}_picture_{int(time.time())}.png"))
            prompt, refs = self.picture_prompt(s, chars)
            names = [self.to_input(r, f"stb_{self.pid[:15]}_{s['id']}_ref{i}{os.path.splitext(r)[1]}")
                     for i, r in enumerate(refs)]
            seed = seed_for(self.pid, s["id"], "pic", time.time() if self.task.get("scenes") else 0)
            t0 = time.time()
            if not self.comfy(self.klein_graph(prompt, names, w, h, seed, f"shritub/{self.pid[:15]}_{s['id']}"),
                              out[:-4], "klein"):
                raise RuntimeError(f"{s['id']}: no picture (ComfyUI kept crashing)")
            store.set_result(self.pid, s["id"], picture_v=int(time.time()), picture_prompt=prompt, picture_seed=seed,
                             clip_outdated=os.path.exists(self.path("clips", s["id"] + ".mp4")))
            self.log(f"{s['id']} picture ({len(refs)} character refs) {time.time() - t0:.0f} s")
        if self.st.get("picture_check", True) and todo:
            self.check_pictures(todo, chars)

    def check_pictures(self, todo, chars):
        """A vision AI looks at every new picture; a doubled or extra person, a missing character or a different
        action -> the picture is drawn again with a new seed (picture_check_tries times). The best try stays."""
        import picqc
        tries = int(self.st.get("picture_check_tries", 2))
        best = {}  # scene id -> (number of problems, file in versions)
        todo = list(todo)
        for r in range(tries + 1):
            stop_comfy(CFG["comfy_url"])  # the vision model needs the GPU
            self.comfy_used_for = None
            bad = []
            for n, s in enumerate(todo, 1):
                self.status(stage="pictures", label=f"Checking pictures {n}/{len(todo)} (round {r + 1})",
                            done=n - 1, total=len(todo))
                out = self.path("pictures", s["id"] + ".png")
                try:
                    res = picqc.check(out, s, chars, self.look, st=self.st)
                except Exception as e:  # no vision model: the pictures stay as they are
                    picqc.unload(self.st)
                    self.log(f"picture check not possible ({str(e)[:150]}) - pictures not checked")
                    return
                store.set_result(self.pid, s["id"], picture_check=res["reasons"] or "ok")
                if res["ok"]:
                    continue
                self.log(f"  {s['id']} picture: {'; '.join(res['reasons'])}")
                keep = self.path("versions", f"{s['id']}_picture_try{r + 1}_{int(time.time())}.png")
                shutil.copy(out, keep)
                if s["id"] not in best or len(res["reasons"]) < best[s["id"]][0]:
                    best[s["id"]] = (len(res["reasons"]), keep)
                bad.append(s)
            picqc.unload(self.st)  # Klein (redraw) or H3 (videos) come next and need the GPU
            self.log(f"picture check round {r + 1}: {len(todo) - len(bad)} OK" +
                     (f", draw again {', '.join(s['id'] for s in bad)}" if bad and r < tries else ""))
            if not bad:
                return
            if r == tries:
                for s in bad:  # still not right: keep the try with the fewest problems, and say so
                    shutil.copy(best[s["id"]][1], self.path("pictures", s["id"] + ".png"))
                    self.log(f"  {s['id']}: kept the best try - please look at this picture")
                return
            w, h = self.st["picture_size"]
            for s in bad:
                out = self.path("pictures", s["id"] + ".png")
                prompt, refs = self.picture_prompt(s, chars)
                names = [self.to_input(f, f"stb_{self.pid[:15]}_{s['id']}_ref{i}{os.path.splitext(f)[1]}")
                         for i, f in enumerate(refs)]
                seed = seed_for(self.pid, s["id"], "pic", time.time())
                self.status(stage="pictures", label=f"Drawing {s['id']} again (round {r + 1})")
                if not self.comfy(self.klein_graph(prompt, names, w, h, seed, f"shritub/{self.pid[:15]}_{s['id']}"),
                                  out[:-4], "klein"):
                    raise RuntimeError(f"{s['id']}: no picture (ComfyUI kept crashing)")
                store.set_result(self.pid, s["id"], picture_v=int(time.time()), picture_prompt=prompt,
                                 picture_seed=seed)
                self.log(f"  {s['id']} drawn again")
            todo = bad

    # ---------- H3 clips ----------
    def h3_prompt(self, s, chars):
        """The detailed H3 prompt: the shot, who is in it (look + voice, the same words every scene), the acting
        beats in order, the camera, then the spoken line in H3's dialogue tag, then the sounds."""
        by_tag = {store.tag(c["name"]).lower(): c for c in chars}
        seen = []

        def names(t):
            def sub(m):
                c = by_tag.get("@" + m.group(1).lower())
                if c and c not in seen:
                    seen.append(c)
                return c["name"] if c else m.group(1)
            return re.sub(r"@(\w+)", sub, t or "")
        look = store.STYLES.get(self.p["style"], store.STYLES["pixar"])["h3"]
        picture, action = names(s["picture"]).rstrip(". "), names(s.get("action")).strip()
        sounds = BAD_SOUND_WORDS.sub("", s.get("sounds") or "").strip(" ,.")
        talk = s["kind"] == "talk" and s.get("line")
        spk = next((c for c in chars if c["name"].lower() == (s.get("speaker") or "").lower()), None) if talk else None
        if spk and spk not in seen:
            seen.insert(0, spk)
        who = " ".join(f"{c['name']} is {self.look(c).rstrip('.')}." for c in seen if self.look(c))
        camera = (s.get("camera") or "").strip().rstrip(".") or (
            "static close-up at eye level with a very slow, gentle push-in" if talk else "smooth, gentle camera movement that follows the action")
        if talk:
            name = spk["name"] if spk else (s.get("speaker") or "The character")
            voice = (spk or {}).get("voice") or "a natural voice"
            if not re.match(r"(a|an|the|his|her)\b", voice, re.I):
                voice = "a " + voice
            line = s["line"].strip().strip('"\u201c\u201d')
            others = [c["name"] for c in seen if c is not spk]
            listen = f" {' and '.join(others)} only listen{'s' if len(others) == 1 else ''}, mouth closed." if others else ""
            lang = store.LANGUAGES[store.language(self.p, s)]["h3"]
            desc = (f"{picture}. {who} {action} Then {name} {s.get('tone') or 'says'} in {voice}: "
                    f"<d>[{lang}] {line}</d> {name}'s mouth shapes every word clearly.{listen} Camera: {camera}.")
            body = TALK.format(extra=f", softly: {sounds}" if sounds else "", lang=lang)
        else:
            desc = (f"{picture}. {who} {action} Camera: {camera}. Nobody speaks."
                    + (f" Only {sounds}." if sounds else ""))
            body = SILENT.format(extra=f": {sounds}" if sounds else "")
        return HEAD.format(look=look) + re.sub(r"\s+", " ", desc).strip() + body

    def make_clip(self, s, chars, seed):
        if self.p.get("kind") == "music":  # a music video shot: lip sync to its piece of the song
            return music.make_music_clip(self, s, chars, seed)
        out = self.path("clips", s["id"])
        prompt = self.h3_prompt(s, chars)
        open(out + ".txt", "w", encoding="utf-8").write(prompt)
        image = self.to_input(self.path("pictures", s["id"] + ".png"), f"stb_{self.pid[:15]}_{s['id']}.png")
        for w, h in self.st["clip_sizes"]:
            graph = h3_graph(image, None, prompt, w, h, H3_FRAMES, seed, f"shritub/{self.pid[:15]}_{s['id']}")
            got = self.comfy(graph, out + "_new", "h3")
            if got:
                os.replace(got, out + ".mp4")
                return f"{w}x{h}"
            self.log(f"{s['id']}: {w}x{h} failed - trying a smaller size")
        raise RuntimeError(f"{s['id']}: no clip at any size")

    def step_clips(self):
        todo = self.targets(lambda s: self.path("clips", s["id"] + ".mp4"))
        todo = [s for s in todo if os.path.exists(self.path("pictures", s["id"] + ".png"))]
        chars = self.chars()
        times = []
        for n, s in enumerate(todo, 1):
            eta = (sum(times) / len(times) if times else 12 * 60) * (len(todo) - n + 1) / 60
            self.status(stage="clips", label=f"Videos {n}/{len(todo)}", done=n - 1, total=len(todo), eta_min=round(eta))
            old = self.path("clips", s["id"] + ".mp4")
            if os.path.exists(old):
                shutil.move(old, self.path("versions", f"{s['id']}_clip_{int(time.time())}.mp4"))
            seed = seed_for(self.pid, s["id"], "clip", time.time() if self.task.get("scenes") else 0)
            t0 = time.time()
            size = self.make_clip(s, chars, seed)
            times.append(time.time() - t0)
            store.set_result(self.pid, s["id"], clip_v=int(time.time()), clip_seed=seed, clip_size=size,
                             clip_outdated=False, qc=None)
            self.log(f"{s['id']} video {size} in {times[-1] / 60:.1f} min" +
                     (f' - "{s["line"]}"' if s["kind"] == "talk" else ""))

    # ---------- quality gate ----------
    def qc(self, ids):
        lines = {s["id"]: (s.get("line") or "") if s["kind"] == "talk" else "" for s in self.p["scenes"]}
        store.write_json(os.path.join(self.dir, "lines.json"), lines)
        store.write_json(os.path.join(self.dir, "langs.json"),  # scene_qc listens for this language (English if missing)
                         {s["id"]: store.LANGUAGES[store.language(self.p, s)]["whisper"] for s in self.p["scenes"]})
        out = os.path.join(self.dir, "qc_last.json")
        if os.path.exists(out):
            os.remove(out)
        r = run([PY, os.path.join(ENGINE, "scene_qc.py"), self.dir, os.path.join(self.dir, "clips"), out] + ids,
                env=dict(os.environ, HF_HUB_OFFLINE="1"))
        if not os.path.exists(out):
            raise RuntimeError("the check failed: " + (r.stderr or r.stdout)[-800:])
        res = store.read_json(out, {})
        if self.st.get("picture_check", True):
            self.look_at_clips(res)
        return res

    def look_at_clips(self, res):
        """H3 sometimes lets a person walk into a shot whose picture was right: the vision AI looks at a frame near
        the end of every clip; an extra or doubled person fails the clip, so the check round makes it again."""
        import picqc
        chars = self.chars()
        stop_comfy(CFG["comfy_url"])  # the vision model needs the GPU
        self.comfy_used_for = None
        by_id = {s["id"]: s for s in self.p["scenes"]}
        try:
            for n, (sid, v) in enumerate(sorted(res.items()), 1):
                s = by_id.get(sid)
                if not s:
                    continue
                self.status(stage="check", label=f"Looking at videos {n}/{len(res)}")
                frame = os.path.join(self.dir, "versions", f"_look_{sid}.jpg")
                run([FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-sseof", "-0.6", "-i",
                     self.path("clips", sid + ".mp4"), "-frames:v", "1", "-q:v", "3", frame])
                if not os.path.exists(frame):
                    continue
                try:
                    look = picqc.check_frame(frame, s, chars, self.look, st=self.st)
                except Exception as e:
                    self.log(f"looking at the videos not possible ({str(e)[:150]})")
                    return
                finally:
                    if os.path.exists(frame):
                        os.remove(frame)
                if not look["ok"]:
                    v["ok"] = False
                    v["problems"] = list(v.get("problems") or []) + look["reasons"]
        finally:
            picqc.unload(self.st)

    def step_check(self):
        if self.p.get("kind") == "music":  # the song is the sound: only who appears in the clips is checked
            return self.check_music_clips()
        have = [s["id"] for s in self.p["scenes"] if os.path.exists(self.path("clips", s["id"] + ".mp4"))]
        ids = self.task.get("scenes") or have
        ids = [i for i in ids if i in have]
        if not ids:
            return
        chars = self.chars()
        rounds = int(self.st["qc_rounds"])
        tries = {}
        for r in range(rounds + 1):
            self.status(stage="check", label=f"Checking {len(ids)} videos (round {r + 1})", done=r, total=rounds + 1)
            res = self.qc(ids)
            for sid, v in res.items():
                copy = self.path("versions", f"{sid}_try{r}_{int(time.time())}.mp4")
                shutil.copy(self.path("clips", sid + ".mp4"), copy)
                tries.setdefault(sid, []).append((copy, v))
                store.set_result(self.pid, sid, qc=v)
            bad = sorted(s for s, v in res.items() if not v["ok"])
            self.log(f"check round {r + 1}: {len(res) - len(bad)} OK" + (f", remake {', '.join(bad)}" if bad else ""))
            for sid in bad:
                self.log(f"  {sid}: {', '.join(res[sid]['problems'])} (heard '{res[sid]['heard'][:80]}')")
            if not bad or r == rounds:
                break
            scenes = [s for s in self.p["scenes"] if s["id"] in bad]
            for n, s in enumerate(scenes, 1):
                self.status(stage="check", label=f"Remaking {s['id']} ({n}/{len(scenes)}, round {r + 1})")
                seed = seed_for(self.pid, s["id"], "clip", "qc", r, time.time())
                self.make_clip(s, chars, seed)
                store.set_result(self.pid, s["id"], clip_v=int(time.time()), clip_seed=seed)
            ids = bad
        rank = lambda t: (t[1]["ok"], -len(t[1]["problems"]), t[1]["rms"] >= 0.003, t[1].get("match") or 0, t[1]["rms"])
        for sid, ts in tries.items():
            best = max(ts, key=rank)
            if best is not ts[-1]:
                shutil.copy(best[0], self.path("clips", sid + ".mp4"))
                self.log(f"{sid}: keeps its better try ({'OK' if best[1]['ok'] else ', '.join(best[1]['problems'])})")
            store.set_result(self.pid, sid, qc=best[1], clip_v=int(time.time()))

    def check_music_clips(self):
        """Music video clips: the vision AI looks at the end of each clip (a person who walked in, a doubled
        character); a bad clip is made once more, and the better of the two stays."""
        if not self.st.get("picture_check", True):
            return
        have = [s["id"] for s in self.p["scenes"] if os.path.exists(self.path("clips", s["id"] + ".mp4"))]
        ids = [i for i in (self.task.get("scenes") or have) if i in have]
        if not ids:
            return
        res = {sid: {"ok": True, "problems": [], "heard": "", "rms": 1.0} for sid in ids}
        self.look_at_clips(res)
        bad = sorted(s for s, v in res.items() if not v["ok"])
        self.log(f"looked at {len(ids)} videos: {len(ids) - len(bad)} OK" + (f", remake {', '.join(bad)}" if bad else ""))
        if not bad:
            return
        chars = self.chars()
        for sid in bad:
            self.log(f"  {sid}: {', '.join(res[sid]['problems'])}")
            first = self.path("versions", f"{sid}_look1_{int(time.time())}.mp4")
            shutil.copy(self.path("clips", sid + ".mp4"), first)
            s = next(x for x in self.p["scenes"] if x["id"] == sid)
            self.status(stage="check", label=f"Remaking {sid}")
            seed = seed_for(self.pid, sid, "clip", "look", time.time())
            self.make_clip(s, chars, seed)
            store.set_result(self.pid, sid, clip_v=int(time.time()), clip_seed=seed)
        again = {sid: {"ok": True, "problems": [], "heard": "", "rms": 1.0} for sid in bad}
        self.look_at_clips(again)
        for sid in bad:
            if again[sid]["ok"]:
                self.log(f"  {sid}: new clip OK")
            else:
                self.log(f"  {sid}: still {', '.join(again[sid]['problems'])} - kept the new clip, please look")

    # ---------- final video ----------
    def clip_list(self, ids=None):
        return [self.path("clips", s["id"] + ".mp4") for s in self.p["scenes"]
                if (ids is None or s["id"] in ids) and os.path.exists(self.path("clips", s["id"] + ".mp4"))]

    def step_final(self):
        if self.p.get("kind") == "music":
            return music.step_music_final(self)
        clips = self.clip_list()
        if not clips:
            raise RuntimeError("no videos to join yet")
        self.status(stage="final", label=f"Joining {len(clips)} videos")
        final = self.path("output", "final.mp4")
        args = [PY, "-I", os.path.join(ENGINE, "assemble.py"), final] + clips + \
               ["--xfade", str(self.st["xfade"]), "--level", str(self.st["level"])]
        opt = self.p.get("options", {})
        if opt.get("music"):
            bgm = self.path("output", "music.wav")  # not "music": that name is the music video module
            if not os.path.exists(bgm):
                self.status(stage="final", label="Making background music")
                stop_comfy(CFG["comfy_url"])
                prompt = opt.get("music_prompt") or "gentle cinematic background score, soft, warm"
                r = run([CFG["music_python"], os.path.join(ENGINE, "music.py"), bgm, prompt,
                         f"{len(clips) * 5:.0f}"])
                self.log("music: " + ("ready" if os.path.exists(bgm) else "failed " + (r.stderr or r.stdout)[-300:]))
            if os.path.exists(bgm):
                args += ["--music", bgm, "--music-volume", str(self.st["music_volume"])]
        if os.path.exists(final):
            shutil.copy(final, self.path("versions", f"final_{int(time.time())}.mp4"))
        r = run(args)
        if r.returncode != 0 or not os.path.exists(final):
            raise RuntimeError("joining the videos failed: " + (r.stderr or r.stdout)[-800:])
        self.add_brand(final)
        copy = os.path.join(store.ROOT, "output", store.safe_name(self.p["title"]) + ".mp4")
        shutil.copy(final, copy)
        self.status(final_seconds=round(seconds(final), 1), final_made=store.now(), copy=copy)
        self.log(f"final video {seconds(final):.1f} s -> {copy}")

    def add_brand(self, final):
        """Logo intro / end card / corner logo (Settings). A failure never costs the video: it stays without logo."""
        import brand
        try:
            done = brand.apply(final, FFMPEG, self.log)
            self.status(brand_offset=2.0 if done and self.st.get("brand_intro") else 0.0)
        except Exception as e:
            self.status(brand_offset=0.0)
            self.log(f"logo not added ({str(e)[:200]}) - the video is fine without it")

    # ---------- publish kit ----------
    def timeline(self, ids=None):
        """(scene, clip, start in the joined video, clip length) for every clip, using the same crossfade."""
        out, t = [], 0.0
        for s in self.p["scenes"]:
            c = self.path("clips", s["id"] + ".mp4")
            if (ids is not None and s["id"] not in ids) or not os.path.exists(c):
                continue
            d = seconds(c)
            out.append((s, c, t, d))
            t += d - self.st["xfade"]
        return out

    def speech_windows(self, items):
        """When the line is spoken in the joined video: (start, end) per talking scene, from the loudness of the
        clip (in talking clips H3 keeps the ambience low, so the voice stands out). Never overlapping."""
        import av
        import numpy as np
        out, last_end = {}, 0.0
        for s, c, t, d in items:
            if s["kind"] != "talk" or not s.get("line"):
                continue
            a0, b0 = 0.3, d - 0.3
            try:
                con = av.open(c)
                res = av.AudioResampler(format="flt", layout="mono", rate=16000)
                a = np.concatenate([r.to_ndarray().reshape(-1) for f in con.decode(audio=0) for r in res.resample(f)])
                con.close()
                hop = 800  # 50 ms
                n = len(a) // hop
                e = np.sqrt((a[:n * hop].reshape(n, hop) ** 2).mean(1))
                e = np.convolve(e, np.ones(3) / 3, mode="same")
                on = np.where(e > max(0.2 * np.percentile(e, 95), 1e-4))[0]
                if len(on) and (on[-1] - on[0]) * 0.05 > 0.5:
                    a0, b0 = max(0.0, on[0] * 0.05 - 0.1), min(d, (on[-1] + 1) * 0.05 + 0.25)
            except Exception as ex:  # keep the whole clip as the window
                self.log(f"speech timing {s['id']}: {str(ex)[:150]}")
            start = max(t + a0, last_end + 0.05)
            end = max(start + 0.8, min(t + b0, t + d - self.st["xfade"]))  # not into the next scene's crossfade
            out[s["id"]] = (start, end)
            last_end = end
        return out

    def srt(self, items, win, path):
        def ts(x):
            ms = int(round(x * 1000))
            return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"
        rows = []
        off = float(store.status(self.pid).get("brand_offset") or 0)  # the logo intro moves everything later
        for s, c, t, d in items:
            if s["id"] in win:
                a, b = win[s["id"]]
                a, b = a + off, b + off
                text = s["line"] + (f"\n({s['line_en']})" if s.get("line_en") and store.language(self.p, s) != "en" else "")
                rows.append(f"{len(rows) + 1}\n{ts(a)} --> {ts(b)}\n{text}\n")
        open(path, "w", encoding="utf-8").write("\n".join(rows))
        return len(rows)

    FONT_FILES = {"impact": ["impact.ttf", "seguibl.ttf", "arialbd.ttf"],
                  "caption": ["seguibl.ttf", "segoeuib.ttf", "arialbd.ttf"]}

    def font_path(self, kind="impact", text=""):
        names = self.FONT_FILES[kind]
        if INDIC_TEXT.search(text or ""):  # Indian scripts: Nirmala UI (comes with Windows); Urdu: Arial
            names = ["arialbd.ttf", "segoeuib.ttf"] if ARABIC_TEXT.search(text) else ["NIRMALAB.TTF", "Nirmala.ttc"]
        for f in names:
            p = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", f)
            if os.path.exists(p):
                return p
        return None

    def font(self, size, kind="impact", text=""):
        from PIL import ImageFont
        p = self.font_path(kind, text)
        return ImageFont.truetype(p, size) if p else ImageFont.load_default()

    def html_text(self, img, text, box, size, kind="impact", align="left"):
        """Indian-script text drawn by Edge (headless): a browser joins Indian letters correctly, this Pillow has no
        text shaping. Same look as glow_text: white, black outline, green glow, shrunk until it fits the box."""
        import html, tempfile
        from PIL import Image
        W, H = img.size
        x, y, w, h = box
        stroke = max(4, size // 14)
        family = '"Segoe UI", Arial' if ARABIC_TEXT.search(text) else '"Nirmala UI"'
        work = tempfile.mkdtemp(prefix="stb_text_")
        page = os.path.join(work, "text.html")
        open(page, "w", encoding="utf-8").write(f"""<!doctype html><html><head><meta charset="utf-8"><style>
html,body{{margin:0;background:transparent;width:{W}px;height:{H}px;overflow:hidden}}
#b{{position:absolute;left:{x}px;top:{y}px;width:{w}px;height:{h}px;display:flex;align-items:center;
justify-content:{'center' if align == 'center' else 'flex-start'};text-align:{align};font-family:{family};
font-weight:700;color:#fff;line-height:1.3;font-size:{size}px;-webkit-text-stroke:{stroke * 2}px #000;
paint-order:stroke fill;text-shadow:0 0 {stroke * 3}px #39ff88,0 0 {stroke * 5}px #39ff88,0 0 {stroke * 7}px #39ff88}}
</style></head><body><div id="b"><div id="t">{html.escape(text)}</div></div><script>
let s={size};const b=document.getElementById("b"),t=document.getElementById("t");
while(s>24&&(t.getBoundingClientRect().height>{h}||t.scrollWidth>{w})){{s-=4;b.style.fontSize=s+"px";}}
</script></body></html>""")
        out = os.path.join(work, "text.png")
        run([EDGE, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--default-background-color=00000000",
             f"--user-data-dir={os.path.join(work, 'edge')}", f"--window-size={W},{H}", f"--screenshot={out}",
             "file:///" + page.replace("\\", "/")], timeout=120)
        if not os.path.exists(out):
            raise RuntimeError("Edge could not draw the Indian-language text")
        layer = Image.open(out).convert("RGBA")
        layer.load()
        if layer.size != img.size:
            layer = layer.crop((0, 0, W, H))
        shutil.rmtree(work, ignore_errors=True)
        img.alpha_composite(layer)
        return img

    def glow_text(self, img, text, box, size, kind="impact", align="left"):
        """White text with a black outline and a green glow, wrapped into box (x, y, w, h)."""
        from PIL import Image, ImageDraw, ImageFilter
        if INDIC_TEXT.search(text or ""):
            return self.html_text(img, text, box, size, kind, align)
        x, y, w, h = box
        while size > 24:
            f = self.font(size, kind)
            words, lines, cur = text.split(), [], ""
            for wd in words:
                t = (cur + " " + wd).strip()
                if f.getlength(t) <= w or not cur:
                    cur = t
                else:
                    lines.append(cur)
                    cur = wd
            lines.append(cur)
            lh = int(size * 1.08)
            if lh * len(lines) <= h and all(f.getlength(l) <= w for l in lines):
                break
            size -= 6
        layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        stroke = max(4, size // 14)
        ty = y + (h - lh * len(lines)) // 2
        pos = []
        for i, l in enumerate(lines):
            lx = x + (w - f.getlength(l)) / 2 if align == "center" else x
            pos.append((lx, ty + i * lh, l))
        glow = Image.new("RGBA", img.size, (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow)
        for lx, ly, l in pos:
            gd.text((lx, ly), l, font=f, fill=(57, 255, 136, 255), stroke_width=stroke * 3, stroke_fill=(57, 255, 136, 255))
        glow = glow.filter(ImageFilter.GaussianBlur(stroke * 2.2))
        for lx, ly, l in pos:
            d.text((lx, ly), l, font=f, fill=(255, 255, 255, 255), stroke_width=stroke, stroke_fill=(0, 0, 0, 255))
        img.alpha_composite(glow)
        img.alpha_composite(layer)
        return img

    def thumbnail(self, base, text, out, episode=None):
        from PIL import Image, ImageDraw, ImageOps
        im = ImageOps.fit(Image.open(base).convert("RGB"), (1280, 720), Image.LANCZOS).convert("RGBA")
        shade = Image.new("RGBA", im.size, (0, 0, 0, 0))
        sd = ImageDraw.Draw(shade)
        for i in range(640):  # dark fade on the left, where the text goes
            sd.line([(i, 0), (i, 720)], fill=(0, 0, 0, int(190 * (1 - i / 640) ** 1.4)))
        im.alpha_composite(shade)
        self.glow_text(im, text.upper(), (48, 60, 640, 600), 150)
        if episode:
            d = ImageDraw.Draw(im)
            f = self.font(44, "caption")
            label = f"EP {episode}"
            tw = f.getlength(label)
            d.rounded_rectangle([1280 - tw - 80, 36, 1240, 106], 16, fill=(0, 0, 0, 220), outline=(57, 255, 136, 255), width=4)
            d.text((1280 - tw - 60, 44), label, font=f, fill=(255, 255, 255, 255))
        im.convert("RGB").save(out, quality=92)

    def pick_short(self, items):
        """The hook scene (scene 1) first, then the contiguous run of scenes with the most spoken lines that still
        fits the Short length (later wins a tie, so the ending/payoff is usually in)."""
        maxs = self.st["short_max_seconds"]
        if not items:
            return []
        hook, rest = items[0], items[1:]
        maxs -= hook[3] - self.st["xfade"]
        best, best_key = [], (-1, -1)
        items = rest
        for i in range(len(items)):
            t, run_ = 0.0, []
            for it in items[i:]:
                if t + it[3] - self.st["xfade"] > maxs:
                    break
                run_.append(it)
                t += it[3] - self.st["xfade"]
            key = (sum(1 for it in run_ if it[0]["kind"] == "talk"), len(run_) >= 6, i)
            if run_ and key > best_key:
                best, best_key = run_, key
        return [hook[0]["id"]] + [it[0]["id"] for it in best]

    def make_short(self, ids, title, out):
        from PIL import Image
        items = self.timeline(ids)
        if not items:
            raise RuntimeError("no videos for the Short")
        tmp = self.path("output", "short_16x9.mp4")
        r = run([PY, "-I", os.path.join(ENGINE, "assemble.py"), tmp] + [c for _, c, _, _ in items] +
                ["--xfade", str(self.st["xfade"]), "--level", str(self.st["level"])])
        if r.returncode != 0 or not os.path.exists(tmp):
            raise RuntimeError("Short: joining failed " + (r.stderr or r.stdout)[-500:])
        win = self.speech_windows(items)
        work = self.path("output", "short_parts")
        os.makedirs(work, exist_ok=True)
        top = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
        title = re.sub(r"#\w+", "", re.sub(r"\s*[|\-–]\s*(youtube\s*)?shorts?\b.*$", "", title, flags=re.I)).strip()
        self.glow_text(top, title.upper(), (60, 70, 960, 230), 92, "impact", "center")
        top.save(os.path.join(work, "title.png"))
        inputs, chain, last = ["-i", tmp, "-i", os.path.join(work, "title.png")], [], "v1"
        fc = ("[0:v]split[a][b];[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
              "gblur=sigma=40,eq=brightness=-0.22[bg];[b]crop=ih*4/5:ih,scale=1080:1350[fg];"
              "[bg][fg]overlay=0:300[v0];[v0][1:v]overlay=0:0[v1]")
        k = 2
        for s, c, t, d in items:
            if s["id"] not in win:
                continue
            a, b = win[s["id"]]
            cap = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
            self.glow_text(cap, s["line"], (70, 1660, 940, 220), 70, "caption", "center")
            p = os.path.join(work, f"cap_{s['id']}.png")
            cap.save(p)
            inputs += ["-i", p]
            chain.append(f"[{last}][{k}:v]overlay=0:0:enable='between(t,{a:.2f},{b:.2f})'[v{k}]")
            last, k = f"v{k}", k + 1
        fc = ";".join([fc] + chain)
        r = run([FFMPEG, "-y", "-loglevel", "error"] + inputs + ["-filter_complex", fc, "-map", f"[{last}]",
                "-map", "0:a?", "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", out])
        if r.returncode != 0 or not os.path.exists(out):
            raise RuntimeError("Short: render failed " + r.stderr[-800:])
        return round(seconds(out), 1)

    def step_publish(self):
        if self.p.get("kind") == "music":
            return music.step_music_publish(self)
        import writer
        final = self.path("output", "final.mp4")
        if not os.path.exists(final):
            raise RuntimeError("make the final video first")
        chars = self.chars()
        pub = store.publish(self.pid)
        lines = [s["line"] for s in self.p["scenes"] if s["kind"] == "talk" and s.get("line")]
        if not pub.get("titles") or self.task.get("texts"):
            self.status(stage="publish", label="Writing titles, description and tags (local AI)")
            stop_comfy(CFG["comfy_url"])
            try:
                pub.update(writer.publish_texts(self.p, chars, lines))
                self.log("titles, description and tags ready")
            except Exception as e:
                self.log(f"AI texts failed ({str(e)[:200]}) - simple texts used, edit them in Publish")
                pub.update(titles=[self.p["title"]], description=(self.p.get("logline") or self.p.get("idea", "")) +
                           "\n\n" + self.st["ai_disclosure"], tags=[c["name"] for c in chars], hashtags=["#shorts"],
                           thumbnail_texts=[self.p["title"]], short_title=self.p["title"], short_description="")
            store.write_json(store.pfile(self.pid, "publish.json"), pub)
        # subtitles
        self.status(stage="publish", label="Subtitles")
        items = self.timeline()
        n = self.srt(items, self.speech_windows(items), self.path("output", "subtitles.srt"))
        pub["subtitles"] = "output/subtitles.srt"
        self.log(f"subtitles: {n} lines")
        # thumbnails: one new dramatic picture + the two strongest close-ups
        self.status(stage="publish", label="Thumbnails")
        texts = (pub.get("thumbnail_texts") or [self.p["title"]]) * 3
        if self.p.get("hook_text"):  # the episode's own hook words go on the first thumbnail
            texts = [self.p["hook_text"]] + texts
        bases = []
        hero = chars[0] if chars else None
        tb = self.path("output", "thumb_base.png")
        if not os.path.exists(tb) or self.task.get("thumbs"):
            look = f"{hero['name']} ({hero.get('look', '')})" if hero else "the main character"
            refs = []
            if hero and (hero.get("views") or {}).get("face"):
                refs = [self.to_input(os.path.join(store.folder("character", hero["id"]), hero["views"]["face"]),
                                      f"stb_{self.pid[:15]}_thumbref.png")]
            story = self.p.get("logline") or self.p.get("idea") or self.p["title"]
            prompt = (f"{self.p['style_prefix']}. Dramatic YouTube thumbnail: {look}, big expressive emotion, looking "
                      f"toward the viewer, placed on the right side of the frame, bold simple background from this "
                      f"story: {story[:300]}. High contrast, strong rim light, empty space on the left"
                      + (". The character looks exactly like the character in image 1." if refs else ""))
            if not self.comfy(self.klein_graph(prompt, refs, 1280, 720, seed_for(self.pid, "thumb", time.time()),
                                               f"shritub/{self.pid[:15]}_thumb"), tb[:-4], "klein"):
                self.log("thumbnail picture failed - scene pictures used")
        if os.path.exists(tb):
            bases.append(tb)
        talk = [s for s in self.p["scenes"] if s["kind"] == "talk"] + [s for s in self.p["scenes"] if s["kind"] != "talk"]
        for s in talk:
            p = self.path("pictures", s["id"] + ".png")
            if os.path.exists(p) and len(bases) < 3:
                bases.append(p)
        thumbs = []
        for i, b in enumerate(bases[:3]):
            out = self.path("output", f"thumb{i + 1}.jpg")
            self.thumbnail(b, texts[i], out, self.p.get("episode"))
            thumbs.append(f"output/thumb{i + 1}.jpg")
        pub["thumbnails"] = thumbs
        pub.setdefault("thumbnail_choice", 0)
        self.log(f"{len(thumbs)} thumbnails")
        # Short
        self.status(stage="publish", label="Making the Short (9:16)")
        ids = self.p.get("short_scenes") or self.pick_short(items)
        secs = self.make_short(ids, self.p.get("hook_text") or pub.get("short_title") or self.p["title"],
                               self.path("output", "short1.mp4"))
        pub["short"] = {"file": "output/short1.mp4", "scenes": ids, "seconds": secs}
        self.log(f"Short: {len(ids)} scenes, {secs} s")
        # more Shorts from the same video: the ending (payoff / moral) and the best middle moment
        shorts = [dict(pub["short"], title=self.p.get("hook_text") or pub.get("short_title") or self.p["title"])]
        for n, (kind, sids) in enumerate(self.more_shorts(items, ids)[:max(0, int(self.st.get("shorts_count", 3)) - 1)],
                                         2):
            lines_in = [s["line"] for s in self.p["scenes"] if s["id"] in sids and s["kind"] == "talk" and s.get("line")]
            title = (self.p["title"] if kind == "story" else lines_in[-1] if lines_in else
                     (pub.get("titles") or [self.p["title"]])[min(n - 1, len(pub.get("titles") or [1]) - 1)])
            self.status(stage="publish", label=f"Making Short {n} (9:16)")
            try:
                secs = self.make_short(sids, title, self.path("output", f"short{n}.mp4"))
            except Exception as e:
                self.log(f"Short {n} failed ({str(e)[:150]})")
                continue
            shorts.append({"file": f"output/short{n}.mp4", "scenes": sids, "seconds": secs, "title": title,
                           "kind": kind})
            self.log(f"Short {n} ({kind}): {len(sids)} scenes, {secs} s")
        pub["shorts"] = shorts
        pub["made"] = store.now()
        store.write_json(store.pfile(self.pid, "publish.json"), pub)

    def more_shorts(self, items, first):
        """Scene lists for extra Shorts. The first Short is the hook + the climax; these add "story" (the opening and
        set-up, ~45 s, if it is not mostly the first Short's scenes) and "moment" (the 3 scenes around the strongest
        spoken line in the second half, ~15 s - a punchy Reel)."""
        xf = self.st["xfade"]
        plans = []
        story, t = [], 0.0
        for it in items:
            if t + it[3] - xf > min(45, self.st["short_max_seconds"]):
                break
            story.append(it[0]["id"])
            t += it[3] - xf
        if len(story) >= 4 and len(set(story) & set(first)) < 0.7 * len(story):
            plans.append(("story", story))
        half = len(items) // 2
        best, best_key = [], (-1, -1)
        for i in range(half, max(half + 1, len(items) - 2)):
            win = items[i:i + 3]
            key = (sum(1 for it in win if it[0]["kind"] == "talk"), i)  # later wins a tie: the payoff
            if len(win) == 3 and key > best_key:
                best, best_key = [it[0]["id"] for it in win], key
        if best and best != story[-3:]:
            plans.append(("moment", best))
        return plans

    # ---------- run ----------
    def step_translate(self):
        """Dubbing: this project is a copy of an episode in another language - translate its spoken lines."""
        import writer
        p = self.p
        if p.get("translated"):
            return
        talk = [s for s in p["scenes"] if s["kind"] == "talk" and s.get("line")]
        lang = store.LANGUAGES[store.language(p)]
        self.status(stage="translate", label=f"Translating {len(talk)} lines to {lang['name']} (local AI)")
        stop_comfy(CFG["comfy_url"])
        out = writer.translate_lines(p, [{"id": s["id"], "line": s["line"], "speaker": s.get("speaker", ""),
                                          "tone": s.get("tone", "")} for s in talk], p.get("hook_text", ""), p["title"])
        by = {x.get("id"): (x.get("line") or "").strip() for x in out.get("lines", [])}
        missing = [s["id"] for s in talk if not by.get(s["id"])]
        if missing:
            raise RuntimeError("the story AI did not translate " + ", ".join(missing) + " - press Retry")
        p = self.reload()
        for s in p["scenes"]:
            if s["id"] in by:
                s["line_en"] = s.get("line_en") or s["line"]
                s["line"] = by[s["id"]]
                s.pop("language", None)
        if (out.get("hook_text") or "").strip():
            p["hook_text"] = out["hook_text"].strip()
        p["translated"] = True
        store.save("project", p)
        self.p = p
        self.log(f"{len(talk)} lines translated to {lang['name']}")

    def step_song(self):
        music.step_song(self)

    def step_plan(self):
        music.step_plan(self)

    STEPS = {"song": "step_song", "plan": "step_plan", "translate": "step_translate",
             "sheets": "step_sheets", "write": "step_write", "pictures": "step_pictures", "clips": "step_clips",
             "check": "step_check", "final": "step_final", "publish": "step_publish"}

    def run(self):
        if self.task["kind"] == "ideas":  # ideas for a season's next episodes (story AI only)
            import writer
            season = store.load("season", self.task["season"])
            stop_comfy(CFG["comfy_url"])
            chars = [c for c in (store.load("character", cid) for cid in season.get("cast", [])) if c]
            prev = [p["title"] + ": " + (p.get("logline") or p.get("idea", ""))[:160]
                    for p in (store.load("project", e) for e in season.get("episodes", [])) if p]
            ideas = writer.season_ideas(season, chars, prev)
            season = store.load("season", self.task["season"])
            season["ideas"] = ideas
            season["ideas_made"] = store.now()
            store.save("season", season)
            return
        if self.task["kind"] == "sheet":
            c = self.task["character"]
            store.update_json(os.path.join(store.folder("character", c), "status.json"), state="running", started=store.now())
            try:
                self.make_sheet(c, force=self.task.get("force", False))
                store.update_json(os.path.join(store.folder("character", c), "status.json"), state="done", error=None)
            except Exception as e:
                store.update_json(os.path.join(store.folder("character", c), "status.json"), state="failed", error=str(e)[:500])
                raise
            return
        steps = self.task["steps"]
        self.status(state="running", task=self.task["id"], steps=steps, error=None, started=store.now(), eta_min=None)
        self.log(f"=== {', '.join(steps)}" + (f" for {', '.join(self.task['scenes'])}" if self.task.get("scenes") else "") + " ===")
        for step in steps:
            self.reload()
            self.status(stage=step, label=step, done=None, total=None)
            getattr(self, self.STEPS[step])()
        if self.task.get("then_approve"):
            self.status(state="approve", stage="approve", label="Pictures ready - check them, then make the videos")
            self.log("pictures ready: check them in Storyboard, then press Make videos")
        else:
            self.status(state="done", stage="done", label="Done", finished=store.now())
            self.log("=== done ===")

"""Music videos: a song made with MiniMax Music 3, then one MiniMax H3 shot per 5.17 s of the song, lip-synced to it.

song   lyrics + music description (the story AI writes them if empty), then MiniMax Music 3 in ComfyUI -> output/song.wav
plan   Whisper finds where the singing is; the story AI writes one shot per 124-frame piece of the song: the singer in
       close-up while words are sung ("sing"), story / dance shots in between ("action")
clips  every shot is an H3 clip with ITS piece of the song as the audio guide, so lips and motion follow the music
final  the clips back to back (each is exactly its piece of the song) under the original song -> perfect sync
publish YouTube texts, thumbnails, lyric subtitles and a 9:16 Short cut from the final video
Called from produce.Producer (kind == "music"). Named musicvideo.py so it never mixes with engine/music.py.
"""
import json, math, os, re, shutil, time

import lyrics
import store

H3_FRAMES, FPS = 124, 24
SHOT = H3_FRAMES / FPS  # 5.1667 s of song per shot
MM3_DIT = "minimax_music3_dit_int8_convrot.safetensors"
MM3_TE = "minimax_music3_text_encoder_pruned_int8_convrot.safetensors"
MM3_VAE = "minimax_music3_dav.safetensors"

# music styles: what goes into the song description (MiniMax Music 3 "Global Metadata" + arrangement hints)
MUSIC_STYLES = {
    "bollywood_romantic": ("Bollywood romantic", "Bollywood romantic ballad, 88 BPM, lush strings, soft tabla, acoustic guitar, warm piano, emotional build into a soaring chorus"),
    "bollywood_dance": ("Bollywood dance", "Bollywood dance number, 120 BPM, dhol and dholak groove, punchy synth bass, claps, brass stabs, festive and energetic"),
    "indian_folk": ("Indian folk", "Indian folk song, 100 BPM, dholak, harmonium, bansuri flute, ektara, village celebration feel"),
    "devotional": ("Devotional / bhajan", "Indian devotional bhajan, 80 BPM, harmonium, tabla, temple bells, manjira cymbals, peaceful and uplifting"),
    "kids_rhyme": ("Kids rhyme", "cheerful children's song, 112 BPM, xylophone, ukulele, glockenspiel, hand claps, bouncy and simple, easy to sing along"),
    "lullaby": ("Lullaby", "soft lullaby, 68 BPM, music box, gentle piano, warm pads, very calm and tender"),
    "pop": ("Pop", "modern pop, 104 BPM, catchy hook, bright synths, punchy drums, clean bass, radio-ready mix"),
    "rock": ("Rock", "energetic rock, 132 BPM, distorted electric guitars, live drums, driving bass, big anthemic chorus"),
    "rap": ("Hip-hop / rap", "Indian hip-hop, 90 BPM, heavy 808 bass, trap hi-hats, dark piano loop, confident rap verses and a sung hook"),
    "lofi": ("Lo-fi chill", "lo-fi chillhop, 78 BPM, warm Rhodes chords, dusty drums, vinyl crackle, relaxed and dreamy"),
    "edm": ("EDM", "EDM festival track, 128 BPM, big build-ups and drops, sidechained supersaws, four-on-the-floor kick"),
    "ghazal": ("Ghazal / classical", "classical ghazal, 70 BPM, sitar, tabla, harmonium, sarangi, slow and poetic"),
    "carnatic_fusion": ("South Indian fusion", "South Indian Carnatic fusion, 96 BPM, veena, mridangam, violin, modern drums, bright and rhythmic"),
    "patriotic": ("Patriotic", "patriotic anthem, 100 BPM, marching snare, brass, strings, choir, proud and inspiring"),
}
VOCALS = {
    "female": "a clear, expressive female lead vocal",
    "male": "a warm, powerful male lead vocal",
    "duet": "a male and female duet, trading verses and singing the chorus together",
    "child": "a sweet, bright child's voice",
    "choir": "a joyful group choir",
    "none": "no vocals, instrumental only",
}

SING = (" The characters shown in <Picture 1> come alive and perform exactly as described, like a professional music "
        "video, with expressive faces and body language. The singer's lips, mouth and jaw move precisely in sync with every "
        "sung syllable of the song, breathing between phrases. Nobody speaks; apart from the song nobody makes a sound."
        "{keep}\n\noverall_soundscape: The song: {genre}, {vocal}, sung in {lang}, exactly as in the audio. No speech, no "
        "other voices.\n\nnon_diegetic_music: {genre}")
DANCE = (" Everything shown in <Picture 1> comes alive and moves exactly as described, in time with the rhythm of the "
         "music, like a professional music video. Nobody speaks or sings in this shot, all mouths stay closed.{keep}"
         "\n\noverall_soundscape: The music of the song continues: {genre}. No speech.\n\nnon_diegetic_music: {genre}")
# sung close-ups the shot plan did not describe get one of these, in turn
SING_POSES = ["singing with emotion", "singing with a big happy smile", "singing with eyes closed, feeling the music",
              "singing and clapping", "singing with one hand raised high", "singing with a hand on the heart",
              "singing and swaying to the beat", "singing straight to the viewer"]


def audio_seconds(path):
    import av
    c = av.open(path)
    try:
        a = c.streams.audio[0]
        if a.duration is not None:
            return float(a.duration * a.time_base)
        return c.duration / 1e6
    finally:
        c.close()


def style_text(m):
    key = m.get("genre") or "pop"
    return MUSIC_STYLES[key][1] if key in MUSIC_STYLES else key


# ---------- song ----------
def step_song(prod):
    import writer
    from produce import CFG, FFMPEG, run, seconds, seed_for, stop_comfy
    p = prod.p
    m = p.setdefault("music", {})
    lang = store.LANGUAGES[store.language(p)]
    if not (m.get("lyrics") or "").strip() or not (m.get("caption") or "").strip():
        prod.status(stage="song", label="Writing the lyrics (local AI)")
        stop_comfy(CFG["comfy_url"])
        out = writer.write_song(p, prod.chars(), style_text(m), VOCALS.get(m.get("vocal") or "female", ""))
        p = prod.reload()
        m = p.setdefault("music", {})
        if not (m.get("lyrics") or "").strip():
            m["lyrics"] = out["lyrics"].strip()
        if not (m.get("caption") or "").strip():
            m["caption"] = out["caption"].strip()
        for k in ("logline", "hook_text"):
            if out.get(k) and not p.get(k):
                p[k] = out[k]
        if not p.get("title") or p["title"].lower().startswith("untitled"):
            p["title"] = out.get("title") or p["title"]
        store.save("project", p)
        prod.p = p
        prod.log(f"lyrics and music description ready ({lang['name']})")
    want = float(m.get("seconds") or 60)
    seed = seed_for(p["id"], "song", m.get("take", 0))
    graph = {
        "1": {"class_type": "CLIPLoader", "inputs": {"clip_name": MM3_TE, "type": "minimax", "device": "default"}},
        "2": {"class_type": "MiniMaxMusic3TextEncode", "inputs": {
            "clip": ["1", 0], "caption": m["caption"], "lyrics": m["lyrics"], "seed": seed, "max_duration": want,
            "cfg_scale": 1.7, "top_k": 50}},
        "3": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["2", 0]}},
        "4": {"class_type": "EmptyMiniMaxMusic3LatentAudio", "inputs": {"seconds": ["2", 1], "batch_size": 1}},
        "5": {"class_type": "UNETLoader", "inputs": {"unet_name": MM3_DIT, "weight_dtype": "default"}},
        "6": {"class_type": "KSampler", "inputs": {
            "model": ["5", 0], "positive": ["2", 0], "negative": ["3", 0], "latent_image": ["4", 0], "seed": seed,
            "steps": 30, "cfg": 1.7, "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0}},
        "7": {"class_type": "VAELoader", "inputs": {"vae_name": MM3_VAE}},
        "8": {"class_type": "VAEDecodeAudioTiled", "inputs": {"samples": ["6", 0], "vae": ["7", 0], "tile_size": 1536,
                                                              "overlap": 64}},
        "9": {"class_type": "SaveAudio", "inputs": {"audio": ["8", 0], "filename_prefix": f"shritub/{p['id'][:15]}_song"}},
    }
    prod.status(stage="song", label=f"Making the song with MiniMax Music 3 (~{want:.0f} s of music)")
    t0 = time.time()
    got = prod.comfy(graph, prod.path("output", "song_raw"), "music")
    if not got:
        raise RuntimeError("no song (ComfyUI kept crashing)")
    song = prod.path("output", "song.wav")
    r = run([FFMPEG, "-y", "-loglevel", "error", "-i", got, "-ar", "44100", "-ac", "2", song])
    if r.returncode or not os.path.exists(song):
        raise RuntimeError("song conversion failed: " + (r.stderr or "")[-300:])
    secs = audio_seconds(song)
    p = prod.reload()
    p.setdefault("music", {})["song_seconds"] = round(secs, 2)
    store.save("project", p)
    prod.p = p
    prod.log(f"song ready: {secs:.1f} s in {(time.time() - t0) / 60:.1f} min")


# ---------- plan ----------
def sung_words(prod, song, lang_code):
    """[(start, end, word)] of the sung words (Whisper small with word timestamps, in the song's language).
    The song is heard one shot-long piece at a time: on a whole song Whisper loses its place on repeated lines and loops
    ("तालिया तालिया तालिया ...", words with zero length), on 5-second pieces it almost never does. A word heard more
    than 3 times in a row is still dropped."""
    import av
    import numpy as np
    from transformers import pipeline
    c = av.open(song)
    res = av.AudioResampler(format="flt", layout="mono", rate=16000)
    a = np.concatenate([r.to_ndarray().reshape(-1) for f in c.decode(audio=0) for r in res.resample(f)]).astype(np.float32)
    c.close()
    whisper = store.LANGUAGES[lang_code]["whisper"]
    for name in ("openai/whisper-small", "openai/whisper-base"):
        try:
            asr = pipeline("automatic-speech-recognition", model=name, device=-1)
            break
        except Exception:
            continue
    rows, step = [], int(SHOT * 16000)
    for k in range(0, len(a), step):
        piece = a[k:k + step]
        if len(piece) < 8000:  # under half a second
            break
        out = asr({"raw": piece, "sampling_rate": 16000}, return_timestamps="word",
                  generate_kwargs={"language": whisper, "task": "transcribe", "no_repeat_ngram_size": 3})
        t0, t1 = k / 16000, (k + len(piece)) / 16000
        for ch in out.get("chunks", []):
            s, e = ch.get("timestamp") or (None, None)
            w = (ch.get("text") or "").strip()
            if s is None or not w:
                continue
            if len(rows) >= 3 and all(r[2] == w for r in rows[-3:]):
                continue
            rows.append((t0 + float(s), min(t1, t0 + float(e if e is not None else s + 0.4)), w))
    return rows


def shot_voices(song, shots):
    """For each sung shot "female" / "male" (or None): the singing voice's pitch (YIN, 75-450 Hz). A man sings around
    85-200 Hz, a woman around 180-400 Hz. Instruments blur it, so only strongly periodic frames count. MiniMax Music
    sometimes gives the chorus to a woman although the song is for a male singer - then that shot needs a woman."""
    import av
    import numpy as np
    c = av.open(song)
    res = av.AudioResampler(format="flt", layout="mono", rate=16000)
    a = np.concatenate([r.to_ndarray().reshape(-1) for f in c.decode(audio=0) for r in res.resample(f)]).astype(np.float32)
    c.close()
    sr, n, hop = 16000, 1024, 512
    tmin, tmax = sr // 450, sr // 75
    w = n - tmax
    out = {}
    for sh in shots:
        if not sh["sung"]:
            continue
        seg = a[int(sh["start"] * sr):int(sh["end"] * sr)]
        if len(seg) < n * 2:
            continue
        fr = np.lib.stride_tricks.sliding_window_view(seg, n)[::hop]
        fr = fr - fr.mean(axis=1, keepdims=True)
        fr = fr[np.sqrt((fr ** 2).mean(axis=1)) > 0.01]
        if len(fr) < 8:
            continue
        d = np.stack([((fr[:, :w] - fr[:, t:t + w]) ** 2).sum(axis=1) for t in range(1, tmax + 1)], axis=1)
        cm = d * np.arange(1, tmax + 1) / np.maximum(np.cumsum(d, axis=1), 1e-9)
        lag = tmin + np.argmin(cm[:, tmin - 1:tmax], axis=1)
        ok = cm[np.arange(len(cm)), lag - 1] < 0.25
        hz = sr / lag[ok]
        if len(hz) >= 8:
            out[sh["id"]] = "female" if (hz > 200).mean() > 0.5 and np.median(hz) > 190 else "male"
    return out


def gender(c):
    return {"she": "female", "he": "male"}.get((c or {}).get("pronoun"))


def step_plan(prod):
    import writer
    from produce import CFG, seconds, stop_comfy
    p = prod.p
    m = p.get("music", {})
    song = prod.path("output", "song.wav")
    if not os.path.exists(song):
        raise RuntimeError("make the song first")
    secs = audio_seconds(song)
    n = max(1, math.ceil(secs / SHOT - 0.15))  # the last bit shorter than ~0.8 s is dropped
    prod.status(stage="plan", label="Finding where the singing is")
    heard = sung_words(prod, song, store.language(p)) if m.get("vocal") != "none" else []
    # the real lyrics on the timeline (Whisper's own spelling only when there are no lyrics or nothing matched)
    times, rows, lwords = lyrics.align(m.get("lyrics"), heard)
    if rows:
        prod.log(f"lyrics found in the song: {len(rows)} lines, {len(times)} words")
    else:
        rows = [{"start": s, "end": e, "text": w} for s, e, w in heard]
    shots = []
    for i in range(n):
        a, b = i * SHOT, min(secs, (i + 1) * SHOT)
        got = (lyrics.sung_between(times, lwords, a, b) if times else
               [w for s, e, w in heard if a - 0.15 <= (s + e) / 2 < b])
        # a shot with less than 2 sung words is an instrumental part: a story / dance shot, mouths closed
        shots.append({"id": f"s{i + 1:03d}", "start": round(a, 2), "end": round(b, 2),
                      "sung": " ".join(got) if len(got) >= 2 else ""})
    store.write_json(prod.path("", "song_words.json"), rows)
    # a song sung from start to end would be all close-ups of one face: when more than half the shots are sung, every
    # second shot of a sung run becomes a story shot (the song plays on under it, so it stays in sync)
    if sum(1 for sh in shots if sh["sung"]) > len(shots) / 2:
        run = 0
        for sh in shots:
            run = run + 1 if sh["sung"] else 0
            if run and run % 2 == 0:
                sh["sung"] = ""
        prod.log(f"mostly sung: {sum(1 for sh in shots if sh['sung'])} close-ups kept, story shots in between")
    # who really sings each shot (adult voices only: a child's voice is high whether boy or girl)
    voices = shot_voices(song, shots) if m.get("vocal") in ("male", "female", "duet") else {}
    if voices:
        prod.log("voices: " + ", ".join(f"{k} {v}" for k, v in sorted(voices.items())))
    if p.get("scenes"):  # a new plan: the old pictures and videos no longer fit, keep them in versions
        stamp = int(time.time())
        for sub in ("pictures", "clips"):
            for f in os.listdir(prod.path(sub, "")):
                if f.endswith((".png", ".mp4")):
                    shutil.move(prod.path(sub, f), prod.path("versions", f"old_{stamp}_{f}"))
    prod.status(stage="plan", label=f"Planning {n} shots (local AI)")
    stop_comfy(CFG["comfy_url"])
    chars = prod.chars()
    sing_list, story_list = m.get("sing_shots") or [], m.get("story_shots") or []
    if sing_list or story_list:  # a hand-written storyboard: no AI needed, used in order (and again if too short)
        planned, ns, na = [], 0, 0
        for sh in shots:
            src = (sing_list[ns % len(sing_list)] if sh["sung"] and sing_list else
                   story_list[na % len(story_list)] if story_list else {})
            if sh["sung"] and sing_list:
                ns += 1
            elif story_list:
                na += 1
            src = {"picture": src} if isinstance(src, str) else dict(src)
            planned.append({"id": sh["id"], **src})
        prod.log(f"hand-written storyboard used ({len(sing_list)} singing, {len(story_list)} story shots)")
    else:
        try:
            planned = writer.plan_music_shots(p, chars, shots, style_text(m))
        except Exception as e:  # the video still gets made: simple shots from templates
            prod.log(f"shot planning by AI failed ({str(e)[:150]}) - simple shots used")
            planned = []
    by_id = {s.get("id"): s for s in planned if isinstance(s, dict)}
    singer = next((c for c in chars if c["id"] in (m.get("singers") or [])), chars[0] if chars else None)
    stag = store.tag(singer["name"]) if singer else ""
    place = m.get("setting") or "a colorful stage with warm lights"
    singers = [c for c in chars if c["id"] in (m.get("singers") or [])]
    scenes = []
    for k, sh in enumerate(shots):
        got = by_id.get(sh["id"], {})
        sing = bool(sh["sung"]) and bool(singer)
        picture = (got.get("picture") or "").strip()
        who, wtag = singer, stag
        voice = voices.get(sh["id"])
        if sing and voice and gender(singer) and gender(singer) != voice:
            # a woman sings this part but the singer is a man (or the other way round): someone of that voice sings it
            alt = (next((c for c in singers if gender(c) == voice), None) or
                   next((c for c in chars if gender(c) == voice), None))
            if alt:
                who, wtag = alt, store.tag(alt["name"])
                picture = picture.replace(stag, wtag)
                if wtag not in picture:
                    picture = ""
            else:
                prod.log(f"{sh['id']}: a {voice} voice sings here but the cast has no {voice} character")
        if sing and (not picture or "close-up" not in picture.lower()):
            # lip sync needs a close-up: keep the planned moment, only change the framing (and vary the pose, or
            # every sung shot comes out the same picture)
            moment = re.sub(r"^(an? )?((extreme|very) )?((wide|medium|full|long|establishing|low[- ]angle|high[- ]angle) )?"
                            r"(shot|view) of ", "", picture, flags=re.I) if picture else place
            picture = (f"tight head-and-shoulders close-up of {wtag}, face filling the frame, "
                       f"{SING_POSES[k % len(SING_POSES)]}, {moment}")
        if not picture:
            picture = (f"wide shot of {stag} dancing joyfully in {place}" if singer and k % 2 else
                       f"cinematic wide shot of {place}, beautiful light, gentle movement")
        scenes.append({
            "id": sh["id"], "kind": "sing" if sing else "action", "picture": picture,
            "action": (got.get("action") or ("sings with real feeling" if sing else "moves with the rhythm")).strip(),
            "speaker": who["name"] if sing else "", "line": sh["sung"], "line_en": (got.get("line_en") or "").strip(),
            "tone": "sings", "sounds": "", "camera": (got.get("camera") or "slow push-in").strip(),
            "start": sh["start"], "end": sh["end"]})
    p = prod.reload()
    p["scenes"] = scenes
    store.save("project", p)
    prod.p = p
    sung = sum(1 for s in scenes if s["kind"] == "sing")
    prod.log(f"{len(scenes)} shots planned ({sung} singing close-ups, {len(scenes) - sung} story/dance shots)")


# ---------- clips ----------
def h3_music_prompt(prod, s, chars):
    from produce import HEAD, KEEP
    p = prod.p
    m = p.get("music", {})
    by_tag = {store.tag(c["name"]).lower(): c for c in chars}
    seen = []

    def names(t):
        def sub(mm):
            c = by_tag.get("@" + mm.group(1).lower())
            if c and c not in seen:
                seen.append(c)
            return c["name"] if c else mm.group(1)
        return re.sub(r"@(\w+)", sub, t or "")
    look = store.STYLES.get(p["style"], store.STYLES["pixar"])["h3"]
    picture, action = names(s["picture"]).rstrip(". "), names(s.get("action")).strip().rstrip(".")
    who = " ".join(f"{c['name']} is {prod.look(c).rstrip('.')}." for c in seen if prod.look(c))
    camera = (s.get("camera") or "slow push-in").strip().rstrip(".")
    genre = style_text(m).split(",")[0]
    lang = store.LANGUAGES[store.language(p, s)]["h3"]
    vocal = VOCALS.get(m.get("vocal") or "female", "")
    singer = next((c for c in chars if c["name"] == s.get("speaker")), None)
    if singer and m.get("vocal") in ("male", "female", "duet"):  # the voice of whoever sings THIS shot (duets)
        vocal = VOCALS["female" if singer.get("pronoun") == "she" else "male"]
    if s["kind"] == "sing" and s.get("line"):
        name = s.get("speaker") or "The singer"
        desc = (f"{picture}. {who} {name} {action}, singing: <d>[{lang}] {s['line']}</d> Camera: {camera}.")
        body = SING.format(keep=KEEP, genre=genre, vocal=vocal, lang=lang)
    else:
        desc = f"{picture}. {who} {action}. Camera: {camera}."
        body = DANCE.format(keep=KEEP, genre=genre)
    return HEAD.format(look=look) + re.sub(r"\s+", " ", desc).strip() + body


def make_music_clip(prod, s, chars, seed):
    """One H3 clip with its own piece of the song as the audio guide (lips and motion follow the music)."""
    from produce import COMFY_DIR, FFMPEG, h3_graph, run
    out = prod.path("clips", s["id"])
    prompt = h3_music_prompt(prod, s, chars)
    open(out + ".txt", "w", encoding="utf-8").write(prompt)
    image = prod.to_input(prod.path("pictures", s["id"] + ".png"), f"stb_{prod.pid[:15]}_{s['id']}.png")
    guide = f"stb_{prod.pid[:15]}_{s['id']}_song.wav"
    r = run([FFMPEG, "-y", "-loglevel", "error", "-ss", f"{s['start']:.3f}", "-t", f"{SHOT:.4f}",
             "-i", prod.path("output", "song.wav"), "-af", f"apad=whole_dur={SHOT:.4f}", "-ac", "1", "-ar", "24000",
             "-sample_fmt", "s16", os.path.join(COMFY_DIR, "input", guide)])
    if r.returncode:
        raise RuntimeError(f"{s['id']}: cutting the song failed " + (r.stderr or "")[-200:])
    for w, h in prod.st["clip_sizes"]:
        graph = h3_graph(image, guide, prompt, w, h, H3_FRAMES, seed, f"shritub/{prod.pid[:15]}_{s['id']}")
        got = prod.comfy(graph, out + "_new", "h3")
        if got:
            os.replace(got, out + ".mp4")
            return f"{w}x{h}"
        prod.log(f"{s['id']}: {w}x{h} failed - trying a smaller size")
    raise RuntimeError(f"{s['id']}: no clip at any size")


# ---------- final ----------
def step_music_final(prod):
    from produce import FFMPEG, run, seconds
    p = prod.p
    clips = [(s, prod.path("clips", s["id"] + ".mp4")) for s in p["scenes"]]
    missing = [s["id"] for s, c in clips if not os.path.exists(c)]
    if missing:
        raise RuntimeError("videos missing for " + ", ".join(missing))
    prod.status(stage="final", label=f"Putting {len(clips)} shots on the song")
    work = prod.path("output", "music_parts")
    os.makedirs(work, exist_ok=True)
    lst = os.path.join(work, "list.txt")
    with open(lst, "w", encoding="utf-8") as f:
        for s, c in clips:
            f.write(f"file '{c.replace(os.sep, '/')}'\n")
    final = prod.path("output", "final.mp4")
    if os.path.exists(final):
        shutil.copy(final, prod.path("versions", f"final_{int(time.time())}.mp4"))
    song = prod.path("output", "song.wav")
    # every clip is exactly its 124-frame piece of the song: back to back at 24 fps under the original song
    r = run([FFMPEG, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-i", song,
             "-map", "0:v", "-map", "1:a", "-vf", "fps=24,scale=1920:1080:flags=lanczos,format=yuv420p",
             "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-c:a", "aac", "-b:a", "192k", "-shortest",
             "-movflags", "+faststart", final])
    if r.returncode or not os.path.exists(final):
        raise RuntimeError("joining the music video failed: " + (r.stderr or "")[-600:])
    prod.add_brand(final)
    copy = os.path.join(store.ROOT, "output", store.safe_name(p["title"]) + ".mp4")
    shutil.copy(final, copy)
    prod.status(final_seconds=round(seconds(final), 1), final_made=store.now(), copy=copy)
    prod.log(f"music video {seconds(final):.1f} s -> {copy}")


# ---------- publish ----------
def lyric_srt(prod, path):
    words = store.read_json(prod.path("", "song_words.json"), []) or []
    off = float(store.status(prod.pid).get("brand_offset") or 0)  # the logo intro moves everything later

    def ts(x):
        x += off
        ms = int(round(x * 1000))
        return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"
    rows = [f"{i + 1}\n{ts(w['start'])} --> {ts(max(w['end'], w['start'] + 0.8))}\n{w['text']}\n"
            for i, w in enumerate(x for x in words if x["text"])]
    open(path, "w", encoding="utf-8").write("\n".join(rows))
    return len(rows)


def step_music_publish(prod):
    import writer
    from PIL import Image
    from produce import CFG, FFMPEG, run, seconds, stop_comfy
    p = prod.p
    final = prod.path("output", "final.mp4")
    if not os.path.exists(final):
        raise RuntimeError("make the final video first")
    chars = prod.chars()
    pub = store.publish(prod.pid)
    song_lines = [l for l in (p.get("music", {}).get("lyrics") or "").splitlines() if l.strip() and not l.startswith("[")]
    if not pub.get("titles") or prod.task.get("texts"):
        prod.status(stage="publish", label="Writing titles, description and tags (local AI)")
        stop_comfy(CFG["comfy_url"])
        try:
            pub.update(writer.publish_texts(p, chars, song_lines[:16]))
        except Exception as e:
            prod.log(f"AI texts failed ({str(e)[:200]}) - simple texts used")
            pub.update(titles=[p["title"]], description=(p.get("logline") or p.get("idea", "")) + "\n\n" +
                       prod.st["ai_disclosure"], tags=[p["title"]], hashtags=["#music", "#shorts"],
                       thumbnail_texts=[p["title"]], short_title=p["title"], short_description="")
        store.write_json(store.pfile(prod.pid, "publish.json"), pub)
    n = lyric_srt(prod, prod.path("output", "subtitles.srt"))
    pub["subtitles"] = "output/subtitles.srt"
    prod.log(f"lyric subtitles: {n} lines")
    # thumbnails from the singer's close-ups (first, middle) and one story shot
    prod.status(stage="publish", label="Thumbnails")
    sing = [s for s in p["scenes"] if s["kind"] == "sing"] or p["scenes"]
    other = [s for s in p["scenes"] if s["kind"] != "sing"]
    picks = [sing[0], sing[len(sing) // 2]] + (other[:1] or sing[-1:])
    texts = ([p["hook_text"]] if p.get("hook_text") else []) + (pub.get("thumbnail_texts") or [p["title"]]) * 3
    thumbs = []
    for i, s in enumerate(picks[:3]):
        src = prod.path("pictures", s["id"] + ".png")
        if os.path.exists(src):
            out = prod.path("output", f"thumb{i + 1}.jpg")
            prod.thumbnail(src, texts[i], out, None)
            thumbs.append(f"output/thumb{i + 1}.jpg")
    pub["thumbnails"] = thumbs
    pub.setdefault("thumbnail_choice", 0)
    # Short: the first chorus-ish minute of the final video, 9:16 with the title on top
    prod.status(stage="publish", label="Making the Short (9:16)")
    work = prod.path("output", "short_parts")
    os.makedirs(work, exist_ok=True)
    top = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
    prod.glow_text(top, (p.get("hook_text") or p["title"]).upper(), (60, 70, 960, 230), 92, "impact", "center")
    top.save(os.path.join(work, "title.png"))
    off = float(store.status(prod.pid).get("brand_offset") or 0)  # skip the logo intro
    length = min(prod.st["short_max_seconds"], seconds(final) - off)
    start = off
    words = store.read_json(prod.path("", "song_words.json"), []) or []
    if words and seconds(final) > off + length + 5:  # start a little before the first sung line
        start = off + max(0.0, min(words[0]["start"] - 1.0, seconds(final) - off - length))
    fc = ("[0:v]split[a][b];[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,gblur=sigma=40,"
          "eq=brightness=-0.22[bg];[b]crop=ih*4/5:ih,scale=1080:1350[fg];[bg][fg]overlay=0:300[v0];[v0][1:v]overlay=0:0[v]")

    def cut(n, a, secs, title_png):
        out = prod.path("output", f"short{n}.mp4")
        r = run([FFMPEG, "-y", "-loglevel", "error", "-ss", f"{a:.2f}", "-t", f"{secs:.2f}", "-i", final,
                 "-i", title_png, "-filter_complex", fc, "-map", "[v]", "-map", "0:a",
                 "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac",
                 "-b:a", "160k", "-movflags", "+faststart", out])
        if r.returncode == 0 and os.path.exists(out):
            return round(seconds(out), 1)
        prod.log(f"Short {n} failed: " + (r.stderr or "")[-300:])
        return None

    shorts = []
    secs = cut(1, start, length, os.path.join(work, "title.png"))
    if secs:
        pub["short"] = {"file": "output/short1.mp4", "scenes": [], "seconds": secs}
        shorts.append(dict(pub["short"], title=p.get("hook_text") or p["title"]))
        prod.log(f"Short: {secs:.1f} s from {start:.1f} s")
    # more Shorts: the chorus (the most repeated lyric line = the hook) and the ending, ~30 s each
    total = seconds(final)
    more = []
    if words and total - off > 60:
        norm = lambda t: re.sub(r"[^\w]+", " ", t).strip().lower()
        counts = {}
        for w in words:
            counts[norm(w["text"])] = counts.get(norm(w["text"]), 0) + 1
        # the chorus: the first line under a [Chorus] tag in the lyrics, else the line sung most often
        lyr = (p.get("music", {}).get("lyrics") or "").splitlines()
        first_chorus = next((norm(lyr[i + 1]) for i, l in enumerate(lyr[:-1])
                             if re.fullmatch(r"\s*\[\s*chorus[^\]]*\]\s*", l, re.I) and lyr[i + 1].strip()), None)
        hook = (next((w for w in words if norm(w["text"]) == first_chorus), None) if first_chorus else None) or \
            max(words, key=lambda w: (counts[norm(w["text"])], -w["start"]))
        a = off + max(0.0, min(hook["start"] - 1.0, total - off - 30))
        if abs(a - start) > 8:
            more.append(("chorus", a, hook["text"]))
        more.append(("ending", max(off, total - 30), p["title"]))
    for n, (kind, a, title) in enumerate(more[:max(0, int(prod.st.get("shorts_count", 3)) - 1)], 2):
        png = os.path.join(work, f"title{n}.png")
        im = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
        prod.glow_text(im, re.sub(r"[()]", "", title).upper(), (60, 70, 960, 230), 92, "impact", "center")
        im.save(png)
        prod.status(stage="publish", label=f"Making Short {n} (9:16)")
        secs = cut(n, a, min(30, total - a), png)
        if secs:
            shorts.append({"file": f"output/short{n}.mp4", "scenes": [], "seconds": secs, "title": title, "kind": kind})
            prod.log(f"Short {n} ({kind}): {secs:.1f} s from {a:.1f} s")
    pub["shorts"] = shorts
    pub["made"] = store.now()
    store.write_json(store.pfile(prod.pid, "publish.json"), pub)

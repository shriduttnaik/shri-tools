"""Story and YouTube texts with a local Ollama model (offline). Every story follows the MiniMax H3 rules that
made SHRI Episodes 1-2 work: one speaker per tight close-up, short English lines, loud named sounds whose source
is in the picture, no crowds of unnamed people, never the words "silence" or "tense"."""
import json, re, urllib.request

import store

STORY_RULES = """You write episodes for short AI-made videos. Every scene is ONE shot of about 5 seconds. A picture
is drawn for each scene, then a video model (MiniMax H3) animates it and makes the sound and the voices itself.
There is NO narrator: the story is told only by what the characters do and say.

Rules for every scene:
- kind "talk": one character says ONE short line (at most 10 words, said in under 4 seconds), in the spoken
  language given with the idea.
  Its picture MUST be "tight head-and-shoulders close-up of @Name, face filling the frame, <expression>,
  <setting behind>". Only that one character is in a talk picture. Set "speaker" to that character's name.
- kind "action": something happens without words. "action" says in 1-2 sentences what moves. "sounds" names
  two or three LOUD, concrete sounds whose source is VISIBLE in that picture (for example "rain drums on the tin
  roof, his boots splash in the puddle"). Never name a sound whose source is not in the picture (the video model
  draws every sound source it hears about). Never write the words silence, silent, quiet, tense or standoff.
- Refer to characters only as @Name, exactly as in the cast list. Only cast characters appear prominently.
  Avoid crowds and unnamed people; if someone else must appear, keep them small and far away.
- Each "picture" is drawn on its own, so describe the setting, time of day and light every time, consistently.
- At most two characters in one picture. Write pictures in English, in present tense, without camera jargon
  except shot size (close-up, medium shot, wide shot).
- About 40% of the scenes are talk scenes. Lines may use Indian names and words.
- Sounds in action scenes must be LOUD and specific, for example "heavy rain drums on the big leaves, the paper
  boat splashes over a small waterfall" or "thunder cracks overhead, his boots splash through the puddle".
  Talk scenes get one soft background sound.
- Every "picture" that shows a character contains its @Name (for example "@Pip"), also in wide shots.
- First write "plot": the whole story in 5-6 sentences. The problem set up at the start must be solved ON SCREEN
  before the end (a lost thing is found, a danger is beaten), then one warm closing moment.
- HOOK: scene 1 must grab the viewer in the first 2 seconds - a surprising action, a funny or shocking line, or
  the conflict itself (never a calm establishing shot). The Short of the episode starts with it.
- "camera" says how the camera moves in that shot (for example "slow push-in on his face", "low angle tracking
  her running", "static eye-level close-up").
- The story has a hook in the first scene, a problem, a turning point and a warm, satisfying ending."""

STORY_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "logline": {"type": "string"},
        "hook_text": {"type": "string"},
        "plot": {"type": "string"},
        "scenes": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": ["talk", "action"]},
                "picture": {"type": "string"},
                "action": {"type": "string"},
                "speaker": {"type": "string"},
                "line": {"type": "string"},
                "line_en": {"type": "string"},
                "tone": {"type": "string"},
                "sounds": {"type": "string"},
                "camera": {"type": "string"},
            },
            "required": ["kind", "picture", "action", "speaker", "line", "line_en", "tone", "sounds", "camera"]}},
    },
    "required": ["title", "logline", "hook_text", "plot", "scenes"],
}

PUBLISH_SCHEMA = {
    "type": "object",
    "properties": {
        "titles": {"type": "array", "items": {"type": "string"}},
        "description": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
        "hashtags": {"type": "array", "items": {"type": "string"}},
        "thumbnail_texts": {"type": "array", "items": {"type": "string"}},
        "short_title": {"type": "string"},
        "short_description": {"type": "string"},
    },
    "required": ["titles", "description", "tags", "hashtags", "thumbnail_texts", "short_title", "short_description"],
}


def ollama(messages, schema, model=None, temperature=0.8, timeout=1800, think="low"):
    """Ask the story AI chosen in Settings: Ollama on this laptop (default) or a cloud provider (llm.py)."""
    st = store.settings()
    if (st.get("llm_provider") or "ollama") != "ollama":
        import llm
        return llm.ask(st["llm_provider"], messages, schema, st, timeout=min(timeout, 900))
    model = model or st["story_model"]
    body = {"model": model, "messages": messages, "stream": False, "format": schema, "keep_alive": 0,
            "options": {"temperature": temperature, "num_ctx": 12288}}
    if model.startswith("gpt-oss"):
        body["think"] = think
    elif "qwen3" in model:
        body["think"] = False
    req = urllib.request.Request(st["ollama_url"] + "/api/chat", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        text = json.loads(r.read())["message"]["content"]
    m = re.search(r"\{[\s\S]*\}", text)
    return json.loads(m.group(0) if m else text)


def cast_text(chars):
    return "\n".join(f"- {store.tag(c['name'])} ({c['name']}):{c.get('look') or 'no description'}; "
                     f"voice: {c.get('voice') or 'natural voice'}" for c in chars) or "- (no cast: invent none, use objects/animals)"


def language_rules(p):
    """Spoken language of the video: lines in that language's own script, everything else stays English."""
    lang = store.LANGUAGES[store.language(p)]
    if lang["name"] == "English":
        return 'Spoken language: English. Set "line_en" to "".'
    return (f"Spoken language: {lang['name']}. Every talk line is natural, everyday spoken {lang['name']} written in "
            f"its own script ({lang['native']}), the way a family really talks (not formal or bookish), at most 8 "
            f"words. \"line_en\" is its English meaning (for subtitles). Everything else (picture, action, sounds, "
            f"camera, tone) stays in English.")


def write_story(p, chars, previous=(), theme=""):
    style = store.STYLES.get(p["style"], store.STYLES["pixar"])["name"]
    prev = "\n".join(f"- Episode {i + 1}: {t}" for i, t in enumerate(previous)) or "- (first episode)"
    user = f"""Video type: {p['kind']}. Visual style: {style}.
Number of scenes: exactly {p['scenes_wanted']}.
Cast:
{cast_text(chars)}
Series theme (every episode teaches it): {theme or "(none)"}
Earlier episodes of this season:
{prev}
Idea from the creator:
{p['idea'] or p['title']}
{language_rules(p)}

Write the episode as JSON: title, logline (one sentence), hook_text (the hook in at most 6 words for the
Short and the thumbnail, e.g. a question), plot (5-6 sentences), scenes. For action scenes set speaker, line and tone
to "". For talk scenes set tone to how the line is said (for example "says firmly", "whispers", "shouts happily")
and sounds to one soft background sound that fits the place."""
    out = ollama([{"role": "system", "content": STORY_RULES}, {"role": "user", "content": user}], STORY_SCHEMA,
                 think="medium")
    return out


def publish_texts(p, chars, lines):
    st = store.settings()
    lang = store.LANGUAGES[store.language(p)]
    lang_note = "" if lang["name"] == "English" else (
        f". Write the titles, thumbnail texts and Shorts title in {lang['name']} ({lang['native']} script) with a few "
        f"English words where they help, the description in {lang['name']} and English, and tags in both.")
    user = f"""Write YouTube texts for this AI-made video.
Title: {p['title']}
Story: {p.get('logline') or p.get('idea')}
Characters: {', '.join(c['name'] for c in chars)}
Spoken lines: {' | '.join(lines)}
Style: {store.STYLES.get(p['style'], store.STYLES['pixar'])['name']}
Spoken language: {store.LANGUAGES[store.language(p)]['name']}{lang_note}

Give: 3 different catchy titles that hook the viewer (under 70 characters, a question or a surprise, no
clickbait lies), a description (3 short paragraphs:
hook, story without spoiling the end, invitation to subscribe for the next episode), 15 search tags, 4 hashtags,
3 thumbnail texts (2-4 punchy hook words each, ALL CAPS), a YouTube Shorts title that hooks in the first
words (under 60 characters) and a
2-sentence Shorts description."""
    out = ollama([{"role": "user", "content": user}], PUBLISH_SCHEMA, temperature=0.7, timeout=900)

    def clean(t):  # YouTube shows plain text: no markdown, plain dashes and quotes
        t = re.sub(r"\*\*|__|^#+\s*", "", t, flags=re.M)
        return t.translate({0x2011: "-", 0x2010: "-", 0x2012: "-", 0x00a0: " ", 0x202f: " "}).strip()
    for k in ("description", "short_title", "short_description"):
        out[k] = clean(out.get(k, ""))
    for k in ("titles", "tags", "hashtags", "thumbnail_texts"):
        out[k] = [clean(x) for x in out.get(k, []) if clean(x)]
    out["hashtags"] = ["#" + h.lstrip("#").replace(" ", "") for h in out["hashtags"]]
    out["description"] = re.sub(r"[ \t]{2,}", " ", out["description"]).rstrip() + "\n\n" + st["ai_disclosure"]
    return out


# ---------- music videos ----------
SONG_SCHEMA = {
    "type": "object",
    "properties": {"title": {"type": "string"}, "logline": {"type": "string"}, "hook_text": {"type": "string"},
                   "lyrics": {"type": "string"}, "caption": {"type": "string"}},
    "required": ["title", "logline", "hook_text", "lyrics", "caption"],
}
SHOTS_SCHEMA = {
    "type": "object",
    "properties": {"shots": {"type": "array", "items": {
        "type": "object",
        "properties": {"id": {"type": "string"}, "picture": {"type": "string"}, "action": {"type": "string"},
                       "camera": {"type": "string"}, "line_en": {"type": "string"}},
        "required": ["id", "picture", "action", "camera", "line_en"]}}},
    "required": ["shots"],
}


def write_song(p, chars, style, vocal):
    """Lyrics (with section tags, in the song's language and script) and a MiniMax Music 3 structured caption."""
    m = p.get("music", {})
    lang = store.LANGUAGES[store.language(p)]
    secs = float(m.get("seconds") or 60)
    lines = max(6, min(28, int(secs / 4.5)))
    script = "English" if lang["name"] == "English" else f"{lang['name']} written in its own script ({lang['native']})"
    user = f"""Write a song for an AI music video.
Title idea: {p.get('title') or '(you choose)'}
What the song is about: {p.get('idea') or m.get('mood') or 'a happy song'}
Music style: {style}
Mood: {m.get('mood') or 'fits the idea'}
Voice: {vocal}
Singer(s) on screen: {', '.join(c['name'] for c in chars) or 'a singer'}
Length: about {secs:.0f} seconds, so about {lines} sung lines in total.
Language of the lyrics: {script}.

Give JSON:
- "lyrics": the lyrics with section tags on their own lines: [Intro], [Verse], [Chorus], [Bridge], [Instrumental],
  [Outro]. A short intro, one or two verses, a catchy chorus that repeats, an outro. Short singable lines (3-8 words),
  simple everyday words, rhymes where natural. Only the words to sing and the tags, nothing else.
- "caption": the music description in English, in three paragraphs that start with "Global Metadata:", "Vocal
  Details:" and "Arrangement:". Global Metadata: genre, BPM, key, mood progression. Vocal Details: {vocal}, singing in
  {lang['name']}, timbre and delivery. Arrangement: instruments per section (intro, verses, chorus, outro).
- "title" (in {lang['name']}, may add English in brackets), "logline" (one English sentence), "hook_text" (2-5 punchy
  words for the thumbnail and Short)."""
    out = ollama([{"role": "user", "content": user}], SONG_SCHEMA, temperature=0.85, think="medium")
    out["lyrics"] = re.sub(r"\n{3,}", "\n\n", (out.get("lyrics") or "").replace("\n", "\n")).strip()
    out["caption"] = (out.get("caption") or "").replace("\n", "\n").strip()
    if not out["lyrics"] or not out["caption"]:
        raise RuntimeError("the story model wrote no lyrics - try again or write them yourself")
    return out


def plan_music_shots(p, chars, shots, style):
    """One picture per 5-second piece of the song: the singer in close-up while words are sung, story/dance shots
    between. shots = [{id, start, end, sung}]."""
    m = p.get("music", {})
    vstyle = store.STYLES.get(p["style"], store.STYLES["pixar"])["name"]
    rows = "\n".join(f"{s['id']} {s['start']:.1f}-{s['end']:.1f}s: " + (f"SUNG: {s['sung']}" if s["sung"] else "music only")
                     for s in shots)
    user = f"""Plan the shots of a music video. Visual style: {vstyle}. Music: {style}.
Song: {p.get('title')}. About: {p.get('logline') or p.get('idea') or ''}
Where it happens: {m.get('setting') or 'choose 2-3 beautiful places that fit the song'}
Cast (use exactly these @Names): {cast_text(chars)}
Lyrics:
{m.get('lyrics', '')}

Shots (each about 5 seconds, in order):
{rows}

For every shot give id, picture, action, camera and line_en.
- A SUNG shot: picture = "tight head-and-shoulders close-up of @Name, face filling the frame, <expression that fits the
  words>, <place and light behind>". Only the singer in the picture. action = how they sing it (e.g. "sings softly
  with closed eyes, then smiles"). line_en = English meaning of the sung words.
- A "music only" shot: a story or dance moment that shows what the song is about (wide or medium shot), with @Names
  for every cast character in it, at most two characters, no crowds. line_en = "".
- Describe place, time of day and light every time, consistently. No text, no logos, no musical instruments floating
  in the air. Camera: e.g. "slow push-in", "slow orbit around her", "low angle tracking him dancing"."""
    out = ollama([{"role": "user", "content": user}], SHOTS_SCHEMA, temperature=0.7, think="low")
    names = {store.tag(c["name"]).lower(): store.tag(c["name"]) for c in chars}
    for s in out.get("shots", []):
        for k in ("picture", "action", "camera"):
            s[k] = re.sub(r"@(\w+)", lambda mm: names.get("@" + mm.group(1).lower(), "@" + mm.group(1)), s.get(k) or "")
    return out.get("shots", [])


# ---------- dubbing: an episode in another language ----------
TRANSLATE_SCHEMA = {
    "type": "object",
    "properties": {"lines": {"type": "array", "items": {"type": "object", "properties": {
        "id": {"type": "string"}, "line": {"type": "string"}}, "required": ["id", "line"]}},
        "hook_text": {"type": "string"}, "title": {"type": "string"}},
    "required": ["lines", "hook_text", "title"],
}


def translate_lines(p, lines, hook="", title=""):
    """lines = [{id, line, speaker, tone}] -> the same lines in the project's language (natural spoken, short)."""
    lang = store.LANGUAGES[store.language(p)]
    rows = "\n".join(f'{x["id"]} | {x.get("speaker") or "?"} ({x.get("tone") or "says"}): {x["line"]}' for x in lines)
    user = f"""Translate the spoken lines of this {store.STYLES.get(p['style'], store.STYLES['pixar'])['name']} video
into natural, everyday spoken {lang['name']}, written in its own script ({lang['native']}).
- Keep each line as short as the original (at most 8 words) and keep its feeling (shouting, asking, whispering).
- Say it the way a family really talks, not formal or bookish. Keep names as they are pronounced (Tuntun, Shri Mama).
- Return every id exactly once.
Also translate the hook words (2-5 punchy words for the thumbnail) and the title.

Lines (id | speaker (tone): line):
{rows}
Hook words: {hook or '-'}
Title: {title or p.get('title', '')}"""
    out = ollama([{"role": "user", "content": user}], TRANSLATE_SCHEMA, temperature=0.4, think="low")
    return out


# ---------- ideas for the next episodes of a season ----------
IDEAS_SCHEMA = {
    "type": "object",
    "properties": {"ideas": {"type": "array", "items": {"type": "object", "properties": {
        "title": {"type": "string"}, "idea": {"type": "string"}, "hook": {"type": "string"}},
        "required": ["title", "idea", "hook"]}}},
    "required": ["ideas"],
}


def season_ideas(season, chars, previous, n=10):
    prev = "\n".join(f"- {t}" for t in previous) or "- (none yet)"
    user = f"""Suggest {n} ideas for the next episodes of a video series.
Series: {season['title']}. Style: {store.STYLES.get(season.get('style'), store.STYLES['pixar'])['name']}.
What every episode is about: {season.get('about') or '(not given)'}
Cast:
{cast_text(chars)}
Episodes already made (do not repeat them):
{prev}

Each idea: a short catchy title, the idea in 2-3 sentences (who wants what, what goes wrong, how it ends - something
that can be shown in about 18 short shots with at most two characters per shot), and a hook (the surprising first
line or moment). Keep the series' tone and lesson; vary places, side characters and situations."""
    return ollama([{"role": "user", "content": user}], IDEAS_SCHEMA, temperature=0.9, think="low").get("ideas", [])[:n]

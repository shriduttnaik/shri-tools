"""Picture check: a vision AI looks at every storyboard picture before it becomes a video.

It answers, for one picture: who is in it, is a character drawn twice, are there people who should not be there, does
it show what the scene describes. A picture that fails is drawn again (new seed) by produce.step_pictures, so nobody
has to look at every picture when videos are made automatically (n8n, schedules, music videos).

Vision AI: Ollama on this laptop (default qwen2.5vl:7b) or, when the story AI in Settings is Claude / OpenAI / Gemini
with a key, that cloud model (better eyes).
"""
import base64, io, json, re, urllib.request

import store

SCHEMA = {
    "type": "object",
    "properties": {
        "people_count": {"type": "integer"},
        "people": {"type": "array", "items": {"type": "string"}},
        "duplicate": {"type": "boolean"},
        "action_matches": {"type": "boolean"},
        "problems": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["people_count", "people", "duplicate", "action_matches", "problems"],
}
CROWD = re.compile(r"\b(crowd|villagers|families|people|devotees|children|kids|men|women|onlookers|audience|"
                   r"background)\b", re.I)
NOBODY = re.compile(r"\b(no people|nobody|no one|empty)\b", re.I)


def expected(scene, chars):
    """The characters a scene's picture should show (by @tag), and whether other people may be in it."""
    pic = scene.get("picture") or ""
    want = [c for c in chars if store.tag(c["name"]).lower() in pic.lower()]
    # "only these two people", "exactly three people and nobody else" limit the count; they do not allow a crowd
    crowd = (bool(CROWD.search(re.sub(r"@\w+", "", pic))) and not NOBODY.search(pic)
             and not re.search(r"\b(only|exactly|nobody else)\b", pic, re.I))
    return want, crowd


def prompt_for(scene, chars, look):
    """Count first, blind: told who should be there, the model tends to list those characters instead of looking (a
    half-hidden extra man was missed that way). The wanted picture is only given for the action question."""
    pic = re.sub(r"@(\w+)", lambda m: next((c["name"] for c in chars if store.tag(c["name"]) == "@" + m.group(1)),
                                           m.group(1)), scene.get("picture") or "")
    pic = re.sub(r"\b(only these \w+ people|exactly \w+ people and nobody else:?|nobody else)\b", "", pic, flags=re.I)
    return ("You check pictures for a film studio. Look very carefully.\n\n"
            "1. Count EVERY person in the picture: adults, children, babies and cartoon characters, also people who are "
            "small, far away in the background, partly hidden behind someone, or only a face at the edge (statues, idols, "
            "paintings, posters and dolls are NOT people - do not count them). Describe "
            "only what you really see, one line per person: age, gender, clothes, where in the picture.\n"
            "2. duplicate = true if two of those people look like the same character (same face and same clothes).\n"
            f"3. The picture was meant to show: {pic}\n"
            "action_matches = true if it really shows that (the pose, the action, the objects); false if the action "
            "or pose is clearly different.\n"
            "4. problems = short notes on anything wrong or strange (extra arms or legs, a face on an object, things "
            "that do not belong).\n\n"
            "Answer in JSON with people_count, people, duplicate, action_matches, problems.")


def _jpeg_b64(path, side=768):
    from PIL import Image
    im = Image.open(path).convert("RGB")
    im.thumbnail((side, side))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=88)
    return base64.b64encode(buf.getvalue()).decode()


def ask_vision(path, text, st=None, cpu_only=False, timeout=600, schema=None):
    st = st or store.settings()
    schema = schema or SCHEMA
    provider = st.get("llm_provider") or "ollama"
    img = _jpeg_b64(path)
    if provider == "claude" and st.get("anthropic_api_key"):
        import llm
        msgs = [{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": img}},
            {"type": "text", "text": text}]}]
        return llm.ask("claude", msgs, schema, st, timeout=timeout)
    if provider in ("openai", "compat") and (st.get("openai_api_key") or st.get("compat_api_key")):
        import llm
        msgs = [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + img}},
            {"type": "text", "text": text}]}]
        return llm.ask(provider, msgs, schema, st, timeout=timeout)
    body = {"model": st.get("vision_model") or "qwen2.5vl:7b", "stream": False, "format": schema, "keep_alive": "5m",
            "messages": [{"role": "user", "content": text, "images": [img]}],
            "options": {"temperature": 0, "num_ctx": 8192, **({"num_gpu": 0} if cpu_only else {})}}
    req = urllib.request.Request(st["ollama_url"] + "/api/chat", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        out = json.loads(r.read())["message"]["content"]
    m = re.search(r"\{[\s\S]*\}", out)
    return json.loads(m.group(0) if m else out)


def unload(st=None):
    """Free the GPU: the vision model stays loaded between pictures, but Klein / H3 need the whole 4 GB after it."""
    st = st or store.settings()
    try:
        body = {"model": st.get("vision_model") or "qwen2.5vl:7b", "keep_alive": 0}
        urllib.request.urlopen(urllib.request.Request(st["ollama_url"] + "/api/generate", data=json.dumps(body).encode(),
                                                      headers={"Content-Type": "application/json"}), timeout=60).read()
    except Exception:
        pass


def verdict(ans, scene, chars):
    """(ok, reasons) from the vision answer, with the counting done here (the model's yes/no alone is not trusted)."""
    want, crowd = expected(scene, chars)
    reasons = []
    # the model's own "duplicate" answer gives false alarms (a picture with exactly the two right people was called
    # doubled); a real doubled character always shows as too many people, which the count below catches
    n = int(ans.get("people_count") or 0)
    if not crowd and want and n > len(want):
        reasons.append(f"{n} people but only {len(want)} should be there")
    elif not crowd and not want and n > 0 and NOBODY.search(scene.get("picture") or ""):
        reasons.append(f"{n} people in a picture that should be empty")
    elif ans.get("extra_people") and not crowd:
        reasons.append("an extra person")
    if ans.get("missing") and want:
        reasons.append("missing: " + ", ".join(map(str, ans["missing"]))[:80])
    if ans.get("action_matches") is False:
        reasons.append("does not show the described action")
    return not reasons, reasons


COUNT = ("Count EVERY person in this picture: adults, children, babies and cartoon characters, also people who are small, "
         "far away in the background or partly hidden (statues, idols, paintings, posters and dolls are NOT people). "
         "Answer in JSON with people_count and people (one short line per person).")
COUNT_SCHEMA = {"type": "object", "properties": {"people_count": {"type": "integer"},
                                                 "people": {"type": "array", "items": {"type": "string"}}},
                "required": ["people_count", "people"]}


LIVING = ("Look very carefully. Count only REAL, LIVING people (adults, children, babies, or animated characters who are "
          "alive in the scene). Do NOT count statues, idols, deity figures, temple murtis, paintings, posters, dolls, "
          "carvings, masks or reflections - even when they look like a person. Answer in JSON with people_count and "
          "people (one short line per living person).")


def count_people(path, st=None):
    return int(ask_vision(path, COUNT, st=st, schema=COUNT_SCHEMA).get("people_count") or 0)


def count_living(path, st=None):
    """A stricter second count, asked only when the first one says someone appeared: a Devi idol filling the frame at
    the end of a push-in was counted as a person once."""
    return int(ask_vision(path, LIVING, st=st, schema=COUNT_SCHEMA).get("people_count") or 0)


def check_clip(first, last, scene, chars, st=None):
    """Did someone walk INTO the shot? The end of the clip is compared with its start (the picture), not with the cast
    list: a picture with a festival crowd behind the cast is right, and the crowd is still there at the end (this
    mistake once failed 11 good Navratri clips). A picture that already has more people than its @Names (background
    people) is left to the picture check - crowds cannot be counted reliably."""
    want, crowd = expected(scene, chars)
    if crowd:
        return {"ok": True, "reasons": [], "start": None, "end": None}
    n0 = count_people(first, st)
    if n0 > len(want) + 1:
        return {"ok": True, "reasons": [], "start": n0, "end": None}
    n1 = count_people(last, st)
    if n1 > max(n0, len(want)):
        n1 = min(n1, count_living(last, st))  # both counts must say so (idols, statues, paintings)
    if n1 > max(n0, len(want)):
        return {"ok": False, "reasons": [f"a person appeared in the video ({n0} at the start, {n1} at the end)"],
                "start": n0, "end": n1}
    return {"ok": True, "reasons": [], "start": n0, "end": n1}


def check(path, scene, chars, look, st=None, cpu_only=False):
    ans = ask_vision(path, prompt_for(scene, chars, look), st=st, cpu_only=cpu_only)
    ok, reasons = verdict(ans, scene, chars)
    return {"ok": ok, "reasons": reasons, "answer": ans}

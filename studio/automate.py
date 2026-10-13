"""Automations: repeating jobs that start by themselves (library/schedules.json), checked once a minute by the server.

  next_episode   the next episode of a season, from its ideas list (Season page -> ideas) or, when the list is used
                 up, a fresh idea in the series' theme; fully automatic, or stop at the pictures for your approval
  dub_latest     the newest finished episode of a season again in another language (pictures and action reused)

A schedule: {id, name, kind, season_id, language, days: [0-6, Monday = 0], time: "HH:MM", auto: bool, enabled,
last_run: "YYYY-MM-DD", last_project}
"""
import os, time, uuid

import store

FILE = os.path.join(store.LIB, "schedules.json")
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def schedules():
    return store.read_json(FILE, []) or []


def save(items):
    store.write_json(FILE, items)


def upsert(s):
    items = schedules()
    s = {**s}
    if not s.get("id"):
        s.update(id=uuid.uuid4().hex[:10], created=store.now(), last_run="")
    s["days"] = sorted({int(d) for d in s.get("days", []) if 0 <= int(d) <= 6})
    if not s["days"]:
        raise ValueError("choose at least one day")
    if not (len(s.get("time", "")) == 5 and s["time"][2] == ":"):
        raise ValueError("time must look like 22:00")
    if s.get("kind") not in ("next_episode", "dub_latest"):
        raise ValueError("unknown automation")
    if not store.load("season", s.get("season_id")):
        raise ValueError("choose a season")
    if s.get("language") and s["language"] not in store.LANGUAGES:
        raise ValueError("unknown language")
    items = [x for x in items if x["id"] != s["id"]] + [s]
    save(items)
    return s


def next_run(s, now=None):
    """The next time this automation starts, as 'YYYY-MM-DD HH:MM' (for the Queue page)."""
    now = now or time.time()
    for k in range(0, 8):
        t = time.localtime(now + k * 86400)
        stamp = time.strftime("%Y-%m-%d", t) + " " + s["time"]
        if t.tm_wday in s["days"] and stamp > time.strftime("%Y-%m-%d %H:%M", time.localtime(now)) \
                and s.get("last_run") != time.strftime("%Y-%m-%d", t):
            return stamp
    return ""


def due(s, now=None):
    t = time.localtime(now or time.time())
    today = time.strftime("%Y-%m-%d", t)
    return (s.get("enabled", True) and t.tm_wday in s["days"] and time.strftime("%H:%M", t) >= s["time"]
            and s.get("last_run") != today)


def fire(s, log=print):
    """Create the video and queue its steps. Returns the new project (or None)."""
    season = store.load("season", s["season_id"])
    if not season:
        log(f"automation {s.get('name')}: season is gone")
        return None
    if s["kind"] == "next_episode":
        ideas = season.get("ideas") or []
        pick = next((x for x in ideas if not x.get("used")), None)
        idea = (pick["idea"] + (" Hook: " + pick["hook"] if pick.get("hook") else "")) if pick else (
            "A new episode in the series' theme: a new place and a new side character, a clear problem solved on "
            "screen, and the series' lesson at the end.")
        p = store.new_project((pick or {}).get("title") or "Untitled video", "episode", season.get("style", "pixar"),
                              season["id"], season.get("cast", []), idea, 18, {"approve_pictures": not s.get("auto")})
        if season.get("style_prefix"):
            p["style_prefix"] = season["style_prefix"]
        if s.get("language"):
            p["language"] = s["language"]
        p["automation"] = s["id"]
        store.save("project", p)
        steps = ["write", "sheets", "pictures"] + (["clips", "check", "final", "publish"] if s.get("auto") else [])
        task = {"kind": "project", "project": p["id"], "steps": steps}
        if not s.get("auto"):
            task["then_approve"] = True
        store.add_task(task)
        store.set_status(p["id"], state="waiting", label="Waiting in the queue (automation)")
        if pick:
            season = store.load("season", season["id"])
            for x in season.get("ideas", []):
                if x.get("title") == pick.get("title") and not x.get("used"):
                    x["used"] = p["id"]
                    break
            store.save("season", season)
        log(f"automation {s.get('name')}: new episode {p['id']}")
        return p
    if s["kind"] == "dub_latest":
        eps = [store.load("project", e) for e in season.get("episodes", [])]
        eps = [e for e in eps if e and store.status(e["id"]).get("state") == "done" and not e.get("dub_of")]
        lang = s.get("language") or "hi"
        done = {x.get("dub_of") for x in store.all_of("project") if x.get("language") == lang}
        todo = next((e for e in reversed(eps) if e["id"] not in done and store.language(e) != lang), None)
        if not todo:
            log(f"automation {s.get('name')}: nothing new to dub")
            return None
        return {"dub": todo["id"], "language": lang}
    return None

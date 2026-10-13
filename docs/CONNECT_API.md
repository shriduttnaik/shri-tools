# Shri Tools Connect (API for n8n and other tools)

Shri Tools Connect lets any tool that can send HTTP requests make videos: send an idea (or ready scenes), and get the
finished episode, the Short, thumbnails, subtitles and YouTube texts back. The app's **Connect** screen shows the
address, the API key and a button to download a ready n8n workflow.

Base address: `http://127.0.0.1:7880` (same laptop). All bodies and answers are JSON.

## Calls

| Method | Path | What |
|---|---|---|
| GET | `/api/connect/health` | is Shri Tools up, is it busy, how many jobs wait |
| GET | `/api/connect/options` | seasons, characters, styles, languages (names and ids) |
| POST | `/api/connect/videos` | make a video (see below) → `201 {video}` |
| GET | `/api/connect/videos` | the latest 30 videos |
| GET | `/api/connect/videos/{id}` | one video: state, progress, files, YouTube texts |
| POST | `/api/connect/videos/{id}/approve` | pictures checked: make the videos (when `approve_pictures` was true) |
| POST | `/api/connect/videos/{id}/retry` | run the unfinished steps again (finished work is skipped) |
| POST | `/api/connect/videos/{id}/cancel` | stop it |
| GET | `/api/connect/videos/{id}/files/{name}` | download `final`, `short`, `subtitles`, `thumb1`, `thumb2`, `thumb3` |
| GET | `/api/connect/n8n-workflow` | the n8n workflow, with this address and key filled in |

### Make a video

```json
POST /api/connect/videos
{
  "title": "Say Thank You, Tuntun!",
  "idea": "Tuntun meets the vegetable seller and learns to say thank you.",
  "season": "Shri Mama and Tuntun",
  "language": "hi",
  "scenes_wanted": 18,
  "approve_pictures": false,
  "callback_url": "http://127.0.0.1:5678/webhook/shritub-done"
}
```

| Field | Default | Meaning |
|---|---|---|
| `idea` (or `prompt`) | - | what happens; the story AI writes the scenes. Or send `scenes` instead |
| `scenes` | - | ready scenes: `[{kind: "talk"|"action", picture, action, speaker, line, line_en, language, tone, sounds, camera}]`, characters as `@Name` |
| `title` | "Untitled video" | |
| `season` / `season_id` | none | an existing season (title or id); its style, cast and style words are used |
| `language` | `en` | `en hi kn kok mr ta te ml bn gu pa ur` or the name ("Hindi") |
| `style` | season's, else `pixar` | `pixar`, `cinematic`, `anime`, `storybook`, `clay` |
| `cast` | season's cast | names or ids; `{"name", "look", "voice"}` makes a new character |
| `scenes_wanted` | 18 | about 5 s per scene |
| `approve_pictures` | false | true = stop after the pictures (state `approve`) until `/approve` is called |
| `music`, `music_prompt` | false | background music (needs the optional MusicGen setup) |
| `hook_text` | from the story AI | the words on the Short and the first thumbnail |
| `callback_url` | none | Shri Tools POSTs here when the video is done, failed or waits for approval |

### Make a music video

```json
POST /api/connect/videos
{
  "kind": "music",
  "title": "Tuntun ka Thank You Gaana",
  "idea": "Tuntun thanks everyone who helps in his colony",
  "language": "hi",
  "genre": "kids_rhyme",
  "vocal": "child",
  "style": "pixar",
  "singers": ["Tuntun"],
  "seconds": 60,
  "setting": "a colorful Indian colony street on a sunny morning"
}
```

`genre`: `bollywood_romantic`, `bollywood_dance`, `indian_folk`, `devotional`, `kids_rhyme`, `lullaby`, `pop`, `rock`,
`rap`, `lofi`, `edm`, `ghazal`, `carnatic_fusion`, `patriotic`. `vocal`: `female`, `male`, `duet`, `child`, `choir`,
`none`. Optional: `lyrics` (with `[Verse]`/`[Chorus]` tags; empty = the story AI writes them), `caption` (music
description), `mood`, `approve_pictures`, `callback_url`. The rest works like a normal video (status, files, callback).

### The video object

```json
{
  "video": {
    "id": "20261013-142733-say-please-tuntun",
    "title": "Say Please, Tuntun!",
    "state": "running",
    "label": "Videos 7/18",
    "stage": "clips",
    "progress": {"done": 6, "total": 18},
    "eta_min": 120,
    "language": "en",
    "files": {"final": "http://127.0.0.1:7880/api/connect/videos/.../files/final", "short": "...", "thumb1": "..."},
    "publish": {"titles": ["..."], "description": "...", "tags": ["..."], "hashtags": ["..."], "short_title": "..."},
    "status_url": "http://127.0.0.1:7880/api/connect/videos/...",
    "open_in_app": "http://127.0.0.1:7880/#/p/.../storyboard",
    "log": ["last log lines"]
  }
}
```

`state` is one of `draft`, `waiting`, `running`, `approve` (pictures ready, waiting for `/approve`), `done`, `failed`,
`cancelled`.

### Callback

When a job stops, Shri Tools POSTs `{"event": "video.done" | "video.failed" | "video.cancelled" | "video.approve",
"video": {...}}` to the video's `callback_url` (3 tries). In n8n, point it at a **Webhook** node and you do not need
to poll.

## API key

On the same laptop no key is needed. In **Connect > API key** you can make one; from then on every call (except
`/health`) needs the header `X-Api-Key: <key>` (or `?key=<key>`). The downloaded n8n workflow already contains it.

**n8n in Docker or on another computer:** make a key, switch on *Allow other computers* and restart Shri Tools. The
server then listens on the network, but only `/api/connect/` answers other computers; the app itself still only
opens on the laptop. From Docker use `http://host.docker.internal:7880`.

## n8n workflow

**Connect > Download n8n workflow**, then in n8n *Workflows > Import from file*. It contains:

`Start (manual)` → `Your video` (edit title, idea, season, language) → `Shri Tools settings` (address + key) →
`Make request body` → `Start video` → `Wait 10 min` → `Check video` → `Done?` → `Download final video` (binary, ready
for a YouTube Upload node). `Failed?` stops with the error; anything else loops back to the wait. A **Webhook**
trigger (`POST /webhook/shritub-connect`) accepts the same fields from other flows.

## Examples

```bash
curl http://127.0.0.1:7880/api/connect/health

curl -X POST -H "Content-Type: application/json" \
  -d '{"title":"The Kite","idea":"Tuntun loses his kite and the watchman helps him.","season":"Shri Mama and Tuntun","language":"kn"}' \
  http://127.0.0.1:7880/api/connect/videos

curl -o episode.mp4 http://127.0.0.1:7880/api/connect/videos/<id>/files/final
```

Errors come back as `{"error": "..."}` with status 400 (bad field), 401 (key), 403 (not allowed from this computer)
or 404 (unknown id / file not made yet).

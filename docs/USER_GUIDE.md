# Using Shri Tools

Start with **Shri Tools.bat**. The app is one window: black, white text, green highlights.

## Screens

| Screen | What you do there |
|---|---|
| **Home** | your videos, what is running, engine status |
| **Create** | a new video: title, season, type (episode, single video, short story), spoken language, idea (or a ready idea), style, cast, length, options → *Write story with AI* or *I'll write the scenes myself* |
| **Seasons** | one style and one cast per season; the story AI reads the earlier episodes of the season |
| **Music videos** | a song (language, music style, voice, mood, lyrics or an idea) sung by your characters with lip sync; see [MUSIC_VIDEOS.md](MUSIC_VIDEOS.md) |
| **Characters** | make a character: name, look words, voice words; draw its pictures from the description, from 1-3 photos (only with that person's permission), or upload your own picture |
| **Queue** | one GPU job at a time; jobs continue after a restart or a power cut; live GPU / temperature / memory panel |
| **Connect** | the API for n8n: address, API key, workflow download (see [CONNECT_API.md](CONNECT_API.md)) |
| **Settings** | story model, video size, check rounds, loudness, Short length, the AI note for descriptions, Telegram bot, optional logo in videos |

A video has tabs: **Story** (idea, logline, hook words, language, write again), **Cast**, **Storyboard** (every
scene: picture, Talk/Action, line, check result; Edit, new Picture, new Video take, play), **Build** (the 7 steps
with times and the log), **Video** (final + check report), **Shorts** (pick scenes, make the 9:16 Short) and
**Publish** (titles, description, tags, thumbnails, downloads, upload checklist).

## Making an episode

1. **Characters first.** Make the main characters (Characters > New character). Good look words are specific and
   are used in every scene: age, skin, hair, clothes, one or two signature details ("small gold hoop earrings",
   "tiny yellow t-shirt with a duck on it"). Draw them and check the two pictures.
2. **Season** (optional): Seasons > New season, choose the style and the cast.
3. **Create**: pick the season, the language and write the idea in a few sentences: who wants what, what goes wrong,
   how it ends. *Write story with AI* takes 5-15 minutes.
4. **Read the story** (Story tab) and fix lines in the Storyboard. Every talk scene should be a close-up of the
   speaker with one short line.
5. **Build everything** (Build tab). With *Let me check the pictures* on, it stops after the pictures.
6. **Check the pictures**: wrong face, extra person, a stray object? Edit the scene text and press *Picture* on that
   scene. When all are right: **Pictures OK - make videos** (about 10 minutes per scene).
7. **Watch the final video** (Video tab). A bad scene: Storyboard → *Video* (a new take) → Build → *Join again*.
8. **Publish**: choose a title and a thumbnail, copy the description and tags, download the video, the Short and the
   subtitles.

## Automations and start times

Queue page → **Automations** → *New automation*: what (the next episode of a season, or the newest episode again in
another language), which days, what time, and whether it runs **fully automatically** or stops at the pictures for
you (with a Telegram message). New episodes use the season's idea list first (Season page → *Give me 10 ideas*). Any
waiting job also has **Start at** to begin at a set time - for example after you go to bed.

## Another language

Story tab → **Make it in another language** → pick the language. A copy of the episode is made: the pictures and the
action scenes are reused, the story AI translates the spoken lines (shown with their English meaning), and only the
talking scenes are made again, then checked and joined as usual.

## Your phone (Telegram)

Settings → Phone (Telegram): make a bot with @BotFather, paste its token, send the bot any message, press *Find my
chat id*, Save, *Send test*. From then on the bot sends a message when a video is ready (with the thumbnail), when
it failed, and when pictures wait for you (with all pictures in one image). Commands: `/status`, `/videos`,
`/approve N`, `/pictures N`, `/short N` (sends the Short), `/make <idea>` (a new episode of your latest season, stops
at the pictures), `/stop N`. The bot only answers your chat id.

## Writing scenes that work

| Scene | Picture text | Tips |
|---|---|---|
| Talk | `tight head-and-shoulders close-up of @Name, face filling the frame, <expression>, <place> behind him` | one line, at most 10 words; *How* = "says warmly", "shouts happily", "asks shyly" |
| Action | `medium shot of @Name <doing something> in <place, time, light>` | *Sounds*: 2-3 loud sounds whose source is in the picture |
| Object | `close-up of a folded wet paper ... lying in a puddle` | Shri Tools adds "no faces or eyes" so objects stay objects |

- Write `@Name` for every character in a picture, also in wide shots (that puts the character's picture in).
- Describe the place, time and light the same way in every scene.
- *Camera*: "static close-up at eye level", "slow push-in on his face", "low angle tracking her run".
- Scene 1 is the hook: a funny or shocking line or action in the first two seconds, never a calm landscape.
- At most two characters in one picture; side characters who come back get their own character card.
- For an episode where a character dresses differently (night, festival, uniform), give the video its own look for
  that character (project `looks`), instead of changing the character card.

## Files

```
library\characters\<id>\     character.json, front.png, face.png, photos\
library\seasons\<id>\        season.json
library\projects\<id>\       project.json (story + scenes), status.json, results.json, publish.json,
                             pictures\, clips\ (+ the H3 prompt of each clip), versions\ (every try), output\
library\queue.json, settings.json, logs\, trash\ (deleted things go here, nothing is erased)
output\                      every final episode, named after its title
```

# How Shri Tools works (and what we learned about MiniMax H3)

## The pipeline

| Step | What happens | Code |
|---|---|---|
| write | the story AI (Ollama, JSON schema) writes title, logline, hook words, plot and N scenes, following the H3 rules below | `studio/writer.py` |
| sheets | each character gets a full-body and a face picture (FLUX.2 klein, 4 steps); photos of a real person can be references | `produce.make_sheet` |
| pictures | the first frame of every scene: the picture text with each `@Name` replaced by name + look, and up to 3 character pictures as reference latents. Then the **picture check**: a vision AI counts the people in every picture; a doubled or extra person, a person in an empty shot or a different action -> drawn again with a new seed (2 tries, the best one stays) | `produce.picture_prompt`, `studio/picqc.py` |
| clips | one MiniMax H3 image-to-video clip per scene (124 frames = 5.2 s at 24 fps, 864x480, 4 steps) with its own voice and sounds | `produce.h3_prompt`, `engine/talk_clip.py` |
| check | Whisper listens to every clip and the vision AI looks at a frame near its end (a person who walked in, a doubled character); failed clips are remade with a new seed (2 rounds by default), every try is kept in `versions\` and the best one wins | `engine/scene_qc.py`, `produce.look_at_clips` |
| final | the clips are joined with 0.3 s crossfades; each clip keeps its own sound, levelled to the same loudness | `engine/assemble.py` |
| publish | titles/description/tags (LLM), subtitles from the measured speech windows, 3 thumbnails, three 9:16 Shorts (hook + climax, the opening story, the strongest moment) | `produce.step_publish` |

The server (`studio/server.py`) runs one GPU job at a time from `library/queue.json` in a separate worker process.
Before H3, ComfyUI is restarted so the picture model is completely out of memory; before the LLM, ComfyUI is stopped.

## The H3 prompt

H3 is a joint audio-video model: it makes picture, speech, lip movement and sound effects in one pass. Every clip's
full prompt is saved next to it (`clips/sNNN.txt`). Structure:

```
For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.

integrated_multimodal_description: [Shot 1] A scene from a 3D animated Pixar-style cartoon film, in exactly the same
visual style as <Picture 1>: <the picture text>. <Name> is <the same look words every scene>. <the acting beats>.
Then <Name> says warmly in a warm, deep, gentle man's voice: <d>[English] Tuntun, no. We never say that.</d>
<Name>'s mouth shapes every word clearly. Camera: static eye-level close-up with a very slow push-in.
<talking template: lip sync, only this line, nobody else talks, keep faces/clothes/composition>

overall_soundscape: The spoken line in clear English, ... softly: the neem leaves rustle in the breeze. No other voices...

non_diegetic_music: N/A
```

Action scenes use a silent template instead ("This shot has no dialogue ... all mouths stay closed") and end with
"Nobody speaks. Only <the sounds>."

## Rules that made the difference

Each of these came from a broken clip:

1. **Talking = one face filling the frame.** In wide shots the mouth is a few pixels and barely moves. "Tight
   head-and-shoulders close-up of @Name, face filling the frame" gives clear lip sync.
2. **Short lines** (at most ~10 words, under 4.5 s). Longer clips need more frames, and 141+ frames run out of
   memory on 4 GB.
3. **Sound words become objects.** "A ceiling fan creaks" put a fan floating in the sky outside a window. Only name
   sounds whose source is already in the picture (her bangles, the broom, rain on the tin roof).
4. **Never write "silence", "silent", "quiet", "tense" or "standoff".** H3 takes them literally and makes a clip with
   almost no sound. Name two or three loud, concrete sounds instead.
5. **Quiet scenes need loud sounds.** People standing still with "wind and distant village sounds" came out silent;
   "a dog barks, a bicycle bell rings, a rooster crows" did not.
6. **H3 is a Chinese model**: without guidance it sometimes adds Chinese crowd voices or gibberish. The templates say
   "Apart from this one line nobody says anything, the people in the background do not talk", and the quality gate
   rejects Chinese/Japanese/Korean/Thai script in the transcript.
7. **One conditional template does not work.** "If a line is in quotes ... otherwise nobody speaks" made H3 invent
   speech; separate talking and silent templates fixed it.
8. **Unnamed extras change face every scene.** Give recurring side characters a character card, or keep extras far
   away and small.
9. **The character's look words win over the scene text.** "Aviator sunglasses" in the look made sunglasses appear
   at night even when the scene said "no sunglasses". A video can override a character's look (`looks` in the
   project) for such episodes.
10. **Never let another app re-time the clips.** Rendering the scenes on a narration timeline moved sound and
    picture apart by up to 3 s. Shri Tools joins the clips themselves, so each clip's sound stays with its picture.
11. **Memory on 4 GB VRAM / 24 GB RAM**: ComfyUI with `--disable-smart-memory --cache-none`, ComfyUI restarted
    between FLUX.2 klein and H3, and the GGUF embedding table read row by row (the patch). With ComfyUI's default
    smart memory, two clips in a row peaked at 39.9 GB of a 42.7 GB commit limit.
12. **In cartoon styles, objects grow faces** (a ball with eyes, a paper boat with a mouth). Pictures without
    characters get "objects are ordinary objects with no faces or eyes".
13. **Frozen splashes become objects.** A still picture of raindrops splashing turned one frozen splash into a
    twig standing next to the object. For close-ups of objects in rain write "rain ripples on the puddle".

## The quality gate

`engine/scene_qc.py` checks every clip:

| Check | Talk scene | Action scene |
|---|---|---|
| loud enough | rms ≥ 0.006 (below 0.003 = "no sound", 0.003-0.006 = "too quiet") | same |
| right words | English: ≥ 75% of the line's words heard (Whisper base.en; letter similarity for Indian names). Indian languages: ≥ 50% of the sounds heard (Whisper small in that language, or the romanized line vs the English Whisper spelling) | at most 3 words (Whisper's stock guesses on noise are ignored) |
| no foreign speech | English lines: no Chinese/Japanese/Korean/Thai script and no Hindi/Urdu words mixed into English. Indian-language lines: no Chinese/Japanese/Korean (Whisper base writes Indian speech in random scripts, e.g. Konkani in Thai letters, so other scripts are not counted) | same as English |
| no extra talking | at most 5 extra words | - |

A failed clip is remade with a new seed. After the last round the best try is kept (passes first, then fewer
problems, then better match).

### Pictures and people (the vision check)

Picture models and H3 sometimes add people: a second copy of the toddler, a stranger behind the cast, a person who
walks into an empty shot. With videos made automatically (n8n, schedules) nobody would see it, so a vision AI looks:

- **Before the videos**, at every picture. It first counts and describes everyone it sees *without* being told who
  should be there (told the cast list, it tends to repeat the list instead of looking), then says whether the picture
  shows the described action. More people than the `@Names` in the picture text, a doubled character, or anyone in
  a picture that says "nobody / empty" -> the picture is drawn again (Settings `picture_check_tries`, default 2).
  Crowds are allowed when the picture text asks for them (families, villagers, people in the background) and not
  limited by "only these two people" / "exactly three people and nobody else". Statues, idols and posters do not count.
- **After the videos**, it counts the people at the start of every clip and 0.6 s before its end (episodes and
  music videos): more people at the end means someone walked into the shot, and the clip is made again. It compares
  the clip with its own start, not with the cast list - a festival crowd that is already in the picture stays in the
  video, and that is fine (an earlier version compared with the cast list and failed 11 good clips of a garba night).

The local model is `qwen2.5vl:7b` in Ollama (Settings `vision_model`), about 1 minute per picture on a 4 GB GPU. It
counts people well but misses subtle action differences (a handshake instead of a wrist grab); with a Claude, OpenAI
or Gemini key in Settings the cloud model is used instead. Tested on 9 known good/bad pictures: 8 right, no good
picture failed; the clip check on 3 known clips: 3 right. Turn it off with Settings `picture_check: false`.

## Timings on the test laptop (RTX 3050 4 GB, 24 GB RAM)

| Work | Time |
|---|---|
| character sheet (2 pictures) | ~1 min |
| scene picture | 25 s (1 reference) to 60 s (3 references) |
| H3 clip 864x480, 124 frames | 7.5-12 min (text encoder ~4 min, 4 sampling steps, VAE decode) |
| check round, 18 clips | ~2 min |
| final + YouTube kit | ~5 min |
| 18-scene episode, start to end | ~4 h |

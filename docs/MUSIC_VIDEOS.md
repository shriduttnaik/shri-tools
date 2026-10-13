# Music videos

**Music videos** (in the menu, under Seasons) makes a song and a lip-synced video for it:

1. **Song**: [MiniMax Music 3](https://huggingface.co/MiniMaxAI/MiniMax-Music3) makes a complete song (vocals and
   instruments, 32 kHz stereo; the model can do 5 minutes, Shri Tools offers up to 3) from **lyrics** and a **music description**. Leave the lyrics
   empty and the story AI writes them in the language you chose, with `[Verse]`, `[Chorus]`, `[Instrumental]` tags.
2. **Plan**: Whisper listens to the song and finds where words are sung. The song is cut into shots of exactly 124
   frames (5.17 s). Sung parts become close-ups of your singer, music-only parts become story or dance shots. The
   story AI writes each shot's picture.
3. **Pictures**: FLUX.2 klein draws every shot with your singer's character pictures as reference. With *Let me check
   the pictures* on, it stops here: fix any picture, then press *Pictures OK - make videos*.
4. **Clips**: every shot is a MiniMax H3 clip that gets **its own 5.17 s piece of the song as the audio guide**, so
   the singer's lips and everybody's movement follow the music.
5. **Final**: the clips are put back to back under the original song. Each clip is exactly its piece of the song, so
   picture and music stay in sync for the whole video. Then a YouTube kit: titles, description, tags, 3 thumbnails,
   lyric subtitles (`.srt`) and a 9:16 Short.

## Choices

| Setting | Options |
|---|---|
| Language | English, Hindi, Kannada, Konkani, Marathi, Tamil, Telugu, Malayalam, Bengali, Gujarati, Punjabi, Urdu |
| Music style | Bollywood romantic, Bollywood dance, Indian folk, Devotional / bhajan, Kids rhyme, Lullaby, Pop, Rock, Hip-hop / rap, Lo-fi chill, EDM, Ghazal / classical, South Indian fusion, Patriotic |
| Voice | Female, Male, Duet, Child, Choir, Instrumental |
| Video style | 3D Pixar cartoon, Realistic cinematic, Anime, Storybook, Claymation, Neon music video, Retro Bollywood, Comic book |
| Singer | any character from your library (two for a duet), or a new one described in the form |
| Length | 30 s to 3 min (about 11 minutes of video making per 5-second shot on a 4 GB GPU) |

The **Song** tab of a music video shows the lyrics and the music description (editable), plays the song, and has
*New take of the song* (same lyrics, new seed) and *Plan shots again*.

## Writing a good music description

MiniMax Music 3 follows a three-part description best:

```
Global Metadata: cheerful children's song, 112 BPM, C major, bouncy and simple, morning in a colorful colony.
Vocal Details: a sweet, bright child's voice, singing in Hindi, clear words, happy smile in the voice.
Arrangement: xylophone and ukulele intro; verses with claps and light percussion; big catchy chorus with a small
choir; short instrumental with a tin whistle; outro slows down to a last "thank you".
```

Lyrics: short singable lines, a chorus that repeats, and one tag per section on its own line. Write Indian-language
lyrics in their own script.

## Models (about 12 GB, downloaded by `setup\check_setup.py --download`)

| ComfyUI folder | File | Size |
|---|---|---|
| `models\diffusion_models` | `minimax_music3_dit_int8_convrot.safetensors` | 2.5 GB |
| `models\text_encoders` | `minimax_music3_text_encoder_pruned_int8_convrot.safetensors` | 9.2 GB |
| `models\vae` | `minimax_music3_dav.safetensors` | 0.2 GB |

From [Comfy-Org/MiniMax-Music-3](https://huggingface.co/Comfy-Org/MiniMax-Music-3) (the int8 files are the low-VRAM
versions). ComfyUI has native nodes for it (`MiniMaxMusic3TextEncode`, `EmptyMiniMaxMusic3LatentAudio`); Shri Tools
uses the same graph as ComfyUI's official template (30 steps, cfg 1.7, tiled audio decode).

**License:** the MiniMax-Music3 Community License. Among other things, a commercial product that uses it must show
"MiniMax-Music3" in its interface, and above a revenue threshold you need written permission from MiniMax. Read the
full [license](https://huggingface.co/MiniMaxAI/MiniMax-Music3/blob/main/LICENSE) before you monetize songs.

## Notes

- In music videos the sound comes from the song, not from H3: H3 only uses its piece of the song as a guide for the
  lips and the movement. (In story episodes all voices are H3's own.)
- Via the API: `POST /api/connect/videos` with `"kind": "music"`, `idea` or `lyrics`, `language`, `genre`, `vocal`,
  `style`, `singers` (names), `seconds` (see [CONNECT_API.md](CONNECT_API.md)).

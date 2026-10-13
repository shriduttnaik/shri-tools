# Setup (Windows + NVIDIA)

About an hour of clicking plus the downloads (about 57 GB, 12 GB of it only for music videos). Everything below is free.

## 0. What you need

- Windows 10/11, an NVIDIA GPU with **4 GB VRAM or more** and a recent driver
- **24 GB RAM** recommended (16 GB is untested; 8 GB crashes in the H3 step at 864x480)
- about **60 GB free disk** (models + a few episodes)
- Microsoft Edge (comes with Windows; draws Indian-script captions)

## 1. ComfyUI (runs the picture and video models)

1. Download the **ComfyUI portable for Windows, NVIDIA** release from
   https://github.com/comfyanonymous/ComfyUI/releases and unpack it, e.g. to `C:\AI\ComfyUI_windows_portable`.
   It must be new enough to have the native MiniMax H3 nodes (`MiniMaxH3ImageToVideo`); any 2026 release does.
2. Add the GGUF loader:
   ```
   cd C:\AI\ComfyUI_windows_portable\ComfyUI\custom_nodes
   git clone https://github.com/city96/ComfyUI-GGUF
   ```
3. The H3 GGUF files carry no architecture metadata, so ComfyUI-GGUF needs a small fix
   (`setup\comfyui-gguf-h3.patch`). `setup\check_setup.py` applies it for you (it runs `git apply`). The patch also
   makes the text encoder's embedding table load row by row instead of all at once, which saves about 3 GB of VRAM.

## 2. FFmpeg

Download an FFmpeg build (e.g. the "essentials" build from https://www.gyan.dev/ffmpeg/builds/), unpack it and note
the path of `bin\ffmpeg.exe`.

## 3. The story writer: Ollama (or a cloud AI)

Install from https://ollama.com, then in a terminal:

```
ollama pull gpt-oss:20b
```

`qwen3.5:9b` also works (faster, a bit simpler stories); pick it in Shri Tools > Settings.

No Ollama, or a slower PC? In Settings > Story AI choose **Claude**, **ChatGPT**, **Gemini** or an
**OpenAI-compatible** service, paste your API key and press *Test*. Only the writing (stories, lyrics, YouTube texts,
translations) goes to that service; everything else stays on your laptop. Claude uses the official `anthropic` Python
package: `<ComfyUI>\python_embeded\python.exe -m pip install anthropic`.

## 4. Shri Tools

1. Download this repository (Code > Download ZIP, or `git clone`), e.g. to `C:\AI\ShriTub`.
2. Copy `config.example.json` to `config.json` and edit the paths:

   | Key | What |
   |---|---|
   | `comfy_dir` | the ComfyUI portable folder |
   | `comfy_python` | `<comfy_dir>\python_embeded\python.exe` |
   | `comfy_url` | leave `http://127.0.0.1:8188` |
   | `comfy_flags` | leave `--disable-smart-memory --cache-none` (needed on 4 GB VRAM / 24 GB RAM) |
   | `ffmpeg` | path of `ffmpeg.exe` |
   | `music_python`, `audiocraft_cache` | optional, only for background music (a Python with `audiocraft`) |

3. Download the models and check everything (run it with ComfyUI's Python, it has everything it needs):

   ```
   C:\AI\ComfyUI_windows_portable\python_embeded\python.exe setup\check_setup.py --download
   ```

   It ends with `READY` or lists what is missing, and writes `setup\setup_report.txt`.

### Models (downloaded by check_setup.py)

| ComfyUI folder | File | Size | From |
|---|---|---|---|
| `models\unet` | `minimax_h3_fl2va_pruned-UD-Q3_K_XL.gguf` | 9.6 GB | [unsloth/MiniMax-H3-GGUF](https://huggingface.co/unsloth/MiniMax-H3-GGUF) |
| `models\text_encoders` | `qwen3vl-32B-MiniMax-H3-Q2_K.gguf` | 8.5 GB | [realrebelai/MiniMax-H3_GGUFs](https://huggingface.co/realrebelai/MiniMax-H3_GGUFs) |
| `models\loras` | `minimax_h3_fl2v_lightx2v_turbo_4step_v0.1_comfy.safetensors` | 2.0 GB | [Kijai/MiniMax-H3_comfy](https://huggingface.co/Kijai/MiniMax-H3_comfy) (`loras/`) |
| `models\vae` | `minimax_h3_video_vae_int8_convrot.safetensors` | 2.8 GB | [Comfy-Org/MiniMax-H3](https://huggingface.co/Comfy-Org/MiniMax-H3) (`vae/`) |
| `models\vae` | `minimax_h3_audio_vae_fp32.safetensors` | 0.6 GB | [Comfy-Org/MiniMax-H3](https://huggingface.co/Comfy-Org/MiniMax-H3) (`vae/`) |
| `models\diffusion_models` | `flux-2-klein-4b-fp8.safetensors` | 4.1 GB | [black-forest-labs/FLUX.2-klein-4b-fp8](https://huggingface.co/black-forest-labs/FLUX.2-klein-4b-fp8) |
| `models\text_encoders` | `qwen_3_4b.safetensors` | 8.0 GB | [Comfy-Org/vae-text-encorder-for-flux-klein-4b](https://huggingface.co/Comfy-Org/vae-text-encorder-for-flux-klein-4b) |
| `models\vae` | `flux2-vae.safetensors` | 0.3 GB | same as above |
| `models\diffusion_models` | `minimax_music3_dit_int8_convrot.safetensors` | 2.5 GB | [Comfy-Org/MiniMax-Music-3](https://huggingface.co/Comfy-Org/MiniMax-Music-3) (music videos) |
| `models	ext_encoders` | `minimax_music3_text_encoder_pruned_int8_convrot.safetensors` | 9.2 GB | same (music videos) |
| `modelsae` | `minimax_music3_dav.safetensors` | 0.2 GB | same (music videos) |
| Hugging Face cache | `openai/whisper-base.en`, `openai/whisper-base`, `openai/whisper-small` | 1.5 GB | [openai](https://huggingface.co/openai) |

If a download fails with 401 or 403, open that model page on huggingface.co while logged in, accept its license,
run `C:\AI\ComfyUI_windows_portable\python_embeded\python.exe -m huggingface_hub.commands.huggingface_cli login`
and start `check_setup.py --download` again.

Why these sizes: the H3 Q3 GGUF is the smallest that still gives clean faces and clear speech; the Q2 text encoder
is the smallest H3 text encoder; the Kijai v0.1 4-step LoRA works with the pruned GGUF (the 8-step v1.0 LoRA made
smeared pictures and droning audio with it).

## 5. Start

Double-click **Shri Tools.bat**. It starts the server with ComfyUI's Python and opens the app in an Edge app window
(http://127.0.0.1:7880). ComfyUI is started automatically when a job needs it. A desktop shortcut to `Shri Tools.bat`
is handy.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `config.json is missing` | copy `config.example.json` to `config.json` |
| Clip step: "ComfyUI stopped (probably out of memory)" | Shri Tools restarts ComfyUI and tries again, then falls back to 736x416. Close other GPU apps. With less than 24 GB RAM pick 736x416 in Settings |
| `Unknown model architecture` when loading the H3 GGUF | the ComfyUI-GGUF fix is missing: run `check_setup.py` again |
| Story step fails at once | Ollama is not running or the model is not pulled (`ollama pull gpt-oss:20b`) |
| Clips have Chinese words or extra talking | the quality gate remakes them; if one scene keeps failing, shorten its line or rewrite the picture (see HOW_IT_WORKS) |
| A scene is nearly silent | name two or three loud sounds whose source is in the picture; never write "silence" or "tense" |
| Indian captions show boxes | Edge is missing; install Microsoft Edge |

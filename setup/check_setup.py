"""Shri Tools setup check: is everything in place to make videos? Optionally downloads what is missing.

  <ComfyUI portable>\\python_embeded\\python.exe setup\\check_setup.py            check only
  <ComfyUI portable>\\python_embeded\\python.exe setup\\check_setup.py --download  also download missing models

Writes setup\\setup_report.txt. Models go into ComfyUI's models folders (about 48 GB) and the Whisper speech
checkers into the Hugging Face cache (about 1.5 GB). MiniMax H3 uses the MiniMax H3 Community License: if a
download says 401/403, open the model page on huggingface.co, accept the license, run `huggingface-cli login`
and start again.
"""
import json, os, shutil, subprocess, sys, time, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORT = os.path.join(ROOT, "setup", "setup_report.txt")
DOWNLOAD = "--download" in sys.argv

# (ComfyUI models subfolder, file name, Hugging Face repo, path in the repo, GB)
MODELS = [
    ("unet", "minimax_h3_fl2va_pruned-UD-Q3_K_XL.gguf", "unsloth/MiniMax-H3-GGUF",
     "minimax_h3_fl2va_pruned-UD-Q3_K_XL.gguf", 9.6),
    ("text_encoders", "qwen3vl-32B-MiniMax-H3-Q2_K.gguf", "realrebelai/MiniMax-H3_GGUFs",
     "qwen3vl-32B-MiniMax-H3-Q2_K.gguf", 8.5),
    ("loras", "minimax_h3_fl2v_lightx2v_turbo_4step_v0.1_comfy.safetensors", "Kijai/MiniMax-H3_comfy",
     "loras/minimax_h3_fl2v_lightx2v_turbo_4step_v0.1_comfy.safetensors", 2.0),
    ("vae", "minimax_h3_video_vae_int8_convrot.safetensors", "Comfy-Org/MiniMax-H3",
     "vae/minimax_h3_video_vae_int8_convrot.safetensors", 2.8),
    ("vae", "minimax_h3_audio_vae_fp32.safetensors", "Comfy-Org/MiniMax-H3",
     "vae/minimax_h3_audio_vae_fp32.safetensors", 0.6),
    ("diffusion_models", "flux-2-klein-4b-fp8.safetensors", "black-forest-labs/FLUX.2-klein-4b-fp8",
     "flux-2-klein-4b-fp8.safetensors", 4.1),
    ("text_encoders", "qwen_3_4b.safetensors", "Comfy-Org/vae-text-encorder-for-flux-klein-4b",
     "split_files/text_encoders/qwen_3_4b.safetensors", 8.0),
    ("vae", "flux2-vae.safetensors", "Comfy-Org/vae-text-encorder-for-flux-klein-4b",
     "split_files/vae/flux2-vae.safetensors", 0.3),
    # music videos (MiniMax Music 3, low-VRAM int8 files)
    ("diffusion_models", "minimax_music3_dit_int8_convrot.safetensors", "Comfy-Org/MiniMax-Music-3",
     "diffusion_models/minimax_music3_dit_int8_convrot.safetensors", 2.5),
    ("text_encoders", "minimax_music3_text_encoder_pruned_int8_convrot.safetensors", "Comfy-Org/MiniMax-Music-3",
     "text_encoders/minimax_music3_text_encoder_pruned_int8_convrot.safetensors", 9.2),
    ("vae", "minimax_music3_dav.safetensors", "Comfy-Org/MiniMax-Music-3", "vae/minimax_music3_dav.safetensors", 0.2),
]
WHISPER = ["openai/whisper-base.en", "openai/whisper-base", "openai/whisper-small"]

lines = []


def say(state, what, detail=""):
    row = f"[{state:<5}] {what}" + (f" - {detail}" if detail else "")
    lines.append(row)
    print(row, flush=True)


def ping(url):
    try:
        with urllib.request.urlopen(url, timeout=3) as r:
            return json.loads(r.read() or b"{}")
    except Exception:
        return None


def hf_download(repo, path, dest):
    from huggingface_hub import hf_hub_download
    tmp = os.path.join(os.path.dirname(dest), "_download")
    got = hf_hub_download(repo, path, local_dir=tmp)
    shutil.move(got, dest)
    shutil.rmtree(tmp, ignore_errors=True)


def main():
    cfg_path = os.path.join(ROOT, "config.json")
    if not os.path.exists(cfg_path):
        say("ERROR", "config.json", "missing: copy config.example.json to config.json and set your paths")
        return finish()
    cfg = json.load(open(cfg_path, encoding="utf-8"))

    # computer
    try:
        gpu = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
                             capture_output=True, text=True, timeout=20).stdout.strip()
        say("OK" if gpu else "WARN", "GPU", gpu or "no NVIDIA GPU found (H3 needs CUDA)")
    except Exception:
        say("WARN", "GPU", "nvidia-smi not found (H3 needs an NVIDIA GPU with CUDA)")
    try:
        import psutil
        ram = psutil.virtual_memory().total / 2 ** 30
        say("OK" if ram >= 23 else "WARN", "RAM", f"{ram:.1f} GB" + ("" if ram >= 23 else
                                                                     " (24 GB or more recommended; 8 GB crashes at 864x480)"))
    except ImportError:
        pass
    free = shutil.disk_usage(ROOT).free / 1e9
    say("OK" if free > 20 else "WARN", "free disk", f"{free:.0f} GB")

    # paths
    for key in ("comfy_dir", "comfy_python", "ffmpeg"):
        p = cfg.get(key, "")
        say("OK" if p and os.path.exists(p) else "ERROR", f"config {key}", p or "(empty)")
    if cfg.get("music_python"):
        say("OK" if os.path.exists(cfg["music_python"]) else "WARN", "config music_python (optional MusicGen)",
            cfg["music_python"])

    # models
    models = os.path.join(cfg.get("comfy_dir", ""), "ComfyUI", "models")
    for folder, name, repo, path, gb in MODELS:
        dest = os.path.join(models, folder, name)
        if os.path.exists(dest):
            say("OK", f"model {name}", f"{os.path.getsize(dest) / 1e9:.1f} GB")
        elif DOWNLOAD:
            say("...", f"downloading {name}", f"{gb} GB from {repo}")
            try:
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                hf_download(repo, path, dest)
                say("OK", f"model {name}", "downloaded")
            except Exception as e:
                say("ERROR", f"model {name}", f"download failed: {str(e)[:200]}")
        else:
            say("MISS", f"model {name}", f"{gb} GB - https://huggingface.co/{repo} ({path}) -> models\\{folder}")

    # ComfyUI-GGUF with the MiniMax H3 fix
    gguf = os.path.join(cfg.get("comfy_dir", ""), "ComfyUI", "custom_nodes", "ComfyUI-GGUF")
    if not os.path.isdir(gguf):
        say("ERROR", "ComfyUI-GGUF", "missing: git clone https://github.com/city96/ComfyUI-GGUF into "
                                     "ComfyUI\\custom_nodes, then apply setup\\comfyui-gguf-h3.patch")
    else:
        patched = "minimax_h3" in open(os.path.join(gguf, "loader.py"), encoding="utf-8", errors="ignore").read()
        if not patched:
            r = subprocess.run(["git", "-C", gguf, "apply", os.path.join(ROOT, "setup", "comfyui-gguf-h3.patch")],
                               capture_output=True, text=True)
            patched = r.returncode == 0
        say("OK" if patched else "ERROR", "ComfyUI-GGUF MiniMax H3 fix",
            "applied" if patched else "could not apply setup\\comfyui-gguf-h3.patch (see docs/SETUP.md)")

    # Whisper (quality check)
    try:
        from huggingface_hub import snapshot_download, try_to_load_from_cache
        for repo in WHISPER:
            cached = lambda f: isinstance(try_to_load_from_cache(repo, f), str)
            if cached("config.json") and (cached("model.safetensors") or cached("pytorch_model.bin")):
                say("OK", f"speech check {repo}")
            else:
                if DOWNLOAD:
                    snapshot_download(repo, allow_patterns=["*.json", "*.txt", "model.safetensors"])
                    say("OK", f"speech check {repo}", "downloaded")
                else:
                    say("MISS", f"speech check {repo}", "run with --download")
    except ImportError:
        say("ERROR", "huggingface_hub", "run this with ComfyUI's python")

    # story AI
    st = {}
    try:
        st = json.load(open(os.path.join(ROOT, "library", "settings.json"), encoding="utf-8"))
    except Exception:
        pass
    url, model = st.get("ollama_url", "http://127.0.0.1:11434"), st.get("story_model", "gpt-oss:20b")
    tags = ping(url + "/api/tags")
    if tags is None:
        say("WARN", "Ollama (story AI)", "not running - install from ollama.com, then: ollama pull " + model)
    else:
        have = [m["name"] for m in tags.get("models", [])]
        say("OK" if model in have else "MISS", f"Ollama model {model}", "ready" if model in have else
            f"run: ollama pull {model}")
        vision = st.get("vision_model", "qwen2.5vl:7b")
        say("OK" if vision in have else "WARN", f"Ollama vision model {vision} (picture + video check)",
            "ready" if vision in have else f"run: ollama pull {vision} (without it nothing is checked)")

    # text drawing for Indian languages
    fonts = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
    say("OK" if os.path.exists(os.path.join(fonts, "NIRMALAB.TTF")) else "WARN", "Nirmala UI font (Indian scripts)")
    edge = os.path.join(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), "Microsoft", "Edge",
                        "Application", "msedge.exe")
    say("OK" if os.path.exists(edge) else "WARN", "Microsoft Edge (draws Indian-script captions)")
    return finish()


def finish():
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    bad = [l for l in lines if l.startswith(("[ERROR", "[MISS"))]
    with open(REPORT, "w", encoding="utf-8") as f:
        f.write(f"Shri Tools setup report {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n" + "\n".join(lines) + "\n\n" +
                ("READY - start Shri Tools" if not bad else f"NOT READY - {len(bad)} item(s) to fix") + "\n")
    print("\nREADY - start Shri Tools" if not bad else f"\nNOT READY - fix the {len(bad)} item(s) above "
          "(or run with --download)")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())

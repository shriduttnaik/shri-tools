"""MiniMax H3 image-to-video graph for ComfyUI (picture + prompt -> clip with H3's own voices and sounds), plus the
helpers that start / stop a memory-safe ComfyUI. The studio calls build(image, None, ...): no audio guide, so all
speech is H3's native audio. As a command line tool it can also take a ready voice line as an audio guide (--voice):
  python_embeded\\python.exe talk_clip.py --image s004.png --prompt-file p.txt --out out\\clip [--voice line.wav]
"""
import argparse, json, os, shutil, subprocess, sys, time, urllib.error, urllib.request, wave
import numpy as np

CFG = json.load(open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.json"),
                     encoding="utf-8"))
COMFY_DIR = os.path.join(CFG["comfy_dir"], "ComfyUI")
UNET = "minimax_h3_fl2va_pruned-UD-Q3_K_XL.gguf"
TEXT_ENCODER = "qwen3vl-32B-MiniMax-H3-Q2_K.gguf"
LORA = "minimax_h3_fl2v_lightx2v_turbo_4step_v0.1_comfy.safetensors"
VIDEO_VAE = "minimax_h3_video_vae_int8_convrot.safetensors"
AUDIO_VAE = "minimax_h3_audio_vae_fp32.safetensors"
FPS = 24


def frames_for(seconds):
    n = max(124, round(seconds * FPS))
    return n + (5 - n % 17) % 17  # H3 grid: 17k+5 frames, 124 (~5.2 s) is the trained minimum


def pad_voice(src, dst, lead, total):
    """Silence before the line, the line, silence to the end of the clip (mono 16-bit)."""
    with wave.open(src) as w:
        sr, ch, sw = w.getframerate(), w.getnchannels(), w.getsampwidth()
        a = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16 if sw == 2 else np.int32)
    if ch > 1:
        a = a.reshape(-1, ch).mean(axis=1).astype(np.int16)
    out = np.zeros(int(total * sr), np.int16)
    start = int(lead * sr)
    seg = a[: len(out) - start]
    out[start:start + len(seg)] = seg
    with wave.open(dst, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes(out.tobytes())
    return len(a) / sr


def build(image_name, audio_name, prompt, width, height, length, seed, prefix):
    g = _graph(image_name, audio_name, prompt, width, height, length, seed, prefix)
    if audio_name is None:  # silent shot: no voice guide, H3 makes its own sound (steps, wind, ...)
        del g["20"], g["21"]
        g["12"]["inputs"]["conditioning"] = ["7", 0]
    return g


def _graph(image_name, audio_name, prompt, width, height, length, seed, prefix):
    return {
        "1": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": UNET}},
        "2": {"class_type": "LoraLoaderModelOnly", "inputs": {"model": ["1", 0], "lora_name": LORA, "strength_model": 1.0}},
        "3": {"class_type": "CLIPLoaderGGUF", "inputs": {"clip_name": TEXT_ENCODER, "type": "minimax"}},
        "4": {"class_type": "VAELoader", "inputs": {"vae_name": VIDEO_VAE}},
        "5": {"class_type": "VAELoader", "inputs": {"vae_name": AUDIO_VAE}},
        "6": {"class_type": "LoadImage", "inputs": {"image": image_name}},
        "7": {"class_type": "MiniMaxH3ImageToVideo", "inputs": {
            "clip": ["3", 0], "vae": ["4", 0], "prompt": prompt,
            "width": width, "height": height, "length": length, "first_frame": ["6", 0]}},
        "20": {"class_type": "LoadAudio", "inputs": {"audio": audio_name}},
        "21": {"class_type": "MiniMaxH3AddGuide", "inputs": {
            "positive": ["7", 0], "latent": ["7", 1], "audio_vae": ["5", 0], "audio": ["20", 0], "frame_idx": 0}},
        "8": {"class_type": "MiniMaxH3SigmaShift", "inputs": {"model": ["2", 0], "shift_video": 12.0, "shift_audio": 3.0}},
        "9": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
        "10": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
        "11": {"class_type": "BasicScheduler", "inputs": {"model": ["8", 0], "scheduler": "simple", "steps": 4, "denoise": 1.0}},
        "12": {"class_type": "BasicGuider", "inputs": {"model": ["8", 0], "conditioning": ["21", 0]}},
        "13": {"class_type": "SamplerCustomAdvanced", "inputs": {
            "noise": ["9", 0], "guider": ["12", 0], "sampler": ["10", 0], "sigmas": ["11", 0], "latent_image": ["7", 1]}},
        "14": {"class_type": "VAEDecode", "inputs": {"samples": ["13", 0], "vae": ["4", 0]}},
        "15": {"class_type": "VAEDecodeAudio", "inputs": {"samples": ["13", 0], "vae": ["5", 0]}},
        "16": {"class_type": "CreateVideo", "inputs": {"images": ["14", 0], "audio": ["15", 0], "fps": FPS}},
        "17": {"class_type": "SaveVideo", "inputs": {"video": ["16", 0], "filename_prefix": prefix, "format": "auto"}},
    }


def call(url, data=None):
    req = urllib.request.Request(url, data=json.dumps(data).encode() if data is not None else None,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


# ComfyUI started by Shri Tools; config comfy_flags = its memory options (memory-safe by default: ComfyUI's default
# smart memory keeps the 9.5 GB H3 text encoder in RAM next to the H3 model)
COMFY_START = (f'cd /d {CFG["comfy_dir"]} && python_embeded\\python.exe -s ComfyUI\\main.py '
               f'--windows-standalone-build --port {CFG["comfy_url"].rsplit(":", 1)[-1]} '
               f'{CFG.get("comfy_flags", "--disable-smart-memory --cache-none")} --disable-auto-launch '
               # no quotes here: Popen's list quoting turns them into \" and cmd then ignores the whole line
               f'>> {os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs", "comfyui.log")} 2>&1')


def stop_comfy(server):
    """Stop whatever ComfyUI listens on the server's port (frees all loaded models)."""
    port = server.rsplit(":", 1)[-1]
    out = subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True).stdout
    pids = {p[-1] for p in (l.split() for l in out.splitlines())
            if len(p) >= 5 and p[1].endswith(":" + port) and p[3] == "LISTENING"}
    for pid in pids:
        subprocess.run(["taskkill", "/PID", pid, "/T", "/F"], capture_output=True)
    if pids:
        print(f"stopped ComfyUI on port {port}", flush=True)
        time.sleep(8)


def ensure_comfy(server):
    """Start ComfyUI if it is not running (it can die of out-of-memory during a long clip)."""
    try:
        call(server + "/system_stats"); return
    except Exception:
        pass
    print("ComfyUI not running - starting it", flush=True)
    subprocess.Popen(["cmd", "/c", COMFY_START], creationflags=0x08000000 | 0x00000008)
    for _ in range(100):
        time.sleep(3)
        try:
            call(server + "/system_stats"); time.sleep(5); return
        except Exception:
            pass
    raise RuntimeError("ComfyUI did not start")


def run_once(server, graph, out):
    """Queue the graph and wait. Returns the saved path, or None if ComfyUI crashed."""
    try:
        pid = call(server + "/prompt", {"prompt": graph})["prompt_id"]
        while True:
            time.sleep(30)
            h = call(f"{server}/history/{pid}").get(pid)
            if not h:
                continue
            st = h.get("status", {})
            if st.get("status_str") == "error":
                print("ERROR:", json.dumps(st.get("messages"), indent=1)[-3000:])
                sys.exit(1)
            for node in h.get("outputs", {}).values():
                for key in ("images", "videos", "gifs"):
                    for f in node.get(key, []):
                        src = os.path.join(COMFY_DIR, "output", f.get("subfolder", ""), f["filename"])
                        os.makedirs(os.path.dirname(out), exist_ok=True)
                        dst = out + os.path.splitext(f["filename"])[1]
                        shutil.copy(src, dst)
                        return dst
            print("finished but no video output:", json.dumps(h)[:2000])
            sys.exit(1)
    except (ConnectionError, urllib.error.URLError, OSError) as e:
        print(f"ComfyUI connection lost ({e}) - it probably ran out of memory", flush=True)
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True)
    ap.add_argument("--voice", help="the spoken line (wav); without it the shot is silent (no dialogue)")
    ap.add_argument("--prompt-file", required=True)
    ap.add_argument("--out", required=True, help="output path without extension")
    ap.add_argument("--lead", type=float, default=0.5, help="seconds of silence before the line")
    ap.add_argument("--width", type=int, default=864)
    ap.add_argument("--height", type=int, default=480)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--server", default=CFG["comfy_url"])
    ap.add_argument("--tries", type=int, default=4)
    a = ap.parse_args()

    tag = os.path.basename(a.out)
    image_name = f"talk_{tag}.png"
    shutil.copy(a.image, os.path.join(COMFY_DIR, "input", image_name))
    if a.voice:
        with wave.open(a.voice) as w:
            line_sec = w.getnframes() / w.getframerate()
        length = frames_for(a.lead + line_sec + 0.8)
        if length > 124 and line_sec + 0.5 <= 124 / FPS:
            # longer clips (141+ frames) run out of memory on a 4 GB GPU: trim the silence to stay at 124 frames
            a.lead, length = 0.2, 124
        audio_name = f"talk_{tag}.wav"
        pad_voice(a.voice, os.path.join(COMFY_DIR, "input", audio_name), a.lead, length / FPS)
    else:
        line_sec, length, audio_name = 0.0, 124, None
    prompt = open(a.prompt_file, encoding="utf-8").read().strip()
    graph = build(image_name, audio_name, prompt, a.width, a.height, length, a.seed, "talk/" + tag)

    t0 = time.time()
    for attempt in range(1, a.tries + 1):
        ensure_comfy(a.server)
        print(f"attempt {attempt}: {a.width}x{a.height}, {length} frames, line {line_sec:.1f} s", flush=True)
        dst = run_once(a.server, graph, a.out)
        if dst:
            print(f"DONE in {int(time.time() - t0)} s -> {dst}")
            return
        time.sleep(20)
    print(f"ERROR: gave up after {a.tries} attempts")
    sys.exit(1)


if __name__ == "__main__":
    main()

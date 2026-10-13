"""Background music with MusicGen (stereo-small). Optional: needs a Python with audiocraft (config "music_python").

  <music_python> music.py <out.wav> "<music description>" <seconds>
"""
import json, os, sys, wave
# where the MusicGen weights are (config "audiocraft_cache"; empty = audiocraft's default); T5 is in the HF cache
_cfg = json.load(open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.json"),
                      encoding="utf-8"))
if _cfg.get("audiocraft_cache"):
    os.environ.setdefault("AUDIOCRAFT_CACHE_DIR", _cfg["audiocraft_cache"])
os.environ.setdefault("HF_HUB_OFFLINE", "1")
import numpy as np
import torch
from audiocraft.models import MusicGen

out, desc, seconds = sys.argv[1], sys.argv[2], float(sys.argv[3])
torch.manual_seed(int(os.environ.get("SEED", "11")))
model = MusicGen.get_pretrained("facebook/musicgen-stereo-small", device="cuda" if torch.cuda.is_available() else "cpu")
model.set_generation_params(duration=seconds, extend_stride=18, top_k=250, cfg_coef=3.5)
wav = model.generate([desc], progress=False)[0].float().cpu().numpy()  # (channels, samples)
wav = wav / max(1e-6, float(np.abs(wav).max())) * 0.9
pcm = (wav.T * 32767).astype(np.int16)
with wave.open(out, "wb") as w:
    w.setnchannels(pcm.shape[1]); w.setsampwidth(2); w.setframerate(model.sample_rate)
    w.writeframes(pcm.tobytes())
print(out, round(pcm.shape[0] / model.sample_rate, 1), "s")

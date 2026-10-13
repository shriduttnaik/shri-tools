"""Join talking clips into the final video. Each clip keeps its own sound, so voices stay in sync with faces.

  <comfy_python> assemble.py out.mp4 clip1.mp4 clip2.mp4 ...  [--xfade 0.3] [--size 1920x1080]

Picture and sound use the same crossfade length, so the whole timeline stays aligned.
(Re-timing the clips onto a separate narration track would move sound and picture apart and break lip sync.)
"""
import argparse, json, os, subprocess
import av
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG = json.load(open(os.path.join(ROOT, "config.json"), encoding="utf-8"))


def duration(path):
    c = av.open(path)
    v = c.streams.video[0]
    d = float(v.duration * v.time_base) if v.duration else c.duration / 1e6
    c.close()
    return d


def level_gain(path, target):
    """Gain that brings the clip's sound to the target rms (H3 clips range 0.002-0.3), 0.25x-4x, never clipping."""
    c = av.open(path)
    if not c.streams.audio:
        c.close()
        return 1.0
    x = np.concatenate([f.to_ndarray().reshape(-1) for f in c.decode(audio=0)]).astype(np.float32)
    c.close()
    if x.size == 0:
        return 1.0
    if np.abs(x).max() > 1.5:  # integer samples
        x = x / 32768
    rms = float(np.sqrt((x ** 2).mean())) or 1e-6
    g = min(4.0, max(0.25, target / rms))
    return min(g, 0.95 / max(1e-6, float(np.abs(x).max())))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("clips", nargs="+")
    ap.add_argument("--xfade", type=float, default=0.3)
    ap.add_argument("--size", default="1920x1080")
    ap.add_argument("--level", type=float, default=0.0,
                    help="bring every clip's sound to this loudness (rms, e.g. 0.08; gain limited to 0.25x-4x)")
    ap.add_argument("--music", help="one music track under the whole video (ducked under the clips' sound)")
    ap.add_argument("--music-volume", type=float, default=0.35)
    a = ap.parse_args()
    w, h = a.size.split("x")
    D = a.xfade
    lens = [duration(c) for c in a.clips]
    gains = [level_gain(c, a.level) if a.level > 0 else 1.0 for c in a.clips]
    f = []
    for i in range(len(a.clips)):
        f.append(f"[{i}:v]scale={w}:{h}:force_original_aspect_ratio=increase:flags=lanczos,crop={w}:{h},"
                 f"setsar=1,format=yuv420p,trim=duration={lens[i]:.3f},setpts=PTS-STARTPTS,"
                 f"fps=24,settb=AVTB[v{i}]")  # xfade needs a constant frame rate on every input
        f.append(f"[{i}:a]aresample=48000,aformat=channel_layouts=stereo,volume={gains[i]:.3f},"
                 f"atrim=duration={lens[i]:.3f},asetpts=PTS-STARTPTS,apad=whole_dur={lens[i]:.3f}[a{i}]")
    vlast, alast, t = "v0", "a0", lens[0]
    for i in range(1, len(a.clips)):
        off = t - D
        f.append(f"[{vlast}][v{i}]xfade=transition=fade:duration={D}:offset={off:.3f}[x{i}]")
        f.append(f"[{alast}][a{i}]acrossfade=d={D}[y{i}]")
        vlast, alast, t = f"x{i}", f"y{i}", t + lens[i] - D
    # xfade switches to yuv444p (High 4:4:4), which Windows Media Player and phones can't play: back to 4:2:0
    f.append(f"[{vlast}]fade=t=in:st=0:d=0.5,fade=t=out:st={t - 1.0:.3f}:d=1.0,format=yuv420p[vout]")
    if a.music:
        m = len(a.clips)
        f.append(f"[{alast}]afade=t=in:st=0:d=0.3,afade=t=out:st={t - 1.0:.3f}:d=1.0,asplit=2[ak][asc]")
        f.append(f"[{m}:a]aresample=48000,aformat=channel_layouts=stereo,atrim=duration={t:.3f},asetpts=PTS-STARTPTS,"
                 f"apad=whole_dur={t:.3f},volume={a.music_volume},afade=t=in:st=0:d=1.0,"
                 f"afade=t=out:st={t - 2.5:.3f}:d=2.5[mus]")
        f.append("[mus][asc]sidechaincompress=threshold=0.04:ratio=5:attack=30:release=500[duck]")
        f.append("[ak][duck]amix=inputs=2:duration=first:normalize=0[aout]")
    else:
        f.append(f"[{alast}]afade=t=in:st=0:d=0.3,afade=t=out:st={t - 1.0:.3f}:d=1.0[aout]")
    cmd = [CFG["ffmpeg"], "-y", "-hide_banner", "-loglevel", "error"]
    for c in a.clips:
        cmd += ["-i", c]
    if a.music:
        cmd += ["-i", a.music]
    cmd += ["-filter_complex", ";".join(f), "-map", "[vout]", "-map", "[aout]",
            "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-profile:v", "high",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart", a.out]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise SystemExit("ffmpeg failed: " + r.stderr[-2000:])
    print(f"assembled {len(a.clips)} clips -> {a.out} ({duration(a.out):.1f} s, expected {t:.1f} s)")


if __name__ == "__main__":
    main()

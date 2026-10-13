"""Your logo on every video: a short intro with the waving saffron flag, a "subscribe" end card and a small corner logo.

Frames are drawn here with Pillow from the same flag shapes as web/logo.svg (three key shapes, smoothly in a loop),
then FFmpeg makes the clips. Everything is cached in library/brand/ and made again when the settings change.
"""
import json, math, os, re, shutil, subprocess, tempfile

import store

FLAG_KEYS = [  # the flag cloth of web/logo.svg (viewBox 900 x 250)
    "M44 50 C80 40,110 70,150 62 L168 74 C150 80,135 84,128 90 C145 98,165 104,182 118 C150 120,110 112,66 120 Z",
    "M44 50 C75 58,112 52,150 72 L170 84 C152 87,138 90,130 97 C148 105,166 111,180 127 C148 125,108 129,66 120 Z",
    "M44 50 C85 44,105 62,148 58 L166 66 C148 75,134 81,126 88 C144 94,166 98,186 108 C152 116,112 106,66 120 Z",
]
FONT = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "seguibl.ttf")  # Segoe UI Black
GREEN, WHITE, SAFFRON = (57, 255, 136), (255, 255, 255), (255, 122, 16)


def _nums(path):
    return [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", path)]


def _flag_points(t):
    """Outline of the flag at time t (seconds), the shapes blended like the SVG animation (2.4 s loop)."""
    phase = (t % 2.4) / 2.4 * 3
    i = int(phase) % 3
    f = phase - int(phase)
    f = f * f * (3 - 2 * f)  # ease in/out
    a, b = _nums(FLAG_KEYS[i]), _nums(FLAG_KEYS[(i + 1) % 3])
    v = [x + (y - x) * f for x, y in zip(a, b)]
    # M p0, C c1 c2 p1, L p2, C c c p3, C c c p4, C c c p5, Z  (same command layout in every key shape)
    pts, cur, k = [], (v[0], v[1]), 2
    for cmd in ("C", "L", "C", "C", "C"):
        if cmd == "L":
            cur = (v[k], v[k + 1]); pts.append(cur); k += 2
            continue
        c1, c2, p = (v[k], v[k + 1]), (v[k + 2], v[k + 3]), (v[k + 4], v[k + 5])
        for j in range(1, 25):
            s = j / 24
            pts.append(tuple((1 - s) ** 3 * cur[n] + 3 * (1 - s) ** 2 * s * c1[n] + 3 * (1 - s) * s ** 2 * c2[n] + s ** 3 * p[n]
                             for n in (0, 1)))
        cur, k = p, k + 6
    return [(v[0], v[1])] + pts


def draw_logo(img, x, y, width, t, tub=True):
    """The SHRI TOOLS logo (or just the flag + SHRI) at (x, y), `width` pixels wide, flag at time t."""
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
    sc = width / 900
    ss = 2  # draw at double size, then shrink: smooth edges
    W, H = int(900 * sc * ss), int(250 * sc * ss)
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    k = sc * ss
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).polygon([(px * k, py * k) for px, py in _flag_points(t)], fill=255)
    grad = Image.new("RGBA", (W, H))
    gd = ImageDraw.Draw(grad)
    for gx in range(W):  # saffron gradient, darker at the pole
        f = gx / max(1, int(190 * k))
        gd.line([(gx, 0), (gx, H)], fill=(255, int(90 + 64 * min(1, f)), int(0 + 46 * min(1, f)), 255))
    layer.paste(grad, (0, 0), mask)
    d.line([(40 * k, 42 * k), (92 * k, 238 * k)], fill=SAFFRON + (255,), width=max(2, int(5 * k)))
    d.ellipse([(35 * k, 35 * k), (45 * k, 45 * k)], fill=(255, 154, 46, 255))
    font = ImageFont.truetype(FONT, int(158 * k)) if os.path.exists(FONT) else ImageFont.load_default()

    def word(text, left, width_px, color):
        tw = font.getlength(text)
        tmp = Image.new("RGBA", (int(tw) + 4, int(200 * k)), (0, 0, 0, 0))
        ImageDraw.Draw(tmp).text((0, 0), text, font=font, fill=color + (255,))
        tmp = tmp.resize((int(width_px * k), tmp.height))
        top = int(200 * k - font.getbbox("S")[3])
        layer.alpha_composite(tmp, (int(left * k), max(0, top)))
    word("SHRI", 82, 318, WHITE)
    if tub:
        word("TOOLS", 436, 440, GREEN)
    small = layer.resize((W // ss, H // ss), Image.LANCZOS)
    glow = small.filter(ImageFilter.GaussianBlur(max(2, width / 90)))
    img.alpha_composite(glow, (int(x), int(y)))
    img.alpha_composite(small, (int(x), int(y)))
    return img


def _settings_key(st):
    return json.dumps({k: st.get(k) for k in ("brand_intro", "brand_end", "brand_watermark", "brand_end_text")}) + "v1"


def _encode(frames_dir, out, secs, ffmpeg):
    r = subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-framerate", "24", "-i", os.path.join(frames_dir, "f%04d.png"),
                        "-f", "lavfi", "-t", f"{secs}", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
                        "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac",
                        "-shortest", out], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError("brand clip failed: " + r.stderr[-300:])


def brand_files(ffmpeg):
    """intro.mp4, end.mp4, watermark.png in library/brand (made once, again only when the settings change)."""
    from PIL import Image, ImageDraw, ImageFont
    st = store.settings()
    bdir = os.path.join(store.LIB, "brand")
    os.makedirs(bdir, exist_ok=True)
    key_file = os.path.join(bdir, "key.txt")
    key = _settings_key(st)
    fresh = os.path.exists(key_file) and open(key_file).read() == key
    out = {}
    if st.get("brand_intro"):
        p = os.path.join(bdir, "intro.mp4")
        if not (fresh and os.path.exists(p)):
            tmp = tempfile.mkdtemp(prefix="stb_brand_")
            for i in range(48):  # 2 s: fade in, the flag waves
                t = i / 24
                im = Image.new("RGBA", (1920, 1080), (0, 0, 0, 255))
                draw_logo(im, 960 - 520, 540 - 176, 1040, t)
                a = min(1.0, t / 0.35) * min(1.0, (2.0 - t) / 0.3)
                im = Image.blend(Image.new("RGBA", im.size, (0, 0, 0, 255)), im, max(0.0, a))
                im.convert("RGB").save(os.path.join(tmp, f"f{i:04d}.png"))
            _encode(tmp, p, 2.0, ffmpeg)
            shutil.rmtree(tmp, ignore_errors=True)
        out["intro"] = p
    if st.get("brand_end"):
        p = os.path.join(bdir, "end.mp4")
        if not (fresh and os.path.exists(p)):
            tmp = tempfile.mkdtemp(prefix="stb_brand_")
            font = ImageFont.truetype(FONT, 84) if os.path.exists(FONT) else ImageFont.load_default()
            text = st.get("brand_end_text") or "SUBSCRIBE FOR THE NEXT EPISODE"
            for i in range(72):  # 3 s
                t = i / 24
                im = Image.new("RGBA", (1920, 1080), (0, 0, 0, 255))
                draw_logo(im, 960 - 420, 250, 840, t)
                d = ImageDraw.Draw(im)
                tw = font.getlength(text)
                pulse = 0.75 + 0.25 * math.sin(t * math.pi * 2 / 1.2)
                d.rounded_rectangle([960 - tw / 2 - 40, 640, 960 + tw / 2 + 40, 760], 26,
                                    outline=GREEN + (255,), width=5, fill=(int(57 * 0.18 * pulse), int(255 * 0.18 * pulse),
                                                                          int(136 * 0.18 * pulse), 255))
                d.text((960 - tw / 2, 650), text, font=font, fill=WHITE + (255,))
                a = min(1.0, t / 0.3)
                im = Image.blend(Image.new("RGBA", im.size, (0, 0, 0, 255)), im, a)
                im.convert("RGB").save(os.path.join(tmp, f"f{i:04d}.png"))
            _encode(tmp, p, 3.0, ffmpeg)
            shutil.rmtree(tmp, ignore_errors=True)
        out["end"] = p
    if st.get("brand_watermark"):
        p = os.path.join(bdir, "watermark.png")
        if not (fresh and os.path.exists(p)):
            im = Image.new("RGBA", (300, 84), (0, 0, 0, 0))
            draw_logo(im, 0, 0, 300, 0.4)
            alpha = im.getchannel("A").point(lambda v: int(v * 0.75))
            im.putalpha(alpha)
            im.save(p)
        out["watermark"] = p
    open(key_file, "w").write(key)
    return out


def apply(final, ffmpeg, log):
    """Put the intro, the end card and the corner logo on a finished video (in place). Off in Settings = no change."""
    files = brand_files(ffmpeg)
    if not files:
        return False
    tmp = final + ".brand.mp4"
    inputs, parts = [], []
    k = 0
    if "intro" in files:
        inputs += ["-i", files["intro"]]
        parts.append(k); k += 1
    inputs += ["-i", final]
    main = k; k += 1
    if "end" in files:
        inputs += ["-i", files["end"]]
        parts_end = k; k += 1
    if "watermark" in files:
        inputs += ["-i", files["watermark"]]
        wm = k; k += 1
    fc = [f"[{main}:v]scale=1920:1080,setsar=1,fps=24" + (f"[mv0];[mv0][{wm}:v]overlay=W-w-36:H-h-30[mv]" if "watermark" in files else "[mv]"),
          f"[{main}:a]aresample=48000,aformat=channel_layouts=stereo[ma]"]
    seq = []
    if "intro" in files:
        fc += [f"[{parts[0]}:v]scale=1920:1080,setsar=1,fps=24[iv]", f"[{parts[0]}:a]aresample=48000,aformat=channel_layouts=stereo[ia]"]
        seq += ["[iv][ia]"]
    seq += ["[mv][ma]"]
    if "end" in files:
        fc += [f"[{parts_end}:v]scale=1920:1080,setsar=1,fps=24[ev]", f"[{parts_end}:a]aresample=48000,aformat=channel_layouts=stereo[ea]"]
        seq += ["[ev][ea]"]
    fc.append("".join(seq) + f"concat=n={len(seq)}:v=1:a=1[v][a]")
    r = subprocess.run([ffmpeg, "-y", "-loglevel", "error", *inputs, "-filter_complex", ";".join(fc), "-map", "[v]", "-map", "[a]",
                        "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
                        "-movflags", "+faststart", tmp], capture_output=True, text=True)
    if r.returncode or not os.path.exists(tmp):
        raise RuntimeError("adding the logo failed: " + r.stderr[-400:])
    os.replace(tmp, final)
    log("logo added: " + ", ".join(n for n in ("intro", "watermark", "end") if n in files))
    return True

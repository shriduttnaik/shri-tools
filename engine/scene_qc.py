"""Quality gate for H3 scene clips: right words, English only, no invented talking, not silent.

  <comfy_python> engine\\scene_qc.py <job_dir> <clip_dir> <out.json> [s001 s004 ...]

Talking scene (the motion text has a line in quotes): English Whisper must hear >= 75% of the line's words,
no more than 5 extra words, and the multilingual Whisper must not hear foreign-script words (Chinese, Hindi /
Urdu script ...: H3 is a Chinese model and sometimes adds such words). Action scene: at most 3 English words
(or a stock Whisper guess on noise) and no foreign-script words. Every clip: not silent (rms >= 0.003) and not too
quiet (rms >= 0.006).
Indian-language line (langs.json in the job folder gives the scene's Whisper language, e.g. "hi", "kn"): Whisper small (base if
small is not downloaded) transcribes in that language, and the romanized line is compared with the English Whisper's
spelling; the best of these must match the line >= 50%; no Chinese / Japanese / Korean / Thai script.
"""
import difflib, json, os, re, sys, unicodedata
os.environ.setdefault("HF_HUB_OFFLINE", "1")
import av
import numpy as np
import torch
from transformers import WhisperForConditionalGeneration, WhisperProcessor, pipeline

job, clip_dir, out_path = sys.argv[1:4]
only = set(sys.argv[4:])
if os.path.exists(os.path.join(job, "lines.json")):  # Shri Tools studio project: {scene: spoken line or ""}
    LINES = json.load(open(os.path.join(job, "lines.json"), encoding="utf-8"))
else:  # OMNITUBE job: the line is the quoted text in each scene's motion
    J = json.load(open(os.path.join(job, "omnitube.json"), encoding="utf-8"))
    LINES = {f"s{i + 1:03d}": " ".join(re.findall(r'"([^"]+)"', m)) for i, m in enumerate(J.get("motion") or [])}
STOCK = {"you", "thank you", "thanks for watching", "thank you for watching", "thank you very much",
         "thank you so much for watching", "bye", "oh", "i'll see you in the next video", "see you in the next video",
         "please subscribe", "subscribe to my channel", "bye bye", "i'll see you in the next one", "see you in the next one",
         "see you next time", "thanks for watching and see you next time"}
FOREIGN = re.compile(r"[؀-ۿऀ-ॿ　-〿぀-ヿ㐀-鿿가-힯฀-๿]")
CJK = re.compile(r"[　-〿぀-ヿ㐀-鿿가-힯฀-๿]")  # Chinese, Japanese, Korean, Thai
HAN = re.compile(r"[　-〿぀-ヿ㐀-鿿가-힯]")  # Chinese, Japanese, Korean
INDIC = re.compile(r"[؀-ۿऀ-ॿ]")  # Urdu / Hindi script
LATIN = re.compile(r"[A-Za-z]{2,}")


def foreign_words(ml):
    """Chinese/Japanese/Korean/Thai = always wrong. Hindi/Urdu script only when MIXED with English words (H3 added
    words to an English line); a line written fully in Hindi script is Whisper spelling Indian-English speech."""
    return bool(CJK.search(ml)) or (bool(INDIC.search(ml)) and bool(LATIN.search(ml)))

LANGS = {}
if os.path.exists(os.path.join(job, "langs.json")):
    LANGS = json.load(open(os.path.join(job, "langs.json"), encoding="utf-8"))
en_asr = pipeline("automatic-speech-recognition", model="openai/whisper-base.en", device=-1)
ml_proc = WhisperProcessor.from_pretrained("openai/whisper-base")
ml_model = WhisperForConditionalGeneration.from_pretrained("openai/whisper-base").eval()
in_proc = in_model = None


def indian_transcript(a, lang):
    """The clip transcribed as the scene's Indian language (Whisper small: much better than base at these)."""
    global in_proc, in_model
    if in_model is None:
        for name in ("openai/whisper-small", "openai/whisper-base"):
            try:
                in_proc = WhisperProcessor.from_pretrained(name)
                in_model = WhisperForConditionalGeneration.from_pretrained(name).eval()
                break
            except Exception:
                continue
    feats = in_proc(a, sampling_rate=16000, return_tensors="pt").input_features
    with torch.no_grad():
        ids = in_model.generate(feats, language=lang, task="transcribe", max_new_tokens=120)
    return in_proc.batch_decode(ids, skip_special_tokens=True)[0].strip()


def letters(t):
    """Letters and vowel signs only (no spaces, punctuation or digits), for comparing Indian-script text."""
    return "".join(ch for ch in t if ch.isalpha() or unicodedata.category(ch) in ("Mn", "Mc"))


# Romanizing Indian scripts: Devanagari, Bengali, Gurmukhi, Gujarati, Odia, Tamil, Telugu, Kannada and Malayalam share
# one Unicode layout (same offset = same sound inside each 128-letter block), so one table reads them all. Used to
# compare a line with what the English Whisper heard ("Thun Thun. Yallarannu, Gauraviswegi." for a Kannada line):
# Whisper small transcribes some of these languages poorly, the English one spells the sounds quite reliably.
BRAHMIC = range(0x0900, 0x0D80)
VOWELS = {0x05: "a", 0x06: "a", 0x07: "i", 0x08: "i", 0x09: "u", 0x0A: "u", 0x0B: "ri", 0x0D: "e", 0x0E: "e", 0x0F: "e",
          0x10: "ai", 0x11: "o", 0x12: "o", 0x13: "o", 0x14: "au"}
SIGNS = {0x3E: "a", 0x3F: "i", 0x40: "i", 0x41: "u", 0x42: "u", 0x43: "ri", 0x44: "ri", 0x45: "e", 0x46: "e", 0x47: "e",
         0x48: "ai", 0x49: "o", 0x4A: "o", 0x4B: "o", 0x4C: "au"}
CONS = dict(zip(range(0x15, 0x3A), "k kh g gh n ch chh j jh ny t th d dh n t th d dh n n p ph b bh m y r r l l l v sh sh s h"
                .split()))
CONS.update({0x58: "q", 0x59: "kh", 0x5A: "gh", 0x5B: "z", 0x5C: "r", 0x5D: "rh", 0x5E: "f", 0x5F: "y"})
SCHWA_DROP = {"hi", "mr", "gu", "pa", "bn"}  # these drop the final "a" of a word (Konkani is checked as Marathi)


def romanize(t, lang):
    out, pending = [], False
    for ch in t + " ":
        cp = ord(ch)
        off = (cp - 0x0900) % 0x80 if cp in BRAHMIC else None
        if off is not None and off in SIGNS:
            out.append(SIGNS[off]); pending = False
        elif off == 0x4D:  # virama: no vowel
            pending = False
        elif off is not None and off in CONS:
            if pending:
                out.append("a")
            out.append(CONS[off]); pending = True
        else:
            end_of_word = not (ch.isalpha() or unicodedata.category(ch) in ("Mn", "Mc"))
            if pending and not (lang in SCHWA_DROP and end_of_word):
                out.append("a")
            pending = False
            if off is not None and off in VOWELS:
                out.append(VOWELS[off])
            elif off in (0x01, 0x02):
                out.append("n")
            elif off == 0x03:
                out.append("h")
            elif cp < 0x80:
                out.append(ch.lower())
    return sound_letters("".join(out))


def sound_letters(t):
    """Latin letters only, aspiration and w/v and doubled letters smoothed (Whisper spells Indian sounds loosely)."""
    t = re.sub(r"[^a-z]", "", t.lower()).replace("w", "v")
    t = re.sub(r"([kgcjtdpb])h", r"\1", t)
    return re.sub(r"(.)\1+", r"\1", t)


def audio16k(path):
    c = av.open(path)
    res = av.AudioResampler(format="flt", layout="mono", rate=16000)
    a = [r.to_ndarray().reshape(-1) for f in c.decode(audio=0) for r in res.resample(f)]
    c.close()
    return np.concatenate(a).astype(np.float32) if a else np.zeros(16000, np.float32)


def words(t):
    return re.findall(r"[a-z']+", t.lower())


def only_stock(h):
    """True when the transcript is just Whisper's stock phrases repeated ("thank you very much thank you very much")."""
    rest = " ".join(h)
    for phrase in sorted(STOCK, key=len, reverse=True):
        rest = re.sub(rf"\b{re.escape(phrase)}\b", " ", rest)
    return not rest.split()


results = {}
for name in sorted(os.listdir(clip_dir)):
    m = re.match(r"(s\d{3})\.mp4$", name)
    if not m or (only and m.group(1) not in only):
        continue
    sid = m.group(1)
    a = audio16k(os.path.join(clip_dir, name))
    rms = float(np.sqrt((a ** 2).mean()))
    heard = en_asr({"raw": a, "sampling_rate": 16000})["text"].strip()
    feats = ml_proc(a, sampling_rate=16000, return_tensors="pt").input_features
    with torch.no_grad():
        ml = ml_proc.batch_decode(ml_model.generate(feats, task="transcribe", max_new_tokens=80),
                                  skip_special_tokens=True)[0].strip()
    problems = []
    if rms < 0.003:
        problems.append("no sound")
    elif rms < 0.006:  # 0.003-0.006 is technically sound but nearly inaudible in the final (clips that sounded fine: 0.007+)
        problems.append("too quiet")
    line = LINES.get(sid, "")
    lang = LANGS.get(sid, "en")
    if line and lang != "en":  # an Indian-language line: listen in that language
        said = indian_transcript(a, lang)
        # best of: the line's letters vs Whisper in that language, and the romanized line vs the English Whisper
        # spelling / the romanized automatic transcript
        sim = lambda x, y: difflib.SequenceMatcher(None, x, y).ratio() if x and y else 0.0
        rom = romanize(line, lang)
        match = max(sim(letters(line), letters(said)), sim(rom, sound_letters(heard)), sim(rom, romanize(ml, lang)),
                    sim(rom, romanize(said, lang)))
        # Whisper base's language guess writes Indian speech in any script (Hindi as Urdu, Kannada as Tamil, Konkani
        # as Thai), so only Chinese/Japanese/Korean counts, and only when the line itself was not heard well
        if HAN.search(said) or (HAN.search(ml) and match < 0.7):
            problems.append("foreign-language words")
        if match < 0.5:
            problems.append(f"line not clear ({match:.0%} of its sounds heard)")
        if len(words(heard)) > 2 * len(line.split()) + 5:
            problems.append("extra talking")
        results[sid] = {"ok": not problems, "problems": problems, "heard": said, "multilingual": ml, "lang": lang,
                        "rms": round(rms, 4), "line": line, "match": round(match, 3)}
        print(f"{sid} {'OK ' if not problems else 'BAD'} [{lang}] | heard '{said}' | rms {rms:.3f}"
              + (f" | {', '.join(problems)}" if problems else ""), flush=True)
        continue
    if foreign_words(ml):
        problems.append("foreign-language words")
    h = words(heard)
    if line:
        e = words(line)
        # word match, or letter-sequence similarity for names / Hindi words the English Whisper spells its own way
        # ("Shri bhaiya" -> "Srivaya")
        match = max(sum(1 for w in e if w in h) / max(1, len(e)),
                    difflib.SequenceMatcher(None, "".join(e), "".join(h)).ratio())
        if match < 0.75:
            problems.append(f"line not clear ({match:.0%} of its words heard)")
        if len(h) > len(e) + 5:
            problems.append("extra talking")
    elif len(h) > 3 and len(set(h)) > 2 and not only_stock(h):
        problems.append("invented talking")
    results[sid] = {"ok": not problems, "problems": problems, "heard": heard, "multilingual": ml,
                    "rms": round(rms, 4), "line": line, "match": round(match, 3) if line else None}
    print(f"{sid} {'OK ' if not problems else 'BAD'} | heard '{heard}' | ml '{ml}' | rms {rms:.3f}"
          + (f" | {', '.join(problems)}" if problems else ""), flush=True)
json.dump(results, open(out_path, "w", encoding="utf-8"), indent=1, ensure_ascii=False)

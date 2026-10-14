"""Put a song's known lyrics on its timeline.

Whisper (word timestamps) hears a sung song with misspellings, merged words and loops ("अपने अपने अपने ..."), so its
text is not good enough for the H3 prompt or the subtitles. Here the heard words are aligned in order to the lyrics we
already have (romanized letter similarity + dynamic programming, so repeated choruses and lines the singer skipped both
work). Each lyric word gets a time; each lyric line gets a span.
"""
import difflib, re

# Indian scripts share one Unicode layout (same offset = same sound in each 128-letter block): one table reads them all
BRAHMIC = range(0x0900, 0x0D80)
VOWELS = {0x05: "a", 0x06: "a", 0x07: "i", 0x08: "i", 0x09: "u", 0x0A: "u", 0x0B: "ri", 0x0D: "e", 0x0E: "e", 0x0F: "e",
          0x10: "ai", 0x11: "o", 0x12: "o", 0x13: "o", 0x14: "au"}
SIGNS = {0x3E: "a", 0x3F: "i", 0x40: "i", 0x41: "u", 0x42: "u", 0x43: "ri", 0x44: "ri", 0x45: "e", 0x46: "e", 0x47: "e",
         0x48: "ai", 0x49: "o", 0x4A: "o", 0x4B: "o", 0x4C: "au"}
CONS = dict(zip(range(0x15, 0x3A), "k kh g gh n ch chh j jh ny t th d dh n t th d dh n n p ph b bh m y r r l l l v sh sh s h"
                .split()))
CONS.update({0x58: "q", 0x59: "kh", 0x5A: "gh", 0x5B: "z", 0x5C: "r", 0x5D: "rh", 0x5E: "f", 0x5F: "y"})
WORD = re.compile(r"[\wऀ-ॣ०-ൿ‌‍'-]+")  # not the danda "।"
GAP = -0.45  # skipping a heard or a lyric word
MATCH = 0.45  # letter similarity that counts as the same word


def rom(t):
    """Latin sound letters of a word in any Indian script (or English), loosely: Whisper spells sung words its own way."""
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
            pending = False
            if off is not None and off in VOWELS:
                out.append(VOWELS[off])
            elif off in (0x01, 0x02):
                out.append("n")
            elif cp < 0x80:
                out.append(ch.lower())
    t = re.sub(r"[^a-z]", "", "".join(out)).replace("w", "v")
    t = re.sub(r"([kgcjtdpb])h", r"\1", t)
    return re.sub(r"(.)\1+", r"\1", t)


def lyric_words(lyrics):
    """(lines, [(line_no, word)]): the sung lines without [Section] tags; "(echo)" parts are sung too."""
    lines, words = [], []
    for raw in (lyrics or "").splitlines():
        raw = raw.strip()
        if not raw or re.fullmatch(r"\[.*\]", raw):
            continue
        lines.append(raw)
        words += [(len(lines) - 1, w) for w in WORD.findall(raw) if rom(w)]
    return lines, words


def align(lyrics, heard):
    """heard = [(start, end, word)] from Whisper. Returns (times, rows, words):
    times {lyric word index: (start, end)}, rows [{start, end, text}] one per sung lyric line, words [(line_no, word)].
    Lines the singer did not sing (or Whisper did not hear at all) get no time."""
    lines, L = lyric_words(lyrics)
    # after an instrumental gap Whisper starts the next word where the last one ended ("भीगी" 20-40 s): its end is right
    H = [(max(s, e - 1.5), e, w) for s, e, w in heard if rom(w)]
    n, m = len(H), len(L)
    if not n or not m:
        return {}, [], L
    hr, lr = [rom(w) for _, _, w in H], [rom(w) for _, w in L]
    sim = [[difflib.SequenceMatcher(None, hr[i], lr[j]).ratio() for j in range(m)] for i in range(n)]
    S = [[0.0] * (m + 1) for _ in range(n + 1)]
    B = [[""] * (m + 1) for _ in range(n + 1)]
    for j in range(1, m + 1):
        S[0][j], B[0][j] = S[0][j - 1] + GAP, "L"
    for i in range(1, n + 1):
        S[i][0], B[i][0] = 0.0, "H"  # heard noise before the lyrics start is free
        for j in range(1, m + 1):
            S[i][j], B[i][j] = max((S[i - 1][j - 1] + 2 * sim[i - 1][j - 1] - 1, "D"), (S[i - 1][j] + GAP, "H"),
                                   (S[i][j - 1] + GAP, "L"))
    i, j = max(range(n + 1), key=lambda k: S[k][m]), m  # heard noise after the lyrics end is free too
    heard_at = {}
    while i > 0 and j > 0:
        if B[i][j] == "D":
            if sim[i - 1][j - 1] >= MATCH:
                heard_at[j - 1] = H[i - 1][:2]
            i, j = i - 1, j - 1
        elif B[i][j] == "H":
            i -= 1
        else:
            j -= 1
    # every word of a heard line gets a time: spread between the heard words around it
    times = {}
    for ln in range(len(lines)):
        idx = [k for k in range(m) if L[k][0] == ln]
        known = [k for k in idx if k in heard_at]
        for k in idx if known else []:
            if k in heard_at:
                times[k] = heard_at[k]
                continue
            before, after = [x for x in known if x < k], [x for x in known if x > k]
            if before and after:
                a, b = before[-1], after[0]
                st = heard_at[a][1] + (k - a) / (b - a) * (heard_at[b][0] - heard_at[a][1])
            elif before:
                st = heard_at[before[-1]][1] + 0.35 * (k - before[-1] - 1)
            else:
                st = heard_at[after[0]][0] - 0.35 * (after[0] - k)
            times[k] = (st, st + 0.35)
    rows, kept = [], set()
    for ln, text in enumerate(lines):
        ks = [k for k in range(m) if L[k][0] == ln and k in times]
        if not ks:
            continue
        r = {"start": round(times[ks[0]][0], 2), "end": round(times[ks[-1]][1], 2), "text": text}
        if rows and r["start"] < rows[-1]["end"]:
            if rows[-1]["end"] - r["start"] > 0.5 * (r["end"] - r["start"]):
                continue  # a repeated chorus line matched in the wrong place: it is mostly inside the line before
            rows[-1]["end"] = r["start"]
        rows.append(r)
        kept.add(ln)
    return {k: t for k, t in times.items() if L[k][0] in kept}, rows, L


def sung_between(times, words, a, b):
    """The lyric words sung in [a, b) (by each word's middle), in order."""
    return [words[k][1] for k in sorted(times) if a - 0.15 <= sum(times[k]) / 2 < b]

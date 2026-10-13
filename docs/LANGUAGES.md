# Indian languages

Shri Tools videos can be spoken in:

| Code | Language | Script | Whisper checks it as |
|---|---|---|---|
| `en` | English | Latin | English |
| `hi` | Hindi | देवनागरी | Hindi |
| `kn` | Kannada | ಕನ್ನಡ | Kannada |
| `kok` | Konkani | देवनागरी | Marathi (Whisper has no Konkani) |
| `mr` | Marathi | देवनागरी | Marathi |
| `ta` | Tamil | தமிழ் | Tamil |
| `te` | Telugu | తెలుగు | Telugu |
| `ml` | Malayalam | മലയാളം | Malayalam |
| `bn` | Bengali | বাংলা | Bengali |
| `gu` | Gujarati | ગુજરાતી | Gujarati |
| `pa` | Punjabi | ਗੁਰਮੁਖੀ | Punjabi |
| `ur` | Urdu | اردو | Urdu |

## How to use it

- **Create** (or the **Story** tab): choose *Spoken language*. The story AI writes every line in that language's
  own script, as everyday spoken language, plus its English meaning. Pictures, actions and sounds stay in English
  (the picture and video models understand English best).
- **One scene in another language**: in the scene editor pick that scene's *Language* (for example an English
  episode where the grandmother speaks Kannada).
- **Write lines yourself** in the native script (Google Input Tools or the Windows keyboard for that language) and
  put the English meaning in *English meaning (subtitles)*.
- Via the API: `"language": "kn"` (or `"Kannada"`), see [CONNECT_API.md](CONNECT_API.md).

## What happens inside

| Step | What changes |
|---|---|
| H3 prompt | the line goes into H3's dialogue tag with the language name: `<d>[Kannada] ತುಂಟುನ್, ಎಲ್ಲರನ್ನೂ ಗೌರವಿಸಬೇಕು.</d>`, and the template asks for "clear, natural Kannada" |
| Quality check | Whisper small transcribes the clip **in that language**, and the line is also compared in romanized form with what the English Whisper heard; at least half of the line's sounds must be heard, no Chinese/Japanese/Korean speech, not much more speech than the line |
| Subtitles | the line in its script with the English meaning under it |
| Short captions, thumbnails | drawn by Microsoft Edge (headless) with the Nirmala UI font, so letters join correctly (conjuncts, vowel signs) |
| YouTube texts | titles and Short title in the language, description in the language and English, tags in both |

## How well does H3 speak these languages?

MiniMax H3 generates speech itself from the text, so the result depends on how much of each language it learned.
Our test on the laptop (the same Shri Mama close-up, one line per language):

| Language | Line | What Whisper heard in H3's clip | Verdict |
|---|---|---|---|
| Hindi | तुनतुन, हम सबका सम्मान करते हैं। | तुन्तुन, हम सब का समान करते हैं (detected Hindi, 99%) | clear, lips in sync |
| Kannada | ತುಂಟುನ್, ಎಲ್ಲರನ್ನೂ ಗೌರವಿಸಬೇಕು. | "Thun Thun. Yallarannu, Gauraviswegi." (English Whisper spelling) | understandable, accent not perfect; lips in sync |
| Konkani | तुनतुन, सगळ्यांक मान दिवंक जाय. | तुन्तुन सगल्यांक्मान दिवंक्जाई (as Marathi) | clear, lips in sync |

(Test clips: 864x480, 5.2 s, about 11 minutes each on the RTX 3050 4 GB laptop. Other languages in the list use the
same mechanism but were not tested yet.)

Whisper small cannot always write Kannada correctly (it sometimes produces a repeating loop), so the check also
**romanizes** the line (one table for all Brahmic scripts: Devanagari, Bengali, Gurmukhi, Gujarati, Odia, Tamil,
Telugu, Kannada, Malayalam) and compares it with what the English Whisper spelled: real Kannada/Hindi/Konkani lines
scored 0.81-0.96, wrong speech about 0.2, so the 0.5 threshold separates them well.

Tips: keep Indian-language lines even shorter than English ones (5-7 words), avoid English words inside the line
(mixing makes H3 and the checker unsure), and listen to the first clips of a new language before making a whole
episode.

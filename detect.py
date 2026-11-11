"""Which language a piece of text is in, from its letters and common words. No model, no network.

Writing systems settle most languages at once (Chinese, Japanese, Korean, Russian, Arabic, Hindi,
Thai, Greek, Hebrew). Languages written in Latin letters are told apart by their most common words.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Optional

NAMES = {
    "en": "English", "es": "Spanish", "fr": "French", "de": "German", "pt": "Portuguese", "it": "Italian",
    "nl": "Dutch", "id": "Indonesian", "tr": "Turkish", "zh": "Chinese", "ja": "Japanese", "ko": "Korean",
    "ru": "Russian", "uk": "Ukrainian", "ar": "Arabic", "fa": "Persian", "hi": "Hindi", "th": "Thai",
    "el": "Greek", "he": "Hebrew",
}

SCRIPTS = [
    ("ja", r"[぀-ヿ]"),            # kana before Han: Japanese mixes both
    ("ko", r"[가-힯ᄀ-ᇿ]"),
    ("zh", r"[一-鿿㐀-䶿]"),
    ("cyr", r"[Ѐ-ӿ]"),
    ("arab", r"[؀-ۿݐ-ݿ]"),
    ("hi", r"[ऀ-ॿ]"),
    ("th", r"[฀-๿]"),
    ("el", r"[Ͱ-Ͽ]"),
    ("he", r"[֐-׿]"),
    ("latin", r"[A-Za-zÀ-ɏ]"),
]

WORDS = {
    "en": "the and is are you to of in it that this for with not on be have what can do i we my your will was but".split(),
    "es": "el la los las que de y es en un una por para con no se lo como más pero su al del está muy qué".split(),
    "fr": "le la les des et est que de un une pour pas dans ce qui sur avec vous je il au du mais très ne".split(),
    "de": "der die das und ist nicht ich du sie es ein eine zu mit auf für den dem von wie auch bitte kann".split(),
    "pt": "o a os as que de e é em um uma para com não se do da por mais como você está muito".split(),
    "it": "il lo la gli le che di e è in un una per con non si del della come più ma sono questo".split(),
    "nl": "de het een en is van dat niet ik je met op voor zijn maar ook wat kan er".split(),
    "id": "yang dan di ini itu untuk dengan tidak ada saya anda dari akan bisa juga ke apa".split(),
    "tr": "ve bir bu da de için ne ile çok ama mi değil var ben sen olarak gibi".split(),
}
_WORD_SETS = {lang: set(words) for lang, words in WORDS.items()}

_CODE = re.compile(r"```.*?```|`[^`\n]*`|https?://\S+|\S+@\S+\.\S+|[\w./\\-]+\.(?:py|js|ts|md|json|yaml|yml|txt|html|css)\b", re.S)


def clean(text: str) -> str:
    """Prose only: code, links, paths and emails say nothing about the language."""
    return _CODE.sub(" ", text or "")


def detect(text: str, min_letters: int = 12) -> Optional[str]:
    """A language code, or None when there is too little text to tell."""
    text = clean(text)
    counts = Counter()
    for name, pattern in SCRIPTS:
        counts[name] = len(re.findall(pattern, text))
    total = sum(counts.values())
    if total < min_letters:
        return None
    script, n = counts.most_common(1)[0]
    if script != "latin" and n >= max(4, 0.25 * total):
        if script == "cyr":
            return "uk" if re.search(r"[іїєґ]", text, re.I) else "ru"
        if script == "arab":
            return "fa" if re.search(r"[پچژگ]", text) else "ar"
        return script
    words = re.findall(r"[a-zà-ÿğışçöü]+", text.lower())
    if len(words) < 3:
        return None
    hits = Counter({lang: sum(w in vocab for w in words) for lang, vocab in _WORD_SETS.items()})
    (best, score), = hits.most_common(1)
    if score < 2 or score < 0.12 * len(words):
        return None
    runner_up = sorted(hits.values())[-2]
    return best if score > runner_up else None


def name(code: Optional[str]) -> str:
    return NAMES.get(code or "", code or "unknown")

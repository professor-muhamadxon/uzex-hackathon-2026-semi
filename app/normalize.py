"""Text normalisation, transliteration and fuzzy matching helpers."""

from __future__ import annotations

import re
import unicodedata

CYRILLIC_TO_LATIN = {
    "а": "a", "б": "b", "в": "v", "г": "g", "ғ": "g", "д": "d", "е": "e",
    "ё": "yo", "ж": "j", "з": "z", "и": "i", "й": "y", "к": "k", "қ": "q",
    "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s",
    "т": "t", "у": "u", "ў": "o", "ф": "f", "х": "x", "ҳ": "h", "ц": "ts",
    "ч": "ch", "ш": "sh", "щ": "sh", "ъ": "", "ы": "i", "ь": "", "э": "e",
    "ю": "yu", "я": "ya",
}


# New Uzbek Latin alphabet -> legacy keys (must run before NFKD strips diacritics).
NEW_LATIN = {"ş": "sh", "ç": "ch", "ö": "o'", "ğ": "g'"}


def normalize_text(value: str) -> str:
    """Lowercase, strip diacritics and punctuation, collapse whitespace."""
    if not value:
        return ""
    text = value.lower()
    for src, dst in NEW_LATIN.items():
        text = text.replace(src, dst)
    for char in ("‘", "’", "ʻ", "ʼ", "`", "´"):
        text = text.replace(char, "'")
    # strip diacritics from Latin letters only: NFKD would turn Cyrillic ў/й/ё into у/и/е
    text = "".join(
        ch if "\u0400" <= ch <= "\u04ff" else
        "".join(c for c in unicodedata.normalize("NFKD", ch) if not unicodedata.combining(c))
        for ch in text
    )
    text = text.replace("'", "")
    text = re.sub(r"[^0-9a-zа-яёўқғҳ\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def transliterate(value: str) -> str:
    return "".join(CYRILLIC_TO_LATIN.get(ch, ch) for ch in value)


def match_key(value: str) -> str:
    """Key used for cross-script fuzzy matching (Cyrillic and Latin)."""
    text = transliterate(normalize_text(value))
    text = text.replace("'", "")
    text = re.sub(r"[^0-9a-z\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def contains_any(text: str, keywords: list[str]) -> bool:
    for keyword in keywords:
        if re.search(rf"(?<!\w){re.escape(keyword)}(?!\w)", text):
            return True
    return False

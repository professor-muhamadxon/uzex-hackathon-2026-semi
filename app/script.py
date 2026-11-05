"""Render Uzbek answers in the script of the question (legacy Latin / new Latin / Cyrillic).

Answers are produced in legacy Latin (o‘, g‘, sh, ch). Data values (company/product
names, codes, numbers) are masked before conversion and restored afterwards, so they
are always shown exactly as in the dataset.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

APOS = "‘’ʻʼ'`"

LEGACY_TO_NEW = [
    (re.compile(rf"([Oo])[{APOS}]"), lambda m: "Ö" if m.group(1) == "O" else "ö"),
    (re.compile(rf"([Gg])[{APOS}]"), lambda m: "Ğ" if m.group(1) == "G" else "ğ"),
    (re.compile(r"S[Hh]"), lambda m: "Ş"),
    (re.compile(r"sh"), lambda m: "ş"),
    (re.compile(r"C[Hh]"), lambda m: "Ç"),
    (re.compile(r"ch"), lambda m: "ç"),
    (re.compile(r"’"), lambda m: "ʼ"),
]

# multi-letter first
LAT2CYR_MULTI = [
    ("o‘", "ў"), ("g‘", "ғ"), ("sh", "ш"), ("ch", "ч"), ("yo", "ё"), ("yu", "ю"), ("ya", "я"),
    ("ye", "е"), ("ts", "ц"),
]
LAT2CYR = {
    "a": "а", "b": "б", "d": "д", "e": "е", "f": "ф", "g": "г", "h": "ҳ", "i": "и",
    "j": "ж", "k": "к", "l": "л", "m": "м", "n": "н", "o": "о", "p": "п", "q": "қ",
    "r": "р", "s": "с", "t": "т", "u": "у", "v": "в", "x": "х", "y": "й", "z": "з",
    "’": "ъ", "'": "ъ", "c": "с", "w": "в",
}

_MASK = "\x00{}\x00"


def _normalize_apostrophes(text: str) -> str:
    return re.sub(r"([OoGg])[‘ʻ`']", r"\1‘", text)


def _lat_word_to_cyr(word: str) -> str:
    out: list[str] = []
    i = 0
    lower = word.lower()
    while i < len(word):
        chunk = None
        for lat, cyr in LAT2CYR_MULTI:
            if lower.startswith(lat, i):
                chunk = (lat, cyr)
                break
        if chunk:
            lat, cyr = chunk
            src = word[i : i + len(lat)]
            i += len(lat)
        else:
            src = word[i]
            cyr = LAT2CYR.get(lower[i])
            i += 1
            if cyr is None:
                out.append(src)
                continue
            # word-initial "e" -> "э"
            if lower[i - 1] == "e" and (i - 1 == 0):
                cyr = "э"
        if src[:1].isupper():
            all_caps = len(word) > 1 and word.upper() == word
            cyr = cyr.upper() if all_caps else cyr[:1].upper() + cyr[1:]
        out.append(cyr)
    return "".join(out)


def latin_to_cyrillic(text: str) -> str:
    text = _normalize_apostrophes(text)
    return re.sub(r"[A-Za-z‘’'ʻ]+", lambda m: _lat_word_to_cyr(m.group(0)), text)


def legacy_to_new(text: str) -> str:
    for pattern, repl in LEGACY_TO_NEW:
        text = pattern.sub(repl, text)
    return text


def _collect_strings(value: Any, out: set[str]) -> None:
    if isinstance(value, str):
        if len(value.strip()) >= 2:
            out.add(value.strip())
    elif isinstance(value, dict):
        for item in value.values():
            _collect_strings(item, out)
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            _collect_strings(item, out)
    elif hasattr(value, "__dict__"):
        _collect_strings(vars(value), out)


def render(text: str, script: str, protect: Iterable[Any] = (), skip: Iterable[str] = ()) -> str:
    """Convert template text to the requested Uzbek script; data values stay intact."""
    if script not in {"lat_new", "cyr"} or not text:
        return text
    strings: set[str] = set()
    for item in protect:
        _collect_strings(item, strings)
    strings -= set(skip)
    masked: list[str] = []

    def mask(value: str) -> str:
        masked.append(value)
        return _MASK.format(len(masked) - 1)

    # longest first so that substrings do not break longer names
    for value in sorted(strings, key=len, reverse=True):
        if value in text:
            text = text.replace(value, mask(value))
    # codes / technical tokens: INN-like numbers, BK001, SQL-ish uppercase words in Cyrillic
    text = re.sub(r"\bBK\d{3}\b|\bUSD\b|\bSQL\b|R²|\bTN VED\b", lambda m: mask(m.group(0)), text)
    text = re.sub(r"[«\"“][^»\"”\x00]{1,80}[»\"”]", lambda m: mask(m.group(0)), text)

    converted = latin_to_cyrillic(text) if script == "cyr" else legacy_to_new(text)
    return re.sub(r"\x00(\d+)\x00", lambda m: masked[int(m.group(1))], converted)

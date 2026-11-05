"""Retrieval layer for entity NAMES only (products, regions, brokers, companies).

Char n-gram TF-IDF cosine over transliterated keys. It returns candidates with scores; it
never produces numbers. Callers accept a hit only if score >= MIN_SCORE and the best
entity beats the runner-up (a different entity) by MARGIN; otherwise "not found".
No embedding model is used (none installed locally); the interface allows adding one.
"""

from __future__ import annotations

import math
import re
import threading
from collections import Counter, defaultdict
from dataclasses import dataclass
from functools import lru_cache

from .normalize import match_key

MIN_SCORE = 0.62
MARGIN = 0.12
MIN_LEN = 5


@dataclass(frozen=True)
class Hit:
    kind: str      # product | region | broker | company
    entity: str    # tnved / region_uz / broker code / inn
    matched: str   # the indexed text that matched
    score: float


_SUFFIX = re.compile(r"(skoy|skaya|skuyu|skiy|skoi|skogo|skom|skie|ning|dagi|lari|ga|da|dan|ni|ov|oy|ya)$")


def _stem(key: str) -> str:
    """Strip one inflection suffix (RU adjectival / UZ case) if a >=4-char stem remains."""
    return _SUFFIX.sub("", key) if len(_SUFFIX.sub("", key)) >= 4 else key


def _grams(key: str) -> Counter:
    padded = f"^{key}$"
    out: Counter = Counter()
    for n in (2, 3):
        for i in range(len(padded) - n + 1):
            out[padded[i:i + n]] += 1
    return out


class _Index:
    def __init__(self) -> None:
        self.docs: list[tuple[str, str, str, dict[str, float], float]] = []
        self._raw: list[tuple[str, str, str, Counter]] = []
        self.df: Counter = Counter()
        self.postings: dict[str, list[int]] = defaultdict(list)
        self.idf: dict[str, float] = {}

    def add(self, kind: str, entity: str, text: str) -> None:
        key = _stem(match_key(text))
        if len(key) < 3:
            return
        g = _grams(key)
        self._raw.append((kind, entity, key, g))
        for gram in g:
            self.df[gram] += 1

    def build(self) -> None:
        n = len(self._raw) or 1
        self.idf = {g: math.log(1 + n / c) for g, c in self.df.items()}
        for i, (kind, entity, key, g) in enumerate(self._raw):
            vec = {gr: (1 + math.log(c)) * self.idf[gr] for gr, c in g.items()}
            norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
            self.docs.append((kind, entity, key, vec, norm))
            for gr in vec:
                self.postings[gr].append(i)

    def query(self, text: str, kind: str, k: int = 5) -> list[Hit]:
        key = _stem(match_key(text))
        if not key:
            return []
        g = _grams(key)
        qvec = {gr: (1 + math.log(c)) * self.idf.get(gr, 0.0) for gr, c in g.items()}
        qnorm = math.sqrt(sum(v * v for v in qvec.values())) or 1.0
        dots: dict[int, float] = defaultdict(float)
        for gr, qv in qvec.items():
            for i in self.postings.get(gr, ()):
                dots[i] += qv * self.docs[i][3][gr]
        best: dict[str, Hit] = {}
        for i, dot in dots.items():
            dkind, entity, dkey, _vec, dnorm = self.docs[i]
            if dkind != kind:
                continue
            score = dot / (qnorm * dnorm)
            # same first letter + similar length: typo, not an unrelated word
            if dkey[0] != key[0] or abs(len(dkey) - len(key)) > max(3, len(key) // 3):
                score *= 0.5
            if entity not in best or score > best[entity].score:
                best[entity] = Hit(dkind, entity, dkey, round(score, 3))
        return sorted(best.values(), key=lambda h: -h.score)[:k]


_LOCK = threading.Lock()


def _index() -> _Index:
    with _LOCK:  # lazy, built once, thread-safe
        return _build_index()


@lru_cache(maxsize=1)
def _build_index() -> _Index:
    from .catalog import PRODUCT_KEYWORDS, get_catalog

    cat = get_catalog()
    idx = _Index()
    for tnved, kws in PRODUCT_KEYWORDS.items():
        for kw in kws:
            if " " not in match_key(kw) and len(match_key(kw)) >= MIN_LEN:
                idx.add("product", tnved, kw)
    for p in cat.products:
        for word in match_key(p.name).split():
            # skip adjectives ("avtomobilniy" benzin): a car is not gasoline
            if len(word) >= MIN_LEN and not re.search(r"(iy|oy|yy|ye|ie|aya|oe|ogo|ykh|ix|ykh|ogo)$", word):
                idx.add("product", p.tnved, word)
    skip = {"viloyati", "oblast", "oblasti", "respublikasi"}
    for alias, region in cat.regions:
        for word in alias.split():
            if len(word) >= MIN_LEN and word not in skip:
                idx.add("region", region, word)
    for b in cat.brokers:
        idx.add("broker", b.code, b.name)
    from .catalog import company_core

    for c in cat.companies:
        key = match_key(c.name)
        idx.add("company", c.inn, company_core(key) or key)
    idx.build()
    return idx


def warm() -> None:
    """Build the index eagerly (e.g. at bot start). Otherwise it is built lazily on first use."""
    _index()


def retrieve(text: str, kind: str, k: int = 5) -> list[Hit]:
    """Ranked candidate entities (one per entity) for a word/phrase."""
    return _index().query(text, kind, k)


def resolve(text: str, kind: str, min_score: float = MIN_SCORE, margin: float = MARGIN) -> Hit | None:
    """Best entity if confidently above threshold and unambiguous, else None.

    Runner-ups with the very same indexed text (namesake companies) do not count as rivals.
    """
    if len(match_key(text)) < MIN_LEN:
        return None
    hits = retrieve(text, kind, 4)
    if not hits or hits[0].score < min_score:
        return None
    rivals = [h for h in hits[1:] if h.matched != hits[0].matched]
    if rivals and hits[0].score - rivals[0].score < margin:
        return None
    return hits[0]


# --- unknown-noun guard -------------------------------------------------------------
# "<noun> bo'yicha" (UZ) / "po <noun>" (RU) where the noun is no known product, region,
# company, broker or metric word -> caller answers "not found" instead of the all-deals total.
_KNOWN_PREFIXES = (
    "region", "god", "mesyats", "mesyac", "kvartal", "tovar", "brok", "kompan", "produk", "viloyat", "hudud",
    "yil", "hafta", "oy", "den", "dn", "korxon", "oblast", "kategor", "status", "tip", "vid", "stran",
    "sdel", "bitim", "dollar", "kurs", "cen", "tsen", "nark", "summ", "ob", "hajm", "son", "statist",
    "sana", "kun", "chorak", "davr", "period", "ves", "kolich", "usd", "uzs", "valyut", "eksport",
    "export", "import", "kontrakt", "dogovor", "kontr", "inn", "dannym", "dannie", "vsem", "vsemu",
    "itog", "obshch", "razrez", "razdel", "ushbu", "etomu", "etim", "reyting", "top", "prodav",
    "pokup", "sotuv", "xarid", "tarkib", "razmer", "ulush", "dol", "protsent", "foiz", "otrasl", "sektor",
    "birja", "tomon", "uchastn", "qatnash", "data", "vremen", "podrobn", "batafsil", "vse", "barcha",
    "hamma", "oxirgi", "posled", "chastich", "polnost", "otmen", "annul", "ispoln", "vypoln", "qisman",
    "bekor", "toliq", "tugal", "oplach", "neopl", "tolan", "kontrakt", "zayav", "lot", "ostat", "qoldiq",
)
_KNOWN_PREFIXES = _KNOWN_PREFIXES + (
    "aylanma", "aylanm", "oborot", "nazvan", "naimenov", "ubiv", "ubyv", "vozrast", "kajd", "kajdom", "kajdyy", "nomi", "nomin", "kazhd", "har", "tebran", "davri", "ortach", "umumiy", "jami",
    "birlik", "yillik", "oylik", "eng", "yuqor", "past", "minim", "maksim", "sredn", "bitta", "keyingi",
    "yarim", "yarm", "prognoz", "bashorat", "dinamik", "ozgar", "o'zgar", "tahlil", "analiz", "izmen",
    "kolebani", "qancha", "nech", "kak", "kakoy", "kakaya", "chto", "qaysi", "barcha", "butun", "davr",
)
_PO_RE = re.compile(r"(?<!\w)po\s+(\w+)")
# "Oltin narxining ...", "Ko'mirning ... tebranish", "цена золота", "динамика угля": the subject of a
# price / fluctuation / forecast question must exist in the registry, otherwise the answer is "not found".
_SUBJECT_RES = (
    re.compile(r"(\w+)\s+(?:narx\w*|nark\w*|tebran\w*|dinamik\w*|prognoz\w*|bashorat\w*)"),
    re.compile(r"(?<!\w)(?:ts?en[ayouei]\w*|izmeneni\w*)\s+(\w+)"),
    re.compile(r"(?<!\w)dinamik\w*\s+(?:ts?en[ayouei]\w*\s+)?(\w+)"),
    re.compile(r"^(\w+?)ning\b"),
)
_SUFFIX_RE = re.compile(r"(ning|ni|ga|da|dan|ning|ini)$")
_BOYICHA_RE = re.compile(r"(\w+)\s+boyicha")


def unknown_noun(text: str, found_any: bool) -> str:
    """text = match_key(question). Returns the unresolved noun or ''."""
    if found_any:
        return ""
    cands = [m.group(1) for m in _PO_RE.finditer(text)] + [m.group(1) for m in _BOYICHA_RE.finditer(text)]
    for tok in cands:
        if len(tok) < 5 or tok.isdigit() or tok.startswith(_KNOWN_PREFIXES):
            continue
        if resolve(tok, "product") or resolve(tok, "region"):
            continue
        return tok
    for pattern in _SUBJECT_RES:
        for match in pattern.finditer(text):
            tok = match.group(1)
            stem = _SUFFIX_RE.sub("", tok)
            if len(stem) < 4 or stem.isdigit() or stem.startswith(_KNOWN_PREFIXES) or tok.startswith(_KNOWN_PREFIXES):
                continue
            if resolve(tok, "product") or resolve(stem, "product") or resolve(tok, "region") or resolve(stem, "region"):
                continue
            return stem
    return ""

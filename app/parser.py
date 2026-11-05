"""Rule-based question parser: language, intent, filters and entities."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from .catalog import (
    Broker,
    Company,
    ProductFilter,
    find_broker,
    find_company,
    company_namesakes,
    find_product_filters,
    find_regions,
)
from .config import RAG_ENABLED
from .extra import detect_extra_intent
from .normalize import match_key, normalize_text

DATA_START = date(2022, 1, 3)
DATA_END = date(2026, 10, 30)

UNSUPPORTED_TERMS = [
    "marja", "margin", "прибыл", "profit", "rentabel", "рентабел",
    "foyda", "фойда", "dividend", "дивиденд", "налог", "солиқ", "tax",
    "bonus", "бонус", "logistika narxi", "стоимость логистики",
    # off-topic: nothing in the registry (must never fall back to a "total")
    "ob-havo", "ob havo", "obhavo", "об-ҳаво", "об ҳаво", "обҳаво", "об-хаво", "погод", "weather",
    "anekdot", "анекдот",
]



MONTHS: dict[int, list[str]] = {
    1: ["yanvar", "январ", "январь", "january", "jan"],
    2: ["fevral", "феврал", "февраль", "february", "feb"],
    3: ["mart", "март", "march", "mar"],
    4: ["aprel", "апрел", "апрель", "april", "apr"],
    5: ["may", "май", "may"],
    6: ["iyun", "июн", "июнь", "june", "jun"],
    7: ["iyul", "июл", "июль", "july", "jul"],
    8: ["avgust", "август", "august", "aug"],
    9: ["sentabr", "сентябр", "сентябрь", "september", "sep", "sentabr"],
    10: ["oktabr", "октябр", "октябрь", "october", "oct"],
    11: ["noyabr", "ноябр", "ноябрь", "november", "nov"],
    12: ["dekabr", "декабр", "декабрь", "december", "dec"],
}

ANNUL = "Аннулирован(Не оплачен)"
DONE = ["Исполнен", "Исполнен(Частично)"]

# keywords -> (label, statuses, needs_status_word)
# needs_status_word: ambiguous everyday words ("yangi", "tuzilgan") only count
# as a status filter when the question explicitly talks about status.
STATUS_KEYWORDS: list[tuple[list[str], str, list[str], bool]] = [
    (["аннулирован", "annul", "не оплачен", "bekor qilingan", "bekor", "отменен", "отменён"], ANNUL, [ANNUL], False),
    (["исполнен частично", "частично", "qisman", "partial"], "Исполнен(Частично)", ["Исполнен(Частично)"], False),
    (["не подписан", "imzolanmagan", "unsigned"], "Не подписан", ["Не подписан"], False),
    (["исполнен", "ijro etilgan", "bajarilgan", "yetkazilgan", "yetkazib berilgan", "completed"],
     "Исполнен, Исполнен(Частично)", DONE, False),
    (["оплачен", "to'langan", "tolangan", "оплата qilingan", "paid"],
     "Оплачен, Исполнен, Исполнен(Частично)", ["Оплачен", *DONE], False),
    (["ждет оплату", "ждёт оплату", "ожидает оплат", "kutmoqda", "tolov kutilmoqda", "waiting payment"],
     "Ждёт оплату", ["Ждёт оплату"], False),
    (["заключен", "заключён", "tuzilgan", "signed"], "Заключен", ["Заключен"], True),
    (["новый", "yangi", "new"], "Новый", ["Новый"], True),
]
STATUS_WORDS = ["holat", "holati", "статус", "состояни", "status"]


@dataclass
class ParsedQuery:
    question: str
    lang: str = "uz"
    intent: str = "unknown"
    metric: str = "amount"  # amount | count | volume | avg_price | usd
    year_from: int | None = None
    year_to: int | None = None
    month: int | None = None
    date_from: date | None = None
    date_to: date | None = None
    status: str | None = None
    statuses: list[str] = field(default_factory=list)
    contract_type: str | None = None
    contract_form: str | None = None
    trade_type: str | None = None
    company: Company | None = None
    company_score: int = 0
    company_role: str = "both"  # seller | buyer | both
    product: ProductFilter = field(default_factory=ProductFilter)
    regions: list[str] = field(default_factory=list)
    region_label: str = ""
    broker: Broker | None = None
    broker_score: int = 0
    contract_id: int | None = None
    deal_id: int | None = None
    top_n: int = 5
    top_n_explicit: bool = False  # "first 5 ... grouped by ..." request handled as top-N
    group: str | None = None  # company | product | region | broker
    wants_usd: bool = False
    not_found_reason: str | None = None  # period | entity | field
    not_found_detail: str = ""
    namesakes: list = field(default_factory=list)
    extra: dict = field(default_factory=dict)
    order_asc: bool = False
    script: str = "lat_old"  # lat_old | lat_new | cyr (for Uzbek answers)
    period_label: str = ""

    def has_filters(self) -> bool:
        return any(
            [
                self.year_from,
                self.month,
                self.date_from,
                self.status,
                self.contract_type,
                self.contract_form,
                self.trade_type,
                self.company,
                self.product.tnveds,
                self.product.categories,
                self.regions,
                self.broker,
                self.contract_id,
            ]
        )


def detect_language(question: str) -> str:
    lower = question.lower()
    if re.search(r"[ўқғҳ]", lower):
        return "uz"
    if re.search(r"[а-яё]", lower):
        uzbek_cyrillic = [
            "қанча", "нечта", "битим", "сўм", "қайси", "вилояти", "ҳажм",
            "бўйича", "учун", "ҳақида", "жами", "сўмда", "долларда", "бўлган",
            "қачон", "қаерда", "нега", "нима",
        ]
        if any(word in lower for word in uzbek_cyrillic):
            return "uz"
        return "ru"
    if re.search(r"[oʻ‘’']", lower) or re.search(
        r"\b(nechta|qancha|yilda|yil|sotilgan|sotgan|kompaniya|tovar|viloyati|bo‘yicha|buyicha)\b",
        lower,
    ):
        return "uz"
    return "uz" if not re.search(r"[а-яё]", lower) else "ru"


def detect_script(question: str, lang: str) -> str:
    if lang != "uz":
        return "cyr"
    if re.search(r"[а-яёўқғҳ]", question.lower()):
        return "cyr"
    if re.search(r"[öğşçÖĞŞÇ]", question):
        return "lat_new"
    return "lat_old"


def _find_years(text: str) -> list[int]:
    years = [int(year) for year in re.findall(r"(?<!\d)(\d{4})(?!\d)", text)]
    return [year for year in years if 1900 <= year <= 2100]


def _find_dates(text: str) -> list[date]:
    dates: list[date] = []
    for match in re.findall(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b", text):
        try:
            dates.append(date(int(match[2]), int(match[1]), int(match[0])))
        except ValueError:
            continue
    for y, m, d in re.findall(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)", text):  # ISO 2024-05-15
        try:
            dates.append(date(int(y), int(m), int(d)))
        except ValueError:
            continue
    # "15 мая 2024", "2025-yil 3-martda", "2024 йил 10 июнда": day + month name + a year somewhere
    years = [int(y) for y in re.findall(r"(?<!\d)(\d{4})(?!\d)", text) if 1900 <= int(y) <= 2100]
    if years and not dates:
        normalized = match_key(text)
        for month, names in MONTHS.items():
            for key in {match_key(name) for name in names}:
                for day in re.findall(rf"(?<!\d)(\d{{1,2}})(?!\d)\s*(?:ta\s+)?{re.escape(key)}", normalized):
                    try:
                        dates.append(date(years[0], month, int(day)))
                    except ValueError:
                        continue
    return sorted(set(dates))


def _month_end(year: int, month: int) -> date:
    if month == 12:
        return date(year, 12, 31)
    return date(year, month + 1, 1) - timedelta(days=1)


def _clip(start: date, end: date) -> tuple[date, date]:
    return max(start, DATA_START), min(end, DATA_END)


def _shift_months(d: date, months: int) -> date:
    total = d.year * 12 + (d.month - 1) - months
    year, month = divmod(total, 12)
    return date(year, month + 1, min(d.day, _month_end(year, month + 1).day))


ROMAN = {"i": 1, "ii": 2, "iii": 3, "iv": 4}
ORDINAL_Q = {
    "birinchi": 1, "ikkinchi": 2, "uchinchi": 3, "tortinchi": 4,
    "perv": 1, "vtor": 2, "tret": 3, "chetvert": 4,
}


def _find_relative_period(question: str, years: list[int]) -> tuple[date, date] | None:
    """Relative periods (UZ/RU), anchored to the last data date 30.10.2026."""
    t = match_key(question)
    anchor = DATA_END
    year = max(years) if years else anchor.year

    def has(pattern: str) -> bool:
        return re.search(pattern, t) is not None

    # today / yesterday
    if has(r"\b(bugun|segodnya)\b"):
        return anchor, anchor
    if has(r"\b(kecha|vchera)\b"):
        d = anchor - timedelta(days=1)
        return d, d

    # last N days / weeks / months / years
    m = re.search(
        r"\b(?:oxirgi|songgi|keyingi|poslednie|poslednih|poslednikh|za poslednie|za)\s+(\d{1,3})\s*(?:ta\s+)?"
        r"(kun|hafta|oy|yil|dn\w*|den\w*|nedel\w*|mesyats\w*|let|god\w*)",
        t,
    )
    if m:
        n = int(m.group(1))
        unit = m.group(2)
        if unit.startswith(("kun", "dn", "den")):
            start = anchor - timedelta(days=n - 1)
        elif unit.startswith(("hafta", "nedel")):
            start = anchor - timedelta(days=7 * n - 1)
        elif unit.startswith(("oy", "mesyats")):
            start = _shift_months(anchor, n) + timedelta(days=1)
        else:
            start = date(anchor.year - n, anchor.month, anchor.day) + timedelta(days=1)
        return _clip(start, anchor)

    # quarters: "3-chorak", "III kvartal", "birinchi chorak", "pervyy kvartal"
    m = re.search(r"\b(\d|iv|i{1,3})\s*(?:-?\s*(?:chi|nchi|y|yy|iy|go|j))?\s*(?:chorak|chorag|kvartal)", t)
    q_num = None
    if m:
        token = m.group(1)
        q_num = int(token) if token.isdigit() else ROMAN.get(token)
    else:
        m = re.search(r"\b(birinchi|ikkinchi|uchinchi|tortinchi|perv|vtor|tret|chetvert)\w*\s+(?:chorak|chorag|kvartal)", t)
        if m:
            q_num = ORDINAL_Q[m.group(1)]
    if q_num and 1 <= q_num <= 4:
        start = date(year, 3 * q_num - 2, 1)
        return _clip(start, _month_end(year, 3 * q_num))

    cur_q = (anchor.month - 1) // 3 + 1
    if has(r"\b(otgan|utgan|oldingi|proshl\w*|predyduship?\w*)\s+(chorak|chorag|kvartal)"):
        qy, qn = (anchor.year, cur_q - 1) if cur_q > 1 else (anchor.year - 1, 4)
        return _clip(date(qy, 3 * qn - 2, 1), _month_end(qy, 3 * qn))
    if has(r"\b(bu|joriy|etom|tekushch\w*)\s+(chorak|chorag|kvartal\w*)"):
        return _clip(date(anchor.year, 3 * cur_q - 2, 1), anchor)

    # "yilning yarmi / yarmidagi" (no ordinal) -> first half, "вторая половина" -> second half
    if has(r"yilning\s+yarm\w*|polovin\w*\s+god\w*|pervoy\s+polovin\w*"):
        return _clip(date(year, 1, 1), date(year, 6, 30))
    if has(r"(ikkinchi|vtoroy)\s+(yarim|polovin)\w*"):
        return _clip(date(year, 7, 1), date(year, 12, 31))

    # half-year
    m = re.search(r"\b(1|2|birinchi|ikkinchi|perv\w*|vtor\w*)\s*-?\s*(?:yarim\s*yil|polugod\w*|yarmi)", t)
    if m:
        h = 1 if m.group(1) in {"1", "birinchi"} or m.group(1).startswith("perv") else 2
        start = date(year, 1 if h == 1 else 7, 1)
        end = date(year, 6, 30) if h == 1 else date(year, 12, 31)
        return _clip(start, end)

    if has(r"\b(otgan|utgan|oldingi|proshl\w*)\s+(yil\w*|god\w*)"):
        return _clip(date(anchor.year - 1, 1, 1), date(anchor.year - 1, 12, 31))
    if has(r"\b(bu|joriy|shu|etom|tekushch\w*|nyneshn\w*)\s+(yil\w*|god\w*)"):
        return _clip(date(anchor.year, 1, 1), anchor)
    if has(r"\b(otgan|utgan|oldingi|proshl\w*)\s+(oy\w*|mesyats\w*)"):
        prev = _shift_months(anchor.replace(day=1), 1)
        return _clip(prev, _month_end(prev.year, prev.month))
    if has(r"\b(bu|joriy|shu|etom|tekushch\w*)\s+(oy\w*|mesyats\w*)"):
        return _clip(anchor.replace(day=1), anchor)
    if has(r"\b(otgan|utgan|oldingi|proshl\w*)\s+(hafta\w*|nedel\w*)"):
        this_monday = anchor - timedelta(days=anchor.weekday())
        return this_monday - timedelta(days=7), this_monday - timedelta(days=1)
    if has(r"\b(bu|joriy|shu|etoy|tekushch\w*)\s+(hafta\w*|nedel\w*)"):
        return anchor - timedelta(days=anchor.weekday()), anchor
    return None


def _find_months(text: str) -> list[int]:
    """All month mentions in order of appearance (for ranges like 'yanvar–mart')."""
    normalized = match_key(text)
    found: list[tuple[int, int]] = []
    for month, names in MONTHS.items():
        best = None
        for name in names:
            key = match_key(name)
            if len(key) <= 3:
                m = re.search(rf"(?<!\w){re.escape(key)}(?!\w)", normalized)
            else:
                m = re.search(rf"(?<!\w){re.escape(key)}", normalized)
            if m and (best is None or m.start() < best):
                best = m.start()
        if best is not None:
            found.append((best, month))
    return [month for _, month in sorted(found)]


def _find_month(text: str) -> int | None:
    normalized = match_key(text)
    for month, names in MONTHS.items():
        for name in names:
            key = match_key(name)
            if len(key) <= 3:
                if re.search(rf"(?<!\w){re.escape(key)}(?!\w)", normalized):
                    return month
            elif key in normalized:
                return month
    return None


def _has_any(text: str, keywords: list[str]) -> bool:
    """Match keywords in raw (Cyrillic) and transliterated forms."""
    normalized = normalize_text(text)
    translit = match_key(text)
    for keyword in keywords:
        raw = normalize_text(keyword)
        if raw:
            if len(raw) <= 3:
                if re.search(rf"(?<!\w){re.escape(raw)}(?!\w)", normalized):
                    return True
            elif raw in normalized:
                return True
        key = match_key(keyword)
        if not key:
            continue
        if len(key) <= 3:
            if re.search(rf"(?<!\w){re.escape(key)}(?!\w)", translit):
                return True
        elif key in translit:
            return True
    return False


def _find_status(text: str) -> tuple[str | None, list[str]]:
    explicit = _has_any(text, STATUS_WORDS)
    for keywords, label, statuses, needs_word in STATUS_KEYWORDS:
        if needs_word and not explicit:
            continue
        if _has_any(text, keywords):
            return label, statuses
    return None, []


def _find_contract_type(text: str) -> str | None:
    if _has_any(text, ["eksport", "экспорт", "export", "tashqi bozor"]):
        return "Экспортный"
    if _has_any(text, ["ichki", "ички", "внутренний", "internal", "domestic"]):
        return "Внутренний"
    return None


def _find_contract_form(text: str) -> str | None:
    if _has_any(text, ["spot", "спот"]):
        return "Спот"
    if _has_any(text, ["forvard", "форвард", "forward"]):
        return "Форвард"
    if _has_any(text, ["fyuchers", "фьючерс", "futures"]):
        return "Фьючерс"
    return None


def _find_trade_type(text: str) -> str | None:
    if _has_any(text, ["teskari", "обратн", "reverse"]):
        return "Обратный аукцион"
    if _has_any(text, ["ikki tomonlama", "двусторонн", "two-sided"]):
        return "Двусторонний аукцион"
    if _has_any(text, ["angliya", "английск", "english", "oshkori"]):
        return "Английский аукцион"
    return None


def _find_metric(text: str, question: str, product: ProductFilter) -> str:
    money_words = ["sum", "сум", "summa", "сумма", "pul", "деньги", "qiymat", "стоимость", "so'm", "сом"]
    count_words = [
        "nechta",
        "нечта",
        "soni",
        "сони",
        "количество",
        "count",
        "число",
        "bitimlar soni",
        "сделок",
        "how many",
        "number of deals",
    ]
    volume_words = ["tonna", "тонн", "kg", "кг", "kilogram", "килограмм", "dona", "дона", "штук", "litr", "литр", "metr", "метр", "hajm", "xajm", "хажм", "объем", "miqdor"]
    price_words = ["narx", "нарх", "цена", "price", "средняя цена"]

    if _has_any(text, ["dollar", "доллар", "usd"]):
        return "usd"
    explicit_count = ["nechta", "нечта", "soni", "сони", "количество", "число", "count", "how many", "сколько сделок", "qancha bitim"]
    if _has_any(text, explicit_count):
        return "count"
    # "по сумме сделок" / "bitimlar summasi" -> money, even though "сделок" is present
    if _has_any(text, ["сумм", "summa", "summasi", "qiymat", "стоимост", "оборот", "aylanma"]):
        return "amount"
    if _has_any(text, count_words):
        return "count"
    if _has_any(text, ["qancha", "nechta", "сколько", "канча"]) and _has_any(
        text, ["bitim", "сделка", "сделок", "сделки", "deal"]
    ):
        return "count"
    # "qaysi regionda eng ko'p bitim" / "самый ... по сделкам" -> count, not amount
    if _has_any(text, ["eng kop", "eng kam", "eng oz", "самый", "самых", "qaysi", "больше всего", "меньше всего", "наибольш", "наименьш"]) and _has_any(
        text, ["bitim", "сделка", "сделок", "deal"]
    ) and not _has_any(text, money_words + price_words + volume_words):
        return "count"
    if _has_any(text, price_words):
        return "avg_price"
    if _has_any(text, money_words):
        return "amount"
    if _has_any(text, volume_words):
        return "volume"
    if product.tnveds or product.categories:
        if _has_any(text, ["qancha", "канча", "сколько", "how much", "jami", "total"]):
            return "volume"
    return "amount"


def _find_role(text: str) -> str:
    buyer_words = ["sotib olgan", "sotib oldi", "xarid", "xaridor", "покупатель", "купил", "buyer", "bought"]
    seller_words = ["sotgan", "sotdi", "sotilgan", "sotuvchi", "продал", "продавец", "поставщик", "seller", "sold"]
    if _has_any(text, buyer_words):
        return "buyer"
    if _has_any(text, seller_words):
        return "seller"
    return "both"


def _find_group(text: str) -> str:
    if _has_any(text, ["region", "вилоят", "viloyat", "област", "регион"]):
        return "region"
    if _has_any(text, ["broker", "брокер"]):
        return "broker"
    if _has_any(text, ["tovar", "товар", "mahsulot", "продукт", "product"]):
        return "product"
    return "company"  # tashkilot / организация / kompaniya / default


def _is_top(text: str) -> bool:
    markers = [
        "top", "eng kop", "eng katta", "eng yuqori", "самый", "самых", "самая", "самое",
        "рейтинг", "ranking", "лидер", "лидир", "peshqadam", "yetakchi",
        "крупнейш", "активн", "faol", "eng yirik", "eng katta", "eng arzon", "eng qimmat",
        "eng kam", "eng oz", "энг кам", "меньше всего", "наименьш", "наименее", "реже всего", "fewest", "least",
        "дешевле всего", "дороже всего", "самый дешев", "самая дешев", "самый дорог", "самая дорог", "qaysi", "больше всего", "наибольш",
    ]
    return _has_any(text, markers)


ASC_WORDS = ["eng kam", "eng oz", "энг кам", "энг оз", "меньше всего", "наименьш", "наименее", "реже всего",
             "fewest", "least",
             "osish tartibida", "o‘sish tartibida", "o'sish tartibida", "ўсиш тартибида",
             "по возрастанию", "в порядке возрастания", "ascending"]
ENTITY_WORDS = (
    r"(?:kompaniya|компания|компаний|компании|tashkilot|ташкилот|организаци|предприяти|korxona|корхона|"
    r"tovar|товар|mahsulot|маҳсулот|продукт|наименован|region|viloyat|вилоят|broker|брокер|"
    r"xaridor|харидор|sotuvchi|сотувчи|покупател|продав)"
)
# "Birinchi 5 ta", "dastlabki 5", "первые 5", "top 5", "eng ... 5"
TOP_PREFIX = r"(?:top|топ|eng|энг|самых|первых|первые|рейтинг|birinchi|биринчи|dastlabki|дастлабки|ilk|илк)"


def _explicit_top_n(text: str) -> int | None:
    match = re.search(TOP_PREFIX + r"\s*[-–]?\s*(\d{1,3})", text, re.IGNORECASE)
    if match:
        return max(1, min(50, int(match.group(1))))
    match = re.search(r"(\d{1,3})\s*(?:ta|та)?\s*" + ENTITY_WORDS, text, re.IGNORECASE)
    if match:
        return max(1, min(50, int(match.group(1))))
    return None


def _find_top_n(text: str) -> int:
    return _explicit_top_n(text) or 5


GROUPING_WORDS = [
    "guruhla", "гурухла", "группир", "сгруппир", "kesimida", "кесимида", "в разрезе",
    "har bir", "ҳар бир", "для каждого", "по каждому", "каждого", "каждый",
]
SORT_WORDS = [
    "saralang", "saralab", "tartibida", "саралан", "тартибида", "отсортир", "сортир", "по убыванию", "по возрастанию",
]


def _explicit_group(text: str) -> str | None:
    """Group noun named in the question (None when the question names none)."""
    if _has_any(text, ["region", "вилоят", "viloyat", "област", "регион"]):
        return "region"
    if _has_any(text, ["broker", "брокер"]):
        return "broker"
    if _has_any(text, ["tovar", "товар", "mahsulot", "маҳсулот", "продукт", "наименован", "product"]):
        return "product"
    if _has_any(text, ["kompaniya", "компани", "tashkilot", "ташкилот", "организац", "korxona", "корхона",
                       "xaridor", "харидор", "sotuvchi", "сотувчи", "покупател", "продав"]):
        return "company"
    return None


def _find_ids(text: str) -> tuple[int | None, int | None]:
    match = re.search(r"(?<!\d)(\d{6})(?!\d)", text)
    if not match:
        return None, None
    number = int(match.group(1))
    if number < 100001 or number > 604956:
        return None, None
    # the keyword closest to the number decides ("Kontrakt 101314 bo'yicha nechta bitim")
    contract_re = r"(kontrakt|контракт|shartnoma|шартнома|договор|contract)"
    deal_re = r"(bitim|битим|сделк|сделка|deal|transaction)"
    before, after = text[: match.start()].lower(), text[match.end():].lower()

    def distance(pattern: str) -> int:
        d = 10**6
        hits = list(re.finditer(pattern, before))
        if hits:
            d = min(d, len(before) - hits[-1].end())
        hit = re.search(pattern, after)
        if hit:
            d = min(d, hit.start())
        return d

    dc, dd = distance(contract_re), distance(deal_re)
    if dc < dd:
        return (number, None) if number <= 106616 else (None, number)
    if dd < dc:
        return None, number
    if number <= 104932:
        return number, None
    return None, number


def _entity_name(question: str) -> str:
    quoted = re.findall(r"[«\"“]([^»\"”]{3,})[»\"”]", question)
    if quoted:
        return quoted[0].strip()
    match = re.search(
        r"(?:компания|компании|company|фирма|korxona|kompaniya)\s+"
        r"([A-ZА-ЯЎҚҒҲ0-9][\w‘'’-]*(?:\s+[A-ZА-ЯЎҚҒҲ0-9][\w‘'’-]*){0,3})",
        question,
    )
    if match:
        return match.group(1).strip()
    match = re.search(
        r"([A-ZА-ЯЎҚҒҲ][\w‘'’-]*(?:\s+[A-ZА-ЯЎҚҒҲ0-9][\w‘'’-]*){0,3}\s+(?:MCHJ|МЧЖ|AJ|АЖ|OK|ОК|XK|ХК|ООО|АО))",
        question,
    )
    return match.group(1).strip() if match else ""


def _entity_missing(question: str, company) -> bool:
    if company is not None:
        return False
    lower = question.lower()
    if re.search(r"(нет такой|не существует|bunday\s+kompaniya\s+yo|unday\s+kompaniya\s+yo)", lower):
        return True

    quoted = re.findall(r"[«\"“]([^»\"”]{3,})[»\"”]", question)
    if quoted and re.search(
        r"(компани|company|фирма|корхона|kompaniya|korxona|mchj|мчж|ооо|ao\b|аж|aj\b|xk\b|хк)", lower
    ):
        return True

    generic = {
        "продала", "продал", "купила", "купил", "сколько", "какая", "какие",
        "это", "по", "на", "в", "за", "и", "qaysi", "nechta", "qancha",
        "sotgan", "sotilgan", "haqida", "boyicha",
    }
    match = re.search(
        r"(?i:компания|компании|company|фирма|korxona|kompaniya)\s+"
        r"([A-ZА-ЯЎҚҒҲ0-9][\w‘'’-]*(?:\s+[A-ZА-ЯЎҚҒҲ0-9][\w‘'’-]*)*)",
        question,
    )
    if match and match.group(1).lower().split()[0] not in generic:
        return True

    match = re.search(
        r"([A-ZА-ЯЎҚҒҲ][\w‘'’-]*(?:\s+[A-ZА-ЯЎҚҒҲ0-9][\w‘'’-]*){0,3})\s+"
        r"(MCHJ|МЧЖ|AJ|АЖ|OK|ОК|XK|ХК)",
        question,
    )
    if match and match.group(1).lower().split()[0] not in generic:
        return True

    return False


def parse_question(question: str) -> ParsedQuery:
    text = normalize_text(question)
    parsed = ParsedQuery(question=question, lang=detect_language(question), intent="total")
    parsed.script = detect_script(question, parsed.lang)

    years = _find_years(question)
    if years:
        parsed.year_from, parsed.year_to = min(years), max(years)

    dates = _find_dates(question)
    if dates:
        parsed.date_from, parsed.date_to = min(dates), max(dates)
        parsed.year_from = parsed.year_to = None

    parsed.month = _find_month(text)
    relative = None if dates else _find_relative_period(question, years)
    months = _find_months(text) if not dates and relative is None else []
    if relative:
        parsed.date_from, parsed.date_to = relative
        parsed.year_from = parsed.year_to = None
        parsed.month = None
        dates = [relative[0], relative[1]]
    elif len(months) >= 2 and parsed.year_from == parsed.year_to:
        # month range: "yanvar–mart 2025", "с января по март"
        year = parsed.year_from or DATA_END.year
        m1, m2 = months[0], months[-1]
        if m1 > m2:
            m1, m2 = m2, m1
        parsed.date_from = date(year, m1, 1)
        parsed.date_to = _month_end(year, m2)
        parsed.year_from = parsed.year_to = None
        parsed.month = None
        dates = [parsed.date_from, min(parsed.date_to, DATA_END) if parsed.date_from <= DATA_END else parsed.date_to]
        parsed.date_to = dates[1]
    elif parsed.month and parsed.year_from is None and parsed.date_from is None:
        # Month without a year -> its latest occurrence up to 30.10.2026.
        year = DATA_END.year if parsed.month <= DATA_END.month else DATA_END.year - 1
        parsed.year_from = parsed.year_to = year

    # --- "not found" traps: period / unsupported field / unknown entity ---
    if dates:
        if min(dates) < DATA_START or max(dates) > DATA_END:
            parsed.not_found_reason = "period"
    elif parsed.year_from is not None:
        if parsed.year_from < DATA_START.year or parsed.year_from > DATA_END.year:
            parsed.not_found_reason = "period"
        elif parsed.year_from == DATA_END.year and parsed.month and parsed.month > DATA_END.month:
            parsed.not_found_reason = "period"
        elif parsed.year_from == DATA_START.year and parsed.month and parsed.month < DATA_START.month:
            parsed.not_found_reason = "period"

    if _has_any(text, UNSUPPORTED_TERMS):
        parsed.not_found_reason = parsed.not_found_reason or "field"
        hits = [term for term in UNSUPPORTED_TERMS if _has_any(text, [term])]
        # variants of one word (ob-havo / ob havo / об-ҳаво) would be listed together: keep one per script
        shown: list[str] = []
        for term in hits:
            if not any(term in other or other in term for other in shown):
                shown.append(term)
        parsed.not_found_detail = ", ".join(shown[:1])

    parsed.status, parsed.statuses = _find_status(text)
    parsed.contract_type = _find_contract_type(text)
    parsed.contract_form = _find_contract_form(text)
    parsed.trade_type = _find_trade_type(text)
    parsed.wants_usd = any(word in match_key(text) for word in ["dollar", "доллар", "usd", "$"])

    parsed.contract_id, parsed.deal_id = _find_ids(question)
    if parsed.contract_id or parsed.deal_id:
        # A concrete record is always answerable even if the question mentions a year.
        if parsed.not_found_reason == "period":
            parsed.not_found_reason = None
    parsed.company, parsed.company_score = find_company(question)
    parsed.company_role = _find_role(text)
    parsed.product = find_product_filters(question)
    if parsed.product.ambiguous:
        parsed.not_found_reason = parsed.not_found_reason or "product"
        parsed.not_found_detail = parsed.not_found_detail or parsed.product.ambiguous
    parsed.regions, parsed.region_label = find_regions(question)
    parsed.broker, parsed.broker_score = find_broker(question)
    if RAG_ENABLED and not parsed.not_found_reason:
        from .rag import unknown_noun
        noun = unknown_noun(match_key(question), bool(
            parsed.product.tnveds or parsed.product.categories or parsed.company or parsed.regions or parsed.broker))
        if noun:
            parsed.not_found_reason, parsed.not_found_detail = "product_unknown", noun

    if parsed.company_score == -1:
        inn = re.search(r"(?<!\d)(\d{9})(?!\d)", question)
        parsed.not_found_reason = parsed.not_found_reason or "entity"
        parsed.not_found_detail = parsed.not_found_detail or (f"INN {inn.group(1)}" if inn else "")
    elif _entity_missing(question, parsed.company):
        parsed.not_found_reason = parsed.not_found_reason or "entity"
        parsed.not_found_detail = parsed.not_found_detail or _entity_name(question)
    if parsed.company is not None:
        parsed.namesakes = company_namesakes(parsed.company)

    parsed.metric = _find_metric(text, question, parsed.product)
    if _has_any(text, ["arzon", "арзон", "дешев", "дешёв", "deshev", "eng past narx", "самая низкая цена", "минимальн цен"]):
        parsed.metric, parsed.order_asc = "avg_price", True
    elif _has_any(text, ["qimmat", "қиммат", "дорог", "самая высокая цена", "eng yuqori narx"]):
        parsed.metric = "avg_price"
    parsed.top_n = _find_top_n(question)
    if _has_any(text, ASC_WORDS):
        parsed.order_asc = True
    parsed.group = _find_group(text)

    normalized = match_key(text)

    if parsed.contract_id is not None:
        parsed.intent = "contract_info"
    elif parsed.deal_id is not None:
        parsed.intent = "deal_info"
    elif parsed.status and any(word in normalized for word in ["holat", "статус", "состояние", "status"]):
        parsed.intent = "status_stats"
    elif _is_top(text) or any(
        word in normalized for word in ["eng kop", "eng katta", "самый", "самых", "рейтинг", "ranking"]
    ):
        parsed.intent = "top"
    elif parsed.company and parsed.company_score >= 80:
        parsed.intent = "company_profile"
    elif parsed.broker and parsed.broker_score >= 90:
        parsed.intent = "broker_stats"
    elif parsed.product.tnveds or parsed.product.categories:
        parsed.intent = "product_stats"
    elif parsed.regions:
        parsed.intent = "region_stats" if _is_top(text) else "total"
    elif parsed.contract_type == "Экспортный":
        parsed.intent = "export_stats"
    elif any(word in normalized for word in ["qaysi bitim", "royxat", "список", "list", "koprsat", "ko'rsat"]):
        parsed.intent = "list_deals"
    elif parsed.metric in {"amount", "count", "volume", "avg_price"} and parsed.has_filters():
        parsed.intent = "total"
    else:
        parsed.intent = "unknown"

    # "Group the deals by product name, count per product, sort descending, show the first 5":
    # an explicit ranking request (grouping/sorting words + a stated N) is a top-N query.
    if (
        parsed.intent in {"total", "unknown", "product_stats", "region_stats"}
        and parsed.contract_id is None
        and parsed.deal_id is None
        and _has_any(text, GROUPING_WORDS + SORT_WORDS)
        and _explicit_top_n(question) is not None
    ):
        grouped = _explicit_group(text)
        if grouped == "product" and (parsed.product.tnveds or parsed.product.categories):
            grouped = None  # the product is a filter here ("neft mahsulotlari"), not the grouping
        if grouped == "region" and parsed.regions:
            grouped = None
        if grouped:
            parsed.intent = "top"
            parsed.group = grouped
            parsed.top_n_explicit = True

    # Top over products/regions/brokers/companies (explicit group wins).
    if parsed.intent == "top" and not parsed.top_n_explicit:
        parsed.group = _find_group(text)

    extra_intent = detect_extra_intent(parsed, question)
    if extra_intent:
        parsed.intent = extra_intent

    # Export questions usually want the USD amount, but show both.
    if parsed.contract_type == "Экспортный" and parsed.metric == "amount":
        parsed.metric = "usd"

    return parsed

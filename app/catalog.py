"""In-memory catalogue and entity matching (companies, products, regions, brokers)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache

from rapidfuzz import fuzz, process

from .db import fetch_dicts
from .normalize import match_key


# ---------------------------------------------------------------------------
# Product concepts: TNVED code -> multilingual keywords
# ---------------------------------------------------------------------------
PRODUCT_KEYWORDS: dict[str, list[str]] = {
    "520100": ["paxta", "pahta", "хлопок", "хлопка", "хлопке", "cotton", "хлопок сырец", "cotton raw"],
    "520512": ["pryaja", "пряжа", "yarn", "ip", "хлопковая пряжа", "paxta ip"],
    "110100": ["un", "мука", "муки", "flour", "мука пшеничная"],
    "100199": ["bugdoy", "буғдой", "пшеница", "пшеницы", "пшеницу", "wheat", "пшеница продовольственная"],
    "100630": ["guruch", "гуруч", "рис", "риса", "rice"],
    "151229": ["paxta yogi", "хлопковое масло", "хлопков", "cotton oil"],
    "151219": ["kungaboqar yogi", "подсолнечное масло", "sunflower oil", "растительное масло"],
    "170199": ["shakar", "шакар", "сахар", "sugar"],
    "220190": ["suv", "сув", "вода", "water", "ichimlik suvi"],
    "230610": ["shrot", "шрот", "kunja", "кунжа", "cake", "cottonseed meal"],
    "230990": ["yem", "ем", "кормосмесь", "feed", "korma"],
    "250100": ["tuz", "туз", "соль", "salt"],
    "252020": ["gips", "гипс", "gypsum"],
    "252210": ["ohak", "оҳак", "известь", "lime"],
    "252329": ["tsement", "sement", "цемент", "семент", "cement", "portland", "portlandsement"],
    "271012": ["benzin", "бензин", "gasoline", "petrol", "ai-80", "ai-92", "ai-95", "аи-80", "аи-92", "аи-95"],
    "271019": ["dizel", "дизель", "дизеля", "дизельного", "diesel", "mazut", "мазут", "топливо", "fuel oil"],
    "271112": ["gaz", "газ", "gas", "propan", "пропан", "butan", "бутан", "pba", "pbt", "сжиженный газ"],
    "271320": ["bitum", "битум", "bitumen"],
    "280421": ["argon", "аргон"],
    "280430": ["azot", "азот", "nitrogen"],
    "280700": ["sulfat kislota", "серная кислота", "sulfuric acid", "кислота"],
    "281511": ["kaustik soda", "каустическая сода", "caustic soda", "soda"],
    "310210": ["karbamid", "карбамид", "urea"],
    "310230": ["selitra", "селитра", "ammonium nitrate", "ammiakli selitra"],
    "320810": ["emal", "эмаль", "enamel", "pf-115", "пф-115"],
    "390120": ["polietilen", "полиэтилен", "polyethylene", "pe", "plastik"],
    "390210": ["polipropilen", "полипропилен", "polypropylene", "pp"],
    "390410": ["polivinilxlorid", "поливинилхлорид", "pvc", "pvx"],
    "391721": ["truba", "труба", "pipe", "quvur"],
    "440711": ["pilomaterial", "пиломатериал", "lumber", "wood", "yogoch", "ёғоч"],
    "690410": ["gisht", "ғишт", "кирпич", "brick"],
    "700529": ["shisha", "шиша", "стекло", "glass"],
    "720853": ["list", "лист", "steel sheet", "po'lat list", "prokat", "прокат"],
    "721420": ["armatura", "арматура", "rebar", "reinforcement"],
    "721710": ["sim", "сим", "проволока", "wire"],
    "740311": ["mis", "мис", "медь", "меди", "copper", "katod", "катод"],
    "760421": ["alyuminiy", "алюминий", "aluminum", "aluminium", "profil"],
    "848210": ["podshipnik", "подшипник", "bearing"],
    "854449": ["kabel", "кабель", "cable"],
}

CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "Продовольственные товары": ["oziq-ovqat", "озиқ-овқат", "продовольствие", "продовольственные", "food"],
    "Сельскохозяйственная продукция": ["qishloq xojaligi", "қишлоқ хўжалиги", "сельхоз", "сельскохозяйственная", "agricultural"],
    "Строительные материалы": ["qurilish materiallari", "қурилиш материаллари", "стройматериалы", "строительные материалы", "construction materials"],
    "Нефтепродукты": ["neft", "нефть", "нефтепродукты", "oil products", "fuel", "ёқилғи"],
    "Химическая продукция": ["kimyo", "кимё", "химия", "химическая", "chemical"],
    "Металлопродукция": ["metall", "металл", "металлопродукция", "metal"],
    "Промышленные товары": ["sanoat", "саноат", "промышленные", "industrial"],
    "Полимерная продукция": ["polimer", "полимер", "polymer", "plastik", "пластик"],
}


def _keyword_in_text(text: str, keyword: str) -> bool:
    keyword = match_key(keyword)
    if not keyword:
        return False
    if len(keyword) <= 3:
        return bool(re.search(rf"(?<!\w){re.escape(keyword)}(?!\w)", text))
    # word-start match: allows inflection suffixes ("paxtani", "пшеницы"),
    # but not hits inside other words ("argon" in "fargona")
    return bool(re.search(rf"(?<!\w){re.escape(keyword)}", text))


@dataclass
class Company:
    inn: str
    name: str
    region: str
    role: str
    activity: str


@dataclass
class Broker:
    code: str
    name: str
    inn: str
    region: str


@dataclass
class Product:
    tnved: str
    name: str
    unit: str
    category: str


@dataclass
class ProductFilter:
    tnveds: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    names: list[str] = field(default_factory=list)
    label: str = ""


@dataclass
class EntityCatalog:
    companies: list[Company]
    brokers: list[Broker]
    products: list[Product]
    regions: list[tuple[str, str]]  # (alias key, region_uz)

    @property
    def company_keys(self) -> list[str]:
        cached = getattr(self, "_company_keys", None)
        if cached is None:
            cached = [match_key(c.name) for c in self.companies]
            object.__setattr__(self, "_company_keys", cached)
        return cached

    @property
    def company_core_keys(self) -> list[str]:
        cached = getattr(self, "_company_core_keys", None)
        if cached is None:
            cached = [company_core(k) for k in self.company_keys]
            object.__setattr__(self, "_company_core_keys", cached)
        return cached


@lru_cache(maxsize=1)
def get_catalog() -> EntityCatalog:
    participants = fetch_dicts(
        "SELECT inn, name, region, role, activity FROM participants"
    )
    companies = [
        Company(
            inn=row["inn"],
            name=row["name"],
            region=row["region"],
            role=row["role"],
            activity=row["activity"],
        )
        for row in participants
    ]

    broker_rows = fetch_dicts("SELECT broker_code, name, inn, region FROM brokers")
    brokers = [
        Broker(code=row["broker_code"], name=row["name"], inn=row["inn"], region=row["region"])
        for row in broker_rows
    ]

    product_rows = fetch_dicts(
        """
        SELECT tnved_code, any_value(product_name) AS name, any_value(unit) AS unit,
               any_value(category) AS category, count(*) AS n
        FROM contracts
        WHERE tnved_code IS NOT NULL
        GROUP BY tnved_code
        """
    )
    products = [
        Product(
            tnved=row["tnved_code"],
            name=row["name"],
            unit=row["unit"],
            category=row["category"],
        )
        for row in product_rows
    ]

    region_pairs = fetch_dicts("SELECT region_ru, region_uz FROM region_map")
    aliases: list[tuple[str, str]] = []
    extra_aliases = {
        "Andijon viloyati": ["andijon", "андижан", "андижанская область", "andijan"],
        "Buxoro viloyati": ["buxoro", "бухоро", "бухар", "бухарская область", "bukhara"],
        "Jizzax viloyati": ["jizzax", "жиззах", "джизак", "джизакская область", "jizzak"],
        "Qashqadaryo viloyati": ["qashqadaryo", "қашқадарё", "кашкадарья", "кашкадарь", "кашкадарьинская область"],
        "Navoiy viloyati": ["navoiy", "навоий", "навоийская область", "navoi"],
        "Namangan viloyati": ["namangan", "наманган", "наманганская область"],
        "Qoraqalpog‘iston Respublikasi": ["qoraqalpogiston", "қорақалпоғистон", "каракалпакстан", "каракалпак"],
        "Samarqand viloyati": ["samarqand", "самарқанд", "самарканд", "самаркандская область"],
        "Surxondaryo viloyati": ["surxondaryo", "сурхондарё", "сурхандарья", "сурхандарь", "сурхандарьинская область"],
        "Sirdaryo viloyati": ["sirdaryo", "сирдарё", "сырдарья", "сырдарь", "сырдарьинская область"],
        "Toshkent viloyati": ["toshkent viloyati", "ташкентская область", "ташкентской области", "ташкентскую область", "ташкентской обл", "тошкент вилояти"],
        "Farg‘ona viloyati": ["fargona", "фарғона", "фергана", "ферган", "ферганская область"],
        "Xorazm viloyati": ["xorazm", "хоразм", "хорезм", "хорезмская область"],
        "Toshkent shahri": ["toshkent shahri", "тошкент шаҳри", "г ташкент", "ташкент город", "toshkent city"],
    }
    for row in region_pairs:
        ru, uz = row["region_ru"], row["region_uz"]
        aliases.append((match_key(ru), uz))
        aliases.append((match_key(uz), uz))
        for alias in extra_aliases.get(uz, []):
            aliases.append((match_key(alias), uz))

    return EntityCatalog(companies=companies, brokers=brokers, products=products, regions=aliases)


# ---------------------------------------------------------------------------
# Entity search
# ---------------------------------------------------------------------------

COMPANY_STOPWORDS = {
    "kompaniya", "компания", "company", "haqida", "haqidagi", "malumot",
    "маълумот", "информация", "info", "about", "boyicha", "буйича",
    "korxona", "предприятие", "firma", "фирма", "qaysi", "какая",
}


GENERIC_COMPANY_WORDS = {
    "mchj", "mch", "mas", "uliyati", "masuliyati", "cheklangan", "jamiyati", "jamiyat",
    "ooo", "oao", "zao", "ao", "aj", "ok", "xk", "chp", "xususiy", "korxonasi", "korxona",
    "aksiyadorlik", "jamiyati", "unitar", "davlat", "qoshma", "korxona", "oilaviy",
    "trade", "treyd", "savdo", "group", "grupp", "servis", "service", "invest", "holding",
    "kholding", "company", "kompaniya", "plus", "lyuks", "lux", "biznes", "business",
    "export", "eksport", "import", "industry", "industriya", "tekstil", "agro", "texnika",
    "fermer", "xojaligi", "mchj", "llc", "ltd",
}


COMMON_QUESTION_WORDS = {
    "god", "goda", "godu", "gody", "godov", "yil", "yilda", "yili", "yilning", "summa", "summe",
    "sdelok", "sdelki", "sdelka", "bitim", "bitimlar", "tovar", "tovara", "tovarov", "region",
    "regione", "oblasti", "oblast", "viloyati", "viloyat", "shahri", "skolko", "qancha", "nechta",
    "prodano", "kupleno", "sotilgan", "sotgan", "sotib", "olgan", "srednyaya", "tsena", "narx",
    "narxi", "eksport", "eksporti", "export", "top", "kompanii", "kompaniy", "kompaniya",
    "prodavets", "pokupatel", "sotuvchi", "xaridor", "broker", "kontrakt", "kontrakta",
    "dollar", "dollarov", "sum", "som", "jami", "obshchaya", "obem", "tonna", "tonn",
    "mesyats", "kvartal", "chorak", "oyda", "proshlom", "otgan", "oxirgi", "posledniy",
}


def company_core(key: str) -> str:
    return " ".join(t for t in key.split() if t not in GENERIC_COMPANY_WORDS and not t.isdigit())


def _entity_candidate(text: str) -> str:
    tokens = [token for token in match_key(text).split() if token not in COMPANY_STOPWORDS]
    return " ".join(tokens)


def find_company(question: str, threshold: int = 85) -> tuple[Company | None, int]:
    """Return the best matching company (or None) and its score."""
    catalog = get_catalog()

    inn_match = re.search(r"(?<!\d)(\d{9})(?!\d)", question)
    if inn_match:
        inn = inn_match.group(1)
        for company in catalog.companies:
            if company.inn == inn:
                return company, 100
        # An explicit INN that is not in the data must never fall back to fuzzy names.
        return None, -1

    # Score on the *distinctive* part of names: legal forms and generic words
    # ("trade", "mchj", "group") must not make two different companies look alike.
    q_tokens = company_core(_entity_candidate(question)).split()
    if not q_tokens:
        return None, 0
    query = " ".join(q_tokens)
    # also try glued neighbours: "sito tom" -> "sitotom"
    q_variants = q_tokens + [a + b for a, b in zip(q_tokens, q_tokens[1:])]
    cores = catalog.company_core_keys
    matches = process.extract(query, cores, scorer=fuzz.token_set_ratio, limit=15)
    best_company: Company | None = None
    best_score = 0
    for _matched, _score, index in matches:
        core = cores[index].split()
        if not core or sum(len(t) for t in core) < 4:
            continue
        # every distinctive token of the company name must appear in the question
        per_token = [max(fuzz.ratio(t, qt) for qt in q_variants) for t in core]
        score = int(min(per_token))
        if len(core) == 1:
            # one-word names collide with ordinary words ("godu", "nur"): exact only
            if len(core[0]) < 5 or core[0] in COMMON_QUESTION_WORDS or score < 100:
                continue
        if score > best_score:
            best_score = score
            best_company = catalog.companies[index]
    if best_score < threshold:
        return None, best_score
    return best_company, best_score


def company_namesakes(company: Company, limit: int = 3) -> list[Company]:
    """Other companies with exactly the same normalized name (different INN)."""
    catalog = get_catalog()
    key = match_key(company.name)
    same = [c for c, k in zip(catalog.companies, catalog.company_keys) if k == key and c.inn != company.inn]
    return same[:limit]


def find_broker(question: str, threshold: int = 86) -> tuple[Broker | None, int]:
    catalog = get_catalog()
    code_match = re.search(r"\b(BK\s*0?(\d{1,3}))\b", question, re.IGNORECASE)
    if code_match:
        number = int(code_match.group(2))
        code = f"BK{number:03d}"
        for broker in catalog.brokers:
            if broker.code == code:
                return broker, 100
    key = match_key(question)
    keys = [match_key(b.name) for b in catalog.brokers]
    matches = process.extract(key, keys, scorer=fuzz.token_set_ratio, limit=5)
    best: Broker | None = None
    best_score = 0
    for _key, score, index in matches:
        if score > best_score:
            best_score = int(score)
            best = catalog.brokers[index]
    if best_score < threshold:
        return None, best_score
    return best, best_score


def find_product_filters(question: str) -> ProductFilter:
    """Resolve product concepts from the question using keywords and fuzzy names."""
    catalog = get_catalog()
    text = match_key(question)
    result = ProductFilter()

    for tnved, keywords in PRODUCT_KEYWORDS.items():
        for keyword in keywords:
            if _keyword_in_text(text, keyword):
                if tnved not in result.tnveds:
                    result.tnveds.append(tnved)
                product = next((p for p in catalog.products if p.tnved == tnved), None)
                if product and not result.label:
                    result.label = product.name
                break

    for category, keywords in CATEGORY_KEYWORDS.items():
        for keyword in keywords:
            if _keyword_in_text(text, keyword):
                if category not in result.categories:
                    result.categories.append(category)
                if not result.label:
                    result.label = category
                break

    # Fuzzy product-name match (only if nothing was found by keywords).
    if not result.tnveds and not result.categories:
        product_keys = [match_key(p.name) for p in catalog.products]
        matches = process.extract(text, product_keys, scorer=fuzz.token_set_ratio, limit=3)
        for _key, score, index in matches:
            if score >= 92:
                product = catalog.products[index]
                result.tnveds.append(product.tnved)
                result.label = product.name
                break

    if result.tnveds and not result.label:
        result.label = ", ".join(result.tnveds)
    return result


def find_regions(question: str) -> tuple[list[str], str]:
    """Return matching region_uz values and a human-readable label."""
    catalog = get_catalog()
    text = match_key(question)
    found: list[str] = []
    labels: list[str] = []

    for alias, region in catalog.regions:
        if _keyword_in_text(text, alias):
            if region not in found:
                found.append(region)
                labels.append(region)

    # "Toshkent" without qualifier is ambiguous: city or region.
    if not found and _keyword_in_text(text, "toshkent"):
        found = ["Toshkent shahri", "Toshkent viloyati"]
        labels = ["Toshkent shahri", "Toshkent viloyati"]
    elif found and "toshkent" in text:
        if "viloyat" in text or "област" in text:
            found = ["Toshkent viloyati"]
        elif "shahar" in text or "город" in text or "city" in text:
            found = ["Toshkent shahri"]

    return found, ", ".join(labels)

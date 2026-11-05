"""Show data values in the language of the question.

Dataset values are mixed: statuses/units/products are Russian, regions in deals are
Uzbek. Known categorical values are translated (exact, whole-word matches only);
company names, codes and numbers are never touched. Product names in Uzbek answers
become "Uzbek name («original»)" so the exact registry wording stays visible.
"""

from __future__ import annotations

import re
from functools import lru_cache

from .db import fetch_dicts

STATUS_UZ = {
    "Аннулирован(Не оплачен)": "bekor qilingan (to‘lanmagan)",
    "Исполнен(Частично)": "qisman ijro etilgan",
    "Не подписан": "imzolanmagan",
    "Ждёт оплату": "to‘lov kutilmoqda",
    "Заключен": "tuzilgan",
    "Оплачен": "to‘langan",
    "Исполнен": "ijro etilgan",
    "Новый": "yangi",
}
UNIT_UZ = {
    "килограмм": "kilogramm", "тонна": "tonna", "штука": "dona", "литр": "litr",
    "куб.метр": "kub metr", "кв.метр": "kvadrat metr", "метр": "metr",
}
MISC_UZ = {
    "Экспортный": "eksport", "Внутренний": "ichki",
    "Спот": "spot", "Форвард": "forvard", "Фьючерс": "fyuchers",
    "Английский аукцион": "ingliz auksioni", "Обратный аукцион": "teskari auksion",
    "Двусторонний аукцион": "ikki tomonlama auksion",
    "Узбекский сум": "o‘zbek so‘mi", "Доллар США": "AQSh dollari",
    "Продавец": "sotuvchi", "Покупатель": "xaridor",
    "Производственное предприятие": "ishlab chiqarish korxonasi",
    "Перерабатывающее предприятие": "qayta ishlash korxonasi",
    "Торговая компания": "savdo kompaniyasi",
    "Транспортная компания": "transport kompaniyasi",
    "Строительная компания": "qurilish kompaniyasi",
    "Производитель": "ishlab chiqaruvchi",
    "Кластер": "klaster",
}
PRODUCT_UZ = {
    "520100": "Paxta xomashyosi", "110100": "Bug‘doy uni", "252329": "Portlandsement",
    "100199": "Oziq-ovqat bug‘doyi", "151229": "Paxta yog‘i", "271012": "Avtomobil benzini",
    "100630": "Silliqlangan guruch", "440711": "Yog‘och materiallari", "230610": "Paxta chigiti shroti",
    "310210": "Karbamid", "271019": "Dizel yoqilg‘isi", "271112": "Suyultirilgan gaz",
    "271320": "Neft bitumi", "320810": "Alkid emal", "220190": "Ichimlik suvi",
    "310230": "Ammiakli selitra", "721420": "Po‘lat armatura", "520512": "Paxta ipi",
    "390210": "Polipropilen", "391721": "Polietilen quvur", "252020": "Qurilish gipsi",
    "690410": "Keramik g‘isht", "700529": "List shisha", "151219": "Rafinadlangan kungaboqar yog‘i",
    "390120": "Polietilen", "720853": "Issiq prokatlangan po‘lat list", "760421": "Alyuminiy profil",
    "740311": "Mis katod", "390410": "Polivinilxlorid", "230990": "Yem aralashmasi",
    "280421": "Argon gazi", "848210": "Podshipnik", "252210": "So‘ndirilmagan ohak",
    "170199": "Oq shakar", "854449": "Kuch kabeli", "721710": "Armatura simi", "280430": "Azot",
    "280700": "Sulfat kislota", "250100": "Osh tuzi", "281511": "Kaustik soda",
}


@lru_cache(maxsize=1)
def _region_ru() -> dict[str, str]:
    try:
        return {r["region_uz"]: r["region_ru"] for r in fetch_dicts("SELECT region_ru, region_uz FROM region_map")}
    except Exception:  # noqa: BLE001
        return {}


@lru_cache(maxsize=1)
def _product_uz() -> dict[str, str]:
    try:
        rows = fetch_dicts("SELECT DISTINCT product_name, tnved_code FROM contracts_full WHERE product_name IS NOT NULL")
    except Exception:  # noqa: BLE001
        return {}
    out = {}
    for r in rows:
        uz = PRODUCT_UZ.get(str(r["tnved_code"]))
        if uz and len(r["product_name"]) >= 4:
            out[r["product_name"]] = uz
    return out


def region_names() -> set[str]:
    return set(_region_ru())


def localizable_values() -> set[str]:
    """Values that the localizer rewrites — the script converter must not freeze them."""
    return set(STATUS_UZ) | set(UNIT_UZ) | set(MISC_UZ) | region_names()


def _sub_all(text: str, mapping: dict[str, str], wrap=None) -> str:
    # never rewrite inside «…» (exact registry wording kept there)
    parts = re.split(r"(«[^»]*»)", text)
    return "".join(
        part if part.startswith("«") else _sub_plain(part, mapping, wrap) for part in parts
    )


def _sub_plain(text: str, mapping: dict[str, str], wrap=None) -> str:
    for src in sorted(mapping, key=len, reverse=True):
        if src not in text:
            continue
        dst = mapping[src] if wrap is None else wrap(src, mapping[src])
        text = re.sub(rf"(?<![\w«]){re.escape(src)}(?![\w»])", lambda _m, d=dst: d, text)
    return text


SOURCE_LABELS = [
    ("Bitimlar / Сделки", "Bitimlar", "Сделки"),
    ("Kontraktlar / Контракты", "Kontraktlar", "Контракты"),
    ("Bitim / Сделка", "Bitim", "Сделка"),
    ("Kontrakt / Контракт", "Kontrakt", "Контракт"),
]


def localize(text: str, lang: str) -> str:
    if not text:
        return text
    for both, uz, ru in SOURCE_LABELS:
        text = text.replace(both, ru if lang == "ru" else uz)
    if lang == "ru":
        return _sub_all(text, _region_ru())
    text = _sub_all(text, _product_uz(), wrap=lambda src, uz: f"{uz} («{src}»)")
    text = _sub_all(text, STATUS_UZ)
    text = _sub_all(text, MISC_UZ)
    text = _sub_all(text, UNIT_UZ)
    return text

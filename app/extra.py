"""Additional template intents: USD rate, extreme deals, distinct participants,
period comparison/dynamics and status shares.

All numbers (including percentages and changes) are computed in SQL.
"""

from __future__ import annotations

import re
from datetime import date

from .db import fetch_dicts
from .normalize import match_key

EXTRA_INTENTS = {"usd_rate", "extreme_deal", "distinct_parties", "compare_periods", "status_share", "avg_deal", "deal_summary", "overview", "contracts_count", "delivery", "analysis", "forecast", "breakdown"}

ANNUL = "Аннулирован(Не оплачен)"


def _has(t: str, pattern: str) -> bool:
    return re.search(pattern, t) is not None


BREAKDOWN_DIMS = [
    ("weekday", r"(hafta kun\w*|haftaning kun\w*|den nedeli|dn\w+ nedeli|dni nedeli|vix\w*dn\w*|dam olish kun\w*)"),
    ("region", r"((viloyat|region|hudud)\w* (boyicha|kesimida|bo.?yicha)|po (region|oblast)\w*|v kajdom (region|oblast)\w*|kajdom (region|oblast)\w*|v razreze (region|oblast)\w*)"),
    ("product", r"((tovar|mahsulot)\w* (turlari |turi )?(boyicha|kesimida)|po tovar\w*|po vidam tovar\w*|v razreze tovar\w*|kajdomu tovaru|kajdyy tovar)"),
    ("category", r"(kategoriya\w*|категори\w*|категор\w*|tovar guruh\w*|guruh\w* (boyicha|kesimida)|tovar toifalari)"),
]
WEEKDAY_UZ = {1: "dushanba", 2: "seshanba", 3: "chorshanba", 4: "payshanba", 5: "juma", 6: "shanba", 7: "yakshanba"}
WEEKDAY_RU = {1: "понедельник", 2: "вторник", 3: "среда", 4: "четверг", 5: "пятница", 6: "суббота", 7: "воскресенье"}


OVERVIEW_INDICATORS = [
    r"(jami|umumiy|obshch\w*|vsego)\s+(\w+\s+)?(bitim\w*|sdelk\w*)|bitimlar soni|kolichestvo sdelok",
    r"(o.?rtacha|sredn\w*)\s+(\w+\s+)?(qiymat\w*|summa\w*|stoimost\w*|znachen\w*)",
    r"(eng katta|eng yirik|krupnejsh\w*|krupnyj\w*|samyh krupn\w*|naibolsh\w*)\s+(\w+\s+)?(qiymat\w*|summa\w*|bitim\w*|sdelk\w*|stoimost\w*)|katta qiymat",
    r"(hudud\w*|viloyat\w*|region\w*|oblast\w*)",
    r"(mahsulot\w*|tovar\w*|produkt\w*|product\w*)",
    r"(eng faol|samyh aktivn\w*|aktivn\w*\s+kompan\w*|faol\s+kompaniya\w*)",
    r"(usd|dollar\w*).*(uzs|som|sum\b)|(ulush\w*|dolya|dolyu|doli)",
    r"\b(top|топ)\s*-?\s*\d+|\b(10|5)\s+ta\b",
]


def is_overview(t: str) -> bool:
    """Several indicators in one request ("complex analysis: totals, average, top deals, regions ...")."""
    return bool(
        _has(t, r"(kompleks\w*|tahlil\w*|analiz\w*|ekonomich\w*|iqtisodiy|otchet\w*|hisobot\w*)")
        and sum(1 for pattern in OVERVIEW_INDICATORS if _has(t, pattern)) >= 5
    )


def detect_breakdown_dim(t: str) -> str | None:
    for dim, pattern in BREAKDOWN_DIMS:
        if re.search(pattern, t):
            return dim
    return None


def detect_extra_intent(p, question: str) -> str | None:
    t = match_key(question)
    if p.contract_id is not None or p.deal_id is not None:
        return None
    from .analytics import detect_analytics

    if is_overview(t):
        return "overview"
    analytic = detect_analytics(p, question)
    if analytic:
        return analytic
    if _has(t, r"\bkurs\w*") and not _has(t, r"\b(summa\w*|summ\w*|bitim\w*|sdel\w*|eksport\w*)"):
        p.extra = {}
        return "usd_rate"
    if getattr(p, "top_n_explicit", False):
        return None  # explicit "group + sort + first N" request stays a ranking
    dim = detect_breakdown_dim(t)
    if dim == "product" and (p.product.tnveds or p.product.categories):
        # "neft mahsulotlari bo‘yicha nechta bitim": the phrase names a product group, it is not a split request
        dim = None
    if not dim and _has(t, r"(qaysi (viloyat|region|hudud)\w*|kakoy region|v kakom region|kakih region)") and _has(
        t, r"(kompaniya|ishtirokchi|qatnashchi|kompani|uchastnik|firm)"
    ) and not _has(t, r"(kontrakt|bitim|sdelk|summa|sum)"):
        p.extra = {"dim": "region", "participants": True}
        return "breakdown"
    if dim:
        p.extra = {"dim": dim}
        if dim == "region" and _has(t, r"(kompaniya|ishtirokchi|qatnashchi|kompani|uchastnik|firm|korxona)") and _has(
            t, r"(nechta|qancha|soni|skolko|kolichestvo|chislo)"
        ):
            p.extra["participants"] = True
        return "breakdown"
    # share by contract form / type / auction type ("spot va forvard ulushi")
    dims = [
        ("contract_form", r"\b(spot\w*|forvard\w*|forward\w*|fyuchers\w*|fyuchers\w*|forma\w*|form\w* kontrakt\w*)"),
        ("contract_type", r"\b(eksport\w*|eksport|ichki|vnutren\w*|tip\w* kontrakt\w*|kontrakt turi)"),
        ("trade_type", r"\b(auksion\w*|aukts\w*|savdo turi|tip\w* torg\w*)"),
    ]
    share_words = r"\b(foiz\w*|ulush\w*|protsent\w*|dol[yei]\w*|nisbat\w*|sootnoshen\w*|taqsimot\w*|raspredelen\w*)"
    if _has(t, share_words) or "%" in question:
        for dim, pattern in dims:
            if len(re.findall(pattern, t)) >= 2 or (dim == "trade_type" and _has(t, pattern)):
                p.extra = {"dim": dim}
                setattr(p, dim, None)
                return "status_share"
        p.extra = {"dim": "status"}
        return "status_share"
    if _has(t, r"(nedopostav\w*|ne postavlen\w*|postavlen\w*|yetkazilmagan|yetkazib berilmagan|yetkazib berilgan|yetkazilgan miqdor|yetkazilish)"):
        return "delivery"
    if _has(t, r"\b(qaysi oy\w*|qaysi oyda|v kakom mesyats\w*|kakoy mesyats|kakom mesyatse)"):
        p.extra = {"grain": "month", "pick_max": True}
        return "compare_periods"
    # "count the deals, the total turnover and the average amount per deal" -> one combined answer
    if (
        _has(t, r"(o.?rtacha|sredn\w*)")
        and _has(t, r"(summa\w*|summ\w*|stoimost\w*|oborot\w*|aylanma\w*)")
        and _has(t, r"(sonin\w*|soni|sanab|sanang|nechta|skolko|kolichestvo|podschita\w*|hisoblab)")
        and _has(t, r"(bitta bitim\w*|bitimga|har bir bitim\w*|bir bitim\w*|odnu sdelk\w*|odnoy sdelk\w*|kazhdoy sdelk\w*|kajdoy sdelk\w*|na sdelk\w*|bitimning o.?rtacha)")
    ):
        return "deal_summary"
    if _has(t, r"(o.?rtacha|srednyaya|sredniy|srednee)\s+(\w+\s+)?(summa\w*|stoimost\w*|razmer\w*|qiymat\w*)\s+(\w+\s+)?(bitim\w*|sdelk\w*)") or _has(
        t, r"(bitim\w*)\s+(\w+\s+)?o.?rtacha\s+(summa|qiymat)"):
        return "avg_deal"
    if _has(t, r"\b(nechta|qancha|skolko|kolichestvo|chislo)\s+(\w+\s+)?(kontrakt\w*|shartnoma\w*)") or _has(
        t, r"\b(kontraktlar soni|shartnomalar soni|zaregistrir\w*|royxatdan otgan|royxatga olingan)"):
        return "contracts_count"
    if not p.statuses and _has(t, r"\b(holat\w*|status\w*|sostoyani\w*)"):
        p.extra = {"dim": "status"}
        return "status_share"
    kind = None
    if _has(t, r"\b(eng|самая|самой|самую|samaya|samoy|samuyu)\s+(katta|yirik|krupn\w*|bolsh\w*|dorog\w*|qimmat)\s*(\w+\s+)?(bitim|sdelk\w*)") or _has(t, r"\b(krupneysh\w*|maksimaln\w*)\s+(sdelk\w*)"):
        kind = "max"
    elif _has(t, r"\b(eng|самая|samaya)\s+(kichik|mayda|malen\w*|melk\w*)\s*(\w+\s+)?(bitim|sdelk\w*)") or _has(t, r"\b(minimaln\w*)\s+sdelk"):
        kind = "min"
    elif _has(t, r"\b(eng\s+)?(birinchi|ilk|perv\w*)\s+(bitim|sdelk\w*)"):
        kind = "first"
    elif _has(t, r"\b(eng\s+)?(oxirgi|songgi|posledn\w*)\s+(bitim|sdelk\w*)") and not _has(t, r"\b(oxirgi|posledn\w*)\s+\d"):
        kind = "last"
    if kind:
        p.extra = {"kind": kind}
        return "extreme_deal"
    if _has(t, r"\b(unikal\w*|unik\w*|uniq\w*|raznyh|razlichn\w*)\b") or _has(
        t, r"\b(nechta|qancha|skolko)\s+(\w+\s+)?(xaridor\w*|sotuvchi\w*|kompaniya\w*|ishtirokchi\w*|qatnashchi\w*|pokupatel\w*|prodavts\w*|prodavets\w*|kompaniy\w*|uchastnik\w*)"
    ):
        role = "both"
        if _has(t, r"(xaridor|pokupatel|sotib ol)"):
            role = "buyer"
        elif _has(t, r"(sotuvchi|prodav|postavshik)"):
            role = "seller"
        p.extra = {"role": role}
        return "distinct_parties"
    compare_words = r"\b(solishtir\w*|taqqos\w*|sravn\w*|farq\w*|raznits\w*|dinamik\w*|ozgar\w*|izmenil\w*|izmenen\w*|rost\w*|osish\w*|osgan)"
    by_year = r"\b(har yil\w*|yillar boyicha|po godam|yilma yil)"
    by_month = r"\b(oyma oy|oylar boyicha|har oy\w*|po mesyats\w*|pomesyachn\w*|ezhemesyachn\w*)"
    if _has(t, by_month):
        p.extra = {"grain": "month"}
        return "compare_periods"
    if _has(t, by_year) or (_has(t, compare_words) and (p.year_to or 0) != (p.year_from or 0)):
        p.extra = {"grain": "year"}
        return "compare_periods"
    if _has(t, compare_words) and p.year_from:
        # "2025 vs previous year" -> compare with the previous year
        p.year_from = p.year_from - 1 if p.year_from > 2022 else p.year_from
        p.extra = {"grain": "year"}
        return "compare_periods"
    return None


# ---------------------------------------------------------------------------
# queries
# ---------------------------------------------------------------------------

def run_extra(p, build_where, base_result):
    if p.intent in {"analysis", "forecast"}:
        from .analytics import run_analytics

        return run_analytics(p, build_where, base_result)
    if p.intent == "usd_rate":
        return _usd_rate(p, base_result)
    if p.intent == "extreme_deal":
        return _extreme_deal(p, build_where, base_result)
    if p.intent == "distinct_parties":
        return _distinct(p, build_where, base_result)
    if p.intent == "compare_periods":
        return _compare(p, build_where, base_result)
    if p.intent == "status_share":
        return _status_share(p, build_where, base_result)
    if p.intent == "breakdown":
        return _breakdown(p, build_where, base_result)
    if p.intent == "avg_deal":
        return _avg_deal(p, build_where, base_result)
    if p.intent == "deal_summary":
        return _deal_summary(p, build_where, base_result)
    if p.intent == "overview":
        return _overview(p, build_where, base_result)
    if p.intent == "delivery":
        return _delivery(p, build_where, base_result)
    if p.intent == "contracts_count":
        return _contracts_count(p, base_result)
    raise ValueError(p.intent)


def _delivery(p, build_where, base_result):
    where = build_where(p)
    if not p.statuses:
        where += " AND status IN ('Оплачен', 'Исполнен', 'Исполнен(Частично)')"
    sql = f"""
        SELECT status, COUNT(*) AS deals, SUM(quantity) AS lots,
               SUM(COALESCE(delivered_quantity, 0)) AS delivered,
               SUM(quantity - COALESCE(delivered_quantity, 0)) AS undelivered,
               ROUND(100.0 * SUM(COALESCE(delivered_quantity, 0)) / NULLIF(SUM(quantity), 0), 2) AS delivered_pct
        FROM deals_enriched WHERE {where}
        GROUP BY 1 ORDER BY deals DESC
    """
    rows = fetch_dicts(sql)
    return base_result(p, "delivery", rows, sql, {})


def _breakdown(p, build_where, base_result):
    """metric x dimension x filters; every figure computed in SQL."""
    dim = p.extra.get("dim", "region")
    if p.extra.get("participants"):
        sql = """SELECT region AS k, NULL AS label, COUNT(*) AS value, COUNT(*) AS deals,
                        ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS share_pct
                 FROM participants GROUP BY 1 ORDER BY value DESC"""
        return base_result(p, "breakdown", fetch_dicts(sql), sql, {"dim": "region", "metric": "participants", "note": "", "unit": None})
    metric, note = p.metric, ""
    where = build_where(p)
    if dim == "weekday":
        key, label, limit = "isodow(deal_date)", "NULL", 7
    elif dim == "product":
        key, label, limit = "tnved_code", "any_value(contract_product_name)", 20
    elif dim == "category":
        key, label, limit = "category", "NULL", 20
    else:
        key, label, limit = "region_uz", "NULL", 20
    if metric == "usd":
        metric = "amount"
    if metric in {"volume", "avg_price"}:
        unit_rows = fetch_dicts(f"SELECT unit FROM deals_enriched WHERE {where} GROUP BY 1 ORDER BY COUNT(*) DESC LIMIT 2")
        if not p.product.tnveds or not unit_rows:
            note = "unit_mix"
            metric = "amount"
        else:
            unit = unit_rows[0]["unit"]
            where += " AND unit = '" + unit.replace("'", "''") + "'"
            if len(unit_rows) > 1:
                note = "unit_chosen"
            p.extra["unit"] = unit
    expr = {
        "count": "COUNT(*)", "amount": "SUM(amount_uzs)", "volume": "SUM(volume)", "avg_price": "AVG(unit_price)",
    }.get(metric, "SUM(amount_uzs)")
    share = metric in {"count", "amount", "volume"}
    sql = f"""
        SELECT {key} AS k, {label} AS label, {expr} AS value, COUNT(*) AS deals,
               {"ROUND(100.0 * " + expr + " / SUM(" + expr + ") OVER (), 2)" if share else "NULL"} AS share_pct
        FROM deals_enriched WHERE {where}
        GROUP BY 1 ORDER BY {"1" if dim == "weekday" else "value DESC NULLS LAST"} LIMIT {limit}
    """
    rows = fetch_dicts(sql)
    return base_result(p, "breakdown", rows, sql, {"dim": dim, "metric": metric, "note": note, "unit": p.extra.get("unit")})


def _avg_deal(p, build_where, base_result):
    where = build_where(p)
    if not p.statuses:
        where += f" AND status <> '{ANNUL}'"
    sql = f"""
        SELECT AVG(amount_uzs) AS avg_uzs, MEDIAN(amount_uzs) AS median_uzs,
               MIN(amount_uzs) AS min_uzs, MAX(amount_uzs) AS max_uzs, COUNT(*) AS deals
        FROM deals_enriched WHERE {where}
    """
    rows = fetch_dicts(sql)
    if rows and not rows[0].get("deals"):
        rows = []
    return base_result(p, "avg_deal", rows, sql, {"annul_excluded": not p.statuses})


def _deal_summary(p, build_where, base_result):
    """Deal count (all statuses), total turnover and average amount per deal (annulled excluded)."""
    where = build_where(p)
    sql = f"""
        SELECT COUNT(*) AS deals_all,
               COUNT(*) FILTER (WHERE status = '{ANNUL}') AS annulled,
               COUNT(*) FILTER (WHERE status <> '{ANNUL}') AS deals_counted,
               SUM(amount_uzs) FILTER (WHERE status <> '{ANNUL}') AS total_uzs,
               AVG(amount_uzs) FILTER (WHERE status <> '{ANNUL}') AS avg_uzs
        FROM deals_enriched WHERE {where}
    """
    rows = fetch_dicts(sql)
    if rows and not rows[0].get("deals_all"):
        rows = []
    return base_result(p, "deal_summary", rows, sql, {})


def _overview(p, build_where, base_result):
    """Complex economic overview: totals, average deal, top deals, regions, products, companies, USD/UZS split.

    Turnover is amount_uzs (USD deals converted at the official rate of the deal date); annulled deals are
    excluded from every sum, ranking and share, and are only counted in the first line.
    """
    where_all = build_where(p)
    where = f"{where_all} AND status <> '{ANNUL}'"
    summary = fetch_dicts(f"""
        SELECT COUNT(*) AS deals_all,
               COUNT(*) FILTER (WHERE status = '{ANNUL}') AS annulled,
               COUNT(*) FILTER (WHERE status <> '{ANNUL}') AS deals_counted,
               SUM(amount_uzs) FILTER (WHERE status <> '{ANNUL}') AS total_uzs,
               AVG(amount_uzs) FILTER (WHERE status <> '{ANNUL}') AS avg_uzs
        FROM deals_enriched WHERE {where_all}
    """)
    if not summary or not summary[0].get("deals_all"):
        return base_result(p, "overview", [], "", {})
    top_deals = fetch_dicts(f"""
        SELECT d.deal_id, d.deal_date, d.contract_product_name AS product, d.amount_uzs,
               ps.name AS seller, pb.name AS buyer
        FROM deals_enriched d
        LEFT JOIN participants ps ON ps.inn = d.seller_inn
        LEFT JOIN participants pb ON pb.inn = d.buyer_inn
        WHERE {where} ORDER BY d.amount_uzs DESC, d.deal_id LIMIT 10
    """)
    regions = fetch_dicts(f"""
        SELECT region_uz AS label, SUM(amount_uzs) AS value, COUNT(*) AS deals
        FROM deals_enriched WHERE {where} GROUP BY 1 ORDER BY value DESC LIMIT 5
    """)
    products = fetch_dicts(f"""
        SELECT tnved_code AS code, any_value(contract_product_name) AS label, SUM(amount_uzs) AS value, COUNT(*) AS deals
        FROM deals_enriched WHERE {where} GROUP BY tnved_code ORDER BY value DESC LIMIT 5
    """)
    companies = fetch_dicts(f"""
        WITH sides AS (
            SELECT seller_inn AS inn, deal_id FROM deals_enriched WHERE {where}
            UNION
            SELECT buyer_inn AS inn, deal_id FROM deals_enriched WHERE {where}
        )
        SELECT s.inn AS code, p.name AS label, COUNT(DISTINCT s.deal_id) AS deals
        FROM sides s LEFT JOIN participants p ON p.inn = s.inn
        GROUP BY s.inn, p.name ORDER BY deals DESC, s.inn LIMIT 10
    """)
    currency = fetch_dicts(f"""
        SELECT CASE WHEN currency = 'Доллар США' THEN 'USD' ELSE 'UZS' END AS cur,
               COUNT(*) AS deals, SUM(amount_uzs) AS value
        FROM deals_enriched WHERE {where} GROUP BY 1 ORDER BY 1
    """)
    total_value = float(summary[0]["total_uzs"] or 0)
    total_deals = sum(float(c["deals"]) for c in currency) or 1.0
    for c in currency:  # shares are computed here so the number guard sees them as sourced values
        c["share_value"] = round(100.0 * float(c["value"] or 0) / total_value, 2) if total_value else 0.0
        c["share_deals"] = round(100.0 * float(c["deals"]) / total_deals, 2)
    meta = {"top_deals": top_deals, "regions": regions, "products": products,
            "companies": companies, "currency": currency}
    return base_result(p, "overview", summary, "-- overview: 6 queries on deals_enriched", meta)


def _contracts_count(p, base_result):
    cond = ["TRUE"]
    if p.date_from or p.date_to:
        cond.append(f"registration_date BETWEEN {_lit(p.date_from or p.date_to)} AND {_lit(p.date_to or p.date_from)}")
    elif p.year_from:
        cond.append(f"EXTRACT(year FROM registration_date) BETWEEN {p.year_from} AND {p.year_to or p.year_from}")
        if p.month:
            cond.append(f"EXTRACT(month FROM registration_date) = {p.month}")
    if p.product.tnveds:
        cond.append("tnved_code IN (" + ", ".join(f"'{c}'" for c in p.product.tnveds) + ")")
    if p.regions:
        cond.append("region_uz IN (" + ", ".join("'" + r.replace("'", "''") + "'" for r in p.regions) + ")")
    if p.contract_type:
        cond.append(f"contract_type = '{p.contract_type}'")
    if p.contract_form:
        cond.append(f"contract_form = '{p.contract_form}'")
    if p.company:
        cond.append(f"seller_inn = '{p.company.inn}'")
    sql = f"""
        SELECT COUNT(*) AS contracts, COUNT(DISTINCT seller_inn) AS sellers,
               COUNT(DISTINCT tnved_code) AS products,
               MIN(registration_date) AS first_date, MAX(registration_date) AS last_date
        FROM contracts_full WHERE {" AND ".join(cond)}
    """
    rows = fetch_dicts(sql)
    if rows and not rows[0].get("contracts"):
        rows = []
    return base_result(p, "contracts_count", rows, sql, {})


def _lit(d: date) -> str:
    return f"DATE '{d.isoformat()}'"


def _usd_rate(p, base_result):
    if p.date_from and p.date_to and p.date_from != p.date_to:
        start, end = p.date_from, p.date_to
    elif p.date_from:
        start = end = p.date_from
    elif p.year_from:
        start = date(p.year_from, p.month or 1, 1)
        end = date(p.year_to or p.year_from, p.month or 12, 28 if p.month == 2 else 30 if p.month in (4, 6, 9, 11) else 31)
    else:
        start = end = date(2026, 10, 30)
    if start == end:
        sql = f"""
            SELECT rate_date, rate FROM usd_rates
            WHERE rate_date <= {_lit(start)}
            ORDER BY rate_date DESC LIMIT 1
        """
        rows = fetch_dicts(sql)
        result = base_result(p, "usd_rate", rows, sql, {"single": True, "asked": start})
    else:
        sql = f"""
            SELECT MIN(rate_date) AS date_from, MAX(rate_date) AS date_to,
                   AVG(rate) AS avg_rate, MIN(rate) AS min_rate, MAX(rate) AS max_rate,
                   arg_min(rate, rate_date) AS first_rate, arg_max(rate, rate_date) AS last_rate,
                   COUNT(*) AS days
            FROM usd_rates WHERE rate_date BETWEEN {_lit(start)} AND {_lit(end)}
        """
        rows = fetch_dicts(sql)
        if rows and not rows[0].get("days"):
            rows = []
        result = base_result(p, "usd_rate", rows, sql, {"single": False})
    result.sources = ["usd_rates.csv"]
    return result


def _extreme_deal(p, build_where, base_result):
    kind = p.extra.get("kind", "max")
    where = build_where(p)
    if kind in {"max", "min"} and not p.statuses:
        where += f" AND status <> '{ANNUL}'"
        p.extra["annul_excluded"] = True
    order = {
        "max": "amount_uzs DESC",
        "min": "amount_uzs ASC",
        "first": "deal_date ASC, deal_time ASC, deal_id ASC",
        "last": "deal_date DESC, deal_time DESC, deal_id DESC",
    }[kind]
    sql = f"""
        SELECT d.deal_id, d.deal_date, d.deal_time, d.contract_id, d.product_name, d.amount, d.currency,
               d.amount_uzs, d.volume, d.unit, d.status, d.region_uz,
               d.seller_inn, s.name AS seller_name, d.buyer_inn, b.name AS buyer_name
        FROM deals_enriched d
        LEFT JOIN participants s ON s.inn = d.seller_inn
        LEFT JOIN participants b ON b.inn = d.buyer_inn
        WHERE {where}
        ORDER BY {order}
        LIMIT 1
    """
    rows = fetch_dicts(sql)
    result = base_result(p, "extreme_deal", rows, sql, dict(p.extra))
    if rows:
        result.sources = [f"Bitim / Сделка: {rows[0]['deal_id']}", f"Kontrakt / Контракт: {rows[0]['contract_id']}"]
    return result


def _distinct(p, build_where, base_result):
    where = build_where(p)
    sql = f"""
        SELECT COUNT(DISTINCT seller_inn) AS sellers,
               COUNT(DISTINCT buyer_inn) AS buyers,
               (SELECT COUNT(*) FROM (
                    SELECT seller_inn AS inn FROM deals_enriched WHERE {where}
                    UNION SELECT buyer_inn FROM deals_enriched WHERE {where})) AS participants,
               COUNT(*) AS deals
        FROM deals_enriched WHERE {where}
    """
    rows = fetch_dicts(sql)
    if rows and not rows[0].get("deals"):
        rows = []
    return base_result(p, "distinct_parties", rows, sql, dict(p.extra))


def _compare(p, build_where, base_result):
    grain = p.extra.get("grain", "year")
    where = build_where(p)
    period = "EXTRACT(year FROM deal_date)" if grain == "year" else "strftime(deal_date, '%Y-%m')"
    status_cond = "TRUE" if p.statuses else f"status <> '{ANNUL}'"
    sql = f"""
        WITH t AS (
            SELECT {period} AS period,
                   COUNT(*) AS deals,
                   SUM(amount_uzs) FILTER (WHERE {status_cond}) AS total_uzs,
                   SUM(volume) FILTER (WHERE {status_cond}) AS volume,
                   COUNT(DISTINCT unit) AS units,
                   any_value(unit) AS unit
            FROM deals_enriched
            WHERE {where}
            GROUP BY 1
        )
        SELECT period, deals, total_uzs, volume, units, unit,
               ROUND(100.0 * (total_uzs - LAG(total_uzs) OVER (ORDER BY period))
                     / NULLIF(LAG(total_uzs) OVER (ORDER BY period), 0), 1) AS change_pct,
               ROUND(100.0 * (deals - LAG(deals) OVER (ORDER BY period))
                     / NULLIF(LAG(deals) OVER (ORDER BY period), 0), 1) AS deals_change_pct
        FROM t ORDER BY period
    """
    rows = fetch_dicts(sql)
    return base_result(p, "compare_periods", rows[:60], sql, dict(p.extra))


def _status_share(p, build_where, base_result):
    saved = p.statuses
    p.statuses = []
    try:
        where = build_where(p)
    finally:
        p.statuses = saved
    dim = (p.extra or {}).get("dim", "status")
    if dim not in {"status", "contract_form", "contract_type", "trade_type"}:
        dim = "status"
    sql = f"""
        SELECT {dim} AS status, COUNT(*) AS deals,
               ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS share_pct,
               SUM(amount_uzs) AS total_uzs,
               ROUND(100.0 * SUM(amount_uzs) / SUM(SUM(amount_uzs)) OVER (), 2) AS amount_share_pct
        FROM deals_enriched
        WHERE {where}
        GROUP BY 1
        ORDER BY deals DESC
    """
    rows = fetch_dicts(sql)
    return base_result(p, "status_share", rows, sql, {"focus": saved, "dim": dim})


# ---------------------------------------------------------------------------
# formatters (legacy Uzbek Latin / Russian; script conversion happens later)
# ---------------------------------------------------------------------------

def format_extra(result, p, fmt_num, fmt_money, fmt_date) -> str:
    if result.intent in {"analysis", "forecast"}:
        from .analytics import format_analytics

        return format_analytics(result, p, fmt_num, fmt_money, fmt_date)
    uz = p.lang == "uz"
    rows = result.rows
    if result.intent == "usd_rate":
        r = rows[0]
        if result.meta.get("single"):
            asked = result.meta.get("asked")
            same = r["rate_date"] == asked
            if uz:
                text = f"{fmt_date(r['rate_date'])} sanadagi USD kursi: 1 USD = {fmt_num(r['rate'])} so‘m."
                if not same:
                    text += f" ({fmt_date(asked)} uchun kurs yo‘q, oxirgi ma’lum kurs olindi.)"
                return text
            text = f"Курс USD на {fmt_date(r['rate_date'])}: 1 USD = {fmt_num(r['rate'])} сум."
            if not same:
                text += f" (на {fmt_date(asked)} курса нет, взят последний известный.)"
            return text
        if uz:
            return (
                f"USD kursi {fmt_date(r['date_from'])} – {fmt_date(r['date_to'])} ({fmt_num(r['days'])} kun): "
                f"o‘rtacha {fmt_num(r['avg_rate'])} so‘m, min {fmt_num(r['min_rate'])}, max {fmt_num(r['max_rate'])}; "
                f"davr boshida {fmt_num(r['first_rate'])}, oxirida {fmt_num(r['last_rate'])} so‘m."
            )
        return (
            f"Курс USD {fmt_date(r['date_from'])} – {fmt_date(r['date_to'])} ({fmt_num(r['days'])} дн.): "
            f"средний {fmt_num(r['avg_rate'])} сум, min {fmt_num(r['min_rate'])}, max {fmt_num(r['max_rate'])}; "
            f"на начало {fmt_num(r['first_rate'])}, на конец {fmt_num(r['last_rate'])} сум."
        )

    if result.intent == "extreme_deal":
        r = rows[0]
        kind = result.meta.get("kind")
        title_uz = {"max": "Eng katta bitim", "min": "Eng kichik bitim", "first": "Eng birinchi bitim", "last": "Eng oxirgi bitim"}[kind]
        title_ru = {"max": "Самая крупная сделка", "min": "Самая маленькая сделка", "first": "Самая первая сделка", "last": "Самая последняя сделка"}[kind]
        cur_usd = r.get("currency") == "Доллар США"
        amount = f"{fmt_num(r['amount'])} USD" if cur_usd else fmt_money(r["amount"], p.lang)
        if uz:
            text = (
                f"{title_uz}: №{r['deal_id']}, {fmt_date(r['deal_date'])} {r['deal_time'] or ''}".rstrip()
                + f". Tovar: {r['product_name']}. Summa: {amount}"
                + (f" ({fmt_money(r['amount_uzs'], p.lang)})" if cur_usd else "")
                + f". Hajm: {fmt_num(r['volume'])} {r['unit']}. Sotuvchi: {r['seller_name']} (INN: {r['seller_inn']}), "
                f"xaridor: {r['buyer_name']} (INN: {r['buyer_inn']}). Kontrakt: {r['contract_id']}, holat: {r['status']}."
            )
        else:
            text = (
                f"{title_ru}: №{r['deal_id']}, {fmt_date(r['deal_date'])} {r['deal_time'] or ''}".rstrip()
                + f". Товар: {r['product_name']}. Сумма: {amount}"
                + (f" ({fmt_money(r['amount_uzs'], p.lang)})" if cur_usd else "")
                + f". Объём: {fmt_num(r['volume'])} {r['unit']}. Продавец: {r['seller_name']} (ИНН: {r['seller_inn']}), "
                f"покупатель: {r['buyer_name']} (ИНН: {r['buyer_inn']}). Контракт: {r['contract_id']}, статус: {r['status']}."
            )
        if kind in {"max", "min"}:
            text += " (summa so‘mda solishtirildi.)" if uz else " (сравнение по сумме в сумах.)"
        return text

    if result.intent == "distinct_parties":
        r = rows[0]
        role = result.meta.get("role")
        if uz:
            parts = {
                "buyer": f"Noyob xaridorlar soni: {fmt_num(r['buyers'])} ta",
                "seller": f"Noyob sotuvchilar soni: {fmt_num(r['sellers'])} ta",
                "both": f"Noyob qatnashchilar (sotuvchi yoki xaridor) soni: {fmt_num(r['participants'])} ta "
                f"(sotuvchilar: {fmt_num(r['sellers'])}, xaridorlar: {fmt_num(r['buyers'])})",
            }[role]
            return f"{parts}; {fmt_num(r['deals'])} ta bitim bo‘yicha (INN bo‘yicha hisoblandi)."
        parts = {
            "buyer": f"Уникальных покупателей: {fmt_num(r['buyers'])}",
            "seller": f"Уникальных продавцов: {fmt_num(r['sellers'])}",
            "both": f"Уникальных участников (продавцы или покупатели): {fmt_num(r['participants'])} "
            f"(продавцов: {fmt_num(r['sellers'])}, покупателей: {fmt_num(r['buyers'])})",
        }[role]
        return f"{parts}; по {fmt_num(r['deals'])} сделкам (подсчёт по ИНН)."

    if result.intent == "compare_periods":
        grain = result.meta.get("grain")
        head = ("Yillar bo‘yicha:" if grain == "year" else "Oylar bo‘yicha:") if uz else ("По годам:" if grain == "year" else "По месяцам:")
        lines = [head]
        for r in rows:
            period = str(int(r["period"])) if grain == "year" else str(r["period"])
            ch = r.get("change_pct")
            dch = r.get("deals_change_pct")
            change = ""
            if ch is not None:
                sign = "+" if ch >= 0 else ""
                dsign = "+" if (dch or 0) >= 0 else ""
                change = (f" (summa {sign}{fmt_num(ch)}%, bitimlar {dsign}{fmt_num(dch)}%)" if uz
                          else f" (сумма {sign}{fmt_num(ch)}%, сделки {dsign}{fmt_num(dch)}%)")
            vol = ""
            if (p.product.tnveds or p.product.categories) and r.get("units") == 1 and r.get("volume") is not None:
                vol = f", {fmt_num(r['volume'])} {r['unit']}"
            if uz:
                lines.append(f"• {period}: {fmt_money(r['total_uzs'], p.lang)}, {fmt_num(r['deals'])} ta bitim{vol}{change}")
            else:
                lines.append(f"• {period}: {fmt_money(r['total_uzs'], p.lang)}, {fmt_num(r['deals'])} сделок{vol}{change}")
        if result.meta.get("pick_max") and rows:
            top_d = max(rows, key=lambda r: r["deals"] or 0)
            top_s = max(rows, key=lambda r: r["total_uzs"] or 0)
            if uz:
                lines.insert(0, f"Eng ko‘p bitim: {top_d['period']} ({fmt_num(top_d['deals'])} ta); "
                                f"eng katta summa: {top_s['period']} ({fmt_money(top_s['total_uzs'], p.lang)}).")
            else:
                lines.insert(0, f"Больше всего сделок: {top_d['period']} ({fmt_num(top_d['deals'])}); "
                                f"наибольшая сумма: {top_s['period']} ({fmt_money(top_s['total_uzs'], p.lang)}).")
        lines.append(
            "Foiz o‘zgarish oldingi davrga nisbatan; summa annul qilinganlarsiz, bitimlar soni barcha holatlar bilan."
            if uz else
            "Изменение в % к предыдущему периоду; сумма без аннулированных, количество сделок — все статусы."
        )
        return "\n".join(lines)

    if result.intent == "overview":
        r, m = rows[0], result.meta
        total = float(r["total_uzs"] or 0)
        deals_label = "ta bitim" if uz else "сделок"

        def money(value):
            return fmt_money(value, p.lang)

        def ranked(title_uz, title_ru, items, label, value_key="value", extra=None):
            lines = ["", title_uz if uz else title_ru]
            for i, it in enumerate(items, start=1):
                tail = f" ({fmt_num(it['deals'])} {deals_label})" if extra == "deals" and it.get("deals") is not None else ""
                lines.append(f"{i}. {label(it)} — {money(it[value_key])}{tail}")
            return lines

        if uz:
            out = [
                "Kompleks iqtisodiy tahlil (summalar so‘mda; USD bitimlari bitim kuni kursi bo‘yicha o‘girilgan, bekor qilinganlarsiz):",
                f"• Jami bitimlar soni: {fmt_num(r['deals_all'])} ta (shundan bekor qilingan {fmt_num(r['annulled'])} ta)",
                f"• Jami savdo summasi: {money(r['total_uzs'])} ({fmt_num(r['deals_counted'])} ta bekor qilinmagan bitim)",
                f"• Bitta bitimning o‘rtacha qiymati: {money(r['avg_uzs'])}",
            ]
        else:
            out = [
                "Комплексный экономический анализ (суммы в сумах; сделки в USD пересчитаны по курсу на дату сделки, без аннулированных):",
                f"• Всего сделок: {fmt_num(r['deals_all'])} (из них аннулировано {fmt_num(r['annulled'])})",
                f"• Общая сумма сделок: {money(r['total_uzs'])} ({fmt_num(r['deals_counted'])} неаннулированных сделок)",
                f"• Средняя сумма одной сделки: {money(r['avg_uzs'])}",
            ]
        out += ranked(
            "Eng katta qiymatga ega 10 ta bitim:", "10 самых крупных сделок:", m["top_deals"],
            lambda it: f"№{it['deal_id']} {fmt_date(it['deal_date'])}, {it.get('product') or '—'}", "amount_uzs",
        )
        out += ranked("Savdo aylanmasi bo‘yicha TOP-5 hudud:", "ТОП-5 регионов по обороту:", m["regions"],
                      lambda it: it["label"] or "—", extra="deals")
        out += ranked("Savdo aylanmasi bo‘yicha TOP-5 mahsulot:", "ТОП-5 товаров по обороту:", m["products"],
                      lambda it: f"{it['label']} (TNVED: {it['code']})", extra="deals")
        out += ["", "Eng faol 10 ta kompaniya (bitimlar soni bo‘yicha):" if uz else "10 самых активных компаний (по числу сделок):"]
        for i, it in enumerate(m["companies"], start=1):
            out.append(f"{i}. {it['label'] or '—'} (INN: {it['code']}) — {fmt_num(it['deals'])} {deals_label}")
        out += ["", "USD va UZS bitimlarining aylanmadagi ulushi:" if uz else "Доля сделок в USD и в UZS в обороте:"]
        for c in m["currency"]:
            share, share_deals = c["share_value"], c["share_deals"]
            name = ("USD bitimlari" if c["cur"] == "USD" else "UZS (so‘m) bitimlari") if uz else (
                "Сделки в USD (в сумах)" if c["cur"] == "USD" else "Сделки в UZS (сум)")
            out.append(
                f"• {name}: {money(c['value'])} — {share:.2f}% aylanma, {fmt_num(c['deals'])} ta bitim ({share_deals:.2f}%)"
                if uz else
                f"• {name}: {money(c['value'])} — {share:.2f}% оборота, {fmt_num(c['deals'])} сделок ({share_deals:.2f}%)"
            )
        return "\n".join(out)

    if result.intent == "deal_summary":
        r = rows[0]
        if uz:
            return (f"Bitimlar soni: {fmt_num(r['deals_all'])} ta (shundan bekor qilingan {fmt_num(r['annulled'])} ta).\n"
                    f"Umumiy savdo summasi: {fmt_money(r['total_uzs'], p.lang)} ({fmt_num(r['deals_counted'])} ta bekor qilinmagan bitim).\n"
                    f"Bitta bitimga o‘rtacha summa: {fmt_money(r['avg_uzs'], p.lang)} "
                    f"(umumiy summa ÷ {fmt_num(r['deals_counted'])}).")
        return (f"Количество сделок: {fmt_num(r['deals_all'])} (из них аннулировано {fmt_num(r['annulled'])}).\n"
                f"Общая сумма сделок: {fmt_money(r['total_uzs'], p.lang)} ({fmt_num(r['deals_counted'])} неаннулированных сделок).\n"
                f"Средняя сумма одной сделки: {fmt_money(r['avg_uzs'], p.lang)} "
                f"(общая сумма ÷ {fmt_num(r['deals_counted'])}).")

    if result.intent == "avg_deal":
        r = rows[0]
        if uz:
            return (f"Bitimning o‘rtacha summasi: {fmt_money(r['avg_uzs'], p.lang)} "
                    f"(mediana {fmt_money(r['median_uzs'], p.lang)}, min {fmt_num(r['min_uzs'])}, max {fmt_num(r['max_uzs'])}; "
                    f"{fmt_num(r['deals'])} ta bitim).")
        return (f"Средняя сумма одной сделки: {fmt_money(r['avg_uzs'], p.lang)} "
                f"(медиана {fmt_money(r['median_uzs'], p.lang)}, min {fmt_num(r['min_uzs'])}, max {fmt_num(r['max_uzs'])}; "
                f"{fmt_num(r['deals'])} сделок).")

    if result.intent == "breakdown":
        dim, metric, note, unit = (result.meta.get(k) for k in ("dim", "metric", "note", "unit"))
        names = {"weekday": ("hafta kunlari", "дням недели"), "region": ("viloyatlar", "регионам"),
                 "product": ("tovarlar", "товарам"), "category": ("kategoriyalar", "категориям")}[dim]
        mname = {"count": ("bitimlar soni", "количество сделок"), "amount": ("summa (so‘m)", "сумма (сум)"),
                 "volume": ("hajm", "объём"), "avg_price": ("o‘rtacha narx", "средняя цена"),
                 "participants": ("kompaniyalar soni (ishtirokchilar reyestri)", "количество компаний (реестр участников)")}[metric]
        lines = [(f"{names[0].capitalize()} bo‘yicha: {mname[0]}" if uz else f"По {names[1]}: {mname[1]}") + (f", {unit}" if unit else "") + ":"]
        if dim == "weekday":
            have = {int(r["k"]): r for r in rows}
            rows = [have.get(d, {"k": d, "label": None, "value": 0, "deals": 0, "share_pct": 0 if metric in {"count", "amount", "volume"} else None}) for d in range(1, 8)]
        for r in rows:
            k = r["k"]
            if dim == "weekday":
                k = (WEEKDAY_UZ if uz else WEEKDAY_RU)[int(k)]
            elif dim == "product":
                k = f"{r['label']} ({k})"
            val = fmt_num(r["value"]) if metric != "amount" else fmt_money(r["value"], p.lang)
            if metric in {"count", "participants"}:
                val += " ta" if uz else ""
            sh = f" — {fmt_num(r['share_pct'])}%" if r.get("share_pct") is not None else ""
            lines.append(f"• {k}: {val}{sh}")
        if note == "unit_mix":
            lines.append("Eslatma: turli o‘lchov birliklari qo‘shilmaydi, shuning uchun summa bo‘yicha ko‘rsatildi." if uz
                         else "Примечание: разные единицы измерения нельзя складывать, поэтому показана сумма.")
        if note == "unit_chosen":
            lines.append(f"Eslatma: tovar bir necha birlikda sotiladi; eng ko‘p uchraydigan birlik ({unit}) olindi." if uz
                         else f"Примечание: товар продаётся в нескольких единицах; взята самая частая ({unit}).")
        if dim == "weekday" and not any(r["value"] for r in rows if int(r["k"]) in (6, 7)):
            lines.append("Shanba va yakshanba kunlari bitim tuzilmagan (ma’lumotlarda 0)." if uz
                         else "В субботу и воскресенье сделок нет (в данных 0).")
        return "\n".join(lines)

    if result.intent == "delivery":
        lines = ["Yetkazib berish (lotlarda):" if uz else "Поставка (в лотах):"]
        for r in rows:
            if uz:
                lines.append(f"• {r['status']}: {fmt_num(r['deals'])} ta bitim, sotilgan {fmt_num(r['lots'])} lot, "
                             f"yetkazilgan {fmt_num(r['delivered'])} ({fmt_num(r['delivered_pct'])}%), "
                             f"yetkazilmagan {fmt_num(r['undelivered'])} lot")
            else:
                lines.append(f"• {r['status']}: {fmt_num(r['deals'])} сделок, продано {fmt_num(r['lots'])} лотов, "
                             f"поставлено {fmt_num(r['delivered'])} ({fmt_num(r['delivered_pct'])}%), "
                             f"недопоставлено {fmt_num(r['undelivered'])} лотов")
        return "\n".join(lines)

    if result.intent == "contracts_count":
        r = rows[0]
        if uz:
            return (f"Ro‘yxatdan o‘tgan kontraktlar: {fmt_num(r['contracts'])} ta "
                    f"(sotuvchilar: {fmt_num(r['sellers'])}, tovar turlari: {fmt_num(r['products'])}; "
                    f"ro‘yxatga olish sanalari {fmt_date(r['first_date'])} – {fmt_date(r['last_date'])}).")
        return (f"Зарегистрировано контрактов: {fmt_num(r['contracts'])} "
                f"(продавцов: {fmt_num(r['sellers'])}, видов товаров: {fmt_num(r['products'])}; "
                f"даты регистрации {fmt_date(r['first_date'])} – {fmt_date(r['last_date'])}).")

    if result.intent == "status_share":
        dim = result.meta.get("dim", "status")
        heads = {
            "status": ("Holatlar ulushi (bitimlar soni bo‘yicha):", "Доли статусов (по количеству сделок):"),
            "contract_form": ("Kontrakt shakllari ulushi (bitimlar soni bo‘yicha):", "Доли форм контракта (по количеству сделок):"),
            "contract_type": ("Kontrakt turlari ulushi (bitimlar soni bo‘yicha):", "Доли типов контракта (по количеству сделок):"),
            "trade_type": ("Savdo turlari ulushi (bitimlar soni bo‘yicha):", "Доли типов торгов (по количеству сделок):"),
        }[dim]
        lines = [heads[0] if uz else heads[1]]
        focus = result.meta.get("focus") or []
        if dim == "status" and focus:
            picked = [r for r in rows if r["status"] in focus]
            for r in picked:
                lines.insert(0, (f"{r['status']}: {fmt_num(r['share_pct'])}% bitimlar ({fmt_num(r['deals'])} ta), "
                                 f"summa bo‘yicha {fmt_num(r['amount_share_pct'])}%." if uz else
                                 f"{r['status']}: {fmt_num(r['share_pct'])}% сделок ({fmt_num(r['deals'])}), "
                                 f"по сумме {fmt_num(r['amount_share_pct'])}%."))
        for r in rows:
            if uz:
                lines.append(f"• {r['status']}: {fmt_num(r['deals'])} ta — {fmt_num(r['share_pct'])}% "
                             f"(summa ulushi {fmt_num(r['amount_share_pct'])}%)")
            else:
                lines.append(f"• {r['status']}: {fmt_num(r['deals'])} — {fmt_num(r['share_pct'])}% "
                             f"(доля суммы {fmt_num(r['amount_share_pct'])}%)")
        return "\n".join(lines)
    return "—"

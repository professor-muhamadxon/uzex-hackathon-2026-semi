"""Additional template intents: USD rate, extreme deals, distinct participants,
period comparison/dynamics and status shares.

All numbers (including percentages and changes) are computed in SQL.
"""

from __future__ import annotations

import re
from datetime import date

from .db import fetch_dicts
from .normalize import match_key

EXTRA_INTENTS = {"usd_rate", "extreme_deal", "distinct_parties", "compare_periods", "status_share", "avg_deal", "contracts_count", "delivery"}

ANNUL = "Аннулирован(Не оплачен)"


def _has(t: str, pattern: str) -> bool:
    return re.search(pattern, t) is not None


def detect_extra_intent(p, question: str) -> str | None:
    t = match_key(question)
    if p.contract_id is not None or p.deal_id is not None:
        return None
    if _has(t, r"\bkurs\w*") and not _has(t, r"\b(summa\w*|summ\w*|bitim\w*|sdel\w*|eksport\w*)"):
        p.extra = {}
        return "usd_rate"
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
    if p.intent == "avg_deal":
        return _avg_deal(p, build_where, base_result)
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

    if result.intent == "avg_deal":
        r = rows[0]
        if uz:
            return (f"Bitimning o‘rtacha summasi: {fmt_money(r['avg_uzs'], p.lang)} "
                    f"(mediana {fmt_money(r['median_uzs'], p.lang)}, min {fmt_num(r['min_uzs'])}, max {fmt_num(r['max_uzs'])}; "
                    f"{fmt_num(r['deals'])} ta bitim).")
        return (f"Средняя сумма одной сделки: {fmt_money(r['avg_uzs'], p.lang)} "
                f"(медиана {fmt_money(r['median_uzs'], p.lang)}, min {fmt_num(r['min_uzs'])}, max {fmt_num(r['max_uzs'])}; "
                f"{fmt_num(r['deals'])} сделок).")

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

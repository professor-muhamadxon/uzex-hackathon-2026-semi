"""Analytics ("tahlil / анализ") and trend forecasts ("bashorat / прогноз").

Every number — including trend slopes, R², forecasts and ranges — is computed in SQL.
Forecasts are always prefixed with an explicit warning that the target period is not
in the data and that the values are a statistical estimate, not facts.
"""

from __future__ import annotations

import re
from datetime import date

from .db import fetch_dicts
from .normalize import match_key

DATA_END = date(2026, 10, 30)
ANNUL = "Аннулирован(Не оплачен)"
MAX_HORIZON = 38  # months after 2026-10 (up to Dec 2029)

ANALYSIS_RE = r"\b(proanaliz\w*|tahlil\w*|taxlil\w*|analiz\w*|analit\w*|tendents\w*|trend\w*|obzor\w*|dinamik\w*|sharh\w*)"
FORECAST_RE = r"\b(bashorat\w*|prognoz\w*|prognos\w*|forecast\w*|predict\w*|predskaz\w*|oldindan ayt\w*)"


def _has(t: str, pattern: str) -> bool:
    return re.search(pattern, t) is not None


def _subject(p, t: str) -> str:
    if _has(t, r"\bkurs\w*") or _has(t, r"\b(dollar|usd)\w* (kurs|narx)"):
        return "usd"
    has_product = bool(p.product.tnveds)
    if has_product and _has(t, r"\b(narx\w*|tsen\w*|price|qiymat\w*)"):
        return "price"
    if has_product and _has(t, r"\b(hajm\w*|obem\w*|obyom\w*|tonn\w*|miqdor\w*|kolichestvo tovar\w*)"):
        return "volume"
    if _has(t, r"\b(soni|nechta|kolichestv\w*|skolko sdel\w*|chislo)"):
        return "count"
    return "deals"


def _forecast_target(question: str, t: str) -> tuple[int, str]:
    """Return (horizon in months after 2026-10, label of the target)."""
    years = [int(y) for y in re.findall(r"(?<!\d)(20\d{2})(?!\d)", question) if int(y) > DATA_END.year]
    if years:
        y = max(years)
        return (y - DATA_END.year) * 12 + (12 - DATA_END.month), f"{y}"
    m = re.search(r"\b(keyingi|kelgusi|kelasi|blizhayshi\w*|sleduyushch\w*|next)\s+(\d{1,2})\s*(?:ta\s+)?(oy|mesyats\w*|month\w*)", t)
    if m:
        n = max(1, min(int(m.group(2)), MAX_HORIZON))
        return n, f"+{n}"
    if _has(t, r"\b(keyingi|kelgusi|kelasi|sleduyushch\w*|next)\s+(oy\w*|mesyats\w*|month)"):
        return 1, "+1"
    if _has(t, r"\b(keyingi|kelgusi|kelasi|sleduyushch\w*|next)\s+(yil\w*|god\w*|year)"):
        return 14, f"{DATA_END.year + 1}"
    if _has(t, r"\bnoyabr"):
        return 1, "+1"
    if _has(t, r"\bdekabr"):
        return 2, "+2"
    return 3, "+3"


def detect_analytics(p, question: str) -> str | None:
    t = match_key(question)
    if _has(t, FORECAST_RE):
        horizon, label = _forecast_target(question, t)
        p.extra = {"subject": _subject(p, t), "horizon": horizon, "target": label}
        # the target period is by definition outside the data: train on the latest months
        if p.not_found_reason == "period":
            p.not_found_reason = None
        p.year_from = p.year_to = None
        p.month = None
        p.date_from = p.date_to = None
        return "forecast"
    if _has(t, ANALYSIS_RE):
        p.extra = {"subject": _subject(p, t)}
        return "analysis"
    return None


# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------

def _lit(d: date) -> str:
    return f"DATE '{d.isoformat()}'"


def _usd_cond(p, col: str = "rate_date") -> str:
    if p.date_from or p.date_to:
        return f"{col} BETWEEN {_lit(p.date_from or p.date_to)} AND {_lit(p.date_to or p.date_from)}"
    cond = ["TRUE"]
    if p.year_from:
        cond.append(f"EXTRACT(year FROM {col}) BETWEEN {p.year_from} AND {p.year_to or p.year_from}")
    if p.month:
        cond.append(f"EXTRACT(month FROM {col}) = {p.month}")
    return " AND ".join(cond)


def _mode_unit(where: str) -> str | None:
    rows = fetch_dicts(
        f"SELECT unit FROM deals_enriched WHERE {where} GROUP BY 1 ORDER BY COUNT(*) DESC LIMIT 1"
    )
    return rows[0]["unit"] if rows else None


def _series_sql(p, subject: str, build_where) -> tuple[str, dict]:
    """Monthly series s(m DATE, v DOUBLE) for the subject."""
    meta: dict = {"subject": subject}
    if subject == "usd":
        return (
            f"SELECT date_trunc('month', rate_date)::DATE AS m, AVG(rate)::DOUBLE AS v "
            f"FROM usd_rates WHERE {_usd_cond(p)} GROUP BY 1"
        ), meta
    where = build_where(p)
    if subject in {"price", "volume"}:
        unit = _mode_unit(where)
        meta["unit"] = unit
        if unit:
            where += " AND unit = '" + unit.replace("'", "''") + "'"
        expr = "AVG(unit_price)" if subject == "price" else "SUM(volume)"
        return (
            f"SELECT date_trunc('month', deal_date)::DATE AS m, ({expr} FILTER (WHERE status <> '{ANNUL}'))::DOUBLE AS v "
            f"FROM deals_enriched WHERE {where} GROUP BY 1"
        ), meta
    if subject == "count":
        return (
            f"SELECT date_trunc('month', deal_date)::DATE AS m, COUNT(*)::DOUBLE AS v "
            f"FROM deals_enriched WHERE {where} GROUP BY 1"
        ), meta
    return (
        f"SELECT date_trunc('month', deal_date)::DATE AS m, "
        f"(SUM(amount_uzs) FILTER (WHERE status <> '{ANNUL}'))::DOUBLE AS v, COUNT(*) AS n "
        f"FROM deals_enriched WHERE {where} GROUP BY 1"
    ), meta


def run_analytics(p, build_where, base_result):
    subject = p.extra.get("subject", "deals")
    series, meta = _series_sql(p, subject, build_where)
    if p.intent == "forecast":
        return _forecast(p, series, meta, base_result)
    return _analysis(p, series, meta, subject, base_result)


def _analysis(p, series: str, meta: dict, subject: str, base_result):
    agg = "AVG(v)" if subject in {"usd", "price"} else "SUM(v)"
    sql = f"""
        WITH s AS ({series}), t AS (SELECT m, v, ROW_NUMBER() OVER (ORDER BY m) AS i FROM s WHERE v IS NOT NULL)
        SELECT COUNT(*) AS months,
               strftime(MIN(m), '%Y-%m') AS first_m, strftime(MAX(m), '%Y-%m') AS last_m,
               arg_min(v, m) AS first_v, arg_max(v, m) AS last_v,
               MIN(v) AS min_v, strftime(arg_min(m, v), '%Y-%m') AS min_m,
               MAX(v) AS max_v, strftime(arg_max(m, v), '%Y-%m') AS max_m,
               AVG(v) AS avg_v, SUM(v) AS sum_v, STDDEV_SAMP(v) AS sd_v,
               ROUND(100.0 * STDDEV_SAMP(v) / NULLIF(AVG(v), 0), 2) AS cv_pct,
               ROUND(100.0 * (arg_max(v, m) - arg_min(v, m)) / NULLIF(arg_min(v, m), 0), 2) AS change_pct,
               regr_slope(v, i) AS slope,
               ROUND(100.0 * regr_slope(v, i) / NULLIF(AVG(v), 0), 2) AS slope_pct,
               ROUND(regr_r2(v, i), 3) AS r2
        FROM t
    """
    rows = fetch_dicts(sql)
    if not rows or not rows[0].get("months"):
        return base_result(p, "analysis", [], sql, meta)
    yearly_sql = f"""
        WITH s AS ({series}), y AS (
            SELECT EXTRACT(year FROM m)::INT AS y, {agg} AS val, COUNT(*) AS months,
                   arg_min(v, m) AS first_v, arg_max(v, m) AS last_v
            FROM s WHERE v IS NOT NULL GROUP BY 1)
        SELECT y, val, months, first_v, last_v,
               ROUND(100.0 * (val - LAG(val) OVER (ORDER BY y)) / NULLIF(LAG(val) OVER (ORDER BY y), 0), 2) AS yoy_pct,
               ROUND(100.0 * (last_v - first_v) / NULLIF(first_v, 0), 2) AS in_year_pct
        FROM y ORDER BY y
    """
    if subject == "usd":
        # yearly figures from daily rates (true average of the year, not mean of monthly means)
        yearly_sql = f"""
            WITH y AS (
                SELECT EXTRACT(year FROM rate_date)::INT AS y, AVG(rate)::DOUBLE AS val,
                       COUNT(DISTINCT date_trunc('month', rate_date)) AS months,
                       arg_min(rate, rate_date)::DOUBLE AS first_v, arg_max(rate, rate_date)::DOUBLE AS last_v
                FROM usd_rates WHERE {_usd_cond(p)} GROUP BY 1)
            SELECT y, val, months, first_v, last_v,
                   ROUND(100.0 * (val - LAG(val) OVER (ORDER BY y)) / NULLIF(LAG(val) OVER (ORDER BY y), 0), 2) AS yoy_pct,
                   ROUND(100.0 * (last_v - first_v) / NULLIF(first_v, 0), 2) AS in_year_pct
            FROM y ORDER BY y
        """
    meta["yearly"] = fetch_dicts(yearly_sql)
    full_sql = sql + ";\n" + yearly_sql
    if subject == "usd":
        daily_sql = f"""
            WITH d AS (SELECT rate_date, rate::DOUBLE AS rate,
                              100.0 * (rate - LAG(rate) OVER (ORDER BY rate_date)) / LAG(rate) OVER (ORDER BY rate_date) AS ch
                       FROM usd_rates WHERE {_usd_cond(p)})
            SELECT MIN(rate_date) AS d_from, MAX(rate_date) AS d_to, COUNT(*) AS days,
                   arg_min(rate, rate_date) AS first_rate, arg_max(rate, rate_date) AS last_rate,
                   MIN(rate) AS min_rate, arg_min(rate_date, rate) AS min_date,
                   MAX(rate) AS max_rate, arg_max(rate_date, rate) AS max_date,
                   ROUND(MAX(ch), 3) AS max_up_pct, arg_max(rate_date, ch) AS max_up_date,
                   ROUND(MIN(ch), 3) AS max_down_pct, arg_min(rate_date, ch) AS max_down_date,
                   ROUND(AVG(ABS(ch)), 3) AS avg_abs_ch,
                   ROUND(100.0 * (POWER(arg_max(rate, rate_date) / arg_min(rate, rate_date),
                         365.0 / NULLIF(MAX(rate_date) - MIN(rate_date), 0)) - 1), 2) AS cagr_pct,
                   ROUND(100.0 * (arg_max(rate, rate_date) - arg_min(rate, rate_date)) / arg_min(rate, rate_date), 2) AS total_pct
            FROM d
        """
        meta["daily"] = (fetch_dicts(daily_sql) or [{}])[0]
        full_sql += ";\n" + daily_sql
    if subject == "deals":
        best_sql = f"""
            WITH s AS ({series})
            SELECT strftime(arg_max(m, n), '%Y-%m') AS busiest_m, MAX(n) AS busiest_n,
                   strftime(arg_min(m, n), '%Y-%m') AS quietest_m, MIN(n) AS quietest_n, SUM(n) AS deals
            FROM s
        """
        meta["counts"] = (fetch_dicts(best_sql) or [{}])[0]
        full_sql += ";\n" + best_sql
    result = base_result(p, "analysis", rows, full_sql, meta)
    return result


def _forecast(p, series: str, meta: dict, base_result):
    h = int(p.extra.get("horizon", 3))
    meta.update({"target": p.extra.get("target"), "horizon": h})
    if h > MAX_HORIZON:
        meta["too_far"] = True
        return base_result(p, "forecast", [{"horizon": h, "max_year": 2029}], "", meta)
    sql = f"""
        WITH s AS ({series}),
        t AS (SELECT m, v, ROW_NUMBER() OVER (ORDER BY m) AS i FROM s WHERE v IS NOT NULL),
        w AS (SELECT * FROM t ORDER BY m DESC LIMIT 12),
        fit AS (SELECT regr_slope(v, i) AS b, regr_intercept(v, i) AS a, MAX(i) AS n, COUNT(*) AS k,
                       MAX(m) AS last_m, MIN(m) AS first_m, arg_max(v, m) AS last_v, ROUND(regr_r2(v, i), 3) AS r2
                FROM w),
        res AS (SELECT STDDEV_SAMP(w.v - (fit.a + fit.b * w.i)) AS sd FROM w, fit),
        h AS (SELECT range AS k FROM range(1, {h + 1})),
        f AS (
            SELECT h.k,
                   strftime(fit.last_m + to_months(h.k::INT), '%Y-%m') AS period,
                   fit.a + fit.b * (fit.n + h.k) AS forecast,
                   GREATEST(0, fit.a + fit.b * (fit.n + h.k) - 1.96 * res.sd) AS low,
                   fit.a + fit.b * (fit.n + h.k) + 1.96 * res.sd AS high,
                   fit.b AS slope, fit.last_v, strftime(fit.last_m, '%Y-%m') AS last_period,
                   strftime(fit.first_m, '%Y-%m') AS train_from, fit.k AS train_months, fit.r2
            FROM fit, res, h)
        SELECT *, SUM(forecast) OVER (PARTITION BY substr(period, 1, 4)) AS year_sum,
               SUM(low) OVER (PARTITION BY substr(period, 1, 4)) AS year_low,
               SUM(high) OVER (PARTITION BY substr(period, 1, 4)) AS year_high,
               AVG(forecast) OVER (PARTITION BY substr(period, 1, 4)) AS year_avg,
               COUNT(*) OVER (PARTITION BY substr(period, 1, 4)) AS year_months
        FROM f ORDER BY k
    """
    rows = fetch_dicts(sql)
    if rows and rows[0].get("forecast") is None:
        rows = []
    return base_result(p, "forecast", rows, sql, meta)


# ---------------------------------------------------------------------------
# Formatting (legacy Uzbek Latin / Russian; script conversion happens later)
# ---------------------------------------------------------------------------

SUBJ_UZ = {"usd": "USD kursi (oylik o‘rtacha, so‘m)", "deals": "bitimlar summasi (oylik, so‘m)",
           "count": "bitimlar soni (oylik)", "price": "o‘rtacha birlik narxi (oylik)", "volume": "savdo hajmi (oylik)"}
SUBJ_RU = {"usd": "курс USD (среднемесячный, сум)", "deals": "сумма сделок (по месяцам, сум)",
           "count": "количество сделок (по месяцам)", "price": "средняя цена за единицу (по месяцам)",
           "volume": "объём торгов (по месяцам)"}


def _trend_word(slope_pct, r2, uz: bool) -> str:
    if slope_pct is None or r2 is None:
        return "trend aniqlanmadi" if uz else "тренд не определён"
    strength = "barqaror" if r2 >= 0.6 else "o‘rtacha" if r2 >= 0.3 else "kuchsiz"
    strength_ru = "устойчивый" if r2 >= 0.6 else "умеренный" if r2 >= 0.3 else "слабый"
    if abs(slope_pct) < 0.1 or r2 < 0.1:
        return "aniq trend yo‘q (qiymatlar asosan bir darajada tebranadi)" if uz else "выраженного тренда нет (значения колеблются около одного уровня)"
    if slope_pct > 0:
        return f"{strength} o‘sish trendi" if uz else f"{strength_ru} рост"
    neuter = {"устойчивый": "устойчивое", "умеренный": "умеренное", "слабый": "слабое"}[strength_ru]
    return f"{strength} pasayish trendi" if uz else f"{neuter} снижение"


def _val(v, subject, meta, fmt_num, fmt_money, lang):
    if subject in {"deals"}:
        return fmt_money(v, lang)
    if subject == "usd":
        return f"{fmt_num(v)} {'so‘m' if lang == 'uz' else 'сум'}"
    if subject == "count":
        return f"{fmt_num(v)} {'ta bitim' if lang == 'uz' else 'сделок'}"
    unit = meta.get("unit") or ""
    if subject == "price":
        return f"{fmt_num(v)} {'so‘m' if lang == 'uz' else 'сум'} / {unit}"
    return f"{fmt_num(v)} {unit}"


def format_analytics(result, p, fmt_num, fmt_money, fmt_date) -> str:
    uz = p.lang == "uz"
    meta = result.meta or {}
    subject = meta.get("subject", "deals")
    rows = result.rows

    def V(v):
        return _val(v, subject, meta, fmt_num, fmt_money, p.lang)

    if result.intent == "forecast":
        target = meta.get("target") or ""
        if meta.get("too_far"):
            return ("Bashorat ufqi juda uzoq: ma’lumotlar 30.10.2026 gacha, ishonchli bashorat ko‘pi bilan 2029-yil oxirigacha beriladi."
                    if uz else "Слишком далёкий горизонт: данные до 30.10.2026, оценка возможна не дальше конца 2029 года.")
        if not rows:
            return "Bashorat uchun ma’lumot yetarli emas." if uz else "Недостаточно данных для прогноза."
        r0 = rows[0]
        if target.isdigit():
            period_txt = f"{target}-yil" if uz else f"{target} год"
        else:
            period_txt = rows[0]["period"] if len(rows) == 1 else f"{rows[0]['period']} – {rows[-1]['period']}"
        warn = (
            f"⚠️ Diqqat: {period_txt} uchun ma’lumotlar berilmagan — ma’lumotlar 30.10.2026 gacha. "
            f"Quyidagi qiymatlar haqiqiy natija emas, balki so‘nggi {fmt_num(r0['train_months'])} oy "
            f"({r0['train_from']} – {r0['last_period']}) ma’lumotlari asosidagi chiziqli trend bo‘yicha statistik taxmin."
            if uz else
            f"⚠️ Внимание: данных за {period_txt} нет — данные заканчиваются 30.10.2026. "
            f"Ниже не фактические значения, а статистическая оценка по линейному тренду за последние "
            f"{fmt_num(r0['train_months'])} мес. ({r0['train_from']} – {r0['last_period']})."
        )
        title = (f"Bashorat: {SUBJ_UZ[subject]}" if uz else f"Прогноз: {SUBJ_RU[subject]}")
        lines = [warn, "", title + ":"]
        shown = [r for r in rows if not target.isdigit() or r["period"].startswith(target)]
        for r in shown:
            rng = (f"taxminiy oraliq {V(r['low'])} – {V(r['high'])}" if uz else f"интервал {V(r['low'])} – {V(r['high'])}")
            lines.append(f"• {r['period']}: ≈ {V(r['forecast'])} ({rng})")
        if target.isdigit() and shown:
            last = shown[-1]
            if subject in {"usd", "price"}:
                lines.append((f"{target}-yil bo‘yicha: o‘rtacha ≈ {V(last['year_avg'])}, yil oxiriga ≈ {V(last['forecast'])}."
                              if uz else f"За {target} год: в среднем ≈ {V(last['year_avg'])}, на конец года ≈ {V(last['forecast'])}."))
            else:
                lines.append((f"{target}-yil jami ≈ {V(last['year_sum'])} (oraliq {V(last['year_low'])} – {V(last['year_high'])}; "
                              f"{fmt_num(last['year_months'])} oy)."
                              if uz else f"Итого за {target} год ≈ {V(last['year_sum'])} (интервал {V(last['year_low'])} – "
                              f"{V(last['year_high'])}; {fmt_num(last['year_months'])} мес.)."))
        slope = r0.get("slope")
        sign = "+" if (slope or 0) >= 0 else ""
        lines.append(
            (f"Asos: oxirgi ma’lum qiymat ({r0['last_period']}) — {V(r0['last_v'])}; trend oyiga {sign}{V(slope)}, R² = {fmt_num(r0['r2'])}."
             if uz else
             f"Основа: последнее известное значение ({r0['last_period']}) — {V(r0['last_v'])}; тренд {sign}{V(slope)} в месяц, R² = {fmt_num(r0['r2'])}.")
        )
        lines.append("Bashorat ishonchliligi R² va oraliq kengligiga bog‘liq; rasmiy prognoz sifatida foydalanmang."
                     if uz else "Надёжность оценки зависит от R² и ширины интервала; не используйте как официальный прогноз.")
        return "\n".join(lines)

    # ---------------- analysis ----------------
    if not rows:
        return "Tahlil uchun ma’lumot topilmadi." if uz else "Данных для анализа не найдено."
    r = rows[0]
    trend = _trend_word(r.get("slope_pct"), r.get("r2"), uz)
    slope = r.get("slope")
    sign = "+" if (slope or 0) >= 0 else ""
    lines: list[str] = []
    if subject == "usd":
        d = meta.get("daily") or {}
        if uz:
            lines.append(f"USD kursi tahlili ({fmt_date(d.get('d_from'))} – {fmt_date(d.get('d_to'))}, {fmt_num(d.get('days'))} kun):")
            lines.append(f"• Boshida {fmt_num(d.get('first_rate'))} so‘m, oxirida {fmt_num(d.get('last_rate'))} so‘m — "
                         f"o‘zgarish {fmt_num(d.get('total_pct'))}% (yillik o‘rtacha {fmt_num(d.get('cagr_pct'))}%).")
            lines.append(f"• Minimum {fmt_num(d.get('min_rate'))} so‘m ({fmt_date(d.get('min_date'))}), "
                         f"maksimum {fmt_num(d.get('max_rate'))} so‘m ({fmt_date(d.get('max_date'))}).")
            lines.append(f"• Kunlik o‘zgarish: o‘rtacha {fmt_num(d.get('avg_abs_ch'))}%; eng katta o‘sish {fmt_num(d.get('max_up_pct'))}% "
                         f"({fmt_date(d.get('max_up_date'))}), eng katta pasayish {fmt_num(d.get('max_down_pct'))}% ({fmt_date(d.get('max_down_date'))}).")
        else:
            lines.append(f"Анализ курса USD ({fmt_date(d.get('d_from'))} – {fmt_date(d.get('d_to'))}, {fmt_num(d.get('days'))} дн.):")
            lines.append(f"• В начале {fmt_num(d.get('first_rate'))} сум, в конце {fmt_num(d.get('last_rate'))} сум — "
                         f"изменение {fmt_num(d.get('total_pct'))}% (в среднем {fmt_num(d.get('cagr_pct'))}% в год).")
            lines.append(f"• Минимум {fmt_num(d.get('min_rate'))} сум ({fmt_date(d.get('min_date'))}), "
                         f"максимум {fmt_num(d.get('max_rate'))} сум ({fmt_date(d.get('max_date'))}).")
            lines.append(f"• Дневные изменения: в среднем {fmt_num(d.get('avg_abs_ch'))}%; максимальный рост {fmt_num(d.get('max_up_pct'))}% "
                         f"({fmt_date(d.get('max_up_date'))}), максимальное падение {fmt_num(d.get('max_down_pct'))}% ({fmt_date(d.get('max_down_date'))}).")
    else:
        title = SUBJ_UZ[subject] if uz else SUBJ_RU[subject]
        lines.append((f"Tahlil: {title}, {r['first_m']} – {r['last_m']} ({fmt_num(r['months'])} oy):"
                      if uz else f"Анализ: {title}, {r['first_m']} – {r['last_m']} ({fmt_num(r['months'])} мес.):"))
        if subject in {"deals", "count", "volume"}:
            lines.append((f"• Jami: {V(r['sum_v'])}; oylik o‘rtacha: {V(r['avg_v'])}." if uz
                          else f"• Всего: {V(r['sum_v'])}; в среднем в месяц: {V(r['avg_v'])}."))
        else:
            lines.append((f"• Birinchi oy: {V(r['first_v'])}, oxirgi oy: {V(r['last_v'])} — o‘zgarish {fmt_num(r['change_pct'])}%."
                          if uz else f"• Первый месяц: {V(r['first_v'])}, последний: {V(r['last_v'])} — изменение {fmt_num(r['change_pct'])}%."))
        lines.append((f"• Eng past oy: {r['min_m']} ({V(r['min_v'])}), eng yuqori oy: {r['max_m']} ({V(r['max_v'])})."
                      if uz else f"• Минимум: {r['min_m']} ({V(r['min_v'])}), максимум: {r['max_m']} ({V(r['max_v'])})."))
        c = meta.get("counts")
        if c and c.get("busiest_m"):
            lines.append((f"• Bitimlar: jami {fmt_num(c['deals'])} ta; eng faol oy {c['busiest_m']} ({fmt_num(c['busiest_n'])} ta), "
                          f"eng sust oy {c['quietest_m']} ({fmt_num(c['quietest_n'])} ta)."
                          if uz else f"• Сделки: всего {fmt_num(c['deals'])}; самый активный месяц {c['busiest_m']} ({fmt_num(c['busiest_n'])}), "
                          f"самый спокойный {c['quietest_m']} ({fmt_num(c['quietest_n'])})."))
        lines.append((f"• Tebranish (variatsiya koeffitsienti): {fmt_num(r['cv_pct'])}%." if uz
                      else f"• Колеблемость (коэффициент вариации): {fmt_num(r['cv_pct'])}%."))
    yearly = meta.get("yearly") or []
    if yearly:
        lines.append("Yillar bo‘yicha:" if uz else "По годам:")
        for y in yearly:
            label = (("o‘rtacha" if uz else "в среднем") if subject in {"usd", "price"} else ("jami" if uz else "всего"))
            yoy = y.get("yoy_pct")
            yoy_txt = ""
            if yoy is not None:
                yoy_txt = (f", oldingi yilga nisbatan {'+' if yoy >= 0 else ''}{fmt_num(yoy)}%" if uz
                           else f", к предыдущему году {'+' if yoy >= 0 else ''}{fmt_num(yoy)}%")
            months = (f" ({fmt_num(y['months'])} oy)" if uz else f" ({fmt_num(y['months'])} мес.)") if y["months"] < 12 else ""
            lines.append(f"• {y['y']}: {label} {V(y['val'])}{months}{yoy_txt}")
    lines.append((f"Trend: oyiga {sign}{V(slope)} ({sign}{fmt_num(r.get('slope_pct'))}% o‘rtachadan), R² = {fmt_num(r.get('r2'))} — {trend}."
                  if uz else f"Тренд: {sign}{V(slope)} в месяц ({sign}{fmt_num(r.get('slope_pct'))}% от среднего), R² = {fmt_num(r.get('r2'))} — {trend}."))
    return "\n".join(lines)

"""Examiner test: 10 analytical questions (each in Russian and Uzbek) with expected answers.

Expected values are computed here with independent SQL / Python (not the agent's code).
The script asks the agent every question, checks that the key facts appear in the
answer, and writes the examiner sheet to docs/ANALYTICS_TEST.md.

    python scripts/analytics_test.py        # run + write docs/ANALYTICS_TEST.md
    python scripts/analytics_test.py -v     # also print the answers
"""

from __future__ import annotations

import argparse
import logging
import math
import statistics as st
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
logging.disable(logging.CRITICAL)

import duckdb  # noqa: E402

from app.agent import Agent  # noqa: E402
from app.config import DB_PATH  # noqa: E402

A = "status <> 'Аннулирован(Не оплачен)'"
con = duckdb.connect(str(DB_PATH), read_only=True)


def one(sql: str):
    return con.execute(sql).fetchone()


def num(v, digits: int = 2) -> str:
    """Same display rule as the bot: thousands with spaces, up to 2 decimals, no trailing zeros."""
    v = float(v)
    if v.is_integer():
        return f"{int(v):,}".replace(",", " ")
    text = f"{v:,.{digits}f}".replace(",", " ")
    return text.rstrip("0").rstrip(".")


def d(x) -> str:
    return x.strftime("%d.%m.%Y")


def linear_forecast(values: list[float], start_index: int, steps: int):
    """OLS on the last 12 monthly values, continued `steps` months; 95% range = ±1.96·sd(residuals)."""
    w = values[-12:]
    xs = list(range(start_index - len(w) + 1, start_index + 1))
    mx, my = st.mean(xs), st.mean(w)
    b = sum((x - mx) * (y - my) for x, y in zip(xs, w)) / sum((x - mx) ** 2 for x in xs)
    a = my - b * mx
    sd = st.stdev([y - (a + b * x) for x, y in zip(xs, w)])
    out = []
    for k in range(1, steps + 1):
        f = a + b * (start_index + k)
        out.append((f, max(0.0, f - 1.96 * sd), f + 1.96 * sd))
    return out, b


# ---------------------------------------------------------------------------
# Gold answers (independent SQL)
# ---------------------------------------------------------------------------

def g1():
    first, last, mn, mx = one("SELECT arg_min(rate, rate_date), arg_max(rate, rate_date), MIN(rate), MAX(rate) FROM usd_rates")
    mxd = one("SELECT arg_max(rate_date, rate) FROM usd_rates")[0]
    pct = round(100 * (float(last) - float(first)) / float(first), 2)
    expect = [num(first), num(last), num(mx), d(mxd), num(pct)]
    text = (f"Boshlanish {num(first)} so‘m → oxiri {num(last)} so‘m, o‘zgarish +{num(pct)}%; "
            f"maksimum {num(mx)} so‘m ({d(mxd)}); trend — barqaror o‘sish.")
    return expect, text


def g2():
    mn, mnd, mx, mxd, avg = one("""SELECT MIN(rate), arg_min(rate_date, rate), MAX(rate), arg_max(rate_date, rate), AVG(rate)
                                   FROM usd_rates WHERE year(rate_date)=2024""")
    expect = [num(mn), d(mnd), num(mx), d(mxd), num(round(float(avg), 2))]
    text = f"2024: minimum {num(mn)} ({d(mnd)}), maksimum {num(mx)} ({d(mxd)}), o‘rtacha ≈ {num(round(float(avg), 2))} so‘m."
    return expect, text


def g3():
    total = one(f"SELECT SUM(amount_uzs) FROM deals_enriched WHERE year(deal_date)=2025 AND {A}")[0]
    best_m, best_n = one("""SELECT strftime(deal_date,'%Y-%m'), COUNT(*) FROM deals_enriched WHERE year(deal_date)=2025
                            GROUP BY 1 ORDER BY 2 DESC LIMIT 1""")
    low_m = one(f"""SELECT strftime(deal_date,'%Y-%m') FROM deals_enriched WHERE year(deal_date)=2025 AND {A}
                    GROUP BY 1 ORDER BY SUM(amount_uzs) LIMIT 1""")[0]
    expect = [num(total), best_m, num(best_n), low_m]
    text = (f"Jami {num(total)} so‘m (annulsiz); eng faol oy {best_m} ({num(best_n)} bitim); "
            f"summa bo‘yicha eng past oy {low_m}.")
    return expect, text


def g4():
    rows = con.execute("SELECT year(deal_date), COUNT(*) FROM deals_enriched GROUP BY 1 ORDER BY 1").fetchall()
    peak_m, peak_n = one("SELECT strftime(deal_date,'%Y-%m'), COUNT(*) FROM deals_enriched GROUP BY 1 ORDER BY 2 DESC LIMIT 1")
    expect = ["500 000"] + [num(n) for _, n in rows] + [peak_m, num(peak_n)]
    text = ("Jami 500 000 bitim; yillar: " + ", ".join(f"{y} — {num(n)}" for y, n in rows)
            + f"; eng yuqori oy {peak_m} ({num(peak_n)}).")
    return expect, text


def g5():
    rows = con.execute(f"""SELECT year(m), AVG(v) FROM (
                             SELECT date_trunc('month', deal_date) m, AVG(unit_price) v FROM deals_enriched
                             WHERE tnved_code='520100' AND unit='килограмм' AND {A} GROUP BY 1) GROUP BY 1 ORDER BY 1""").fetchall()
    expect = [num(round(float(v), 2)) for _, v in rows]
    text = "Paxta (so‘m/kg, oylik o‘rtachalar o‘rtachasi): " + ", ".join(f"{y} — {num(round(float(v), 2))}" for y, v in rows) + "; barqaror o‘sish."
    return expect, text


def g6():
    total = one(f"SELECT SUM(volume) FROM deals_enriched WHERE tnved_code='100199' AND year(deal_date)=2024 AND unit='тонна' AND {A}")[0]
    mx_m = one(f"""SELECT strftime(deal_date,'%Y-%m') FROM deals_enriched WHERE tnved_code='100199' AND year(deal_date)=2024
                   AND unit='тонна' AND {A} GROUP BY 1 ORDER BY SUM(volume) DESC LIMIT 1""")[0]
    expect = [num(total), mx_m]
    text = f"Bug‘doy 2024: jami {num(total)} tonna (annulsiz); eng katta hajm oyi {mx_m}."
    return expect, text


def g7():
    s24 = one(f"SELECT SUM(amount_uzs) FROM deals_enriched WHERE year(deal_date)=2024 AND {A}")[0]
    s25 = one(f"SELECT SUM(amount_uzs) FROM deals_enriched WHERE year(deal_date)=2025 AND {A}")[0]
    pct = round(100 * (float(s25) - float(s24)) / float(s24), 1)
    expect = [num(s24), num(s25), num(pct)]
    text = f"2024: {num(s24)} so‘m → 2025: {num(s25)} so‘m, o‘zgarish +{num(pct)}%."
    return expect, text


def g8():
    pct = one("""SELECT ROUND(100.0*COUNT(*) FILTER (WHERE status='Аннулирован(Не оплачен)')/COUNT(*), 2)
                 FROM deals_enriched WHERE year(deal_date)=2025""")[0]
    n = one("SELECT COUNT(*) FROM deals_enriched WHERE year(deal_date)=2025 AND status='Аннулирован(Не оплачен)'")[0]
    expect = [num(pct), num(n)]
    text = f"2025-yilda bekor qilingan bitimlar: {num(n)} ta, ya’ni {num(pct)}%."
    return expect, text


def g9():
    vals = [float(v) for (v,) in con.execute(
        "SELECT AVG(rate) FROM usd_rates GROUP BY date_trunc('month', rate_date) ORDER BY date_trunc('month', rate_date)").fetchall()]
    (f, lo, hi), = linear_forecast(vals, len(vals), 1)[0][:1]
    expect = [num(round(f, 2)), num(round(lo, 2)), num(round(hi, 2)), "WARN"]
    text = (f"⚠️ 2026-11 uchun ma’lumot yo‘qligi aytilishi SHART; taxmin ≈ {num(round(f, 2))} so‘m "
            f"(95% oraliq {num(round(lo, 2))} – {num(round(hi, 2))}).")
    return expect, text


def g10():
    vals = [float(v) for (v,) in con.execute(
        "SELECT COUNT(*) FROM deals_enriched GROUP BY date_trunc('month', deal_date) ORDER BY date_trunc('month', deal_date)").fetchall()]
    fc, _ = linear_forecast(vals, len(vals), 14)  # Nov 2026 .. Dec 2027
    year = fc[2:]  # 2027-01 .. 2027-12
    total = sum(f for f, _, _ in year)
    expect = [num(round(total, 2)), "WARN"]
    text = f"⚠️ 2027-yil uchun ma’lumot yo‘qligi aytilishi SHART; 2027-yil jami taxmin ≈ {num(round(total, 2))} bitim."
    return expect, text


CASES = [
    ("USD kursi butun davr tahlili", "Проанализируй курс доллара за весь период", "Barcha davr bo‘yicha dollar kursini tahlil qil", g1),
    ("USD kursi 2024 tahlili", "Анализ курса доллара за 2024 год", "2024-yil dollar kursi tahlili", g2),
    ("2025 bitimlar tahlili", "Аналитика сделок за 2025 год", "2025-yil bitimlar tahlili", g3),
    ("Bitimlar soni dinamikasi", "Анализ количества сделок за весь период", "Bitimlar soni dinamikasini tahlil qil", g4),
    ("Paxta narxi dinamikasi", "Проанализируй динамику цены хлопка", "Paxta narxi dinamikasini tahlil qiling", g5),
    ("Bug‘doy hajmi 2024", "Анализ объёма продаж пшеницы в тоннах за 2024 год", "2024-yil bug‘doy savdo hajmi tahlili tonnada", g6),
    ("2024 va 2025 taqqoslash", "Сравни общую сумму сделок 2024 и 2025 годов", "2024 va 2025 yillarda jami summani solishtiring", g7),
    ("Annul ulushi 2025", "Какой процент сделок аннулирован в 2025 году?", "2025-yilda bekor qilingan bitimlar ulushi necha foiz?", g8),
    ("USD bashorati noyabr 2026", "Прогноз курса доллара на ноябрь", "Dollar kursi bashorati noyabr oyi uchun", g9),
    ("Bitimlar soni bashorati 2027", "Прогноз количества сделок на 2027 год", "2027-yil uchun bitimlar soni bashorati", g10),
]

WARN_MARKERS = ["berilmagan", "берилмаган", "данных за", "нет — данные"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    agent = Agent(llm_enabled=False)
    agent.ask("2025-yilda jami savdo summasi qancha?")

    results = []
    for i, (title, q_ru, q_uz, gold) in enumerate(CASES, 1):
        expect, text = gold()
        for lang, q in (("RU", q_ru), ("UZ", q_uz)):
            t0 = time.perf_counter()
            r = agent.ask(q)
            dt = time.perf_counter() - t0
            missing = []
            for e in expect:
                if e == "WARN":
                    if not any(m in r.answer for m in WARN_MARKERS):
                        missing.append("⚠️ warning")
                elif e not in r.answer:
                    missing.append(e)
            ok = not missing and not r.unverified
            results.append((i, title, lang, q, ok, missing, dt, r.intent, r.answer, expect, text))
            flag = "PASS" if ok else "FAIL"
            print(f"[{i:02d}-{lang}] {flag} {dt:.2f}s intent={r.intent}  {q}" + (f"  missing={missing}" if missing else ""))
            if args.verbose:
                print("     " + r.answer.split("\n\n🔎")[0].replace("\n", "\n     ")[:1500])

    passed = sum(1 for r in results if r[4])
    print(f"\nPassed: {passed}/{len(results)}")

    out = ROOT / "docs" / "ANALYTICS_TEST.md"
    out.parent.mkdir(exist_ok=True)
    lines = [
        "# Analitik savollar — tekshiruvchi varaqasi / Аналитические вопросы — лист проверяющего",
        "",
        "Kutilgan qiymatlar agent kodidan mustaqil SQL/Python bilan hisoblangan (`scripts/analytics_test.py`).",
        "Ожидаемые значения посчитаны независимым SQL/Python, не кодом агента.",
        "",
        "Baholash qoidasi: javobda barça kalit raqamlar bölişi, bashoratda esa maʼlumot yöqligi haqida ogohlantiriş "
        "bölişi şart. / Правило: в ответе должны быть все ключевые числа; в прогнозе — обязательное предупреждение "
        "об отсутствии данных.",
        "",
        f"Natija / Результат: **{passed}/{len(results)}**",
        "",
    ]
    for i, (title, q_ru, q_uz, gold) in enumerate(CASES, 1):
        rs = [r for r in results if r[0] == i]
        expect, text = rs[0][9], rs[0][10]
        status = " · ".join(f"{r[2]}: {'✅' if r[4] else '❌'} ({r[6]:.2f} s)" for r in rs)
        lines += [
            f"## {i}. {title}",
            "",
            f"- **RU:** {q_ru}",
            f"- **UZ:** {q_uz}",
            f"- **Kutilgan javob / Ожидаемый ответ:** {text}",
            f"- **Kalit qiymatlar / Ключевые значения:** " + ", ".join(f"`{e}`" if e != "WARN" else "⚠️ ogohlantiriş" for e in expect),
            f"- **Agent:** {status}",
            "",
        ]
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"Examiner sheet: {out.relative_to(ROOT)}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())

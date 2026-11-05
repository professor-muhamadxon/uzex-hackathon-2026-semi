"""Benchmark LLM-written SQL on hard questions (growth, CAGR, same-period comparison, shares, traps).

Gold rows come from hand-written SQL. A case passes when every gold number appears in the numbers the
LLM query returns (extra columns are fine); trap cases pass when the model answers SELECT 'not_found'.

    python scripts/sql_bench.py [model] [-v]
"""

from __future__ import annotations

import sys
import time
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import duckdb  # noqa: E402

from app import llm  # noqa: E402
from app.config import DB_PATH  # noqa: E402
from app.parser import parse_question  # noqa: E402
from app.validator import execute_sql  # noqa: E402

A = "status <> 'Аннулирован(Не оплачен)'"

CASES = [
    ("uz", "Un va shakar savdo summasi yillar bo'yicha qanday o'sgan? Har biri alohida, o'sish foizi bilan.",
     "WITH y AS (SELECT tnved_code t, year(deal_date) y, SUM(amount_uzs) FILTER (WHERE " + A + ") v FROM deals_enriched "
     "WHERE tnved_code IN ('110100','170199') GROUP BY 1,2) SELECT ROUND(100.0*(v-LAG(v) OVER (PARTITION BY t ORDER BY y))"
     "/LAG(v) OVER (PARTITION BY t ORDER BY y),2) g FROM y WHERE y>2022", "num"),
    ("uz", "Dizel va polietilen savdo aylanmasining o'rtacha yillik o'sish sur'ati (CAGR) 2022-2025 yillar uchun qancha?",
     "WITH y AS (SELECT tnved_code t, year(deal_date) y, SUM(amount_uzs) FILTER (WHERE " + A + ") v FROM deals_enriched "
     "WHERE tnved_code IN ('271019','390120') AND year(deal_date) BETWEEN 2022 AND 2025 GROUP BY 1,2) "
     "SELECT ROUND(100.0*(POWER(MAX(v) FILTER (WHERE y=2025)/MAX(v) FILTER (WHERE y=2022),1.0/3)-1),2) FROM y GROUP BY t", "num"),
    ("ru", "Сравни январь-октябрь 2026 с январём-октябрём 2025 по цементу и по пшенице: рост в процентах.",
     "SELECT ROUND(100.0*(SUM(amount_uzs) FILTER (WHERE year(deal_date)=2026 AND " + A + ")/SUM(amount_uzs) FILTER "
     "(WHERE year(deal_date)=2025 AND " + A + ")-1),2) FROM deals_enriched WHERE tnved_code IN ('252329','100199') "
     "AND month(deal_date)<=10 AND year(deal_date) IN (2025,2026) GROUP BY tnved_code", "num"),
    ("uz", "2025-yilda 2024-yilga nisbatan summa bo'yicha eng ko'p o'sgan viloyat qaysi va necha foiz o'sgan?",
     "SELECT ROUND(100.0*(SUM(amount_uzs) FILTER (WHERE year(deal_date)=2025 AND " + A + ")/SUM(amount_uzs) FILTER "
     "(WHERE year(deal_date)=2024 AND " + A + ")-1),2) g FROM deals_enriched GROUP BY region_uz ORDER BY g DESC LIMIT 1", "num"),
    ("ru", "Какова доля топ-3 компаний (продавцов) в общем обороте 2025 года, в процентах?",
     "WITH t AS (SELECT seller_inn, SUM(amount_uzs) v FROM deals_enriched WHERE year(deal_date)=2025 AND " + A + " "
     "GROUP BY 1 ORDER BY v DESC LIMIT 3) SELECT ROUND(100.0*(SELECT SUM(v) FROM t)/(SELECT SUM(amount_uzs) FROM "
     "deals_enriched WHERE year(deal_date)=2025 AND " + A + "),2)", "num"),
    ("uz", "2025-yilda har bir chorakda bitimlar soni qancha bo'lgan?",
     "SELECT COUNT(*) FROM deals_enriched WHERE year(deal_date)=2025 GROUP BY quarter(deal_date) ORDER BY 1", "num"),
    ("ru", "Как менялась средняя цена хлопка по годам и на сколько процентов она выросла каждый год?",
     "WITH y AS (SELECT year(deal_date) y, AVG(unit_price) FILTER (WHERE " + A + ") p FROM deals_enriched "
     "WHERE tnved_code='520100' GROUP BY 1) SELECT ROUND(p,2) FROM y UNION ALL SELECT ROUND(100.0*(p-LAG(p) OVER "
     "(ORDER BY y))/LAG(p) OVER (ORDER BY y),2) FROM y", "num"),
    ("ru", "Сколько компаний в 2025 году были одновременно и продавцом, и покупателем?",
     "SELECT COUNT(*) FROM (SELECT seller_inn FROM deals_enriched WHERE year(deal_date)=2025 INTERSECT "
     "SELECT buyer_inn FROM deals_enriched WHERE year(deal_date)=2025)", "num"),
    ("uz", "2025-yilda eng ko'p bitim bo'lgan hafta kuni qaysi va uning ulushi necha foiz?",
     "SELECT ROUND(100.0*COUNT(*)/(SELECT COUNT(*) FROM deals_enriched WHERE year(deal_date)=2025),2) FROM "
     "deals_enriched WHERE year(deal_date)=2025 GROUP BY isodow(deal_date) ORDER BY COUNT(*) DESC LIMIT 1", "num"),
    ("ru", "В каком месяце 2025 года оборот по бензину был максимальным и какую долю годового оборота он составил?",
     "WITH m AS (SELECT month(deal_date) mo, SUM(amount_uzs) FILTER (WHERE " + A + ") v FROM deals_enriched "
     "WHERE tnved_code='271012' AND year(deal_date)=2025 GROUP BY 1) SELECT ROUND(100.0*v/(SELECT SUM(v) FROM m),2) "
     "FROM m ORDER BY v DESC LIMIT 1", "num"),
    ("uz", "Oltin narxi 2022 dan 2025 gacha yillar bo'yicha qanday o'sgan?", None, "trap"),
    ("ru", "Какой годовой объём продаж угля и как он вырос?", None, "trap"),
]


def numbers(rows) -> list[float]:
    out: list[float] = []
    for row in rows:
        for value in (row.values() if isinstance(row, dict) else row):
            if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
                out.append(float(value))
    return out


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if args:
        llm.LLM_MODEL = args[0]
    verbose = "-v" in sys.argv
    con = duckdb.connect(str(DB_PATH), read_only=True)
    passed = 0
    times: list[float] = []
    for lang, question, gold, kind in CASES:
        hints = llm.sql_hints(parse_question(question))
        started = time.time()
        sql = llm.generate_sql(question, lang, hints=hints)
        err = None
        rows: list = []
        for _ in range(2):
            if not sql:
                break
            try:
                rows = execute_sql(sql)
                err = None
                break
            except Exception as exc:  # noqa: BLE001
                err = str(exc)[:160]
                sql = llm.generate_sql(question, lang, previous_error=err, hints=hints)
        elapsed = time.time() - started
        times.append(elapsed)
        if kind == "trap":
            ok = bool(rows) and str(rows[0].get("error", "")).lower() == "not_found"
            why = "not_found" if ok else f"rows={str(rows)[:120]} err={err}"
        else:
            want = numbers(con.execute(gold).fetchall())
            have = numbers(rows)
            missing = [w for w in want if not any(abs(w - h) <= max(0.011, abs(w) * 1e-9) for h in have)]
            ok = bool(rows) and not missing
            why = "ok" if ok else f"missing {missing[:4]} | err={err}"
        passed += ok
        print(f"{'OK  ' if ok else 'FAIL'} {elapsed:4.1f}s {question[:80]}")
        if not ok or verbose:
            print("      ", why, "\n       SQL:", (sql or "")[:300].replace("\n", " "))
    times.sort()
    print(f"\n{llm.LLM_MODEL}: {passed}/{len(CASES)} passed, median {times[len(times) // 2]:.1f}s, max {times[-1]:.1f}s")


if __name__ == "__main__":
    main()

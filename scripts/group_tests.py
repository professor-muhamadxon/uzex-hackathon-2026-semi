"""Regression tests for ranking / summary / missing-subject questions (RU, UZ lat, UZ cyr).

Gold values come from independent SQL, not from the agent:
  * "group by product, count, sort descending, show the first N"
  * "count deals + total turnover + average per deal"
  * price / fluctuation / forecast questions about goods that are NOT in the registry (gold, coal)
  * "least ..." rankings and "first half of the year" periods

    python scripts/group_tests.py
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import duckdb  # noqa: E402

from app.agent import Agent  # noqa: E402
from app.config import DB_PATH  # noqa: E402
from eval import is_not_found, spaced  # noqa: E402

ANNUL = "Аннулирован(Не оплачен)"  # status value of cancelled deals

con = duckdb.connect(str(DB_PATH), read_only=True)
FEB = "deal_date BETWEEN DATE '2025-02-01' AND DATE '2025-02-28'"


def top_counts(n: int) -> list[str]:
    rows = con.execute(
        f"SELECT COUNT(*) c FROM deals_enriched WHERE {FEB} GROUP BY tnved_code ORDER BY c DESC LIMIT {n}"
    ).fetchall()
    return [spaced(r[0]) for r in rows]


def summary_values() -> list[str]:
    total, annulled, total_sum, avg = con.execute(
        f"""SELECT COUNT(*), COUNT(*) FILTER (WHERE status='{ANNUL}'),
                   SUM(amount_uzs) FILTER (WHERE status<>'{ANNUL}'),
                   AVG(amount_uzs) FILTER (WHERE status<>'{ANNUL}')
            FROM deals_enriched WHERE year(deal_date)=2025"""
    ).fetchone()
    return [spaced(total), spaced(annulled), spaced(math.floor(float(total_sum))), spaced(math.floor(float(avg)))]


def least_companies() -> list[str]:
    inn = con.execute(
        """WITH s AS (SELECT seller_inn inn, deal_id FROM deals_enriched UNION SELECT buyer_inn, deal_id FROM deals_enriched)
           SELECT inn FROM s GROUP BY inn ORDER BY COUNT(DISTINCT deal_id), inn LIMIT 1"""
    ).fetchone()[0]
    return [inn]


def cotton_h1() -> list[str]:
    value = con.execute(
        f"""SELECT SUM(amount_uzs) FROM deals_enriched WHERE tnved_code='520100'
            AND deal_date BETWEEN DATE '2025-01-01' AND DATE '2025-06-30' AND status<>'{ANNUL}'"""
    ).fetchone()[0]
    return [spaced(math.floor(float(value)))]


def overview_values() -> list[str]:
    where = f"year(deal_date)=2025 AND status<>'{ANNUL}'"
    region = con.execute(f"SELECT SUM(amount_uzs) v FROM deals_enriched WHERE {where} GROUP BY region_uz ORDER BY v DESC LIMIT 1").fetchone()[0]
    product = con.execute(f"SELECT SUM(amount_uzs) v FROM deals_enriched WHERE {where} GROUP BY tnved_code ORDER BY v DESC LIMIT 1").fetchone()[0]
    top_deal = con.execute(f"SELECT MAX(amount_uzs) FROM deals_enriched WHERE {where}").fetchone()[0]
    company = con.execute(
        f"""WITH s AS (SELECT seller_inn inn, deal_id FROM deals_enriched WHERE {where}
                       UNION SELECT buyer_inn, deal_id FROM deals_enriched WHERE {where})
            SELECT COUNT(DISTINCT deal_id) c FROM s GROUP BY inn ORDER BY c DESC LIMIT 1"""
    ).fetchone()[0]
    usd, total = con.execute(
        f"SELECT SUM(amount_uzs) FILTER (WHERE currency='Доллар США'), SUM(amount_uzs) FROM deals_enriched WHERE {where}"
    ).fetchone()
    share = f"{100 * float(usd) / float(total):.2f}"
    return summary_values() + [spaced(math.floor(float(region))), spaced(math.floor(float(product))),
                               spaced(math.floor(float(top_deal))), spaced(company), share]


CASES = [
    ("uz-lat", "2025-yil davomida UZEX birjasida amalga oshirilgan bitimlarni kompleks iqtisodiy tahlil qiling. Quyidagi ko‘rsatkichlarni hisoblang: jami bitimlar soni, jami savdo summasi UZSda, bitta bitimning o‘rtacha qiymati, eng katta qiymatga ega 10 ta bitim, savdo aylanmasi bo‘yicha TOP-5 hudud, savdo aylanmasi bo‘yicha TOP-5 mahsulot, eng faol 10 ta kompaniya, USD va UZS bitimlarining umumiy aylanmadagi ulushi.", overview_values, "values"),
    ("ru", "Проведите комплексный экономический анализ сделок за 2025 год: общее количество сделок, общая сумма в UZS, средняя сумма сделки, 10 самых крупных сделок, ТОП-5 регионов по обороту, ТОП-5 товаров по обороту, 10 самых активных компаний, доля сделок в USD и UZS в обороте.", overview_values, "values"),
    ("uz-cyr", "2025-йилда тузилган битимларнинг умумий савдо суммасини, битимлар сонини ва битта битимга тўғри келадиган ўртача суммани ҳисобласин. USD битимларини битим тузилган кундаги расмий курс бўйича UZSга айлантирсин. Жавобни UZS кўринишида бер", summary_values, "values"),
    ("uz-lat", "2025-yil fevral oyidagi bitimlarni mahsulot nomi bo‘yicha guruhlang, har bir mahsulot uchun bitimlar sonini hisoblang va natijalarni kamayish tartibida saralang. Birinchi 5 ta mahsulotni ko‘rsating.", lambda: top_counts(5), "values"),
    ("uz-cyr", "2025 йил феврал ойидаги битимларни маҳсулот номи бўйича гуруҳланг, ҳар бир маҳсулот учун битимлар сонини ҳисобланг, камайиш тартибида саралаб, биринчи 5 тасини кўрсатинг.", lambda: top_counts(5), "values"),
    ("ru", "Группируйте сделки за февраль 2025 по названию товара, посчитайте количество сделок по каждому товару, отсортируйте по убыванию и покажите первые 5.", lambda: top_counts(5), "values"),
    ("uz-lat", "2025-yilda tuzilgan bitimlar sonini sanab, umumiy savdo summasini va bitta bitimga to‘g‘ri keladigan o‘rtacha summani aniqla", summary_values, "values"),
    ("uz-cyr", "2025 йилда тузилган битимлар сонини санаб, умумий савдо суммасини ва битта битимга тўғри келадиган ўртача суммани аниқланг", summary_values, "values"),
    ("ru", "Посчитай количество сделок за 2025 год, общую сумму и среднюю сумму на одну сделку", summary_values, "values"),
    ("uz-lat", "Oltin narxining 2025 yildan 2026 yilgacha bo'lgan tebranish davri va 2027 chi yilgacha bolgan prognoz", None, "trap"),
    ("uz-lat", "Ko'mirning 2025 yilning yarmidagi tebranish davri", None, "trap"),
    ("ru", "Какова динамика цены золота за 2025 год и прогноз до 2027 года?", None, "trap"),
    ("uz-cyr", "Кўмирнинг 2025 йилдаги нарх тебраниши", None, "trap"),
    ("uz-lat", "Eng kam bitim tuzgan 10 ta tashkilot", least_companies, "values"),
    ("ru", "Какие 10 организаций заключили меньше всего сделок?", least_companies, "values"),
    ("uz-lat", "Paxtaning 2025 yilning yarmidagi savdo summasi qancha?", cotton_h1, "values"),
]


def main() -> int:
    agent = Agent(llm_enabled=False)
    agent.ask("2025-yilda jami savdo summasi qancha?")
    failed = 0
    for lang, question, gold, kind in CASES:
        answer = agent.ask(question).answer
        if kind == "trap":
            ok, why = is_not_found(answer), "must say the subject is not in the data"
        else:
            expected = gold()
            missing = [e for e in expected if e not in answer]
            ok, why = not missing, f"missing {missing}" if missing else "ok"
        failed += not ok
        print(f"{'OK  ' if ok else 'FAIL'} [{lang}] {question[:70]}")
        if not ok:
            print("     ", why, "|", answer.split("\n\n")[0][:200].replace("\n", " | "))
    print(f"\n{len(CASES) - failed}/{len(CASES)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

"""50 new test questions (RU, Uzbek Cyrillic, Uzbek Latin) with independent gold SQL.

Writes docs/claude_tests.md: every question, the gold value computed directly from the
database (not through the agent), the agent's answer and a pass/fail mark.

    python scripts/claude_tests.py
"""

from __future__ import annotations

import math
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import duckdb  # noqa: E402

from app.agent import Agent  # noqa: E402
from app.config import DB_PATH  # noqa: E402
from eval import ANNUL, answer_lang_ok, is_not_found, spaced  # noqa: E402

D = "deals_enriched"


def cnt(where: str) -> str:
    return f"SELECT COUNT(*) FROM {D} WHERE {where}"


def amt(where: str) -> str:
    return f"SELECT SUM(amount_uzs) FROM {D} WHERE {where} AND {ANNUL}"


def reg(name: str) -> str:
    return f"region_ru = '{name}'"


# (language, question, kind, gold sql | None)   kind: num | trap
CASES = [
    # ---------------------------------------------------------------- Russian
    ("ru", "Сколько сделок было в Самаркандской области в 2023 году?", "num", cnt(f"year(deal_date)=2023 AND {reg('Самаркандская область')}")),
    ("ru", "Сколько сделок в Хорезмской области в 2025 году?", "num", cnt(f"year(deal_date)=2025 AND {reg('Хорезмская область')}")),
    ("ru", "Какова общая сумма сделок в 2022 году?", "num", amt("year(deal_date)=2022")),
    ("ru", "Какова общая сумма сделок в 2026 году?", "num", amt("year(deal_date)=2026")),
    ("ru", "Сколько сделок со статусом «Исполнен» в 2024 году?", "num", cnt("year(deal_date)=2024 AND status='Исполнен'")),
    ("ru", "Сколько сделок было аннулировано в 2023 году?", "num", cnt("year(deal_date)=2023 AND status='Аннулирован(Не оплачен)'")),
    ("ru", "Сколько сделок по нефтепродуктам в 2024 году?", "num", cnt("year(deal_date)=2024 AND category='Нефтепродукты'")),
    ("ru", "Какая общая сумма сделок по металлопродукции в 2025 году?", "num", amt("year(deal_date)=2025 AND category='Металлопродукция'")),
    ("ru", "Сколько сделок в Ферганской области за 2022 год?", "num", cnt(f"year(deal_date)=2022 AND {reg('Ферганская область')}")),
    ("ru", "Сколько контрактов зарегистрировано в 2023 году?", "num", "SELECT COUNT(*) FROM contracts_full WHERE year(registration_date)=2023"),
    ("ru", "Какой курс доллара на 15 мая 2024 года?", "num", "SELECT rate FROM usd_rates WHERE rate_date='2024-05-15'"),
    ("ru", "Сколько сделок в Ташкентской области в 2024 году?", "num", cnt(f"year(deal_date)=2024 AND {reg('Ташкентская область')}")),
    ("ru", "Сколько сделок в Бухарской области в первом квартале 2025 года?", "num", cnt(f"deal_date BETWEEN '2025-01-01' AND '2025-03-31' AND {reg('Бухарская область')}")),
    ("ru", "Сколько сделок было в марте 2024 года?", "num", cnt("year(deal_date)=2024 AND month(deal_date)=3")),
    ("ru", "Какая сумма сделок в 2028 году?", "trap", None),
    ("ru", "Какая чистая прибыль у продавцов?", "trap", None),
    ("ru", "Сколько сделок по золоту в 2024 году?", "trap", None),
    # ------------------------------------------------------- Uzbek (Cyrillic)
    ("uz-cyr", "2024 йилда Фарғона вилоятида нечта битим бўлган?", "num", cnt(f"year(deal_date)=2024 AND {reg('Ферганская область')}")),
    ("uz-cyr", "2023 йилда Бухоро вилоятида нечта битим бўлган?", "num", cnt(f"year(deal_date)=2023 AND {reg('Бухарская область')}")),
    ("uz-cyr", "2025 йилда жами савдо суммаси қанча?", "num", amt("year(deal_date)=2025")),
    ("uz-cyr", "2022 йилда жами савдо суммаси қанча?", "num", amt("year(deal_date)=2022")),
    ("uz-cyr", "2025 йилда нечта битим бекор қилинган?", "num", cnt("year(deal_date)=2025 AND status='Аннулирован(Не оплачен)'")),
    ("uz-cyr", "2024 йилда нечта битим ижро этилган?", "num", cnt("year(deal_date)=2024 AND status IN ('Исполнен','Исполнен(Частично)')")),
    ("uz-cyr", "2024 йилда нефть маҳсулотлари бўйича нечта битим бўлган?", "num", cnt("year(deal_date)=2024 AND category='Нефтепродукты'")),
    ("uz-cyr", "2023 йилда Навоий вилоятида нечта битим бўлган?", "num", cnt(f"year(deal_date)=2023 AND {reg('Навоийская область')}")),
    ("uz-cyr", "2026 йилда нечта битим тузилган?", "num", cnt("year(deal_date)=2026")),
    ("uz-cyr", "2022 йилда Қашқадарё вилоятида нечта битим бўлган?", "num", cnt(f"year(deal_date)=2022 AND {reg('Кашкадарьинская область')}")),
    ("uz-cyr", "2025 йил май ойида нечта битим тузилган?", "num", cnt("year(deal_date)=2025 AND month(deal_date)=5")),
    ("uz-cyr", "2024 йилда Хоразм вилоятида битимлар суммаси қанча?", "num", amt(f"year(deal_date)=2024 AND {reg('Хорезмская область')}")),
    ("uz-cyr", "2025 йил 1-чоракда нечта битим тузилган?", "num", cnt("deal_date BETWEEN '2025-01-01' AND '2025-03-31'")),
    ("uz-cyr", "2024 йил 10 июнда доллар курси қанча?", "num", "SELECT rate FROM usd_rates WHERE rate_date='2024-06-10'"),
    ("uz-cyr", "2027 йилда нечта битим бўлади?", "trap", None),
    ("uz-cyr", "Тошкентда бугун об-ҳаво қандай?", "trap", None),
    ("uz-cyr", "Олтин бўйича 2024 йилда нечта битим бўлган?", "trap", None),
    # ---------------------------------------------------------- Uzbek (Latin)
    ("uz-lat", "2023-yilda Namangan viloyatida nechta bitim bo‘lgan?", "num", cnt(f"year(deal_date)=2023 AND {reg('Наманганская область')}")),
    ("uz-lat", "2024-yilda Samarqand viloyatida nechta bitim bo‘lgan?", "num", cnt(f"year(deal_date)=2024 AND {reg('Самаркандская область')}")),
    ("uz-lat", "2023-yilda jami savdo summasi qancha?", "num", amt("year(deal_date)=2023")),
    ("uz-lat", "2026-yilda jami savdo summasi qancha?", "num", amt("year(deal_date)=2026")),
    ("uz-lat", "2025-yilda nechta bitim bekor qilingan?", "num", cnt("year(deal_date)=2025 AND status='Аннулирован(Не оплачен)'")),
    ("uz-lat", "2023-yilda nechta bitim ijro etilgan?", "num", cnt("year(deal_date)=2023 AND status IN ('Исполнен','Исполнен(Частично)')")),
    ("uz-lat", "2025-yilda neft mahsulotlari bo‘yicha nechta bitim bo‘lgan?", "num", cnt("year(deal_date)=2025 AND category='Нефтепродукты'")),
    ("uz-lat", "2022-yilda Andijon viloyatida nechta bitim bo‘lgan?", "num", cnt(f"year(deal_date)=2022 AND {reg('Андижанская область')}")),
    ("uz-lat", "2025-yil iyul oyida nechta bitim tuzilgan?", "num", cnt("year(deal_date)=2025 AND month(deal_date)=7")),
    ("uz-lat", "2024-yilda kimyo mahsulotlari bo‘yicha nechta bitim bo‘lgan?", "num", cnt("year(deal_date)=2024 AND category='Химическая продукция'")),
    ("uz-lat", "2025-yilda Surxondaryo viloyatida bitimlar summasi qancha?", "num", amt(f"year(deal_date)=2025 AND {reg('Сурхандарьинская область')}")),
    ("uz-lat", "2024-yil 2-chorakda nechta bitim tuzilgan?", "num", cnt("deal_date BETWEEN '2024-04-01' AND '2024-06-30'")),
    ("uz-lat", "2025-yil 3-martda dollar kursi qancha?", "num", "SELECT rate FROM usd_rates WHERE rate_date='2025-03-03'"),
    ("uz-lat", "2023-yilda ro‘yxatdan o‘tgan kontraktlar soni nechta?", "num", "SELECT COUNT(*) FROM contracts_full WHERE year(registration_date)=2023"),
    ("uz-lat", "Eng ko‘p foyda ko‘rgan kompaniya qaysi?", "trap", None),
    ("uz-lat", "2019-yilda nechta bitim bo‘lgan?", "trap", None),
]
assert len(CASES) == 50, len(CASES)


def gold_strings(value) -> list[str]:
    v = float(value)
    return sorted({spaced(math.floor(v)), spaced(round(v))})


def main() -> int:
    con = duckdb.connect(str(DB_PATH), read_only=True)
    agent = Agent(llm_enabled=False)
    agent.ask("2025-yilda jami savdo summasi qancha?")  # warm-up

    rows = []
    for index, (lang, question, kind, sql) in enumerate(CASES, start=1):
        gold = None
        expected: list[str] = []
        if sql:
            gold = con.execute(sql).fetchone()[0]
            expected = gold_strings(gold) if gold is not None else []
        started = time.perf_counter()
        response = agent.ask(question)
        seconds = time.perf_counter() - started
        answer = response.answer
        if kind == "trap":
            ok = is_not_found(answer)
        else:
            ok = bool(expected) and any(e in answer for e in expected) and not is_not_found(answer)
        rows.append({
            "n": index, "lang": lang, "q": question, "kind": kind, "gold": gold, "expected": expected,
            "answer": answer, "ok": ok, "lang_ok": answer_lang_ok(answer, lang), "seconds": seconds,
            "unverified": response.unverified,
        })

    passed = sum(r["ok"] for r in rows)
    traps = [r for r in rows if r["kind"] == "trap"]
    lines = [
        "# claude_tests: 50 ta yangi savol (rus, o‘zbek kirill, o‘zbek lotin)",
        "",
        f"Sana: {time.strftime('%Y-%m-%d %H:%M')}. Agent: LLM o‘chiq (`llm_enabled=False`), `RAG_ENABLED` .env bo‘yicha.",
        "Kutilgan qiymatlar agent kodidan **mustaqil** SQL bilan to‘g‘ridan-to‘g‘ri bazadan hisoblangan "
        "(`scripts/claude_tests.py`). Summa va narxlarda annul qilingan bitimlar hisobga olinmaydi, "
        "bitimlar sonida hisobga olinadi. Viloyat filtri sotuvchi ombori viloyatini bildiradi. «Ijro etilgan» = «Исполнен» + «Исполнен(Частично)» (agent shuni javobda ko‘rsatadi).",
        "",
        "## Natija",
        "",
        "| Guruh | Savollar | To‘g‘ri |",
        "|---|---:|---:|",
    ]
    for lang in ("ru", "uz-cyr", "uz-lat"):
        group = [r for r in rows if r["lang"] == lang]
        lines.append(f"| {lang} | {len(group)} | {sum(r['ok'] for r in group)} |")
    lines.append(f"| shundan tuzoq (ma’lumotda javob yo‘q) | {len(traps)} | {sum(r['ok'] for r in traps)} |")
    lines.append(f"| **Jami** | **{len(rows)}** | **{passed}** |")
    lines += [
        "",
        f"Javob tili/yozuvi to‘g‘ri: {sum(r['lang_ok'] for r in rows)}/{len(rows)}. "
        f"Tasdiqlanmagan raqamli javoblar: {sum(1 for r in rows if r['unverified'])}. "
        f"O‘rtacha vaqt: {sum(r['seconds'] for r in rows) / len(rows):.2f} s, eng uzog‘i: {max(r['seconds'] for r in rows):.2f} s.",
        "",
        "## Savollar",
        "",
        "| № | Til | Savol | Kutilgan | Natija |",
        "|---:|---|---|---|---|",
    ]
    for r in rows:
        exp = "topilmadi (tuzoq)" if r["kind"] == "trap" else (r["expected"][0] if r["expected"] else "—")
        lines.append(f"| {r['n']} | {r['lang']} | {r['q']} | {exp} | {'✅' if r['ok'] else '❌'} |")

    failed = [r for r in rows if not r["ok"] or not r["lang_ok"]]
    lines += ["", "## Xatolar", ""]
    if not failed:
        lines.append("Xato yo‘q.")
    for r in failed:
        short = r["answer"].split("\n\n")[0].replace("\n", " ")[:300]
        lines.append(f"- **№{r['n']}** ({r['lang']}) {r['q']}")
        lines.append(f"  - kutilgan: {r['expected'] or r['kind']}; til/yozuv: {'to‘g‘ri' if r['lang_ok'] else 'NOTO‘G‘RI'}")
        lines.append(f"  - agent javobi: {short}")
    out = ROOT / "docs" / "claude_tests.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{passed}/{len(rows)} correct; written {out}")
    for r in failed:
        print("FAIL", r["n"], r["q"], "|", r["expected"] or r["kind"], "|", r["answer"].split("\n\n")[0][:160])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""End-to-end smoke tests for the local agent.

Run:  .venv/bin/python scripts/smoke_test.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agent import get_agent  # noqa: E402

# (question, required substrings in the answer)
CASES: list[tuple[str, list[str]]] = [
    ("2025-yilda jami savdo summasi qancha?", ["52 060 836 360 057"]),
    ("2025-yilda qancha bitim bo‘lgan?", ["115 763"]),
    ("2025-yilda qancha paxta sotilgan?", ["Хлопок сырец", "1 844 729 923"]),
    ("Eng ko‘p paxta sotgan 5 kompaniya", ["SITO‘TOM TEKSTIL", "Top 5"]),
    ("Eng ko‘p sotilgan 5 tovar", ["520100", "100199"]),
    ("Qaysi regionda eng ko‘p bitim?", ["Toshkent shahri", "98 435"]),
    ("Namangan viloyatida qancha bitim bo‘lgan?", ["58 493"]),
    ("Toshkent shahrida jami savdo summasi qancha?", ["37 679 992 529 872"]),
    ("100001-kontrakt haqida ma’lumot", ["100001", "Профиль алюминиевый"]),
    ("100001-bitim haqida ma’lumot", ["100001", "Шрот хлопковых семян"]),
    ("604956-bitim", ["604956", "Хлопок"]),
    ("Annul qilingan bitimlar soni", ["33 719"]),
    ("Broker BK001 bo‘yicha statistika", ["BK001", "4 282"]),
    ("Qaysi broker eng ko‘p bitim qilgan?", ["BK111"]),
    ("2026-yilda bug‘doy narxi qancha?", ["Пшеница", "tonna"]),
    ("2025-yil yanvar oyida qancha bitim bo‘ldi?", ["6 196"]),
    ("SITO‘TOM TEKSTIL MCHJ haqida ma’lumot", ["925910430", "11 341"]),
    ("925910430 INN bo‘yicha ma’lumot", ["SITO‘TOM TEKSTIL", "925910430"]),
    ("2024-yilda eksport qancha dollar?", ["$202 495 621"]),
    ("2023-yilda eksport summasi dollarida", ["$193 408 881"]),
    ("2022-yilda jami summa", ["27 965 891 730 951"]),
    # Russian
    ("В каком регионе больше всего сделок?", ["г. Ташкент", "98 435"]),
    ("Сколько сделок в Наманганской области?", ["58 493"]),
    ("Топ-5 компаний по сумме сделок в 2024 году", ["Mo‘jotat Klaster"]),
    ("Сколько тонн пшеницы продано в 2023 году?", ["Пшеница", "1 830 742"]),
    ("Средняя цена хлопка в 2025 году", ["9 207"]),
    ("Аннулированные сделки за 2025 год", ["8 085"]),
    ("Какие товары продавались больше всего?", ["520100", "100199"]),
    ("Сколько муки продано в 2024 году?", ["Мука пшеничная", "109 538 300"]),
    ("Компания SITO TOM TEKSTIL", ["SITO‘TOM TEKSTIL", "925910430"]),
    ("2023-yilda eksport summasi dollarida", ["$193 408 881"]),
    # Honest "not found" behaviour
    ("Экспорт хлопка в 2025 году", ["не найдено"]),
    ("2024-yilda paxta eksporti qancha?", ["topilmadi"]),
]


def main() -> int:
    agent = get_agent()
    failures: list[str] = []

    for index, (question, required) in enumerate(CASES, start=1):
        try:
            response = agent.ask(question)
            answer = response.answer
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{index}. {question}\n   ERROR: {exc}")
            print(f"[{index:02d}] ERROR  {question}")
            continue

        missing = [item for item in required if item not in answer]
        if missing:
            failures.append(
                f"{index}. {question}\n   missing: {missing}\n   answer: {answer[:400]}"
            )
            print(f"[{index:02d}] FAIL   {question}  (missing: {missing})")
        else:
            print(f"[{index:02d}] OK     {question}")

    print()
    if failures:
        print(f"{len(failures)} / {len(CASES)} failed:\n")
        for failure in failures:
            print(failure)
            print()
        return 1

    print(f"All {len(CASES)} smoke tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

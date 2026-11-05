"""Regression eval: agent answers vs. gold values from hand-written SQL.

Gold SQL in scripts/eval_set.json is written independently of the agent's templates.
Checks: the gold number appears in the answer (num), the gold string appears
(contains), or the answer is an explicit "not found" (not_found). Also: language of
the answer, unverified numbers (answer guard) and latency.

    python scripts/eval.py            # summary + failures
    python scripts/eval.py -v         # every answer
    python scripts/eval.py --md       # markdown table for SOLUTION.md
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import duckdb  # noqa: E402

from app.agent import Agent  # noqa: E402
from app.config import DB_PATH  # noqa: E402

ANNUL = "status <> 'Аннулирован(Не оплачен)'"
NOT_FOUND_MARKERS = [
    "topilmadi", "топилмади", "mavjud emas", "мавжуд эмас", "не найден", "нет информации",
    "отсутствует", "не найдено", "ma’lumot topilmadi", "qamraydi", "қамрайди", "охватывают",
]


def spaced(n: int) -> str:
    return f"{n:,}".replace(",", " ")


def gold_strings(value) -> list[str]:
    v = float(value)
    return list({spaced(math.floor(v)), spaced(round(v))})


def is_not_found(answer: str) -> bool:
    low = answer.lower()
    return any(m in low for m in NOT_FOUND_MARKERS)


def answer_lang_ok(answer: str, lang: str) -> bool:
    """Template words must be in the question's language/script (data names are exempt)."""
    if lang == "ru":
        return not re.search(r"\b(bitim|so‘m|Jami|Filtr|битим|сўм)\b", answer)
    if lang == "uz-cyr":
        return bool(re.search(r"(битим|сўм|жами|филтр|топилмади|мавжуд|сони|қанча|Маълумот|Саволни)", answer, re.I)) \
            and not re.search(r"\b(bitim|so‘m|Filtr)\b", answer)
    if lang == "uz-new":
        return not re.search(r"(so‘m|bo‘yicha|o‘rtacha|Ma’lumot|Filtr: .*bo‘)", answer)
    return not re.search(r"\b(сделок|Фильтр)\b", answer)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("--md", action="store_true")
    args = ap.parse_args()

    cases = json.loads((ROOT / "scripts" / "eval_set.json").read_text(encoding="utf-8"))
    con = duckdb.connect(str(DB_PATH), read_only=True)
    agent = Agent(llm_enabled=False)
    agent.ask("2025-yilda jami savdo summasi qancha?")  # warm-up (catalog load)

    results = []
    for case in cases:
        expected: list[str] = []
        if case.get("gold"):
            row = con.execute(case["gold"].replace("{A}", ANNUL)).fetchone()
            value = row[0] if row else None
            if case["type"] == "num":
                expected = gold_strings(value) if value is not None else []
            else:
                expected = [str(value)]
        started = time.perf_counter()
        resp = agent.ask(case["q"])
        seconds = time.perf_counter() - started
        answer = resp.answer
        if case["type"] == "not_found":
            ok = is_not_found(answer)
        else:
            ok = bool(expected) and any(e in answer for e in expected) and not is_not_found(answer)
        lang_ok = answer_lang_ok(answer, case["lang"])
        results.append({**case, "ok": ok, "lang_ok": lang_ok, "seconds": seconds,
                        "expected": expected, "answer": answer, "unverified": resp.unverified})

    total = len(results)
    passed = sum(r["ok"] for r in results)
    lang_passed = sum(r["lang_ok"] for r in results)
    traps = [r for r in results if r["type"] == "not_found"]
    avg = sum(r["seconds"] for r in results) / total
    worst = max(r["seconds"] for r in results)
    unverified = sum(1 for r in results if r["unverified"])

    for r in results:
        if args.verbose or not r["ok"] or not r["lang_ok"]:
            flag = "OK  " if r["ok"] else "FAIL"
            print(f"[{r['id']:02d}] {flag} lang={'ok' if r['lang_ok'] else 'BAD'} {r['seconds']:.2f}s  {r['q']}")
            if not r["ok"] or args.verbose:
                print(f"     expected: {r['expected'] or r['type']}")
                print("     answer:  ", r["answer"].split("\n\n")[0][:300].replace("\n", " | "))

    by_lang: dict[str, list[bool]] = {}
    for r in results:
        by_lang.setdefault(r["lang"], []).append(r["ok"])
    print()
    print(f"Correct: {passed}/{total} ({100 * passed / total:.1f}%)")
    print(f"Traps ('not found') correct: {sum(r['ok'] for r in traps)}/{len(traps)}")
    print(f"Answer language/script correct: {lang_passed}/{total}")
    print(f"Answers with unverified numbers: {unverified}")
    print(f"Latency: avg {avg:.2f}s, max {worst:.2f}s")
    for lang, oks in by_lang.items():
        print(f"  {lang}: {sum(oks)}/{len(oks)}")

    if args.md:
        print("\n| Group | Questions | Correct |\n|---|---:|---:|")
        for lang, oks in by_lang.items():
            print(f"| {lang} | {len(oks)} | {sum(oks)} |")
        print(f"| trap questions (not found) | {len(traps)} | {sum(r['ok'] for r in traps)} |")
        print(f"| **Total** | **{total}** | **{passed} ({100 * passed / total:.0f}%)** |")
        print(f"\nAverage latency {avg:.2f} s, max {worst:.2f} s (without LLM).")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())

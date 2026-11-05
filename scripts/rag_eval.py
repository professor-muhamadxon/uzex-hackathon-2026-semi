"""RAG on/off comparison.

Runs the same questions in two subprocesses (RAG_ENABLED=0 / 1) so the flag is read fresh.
Set A: scripts/eval_set.json (regression). Set B: typo/synonym RU/UZ product/region
questions below, with independent gold SQL (counts of deals) or expected "not found".
A wrong-but-confident answer (neither gold nor 'not found') is counted as WRONG.

    python scripts/rag_eval.py            # orchestrates both runs, prints table
"""

from __future__ import annotations

import json
import math
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# (question, lang, gold SQL or None for expected not_found)
TYPO_CASES = [
    ("2025-yilda sementt bo‘yicha nechta bitim bo‘lgan?", "uz-lat", "tnved_code='252329' AND year(deal_date)=2025"),
    ("2024 yilda nechta bitim tsemnt bo‘yicha?", "uz-lat", "tnved_code='252329' AND year(deal_date)=2024"),
    ("Сколько сделок по цименту в 2025 году?", "ru", "tnved_code='252329' AND year(deal_date)=2025"),
    ("Сколько сделок по пшеницие в 2024 году?", "ru", "tnved_code='100199' AND year(deal_date)=2024"),
    ("2025-yilda guruchh bo‘yicha nechta bitim?", "uz-lat", "tnved_code='100630' AND year(deal_date)=2025"),
    ("Сколько сделок по бензену в 2025 году?", "ru", "tnved_code='271012' AND year(deal_date)=2025"),
    ("2024-yilda dizell bo‘yicha nechta bitim?", "uz-lat", "tnved_code='271019' AND year(deal_date)=2024"),
    ("Сколько сделок по сахару 2025 — сахарр?", "ru", "tnved_code='170199' AND year(deal_date)=2025"),
    ("2023-yilda armaturra bo‘yicha nechta bitim?", "uz-lat", "tnved_code='721420' AND year(deal_date)=2023"),
    ("Сколько сделок по карбомиду в 2024 году?", "ru", "tnved_code='310210' AND year(deal_date)=2024"),
    ("2025-yilda ammiakli selitrra bo‘yicha nechta bitim?", "uz-lat", "tnved_code='310230' AND year(deal_date)=2025"),
    ("Сколько сделок по алюминию в 2025 году?", "ru", "tnved_code='760421' AND year(deal_date)=2025"),
    ("Сколько сделок в Самаркандкой области в 2025 году?", "ru", "region_uz='Samarqand viloyati' AND year(deal_date)=2025"),
    ("2024-yilda Samarqnad viloyatida nechta bitim?", "uz-lat", "region_uz='Samarqand viloyati' AND year(deal_date)=2024"),
    ("Сколько сделок в Хорезмской облсти в 2025 году?", "ru", "region_uz='Xorazm viloyati' AND year(deal_date)=2025"),
    ("2025-yilda Fargonaa viloyatida nechta bitim?", "uz-lat", "region_uz='Farg‘ona viloyati' AND year(deal_date)=2025"),
    ("Сколько сделок в Бухорской области в 2024 году?", "ru", "region_uz='Buxoro viloyati' AND year(deal_date)=2024"),
    # traps: nonsense / absent products must give 'not found', never a guess
    ("2025-yilda qizilbaliq bo‘yicha nechta bitim?", "uz-lat", None),
    ("Сколько сделок по зубочисткам в 2025 году?", "ru", None),
    ("2025-yilda xlorofuzin bo‘yicha nechta bitim?", "uz-lat", None),
    ("Сколько сделок по золоту в 2025 году?", "ru", None),
    ("Сколько сделок по компьютерам в 2024 году?", "ru", None),
    ("Сколько сделок по шоколаду в 2025 году?", "ru", None),
    ("2024-yilda avtomobil bo‘yicha nechta bitim?", "uz-lat", None),
    ("2025-yilda oltin bo‘yicha nechta bitim?", "uz-lat", None),
    ("2023-yilda kartoshka bo‘yicha nechta bitim?", "uz-lat", None),
    ("2025-йилда телевизор бўйича нечта битим?", "uz-cyr", None),
    ("Сколько сделок по смартфонам в 2023 году?", "ru", None),
    ("2024-yilda mashina bo‘yicha nechta bitim?", "uz-lat", None),
    ("Сколько сделок по молоку в 2025 году?", "ru", None),
    # company typos (RAG fallback, strict threshold)
    ("SITOTOM TEKSTILL MCHJ haqida ma’lumot", "uz-lat", ("contains", "925910430")),
]


def spaced(n: int) -> str:
    return f"{n:,}".replace(",", " ")


def run_one() -> None:
    """Child process: print JSON results for both sets with the current RAG flag."""
    import duckdb

    from app.agent import Agent
    from app.config import DB_PATH, RAG_ENABLED
    from scripts.eval import ANNUL, gold_strings, is_not_found  # noqa: F401

    con = duckdb.connect(str(DB_PATH), read_only=True)
    agent = Agent(llm_enabled=False)
    agent.ask("2025-yilda jami savdo summasi qancha?")
    out = {"rag": RAG_ENABLED, "A": [], "B": []}
    for case in json.loads((ROOT / "scripts" / "eval_set.json").read_text(encoding="utf-8")):
        ans = agent.ask(case["q"]).answer
        if case["type"] == "not_found":
            ok = is_not_found(ans)
        else:
            v = con.execute(case["gold"].replace("{A}", ANNUL)).fetchone()[0]
            exp = gold_strings(v) if case["type"] == "num" and v is not None else [str(v)]
            ok = any(e in ans for e in exp) and not is_not_found(ans)
        out["A"].append({"q": case["q"], "ok": ok})
    for q, lang, where in TYPO_CASES:
        ans = agent.ask(q).answer
        nf = is_not_found(ans)
        if isinstance(where, tuple):
            verdict = "ok" if where[1] in ans and not nf else ("notfound" if nf else "WRONG")
        elif where is None:
            verdict = "ok" if nf else "WRONG"
        else:
            n = con.execute(f"SELECT COUNT(*) FROM deals_enriched WHERE {where}").fetchone()[0]
            verdict = "ok" if (spaced(n) in ans and not nf) else ("notfound" if nf else "WRONG")
        out["B"].append({"q": q, "lang": lang, "verdict": verdict, "answer": ans.split("\n")[0][:140]})
    print("@@" + json.dumps(out, ensure_ascii=False))


def main() -> int:
    if "--child" in sys.argv:
        run_one()
        return 0
    res = {}
    for flag in ("0", "1"):
        env = {**os.environ, "RAG_ENABLED": flag, "LLM_ENABLED": "0", "PYTHONIOENCODING": "utf-8"}
        p = subprocess.run([sys.executable, __file__, "--child"], env=env, cwd=ROOT,
                           capture_output=True, text=True, encoding="utf-8")
        line = next((ln for ln in p.stdout.splitlines() if ln.startswith("@@")), None)
        if not line:
            print(p.stdout[-1500:], p.stderr[-1500:])
            return 2
        res[flag] = json.loads(line[2:])
    for flag, r in res.items():
        a_ok = sum(x["ok"] for x in r["A"])
        v = [x["verdict"] for x in r["B"]]
        print(f"RAG={flag}: regression {a_ok}/{len(r['A'])} | typo set ok={v.count('ok')} "
              f"notfound={v.count('notfound')} WRONG={v.count('WRONG')} of {len(v)}")
    print("\nTypo set detail (off -> on):")
    for off, on in zip(res["0"]["B"], res["1"]["B"]):
        print(f"- {off['verdict']:8s} -> {on['verdict']:8s} {off['q']}")
        if on["verdict"] != "ok":
            print(f"    on: {on['answer']}")
    bad = [x for x in res["1"]["A"] if not x["ok"]]
    return 1 if bad or any(x["verdict"] == "WRONG" for x in res["1"]["B"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())

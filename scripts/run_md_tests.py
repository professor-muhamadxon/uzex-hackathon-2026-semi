"""Run the questions of a test markdown file (docs/opencode_tests.md format) through the agent.

For every table row  | **A1** | question | lang | expected | status |  the bold values (**...**) of
'expected' must appear in the answer (digits compared without spaces/separators, names case-insensitive).
Rows without bold values: G* must be 'not found', F5 must be a forecast with a warning.

    python scripts/run_md_tests.py [docs/opencode_tests.md] [-v]
"""
from __future__ import annotations
import re, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
from app.agent import Agent  # noqa: E402
from eval import is_not_found  # noqa: E402

ROW = re.compile(r"^\|\s*\*\*([A-Z]\d+)\*\*\s*\|\s*(.+?)\s*\|\s*([\w-]+)\s*\|\s*(.+?)\s*\|\s*[✅❌]")

def digits(s: str) -> str:
    return re.sub(r"\D", "", s)

def check(tid: str, expected: str, answer: str) -> tuple[bool, str]:
    bolds = re.findall(r"\*\*(.+?)\*\*", expected)
    if tid == "F5":
        low = answer.lower()
        ok = any(w in low for w in ("taxmin", "прогноз", "statistik", "bashorat")) and any(
            w in low for w in ("berilmagan", "ma’lumot", "данные", "не предоставлен"))
        return ok, "forecast+warning"
    if tid.startswith("G"):
        return is_not_found(answer), "not found"
    if not bolds:
        return False, "no expectation"
    missing = []
    for b in bolds:
        d = digits(b)
        if d and re.search(r"\d", b):
            # decimal tails may be rounded differently: compare the integer part too
            whole = digits(re.split(r"[.,]\d+$", b)[0]) if re.search(r"[.,]\d+$", b) else d
            if d not in digits(answer) and whole not in digits(answer):
                missing.append(b)
        elif b.lower() not in answer.lower():
            missing.append(b)
    return not missing, "missing: " + ", ".join(missing) if missing else "ok"

def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    verbose = "-v" in sys.argv
    path = Path(args[0]) if args else ROOT / "docs" / "opencode_tests.md"
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        m = ROW.match(line)
        if m:
            rows.append(m.groups())
    agent = Agent(llm_enabled=False)
    agent.ask("2025-yilda jami savdo summasi qancha?")
    passed = 0; total_t = 0.0; fails = []
    for tid, q, lang, expected in rows:
        q = q.replace("\\|", "|")
        t = time.perf_counter(); resp = agent.ask(q); dt = time.perf_counter() - t; total_t += dt
        ok, why = check(tid, expected, resp.answer)
        passed += ok
        if verbose or not ok:
            print(f"[{tid}] {'OK  ' if ok else 'FAIL'} {dt:.2f}s {q}")
            if not ok:
                print("     expected:", expected[:200].replace("<br>", " | "))
                print("     reason  :", why)
                print("     answer  :", resp.answer.split("\n\n")[0][:300].replace("\n", " | "))
        if not ok: fails.append(tid)
    print(f"\n{passed}/{len(rows)} passed; total {total_t:.1f}s; failed: {', '.join(fails) or '-'}")
    return 0 if passed == len(rows) else 1

if __name__ == "__main__":
    raise SystemExit(main())

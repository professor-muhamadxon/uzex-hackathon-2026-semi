"""Compare local Ollama models on the semantic classifier (intent only).

Reference intent = what the rule parser decides for the eval questions; plus
off-topic questions that must be 'unsupported'.   python scripts/model_bench.py qwen3:4b tev1:4b
"""
from __future__ import annotations
import json, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app import semantic, llm
from app.parser import parse_question

OFF = ["Какая погода завтра в Ташкенте?", "Bugun ob-havo qanday?", "Расскажи анекдот",
       "Sotuvchilarning foyda marjasi qancha?", "Какая маржа у брокеров?", "Qachon yetkazib berish tugaydi?"]
MAP = {"total", "top", "breakdown", "usd_rate"}

def main(models):
    qs = [(x["q"], None) for x in json.load(open(ROOT / "scripts/eval_set.json", encoding="utf8"))]
    ref = []
    for q, _ in qs:
        p = parse_question(q)
        ref.append((q, p.intent if p.intent in MAP else None))
    ref = [r for r in ref if r[1]] + [(q, "unsupported") for q in OFF]
    for m in models:
        semantic.LLM_MODEL = m
        llm.LLM_MODEL = m
        ok = bad = none = 0; times = []; fails = []
        for q, want in ref:
            t = time.time(); raw = semantic._call(q); times.append(time.time() - t)
            form = semantic.validate(raw)
            if form is None: none += 1; fails.append((q, want, None)); continue
            if form["intent"] == want: ok += 1
            else: bad += 1; fails.append((q, want, form["intent"]))
        times.sort()
        print(f"{m}: n={len(ref)} ok={ok} wrong={bad} unusable={none} median={times[len(times)//2]:.1f}s p90={times[int(len(times)*.9)]:.1f}s")
        for f in fails[:6]: print("   ", f)

if __name__ == "__main__":
    main(sys.argv[1:] or ["qwen3:4b", "tev1:4b"])

"""Append-only Q/A log (logs/qa.jsonl) shared by the bot and the web API."""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime
from pathlib import Path

from .config import ROOT

LOG_PATH = ROOT / "logs" / "qa.jsonl"
_lock = threading.Lock()


def ask_logged(question: str, channel: str, user: str | int | None = None):
    """Run the agent, time it and log the exchange. Returns (response, seconds)."""
    from .agent import get_agent

    started = time.perf_counter()
    response = get_agent().ask(question)
    elapsed = time.perf_counter() - started
    record = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "channel": channel,
        "user": user,
        "question": question,
        "lang": response.lang,
        "intent": response.intent,
        "used_llm": response.used_llm,
        "unverified": response.unverified,
        "seconds": round(elapsed, 3),
        "sql": response.sql,
        "filters": response.filters,
        "answer": response.answer,
    }
    try:
        Path(LOG_PATH).parent.mkdir(parents=True, exist_ok=True)
        with _lock, open(LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    except OSError:
        pass
    return response, elapsed

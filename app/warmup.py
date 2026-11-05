"""Warm everything up once at start so the first real question is as fast as the next ones.

* the local LLM is loaded into memory and pinned there (Ollama ``keep_alive``), then one real
  classification request primes its prompt cache;
* the product / company / region catalog, the DuckDB connection and the RAG index are built.

Runs in a background thread: the bot / web app start answering immediately, and a failure here only
costs speed (it is logged and ignored).
"""

from __future__ import annotations

import json
import logging
import threading
import time
import urllib.request

from .config import LLM_BASE_URL, LLM_ENABLED, LLM_MODEL, RAG_ENABLED

log = logging.getLogger(__name__)
KEEP_ALIVE = "24h"


def _ollama_native_url() -> str:
    base = LLM_BASE_URL.rstrip("/")
    return (base[:-3] if base.endswith("/v1") else base) + "/api/generate"


def pin_model() -> bool:
    """Load the model into memory and keep it there (empty prompt = load only)."""
    body = json.dumps({"model": LLM_MODEL, "prompt": "", "keep_alive": KEEP_ALIVE, "stream": False}).encode()
    request = urllib.request.Request(_ollama_native_url(), body, {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            response.read()
        return True
    except Exception as exc:  # noqa: BLE001 - not an Ollama endpoint / model missing: LLM stays optional
        log.warning("warmup: could not pin model %s: %s", LLM_MODEL, exc)
        return False


def warm_all() -> None:
    started = time.perf_counter()
    steps: list[str] = []
    try:
        from .agent import get_agent

        get_agent().ask("2025-yilda jami savdo summasi qancha?")  # catalog, DuckDB, parser
        steps.append("catalog")
        if RAG_ENABLED:
            from . import rag

            rag.warm()
            steps.append("rag")
        if LLM_ENABLED and pin_model():
            steps.append("llm-loaded")
            from . import semantic

            semantic._call("Qaysi tovar eng ko'p sotilgan?")  # primes the classification prompt
            steps.append("llm-primed")
    except Exception:  # noqa: BLE001 - warm-up must never stop the app
        log.exception("warmup failed")
    log.info("warmup: %s in %.1fs", ", ".join(steps) or "nothing", time.perf_counter() - started)


def start_in_background() -> threading.Thread:
    thread = threading.Thread(target=warm_all, name="warmup", daemon=True)
    thread.start()
    return thread

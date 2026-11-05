"""Application configuration (loaded from environment / .env)."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def _path(name: str, default: Path) -> Path:
    value = os.getenv(name)
    return Path(value).expanduser().resolve() if value else default


DATA_DIR = _path("DATA_DIR", ROOT / "data" / "uzex_spot_data")
DB_PATH = _path("DB_PATH", ROOT / "data" / "uzex.duckdb")

LLM_ENABLED = os.getenv("LLM_ENABLED", "1").strip().lower() not in {"0", "false", "no", "off"}
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:11434/v1").strip()
LLM_API_KEY = os.getenv("LLM_API_KEY", "ollama").strip()
LLM_MODEL = os.getenv("LLM_MODEL", "qwen2.5-coder:7b").strip()
LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "20"))
# Thinking models (qwen3) may spend the whole max_tokens budget on reasoning and
# return empty content. "none" disables that (Ollama/OpenAI-compatible extension);
# leave empty for cloud endpoints that do not support it.
LLM_REASONING_EFFORT = os.getenv("LLM_REASONING_EFFORT", "").strip()
SQL_TIMEOUT = float(os.getenv("SQL_TIMEOUT", "10"))

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()

# --- Monitoring relay: copy every incoming question to a second Telegram chat ---
# Telegram never delivers a bot's messages to another bot, so the second bot is used
# only as the sender: its token posts a copy into a chat your team watches.
# Empty RELAY_CHAT_ID disables the whole feature.
RELAY_CHAT_ID = os.getenv("RELAY_CHAT_ID", "").strip()
RELAY_BOT_TOKEN = os.getenv("RELAY_BOT_TOKEN", "").strip() or TELEGRAM_BOT_TOKEN
RELAY_ENABLED = (
    os.getenv("RELAY_ENABLED", "1").strip().lower() not in {"0", "false", "no", "off"}
    and bool(RELAY_CHAT_ID)
    and bool(RELAY_BOT_TOKEN)
)
RELAY_ANSWERS = os.getenv("RELAY_ANSWERS", "1").strip().lower() not in {"0", "false", "no", "off"}
RELAY_SQL = os.getenv("RELAY_SQL", "0").strip().lower() in {"1", "true", "yes", "on"}
RELAY_THREAD_ID = os.getenv("RELAY_THREAD_ID", "").strip()

MAX_RESULT_ROWS = int(os.getenv("MAX_RESULT_ROWS", "200"))

# LLM may write SQL only when explicitly enabled; by default it only classifies meaning (app/semantic.py)
RAG_ENABLED = os.getenv("RAG_ENABLED", "0").strip().lower() in {"1", "true", "yes", "on"}
LLM_SQL =os.getenv("LLM_SQL", "0").strip().lower() in {"1", "true", "yes", "on"}

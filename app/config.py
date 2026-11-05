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
SQL_TIMEOUT = float(os.getenv("SQL_TIMEOUT", "10"))

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()

MAX_RESULT_ROWS = int(os.getenv("MAX_RESULT_ROWS", "200"))

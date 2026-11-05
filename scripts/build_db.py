"""Build the DuckDB database from CSV files."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.etl import build  # noqa: E402


if __name__ == "__main__":
    build()

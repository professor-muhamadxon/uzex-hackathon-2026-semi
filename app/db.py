"""Thin DuckDB access layer."""

from __future__ import annotations

import threading
from typing import Any

import duckdb

from .config import DB_PATH, SQL_TIMEOUT


def connect(read_only: bool = True) -> duckdb.DuckDBPyConnection:
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"DuckDB bazasi topilmadi: {DB_PATH}\n"
            "Avval `python scripts/build_db.py` buyrug'ini bajaring."
        )
    con = duckdb.connect(str(DB_PATH), read_only=read_only)
    if read_only:
        # LLM-generated SQL must not be able to read arbitrary files.
        con.execute("SET enable_external_access=false")
    return con


def fetch_dicts(
    sql: str, params: list[Any] | None = None, timeout: float = SQL_TIMEOUT
) -> list[dict[str, Any]]:
    con = connect(read_only=True)
    timer = threading.Timer(timeout, con.interrupt)
    timer.start()
    try:
        cur = con.execute(sql, params or [])
        columns = [item[0] for item in cur.description]
        rows = cur.fetchall()
        return [dict(zip(columns, row)) for row in rows]
    finally:
        timer.cancel()
        con.close()


def fetch_one(sql: str, params: list[Any] | None = None) -> dict[str, Any] | None:
    rows = fetch_dicts(sql, params)
    return rows[0] if rows else None


def table_exists(name: str) -> bool:
    con = connect(read_only=True)
    try:
        return bool(
            con.execute(
                "SELECT count(*) FROM information_schema.tables WHERE table_name = ?", [name]
            ).fetchone()[0]
        )
    finally:
        con.close()

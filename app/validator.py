"""SQL validation and safe execution for LLM-generated queries."""

from __future__ import annotations

import re
from typing import Any

import sqlglot
from sqlglot import exp

from .config import MAX_RESULT_ROWS
from .db import fetch_dicts

ALLOWED_TABLES = {
    "deals_enriched",
    "contracts_full",
    "deals",
    "contracts",
    "participants",
    "brokers",
    "usd_rates",
    "region_map",
}

FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|TRUNCATE|MERGE|ATTACH|DETACH|"
    r"PRAGMA|COPY|EXPORT|IMPORT|CALL|INSTALL|LOAD|VACUUM|REPLACE)\b",
    re.IGNORECASE,
)

# File/network-reading table functions are never needed by the agent.
FORBIDDEN_FUNCTIONS = re.compile(
    r"\b(read_csv|read_csv_auto|read_parquet|read_json|read_json_auto|"
    r"parquet_scan|csv_scan|json_scan|sqlite_scan|postgres_scan|mysql_scan|"
    r"glob|getenv)\s*\(",
    re.IGNORECASE,
)


class SQLValidationError(ValueError):
    pass


def _clean_sql(sql: str) -> str:
    sql = sql.strip()
    if sql.startswith("```"):
        sql = re.sub(r"^```[a-zA-Z]*\n?", "", sql)
        sql = re.sub(r"\n?```$", "", sql)
    sql = sql.strip().rstrip(";").strip()
    return sql


def validate_sql(sql: str) -> str:
    sql = _clean_sql(sql)
    if not sql:
        raise SQLValidationError("empty SQL")
    if FORBIDDEN.search(sql):
        raise SQLValidationError("forbidden statement")
    if FORBIDDEN_FUNCTIONS.search(sql):
        raise SQLValidationError("forbidden function")
    if sql.count(";") > 0:
        raise SQLValidationError("multiple statements are not allowed")

    try:
        tree = sqlglot.parse_one(sql, read="duckdb")
    except Exception as exc:
        raise SQLValidationError(f"SQL parse error: {exc}") from exc

    if not isinstance(tree, (exp.Select, exp.Union, exp.With)):
        raise SQLValidationError("only SELECT queries are allowed")

    for table in tree.find_all(exp.Table):
        name = table.name
        if not name:
            continue
        if name.lower() not in ALLOWED_TABLES:
            raise SQLValidationError(f"table not allowed: {name}")

    if re.search(r"\b(information_schema|duckdb_\w+|sqlite_\w+)\b", sql, re.IGNORECASE):
        raise SQLValidationError("system tables are not allowed")

    return sql


def execute_sql(sql: str, limit: int = MAX_RESULT_ROWS) -> list[dict[str, Any]]:
    sql = validate_sql(sql)
    wrapped = f"SELECT * FROM ({sql}) AS _agent_query LIMIT {int(limit)}"
    fetch_dicts(f"EXPLAIN {wrapped}")  # cheap planner check before running
    return fetch_dicts(wrapped)


# ---------------------------------------------------------------------------
# Answer guard: every number in the answer must come from SQL results / filters
# ---------------------------------------------------------------------------

from datetime import date as _date, datetime as _datetime, time as _time  # noqa: E402
from decimal import Decimal as _Decimal  # noqa: E402

_DATE_RE = re.compile(r"\b\d{2}\.\d{2}\.\d{4}\b")
_TIME_RE = re.compile(r"\b\d{2}:\d{2}(?::\d{2})?\b")
_NUM_RE = re.compile(r"(?<![\w.])\d{1,3}(?:[  ]\d{3})+(?:\.\d+)?(?![\w])|(?<![\w.])\d+(?:\.\d+)?(?![\w])")


def _walk(value: Any, nums: set[float], texts: set[str]) -> None:
    if value is None or isinstance(value, bool):
        return
    if isinstance(value, (int, float, _Decimal)):
        nums.add(float(value))
        nums.add(abs(float(value)))
    elif isinstance(value, _time):
        texts.add(value.strftime("%H:%M:%S"))
        texts.add(value.strftime("%H:%M"))
    elif isinstance(value, (_date, _datetime)):
        texts.add(value.strftime("%d.%m.%Y"))
    elif isinstance(value, str):
        texts.add(value)
        for token in re.findall(r"\d+(?:\.\d+)?", value):
            nums.add(float(token))
    elif isinstance(value, dict):
        for item in value.values():
            _walk(item, nums, texts)
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            _walk(item, nums, texts)
    elif hasattr(value, "__dict__"):
        _walk(vars(value), nums, texts)


def unverified_numbers(answer: str, sources: list[Any], small_ok: int = 20) -> list[str]:
    """Return numbers in `answer` that are not backed by `sources` (rows, meta, filters).

    Small integers (list enumeration, "Top 5") are allowed. Values match when equal
    after rounding to the displayed precision.
    """
    nums: set[float] = set()
    texts: set[str] = set()
    for source in sources:
        _walk(source, nums, texts)
    joined = " ".join(texts)
    bad: list[str] = []
    body = answer
    for d in _DATE_RE.findall(answer):
        if d not in joined:
            bad.append(d)
    body = _DATE_RE.sub(" ", body)
    for t in _TIME_RE.findall(body):
        if t not in joined:
            bad.append(t)
    body = _TIME_RE.sub(" ", body)
    for token in _NUM_RE.findall(body):
        raw = token.replace(" ", "").replace(" ", "")
        try:
            value = float(raw)
        except ValueError:
            continue
        if value.is_integer() and 0 <= value <= small_ok:
            continue
        decimals = len(raw.split(".")[1]) if "." in raw else 0
        ok = any(abs(round(n, decimals) - value) <= 0.011 for n in nums)
        if not ok and decimals == 0:
            ok = any(abs(n - value) < 1 for n in nums)  # integer display of a decimal
        if not ok:
            bad.append(token)
    return bad

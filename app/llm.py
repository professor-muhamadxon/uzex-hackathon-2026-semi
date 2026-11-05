"""Optional LLM fallback: natural language -> DuckDB SQL."""

from __future__ import annotations

import re
import threading

from openai import OpenAI

from .config import (
    LLM_API_KEY,
    LLM_BASE_URL,
    LLM_ENABLED,
    LLM_MODEL,
    LLM_REASONING_EFFORT,
    LLM_TIMEOUT,
)

_client: OpenAI | None = None
_SEMAPHORE = threading.BoundedSemaphore(4)  # at most 4 concurrent LLM calls

SCHEMA = """
Tables (DuckDB):

deals_enriched(
  deal_id BIGINT, deal_date DATE, deal_time TIME, trade_type VARCHAR,
  quantity DECIMAL, amount DECIMAL, start_price DECIMAL, contract_id BIGINT,
  product_name VARCHAR, lot DECIMAL, unit VARCHAR, region_uz VARCHAR,
  contract_type VARCHAR, contract_form VARCHAR, status VARCHAR,
  seller_inn VARCHAR, buyer_inn VARCHAR, seller_broker VARCHAR, buyer_broker VARCHAR,
  payment_date DATE, delivery_date DATE, delivered_quantity DECIMAL,
  currency VARCHAR, category VARCHAR, group_name VARCHAR, industry VARCHAR,
  tnved_code VARCHAR, region_ru VARCHAR, base_price DECIMAL,
  payment_term_days INTEGER, delivery_term_days INTEGER,
  contract_product_name VARCHAR,
  volume DECIMAL,            -- quantity * lot
  unit_price DECIMAL,        -- amount / volume, in contract currency
  amount_uzs DECIMAL,        -- amount converted to UZS at deal date
  usd_rate DECIMAL
)

contracts_full(
  contract_id BIGINT, product_name VARCHAR, brand VARCHAR, size VARCHAR,
  grade VARCHAR, type VARCHAR, class VARCHAR, tnved_code VARCHAR,
  group_name VARCHAR, category VARCHAR, industry VARCHAR, unit VARCHAR,
  lot DECIMAL, currency VARCHAR, base_price DECIMAL, deposit_pct DECIMAL,
  delivery_basis VARCHAR, region_ru VARCHAR, warehouse_address VARCHAR,
  trade_type VARCHAR, contract_type VARCHAR, contract_form VARCHAR,
  payment_term_days INTEGER, delivery_term_days INTEGER, packaging VARCHAR,
  seller_inn VARCHAR, registration_date DATE, valid_until DATE,
  seller_name VARCHAR, seller_activity VARCHAR, seller_region VARCHAR, region_uz VARCHAR
)

participants(inn VARCHAR, name VARCHAR, region VARCHAR, activity VARCHAR, role VARCHAR, vat_payer VARCHAR)
brokers(broker_code VARCHAR, name VARCHAR, inn VARCHAR, region VARCHAR)
usd_rates(rate_date DATE, rate DECIMAL)
region_map(region_ru VARCHAR, region_uz VARCHAR)

Key values:
  status: 'Новый','Не подписан','Заключен','Ждёт оплату','Оплачен','Исполнен','Исполнен(Частично)','Аннулирован(Не оплачен)'
  contract_type: 'Внутренний','Экспортный'
  contract_form: 'Спот','Форвард','Фьючерс'
  trade_type: 'Английский аукцион','Обратный аукцион','Двусторонний аукцион'
  currency: 'Узбекский сум','Доллар США'

Synonyms (RU / UZ -> column):
  сумма / summa / qiymat -> amount_uzs (UZS) or amount (contract currency)
  количество сделок / bitimlar soni -> COUNT(*)
  объём / hajm / miqdor -> volume (+ unit);  цена / narx -> unit_price
  продавец / sotuvchi -> seller_inn;  покупатель / xaridor -> buyer_inn (join participants.inn for names)
  брокер / broker -> seller_broker, buyer_broker (join brokers.broker_code)
  регион / viloyat -> region_uz;  товар / tovar -> contract_product_name, tnved_code
  экспорт / eksport -> contract_type = 'Экспортный'

Status dictionary:
  исполненные / ijro etilgan -> status IN ('Исполнен','Исполнен(Частично)')
  оплаченные / to'langan -> status IN ('Оплачен','Исполнен','Исполнен(Частично)')
  аннулированные / bekor qilingan -> status = 'Аннулирован(Не оплачен)'
  Default for sums/volumes/prices: status <> 'Аннулирован(Не оплачен)'; counts: all statuses.

The data ends on 2026-10-30: "today" = DATE '2026-10-30', "last year" = 2025,
"last month" = September 2026. Data starts 2022-01-03.

Rules:
  - Only one SELECT statement. Never use INSERT/UPDATE/DELETE/DDL.
  - Use deals_enriched for deal questions; use amount_uzs for UZS totals.
  - amount is in the contract currency (USD for export deals). Use amount for USD totals.
  - For period filters: EXTRACT(year FROM deal_date) = 2025, EXTRACT(month FROM deal_date) = 3.
  - For product filters use tnved_code (e.g. cotton 520100, wheat 100199, flour 110100,
    cement 252329, polyethylene 390120, polypropylene 390210, petrol 271012,
    diesel 271019, sugar 170199).
  - Region filter uses region_uz (Uzbek names, e.g. 'Namangan viloyati', 'Toshkent shahri').
  - Volume is quantity * lot. Do not sum volume across different units unless GROUP BY unit.
  - Never invent data. If the question is not answerable from the schema, return
    SELECT 'not_found' AS error. Goods that are not in the registry (gold, coal, computers ...)
    and indicators that do not exist (margin, profit) are "not_found", not an empty result.
  - Several goods / regions in one question: ONE ROW PER ENTITY (GROUP BY tnved_code / region_uz,
    year), never one merged total. Show the entity and the year in the output columns.
  - Growth rate = (this - previous) / previous * 100, ROUND(..., 2). Use LAG() OVER (PARTITION BY
    entity ORDER BY year). Average annual growth (CAGR) = (last/first)^(1.0/years) - 1 over full years.
  - The data covers 2022-01-03 .. 2026-10-30: 2022 .. 2025 are full years, 2026 has only 10 months.
    Never compare a partial year with a full year; compare the same months (Jan-Oct) or say so.
    "Last 5 years" is not fully available (4 years 10 months): use all data and keep that visible.
  - Sums and prices exclude annulled deals: SUM(amount_uzs) FILTER (WHERE status <> 'Аннулирован(Не оплачен)').
  - Column aliases must be short and readable (year, product, total_uzs, deals, growth_pct).
  - Seasonality: cotton is sold mostly in autumn, so month-by-month and partial-year comparisons mislead.
"""

FEW_SHOT = """
UZ: 2025-yilda jami savdo summasi qancha?
SQL: SELECT SUM(amount_uzs) AS total_uzs, COUNT(*) AS deals FROM deals_enriched WHERE EXTRACT(year FROM deal_date) = 2025

RU: Топ-5 компаний по сумме сделок в 2024 году
SQL: SELECT seller_inn AS code, SUM(amount_uzs) AS total_uzs, COUNT(*) AS deals FROM deals_enriched WHERE EXTRACT(year FROM deal_date) = 2024 GROUP BY seller_inn ORDER BY total_uzs DESC LIMIT 5

RU: Сколько тонн пшеницы продано в 2023 году?
SQL: SELECT unit, SUM(volume) AS volume, COUNT(*) AS deals FROM deals_enriched WHERE tnved_code = '100199' AND EXTRACT(year FROM deal_date) = 2023 GROUP BY unit

RU: Экспорт в 2025 году в долларах
SQL: SELECT SUM(amount) AS total_usd, COUNT(*) AS deals FROM deals_enriched WHERE contract_type = 'Экспортный' AND EXTRACT(year FROM deal_date) = 2025

UZ: Benzin va paxta savdo summasi yillar bo'yicha qanday o'sgan (har biri alohida, o'sish foizi bilan)?
SQL: WITH y AS (SELECT tnved_code, any_value(contract_product_name) AS product, EXTRACT(year FROM deal_date) AS year, SUM(amount_uzs) FILTER (WHERE status <> 'Аннулирован(Не оплачен)') AS total_uzs FROM deals_enriched WHERE tnved_code IN ('271012','520100') GROUP BY tnved_code, EXTRACT(year FROM deal_date)) SELECT product, year, total_uzs, ROUND(100.0 * (total_uzs - LAG(total_uzs) OVER (PARTITION BY tnved_code ORDER BY year)) / LAG(total_uzs) OVER (PARTITION BY tnved_code ORDER BY year), 2) AS growth_pct FROM y ORDER BY tnved_code, year

RU: Среднегодовой темп роста оборота по цементу и пшенице за полные годы 2022-2025
SQL: WITH y AS (SELECT tnved_code, any_value(contract_product_name) AS product, EXTRACT(year FROM deal_date) AS year, SUM(amount_uzs) FILTER (WHERE status <> 'Аннулирован(Не оплачен)') AS total_uzs FROM deals_enriched WHERE tnved_code IN ('252329','100199') AND EXTRACT(year FROM deal_date) BETWEEN 2022 AND 2025 GROUP BY tnved_code, EXTRACT(year FROM deal_date)) SELECT product, ROUND(100.0 * (POWER(MAX(total_uzs) FILTER (WHERE year = 2025) / MAX(total_uzs) FILTER (WHERE year = 2022), 1.0 / 3) - 1), 2) AS cagr_pct FROM y GROUP BY tnved_code, product

UZ: 2026-yil yanvar-oktabr oylarini 2025-yilning shu oylari bilan solishtiring (paxta)
SQL: SELECT EXTRACT(year FROM deal_date) AS year, SUM(amount_uzs) FILTER (WHERE status <> 'Аннулирован(Не оплачен)') AS total_uzs FROM deals_enriched WHERE tnved_code = '520100' AND EXTRACT(month FROM deal_date) <= 10 AND EXTRACT(year FROM deal_date) IN (2025, 2026) GROUP BY 1 ORDER BY 1

UZ: Oltin narxi qanday o'zgargan?
SQL: SELECT 'not_found' AS error
"""


def _client_instance() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            base_url=LLM_BASE_URL,
            api_key=LLM_API_KEY or "local",
            timeout=LLM_TIMEOUT,
            max_retries=0,
        )
    return _client


def _reasoning_kwargs() -> dict:
    """Stop thinking models from spending the token budget on reasoning.

    Ollama's OpenAI-compatible endpoint accepts ``reasoning_effort="none"``; without
    it qwen3-style models return empty content and the call looks like a timeout.
    Cloud endpoints that do not support the field are left untouched.
    """
    return {"reasoning_effort": LLM_REASONING_EFFORT} if LLM_REASONING_EFFORT else {}


def _extract_sql(text: str) -> str | None:
    if not text:
        return None
    match = re.search(r"```(?:sql)?\s*(.*?)```", text, re.IGNORECASE | re.DOTALL)
    if match:
        candidate = match.group(1)
    else:
        candidate = text
    candidate = candidate.strip().strip("`").strip()
    if candidate.lower().startswith(("select", "with")):
        return candidate.rstrip(";").strip()
    match = re.search(r"(SELECT|WITH)\b.*", candidate, re.IGNORECASE | re.DOTALL)
    if match:
        return match.group(0).rstrip(";").strip()
    return None


def sql_hints(parsed) -> str:
    """Filters the rule parser already resolved (product codes, regions, period); the LLM must reuse them."""
    lines: list[str] = []
    product = getattr(parsed, "product", None)
    if product is not None and product.tnveds:
        codes = ", ".join(f"'{code}'" for code in product.tnveds)
        lines.append(f"- tnved_code IN ({codes})  -- goods named in the question; one row per code")
    if product is not None and product.categories:
        cats = ", ".join("'" + c.replace("'", "''") + "'" for c in product.categories)
        lines.append(f"- category IN ({cats})")
    if getattr(parsed, "regions", None):
        regions = ", ".join("'" + r.replace("'", "''") + "'" for r in parsed.regions)
        lines.append(f"- region_uz IN ({regions})")
    if getattr(parsed, "date_from", None) and getattr(parsed, "date_to", None):
        lines.append(f"- deal_date BETWEEN DATE '{parsed.date_from}' AND DATE '{parsed.date_to}'")
    elif getattr(parsed, "year_from", None):
        lines.append(f"- year(s) {parsed.year_from}..{parsed.year_to or parsed.year_from}")
    return "\n".join(lines)


import os as _os

THINK_SQL = _os.getenv("LLM_SQL_THINK", "0").strip().lower() in {"1", "true", "yes"}


def _ollama_chat_sql(system: str, user: str) -> str | None:
    """Ollama native chat: thinking off and the reply forced into {"sql": "..."} (no free-form reasoning)."""
    import json
    import urllib.request

    base = LLM_BASE_URL.rstrip("/")
    url = (base[:-3] if base.endswith("/v1") else base) + "/api/chat"
    body = {
        "model": LLM_MODEL,
        "stream": False,
        "think": THINK_SQL,
        "format": {"type": "object", "properties": {"sql": {"type": "string"}}, "required": ["sql"]},
        "options": {"temperature": 0, "num_predict": 4000 if THINK_SQL else 1000, "num_ctx": 8192},
        "keep_alive": "24h",
        "messages": [
            {"role": "system", "content": system + "\n\nReply as JSON: {\"sql\": \"<one DuckDB SELECT statement>\"}."},
            {"role": "user", "content": user},
        ],
    }
    request = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json"})
    try:
        with _SEMAPHORE:
            with urllib.request.urlopen(request, timeout=LLM_TIMEOUT) as response:
                data = json.loads(response.read().decode("utf-8"))
        sql = json.loads(data["message"]["content"]).get("sql", "")
        return _extract_sql(sql) if isinstance(sql, str) and sql.strip() else None
    except Exception:  # noqa: BLE001 - not Ollama / model missing: caller falls back to the OpenAI route
        return None


def generate_sql(question: str, lang: str, previous_error: str | None = None, hints: str = "") -> str | None:
    """Ask the LLM for a SQL query. Returns None if the LLM is unavailable."""
    if not LLM_ENABLED:
        return None
    system = (
        "You are a DuckDB SQL generator for a commodity exchange registry. "
        "Return ONLY one SQL SELECT statement, no explanations. "
        "Use exactly the tables and column names from the schema.\n\n"
        + SCHEMA
        + "\n\nExamples:\n"
        + FEW_SHOT
    )
    user = f"Question language: {lang}\nQuestion: {question}"
    if hints:
        user += f"\nResolved by the program (use exactly these filters):\n{hints}"
    if previous_error:
        user += f"\nThe previous SQL failed or was invalid. Error: {previous_error}\nFix it."

    native = _ollama_chat_sql(system, user)
    if native:
        return native
    try:
        with _SEMAPHORE:
            response = _client_instance().chat.completions.create(
                model=LLM_MODEL,
                temperature=0,
                max_tokens=900,
                **_reasoning_kwargs(),
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )
        return _extract_sql(response.choices[0].message.content or "")
    except Exception:
        return None

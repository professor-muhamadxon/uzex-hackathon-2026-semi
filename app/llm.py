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
    SELECT 'not_found' AS error.
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


def generate_sql(question: str, lang: str, previous_error: str | None = None) -> str | None:
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
    if previous_error:
        user += f"\nThe previous SQL failed or was invalid. Error: {previous_error}\nFix it."

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

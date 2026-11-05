"""Deterministic SQL templates for the most common question intents."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .db import fetch_dicts, fetch_one
from .extra import EXTRA_INTENTS, run_extra
from .parser import ParsedQuery


@dataclass
class QueryResult:
    intent: str
    rows: list[dict[str, Any]] = field(default_factory=list)
    sql: str = ""
    filters: str = ""
    sources: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)
    not_found: bool = False


def q(value: Any) -> str:
    """Quote a value for a generated SQL literal."""
    if value is None:
        return "NULL"
    text = str(value).replace("'", "''")
    return f"'{text}'"


def _date_literal(value) -> str:
    return f"DATE '{value.isoformat()}'"


def _product_condition(p: ParsedQuery) -> str | None:
    if p.product.tnveds:
        return "tnved_code IN (" + ", ".join(q(code) for code in p.product.tnveds) + ")"
    if p.product.categories:
        return "category IN (" + ", ".join(q(cat) for cat in p.product.categories) + ")"
    return None


ANNUL_STATUS = "Аннулирован(Не оплачен)"
SUM_INTENTS = {"total", "product_stats", "company_profile", "export_stats", "region_stats", "top", "broker_stats", "breakdown"}


def excludes_annulled(p: ParsedQuery) -> bool:
    """Default rule: sums/volumes/prices exclude annulled deals; deal counts include all."""
    return not p.statuses and p.metric != "count" and p.intent in SUM_INTENTS


def build_where(p: ParsedQuery, force_export: bool = False) -> str:
    conditions: list[str] = []

    if p.date_from or p.date_to:
        start = p.date_from or p.date_to
        end = p.date_to or p.date_from
        conditions.append(f"deal_date BETWEEN {_date_literal(start)} AND {_date_literal(end)}")
    else:
        if p.year_from:
            end_year = p.year_to or p.year_from
            conditions.append(f"EXTRACT(year FROM deal_date) BETWEEN {p.year_from} AND {end_year}")
        if p.month:
            conditions.append(f"EXTRACT(month FROM deal_date) = {p.month}")

    if p.statuses:
        conditions.append("status IN (" + ", ".join(q(st) for st in p.statuses) + ")")
    elif excludes_annulled(p):
        conditions.append(f"status <> {q(ANNUL_STATUS)}")
    if force_export:
        conditions.append(f"contract_type = {q('Экспортный')}")
    elif p.contract_type:
        conditions.append(f"contract_type = {q(p.contract_type)}")
    if p.contract_form:
        conditions.append(f"contract_form = {q(p.contract_form)}")
    if p.trade_type:
        conditions.append(f"trade_type = {q(p.trade_type)}")

    product_condition = _product_condition(p)
    if product_condition:
        conditions.append(f"({product_condition})")

    if p.regions:
        conditions.append("region_uz IN (" + ", ".join(q(region) for region in p.regions) + ")")

    if p.contract_id is not None:
        conditions.append(f"contract_id = {int(p.contract_id)}")
    if p.deal_id is not None:
        conditions.append(f"deal_id = {int(p.deal_id)}")

    if p.company:
        if p.company_role == "seller":
            conditions.append(f"seller_inn = {q(p.company.inn)}")
        elif p.company_role == "buyer":
            conditions.append(f"buyer_inn = {q(p.company.inn)}")
        else:
            conditions.append(f"(seller_inn = {q(p.company.inn)} OR buyer_inn = {q(p.company.inn)})")

    if p.broker:
        conditions.append(
            f"(seller_broker = {q(p.broker.code)} OR buyer_broker = {q(p.broker.code)})"
        )

    return " AND ".join(conditions) if conditions else "TRUE"


def filter_summary(p: ParsedQuery) -> str:
    uz = p.lang == "uz"
    parts: list[str] = []

    if p.date_from or p.date_to:
        start = p.date_from or p.date_to
        end = p.date_to or p.date_from
        parts.append(f"{start.strftime('%d.%m.%Y')} – {end.strftime('%d.%m.%Y')}")
    else:
        if p.year_from:
            if p.year_to and p.year_to != p.year_from:
                parts.append(f"{p.year_from}–{p.year_to}")
            else:
                parts.append(f"{p.year_from}-yil" if uz else f"{p.year_from} год")
        if p.month:
            month_names_uz = [
                "yanvar", "fevral", "mart", "aprel", "may", "iyun",
                "iyul", "avgust", "sentabr", "oktabr", "noyabr", "dekabr",
            ]
            month_names_ru = [
                "январь", "февраль", "март", "апрель", "май", "июнь",
                "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь",
            ]
            parts.append((month_names_uz if uz else month_names_ru)[p.month - 1])

    if p.product.label:
        parts.append(("tovar: " if uz else "товар: ") + p.product.label)
    if p.regions:
        parts.append(("region (sotuvchi ombori): " if uz else "регион (склад продавца): ") + ", ".join(p.regions))
    if p.company:
        parts.append(("kompaniya: " if uz else "компания: ") + p.company.name)
    if p.broker:
        parts.append(("broker: " if uz else "брокер: ") + f"{p.broker.code} {p.broker.name}")
    if p.status:
        parts.append(("holat: " if uz else "статус: ") + p.status)
    if p.contract_type:
        parts.append(("turi: " if uz else "тип: ") + p.contract_type)
    if p.contract_form:
        parts.append(("forma: " if uz else "форма: ") + p.contract_form)
    if p.trade_type:
        parts.append(("savdo: " if uz else "торги: ") + p.trade_type)
    if p.contract_id:
        parts.append(("kontrakt: " if uz else "контракт: ") + str(p.contract_id))
    if p.deal_id:
        parts.append((("bitim: " if uz else "сделка: ")) + str(p.deal_id))

    if excludes_annulled(p):
        parts.append("annul qilinganlar hisobga olinmagan" if uz else "без аннулированных")
    elif not p.statuses and p.intent in SUM_INTENTS:
        parts.append("barcha holatlar, annul qilinganlar ham" if uz else "все статусы, включая аннулированные")

    if not parts:
        return "barcha ma’lumotlar" if uz else "все данные"
    return ", ".join(parts)


def _source_hint(p: ParsedQuery, limit: int = 3) -> list[str]:
    if p.deal_id:
        return [f"Bitim / Сделка: {p.deal_id}"]
    if p.contract_id:
        return [f"Kontrakt / Контракт: {p.contract_id}"]
    try:
        where = build_where(p)
        rows = fetch_dicts(
            f"""
            SELECT deal_id, contract_id
            FROM deals_enriched
            WHERE {where}
            ORDER BY deal_date DESC
            LIMIT {limit}
            """
        )
    except Exception:
        return []
    if not rows:
        return []
    deal_ids = [str(row["deal_id"]) for row in rows]
    contract_ids = sorted({str(row["contract_id"]) for row in rows})
    return [
        "Bitimlar / Сделки: " + ", ".join(deal_ids),
        "Kontraktlar / Контракты: " + ", ".join(contract_ids),
    ]


def _base_result(p: ParsedQuery, intent: str, rows: list[dict], sql: str, meta: dict | None = None) -> QueryResult:
    return QueryResult(
        intent=intent,
        rows=rows,
        sql=sql,
        filters=filter_summary(p),
        sources=_source_hint(p),
        meta=meta or {},
        not_found=not rows,
    )


# ---------------------------------------------------------------------------
# Intents
# ---------------------------------------------------------------------------

def total_query(p: ParsedQuery) -> QueryResult:
    where = build_where(p)
    if p.metric == "volume":
        sql = f"""
            SELECT unit, SUM(volume) AS value, COUNT(*) AS deals
            FROM deals_enriched
            WHERE {where}
            GROUP BY unit
            ORDER BY value DESC
        """
        rows = fetch_dicts(sql)
    elif p.metric == "avg_price":
        sql = f"""
            SELECT unit, currency, AVG(unit_price) AS value,
                   MIN(unit_price) AS min_price, MAX(unit_price) AS max_price,
                   COUNT(*) AS deals
            FROM deals_enriched
            WHERE {where}
            GROUP BY unit, currency
            ORDER BY deals DESC
        """
        rows = fetch_dicts(sql)
    else:
        sql = f"""
            SELECT COUNT(*) AS deals,
                   COUNT(DISTINCT contract_id) AS contracts,
                   SUM(amount_uzs) AS total_uzs,
                   SUM(CASE WHEN currency = 'Доллар США' THEN amount ELSE 0 END) AS export_usd,
                   SUM(CASE WHEN currency = 'Доллар США' THEN 1 ELSE 0 END) AS export_deals
            FROM deals_enriched
            WHERE {where}
        """
        rows = fetch_dicts(sql)
    return _base_result(p, "total", rows, sql)


def export_query(p: ParsedQuery) -> QueryResult:
    where = build_where(p, force_export=True)
    sql = f"""
        SELECT COUNT(*) AS deals,
               COUNT(DISTINCT contract_id) AS contracts,
               SUM(amount) AS total_usd,
               SUM(amount_uzs) AS total_uzs,
               COUNT(DISTINCT seller_inn) AS sellers,
               COUNT(DISTINCT buyer_inn) AS buyers
        FROM deals_enriched
        WHERE {where}
    """
    rows = fetch_dicts(sql)
    return _base_result(p, "export_stats", rows, sql)


def _value_expr(metric: str, alias: str = "d", distinct_deals: bool = False) -> str:
    count_expr = f"COUNT(DISTINCT {alias}.deal_id)" if distinct_deals else f"COUNT(*)"
    if metric == "count":
        return count_expr
    if metric == "volume":
        return f"SUM({alias}.volume)"
    if metric == "avg_price":
        return f"AVG({alias}.unit_price)"
    if metric == "usd":
        return f"SUM(CASE WHEN {alias}.currency = 'Доллар США' THEN {alias}.amount ELSE 0 END)"
    return f"SUM({alias}.amount_uzs)"


def top_query(p: ParsedQuery) -> QueryResult:
    where = build_where(p)
    direction = "ASC" if p.order_asc else "DESC"
    group = p.group or "company"
    metric = p.metric
    # Summing volume across different units is meaningless; fall back to money.
    if metric == "volume" and not (p.product.tnveds or p.product.categories):
        metric = "amount"
    meta = {"group": group, "metric": metric}

    if group == "company":
        if p.company_role in {"seller", "buyer"}:
            inn_col = "seller_inn" if p.company_role == "seller" else "buyer_inn"
            sql = f"""
                SELECT d.{inn_col} AS code, p.name AS label,
                       {_value_expr(metric, 'd')} AS value,
                       COUNT(DISTINCT d.deal_id) AS deals
                FROM deals_enriched d
                LEFT JOIN participants p ON p.inn = d.{inn_col}
                WHERE {where}
                GROUP BY d.{inn_col}, p.name
                ORDER BY value {direction} NULLS LAST
                LIMIT {p.top_n}
            """
        else:
            sql = f"""
                WITH sides AS (
                    SELECT seller_inn AS inn, amount_uzs, volume, unit_price, currency, deal_id
                    FROM deals_enriched WHERE {where}
                    UNION
                    SELECT buyer_inn AS inn, amount_uzs, volume, unit_price, currency, deal_id
                    FROM deals_enriched WHERE {where}
                )
                SELECT s.inn AS code, p.name AS label,
                       {_value_expr(metric, 's', distinct_deals=True)} AS value,
                       COUNT(DISTINCT s.deal_id) AS deals
                FROM sides s
                LEFT JOIN participants p ON p.inn = s.inn
                GROUP BY s.inn, p.name
                ORDER BY value {direction} NULLS LAST
                LIMIT {p.top_n}
            """
    elif group == "product":
        if metric == "volume":
            sql = f"""
                SELECT d.tnved_code AS code,
                       any_value(d.contract_product_name) AS label,
                       d.unit,
                       SUM(d.volume) AS value,
                       COUNT(*) AS deals
                FROM deals_enriched d
                WHERE {where}
                GROUP BY d.tnved_code, d.unit
                ORDER BY value {direction} NULLS LAST
                LIMIT {p.top_n}
            """
        else:
            sql = f"""
                SELECT d.tnved_code AS code,
                       any_value(d.contract_product_name) AS label,
                       {_value_expr(metric, 'd')} AS value,
                       COUNT(*) AS deals
                FROM deals_enriched d
                WHERE {where}
                GROUP BY d.tnved_code
                ORDER BY value {direction} NULLS LAST
                LIMIT {p.top_n}
            """
    elif group == "region":
        sql = f"""
            SELECT d.region_uz AS code, d.region_uz AS label,
                   {_value_expr(metric, 'd')} AS value,
                   COUNT(*) AS deals
            FROM deals_enriched d
            WHERE {where}
            GROUP BY d.region_uz
            ORDER BY value {direction} NULLS LAST
            LIMIT {p.top_n}
        """
    elif group == "broker":
        sql = f"""
            WITH sides AS (
                SELECT seller_broker AS broker_code, amount_uzs, volume, unit_price, currency, deal_id
                FROM deals_enriched WHERE {where}
                UNION
                SELECT buyer_broker AS broker_code, amount_uzs, volume, unit_price, currency, deal_id
                FROM deals_enriched WHERE {where}
            )
            SELECT s.broker_code AS code, b.name AS label,
                   {_value_expr(metric, 's', distinct_deals=True)} AS value,
                   COUNT(DISTINCT s.deal_id) AS deals
            FROM sides s
            LEFT JOIN brokers b ON b.broker_code = s.broker_code
            GROUP BY s.broker_code, b.name
            ORDER BY value {direction} NULLS LAST
            LIMIT {p.top_n}
        """
    else:
        sql = f"""
            SELECT {_value_expr(metric, 'd')} AS value, COUNT(*) AS deals
            FROM deals_enriched d
            WHERE {where}
        """
    rows = fetch_dicts(sql)
    if metric == "avg_price" and rows:
        # attach the unit/currency when the filtered deals share a single one
        uc = fetch_dicts(f"SELECT DISTINCT unit, currency FROM deals_enriched WHERE {where} LIMIT 3")
        if len(uc) == 1:
            for row in rows:
                row.setdefault("unit", uc[0]["unit"])
                row.setdefault("currency", uc[0]["currency"])
    return _base_result(p, "top", rows, sql, meta)


def company_profile_query(p: ParsedQuery) -> QueryResult:
    assert p.company is not None
    company = p.company
    where = build_where(p)
    where = where.replace(f"(seller_inn = {q(company.inn)} OR buyer_inn = {q(company.inn)})", "TRUE")

    role_parts: list[str] = []
    if p.company_role in {"seller", "both"}:
        role_parts.append(
            f"""
            SELECT 'seller' AS role, COUNT(*) AS deals,
                   SUM(amount_uzs) AS total_uzs,
                   COUNT(DISTINCT contract_id) AS contracts,
                   MIN(deal_date) AS first_date, MAX(deal_date) AS last_date
            FROM deals_enriched
            WHERE {where} AND seller_inn = {q(company.inn)}
            """
        )
    if p.company_role in {"buyer", "both"}:
        role_parts.append(
            f"""
            SELECT 'buyer' AS role, COUNT(*) AS deals,
                   SUM(amount_uzs) AS total_uzs,
                   COUNT(DISTINCT contract_id) AS contracts,
                   MIN(deal_date) AS first_date, MAX(deal_date) AS last_date
            FROM deals_enriched
            WHERE {where} AND buyer_inn = {q(company.inn)}
            """
        )
    sql = " UNION ALL ".join(role_parts)
    rows = fetch_dicts(sql)

    company_condition = (
        f"seller_inn = {q(company.inn)} OR buyer_inn = {q(company.inn)}"
    )
    if p.company_role == "seller":
        company_condition = f"seller_inn = {q(company.inn)}"
    elif p.company_role == "buyer":
        company_condition = f"buyer_inn = {q(company.inn)}"

    top_sql = f"""
        SELECT tnved_code AS code,
               any_value(contract_product_name) AS label,
               SUM(amount_uzs) AS value,
               COUNT(*) AS deals
        FROM deals_enriched
        WHERE {where} AND ({company_condition}) AND tnved_code IS NOT NULL
        GROUP BY tnved_code
        ORDER BY value DESC
        LIMIT 5
    """
    products = fetch_dicts(top_sql)

    sources = _source_hint(p)
    return QueryResult(
        intent="company_profile",
        rows=rows,
        sql=sql,
        filters=filter_summary(p),
        sources=sources,
        meta={
            "company": {
                "inn": company.inn,
                "name": company.name,
                "region": company.region,
                "activity": company.activity,
                "role": company.role,
            },
            "products": products,
        },
        not_found=not rows,
    )


def product_stats_query(p: ParsedQuery) -> QueryResult:
    where = build_where(p)
    sql = f"""
        SELECT COUNT(*) AS deals,
               COUNT(DISTINCT contract_id) AS contracts,
               SUM(amount_uzs) AS total_uzs,
               SUM(CASE WHEN currency = 'Доллар США' THEN amount ELSE 0 END) AS export_usd,
               COUNT(DISTINCT seller_inn) AS sellers,
               COUNT(DISTINCT buyer_inn) AS buyers
        FROM deals_enriched
        WHERE {where}
    """
    rows = fetch_dicts(sql)

    units = fetch_dicts(
        f"""
        SELECT unit, SUM(volume) AS volume, COUNT(*) AS deals
        FROM deals_enriched
        WHERE {where}
        GROUP BY unit
        ORDER BY volume DESC
        """
    )
    prices = fetch_dicts(
        f"""
        SELECT unit, currency, AVG(unit_price) AS avg_price,
               MIN(unit_price) AS min_price, MAX(unit_price) AS max_price,
               COUNT(*) AS deals
        FROM deals_enriched
        WHERE {where}
        GROUP BY unit, currency
        ORDER BY deals DESC
        """
    )
    statuses = fetch_dicts(
        f"""
        SELECT status, COUNT(*) AS deals, SUM(amount_uzs) AS total_uzs
        FROM deals_enriched
        WHERE {where}
        GROUP BY status
        ORDER BY deals DESC
        """
    )
    top_companies = fetch_dicts(
        f"""
        SELECT seller_inn AS inn, p.name AS name,
               SUM(amount_uzs) AS value, COUNT(*) AS deals
        FROM deals_enriched d
        LEFT JOIN participants p ON p.inn = d.seller_inn
        WHERE {where}
        GROUP BY seller_inn, p.name
        ORDER BY value DESC NULLS LAST
        LIMIT 5
        """
    )
    return QueryResult(
        intent="product_stats",
        rows=rows,
        sql=sql,
        filters=filter_summary(p),
        sources=_source_hint(p),
        meta={
            "units": units,
            "prices": prices,
            "statuses": statuses,
            "top_companies": top_companies,
            "product_label": p.product.label,
        },
        not_found=not rows,
    )


def contract_info_query(p: ParsedQuery) -> QueryResult:
    assert p.contract_id is not None
    contract = fetch_one(
        f"""
        SELECT c.*
        FROM contracts_full c
        WHERE c.contract_id = {int(p.contract_id)}
        """
    )
    if not contract:
        return QueryResult(
            intent="contract_info",
            rows=[],
            sql="",
            filters=filter_summary(p),
            sources=[f"Kontrakt / Контракт: {p.contract_id}"],
            not_found=True,
        )

    summary = fetch_one(
        f"""
        SELECT COUNT(*) AS deals, COUNT(DISTINCT seller_inn) AS sellers,
               COUNT(DISTINCT buyer_inn) AS buyers,
               SUM(amount_uzs) AS total_uzs,
               SUM(volume) AS volume,
               MIN(deal_date) AS first_date, MAX(deal_date) AS last_date
        FROM deals_enriched
        WHERE contract_id = {int(p.contract_id)}
        """
    ) or {}
    statuses = fetch_dicts(
        f"""
        SELECT status, COUNT(*) AS deals
        FROM deals_enriched
        WHERE contract_id = {int(p.contract_id)}
        GROUP BY status
        ORDER BY deals DESC
        """
    )
    return QueryResult(
        intent="contract_info",
        rows=[contract],
        sql="",
        filters=filter_summary(p),
        sources=[f"Kontrakt / Контракт: {p.contract_id}"],
        meta={"summary": summary, "statuses": statuses},
    )


def deal_info_query(p: ParsedQuery) -> QueryResult:
    assert p.deal_id is not None
    row = fetch_one(
        f"""
        SELECT d.*, sp.name AS seller_name, bp.name AS buyer_name
        FROM deals_enriched d
        LEFT JOIN participants sp ON sp.inn = d.seller_inn
        LEFT JOIN participants bp ON bp.inn = d.buyer_inn
        WHERE d.deal_id = {int(p.deal_id)}
        """
    )
    if not row:
        return QueryResult(
            intent="deal_info",
            rows=[],
            sql="",
            filters=filter_summary(p),
            sources=[f"Bitim / Сделка: {p.deal_id}"],
            not_found=True,
        )
    return QueryResult(
        intent="deal_info",
        rows=[row],
        sql="",
        filters=filter_summary(p),
        sources=[f"Bitim / Сделка: {p.deal_id}"],
    )


def status_stats_query(p: ParsedQuery) -> QueryResult:
    where = build_where(p)
    sql = f"""
        SELECT status, COUNT(*) AS deals, SUM(amount_uzs) AS total_uzs
        FROM deals_enriched
        WHERE {where}
        GROUP BY status
        ORDER BY deals DESC
    """
    rows = fetch_dicts(sql)
    return _base_result(p, "status_stats", rows, sql)


def region_stats_query(p: ParsedQuery) -> QueryResult:
    where = build_where(p)
    if p.metric == "count":
        value_expr = "COUNT(*)"
    elif p.metric == "volume":
        value_expr = "SUM(volume)"
    else:
        value_expr = "SUM(amount_uzs)"
    sql = f"""
        SELECT region_uz AS label, {value_expr} AS value, COUNT(*) AS deals
        FROM deals_enriched
        WHERE {where}
        GROUP BY region_uz
        ORDER BY value DESC NULLS LAST
        LIMIT {p.top_n}
    """
    rows = fetch_dicts(sql)
    return _base_result(p, "region_stats", rows, sql, {"metric": p.metric})


def broker_stats_query(p: ParsedQuery) -> QueryResult:
    where = build_where(p)
    if p.broker:
        sql = f"""
            WITH sides AS (
                SELECT seller_broker AS broker_code, amount_uzs, deal_id
                FROM deals_enriched WHERE {where}
                UNION
                SELECT buyer_broker AS broker_code, amount_uzs, deal_id
                FROM deals_enriched WHERE {where}
            )
            SELECT b.broker_code AS code, b.name AS label, b.region AS region,
                   COUNT(DISTINCT s.deal_id) AS deals,
                   SUM(s.amount_uzs) AS value
            FROM sides s
            LEFT JOIN brokers b ON b.broker_code = s.broker_code
            WHERE s.broker_code = {q(p.broker.code)}
            GROUP BY b.broker_code, b.name, b.region
        """
        rows = fetch_dicts(sql)
        return _base_result(p, "broker_stats", rows, sql, {"broker": p.broker.name})
    sql = f"""
        WITH sides AS (
            SELECT seller_broker AS broker_code, amount_uzs, deal_id
            FROM deals_enriched WHERE {where}
            UNION
            SELECT buyer_broker AS broker_code, amount_uzs, deal_id
            FROM deals_enriched WHERE {where}
        )
        SELECT s.broker_code AS code, b.name AS label,
               COUNT(DISTINCT s.deal_id) AS deals,
               SUM(s.amount_uzs) AS value
        FROM sides s
        LEFT JOIN brokers b ON b.broker_code = s.broker_code
        GROUP BY s.broker_code, b.name
        ORDER BY value DESC NULLS LAST
        LIMIT {p.top_n}
    """
    rows = fetch_dicts(sql)
    return _base_result(p, "broker_stats", rows, sql, {"top": True})


def list_deals_query(p: ParsedQuery) -> QueryResult:
    where = build_where(p)
    sql = f"""
        SELECT deal_id, deal_date, product_name, amount_uzs, status,
               seller_inn, buyer_inn, contract_id
        FROM deals_enriched
        WHERE {where}
        ORDER BY deal_date DESC, deal_id DESC
        LIMIT 10
    """
    rows = fetch_dicts(sql)
    return _base_result(p, "list_deals", rows, sql)


def annulled_summary(p: ParsedQuery) -> dict | None:
    """How many annulled deals were left out by the default rule (for transparency)."""
    if not excludes_annulled(p):
        return None
    saved = p.statuses
    try:
        p.statuses = [ANNUL_STATUS]
        where = build_where(p, force_export=p.intent == "export_stats")
    finally:
        p.statuses = saved
    rows = fetch_dicts(
        f"SELECT COUNT(*) AS deals, SUM(amount_uzs) AS total_uzs FROM deals_enriched WHERE {where}"
    )
    if not rows or not rows[0].get("deals"):
        return None
    return rows[0]


def _run_template(p: ParsedQuery) -> QueryResult:
    if p.intent in EXTRA_INTENTS:
        return run_extra(p, build_where, _base_result)
    if p.intent == "contract_info" and p.contract_id is not None:
        return contract_info_query(p)
    if p.intent == "deal_info" and p.deal_id is not None:
        return deal_info_query(p)
    if p.intent == "top":
        return top_query(p)
    if p.intent == "company_profile" and p.company:
        return company_profile_query(p)
    if p.intent == "product_stats":
        return product_stats_query(p)
    if p.intent == "status_stats":
        return status_stats_query(p)
    if p.intent == "region_stats":
        return region_stats_query(p)
    if p.intent == "broker_stats":
        return broker_stats_query(p)
    if p.intent == "export_stats":
        return export_query(p)
    if p.intent == "list_deals":
        return list_deals_query(p)
    if p.intent == "total":
        return total_query(p)
    return QueryResult(intent="unknown")


def run_template(p: ParsedQuery) -> QueryResult:
    result = _run_template(p)
    if result.rows and not result.not_found:
        annulled = annulled_summary(p)
        if annulled:
            result.meta["annulled"] = annulled
    return result

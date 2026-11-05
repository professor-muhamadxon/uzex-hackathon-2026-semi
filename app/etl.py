"""ETL: load raw CSV files into a normalised DuckDB database.

Run:  python scripts/build_db.py
"""

from __future__ import annotations

from pathlib import Path

import duckdb

from .config import DATA_DIR, DB_PATH

DEAL_FILES = [
    "deals_2022.csv",
    "deals_2023.csv",
    "deals_2024.csv",
    "deals_2025.csv",
    "deals_2026.csv",
]


def _csv_list(files: list[str]) -> str:
    paths = [str(DATA_DIR / name) for name in files]
    return "[" + ", ".join("'" + path.replace("'", "''") + "'" for path in paths) + "]"


def _num(col: str) -> str:
    """Cast a space-separated decimal string to DECIMAL."""
    return (
        f"try_cast(replace(replace(trim({col}), ' ', ''), ',', '.') AS DECIMAL(20,4))"
    )


def _date(col: str) -> str:
    return (
        f"CASE WHEN trim({col}) = '' THEN NULL "
        f"ELSE try_cast(strptime(trim({col}), '%d.%m.%Y') AS DATE) END"
    )


REGION_MAP = [
    ("Андижанская область", "Andijon viloyati"),
    ("Бухарская область", "Buxoro viloyati"),
    ("Джизакская область", "Jizzax viloyati"),
    ("Кашкадарьинская область", "Qashqadaryo viloyati"),
    ("Навоийская область", "Navoiy viloyati"),
    ("Наманганская область", "Namangan viloyati"),
    ("Республика Каракалпакстан", "Qoraqalpog‘iston Respublikasi"),
    ("Самаркандская область", "Samarqand viloyati"),
    ("Сурхандарьинская область", "Surxondaryo viloyati"),
    ("Сырдарьинская область", "Sirdaryo viloyati"),
    ("Ташкентская область", "Toshkent viloyati"),
    ("Ферганская область", "Farg‘ona viloyati"),
    ("Хорезмская область", "Xorazm viloyati"),
    ("г. Ташкент", "Toshkent shahri"),
]


def build(db_path: Path = DB_PATH, data_dir: Path = DATA_DIR) -> None:
    global DATA_DIR
    DATA_DIR = data_dir
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    con = duckdb.connect(str(db_path))
    con.execute("PRAGMA threads=4")

    print("[1/8] participants")
    con.execute(
        f"""
        CREATE TABLE participants AS
        SELECT
            trim("ИНН")                         AS inn,
            trim("Наименование")                AS name,
            trim("Регион")                      AS region,
            trim("Вид деятельности")            AS activity,
            trim("Роль")                        AS role,
            trim("Плательщик НДС")              AS vat_payer
        FROM read_csv('{data_dir / "participants.csv"}', header=true, all_varchar=true)
        """
    )

    print("[2/8] brokers")
    con.execute(
        f"""
        CREATE TABLE brokers AS
        SELECT
            trim("Код брокера")                 AS broker_code,
            trim("Наименование")                AS name,
            trim("ИНН")                         AS inn,
            trim("Регион")                      AS region
        FROM read_csv('{data_dir / "brokers.csv"}', header=true, all_varchar=true)
        """
    )

    print("[3/8] usd_rates")
    con.execute(
        f"""
        CREATE TABLE usd_rates AS
        SELECT
            try_cast(strptime(trim("Дата"), '%d.%m.%Y') AS DATE) AS rate_date,
            {_num('"Курс"')}                   AS rate
        FROM read_csv('{data_dir / "usd_rates.csv"}', header=true, all_varchar=true)
        """
    )

    print("[4/8] contracts")
    con.execute(
        f"""
        CREATE TABLE contracts AS
        SELECT
            try_cast("Номер контракта" AS BIGINT)          AS contract_id,
            trim("Наименование продукта")                  AS product_name,
            trim("Марка товара")                           AS brand,
            trim("Размер товара")                          AS size,
            trim("Сорт товара")                            AS grade,
            trim("Тип товара")                             AS type,
            trim("Класс товара")                           AS class,
            trim("Код ТН ВЭД")                             AS tnved_code,
            trim("Группа товара")                          AS group_name,
            trim("Категория товара")                       AS category,
            trim("Отрасль промышленности")                 AS industry,
            trim("Единица измерения")                      AS unit,
            {_num('"Лот"')}                                AS lot,
            trim("Валюта")                                 AS currency,
            {_num('"Базисная цена"')}                      AS base_price,
            try_cast(
                replace(replace(replace(trim("Сумма залога"), ' ', ''), '%', ''), ',', '.')
                AS DECIMAL(10,2)
            )                                              AS deposit_pct,
            trim("Базис поставки")                         AS delivery_basis,
            trim("Регион")                                 AS region_ru,
            trim("Адрес склада")                           AS warehouse_address,
            trim("Тип торгов")                             AS trade_type,
            trim("Тип контракта")                          AS contract_type,
            trim("Форма контракта")                        AS contract_form,
            try_cast(trim("Срок оплаты") AS INTEGER)       AS payment_term_days,
            try_cast(trim("Срок поставки") AS INTEGER)     AS delivery_term_days,
            trim("Упаковка")                               AS packaging,
            trim("ИНН продавца")                           AS seller_inn,
            {_date('"Дата регистрации"')}                  AS registration_date,
            {_date('"Действует до"')}                      AS valid_until
        FROM read_csv('{data_dir / "contracts.csv"}', header=true, all_varchar=true)
        """
    )

    print("[5/8] deals")
    con.execute(
        f"""
        CREATE TABLE deals AS
        SELECT
            try_cast("Номер сделки" AS BIGINT)             AS deal_id,
            {_date('"Дата сделки"')}                       AS deal_date,
            try_cast(trim("Время сделки") AS TIME)         AS deal_time,
            trim("Тип торгов")                             AS trade_type,
            {_num('"Количество"')}                         AS quantity,
            {_num('"Сумма сделки"')}                       AS amount,
            {_num('"Стартовая цена"')}                     AS start_price,
            try_cast("Номер контракта" AS BIGINT)          AS contract_id,
            trim("Наименование товара")                    AS product_name,
            {_num('"Лот"')}                                AS lot,
            trim("Единица измерения")                      AS unit,
            trim("Регион")                                 AS region_uz,
            trim("Тип контракта")                          AS contract_type,
            trim("Форма контракта")                        AS contract_form,
            trim("Состояние сделки")                       AS status,
            trim("ИНН продавца")                           AS seller_inn,
            trim("ИНН покупателя")                         AS buyer_inn,
            trim("Брокер продавца")                        AS seller_broker,
            trim("Брокер покупателя")                      AS buyer_broker,
            {_date('"Дата оплаты"')}                       AS payment_date,
            {_date('"Дата поставки"')}                     AS delivery_date,
            {_num('"Поставлено"')}                         AS delivered_quantity
        FROM read_csv(
            {_csv_list(DEAL_FILES)},
            header=true,
            all_varchar=true,
            union_by_name=true
        )
        """
    )

    print("[6/8] region mapping")
    con.execute("CREATE TABLE region_map(region_ru VARCHAR, region_uz VARCHAR)")
    con.executemany("INSERT INTO region_map VALUES (?, ?)", REGION_MAP)

    print("[7/8] enriched tables")
    con.execute(
        """
        CREATE TABLE contracts_full AS
        SELECT
            c.*,
            p.name          AS seller_name,
            p.activity      AS seller_activity,
            p.region        AS seller_region,
            rm.region_uz    AS region_uz
        FROM contracts c
        LEFT JOIN participants p ON p.inn = c.seller_inn
        LEFT JOIN region_map rm ON rm.region_ru = c.region_ru
        """
    )

    con.execute(
        """
        CREATE TABLE deals_enriched AS
        SELECT
            d.*,
            c.currency,
            c.category,
            c.group_name,
            c.industry,
            c.tnved_code,
            c.region_ru,
            c.base_price,
            c.payment_term_days,
            c.delivery_term_days,
            c.product_name AS contract_product_name,
            d.quantity * d.lot AS volume,
            CASE
                WHEN d.quantity * d.lot = 0 THEN NULL
                ELSE d.amount / (d.quantity * d.lot)
            END AS unit_price,
            CASE
                WHEN c.currency = 'Доллар США' THEN d.amount * r.rate
                ELSE d.amount
            END AS amount_uzs,
            r.rate AS usd_rate
        FROM deals d
        LEFT JOIN contracts c ON c.contract_id = d.contract_id
        LEFT JOIN usd_rates r ON r.rate_date = d.deal_date
        """
    )

    print("[8/8] indexes")
    for name, cols in {
        "idx_deals_date": "deal_date",
        "idx_deals_contract": "contract_id",
        "idx_deals_seller": "seller_inn",
        "idx_deals_buyer": "buyer_inn",
        "idx_deals_status": "status",
        "idx_contracts_tnved": "tnved_code",
    }.items():
        table = "deals" if name.startswith("idx_deals") else "contracts"
        con.execute(f"CREATE INDEX {name} ON {table}({cols})")

    counts = {
        table: con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        for table in [
            "deals",
            "contracts",
            "participants",
            "brokers",
            "usd_rates",
            "deals_enriched",
        ]
    }
    con.close()

    print("\nBaza tayyor:", db_path)
    for table, count in counts.items():
        print(f"  {table:16s} {count:>9,}")
    print("\nMisol:  python -m app.cli")

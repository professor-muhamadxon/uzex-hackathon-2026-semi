"""Deterministic bilingual answer formatting."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from .parser import ParsedQuery
from .sql import QueryResult

UNIT_UZ = {
    "килограмм": "kg",
    "тонна": "tonna",
    "метр": "metr",
    "штука": "dona",
    "куб.метр": "kub metr",
    "кв.метр": "kv metr",
    "литр": "litr",
}

ROLE_UZ = {"seller": "sotuvchi", "buyer": "xaridor"}
ROLE_RU = {"seller": "продавец", "buyer": "покупатель"}

GROUP_UZ = {
    "company": "kompaniya",
    "product": "tovar",
    "region": "region",
    "broker": "broker",
}
GROUP_RU = {
    "company": "компаний",
    "product": "товаров",
    "region": "регионов",
    "broker": "брокеров",
}

METRIC_UZ = {
    "amount": "summa",
    "count": "bitimlar soni",
    "volume": "hajm",
    "avg_price": "o‘rtacha narx",
    "usd": "dollar summasi",
}
METRIC_RU = {
    "amount": "сумма",
    "count": "количество сделок",
    "volume": "объём",
    "avg_price": "средняя цена",
    "usd": "сумма в долларах",
}


def fmt_num(value: Any, digits: int = 2) -> str:
    if value is None:
        return "—"
    if isinstance(value, Decimal):
        value = float(value)
    if isinstance(value, int) or (isinstance(value, float) and value.is_integer()):
        return f"{int(value):,}".replace(",", " ")
    text = f"{float(value):,.{digits}f}"
    text = text.replace(",", " ")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def fmt_money(value: Any, lang: str) -> str:
    if value is None:
        return "—"
    return f"{fmt_num(value)} {'so‘m' if lang == 'uz' else 'сум'}"


def fmt_usd(value: Any, lang: str) -> str:
    if value is None:
        return "—"
    return f"${fmt_num(value)}" if lang == "uz" else f"{fmt_num(value)} USD"


def fmt_unit(unit: str, lang: str) -> str:
    if lang == "uz":
        return UNIT_UZ.get(unit, unit)
    return unit


CURRENCY_UZ = {
    "Узбекский сум": "so‘m",
    "Доллар США": "USD",
}
CURRENCY_RU = {
    "Узбекский сум": "сум",
    "Доллар США": "USD",
}


def fmt_currency(currency: str | None, lang: str) -> str:
    if not currency:
        return ""
    return (CURRENCY_UZ if lang == "uz" else CURRENCY_RU).get(currency, currency)


def fmt_date(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, (date, datetime)):
        return value.strftime("%d.%m.%Y")
    return str(value)


def _filters_line(p: ParsedQuery, filters: str, lang: str) -> str:
    label = "Filtr" if lang == "uz" else "Фильтр"
    return f"{label}: {filters}"


def _sources_line(sources: list[str], lang: str) -> str:
    if not sources:
        return ""
    label = "Manba" if lang == "uz" else "Источник"
    return f"{label}: " + "; ".join(sources)


def _append_footer(text: str, result: QueryResult, p: ParsedQuery) -> str:
    parts = [text.strip()]
    annulled = result.meta.get("annulled") if result.meta else None
    if annulled:
        if p.lang == "uz":
            parts.append(
                f"Annul qilingan {fmt_num(annulled.get('deals'))} ta bitim "
                f"({fmt_money(annulled.get('total_uzs'), p.lang)}) hisobga olinmagan."
            )
        else:
            parts.append(
                f"Аннулированные сделки ({fmt_num(annulled.get('deals'))} шт., "
                f"{fmt_money(annulled.get('total_uzs'), p.lang)}) не учтены."
            )
    if not result.not_found:
        from .explain import explain

        parts.append(explain(result, p))
    parts.append(_filters_line(p, result.filters, p.lang))
    sources = _sources_line(result.sources, p.lang)
    if sources:
        parts.append(sources)
    return "\n\n".join(part for part in parts if part)


def format_result(result: QueryResult, p: ParsedQuery) -> str:
    lang = p.lang
    if result.not_found:
        if lang == "uz":
            return _append_footer(
                "Ma’lumotlarda bu savolga mos javob topilmadi. "
                "Iltimos, davr, tovar yoki kompaniya nomini aniqlashtiring.",
                result,
                p,
            )
        return _append_footer(
            "В данных не найдено ответа на этот вопрос. "
            "Уточните период, товар или название компании.",
            result,
            p,
        )

    from .extra import EXTRA_INTENTS, format_extra

    if result.intent in EXTRA_INTENTS:
        return _append_footer(format_extra(result, p, fmt_num, fmt_money, fmt_date), result, p)

    formatter = {
        "total": _format_total,
        "export_stats": _format_export,
        "top": _format_top,
        "company_profile": _format_company,
        "product_stats": _format_product,
        "contract_info": _format_contract,
        "deal_info": _format_deal,
        "status_stats": _format_status,
        "region_stats": _format_region,
        "broker_stats": _format_broker,
        "list_deals": _format_list,
    }.get(result.intent, _format_generic)

    text = formatter(result, p)
    return _append_footer(text, result, p)


def _format_total(result: QueryResult, p: ParsedQuery) -> str:
    lang = p.lang
    if not result.rows:
        return "—"
    if p.metric == "volume":
        lines = [
            ("Jami hajm" if lang == "uz" else "Общий объём") + ":"
        ]
        for row in result.rows:
            lines.append(
                f"• {fmt_num(row.get('value'))} {fmt_unit(row.get('unit', ''), lang)} "
                f"({fmt_num(row.get('deals'))} {'ta bitim' if lang == 'uz' else 'сделок'})"
            )
        return "\n".join(lines)
    if p.metric == "avg_price":
        lines = [("O‘rtacha narx" if lang == "uz" else "Средняя цена") + ":"]
        for row in result.rows:
            lines.append(
                f"• {fmt_num(row.get('value'))} {fmt_currency(row.get('currency'), lang)} / "
                f"{fmt_unit(row.get('unit', ''), lang)} "
                f"(min {fmt_num(row.get('min_price'))}, max {fmt_num(row.get('max_price'))}, "
                f"{fmt_num(row.get('deals'))} {'ta bitim' if lang == 'uz' else 'сделок'})"
            )
        return "\n".join(lines)

    row = result.rows[0]
    if p.metric == "count":
        if lang == "uz":
            return f"Bitimlar soni: {fmt_num(row.get('deals'))} ta."
        return f"Количество сделок: {fmt_num(row.get('deals'))}."

    if p.metric == "usd" or p.intent == "export_stats":
        usd = row.get("total_usd", row.get("export_usd"))
        if lang == "uz":
            return (
                f"Eksport summasi: {fmt_usd(usd, lang)}; "
                f"so‘m ekvivalenti: {fmt_money(row.get('total_uzs'), lang)} "
                f"({fmt_num(row.get('deals'))} ta bitim)."
            )
        return (
            f"Сумма экспорта: {fmt_usd(usd, lang)}; "
            f"эквивалент в сумах: {fmt_money(row.get('total_uzs'), lang)} "
            f"({fmt_num(row.get('deals'))} сделок)."
        )

    total = row.get("total_uzs")
    deals = row.get("deals")
    contracts = row.get("contracts")
    export_usd = row.get("export_usd") or 0
    if lang == "uz":
        text = f"Jami summa: {fmt_money(total, lang)} ({fmt_num(deals)} ta bitim, {fmt_num(contracts)} ta kontrakt)."
        if export_usd:
            text += f" Shu jumladan eksport: {fmt_usd(export_usd, lang)}."
        return text
    text = f"Общая сумма: {fmt_money(total, lang)} ({fmt_num(deals)} сделок, {fmt_num(contracts)} контрактов)."
    if export_usd:
        text += f" В том числе экспорт: {fmt_usd(export_usd, lang)}."
    return text


def _format_export(result: QueryResult, p: ParsedQuery) -> str:
    if not result.rows:
        return "—"
    row = result.rows[0]
    lang = p.lang
    if lang == "uz":
        return (
            f"Eksport bitimlari: {fmt_num(row.get('deals'))} ta, "
            f"summa: {fmt_usd(row.get('total_usd'), lang)}; "
            f"so‘m ekvivalenti: {fmt_money(row.get('total_uzs'), lang)}. "
            f"Sotuvchilar: {fmt_num(row.get('sellers'))}, xaridorlar: {fmt_num(row.get('buyers'))}."
        )
    return (
        f"Экспортные сделки: {fmt_num(row.get('deals'))}, "
        f"сумма: {fmt_usd(row.get('total_usd'), lang)}; "
        f"эквивалент в сумах: {fmt_money(row.get('total_uzs'), lang)}. "
        f"Продавцов: {fmt_num(row.get('sellers'))}, покупателей: {fmt_num(row.get('buyers'))}."
    )


def _format_top(result: QueryResult, p: ParsedQuery) -> str:
    if not result.rows:
        return "—"
    lang = p.lang
    group = result.meta.get("group", "company")
    metric = result.meta.get("metric", "amount")
    group_label = GROUP_UZ.get(group, group) if lang == "uz" else GROUP_RU.get(group, group)
    if group == "company" and p.company_role in {"buyer", "seller"}:
        group_label = {
            ("uz", "buyer"): "xaridor", ("uz", "seller"): "sotuvchi",
            ("ru", "buyer"): "покупателей", ("ru", "seller"): "продавцов",
        }[(lang, p.company_role)]
    metric_label = METRIC_UZ.get(metric, metric) if lang == "uz" else METRIC_RU.get(metric, metric)
    header = (
        f"Top {len(result.rows)} {group_label} ({metric_label} bo‘yicha):"
        if lang == "uz"
        else f"Топ-{len(result.rows)} {group_label} (по показателю «{metric_label}»):"
    )
    lines = [header]
    for index, row in enumerate(result.rows, start=1):
        label = row.get("label") or row.get("code") or "—"
        code = row.get("code")
        if group == "company":
            code_text = f" (INN: {code})" if code else ""
        elif group == "product":
            code_text = f" (TNVED: {code})" if code else ""
        else:
            code_text = f" ({code})" if code and str(code) != str(label) else ""
        if metric == "count":
            value_text = f"{fmt_num(row.get('value'))} ta bitim"
            if lang == "ru":
                value_text = f"{fmt_num(row.get('value'))} сделок"
        elif metric == "volume":
            value_text = f"{fmt_num(row.get('value'))} {fmt_unit(row.get('unit', ''), lang)}"
        elif metric == "usd":
            value_text = fmt_usd(row.get("value"), lang)
        elif metric == "avg_price":
            value_text = f"{fmt_num(row.get('value'))} {fmt_currency(row.get('currency'), lang)}"
            if row.get("unit"):
                value_text += f" / {fmt_unit(row.get('unit'), lang)}"
        else:
            value_text = fmt_money(row.get("value"), lang)
        lines.append(f"{index}. {label}{code_text} — {value_text}")
    return "\n".join(lines)


def _format_company(result: QueryResult, p: ParsedQuery) -> str:
    lang = p.lang
    info = result.meta.get("company", {})
    lines: list[str] = []
    if lang == "uz":
        lines.append(
            f"Kompaniya: {info.get('name')} (INN: {info.get('inn')}), "
            f"region: {info.get('region')}, faoliyat: {info.get('activity')}."
        )
    else:
        lines.append(
            f"Компания: {info.get('name')} (ИНН: {info.get('inn')}), "
            f"регион: {info.get('region')}, деятельность: {info.get('activity')}."
        )
    for row in result.rows:
        role = row.get("role")
        role_label = ROLE_UZ.get(role, role) if lang == "uz" else ROLE_RU.get(role, role)
        if lang == "uz":
            lines.append(
                f"{role_label.capitalize()} sifatida: {fmt_num(row.get('deals'))} ta bitim, "
                f"{fmt_money(row.get('total_uzs'), lang)}, {fmt_num(row.get('contracts'))} ta kontrakt; "
                f"davr: {fmt_date(row.get('first_date'))} – {fmt_date(row.get('last_date'))}."
            )
        else:
            lines.append(
                f"Как {role_label}: {fmt_num(row.get('deals'))} сделок, "
                f"{fmt_money(row.get('total_uzs'), lang)}, {fmt_num(row.get('contracts'))} контрактов; "
                f"период: {fmt_date(row.get('first_date'))} – {fmt_date(row.get('last_date'))}."
            )
    products = result.meta.get("products") or []
    if products:
        lines.append("Asosiy tovarlar:" if lang == "uz" else "Основные товары:")
        for item in products:
            value = fmt_money(item.get("value"), lang)
            lines.append(
                f"• {item.get('label')} ({item.get('code')}) — {value}, "
                f"{fmt_num(item.get('deals'))} {'ta bitim' if lang == 'uz' else 'сделок'}"
            )
    return "\n".join(lines)


def _format_product(result: QueryResult, p: ParsedQuery) -> str:
    if not result.rows:
        return "—"
    lang = p.lang
    row = result.rows[0]
    product_label = result.meta.get("product_label")
    label = product_label or ("Tovar" if lang == "uz" else "Товар")
    lines: list[str] = []
    if lang == "uz":
        lines.append(
            f"Tovar: {label}. Bitimlar: {fmt_num(row.get('deals'))} ta, "
            f"kontraktlar: {fmt_num(row.get('contracts'))}, "
            f"jami summa: {fmt_money(row.get('total_uzs'), lang)}."
        )
    else:
        lines.append(
            f"Товар: {label}. Сделок: {fmt_num(row.get('deals'))}, "
            f"контрактов: {fmt_num(row.get('contracts'))}, "
            f"общая сумма: {fmt_money(row.get('total_uzs'), lang)}."
        )
    export_usd = row.get("export_usd") or 0
    if export_usd:
        lines[-1] += (f" Shundan dollardagi (eksport) bitimlar: {fmt_usd(export_usd, lang)}."
                      if lang == "uz" else f" В том числе долларовые (экспортные) сделки: {fmt_usd(export_usd, lang)}.")
    units = result.meta.get("units") or []
    if units:
        lines.append("Hajm:" if lang == "uz" else "Объём:")
        for unit in units:
            lines.append(
                f"• {fmt_num(unit.get('volume'))} {fmt_unit(unit.get('unit', ''), lang)} "
                f"({fmt_num(unit.get('deals'))} {'ta bitim' if lang == 'uz' else 'сделок'})"
            )
    prices = result.meta.get("prices") or []
    if prices:
        lines.append("Narxlar:" if lang == "uz" else "Цены:")
        for price in prices:
            lines.append(
                f"• {fmt_num(price.get('avg_price'))} {fmt_currency(price.get('currency'), lang)} / "
                f"{fmt_unit(price.get('unit', ''), lang)} "
                f"(min {fmt_num(price.get('min_price'))}, max {fmt_num(price.get('max_price'))})"
            )
    top_companies = result.meta.get("top_companies") or []
    if top_companies:
        lines.append("Eng ko‘p sotgan kompaniyalar:" if lang == "uz" else "Крупнейшие продавцы:")
        for item in top_companies:
            lines.append(
                f"• {item.get('name')} (INN: {item.get('inn')}) — "
                f"{fmt_money(item.get('value'), lang)}, "
                f"{fmt_num(item.get('deals'))} {'ta bitim' if lang == 'uz' else 'сделок'}"
            )
    return "\n".join(lines)


def _format_contract(result: QueryResult, p: ParsedQuery) -> str:
    if not result.rows:
        return "—"
    lang = p.lang
    contract = result.rows[0]
    lines: list[str] = []
    if lang == "uz":
        lines.append(
            f"Kontrakt {contract.get('contract_id')}: {contract.get('product_name')}"
            + (f", markasi: {contract.get('brand')}" if contract.get("brand") else "")
            + f". Sotuvchi: {contract.get('seller_name') or contract.get('seller_inn')}."
        )
        lines.append(
            f"O‘lchov: {contract.get('unit')}, lot: {fmt_num(contract.get('lot'))}, "
            f"valyuta: {fmt_currency(contract.get('currency'), lang)}, bazis narx: {fmt_num(contract.get('base_price'))}."
        )
        lines.append(
            f"Turi: {contract.get('contract_type')}, forma: {contract.get('contract_form')}, "
            f"savdo: {contract.get('trade_type')}, region: {contract.get('region_uz') or contract.get('region_ru')}."
        )
        lines.append(
            f"To‘lov muddati: {contract.get('payment_term_days')} kun, "
            f"yetkazish muddati: {contract.get('delivery_term_days')} kun, "
            f"ro‘yxatdan o‘tgan: {fmt_date(contract.get('registration_date'))}, "
            f"amal qiladi: {fmt_date(contract.get('valid_until'))} gacha."
        )
    else:
        lines.append(
            f"Контракт {contract.get('contract_id')}: {contract.get('product_name')}"
            + (f", марка: {contract.get('brand')}" if contract.get("brand") else "")
            + f". Продавец: {contract.get('seller_name') or contract.get('seller_inn')}."
        )
        lines.append(
            f"Единица: {contract.get('unit')}, лот: {fmt_num(contract.get('lot'))}, "
            f"валюта: {fmt_currency(contract.get('currency'), lang)}, базовая цена: {fmt_num(contract.get('base_price'))}."
        )
        lines.append(
            f"Тип: {contract.get('contract_type')}, форма: {contract.get('contract_form')}, "
            f"торги: {contract.get('trade_type')}, регион: {contract.get('region_uz') or contract.get('region_ru')}."
        )
        lines.append(
            f"Срок оплаты: {contract.get('payment_term_days')} дней, "
            f"срок поставки: {contract.get('delivery_term_days')} дней, "
            f"регистрация: {fmt_date(contract.get('registration_date'))}, "
            f"действует до: {fmt_date(contract.get('valid_until'))}."
        )

    summary = result.meta.get("summary") or {}
    if summary:
        if lang == "uz":
            lines.append(
                f"Bitimlar: {fmt_num(summary.get('deals'))} ta, "
                f"summa: {fmt_money(summary.get('total_uzs'), lang)}, "
                f"hajm: {fmt_num(summary.get('volume'))} {fmt_unit(contract.get('unit', ''), lang)}, "
                f"davr: {fmt_date(summary.get('first_date'))} – {fmt_date(summary.get('last_date'))}."
            )
        else:
            lines.append(
                f"Сделок: {fmt_num(summary.get('deals'))}, "
                f"сумма: {fmt_money(summary.get('total_uzs'), lang)}, "
                f"объём: {fmt_num(summary.get('volume'))} {fmt_unit(contract.get('unit', ''), lang)}, "
                f"период: {fmt_date(summary.get('first_date'))} – {fmt_date(summary.get('last_date'))}."
            )
    statuses = result.meta.get("statuses") or []
    if statuses:
        parts = [f"{row.get('status')}: {fmt_num(row.get('deals'))}" for row in statuses]
        lines.append(("Holatlar: " if lang == "uz" else "Статусы: ") + "; ".join(parts))
    return "\n".join(lines)


def _format_deal(result: QueryResult, p: ParsedQuery) -> str:
    if not result.rows:
        return "—"
    lang = p.lang
    row = result.rows[0]
    if lang == "uz":
        return (
            f"Bitim {row.get('deal_id')}: {fmt_date(row.get('deal_date'))} "
            f"{row.get('deal_time')}, {row.get('product_name')}. "
            f"Miqdor: {fmt_num(row.get('quantity'))} lot × {fmt_num(row.get('lot'))} "
            f"= {fmt_num(row.get('volume'))} {fmt_unit(row.get('unit', ''), lang)}. "
            f"Summa: {fmt_money(row.get('amount_uzs'), lang)} "
            f"({fmt_num(row.get('amount'))} {fmt_currency(row.get('currency'), lang)}), "
            f"birlik narxi: {fmt_num(row.get('unit_price'))} {fmt_currency(row.get('currency'), lang)}. "
            f"Sotuvchi: {row.get('seller_name')} (INN: {row.get('seller_inn')}), "
            f"xaridor: {row.get('buyer_name')} (INN: {row.get('buyer_inn')}). "
            f"Kontrakt: {row.get('contract_id')}, holat: {row.get('status')}, "
            f"to‘lov: {fmt_date(row.get('payment_date'))}, yetkazish: {fmt_date(row.get('delivery_date'))}."
        )
    return (
        f"Сделка {row.get('deal_id')}: {fmt_date(row.get('deal_date'))} "
        f"{row.get('deal_time')}, {row.get('product_name')}. "
        f"Количество: {fmt_num(row.get('quantity'))} лот × {fmt_num(row.get('lot'))} "
        f"= {fmt_num(row.get('volume'))} {fmt_unit(row.get('unit', ''), lang)}. "
        f"Сумма: {fmt_money(row.get('amount_uzs'), lang)} "
        f"({fmt_num(row.get('amount'))} {fmt_currency(row.get('currency'), lang)}), "
        f"цена за единицу: {fmt_num(row.get('unit_price'))} {fmt_currency(row.get('currency'), lang)}. "
        f"Продавец: {row.get('seller_name')} (ИНН: {row.get('seller_inn')}), "
        f"покупатель: {row.get('buyer_name')} (ИНН: {row.get('buyer_inn')}). "
        f"Контракт: {row.get('contract_id')}, статус: {row.get('status')}, "
        f"оплата: {fmt_date(row.get('payment_date'))}, поставка: {fmt_date(row.get('delivery_date'))}."
    )


def _format_status(result: QueryResult, p: ParsedQuery) -> str:
    if not result.rows:
        return "—"
    lang = p.lang
    lines = [("Holatlar bo‘yicha:" if lang == "uz" else "По статусам:")]
    for row in result.rows:
        lines.append(
            f"• {row.get('status')}: {fmt_num(row.get('deals'))} "
            f"{'ta bitim' if lang == 'uz' else 'сделок'}, "
            f"{fmt_money(row.get('total_uzs'), lang)}"
        )
    return "\n".join(lines)


def _format_region(result: QueryResult, p: ParsedQuery) -> str:
    if not result.rows:
        return "—"
    lang = p.lang
    metric = result.meta.get("metric", "amount")
    lines = [
        ("Regionlar bo‘yicha:" if lang == "uz" else "По регионам:")
    ]
    for row in result.rows:
        if metric == "count":
            value = f"{fmt_num(row.get('value'))} {'ta bitim' if lang == 'uz' else 'сделок'}"
        elif metric == "volume":
            value = f"{fmt_num(row.get('value'))}"
        else:
            value = fmt_money(row.get("value"), lang)
        lines.append(f"• {row.get('label')} — {value}")
    return "\n".join(lines)


def _format_broker(result: QueryResult, p: ParsedQuery) -> str:
    if not result.rows:
        return "—"
    lang = p.lang
    if not result.meta.get("top"):
        row = result.rows[0]
        if lang == "uz":
            return (
                f"Broker {row.get('code')} {row.get('label')}: "
                f"{fmt_num(row.get('deals'))} ta bitim, {fmt_money(row.get('value'), lang)}, "
                f"region: {row.get('region')}."
            )
        return (
            f"Брокер {row.get('code')} {row.get('label')}: "
            f"{fmt_num(row.get('deals'))} сделок, {fmt_money(row.get('value'), lang)}, "
            f"регион: {row.get('region')}."
        )
    lines = [("Brokerlar bo‘yicha:" if lang == "uz" else "По брокерам:")]
    for index, row in enumerate(result.rows, start=1):
        lines.append(
            f"{index}. {row.get('code')} {row.get('label')} — "
            f"{fmt_num(row.get('deals'))} {'ta bitim' if lang == 'uz' else 'сделок'}, "
            f"{fmt_money(row.get('value'), lang)}"
        )
    return "\n".join(lines)


def _format_list(result: QueryResult, p: ParsedQuery) -> str:
    if not result.rows:
        return "—"
    lang = p.lang
    lines = [("So‘nggi bitimlar:" if lang == "uz" else "Последние сделки:")]
    for row in result.rows:
        lines.append(
            f"• {row.get('deal_id')} | {fmt_date(row.get('deal_date'))} | "
            f"{row.get('product_name')} | {fmt_money(row.get('amount_uzs'), lang)} | "
            f"{row.get('status')}"
        )
    return "\n".join(lines)


COLUMN_LABELS = {
    "deal_id": ("Bitim", "Сделка"),
    "deal_date": ("Sana", "Дата"),
    "product_name": ("Tovar", "Товар"),
    "amount_uzs": ("Summa (so‘m)", "Сумма (сум)"),
    "amount": ("Summa", "Сумма"),
    "volume": ("Hajm", "Объём"),
    "unit": ("Birlik", "Единица"),
    "status": ("Holat", "Статус"),
    "seller_inn": ("Sotuvchi INN", "ИНН продавца"),
    "buyer_inn": ("Xaridor INN", "ИНН покупателя"),
    "contract_id": ("Kontrakt", "Контракт"),
}


def _format_generic(result: QueryResult, p: ParsedQuery) -> str:
    if not result.rows:
        return "—"
    lang = p.lang
    lines: list[str] = []
    if len(result.rows) == 1:
        row = result.rows[0]
        for key, value in row.items():
            label = COLUMN_LABELS.get(key, (key, key))[0 if lang == "uz" else 1]
            if isinstance(value, (date, datetime)):
                value = fmt_date(value)
            elif isinstance(value, (int, float, Decimal)):
                value = fmt_num(value)
            elif value is None:
                value = "—"
            lines.append(f"• {label}: {value}")
    else:
        for row in result.rows[:20]:
            parts = []
            for key, value in row.items():
                label = COLUMN_LABELS.get(key, (key, key))[0 if lang == "uz" else 1]
                if isinstance(value, (date, datetime)):
                    value = fmt_date(value)
                elif isinstance(value, (int, float, Decimal)):
                    value = fmt_num(value)
                parts.append(f"{label}: {value}")
            lines.append("• " + "; ".join(parts))
        if len(result.rows) > 20:
            lines.append(f"... ({len(result.rows)} qator)" if lang == "uz" else f"... (строк: {len(result.rows)})")
    return "\n".join(lines)

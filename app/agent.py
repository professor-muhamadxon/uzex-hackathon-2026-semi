"""Agent orchestration: parse -> template SQL -> (fallback) LLM SQL -> answer."""

from __future__ import annotations

from dataclasses import dataclass, field

from .db import fetch_dicts
from .formatter import format_result
from .semantic import semantic_parse
from .config import LLM_ENABLED, LLM_SQL
from .localize import localizable_values, localize
from .script import render
from .llm import generate_sql
from .parser import DATA_END, DATA_START, ParsedQuery, parse_question
from .sql import QueryResult, filter_summary, run_template
from .validator import SQLValidationError, execute_sql, unverified_numbers
import logging

log = logging.getLogger(__name__)


@dataclass
class AgentResponse:
    answer: str
    intent: str
    lang: str
    sql: str = ""
    filters: str = ""
    used_llm: bool = False
    parsed: ParsedQuery | None = None
    protect: list = field(default_factory=list)
    rows: list = field(default_factory=list)
    unverified: list = field(default_factory=list)


class Agent:
    def __init__(self, llm_enabled: bool = True):
        self.llm_enabled = llm_enabled

    def ask(self, question: str) -> AgentResponse:
        response = self._ask(question)
        parsed = response.parsed
        if response.protect and parsed is not None:
            sources = [*response.protect, response.filters, parsed.question,
                       parsed.date_from, parsed.date_to, DATA_START, DATA_END, 100, 1.96, 95, 12]
            bad = unverified_numbers(response.answer, sources)
            response.unverified = bad
            if bad:
                log.warning("unverified numbers %s in answer to %r", bad, question)
        if parsed is not None:
            response.answer = localize(response.answer, parsed.lang)
        if parsed is not None and parsed.lang == "uz" and parsed.script != "lat_old":
            protect = [response.protect, parsed.company, parsed.broker,
                       parsed.not_found_detail, parsed.namesakes]
            response.answer = render(response.answer, parsed.script, protect, skip=localizable_values())
        return response

    def _ask(self, question: str) -> AgentResponse:
        question = question.strip()
        if not question:
            return AgentResponse(
                answer="Savol bo‘sh. Iltimos, savolingizni yozing.",
                intent="empty",
                lang="uz",
            )

        parsed = parse_question(question)

        # Small-LLM meaning layer (optional): only for questions the rules could not classify.
        if parsed.intent == "unknown" and not parsed.not_found_reason and self.llm_enabled and LLM_ENABLED:
            verdict = semantic_parse(question, parsed)
            if verdict is False:
                return AgentResponse(
                    answer=self._unsupported_answer(parsed.lang), intent="unsupported", lang=parsed.lang, parsed=parsed
                )

        if parsed.not_found_reason:
            return AgentResponse(
                answer=self._not_found_answer(parsed),
                intent="not_found",
                lang=parsed.lang,
                filters=filter_summary(parsed),
                parsed=parsed,
            )

        if parsed.intent != "unknown":
            try:
                result = run_template(parsed)
            except Exception as exc:  # noqa: BLE001 - never crash the bot on a template error
                log.exception("template failed for %r: %s", question, exc)
                result = None
            if result is None:
                return AgentResponse(
                    answer=self._error_answer(parsed.lang), intent="error", lang=parsed.lang, parsed=parsed
                )
            if not result.not_found and result.rows:
                deals = result.rows[0].get("deals")
                if deals is not None and float(deals or 0) == 0:
                    result.not_found = True
            answer = format_result(result, parsed)
            return AgentResponse(
                answer=answer,
                intent=result.intent,
                lang=parsed.lang,
                sql=result.sql,
                filters=result.filters,
                parsed=parsed,
                protect=[result.rows, result.meta, result.sources],
                rows=result.rows,
            )

        if self.llm_enabled and LLM_SQL:
            result = self._llm_query(question, parsed)
            if result is not None:
                answer = format_result(result, parsed)
                return AgentResponse(
                    answer=answer,
                    intent="llm_sql",
                    lang=parsed.lang,
                    sql=result.sql,
                    filters=result.filters,
                    used_llm=True,
                    parsed=parsed,
                    protect=[result.rows, result.meta],
                    rows=result.rows,
                )

        if parsed.lang == "ru":
            answer = (
                "Не удалось уверенно сопоставить вопрос с доступными расчётами, поэтому я не буду гадать. "
                "Доступно: суммы, количество и объём сделок, цены, топ компаний/товаров/регионов/брокеров, "
                "разрезы по регионам, товарам и дням недели, доли, курс доллара, анализ и прогноз. "
                "Переформулируйте вопрос, указав показатель и период."
            )
        else:
            answer = (
                "Savolni mavjud hisoblar bilan ishonchli moslab bo‘lmadi, shuning uchun taxmin qilmayman. "
                "Mavjud: bitimlar summasi, soni, hajmi, narx, kompaniya/tovar/viloyat/broker reytingi, "
                "viloyat, tovar va hafta kunlari kesimi, ulushlar, dollar kursi, tahlil va bashorat. "
                "Savolni ko‘rsatkich va davr bilan aniqroq yozing."
            )
        return AgentResponse(answer=answer, intent="unknown", lang=parsed.lang, parsed=parsed)

    @staticmethod
    def _unsupported_answer(lang: str) -> str:
        if lang == "ru":
            return ("Такой показатель или расчёт в данных и в доступных расчётах отсутствует "
                    "(например, маржа, прибыль, сроки поставки). Доступны суммы, количество, объёмы, цены, "
                    "рейтинги, разрезы, доли, курс доллара, анализ и прогноз.")
        return ("Bunday ko‘rsatkich yoki hisob ma’lumotlarda va mavjud hisoblarda yo‘q "
                "(masalan, marja, foyda, yetkazish muddati). Mavjud: summa, soni, hajm, narx, reyting, kesimlar, "
                "ulushlar, dollar kursi, tahlil va bashorat.")

    @staticmethod
    def _error_answer(lang: str) -> str:
        if lang == "ru":
            return "Не удалось надёжно вычислить ответ по данным. Переформулируйте вопрос, пожалуйста."
        return "Ma’lumotlar bo‘yicha javobni ishonchli hisoblab bo‘lmadi. Savolni boshqacha yozib ko‘ring."

    def _not_found_answer(self, parsed: ParsedQuery) -> str:
        lang = parsed.lang
        reason = parsed.not_found_reason
        if reason == "period":
            if lang == "ru":
                future = (parsed.year_from or 0) > DATA_END.year or (
                    parsed.year_from == DATA_END.year and (parsed.month or 0) > DATA_END.month
                ) or (parsed.date_to is not None and parsed.date_to > DATA_END)
                text = (
                    "В данных нет информации за запрошенный период. "
                    "Данные охватывают 03.01.2022 – 30.10.2026."
                )
                if future:
                    text += (" Если нужна статистическая оценка на будущее, спросите «прогноз …» "
                             "(например: «прогноз курса доллара на 2027 год»).")
                return text
            future = (parsed.year_from or 0) > DATA_END.year or (
                parsed.year_from == DATA_END.year and (parsed.month or 0) > DATA_END.month
            ) or (parsed.date_to is not None and parsed.date_to > DATA_END)
            text = (
                "So‘ralgan davr bo‘yicha ma’lumot topilmadi. "
                "Ma’lumotlar 03.01.2022 – 30.10.2026 oralig‘ini qamraydi."
            )
            if future:
                text += (" Kelajak uchun statistik taxmin kerak bo‘lsa, «… bashorat qil» deb so‘rang "
                         "(masalan: «2027-yil uchun dollar kursini bashorat qil»).")
            return text
        if reason == "entity":
            name = parsed.not_found_detail
            if lang == "ru":
                who = f"Компания «{name}»" if name else "Указанная компания"
                return (
                    f"{who} не найдена в данных (участники и сделки биржи). "
                    "Укажите точное название или 9-значный ИНН."
                )
            who = f"«{name}» nomli kompaniya" if name else "Ko‘rsatilgan kompaniya"
            return (
                f"{who} ma’lumotlarda (birja qatnashchilari va bitimlari) topilmadi. "
                "Aniq nomini yoki 9 xonali INNni ko‘rsating."
            )
        if reason == "product_unknown":
            word = parsed.not_found_detail
            if lang == "ru":
                return (f"Товар или показатель «{word}» в данных не найден. "
                        "В данных есть сделки биржи: суммы, количества, объёмы, цены и курс доллара.")
            return (f"«{word}» tovari yoki ko‘rsatkichi ma’lumotlarda topilmadi. "
                    "Ma’lumotlarda birja bitimlari bor: summa, soni, hajm, narx va dollar kursi.")
        if reason == "product":
            word = parsed.not_found_detail
            if lang == "ru":
                return (f"Слово «{word}» не удалось уверенно сопоставить с товаром из данных "
                        "(подходит несколько вариантов). Уточните название товара.")
            return (f"«{word}» so‘zini ma’lumotlardagi bitta tovarga aniq moslab bo‘lmadi "
                    "(bir nechta variant mos keladi). Tovar nomini aniqroq yozing.")
        if reason == "field":
            detail = f" ({parsed.not_found_detail})" if parsed.not_found_detail else ""
            if lang == "ru":
                return (
                    f"Такой показатель{detail} в данных отсутствует. "
                    "Доступны: сумма, количество сделок, объём и цена за единицу."
                )
            return (
                f"Bunday ko‘rsatkich{detail} ma’lumotlarda mavjud emas. "
                "Mavjud: summa, bitimlar soni, hajm va birlik narxi."
            )
        if lang == "ru":
            return "В данных не найдено ответа на этот вопрос. Уточните параметры запроса."
        return "Ma’lumotlarda bu savolga mos javob topilmadi. Savol tafsilotlarini aniqlashtiring."

    def _llm_query(self, question: str, parsed: ParsedQuery) -> QueryResult | None:
        sql = generate_sql(question, parsed.lang)
        if not sql:
            return None
        error: str | None = None
        for attempt in range(2):
            try:
                rows = execute_sql(sql)
                if rows and str(rows[0].get("error", "")).lower() == "not_found":
                    return QueryResult(
                        intent="generic",
                        rows=[],
                        sql=sql,
                        filters=filter_summary(parsed),
                        not_found=True,
                    )
                return QueryResult(
                    intent="generic",
                    rows=rows,
                    sql=sql,
                    filters=filter_summary(parsed),
                    sources=[],
                    not_found=not rows,
                )
            except (SQLValidationError, Exception) as exc:  # noqa: BLE001
                error = str(exc)
                if attempt == 0:
                    sql = generate_sql(question, parsed.lang, previous_error=error)
                    if not sql:
                        return None
        return None

    def ask_text(self, question: str) -> str:
        return self.ask(question).answer


_default_agent: Agent | None = None


def get_agent() -> Agent:
    global _default_agent
    if _default_agent is None:
        _default_agent = Agent()
    return _default_agent

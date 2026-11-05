"""Telegram bot interface (aiogram 3.x, polling mode)."""

from __future__ import annotations

import asyncio
import csv
import html
import io
import logging
import time
from collections import OrderedDict

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from .config import TELEGRAM_BOT_TOKEN
from .qalog import ask_logged
from .relay import relay
from .tgstyle import style

logging.basicConfig(level=logging.INFO)

EXAMPLES = [
    "2025-yilda jami savdo summasi qancha?",
    "Ötgan oyda eksport qança dollar?",
    "Ўтган йили энг кўп пахта сотган 3 та компания",
    "Топ-5 компаний по сумме сделок в 2024 году",
    "Barcha davr bo‘yicha dollar kursini tahlil qil",
    "Прогноз курса доллара на 2027 год",
]

CREDIT_UZ = "Qöqon universiteti Andijon filiali (KUAF) iştirokçilari tomonidan tayyorlandi."
CREDIT_RU = "Подготовлено участниками Андижанского филиала Кокандского университета (KUAF)."

WELCOME_UZ = (
    "👋 <b>Xuş kelibsiz!</b>\n\n"
    "Men UZEX birja bitimlari böyiça AI-agentman. Savolni özbek (lotin, yangi alifbo yoki kirill) "
    "yoki rus tilida yozing: davr, tovar, kompaniya, region, broker yoki kontrakt raqami böyiça.\n\n"
    "• Javob savol tilida va yozuvida beriladi.\n"
    "• Har javobda <b>qanday hisoblangani</b>, filtrlar va manba körsatiladi.\n"
    "• Raqamlar faqat maʼlumotlardan olinadi; topilmasa — oçiq aytaman.\n"
    "• Maʼlumotlar davri: 03.01.2022 – 30.10.2026."
)
WELCOME_RU = (
    "👋 <b>Добро пожаловать!</b>\n\n"
    "Я AI-агент по сделкам биржи UZEX. Задайте вопрос на русском или узбекском "
    "(латиница, новый алфавит или кириллица): о периоде, товаре, компании, регионе, брокере "
    "или номере контракта.\n\n"
    "• Отвечаю на языке и в алфавите вопроса.\n"
    "• В каждом ответе — <b>как посчитано</b>, фильтры и источник.\n"
    "• Числа берутся только из данных; если ответа нет — скажу прямо.\n"
    "• Период данных: 03.01.2022 – 30.10.2026."
)


def _welcome(language_code: str | None) -> str:
    footer = f"\n\n<i>{CREDIT_UZ}\n{CREDIT_RU}</i>\n\nMisollar / Примеры 👇"
    if (language_code or "").startswith("ru"):
        return WELCOME_RU + "\n\n" + WELCOME_UZ + footer
    return WELCOME_UZ + "\n\n" + WELCOME_RU + footer


HELP = (
    "Misollar / Примеры:\n"
    "• 2025-yilda jami savdo summasi qancha?\n"
    "• Ötgan oyda eksport qança dollar?\n"
    "• Eng köp paxta sotgan 5 kompaniya\n"
    "• Наманган вилоятида нечта битим бўлган?\n"
    "• 100001-kontrakt haqida maʼlumot\n"
    "• Аннулированные сделки за 2025 год\n"
    "• Средняя цена хлопка за последние 3 месяца\n"
    "• Курс доллара на 01.06.2024\n"
    "• Barcha davr bo‘yicha dollar kursini tahlil qil\n"
    "• Прогноз курса доллара на 2027 год (статистическая оценка)\n\n"
    "Javob ostidagi «SQL» tugmasi bajarilgan sörovni körsatadi.\n"
    "Кнопка «SQL» под ответом показывает выполненный запрос.\n\n"
    + CREDIT_UZ + "\n" + CREDIT_RU
)

BOT_DESCRIPTION = (
    "UZEX birja bitimlari böyiça AI-agent: özbek (lotin, yangi alifbo, kirill) va rus tilidagi savollarga "
    "maʼlumotlar asosida javob beradi, qanday hisoblanganini körsatadi.\n"
    "AI-агент по сделкам биржи UZEX: отвечает на вопросы на русском и узбекском по данным и показывает, как посчитано.\n\n"
    + CREDIT_UZ + "\n" + CREDIT_RU
)
BOT_SHORT_DESCRIPTION = "UZEX bitimlari böyiça AI-agent · AI-агент по сделкам UZEX · KUAF"

RATE_LIMIT_SECONDS = 3.0
CSV_MIN_ROWS = 20
_last_question: dict[int, float] = {}
_explain: OrderedDict[str, tuple[str, str, str]] = OrderedDict()  # key -> (lang, sql, filters)
_EXPLAIN_MAX = 2000


def _chunks(text: str, limit: int = 4000) -> list[str]:
    chunks: list[str] = []
    current = ""
    for line in text.splitlines():
        if len(current) + len(line) + 1 > limit:
            if current:
                chunks.append(current)
            current = line[:limit]
        else:
            current = f"{current}\n{line}" if current else line
    if current:
        chunks.append(current)
    return chunks or [text[:limit]]


def _examples_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=q, callback_data=f"ex:{i}")] for i, q in enumerate(EXAMPLES)
        ]
    )


def _explain_keyboard(key: str, lang: str) -> InlineKeyboardMarkup:
    label = "🧾 SQL-запрос" if lang == "ru" else "🧾 SQL sörov"
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=label, callback_data=f"sql:{key}")]]
    )


def _remember(key: str, lang: str, sql: str, filters: str) -> None:
    _explain[key] = (lang, sql, filters)
    while len(_explain) > _EXPLAIN_MAX:
        _explain.popitem(last=False)


def _rows_csv(rows: list[dict]) -> bytes:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    for row in rows:
        writer.writerow({k: ("" if v is None else v) for k, v in row.items()})
    return buffer.getvalue().encode("utf-8-sig")


async def start_handler(message: Message) -> None:
    lang = message.from_user.language_code if message.from_user else None
    await message.answer(_welcome(lang), parse_mode=ParseMode.HTML, reply_markup=_examples_keyboard())


async def help_handler(message: Message) -> None:
    await message.answer(HELP)


def _styled_parts(answer: str) -> list[str]:
    """Plain answer -> Telegram HTML parts (< 4096 chars each); falls back to escaped plain text."""
    try:
        parts = [style(chunk) for chunk in _chunks(answer, limit=2200)]
        if all(len(part) <= 3900 for part in parts):
            return parts
    except Exception:  # noqa: BLE001 - presentation must never block the answer
        logging.exception("style failed")
    return _chunks(html.escape(answer))


async def _answer(
    message: Message,
    question: str,
    user_id: int,
    username: str | None = None,
    channel: str = "telegram",
) -> None:
    relay.question(
        question=question,
        user_id=user_id,
        username=username,
        chat_id=message.chat.id,
        channel=channel,
    )
    status = await message.answer("⏳ Tahlil qilinmoqda... / Анализирую...")
    try:
        response, elapsed = await asyncio.wait_for(
            asyncio.to_thread(ask_logged, question, "telegram", user_id), timeout=80
        )
    except asyncio.TimeoutError:
        relay.answer(
            question=question,
            answer="⏳ 80 soniyada javob topilmadi (timeout).",
            seconds=80.0,
            lang="—",
            intent="timeout",
            channel=channel,
        )
        await status.edit_text(
            "Javobni 80 soniyada hisoblab bo‘lmadi — savolni aniqroq yozing.\n"
            "Не удалось вычислить ответ за 80 секунд — уточните вопрос."
        )
        return
    except Exception:
        logging.exception("question failed")
        relay.answer(
            question=question,
            answer="⚠️ Texnik xatolik (exception). Batafsil: logs/bot.out.",
            seconds=0.0,
            lang="—",
            intent="error",
            channel=channel,
        )
        await status.edit_text(
            "Kechirasiz, texnik xatolik yuz berdi. Qayta urinib ko‘ring.\n"
            "Извините, произошла техническая ошибка. Попробуйте ещё раз."
        )
        return

    relay.answer(
        question=question,
        answer=response.answer,
        seconds=elapsed,
        lang=response.lang,
        intent=response.intent,
        sql=response.sql,
        filters=response.filters,
        channel=channel,
    )

    parts = _styled_parts(response.answer)
    timing = (
        f"⏱ Javob vaqti: {elapsed:.2f} s" if response.lang == "uz" else f"⏱ Время ответа: {elapsed:.2f} с"
    )
    parts[-1] = f"{parts[-1]}\n\n<i>{timing}</i>"
    markup = None
    if response.sql:
        key = f"{message.chat.id}:{status.message_id}"
        _remember(key, response.lang, response.sql, response.filters)
        markup = _explain_keyboard(key, response.lang)
    await status.edit_text(
        parts[0], parse_mode=ParseMode.HTML, reply_markup=markup if len(parts) == 1 else None
    )
    for index, part in enumerate(parts[1:], start=1):
        await message.answer(
            part, parse_mode=ParseMode.HTML, reply_markup=markup if index == len(parts) - 1 else None
        )
    if len(response.rows) > CSV_MIN_ROWS:
        caption = "Batafsil jadval" if response.lang == "uz" else "Подробная таблица"
        await message.answer_document(
            BufferedInputFile(_rows_csv(response.rows), filename="uzex_result.csv"), caption=caption
        )
    logging.info("answered in %.2fs intent=%s", elapsed, response.intent)


async def question_handler(message: Message) -> None:
    question = (message.text or "").strip()
    if not question or question.startswith("/"):
        return
    user_id = message.from_user.id if message.from_user else message.chat.id
    now = time.monotonic()
    if now - _last_question.get(user_id, 0.0) < RATE_LIMIT_SECONDS:
        await message.answer("⏱ Bir oz kuting… / Подождите пару секунд…")
        return
    _last_question[user_id] = now
    username = message.from_user.username if message.from_user else None
    await _answer(message, question[:500], user_id, username)


async def example_callback(callback: CallbackQuery) -> None:
    index = int((callback.data or "ex:0").split(":", 1)[1])
    question = EXAMPLES[index] if 0 <= index < len(EXAMPLES) else EXAMPLES[0]
    await callback.answer()
    if callback.message is None:
        return
    await callback.message.answer(f"❓ {html.escape(question)}", parse_mode=ParseMode.HTML)
    await _answer(
        callback.message,
        question,
        callback.from_user.id,
        callback.from_user.username,
        channel="telegram-misol",
    )


async def explain_callback(callback: CallbackQuery) -> None:
    key = (callback.data or "").split(":", 1)[1]
    item = _explain.get(key)
    await callback.answer()
    if callback.message is None:
        return
    if item is None:
        await callback.message.answer("SQL topilmadi (bot qayta ishga tushgan). / SQL недоступен.")
        return
    lang, sql, filters = item
    title = "SQL-запрос" if lang == "ru" else "SQL sörov"
    filt = "Фильтры" if lang == "ru" else "Filtrlar"
    note = (
        "Запрос выполнен к DuckDB (read-only) по реестру сделок; все числа в ответе — из результата запроса."
        if lang == "ru"
        else "So‘rov DuckDB (faqat o‘qish) bazasida bitimlar reyestri bo‘yicha bajarildi; "
        "javobdagi barcha raqamlar shu natijadan olingan."
    )
    sql_text = " ".join(line.strip() for line in sql.strip().splitlines() if line.strip())
    body = (
        f"<b>{title}</b>\n{filt}: {html.escape(filters)}\n\n"
        f"<pre>{html.escape(sql_text[:3300])}</pre>\n{note}"
    )
    await callback.message.answer(body, parse_mode=ParseMode.HTML)


async def main() -> None:
    if not TELEGRAM_BOT_TOKEN:
        raise SystemExit(
            "TELEGRAM_BOT_TOKEN topilmadi. .env fayliga bot tokenini yozing "
            "(BotFather orqali olinadi)."
        )
    # warm up DuckDB + entity catalog so the first question is fast
    await asyncio.to_thread(ask_logged, "2025-yilda jami savdo summasi qancha?", "warmup")
    bot = Bot(TELEGRAM_BOT_TOKEN)
    try:  # text shown before the user presses Start
        await bot.set_my_description(BOT_DESCRIPTION[:512])
        await bot.set_my_short_description(BOT_SHORT_DESCRIPTION[:120])
    except Exception:  # noqa: BLE001
        logging.warning("could not set bot description")
    dispatcher = Dispatcher()
    dispatcher.message.register(start_handler, CommandStart())
    dispatcher.message.register(help_handler, Command("help"))
    dispatcher.message.register(question_handler, F.text)
    dispatcher.callback_query.register(example_callback, F.data.startswith("ex:"))
    dispatcher.callback_query.register(explain_callback, F.data.startswith("sql:"))
    await relay.start()
    print("Telegram bot polling boshlandi...")
    try:
        await dispatcher.start_polling(bot)
    finally:
        await relay.close()


if __name__ == "__main__":
    asyncio.run(main())

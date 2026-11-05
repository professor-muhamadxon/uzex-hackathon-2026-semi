"""Mirror incoming questions (and answers) into a Telegram monitoring chat.

Why a chat and not a bot-to-bot message: Telegram's Bot API never delivers
messages written by one bot to another bot ("Bad Request: bots can't send
messages to bots") and bots do not receive updates about other bots' messages.
So a bot cannot literally "receive" another bot's questions. The working pattern
is:

    user -> bot A (this agent) --copy--> monitoring chat, sent by bot B's token

The second bot is only a sender identity: its code stays untouched, you need its
token and a chat id (a group where it is a member, a channel where it is an
admin, or a private chat whose owner pressed /start).

Sending runs in one background worker with a bounded queue, so a slow or broken
Telegram call can never delay the user's answer. Every relay failure is logged
and swallowed.
"""

from __future__ import annotations

import asyncio
import html
import logging
from datetime import datetime

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramRetryAfter

from . import config

log = logging.getLogger(__name__)

TEXT_LIMIT = 3800
QUEUE_MAX = 1000


def _esc(value: object) -> str:
    return html.escape(str(value), quote=False)


def _short(value: object, limit: int = 300) -> str:
    text = " ".join(str(value).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _chat_id(raw: str) -> int | str:
    value = raw.strip()
    return int(value) if value.lstrip("-").isdigit() else value


def _chunks(text: str, limit: int = TEXT_LIMIT) -> list[str]:
    """Split on line boundaries so HTML tags of the header stay balanced."""
    chunks: list[str] = []
    current = ""
    for line in text.splitlines():
        if len(current) + len(line) + 1 > limit:
            if current:
                chunks.append(current)
            while len(line) > limit:
                chunks.append(line[:limit])
                line = line[limit:]
            current = line
        else:
            current = f"{current}\n{line}" if current else line
    if current:
        chunks.append(current)
    return chunks or [text[:limit]]


def _user(username: str | None, user_id: object) -> str:
    if username:
        return f"@{_esc(username)}"
    return f"id <code>{_esc(user_id)}</code>"


class Relay:
    """Best-effort mirror of Q/A exchanges to one monitoring chat."""

    def __init__(self) -> None:
        self.bot: Bot | None = None
        self.chat_id: int | str | None = None
        self.thread_id: int | None = None
        self._queue: asyncio.Queue[dict | None] | None = None
        self._worker: asyncio.Task | None = None
        self._dropped = 0
        self._failures = 0

    @property
    def enabled(self) -> bool:
        return bool(config.RELAY_ENABLED and config.RELAY_CHAT_ID and config.RELAY_BOT_TOKEN)

    async def start(self) -> None:
        if not self.enabled:
            log.info("relay: off (RELAY_CHAT_ID is empty or RELAY_ENABLED=0)")
            return
        self.chat_id = _chat_id(config.RELAY_CHAT_ID)
        self.thread_id = int(config.RELAY_THREAD_ID) if config.RELAY_THREAD_ID.isdigit() else None
        self.bot = Bot(config.RELAY_BOT_TOKEN)
        self._queue = asyncio.Queue(QUEUE_MAX)
        self._worker = asyncio.create_task(self._run(), name="relay-worker")
        try:
            me = await self.bot.get_me()
            chat = await self.bot.get_chat(self.chat_id)
            title = chat.title or chat.full_name or chat.username or ""
            log.info("relay: on -> chat %s (%s) as @%s", self.chat_id, title, me.username)
        except Exception as exc:  # noqa: BLE001 - diagnostics only, worker keeps trying
            log.warning("relay: startup check failed: %s", _short(exc, 200))

    async def close(self) -> None:
        if self._worker is None:
            return
        try:
            if self._queue is not None:
                try:
                    self._queue.put_nowait(None)
                except asyncio.QueueFull:
                    self._worker.cancel()
            await asyncio.wait_for(self._worker, timeout=10)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            self._worker.cancel()
        finally:
            if self.bot is not None:
                await self.bot.session.close()
            self._worker = None
            self.bot = None

    # -- public API used by the bot handlers ---------------------------------

    def question(
        self,
        *,
        question: str,
        user_id: object,
        username: str | None = None,
        chat_id: object = "",
        channel: str = "telegram",
    ) -> None:
        if not self.enabled:
            return
        head = (
            f"❓ <b>Yangi savol</b> · <code>{_esc(channel)}</code>\n"
            f"👤 {_user(username, user_id)} · chat <code>{_esc(chat_id)}</code>\n"
            f"🕒 {datetime.now():%d.%m.%Y %H:%M:%S}"
        )
        self._submit(f"{head}\n\n{_esc(_short(question, 1500))}")

    def answer(
        self,
        *,
        question: str,
        answer: str,
        seconds: float,
        lang: str,
        intent: str,
        sql: str = "",
        filters: str = "",
        channel: str = "telegram",
    ) -> None:
        if not self.enabled or not config.RELAY_ANSWERS:
            return
        head = (
            f"✅ <b>Javob</b> · {seconds:.2f} s · <code>{_esc(intent)}</code> · {_esc(lang)}"
            f" · <code>{_esc(channel)}</code>\n"
            f"❓ {_esc(_short(question))}"
        )
        body = f"{head}\n\n{_esc(answer)}"
        if filters:
            body += f"\n\n<i>{_esc(_short(filters, 400))}</i>"
        if config.RELAY_SQL and sql:
            body += f"\n\n<b>SQL</b>\n<pre>{_esc(sql.strip()[:1800])}</pre>"
        self._submit(body)

    # -- internals -----------------------------------------------------------

    def _submit(self, text: str) -> None:
        if self._worker is None or self._worker.done() or self._queue is None:
            return
        try:
            self._queue.put_nowait({"text": text})
        except asyncio.QueueFull:
            self._dropped += 1
            if self._dropped == 1 or self._dropped % 100 == 0:
                log.warning("relay: queue full, dropped %d message(s)", self._dropped)

    async def _run(self) -> None:
        assert self._queue is not None
        while True:
            item = await self._queue.get()
            try:
                if item is None:
                    return
                await self._send(item["text"])
                self._failures = 0
            except Exception as exc:  # noqa: BLE001 - monitoring must never crash the bot
                self._failures += 1
                if self._failures == 1 or self._failures % 50 == 0:
                    log.warning(
                        "relay: send failed (%d in a row): %s",
                        self._failures,
                        _short(exc, 200),
                    )
                await asyncio.sleep(2)  # do not hammer a chat the bot cannot post to
            finally:
                self._queue.task_done()

    async def _send(self, text: str) -> None:
        assert self.bot is not None and self.chat_id is not None
        for chunk in _chunks(text):
            attempt = 0
            while True:
                try:
                    await self.bot.send_message(
                        self.chat_id,
                        chunk,
                        parse_mode=ParseMode.HTML,
                        message_thread_id=self.thread_id,
                    )
                    break
                except TelegramRetryAfter as exc:
                    attempt += 1
                    if attempt > 1:
                        raise
                    await asyncio.sleep(min(exc.retry_after + 1, 30))


relay = Relay()

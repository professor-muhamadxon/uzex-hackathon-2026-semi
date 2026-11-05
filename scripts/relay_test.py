#!/usr/bin/env python3
"""Check the monitoring relay (RELAY_* settings) and send one test message.

    python scripts/relay_test.py          # token + chat + sendMessage
    python scripts/relay_test.py --find   # show chat ids the relay bot can see

Reads .env itself and talks to Telegram over plain HTTPS, so it runs even before
the venv dependencies are installed.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):  # Windows console may be cp1251
        _stream.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent


def load_env() -> None:
    """Same semantics as python-dotenv: fill os.environ, never override it."""
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env()

RELAY_CHAT_ID = os.environ.get("RELAY_CHAT_ID", "").strip()
RELAY_BOT_TOKEN = os.environ.get("RELAY_BOT_TOKEN", "").strip() or os.environ.get(
    "TELEGRAM_BOT_TOKEN", ""
).strip()
RELAY_THREAD_ID = os.environ.get("RELAY_THREAD_ID", "").strip()
RELAY_ENABLED = (
    os.environ.get("RELAY_ENABLED", "1").strip().lower() not in {"0", "false", "no", "off"}
    and bool(RELAY_CHAT_ID)
    and bool(RELAY_BOT_TOKEN)
)

API = "https://api.telegram.org/bot{token}/{method}"

HINTS = {
    "chat not found": (
        "chat_id xato yoki bot bu chatga qoʻshilmagan. Guruh/kanal idʼsi -100… bilan "
        "boshlanadi; shaxsiy chatda avval botga /start bosilgan boʻlishi kerak."
    ),
    "bot is not a member": "Ikkinchi botni guruhga aʼzo qiling (kanalda — administrator).",
    "bot was blocked": "Foydalanuvchi botni bloklagan: blokdan chiqarib, /start bosing.",
    "have no rights": "Kanalda botga “Post messages” huquqini bering.",
    "not enough rights": "Kanalda botga “Post messages” huquqini bering.",
    "bots can't send messages to bots": (
        "Bu chat boshqa botning shaxsiy chati — Telegram bot-botga xabar yuborishga ruxsat "
        "bermaydi. Monitoring uchun guruh, kanal yoki odamning shaxsiy chatini ishlating."
    ),
    "not a valid": "RELAY_CHAT_ID formati xato (masalan: -1001234567890 yoki @kanal).",
    "unauthorized": "RELAY_BOT_TOKEN xato. BotFather’dan tokenni qayta oling.",
    "conflict": (
        "Bot hozir getUpdates (polling) bilan band. --find uchun botni toʻxtating yoki "
        "chat idʼni guruhdan @userinfobot orqali oling."
    ),
}


def describe(description: str) -> str:
    lowered = description.lower()
    for needle, hint in HINTS.items():
        if needle in lowered:
            return hint
    return ""


def api(method: str, token: str, **params: object) -> dict:
    url = API.format(token=token, method=method)
    body = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None}).encode()
    request = urllib.request.Request(url, data=body if body else None)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        try:
            return json.load(exc)
        except Exception:  # noqa: BLE001
            return {"ok": False, "description": f"HTTP {exc.code}"}
    except urllib.error.URLError as exc:
        return {"ok": False, "description": f"network: {exc.reason}"}


def fail(result: dict) -> int:
    description = str(result.get("description", "nomaʼlum xatolik"))
    print(f"❌ {description}")
    hint = describe(description)
    if hint:
        print(f"   → {hint}")
    return 1


def find_chats(token: str) -> int:
    result = api("getUpdates", token, limit=100, timeout=0)
    if not result.get("ok"):
        return fail(result)
    seen: dict[int, tuple[str, str]] = {}
    for update in result.get("result", []):
        message = (
            update.get("message")
            or update.get("channel_post")
            or update.get("edited_message")
            or update.get("my_chat_member", {}).get("chat")
            or {}
        )
        chat = message.get("chat") if isinstance(message, dict) else None
        if chat:
            title = chat.get("title") or chat.get("full_name") or chat.get("username") or "—"
            seen[chat["id"]] = (chat.get("type", "?"), title)
    if not seen:
        print("Boʻsh. Guruhga/kanalga bitta xabar yozing, keyin qayta urinib koʻring.")
        print("Bot pollingda ishlayotgan boʻlsa, avval uni toʻxtating (409 Conflict).")
        return 0
    print("Koʻrilgan chatlar:\n")
    for chat_id, (kind, title) in seen.items():
        print(f"  RELAY_CHAT_ID={chat_id}   # {kind} · {title}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Monitoring relay testi")
    parser.add_argument("--find", action="store_true", help="getUpdates orqali chat idʼlarni koʻrsatish")
    args = parser.parse_args()

    if not RELAY_BOT_TOKEN:
        print("❌ RELAY_BOT_TOKEN ham, TELEGRAM_BOT_TOKEN ham boʻsh (.env).")
        return 1
    if ":" not in RELAY_BOT_TOKEN:
        print("❌ RELAY_BOT_TOKEN formati xato: 123456:ABC… koʻrinishida boʻlishi kerak.")
        return 1

    if args.find:
        return find_chats(RELAY_BOT_TOKEN)

    if not RELAY_CHAT_ID:
        print("❌ RELAY_CHAT_ID boʻsh — relay oʻchirilgan (.env).")
        print("   Chat idʼni topish: python scripts/relay_test.py --find")
        return 1

    print(f"Sozlama: RELAY_ENABLED={int(RELAY_ENABLED)} · chat={RELAY_CHAT_ID} · thread={RELAY_THREAD_ID or '—'}")

    me = api("getMe", RELAY_BOT_TOKEN)
    if not me.get("ok"):
        return fail(me)
    sender = me["result"]
    print(f"Yuboruvchi bot: @{sender.get('username')} (id {sender['id']})")

    chat = api("getChat", RELAY_BOT_TOKEN, chat_id=RELAY_CHAT_ID)
    if not chat.get("ok"):
        return fail(chat)
    info = chat["result"]
    title = info.get("title") or info.get("full_name") or info.get("username") or "—"
    print(f"Chat: {info['id']} · {info.get('type')} · {title}")

    sent = api(
        "sendMessage",
        RELAY_BOT_TOKEN,
        chat_id=RELAY_CHAT_ID,
        message_thread_id=RELAY_THREAD_ID or None,
        parse_mode="HTML",
        text=(
            "🧪 <b>Relay test</b>\n"
            f"Yuboruvchi: @{sender.get('username')}\n"
            f"Chat: <code>{info['id']}</code> · {info.get('type')}\n"
            "Agar bu xabarni koʻrsangiz, monitoring ishlaydi."
        ),
    )
    if not sent.get("ok"):
        return fail(sent)

    print("✅ Test xabari yuborildi.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

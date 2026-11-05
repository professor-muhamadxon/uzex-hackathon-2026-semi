"""Telegram presentation layer: turns a plain agent answer into readable Telegram HTML.

Only the text the bot sends changes; the agent answer (web / API / tests) stays plain.
The layout:

    <b>header line</b>                       section titles
    🥇 <b>1.</b> Name (INN <code>…</code>) — <b>12 147 ta</b>     ranked rows, medals for top 3
    • label: <b>value</b>                    bullet rows
    <b>numbers with units</b>                the figures people look for
    <i>ℹ️ annulled deals note</i>
    <blockquote expandable>🔎 how it was calculated, filter, source</blockquote>   collapsed

Everything is HTML-escaped first, so tags can only come from this module.
"""

from __future__ import annotations

import html
import re

MEDALS = {1: "🥇", 2: "🥈", 3: "🥉"}

# lines that explain the calculation: grouped into one collapsed quote
META_PREFIXES = (
    "🔎", "Filtr:", "Фильтр:", "Филтр:", "Manba:", "Источник:", "Манба:", "Qanday hisoblandi",
    "Как посчитано", "Қандай ҳисобланди",
)
NOTE_PREFIXES = (
    "Annul qilingan", "Аннулирован", "Аннул қилинган", "Annul qilinganlar", "⚠", "ℹ",
)
UNITS = (
    r"so‘m|so'm|сўм|сум|so‘mga|ta|та|%|\$|USD|dollar|доллар|сделок|сделки|сделка|контрактов|контракта|"
    r"kontrakt|контракт|bitim|битим|tonna|тонн|kg|кг|litr|литр|dona|штук"
)
NUM_RE = re.compile(
    rf"(?<![\w.,/])(\$?\d{{1,3}}(?:[   ]\d{{3}})+(?:[.,]\d+)?|\$?\d+(?:[.,]\d+)?)"
    rf"(?![\d]*[.]\d{{2}}[.]\d{{4}})(\s?(?:{UNITS})\b|%)?"
)
CODE_RE = re.compile(r"\b(INN|ИНН|TNVED|ТНВЭД)(:?\s)(\d{6,14})\b")
BROKER_RE = re.compile(r"\((BK\d+)\)")
DATE_RE = re.compile(r"\b\d{2}\.\d{2}\.\d{4}\b|\b\d{4}-\d{2}(?:-\d{2})?\b")


def _bold_numbers(esc: str) -> str:
    """Bold figures (with their unit) but never codes, dates or ids."""
    keep: list[str] = []

    def put(value: str) -> str:
        keep.append(value)
        return "" + chr(0xE100 + len(keep) - 1) + ""

    protected = DATE_RE.sub(lambda m: put(m.group(0)), esc)
    protected = CODE_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}" + put(f"<code>{m.group(3)}</code>"), protected)
    protected = BROKER_RE.sub(lambda m: "(" + put(f"<code>{m.group(1)}</code>") + ")", protected)

    def bold(match: re.Match) -> str:
        return f"<b>{match.group(1)}{match.group(2) or ''}</b>"

    out = NUM_RE.sub(bold, protected)
    return re.sub("(.)", lambda m: keep[ord(m.group(1)) - 0xE100], out)


def _codes_only(esc: str) -> str:
    esc = CODE_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}<code>{m.group(3)}</code>", esc)
    return BROKER_RE.sub(lambda m: f"(<code>{m.group(1)}</code>)", esc)


def _is_meta(line: str) -> bool:
    return line.startswith(META_PREFIXES)


def _style_line(line: str, first: bool) -> str:
    esc = html.escape(line, quote=False)
    stripped = line.strip()

    # ranked row: "1. Name (INN: 123) — value"
    ranked = re.match(r"^(\d{1,3})\.\s+(.*?)(\s+—\s+)(.+)$", stripped)
    if ranked:
        number, name, _sep, value = ranked.groups()
        medal = MEDALS.get(int(number), "▫️")
        name_html = _codes_only(html.escape(name, quote=False))
        return f"{medal} <b>{number}.</b> {name_html} — <b>{html.escape(value, quote=False)}</b>"

    # bullet row: "• label: value"
    if stripped.startswith("•"):
        body = stripped.lstrip("•").strip()
        label, sep, value = body.partition(": ")
        if sep and len(label) <= 90:
            return f"• <b>{html.escape(label, quote=False)}</b>: {_bold_numbers(html.escape(value, quote=False))}"
        return "• " + _bold_numbers(html.escape(body, quote=False))

    # section header: ends with ":" (Top 5 ..., Holatlar bo‘yicha:, По регионам: ...)
    if stripped.endswith(":") and len(stripped) <= 120:
        return f"📊 <b>{esc}</b>" if first else f"<b>{esc}</b>"

    # trend / single-line label: value
    if stripped.startswith(NOTE_PREFIXES):
        mark = "" if stripped.startswith(("⚠", "ℹ")) else "ℹ️ "
        return f"<i>{mark}{esc}</i>"

    if stripped.startswith("⏱"):
        return f"<i>{esc}</i>"

    return _bold_numbers(esc)


def style(text: str) -> str:
    """Plain answer text -> Telegram HTML (parse_mode=HTML)."""
    out: list[str] = []
    meta: list[str] = []
    first = True

    def flush_meta() -> None:
        if meta:
            out.append("<blockquote expandable><i>" + "\n".join(meta) + "</i></blockquote>")
            meta.clear()

    for raw in text.split("\n"):
        line = raw.rstrip()
        if not line.strip():
            if not meta:
                out.append("")
            continue
        if _is_meta(line.strip()):
            meta.append(html.escape(line.strip(), quote=False))
            continue
        flush_meta()
        out.append(_style_line(line, first))
        first = False
    flush_meta()
    result = "\n".join(out)
    return re.sub(r"\n{3,}", "\n\n", result).strip()

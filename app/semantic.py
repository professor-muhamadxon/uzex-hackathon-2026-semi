"""Optional small-LLM *meaning* layer.

The LLM never writes SQL and never produces numbers. For questions the rules could not
classify it only fills a tiny JSON form (intent, metric, grouping, ...). Every field is
checked against a fixed list, the product word is resolved through the product catalog,
and the answer is then computed by the normal SQL templates. Anything the form cannot
express -> "unsupported" -> an honest "not found / not supported" reply.
"""

from __future__ import annotations

import json
import logging
import re

from .catalog import find_product_filters
from .config import LLM_ENABLED
from .llm import _client_instance, _reasoning_kwargs, _SEMAPHORE, LLM_MODEL

log = logging.getLogger(__name__)

INTENTS = {"total", "top", "breakdown", "usd_rate", "unsupported"}
METRICS = {"amount", "count", "volume", "avg_price", "usd"}
GROUPS = {"company", "product", "region", "broker", "weekday"}
ROLES = {"seller", "buyer", "both"}

SYSTEM = """You classify questions about a commodity-exchange deal registry (Uzbek or Russian).
Return ONLY a JSON object, no text. Fields:
  "intent": one of
     "total"      - one number for a period/filter (sum, count, volume, average price)
     "top"        - ranking of companies/products/regions/brokers
     "breakdown"  - the same metric split by region, product or weekday
     "usd_rate"   - the USD exchange rate
     "unsupported"- anything else (margins, profit, deadlines, delivery times, weather, ...)
  "metric": "amount" | "count" | "volume" | "avg_price" | "usd"
  "group": "company" | "product" | "region" | "broker" | "weekday" | null
  "role": "seller" | "buyer" | "both"
  "order": "desc" | "asc"
  "product_word": the product named in the question, copied as written, or null
  "year": integer or null
Examples:
  "Qaysi tovar eng ko'p sotilgan?" -> {"intent":"top","metric":"count","group":"product","role":"both","order":"desc","product_word":null,"year":null}
  "Кто купил больше всего цемента в 2025?" -> {"intent":"top","metric":"amount","group":"company","role":"buyer","order":"desc","product_word":"цемента","year":2025}
  "Какая у продавцов маржа?" -> {"intent":"unsupported","metric":"amount","group":null,"role":"both","order":"desc","product_word":null,"year":null}
Never invent values. If unsure use "unsupported"."""


def _call(question: str) -> dict | None:
    if not LLM_ENABLED:
        return None
    try:
        with _SEMAPHORE:
            response = _client_instance().chat.completions.create(
                model=LLM_MODEL,
                temperature=0,
                max_tokens=200,
                response_format={"type": "json_object"},
                **_reasoning_kwargs(),
                messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": question}],
            )
        text = response.choices[0].message.content or ""
        match = re.search(r"\{.*\}", text, re.DOTALL)
        return json.loads(match.group(0)) if match else None
    except Exception as exc:  # noqa: BLE001 - LLM is optional; never break the bot
        log.warning("semantic LLM unavailable: %s", exc)
        return None


def validate(raw: dict | None) -> dict | None:
    """Keep only whitelisted values; return None if the form is unusable."""
    if not isinstance(raw, dict):
        return None
    intent = raw.get("intent")
    if intent not in INTENTS:
        return None
    out = {
        "intent": intent,
        "metric": raw.get("metric") if raw.get("metric") in METRICS else "amount",
        "group": raw.get("group") if raw.get("group") in GROUPS else None,
        "role": raw.get("role") if raw.get("role") in ROLES else "both",
        "order": "asc" if raw.get("order") == "asc" else "desc",
        "product_word": None,
        "year": None,
    }
    word = raw.get("product_word")
    if isinstance(word, str) and 2 <= len(word.strip()) <= 40:
        out["product_word"] = word.strip()
    year = raw.get("year")
    if isinstance(year, int) and 1900 <= year <= 2100:
        out["year"] = year
    if intent == "top" and out["group"] in (None, "weekday"):
        out["group"] = "company"
    if intent == "breakdown" and out["group"] not in {"region", "product", "weekday"}:
        return None
    return out


def apply_semantic(parsed, form: dict) -> bool:
    """Write the validated form into ParsedQuery. Returns False if it can't be answered."""
    parsed.metric = form["metric"]
    parsed.order_asc = form["order"] == "asc"
    if form["role"] != "both":
        parsed.company_role = form["role"]
    if form["year"] and parsed.year_from is None and parsed.date_from is None:
        parsed.year_from = parsed.year_to = form["year"]
    if form["product_word"] and not parsed.product.tnveds:
        product = find_product_filters(form["product_word"])
        if not product.tnveds and not product.categories:
            parsed.not_found_reason = "product_unknown"
            parsed.not_found_detail = form["product_word"]
            return True
        parsed.product = product
    intent = form["intent"]
    if intent == "unsupported":
        return False
    if intent == "total":
        parsed.intent = "total"
    elif intent == "top":
        parsed.intent, parsed.group = "top", form["group"]
    elif intent == "breakdown":
        parsed.intent = "breakdown"
        parsed.extra = {"dim": form["group"]}
    elif intent == "usd_rate":
        parsed.intent = "usd_rate"
        parsed.extra = {}
    return True


def semantic_parse(question: str, parsed) -> bool | None:
    """True = parsed filled and answerable, False = LLM says unsupported, None = LLM unavailable."""
    form = validate(_call(question))
    if form is None:
        return None
    return apply_semantic(parsed, form)

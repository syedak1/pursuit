"""LLM gap-fill: read the memo for fields the rules could not find.

The LLM is a second reader, not an oracle. It runs only on contracts that have
memo text and are missing a term, an end date, a vendor, or a procurement route.
Its answers are held to the same standard as the rules:

1. Every value must come with a verbatim quote from the memo.
2. The quote must be found in the memo (clock/text.py: verify). If not, the value is dropped.
3. "Not stated" (null) is always an allowed answer, and the prompt says so plainly.
   Models fabricate most often when asked about things that are not there.
4. The model is told not to do arithmetic. Dates are derived in build.py, in code, with
   the derivation shown to the user.

Responses are cached by prompt hash under data/cache/llm/, so re-runs are free and
the demo is reproducible.

Requires: pip install anthropic, and ANTHROPIC_API_KEY in the environment.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections import Counter
from pathlib import Path

from .rules import vendor_key
from .text import normalize, verify

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "cache" / "llm"
DEFAULT_MODEL = os.environ.get("CLOCK_MODEL", "claude-haiku-5-5")
MAX_CHARS = 18_000  # memos are short; this bounds cost on the occasional giant one

SYSTEM = """You extract contract facts from city council documents for a procurement database.
You are careful and literal. You never guess. If a fact is not stated in the document, you return null for it.
Every non-null value must be supported by a quote copied character-for-character from the document:
no paraphrasing, no ellipses, no fixing typos. Keep each quote to one sentence or clause (under 50 words)."""

INSTRUCTIONS = """Read this Ann Arbor City Council resolution and staff memo, then call the record_contract tool.

Only report what the document states about THIS contract (not prior contracts, not other vendors):
- vendor: the company the city is contracting with, as written.
- term_months: the length of the contract term, in months, only if a length is stated ("three-year agreement" = 36). Do not count renewal options in the term.
- start_date / end_date: only if a calendar date is stated for when the contract starts or ends (YYYY-MM-DD). Do not compute dates.
- renewals: only if renewal or extension options are stated.
- route: how the vendor was selected, only if stated: "competitive" (RFP, ITB, bids), "cooperative" (MiDEAL, Sourcewell, another agency's contract), "sole_source", or "emergency".

Use null whenever the document does not say. That is a normal, correct answer.

TITLE: {title}

DOCUMENT:
{text}"""

def _field(value_schema: dict) -> dict:
    return {
        "type": ["object", "null"],
        "properties": {"value": value_schema, "quote": {"type": "string", "description": "verbatim from the document"}},
        "required": ["value", "quote"],
    }


TOOL = {
    "name": "record_contract",
    "description": "Record contract facts stated in the document. Use null for anything not stated.",
    "input_schema": {
        "type": "object",
        "properties": {
            "vendor": _field({"type": "string"}),
            "term_months": _field({"type": "integer", "minimum": 1, "maximum": 120}),
            "start_date": _field({"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}$"}),
            "end_date": _field({"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}$"}),
            "renewals": _field({
                "type": "object",
                "properties": {"count": {"type": "integer"}, "months_each": {"type": "integer"}},
                "required": ["count", "months_each"],
            }),
            "route": _field({"type": "string", "enum": ["competitive", "cooperative", "sole_source", "emergency"]}),
        },
        "required": ["vendor", "term_months", "start_date", "end_date", "renewals", "route"],
    },
}

_MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
           "October", "November", "December"]


_ROUTE_WORDS = {
    "sole_source": r"sole",
    "cooperative": r"mideal|sourcewell|naspo|cooperative|piggyback|state of michigan|consortium|omnia",
    "competitive": r"rfp|itb|rfq|bid|proposal|competitive",
    "emergency": r"emergency",
}


def _plausible(field: str, value, quote: str) -> bool:
    """Cheap consistency checks between a value and its own quote.

    A verified quote proves the sentence exists; these checks catch the model
    attaching a real sentence to the wrong value.
    """
    q = quote.lower()
    if field in ("start_date", "end_date"):
        y, m, d = value.split("-")
        month = _MONTHS[int(m) - 1].lower()
        return y in q and (month in q or f"{int(m)}/" in q)
    if field == "term_months":
        return bool(re.search(r"\b(year|month)", q))
    if field == "renewals":
        return bool(re.search(r"renew|extension|extend|option", q))
    if field == "route":
        return bool(re.search(_ROUTE_WORDS[value], q))
    if field == "vendor":
        k = vendor_key(value)
        return bool(k) and k.split()[0] in q
    return True


def _call(client, model: str, title: str, text: str) -> dict:
    prompt = INSTRUCTIONS.format(title=title, text=text[:MAX_CHARS])
    key = hashlib.sha256(f"{model}\n{SYSTEM}\n{prompt}".encode()).hexdigest()
    path = CACHE / f"{key}.json"
    if path.exists():
        return json.loads(path.read_text())
    resp = client.messages.create(
        model=model,
        max_tokens=1024,
        system=SYSTEM,
        tools=[TOOL],
        tool_choice={"type": "tool", "name": "record_contract"},
        messages=[{"role": "user", "content": prompt}],
    )
    out = next(b.input for b in resp.content if b.type == "tool_use")
    CACHE.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"model": model, "result": out, "usage": resp.usage.model_dump()}, indent=1))
    return {"model": model, "result": out, "usage": resp.usage.model_dump()}


def fill_gaps(events: dict, rows: dict, texts: dict, evidence: list, model: str | None = None) -> Counter:
    import anthropic  # imported here so the rules-only build needs no third-party packages

    model = model or DEFAULT_MODEL
    client = anthropic.Anthropic()
    stats: Counter = Counter()
    wanted = ("vendor", "term_months", "start_date", "end_date", "renewals", "route")

    for mid, ev in events.items():
        if ev["event_type"] != "contract" or mid not in texts or ev.get("class") == "one_time":
            continue  # one-time purchases have no renewal date to find
        missing = [f for f in wanted if not ev.get(f)]
        if not any(f in missing for f in ("term_months", "end_date")) and "route" not in missing:
            continue
        stats["llm_calls"] += 1
        try:
            res = _call(client, model, normalize(rows[mid]["title"]), texts[mid])
        except Exception as e:  # one bad call should not sink the build
            stats["llm_errors"] += 1
            print(f"  llm error on {mid}: {e!r}")
            continue
        for fld in missing:
            item = (res["result"] or {}).get(fld)
            if not item or item.get("value") in (None, "", {}):
                stats[f"llm_null_{fld}"] += 1
                continue
            quote = item.get("quote") or ""
            ok, qs, qe = verify(quote, texts[mid])
            if not ok:
                stats["llm_quote_not_found"] += 1
                continue
            if not _plausible(fld, item["value"], quote):
                stats["llm_quote_mismatch"] += 1
                continue
            ev[fld] = item["value"]
            if fld == "vendor":
                ev["vendor_key"] = vendor_key(item["value"])
            evidence.append({
                "event_id": mid, "field": fld, "value": item["value"], "source": "text", "method": "llm",
                "rule": res["model"], "verified": True, "quote": texts[mid][qs:qe], "q_start": qs, "q_end": qe,
                "m_start": qs, "m_end": qe, "derivation": None,
            })
            stats[f"llm_added_{fld}"] += 1
    return stats

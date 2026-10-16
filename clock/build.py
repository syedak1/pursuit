"""Turn the raw crawl into the database and the site's data file.

    python -m clock.build                  # rules only: free, offline, deterministic
    python -m clock.build --llm            # also run the LLM pass on what rules missed
    python -m clock.build --client detroit

Pipeline: raw JSON -> matters/texts -> rule extraction -> (optional) LLM gap-fill
-> quote verification -> derived dates -> SQLite -> web/data/site.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

from . import db as dbm
from .rules import (CATEGORIES, Hit, categorize, contract_class, is_funding, is_intergovernmental, is_purchase,
                    parse_auto_renew, parse_incumbent_since, parse_staff, parse_text, parse_title, title_fiscal_year, vendor_key)
from .text import context, normalize, verify

ROOT = Path(__file__).resolve().parent.parent
CITY_NAMES = {"a2gov": "Ann Arbor, MI"}
LEGISTAR_WEB = {"a2gov": "https://a2gov.legistar.com"}

# Legistar's "requester" is typed by staff, so one department appears under several spellings or
# under an old name. Grouping by the raw string would split its history; this maps each spelling to
# one display name. The raw value is kept in the matters table.
DEPARTMENT_ALIASES = {
    "15th District Court": "Fifteenth District Court",
    "Water Treament Plant Services": "Water Treatment Plant Services",
    "System Planning Unit": "Systems Planning Services",
    "Sustainability Office": "Sustainability and Innovations Unit",
    # An advisory body recommends; the department that scopes and pays is Parks and Recreation.
    "Park Advisory Commission": "Parks and Recreation Services",
}


def department(requester: str | None) -> str:
    r = (requester or "").strip()
    return DEPARTMENT_ALIASES.get(r, r) or "Unknown"


# What a resolution's Legistar status means for a contract. Only "approved" items are in force;
# "pending" ones are on an upcoming agenda (an early signal); the rest never took effect.
NOT_APPROVED = {"defeated", "rescinded", "withdrawn", "failed", "filed", "vetoed"}


def approval_state(status: str, passed_date: str | None) -> str:
    st = (status or "").strip().lower()
    if st in NOT_APPROVED:
        return "not_approved"
    if passed_date or st in ("passed", "adopted", "approved"):
        return "approved"
    return "pending"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def iso(d: str | None) -> str | None:
    return d[:10] if d else None


def add_months(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 + months, 12)
    y += d.year
    m += 1
    # Clamp the day (Jan 31 + 1 month -> Feb 28/29).
    for day in (d.day, 30, 29, 28):
        try:
            return date(y, m, day)
        except ValueError:
            continue
    raise ValueError(d)


def repair_date(raw: str | None, fallback: str | None, today: date) -> tuple[str | None, str | None]:
    """Legistar sometimes has typos like '5012-05-07'. Repair from the agenda date and say so."""
    d = iso(raw)
    if d is None:
        return None, None
    year = int(d[:4])
    if 2000 <= year <= today.year + 2:
        return d, None
    fb = iso(fallback)
    if fb and 2000 <= int(fb[:4]) <= today.year + 2:
        return fb, f"intro date {d} is implausible; used agenda date {fb}"
    return None, f"intro date {d} is implausible and no usable fallback; left blank"


def legistar_url(client: str, m: dict) -> str:
    # LegislationDetail.aspx wants the web site's own ID/GUID pair, which is not always the API's
    # (Ann Arbor answers "Invalid parameters!"). gateway.aspx takes the API MatterId and redirects.
    base = LEGISTAR_WEB.get(client, f"https://{client}.legistar.com")
    return f"{base}/gateway.aspx?M=L&ID={m['MatterId']}"


# ---------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------

def build(client: str, use_llm: bool = False, today: date | None = None, model: str | None = None) -> dict:
    today = today or date.today()
    raw = ROOT / "data" / "raw" / client
    matters = json.loads((raw / "matters.json").read_text())
    con = dbm.connect(ROOT / "data" / "clock.db")
    dbm.reset(con)
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    stats: Counter = Counter()

    # 1. matters, texts, attachments --------------------------------------
    rows = {}
    for m in matters:
        intro, issue = repair_date(m.get("MatterIntroDate"), m.get("MatterAgendaDate"), today)
        if issue:
            con.execute("INSERT INTO quality VALUES (?,?,?,?)", (m["MatterId"], "bad_date", m.get("MatterIntroDate"), issue))
            stats["dates_repaired"] += 1
        row = {
            "matter_id": m["MatterId"], "client": client, "guid": m.get("MatterGuid"), "file": m.get("MatterFile"),
            "title": m.get("MatterTitle") or m.get("MatterName") or "", "status": (m.get("MatterStatusName") or "").strip(),
            "intro_date": intro, "agenda_date": iso(m.get("MatterAgendaDate")), "passed_date": iso(m.get("MatterPassedDate")),
            "requester": (m.get("MatterRequester") or "").strip() or None, "enactment": m.get("MatterEnactmentNumber"),
            "url": legistar_url(client, m),
        }
        if not row["title"]:
            con.execute("INSERT INTO quality VALUES (?,?,?,?)", (m["MatterId"], "no_title", "", "skipped"))
            continue
        rows[m["MatterId"]] = row
        con.execute(
            "INSERT INTO matters VALUES (:matter_id,:client,:guid,:file,:title,:status,:intro_date,:agenda_date,"
            ":passed_date,:requester,:enactment,:url)", row)

    texts: dict[int, str] = {}
    for p in (raw / "texts").glob("*.json"):
        d = json.loads(p.read_text())
        plain = ((d.get("text") or {}).get("MatterTextPlain") or "").strip()
        if d["MatterId"] in rows and plain:
            t = normalize(plain)
            texts[d["MatterId"]] = t
            con.execute("INSERT INTO texts VALUES (?,?,?)", (d["MatterId"], t, hashlib.sha256(t.encode()).hexdigest()))
    attachments: dict[int, list[dict]] = defaultdict(list)
    for p in (raw / "attachments").glob("*.json"):
        mid = int(p.stem)
        for a in json.loads(p.read_text()) or []:
            item = {"name": a.get("MatterAttachmentName"), "url": a.get("MatterAttachmentHyperlink")}
            if mid in rows and item["url"]:
                attachments[mid].append(item)
                con.execute("INSERT INTO attachments VALUES (?,?,?)", (mid, item["name"], item["url"]))
    stats["matters"], stats["texts"] = len(rows), len(texts)

    # 2. rule extraction ------------------------------------------------------
    events: dict[int, dict] = {}
    evidence: list[dict] = []

    def add_evidence(eid: int, h: Hit, source: str, src_text: str, method: str = "rule") -> None:
        # We know exactly where the quote sits (h.quote_start..end); verify() is the independent check
        # that the text we will show really occurs in the source. Same sentence can appear twice
        # (memo and resolution repeat each other), so keep our own offsets rather than the first hit.
        qs, qe = h.quote_start, h.quote_end
        quote = src_text[qs:qe]
        ok = verify(quote, src_text)[0] and qs <= h.start and h.end <= qe
        evidence.append({
            "event_id": eid, "field": h.field, "value": h.value, "source": source, "method": method,
            "rule": h.rule, "verified": ok, "quote": quote, "q_start": qs, "q_end": qe,
            "m_start": h.start, "m_end": h.end, "derivation": None,
        })
        stats["quotes_verified" if ok else "quotes_rejected"] += 1

    for mid, row in rows.items():
        title = normalize(row["title"])
        hits = parse_title(title)
        if is_purchase(title, hits):
            etype = "contract"
        elif is_funding(title):
            etype = "funding"
        else:
            if is_intergovernmental(title):
                stats["intergovernmental_skipped"] += 1
            continue
        f = {h.field: h for h in hits}
        ev = {
            "event_id": mid, "event_type": etype, "kind": f["kind"].value if "kind" in f else None,
            "vendor": f["vendor"].value if "vendor" in f and etype == "contract" else None,
            "amount": f["amount"].value if "amount" in f else None,
            "route": f["route"].value if "route" in f else None,
            "department": department(row["requester"]), "categories": categorize(title, row["requester"]),
            "start_date": None, "term_months": None, "end_date": None, "end_basis": None,
            "renewals": None, "max_end_date": None,
            "amount_basis": f["amount_basis"].value if "amount_basis" in f else None,
            "state": approval_state(row["status"], row["passed_date"]),
        }
        ev["vendor_key"] = vendor_key(ev["vendor"]) if ev["vendor"] else None
        ev["class"] = contract_class(title, ev["kind"]) if etype == "contract" else None
        if etype == "contract" and (fy := title_fiscal_year(title)):
            hits.append(fy)
            ev["_fy"] = fy.value
        for h in hits:
            if h.field == "vendor" and etype != "contract":
                continue
            add_evidence(mid, h, "title", title)

        # The memo's authors: who scoped this purchase inside the department.
        if mid in texts:
            for h in parse_staff(texts[mid]):
                add_evidence(mid, h, "text", texts[mid])

        # Memo text adds terms and dates; title evidence wins where both exist.
        if etype == "contract" and mid in texts:
            t = texts[mid]
            for h in parse_text(t):
                if h.field == "route" and ev["route"]:
                    continue
                if h.field == "route":
                    ev["route"] = h.value
                elif h.field == "term_months":
                    ev["term_months"] = h.value
                elif h.field == "start_date":
                    ev["start_date"] = h.value
                elif h.field == "end_date":
                    ev["end_date"] = h.value
                elif h.field == "renewals":
                    ev["renewals"] = h.value
                elif h.field == "prices_until":
                    ev["_prices_until"] = h.value
                elif h.field == "fy_range":
                    if "_fy" in ev:
                        continue  # the title's fiscal year is the more direct statement
                    ev["_fy"] = h.value
                add_evidence(mid, h, "text", t)
            if (since := parse_incumbent_since(t, ev["vendor"])):
                add_evidence(mid, since, "text", t)
            if (auto := parse_auto_renew(t)):
                add_evidence(mid, auto, "text", t)
        events[mid] = ev
    stats["contracts"] = sum(e["event_type"] == "contract" for e in events.values())
    for st in ("approved", "pending", "not_approved"):
        stats[f"contracts_{st}"] = sum(e["event_type"] == "contract" and e["state"] == st for e in events.values())
    stats["funding"] = sum(e["event_type"] == "funding" for e in events.values())

    # 3. optional LLM gap-fill -------------------------------------------------
    if use_llm:
        from .llm import fill_gaps

        added = fill_gaps(events, rows, texts, evidence, model=model)
        stats.update(added)

    # Drop anything that failed verification before it can reach the UI.
    rejected = [e for e in evidence if not e["verified"]]
    for e in rejected:
        ev = events.get(e["event_id"])
        if ev and e["field"] in ("term_months", "start_date", "end_date", "renewals", "route", "vendor"):
            key = {"renewals": "renewals"}.get(e["field"], e["field"])
            if ev.get(key) == e["value"]:
                ev[key] = None
    evidence = [e for e in evidence if e["verified"]]

    # 4. derived dates -------------------------------------------------------------
    for mid, ev in events.items():
        if ev["event_type"] != "contract":
            continue
        approved = rows[mid]["passed_date"] or rows[mid]["intro_date"]
        # A stated end date before council even approved this item belongs to a previous contract
        # ("the original lease expired on June 30, 2020"). Drop it rather than show a wrong clock.
        if ev["end_date"] and approved and ev["end_date"] < approved:
            con.execute("INSERT INTO quality VALUES (?,?,?,?)", (mid, "end_before_approval", ev["end_date"],
                        "ignored a stated end date that falls before council approval (likely a prior contract)"))
            ev["end_date"] = None
            evidence[:] = [e for e in evidence if not (e["event_id"] == mid and e["field"] == "end_date")]
            stats["end_dates_dropped_prior"] += 1
        end, basis, how = None, None, None
        if ev["end_date"]:
            end, basis, how = ev["end_date"], "stated", "End date stated in the memo."
        elif ev["term_months"] and ev["start_date"]:
            end = (add_months(date.fromisoformat(ev["start_date"]), ev["term_months"]) - _one_day()).isoformat()
            basis, how = "start+term", f"Start {ev['start_date']} + {ev['term_months']} months (both stated in the memo)."
        elif ev.get("_fy"):
            fy_to = ev["_fy"]["to"]
            end, basis = f"{fy_to}-06-30", "fiscal_years"
            src = "title" if ev["_fy"]["from"] == fy_to and any(
                e["event_id"] == mid and e["rule"] == "title.fiscal_year" for e in evidence) else "memo"
            how = (f"The {src} ties this agreement to fiscal year{'s through' if ev['_fy']['from'] != fy_to else ''} "
                   f"FY{fy_to}; Ann Arbor's fiscal year ends June 30, so FY{fy_to} ends {fy_to}-06-30.")
        elif ev["term_months"] and approved and ev.get("class") == "change":
            # An amendment's "five-year agreement" is the original agreement's term, which began years
            # before this vote. Adding it to the amendment's date would invent a later end. Log, don't guess.
            con.execute("INSERT INTO quality VALUES (?,?,?,?)", (mid, "amendment_term_not_dated", str(ev["term_months"]),
                        "amendment states a term but not when the original agreement started; no end date derived"))
            stats["amendment_terms_not_dated"] += 1
        elif ev["term_months"] and approved:
            end = (add_months(date.fromisoformat(approved), ev["term_months"]) - _one_day()).isoformat()
            basis = "approval+term"
            when = "council approval" if ev["state"] == "approved" else "its council date (not yet voted on)"
            how = (f"No start date stated, so we assume work starts at {when} ({approved}); "
                   f"+ {ev['term_months']} months.")
        elif ev.get("_prices_until") and ev["kind"] == "purchase_order":
            end, basis = ev["_prices_until"], "price_expiry"
            how = (f"No contract end is stated. The bid prices are firm only through {end}, so that is when "
                   f"the city needs new prices for this supply order: a rebid or a renegotiation.")
        ev.pop("_fy", None)
        ev.pop("_prices_until", None)
        if end:
            ev["end_date"], ev["end_basis"] = end, basis
            evidence.append({
                "event_id": mid, "field": "expires", "value": end, "source": "derived", "method": "derived",
                "rule": basis, "verified": True, "quote": None, "q_start": None, "q_end": None,
                "m_start": None, "m_end": None, "derivation": how,
            })
            stats[f"end_{basis}"] += 1
            r = ev["renewals"]
            if r:
                ev["max_end_date"] = add_months(date.fromisoformat(end), r["count"] * r["months_each"]).isoformat()

    for cls in ("term", "one_time", "change"):
        group = [e for e in events.values() if e.get("class") == cls]
        stats[f"class_{cls}"] = len(group)
        stats[f"class_{cls}_with_end"] = sum(1 for e in group if e["end_date"])

    # 5. write -------------------------------------------------------------------
    for ev in events.values():
        con.execute(
            "INSERT INTO events VALUES (:event_id,:event_type,:kind,:class,:vendor,:vendor_key,:amount,:route,:department,"
            ":categories,:start_date,:term_months,:end_date,:end_basis,:renewals,:max_end_date,:amount_basis,:state)",
            {**ev, "class": ev.get("class"), "categories": json.dumps(ev["categories"]), "renewals": json.dumps(ev["renewals"]) if ev["renewals"] else None},
        )
    for mid, ev in events.items():
        r = rows[mid]
        con.execute("INSERT INTO search VALUES (?,?,?,?,?,?)",
                    (mid, r["file"], r["title"], ev["vendor"] or "", ev["department"], texts.get(mid, "")))
    for e in evidence:
        con.execute(
            "INSERT INTO evidence (event_id,field,value,source,method,rule,verified,quote,q_start,q_end,m_start,m_end,derivation)"
            " VALUES (:event_id,:field,:value,:source,:method,:rule,:verified,:quote,:q_start,:q_end,:m_start,:m_end,:derivation)",
            {**e, "value": json.dumps(e["value"]), "verified": int(e["verified"])},
        )
    con.execute("INSERT INTO runs (started_utc, finished_utc, client, stats) VALUES (?,?,?,?)",
                (started, datetime.now(timezone.utc).isoformat(timespec="seconds"), client, json.dumps(stats)))
    con.commit()

    site = export(con, client, rows, texts, attachments, events, today)
    out = ROOT / "web" / "data" / "site.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    blob = json.dumps(site, ensure_ascii=False, separators=(",", ":"))
    out.write_text(blob)
    # Same data as a script, so web/index.html works when opened straight from disk (no server).
    (out.parent / "site.js").write_text("window.SITE=" + blob.replace("</", "<\\/") + ";\n")
    stats["site_kb"] = round(out.stat().st_size / 1024)
    from .feed import build_feeds

    import os

    stats["feed_entries"] = build_feeds(site, os.environ.get("CLOCK_SITE_URL", "../index.html"))["all"]
    return dict(stats)


def _one_day():
    from datetime import timedelta

    return timedelta(days=1)


# ---------------------------------------------------------------------------
# export for the web app
# ---------------------------------------------------------------------------

def export(con, client, rows, texts, attachments, events, today) -> dict:
    ev_rows = [dict(r) for r in con.execute("SELECT * FROM evidence ORDER BY evidence_id")]
    by_event: dict[int, list[dict]] = defaultdict(list)
    out_evidence = []
    for e in ev_rows:
        mid = e["event_id"]
        item = {
            "id": e["evidence_id"], "event": mid, "field": e["field"], "value": json.loads(e["value"]),
            "source": e["source"], "method": e["method"], "rule": e["rule"], "derivation": e["derivation"],
        }
        if e["source"] == "title":
            t = normalize(rows[mid]["title"])
            item["ctx"] = {"before": t[: e["m_start"]], "quote": t[e["m_start"]: e["m_end"]], "after": t[e["m_end"]:]}
        elif e["source"] == "text":
            t = texts[mid]
            c = context(t, e["q_start"], e["q_end"])
            # Mark the matched span inside the quote so the UI can underline exactly what the rule saw.
            c["mark"] = [e["m_start"] - e["q_start"], e["m_end"] - e["q_start"]]
            item["ctx"] = c
        out_evidence.append(item)
        by_event[mid].append(item)

    out_events = []
    for mid, ev in events.items():
        r = rows[mid]
        fields = {}
        for item in by_event.get(mid, []):
            fields.setdefault(item["field"], item["id"])
        out_events.append({
            "id": mid, "type": ev["event_type"], "file": r["file"], "title": r["title"], "status": r["status"],
            "introduced": r["intro_date"], "passed": r["passed_date"], "url": r["url"],
            "kind": ev["kind"], "class": ev.get("class"), "state": ev["state"], "amountBasis": ev["amount_basis"],
            "agenda": r["agenda_date"], "vendor": ev["vendor"], "vendorKey": ev["vendor_key"], "amount": ev["amount"],
            "route": ev["route"], "dept": ev["department"], "cats": ev["categories"],
            "start": ev["start_date"], "termMonths": ev["term_months"], "end": ev["end_date"],
            "endBasis": ev["end_basis"], "renewals": ev["renewals"], "maxEnd": ev["max_end_date"],
            "hasText": mid in texts, "attachments": attachments.get(mid, [])[:8], "fields": fields,
            "staff": [{"role": i["field"], **i["value"], "ev": i["id"]} for i in by_event.get(mid, [])
                      if i["field"] in ("prepared_by", "reviewed_by")],
        })
    out_events.sort(key=lambda e: e["introduced"] or "", reverse=True)

    quality = [dict(r) for r in con.execute("SELECT * FROM quality")]
    stats = json.loads(con.execute("SELECT stats FROM runs ORDER BY run_id DESC LIMIT 1").fetchone()[0])
    manifest_p = ROOT / "data" / "raw" / client / "manifest.json"
    manifest = json.loads(manifest_p.read_text()) if manifest_p.exists() else {}
    dates = sorted(r["intro_date"] for r in rows.values() if r["intro_date"])
    return {
        "meta": {
            "client": client, "city": CITY_NAMES.get(client, client), "today": today.isoformat(),
            "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            # Shown on the For Pursuit tab: CLOCK_REPO_URL=https://github.com/you/incumbent-clock python -m clock build
            "repo": os.environ.get("CLOCK_REPO_URL") or None,
            "crawled": manifest.get("finished_utc"), "since": manifest.get("since") or (dates[0] if dates else None),
            "through": dates[-1] if dates else None, "stats": stats,
        },
        "categories": {k: v["label"] for k, v in CATEGORIES.items()},
        "events": out_events,
        "evidence": out_evidence,
        # Full memo text for the Research tab's search; the quotes above index into these same strings.
        "texts": {str(e["id"]): texts[e["id"]] for e in out_events if e["id"] in texts},
        "quality": quality,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Build data/clock.db and web/data/site.json from the raw crawl.")
    ap.add_argument("--client", default="a2gov")
    ap.add_argument("--llm", action="store_true", help="fill gaps with an LLM (needs ANTHROPIC_API_KEY)")
    ap.add_argument("--model", default=None, help="model for --llm (default: see clock/llm.py)")
    ap.add_argument("--today", default=None, help="pretend today is YYYY-MM-DD (for reproducible demos)")
    args = ap.parse_args(argv)
    if args.llm:
        # Fail fast with a clear message instead of one error per memo.
        import os
        try:
            import anthropic  # noqa: F401
        except ImportError:
            raise SystemExit("--llm needs the Anthropic client: pip install anthropic")
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise SystemExit("--llm needs an API key: export ANTHROPIC_API_KEY=... (from console.anthropic.com), then run again")
    today = date.fromisoformat(args.today) if args.today else None
    stats = build(args.client, use_llm=args.llm, today=today, model=args.model)
    width = max(len(k) for k in stats)
    for k, v in sorted(stats.items()):
        print(f"  {k:<{width}}  {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

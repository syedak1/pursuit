"""Atom feeds of new signals, one per market, so a team can follow a market without opening the site.

    python -m clock.feed            # writes web/feeds/<market>.xml and web/feeds/all.xml

Any feed reader works, and so does Slack ("/feed subscribe <url>") or an RSS-to-email service.
The nightly GitHub Action rebuilds these with the site, so subscribers see each change the morning
after it reaches Legistar.

Three kinds of entry, each with a stable id so a reader shows it once:
    window    an approved service contract whose end date is now within 18 months
    pending   a contract or funding item on an upcoming council agenda (not yet voted on)
    approved  a contract or funding item council approved in the last 90 days
Each entry says where its facts came from and links to the record on Legistar.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
ATOM = "http://www.w3.org/2005/Atom"
WINDOW_MONTHS = 18
RECENT_DAYS = 90


def _months_before(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 - months, 12)
    return date(d.year + y, m + 1, min(d.day, 28))


def _day(d: date, with_day: bool = True) -> str:
    return f"{d:%b} {d.day}, {d.year}" if with_day else f"{d:%b} {d.year}"


def _money(n) -> str:
    if n is None:
        return "amount not stated"
    return f"${n / 1e6:.1f}M" if n >= 1e6 else f"${n / 1e3:.0f}K" if n >= 1e4 else f"${n:,.0f}"


def entries(site: dict) -> list[dict]:
    today = date.fromisoformat(site["meta"]["today"])
    ev = {e["id"]: e for e in site["evidence"]}
    out = []
    for e in site["events"]:
        quote = lambda f: (ev[e["fields"][f]].get("ctx") or {}).get("quote") if f in e["fields"] else None  # noqa: E731
        who = e["vendor"] or "A vendor not named in the title"
        facts = [f"Department: {e['dept']}", f"Amount: {_money(e['amount'])}" + (f" ({e['amountBasis']})" if e.get("amountBasis") not in (None, "stated") else ""),
                 f"Award method: {(e['route'] or 'not stated').replace('_', ' ')}"]
        if e["type"] == "contract" and e["state"] == "approved" and e.get("class") != "one_time" and e["end"]:
            end = date.fromisoformat(e["end"])
            if today < end and (end - today) <= timedelta(days=WINDOW_MONTHS * 30.44):
                entered = max(_months_before(end, WINDOW_MONTHS), date.fromisoformat((e["passed"] or e["introduced"])[:10]))
                if True:
                    opts = e.get("renewals")
                    after = f" Renewal options could extend it to {e['maxEnd']}." if opts and e.get("maxEnd") else " No renewal options stated."
                    out.append({
                        "id": f"{e['file']}:window", "kind": "window", "updated": entered.isoformat(), "cats": e["cats"],
                        "title": f"Ends {_day(end, False)}: {who} ({e['dept']})",
                        "summary": f"{who}'s {(e['kind'] or 'contract').replace('_', ' ')} with {e['dept']} ends {_day(end)} ({e['endBasis']}).{after}",
                        "facts": facts + [f"End date basis: {e['endBasis']}"], "quote": quote("end_date") or quote("term_months") or quote("fy_range"),
                        "url": e["url"],
                    })
        if e["state"] == "pending":
            when = e.get("agenda") or e["introduced"]
            out.append({
                "id": f"{e['file']}:pending", "kind": "pending", "updated": (when or site["meta"]["today"])[:10], "cats": e["cats"],
                "title": f"On the agenda{' ' + _day(date.fromisoformat(when[:10])) if when else ''}: {e['title'][:140]}",
                "summary": "Not yet voted on. " + e["title"], "facts": facts, "quote": None, "url": e["url"],
            })
        if e["state"] == "approved" and e["passed"]:
            passed = date.fromisoformat(e["passed"][:10])
            if (today - passed).days <= RECENT_DAYS:
                out.append({
                    "id": f"{e['file']}:approved", "kind": "approved", "updated": passed.isoformat(), "cats": e["cats"],
                    "title": f"Approved {_day(passed)}: {e['title'][:140]}",
                    "summary": e["title"], "facts": facts, "quote": quote("vendor"), "url": e["url"],
                })
    return sorted(out, key=lambda x: x["updated"], reverse=True)


def write_feed(path: Path, title: str, items: list[dict], site_url: str, city: str) -> None:
    ET.register_namespace("", ATOM)
    feed = ET.Element(f"{{{ATOM}}}feed")
    ET.SubElement(feed, f"{{{ATOM}}}title").text = title
    ET.SubElement(feed, f"{{{ATOM}}}subtitle").text = f"New contract signals from {city} City Council records."
    ET.SubElement(feed, f"{{{ATOM}}}id").text = f"urn:incumbent-clock:{path.stem}"
    ET.SubElement(feed, f"{{{ATOM}}}updated").text = (items[0]["updated"] if items else "2000-01-01") + "T12:00:00Z"
    ET.SubElement(feed, f"{{{ATOM}}}link", href=site_url)
    for it in items[:200]:
        e = ET.SubElement(feed, f"{{{ATOM}}}entry")
        ET.SubElement(e, f"{{{ATOM}}}title").text = it["title"]
        ET.SubElement(e, f"{{{ATOM}}}id").text = f"urn:incumbent-clock:{it['id']}"
        ET.SubElement(e, f"{{{ATOM}}}updated").text = it["updated"] + "T12:00:00Z"
        ET.SubElement(e, f"{{{ATOM}}}link", href=it["url"])
        ET.SubElement(e, f"{{{ATOM}}}category", term=it["kind"])
        body = f"<p>{_esc(it['summary'])}</p><ul>" + "".join(f"<li>{_esc(f)}</li>" for f in it["facts"]) + "</ul>"
        if it["quote"]:
            body += f"<blockquote>{_esc(it['quote'])}</blockquote><p>Quoted word for word from the council record.</p>"
        ET.SubElement(e, f"{{{ATOM}}}content", type="html").text = body
    path.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(feed).write(path, encoding="utf-8", xml_declaration=True)


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_feeds(site: dict, site_url: str = "../index.html") -> dict:
    items = entries(site)
    city = site["meta"]["city"]
    out = WEB / "feeds"
    write_feed(out / "all.xml", f"Incumbent Clock: {city}, all markets", items, site_url, city)
    counts = {"all": len(items)}
    for key, label in site["categories"].items():
        mine = [i for i in items if key in i["cats"]]
        write_feed(out / f"{key}.xml", f"Incumbent Clock: {city}, {label}", mine, site_url, city)
        counts[key] = len(mine)
    return counts


if __name__ == "__main__":
    site = json.loads((WEB / "data" / "site.json").read_text())
    for k, n in build_feeds(site).items():
        print(f"  {k:<26} {n} entries")

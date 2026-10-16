"""Crawl a city's Legistar Web API into a local raw-data cache.

Standard library only, so it runs anywhere with Python 3.9+:

    python fetch.py                            # Ann Arbor, FY2023 onward (or: python -m clock.fetch)
    python -m clock.fetch --client <slug>      # another Legistar client (its titles may need new rules)
    python -m clock.fetch --since 2024-07-01 --workers 4

What it saves (under data/raw/<client>/):
    matters.json             every City Council resolution since --since
    texts/<matter_id>.json   the legislation text (staff memo + resolution), plain text only
    attachments/<id>.json    attachment names and links (memos, contracts, bid tabs)
    manifest.json            when the crawl ran, with what settings, and what failed

Design notes
- The crawl is incremental: a matter whose text is cached is skipped unless Legistar's
  MatterLastModifiedUtc is newer than the copy we saved, so a nightly run only fetches
  what changed. A crash or Ctrl-C costs nothing. --refresh re-downloads everything.
- We only fetch texts for resolutions that look like contracts or purchases
  (see CONTRACT_HINT). Everything else is kept in matters.json for context but
  costs no extra requests.
- The RTF copy of each text is dropped on save; the plain-text copy is what the
  extractor quotes from, so that is the source of truth for evidence.
- Requests are polite: a small worker pool, retries with backoff, and an honest
  User-Agent. Legistar is a public API run by Granicus on behalf of the city.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import os
API = os.environ.get("LEGISTAR_API", "https://webapi.legistar.com/v1/{client}")
PAGE = 1000  # Legistar's hard cap per request
USER_AGENT = "incumbent-clock/0.1 (civic data project; github.com/<your-handle>/incumbent-clock)"

# A resolution is worth a text fetch if its title smells like spending money with a vendor.
CONTRACT_HINT = re.compile(
    r"\$|agreement|contract|purchase|order|amendment|change order|services|bid|rfp|itb|"
    r"sole source|cooperative|midael|mideal|sourcewell|naspo|lease|renewal|extension",
    re.I,
)



def get_json(url: str, tries: int = 4) -> object:
    """GET a URL and parse JSON, retrying transient failures with backoff."""
    last: Exception | None = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in (400, 401, 403, 404):
                # Not transient. 401/403 means this client needs an API token.
                raise
            last = e
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            if "CERTIFICATE_VERIFY_FAILED" in str(e):
                # Common on a Mac with Python from python.org: it ships without the certificates it needs.
                raise RuntimeError(
                    "Python can't verify Legistar's security certificate. On a Mac with Python from python.org, "
                    "open Applications > Python 3.x and double-click 'Install Certificates.command', then try again."
                ) from e
            last = e
        time.sleep(1.5 * (2**attempt))
    raise RuntimeError(f"giving up on {url}: {last}")


def odata(base: str, path: str, **params: str) -> str:
    safe = "',()"
    query = "&".join("$" + k + "=" + urllib.parse.quote(v, safe=safe) for k, v in params.items())
    return f"{base}/{path}?{query}"


# Contracts are approved by resolution. Ann Arbor also files some as "Resolution/Public Hearing".
DEFAULT_TYPES = ("Resolution", "Resolution/Public Hearing")


def fetch_matters(base: str, since: str, types: tuple[str, ...] = DEFAULT_TYPES) -> list[dict]:
    """All City Council resolutions introduced on or after `since`, paged."""
    out: list[dict] = []
    for typ in types:
        flt = f"MatterIntroDate ge datetime'{since}' and MatterTypeName eq '{typ}'"
        skip = 0
        while True:
            try:
                page = get_json(odata(base, "matters", filter=flt, orderby="MatterId", top=str(PAGE), skip=str(skip)))
            except urllib.error.HTTPError as e:
                if e.code == 400 and typ != types[0]:
                    print(f"  skipping type {typ!r}: Legistar rejected the query (HTTP 400)")
                    break
                raise
            assert isinstance(page, list)
            out.extend(page)
            print(f"  matters: {len(out)}", end="\r", flush=True)
            if len(page) < PAGE:
                break
            skip += PAGE
    print()
    # Keep council items only; commissions also file resolutions (e.g. the Housing Commission).
    return [m for m in out if (m.get("MatterBodyName") or "").strip() == "City Council"]


def fetch_one(base: str, out_dir: Path, matter: dict, refresh: bool) -> tuple[int, str]:
    mid = matter["MatterId"]
    text_path = out_dir / "texts" / f"{mid}.json"
    att_path = out_dir / "attachments" / f"{mid}.json"
    if text_path.exists() and att_path.exists() and not refresh:
        # Re-fetch only if Legistar says the item changed after we saved it (staff often revise a memo
        # between the agenda going out and the vote). Old caches without the stamp are kept as they are.
        cached = json.loads(text_path.read_text()).get("MatterLastModifiedUtc")
        now = matter.get("MatterLastModifiedUtc")
        if not (cached and now and now > cached):
            return mid, "cached"

    versions = get_json(f"{base}/matters/{mid}/versions")
    text: dict = {"MatterId": mid, "MatterLastModifiedUtc": matter.get("MatterLastModifiedUtc"),
                  "versions": versions, "text": None}
    if isinstance(versions, list) and versions:
        # Highest version is the one council acted on.
        latest = max(versions, key=lambda v: float(v.get("Value") or 0))
        body = get_json(f"{base}/matters/{mid}/texts/{latest['Key']}")
        if isinstance(body, dict):
            text["text"] = {
                "MatterTextId": body.get("MatterTextId"),
                "MatterTextVersion": body.get("MatterTextVersion"),
                "MatterTextPlain": body.get("MatterTextPlain"),
                "MatterTextLastModifiedUtc": body.get("MatterTextLastModifiedUtc"),
            }
    attachments = get_json(f"{base}/matters/{mid}/attachments")

    text_path.write_text(json.dumps(text, ensure_ascii=False, indent=1))
    att_path.write_text(json.dumps(attachments, ensure_ascii=False, indent=1))
    return mid, "fetched"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--client", default="a2gov", help="Legistar client slug (a2gov = Ann Arbor)")
    ap.add_argument("--since", default="2022-07-01", help="earliest MatterIntroDate, YYYY-MM-DD")
    ap.add_argument("--workers", type=int, default=6, help="parallel requests (be polite)")
    ap.add_argument("--limit", type=int, default=0, help="only fetch texts for the N newest contract items (testing)")
    ap.add_argument("--refresh", action="store_true", help="re-download cached texts")
    ap.add_argument("--out", default="data/raw", help="output folder (relative to where you run this)")
    ap.add_argument("--types", default=",".join(DEFAULT_TYPES), help="Legistar matter types to crawl, comma-separated")
    args = ap.parse_args(argv)

    base = API.format(client=args.client)
    out_dir = Path(args.out) / args.client
    (out_dir / "texts").mkdir(parents=True, exist_ok=True)
    (out_dir / "attachments").mkdir(parents=True, exist_ok=True)

    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    print(f"Crawling {base} since {args.since}")
    try:
        matters = fetch_matters(base, args.since, tuple(t.strip() for t in args.types.split(",") if t.strip()))
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            print(f"{args.client} requires a Legistar API token (HTTP {e.code}). Ask the city clerk for one.")
            return 2
        raise
    (out_dir / "matters.json").write_text(json.dumps(matters, ensure_ascii=False, indent=1))

    targets = [m for m in matters if CONTRACT_HINT.search(m.get("MatterTitle") or "")]
    targets.sort(key=lambda m: m["MatterId"], reverse=True)
    if args.limit:
        targets = targets[: args.limit]
    print(f"{len(matters)} council resolutions; {len(targets)} look like contracts -> fetching texts")

    failures: list[dict] = []
    results: dict[str, int] = {}
    done = 0
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {pool.submit(fetch_one, base, out_dir, m, args.refresh): m for m in targets}
        for fut in as_completed(futures):
            m = futures[fut]
            done += 1
            try:
                _, how = fut.result()
                results[how] = results.get(how, 0) + 1
            except Exception as e:  # keep going; record what broke
                failures.append({"MatterId": m["MatterId"], "error": repr(e)})
            print(f"  texts: {done}/{len(targets)}  failures: {len(failures)}", end="\r", flush=True)
    print()

    manifest = {
        "client": args.client,
        "since": args.since,
        "started_utc": started,
        "finished_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "council_resolutions": len(matters),
        "contract_like": len(targets),
        "fetched": results.get("fetched", 0),
        "cached": results.get("cached", 0),
        "failures": failures,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=1))
    print(f"Done. Saved to {out_dir}  ({len(failures)} failures; re-run to retry them)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
"""Measure extraction quality against labels a human made by reading the source.

    python -m clock.eval sample --n 40     # writes eval/labels.csv to fill in
    python -m clock.eval score             # compares labels to data/clock.db, writes eval/report.md

How to label (about a minute per row): open the Legistar link, read the title and the
"Text" tab, and fill in what the record actually says. Leave a cell blank if the record
does not state it; that blank is itself a label ("not stated"), and it is how we catch
the pipeline inventing things. Put "yes" in `labeled` when the row is done.

The sample is stratified on purpose: most rows are items the pipeline called contracts
(to measure precision of each field), and some are council resolutions it skipped (to
catch contracts it missed).
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sqlite3
from collections import Counter
from pathlib import Path

from .rules import vendor_key

ROOT = Path(__file__).resolve().parent.parent
LABELS = ROOT / "eval" / "labels.csv"
REPORT = ROOT / "eval" / "report.md"
FIELDS = ["is_contract", "vendor", "amount", "route", "term_months", "end_date"]
COLUMNS = ["matter_id", "file", "url", "title", "labeled", *FIELDS, "notes"]
ROUTES = "competitive | cooperative | sole_source | emergency"


def sample(n: int, seed: int) -> None:
    con = sqlite3.connect(ROOT / "data" / "clock.db")
    con.row_factory = sqlite3.Row
    contracts = [dict(r) for r in con.execute(
        "SELECT m.matter_id, m.file, m.url, m.title FROM events e JOIN matters m ON m.matter_id = e.event_id "
        "JOIN texts t ON t.matter_id = m.matter_id WHERE e.event_type = 'contract'")]
    others = [dict(r) for r in con.execute(
        "SELECT m.matter_id, m.file, m.url, m.title FROM matters m LEFT JOIN events e ON e.event_id = m.matter_id "
        "WHERE e.event_id IS NULL")]
    rng = random.Random(seed)
    k_other = max(1, n // 4)
    rows = rng.sample(contracts, min(len(contracts), n - k_other)) + rng.sample(others, min(len(others), k_other))
    rng.shuffle(rows)
    LABELS.parent.mkdir(exist_ok=True)
    if LABELS.exists():
        raise SystemExit(f"{LABELS} exists; refusing to overwrite labels. Move it aside first.")
    with LABELS.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow({**r, "labeled": ""})
    print(f"Wrote {len(rows)} rows to {LABELS}.")
    print(f"Fill in: is_contract (yes/no), vendor, amount (number), route ({ROUTES}), "
          "term_months (number), end_date (YYYY-MM-DD). Blank = not stated. Then set labeled=yes.")


def _same(field: str, truth: str, got) -> bool:
    if field == "vendor":
        a, b = vendor_key(truth), vendor_key(got or "")
        return bool(a and b) and (a == b or a in b or b in a)
    if field == "amount":
        try:
            return abs(float(truth.replace("$", "").replace(",", "")) - float(got)) <= 1.0
        except (TypeError, ValueError):
            return False
    if field == "term_months":
        try:
            return int(truth) == int(got)
        except (TypeError, ValueError):
            return False
    return str(truth).strip().lower() == str(got).strip().lower()


def score() -> None:
    con = sqlite3.connect(ROOT / "data" / "clock.db")
    con.row_factory = sqlite3.Row
    events = {r["event_id"]: dict(r) for r in con.execute("SELECT * FROM events")}
    rows = [r for r in csv.DictReader(LABELS.open()) if r["labeled"].strip().lower() == "yes"]
    if not rows:
        raise SystemExit("No rows marked labeled=yes yet.")

    tally = {f: Counter() for f in FIELDS}
    misses: list[str] = []
    for r in rows:
        ev = events.get(int(r["matter_id"]))
        is_c = r["is_contract"].strip().lower() in ("yes", "y", "true", "1")
        got_c = bool(ev and ev["event_type"] == "contract")
        t = tally["is_contract"]
        t["tp" if is_c and got_c else "fp" if got_c else "fn" if is_c else "tn"] += 1
        if is_c != got_c:
            misses.append(f"- {r['file']}: contract={is_c}, pipeline said {got_c}. {r['title'][:110]}")
        if not (is_c and got_c):
            continue
        for f in FIELDS[1:]:
            truth = r[f].strip()
            got = ev.get(f)
            t = tally[f]
            if got in (None, ""):
                t["fn" if truth else "tn"] += 1  # pipeline abstained
                if truth:
                    misses.append(f"- {r['file']} {f}: missed (label: {truth})")
            elif not truth:
                t["fp"] += 1  # pipeline stated something the record doesn't say
                misses.append(f"- {r['file']} {f}: pipeline said {got!r}, label says not stated")
            elif _same(f, truth, got):
                t["tp"] += 1
            else:
                t["wrong"] += 1
                misses.append(f"- {r['file']} {f}: pipeline said {got!r}, label {truth!r}")

    lines = [f"# Extraction quality ({len(rows)} hand-labeled records)", "",
             "Precision: of the values the pipeline showed, how many were right. "
             "Recall: of the values the records state, how many the pipeline found. "
             "Wrong and invented values both count against precision.", "",
             "| Field | Precision | Recall | Right | Wrong | Invented | Missed | Correctly blank |",
             "|---|---|---|---|---|---|---|---|"]
    for f in FIELDS:
        c = tally[f]
        shown = c["tp"] + c["wrong"] + c["fp"]
        stated = c["tp"] + c["wrong"] + c["fn"]
        p = f"{c['tp'] / shown:.0%}" if shown else "n/a"
        rc = f"{c['tp'] / stated:.0%}" if stated else "n/a"
        lines.append(f"| {f} | {p} | {rc} | {c['tp']} | {c['wrong']} | {c['fp']} | {c['fn']} | {c['tn']} |")
    lines += ["", "## Every disagreement", "", *misses]
    REPORT.write_text("\n".join(lines) + "\n")
    print("\n".join(lines[:4 + 2 + len(FIELDS) + 2]))
    print(f"\nFull report: {REPORT}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sample")
    s.add_argument("--n", type=int, default=40)
    s.add_argument("--seed", type=int, default=1)
    sub.add_parser("score")
    args = ap.parse_args(argv)
    sample(args.n, args.seed) if args.cmd == "sample" else score()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

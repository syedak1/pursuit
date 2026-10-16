"""SQLite store. One file, data/clock.db, holds everything the demo needs.

Why SQLite: zero setup, a single file you can commit or hand to someone, and
real SQL for questions the UI doesn't answer yet (`sqlite3 data/clock.db`).

Tables
    matters      one row per council resolution, as crawled
    texts        normalized memo + resolution text, with a content hash
    attachments  attachment names and links
    events       what we extracted: a vendor contract, or a funding action
    evidence     one row per extracted field: value, verbatim quote, where it came from, how
    quality      data problems we found and how we handled them
    runs         one row per pipeline run, for provenance
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS matters (
    matter_id     INTEGER PRIMARY KEY,
    client        TEXT NOT NULL,
    guid          TEXT,
    file          TEXT,
    title         TEXT NOT NULL,
    status        TEXT,
    intro_date    TEXT,      -- ISO date, after repairs (see quality)
    agenda_date   TEXT,
    passed_date   TEXT,
    requester     TEXT,
    enactment     TEXT,
    url           TEXT
);

CREATE TABLE IF NOT EXISTS texts (
    matter_id     INTEGER PRIMARY KEY REFERENCES matters(matter_id),
    text          TEXT NOT NULL,  -- normalized; evidence offsets index into this
    sha256        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS attachments (
    matter_id     INTEGER REFERENCES matters(matter_id),
    name          TEXT,
    url           TEXT
);

CREATE TABLE IF NOT EXISTS events (
    event_id      INTEGER PRIMARY KEY,   -- = matter_id: one event per resolution
    event_type    TEXT NOT NULL,         -- 'contract' | 'funding'
    kind          TEXT,                  -- agreement, purchase_order, amendment, ...
    class         TEXT,                  -- term | one_time | change (only term contracts have a renewal clock)
    vendor        TEXT,
    vendor_key    TEXT,
    amount        REAL,
    route         TEXT,                  -- competitive | cooperative | sole_source | emergency | NULL
    department    TEXT,
    categories    TEXT,                  -- JSON list
    start_date    TEXT,
    term_months   INTEGER,
    end_date      TEXT,
    end_basis     TEXT,                  -- stated | start+term | approval+term | fiscal_years | NULL
    renewals      TEXT,                  -- JSON {count, months_each}
    max_end_date  TEXT,                  -- if every renewal option is exercised
    amount_basis  TEXT,                  -- annual | ceiling | total | increase | stated
    state         TEXT                   -- approved | pending | not_approved
);

CREATE TABLE IF NOT EXISTS evidence (
    evidence_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id      INTEGER REFERENCES events(event_id),
    field         TEXT NOT NULL,
    value         TEXT,                  -- JSON-encoded
    source        TEXT NOT NULL,         -- 'title' | 'text' | 'derived'
    method        TEXT NOT NULL,         -- 'rule' | 'llm' | 'derived'
    rule          TEXT,
    verified      INTEGER NOT NULL,      -- 1 if quote found verbatim in source
    quote         TEXT,
    q_start       INTEGER,
    q_end         INTEGER,
    m_start       INTEGER,               -- the exact matched span inside the quote's source
    m_end         INTEGER,
    derivation    TEXT                   -- for derived fields: the arithmetic, in words
);

CREATE TABLE IF NOT EXISTS quality (
    matter_id     INTEGER,
    issue         TEXT,
    detail        TEXT,
    action        TEXT
);

CREATE TABLE IF NOT EXISTS runs (
    run_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    started_utc   TEXT,
    finished_utc  TEXT,
    client        TEXT,
    stats         TEXT
);

-- Full-text index for search (titles, vendors, departments, memo text). BM25 ranking via ORDER BY rank.
CREATE VIRTUAL TABLE IF NOT EXISTS search USING fts5(
    matter_id UNINDEXED, file, title, vendor, department, text, tokenize = 'porter unicode61'
);

CREATE INDEX IF NOT EXISTS ev_event ON evidence(event_id);
CREATE INDEX IF NOT EXISTS events_vendor ON events(vendor_key);
CREATE INDEX IF NOT EXISTS events_dept ON events(department);
"""


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def reset(con: sqlite3.Connection) -> None:
    """Rebuild derived tables from scratch; the raw crawl on disk is the source of truth."""
    for t in ("search", "evidence", "events", "quality", "attachments", "texts", "matters"):
        con.execute(f"DELETE FROM {t}")

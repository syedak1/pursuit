"""Invariants of the committed build (data/clock.db): rules the pipeline promises, checked on real data."""
import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "data" / "clock.db"


def q(sql):
    con = sqlite3.connect(DB)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def test_amendments_are_never_dated_from_their_own_vote():
    # "Amendment 1 to the Five-Year Agreement" restates the original's term, which began before this vote.
    assert q("SELECT count(*) FROM events WHERE class='change' AND end_basis='approval+term'") == [(0,)]


def test_price_expiry_only_for_purchase_orders():
    assert q("SELECT count(*) FROM events WHERE end_basis='price_expiry' AND kind != 'purchase_order'") == [(0,)]


def test_latest_end_follows_end():
    assert q("SELECT count(*) FROM events WHERE max_end_date IS NOT NULL AND max_end_date <= end_date") == [(0,)]


def test_every_quoted_fact_has_its_quote():
    assert q("SELECT count(*) FROM evidence WHERE source != 'derived' AND (quote IS NULL OR quote = '')") == [(0,)]

from xml.etree import ElementTree as ET

from clock import feed


def site(today="2026-10-10"):
    base = {"type": "contract", "class": "term", "state": "approved", "cats": ["it_software"], "vendor": "Acme",
            "dept": "IT", "amount": 1e5, "amountBasis": "stated", "route": "competitive", "kind": "agreement",
            "title": "Agreement with Acme", "url": "https://x/1", "fields": {}, "renewals": None, "maxEnd": None,
            "endBasis": "stated", "agenda": None}
    return {"meta": {"today": today, "city": "Ann Arbor, MI"}, "categories": {"it_software": "IT & software"}, "evidence": [],
            "events": [
                {**base, "id": 1, "file": "26-1", "end": "2027-06-30", "passed": "2024-07-01", "introduced": "2024-07-01"},
                {**base, "id": 2, "file": "26-2", "end": "2031-06-30", "passed": "2024-07-01", "introduced": "2024-07-01"},
                {**base, "id": 3, "file": "26-3", "end": None, "state": "pending", "passed": None, "introduced": "2026-10-09", "agenda": "2026-10-19"},
                {**base, "id": 4, "file": "26-4", "end": None, "passed": "2026-09-22", "introduced": "2026-09-22"},
            ]}


def test_entries_kinds():
    kinds = {(e["id"]) for e in feed.entries(site())}
    assert kinds == {"26-1:window", "26-3:pending", "26-4:approved"}  # 26-2 ends too far out


def test_feed_is_valid_atom(tmp_path):
    p = tmp_path / "f.xml"
    feed.write_feed(p, "t", feed.entries(site()), "../index.html", "Ann Arbor, MI")
    root = ET.parse(p).getroot()
    assert root.tag.endswith("feed") and len(root.findall("{http://www.w3.org/2005/Atom}entry")) == 3

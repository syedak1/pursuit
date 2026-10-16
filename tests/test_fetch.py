"""The crawler against a local stand-in for Legistar: paging, caching, and re-fetching changed items."""

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

from clock import fetch

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def server():
    p = subprocess.Popen([sys.executable, str(ROOT / "tests" / "fake_legistar.py"), "8766"])
    time.sleep(0.6)
    yield "http://127.0.0.1:8766/v1/{client}"
    p.terminate()


def test_crawl_pages_caches_and_refetches_changed(server, tmp_path, monkeypatch):
    monkeypatch.setattr(fetch, "API", server)
    assert fetch.main(["--client", "fake", "--limit", "5", "--out", str(tmp_path)]) == 0
    out = tmp_path / "fake"
    m = json.loads((out / "manifest.json").read_text())
    assert m["council_resolutions"] == 2501 and m["fetched"] == 5  # paged past 1,000 and 2,000
    assert fetch.main(["--client", "fake", "--limit", "5", "--out", str(tmp_path)]) == 0
    assert json.loads((out / "manifest.json").read_text())["cached"] == 5  # second run: nothing re-downloaded
    # Pretend our copy of one item is older than Legistar's: that one is fetched again.
    one = sorted((out / "texts").glob("*.json"))[0]
    d = json.loads(one.read_text()); d["MatterLastModifiedUtc"] = "2020-01-01T00:00:00"; one.write_text(json.dumps(d))
    assert fetch.main(["--client", "fake", "--limit", "5", "--out", str(tmp_path)]) == 0
    m = json.loads((out / "manifest.json").read_text())
    assert m["fetched"] == 1 and m["cached"] == 4

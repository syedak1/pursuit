"""The local server serves the static site, including the data file and feeds."""

import threading
import urllib.request
from http.server import ThreadingHTTPServer

from clock import serve


def test_serves_site_data_and_feeds():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), serve.Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        base = f"http://127.0.0.1:{srv.server_address[1]}/"
        assert b"<main" in urllib.request.urlopen(base).read()
        assert urllib.request.urlopen(base + "data/site.js").read().startswith(b"window.SITE")
        assert b"<feed" in urllib.request.urlopen(base + "feeds/all.xml").read()
    finally:
        srv.shutdown()

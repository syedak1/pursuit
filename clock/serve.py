"""Serve the site locally.

    python -m clock serve                       # http://localhost:8000
    python -m clock serve --host 0.0.0.0        # reachable from other machines (Docker, Fly.io, Render)

The site is static: web/index.html reads web/data/site.js, which `clock build` writes. Opening
web/index.html straight from disk works too; serving it adds the Atom feeds under /feeds/ and
normal link sharing. No API keys, no database access at request time. Standard library only.
"""

from __future__ import annotations

import argparse
import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(WEB), **kw)

    def log_message(self, fmt, *args):  # quiet: the page loads a handful of files
        pass


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Serve Incumbent Clock.")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8000)))
    args = ap.parse_args(argv)
    if not (WEB / "data" / "site.js").exists():
        raise SystemExit("No web/data/site.js yet. Run: python -m clock build")
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Incumbent Clock on http://{'localhost' if args.host in ('127.0.0.1', '0.0.0.0') else args.host}:{args.port}  (Ctrl+C to stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

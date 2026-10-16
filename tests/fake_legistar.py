"""A tiny stand-in for the Legistar Web API, used to test the crawler offline."""
import json, re, sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

MATTERS = [
    {"MatterId": i, "MatterFile": f"26-{i}", "MatterTypeName": "Resolution", "MatterBodyName": "City Council",
     "MatterIntroDate": "2026-09-22T00:00:00", "MatterLastModifiedUtc": "2026-09-22T10:00:00",
     "MatterTitle": ("Resolution to Approve an Agreement with Acme ($10,000.00)" if i % 2 else "Resolution to Accept an Easement")}
    for i in range(1, 2502)
]

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def send(self, obj):
        b = json.dumps(obj).encode(); self.send_response(200)
        self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        u = urlparse(self.path); q = parse_qs(u.query); path = u.path
        if path.endswith("/matters"):
            top = int(q["$top"][0]); skip = int(q.get("$skip", ["0"])[0])
            f = q["$filter"][0]
            assert "datetime'" in f
            rows = MATTERS if "eq 'Resolution'" in f else []
            return self.send(rows[skip:skip + top])
        if m := re.search(r"/matters/(\d+)/versions$", path):
            return self.send([{"Key": str(int(m[1]) * 10), "Value": "1"}])
        if m := re.search(r"/matters/(\d+)/texts/(\d+)$", path):
            return self.send({"MatterTextId": int(m[2]), "MatterTextVersion": "1", "MatterTextPlain": "for a term of three years", "MatterTextRtf": "{\\rtf huge}"})
        if re.search(r"/matters/(\d+)/attachments$", path):
            return self.send([])
        self.send_response(404); self.end_headers()

if __name__ == "__main__":
    HTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()

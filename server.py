#!/usr/bin/env python3
"""
hkslc — local development server.

Serves the site (index.html, app.js, style.css) and the API at
    GET /api/stock?code=00700

The API logic lives in api/stock.py — the same file Vercel runs as a
serverless function — so local and deployed behaviour are identical.

Run:  python3 server.py   →  http://localhost:8765
"""

import json
import os
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent

sys.path.insert(0, str(ROOT / "api"))
import stock as hkapi  # noqa: E402

PORT = int(os.environ.get("PORT", "8765"))  # hosting platforms assign PORT

# Explicit whitelist: nothing else in the repo is ever served.
STATIC = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # quieter logs
        print("[srv]", fmt % args)

    def _send(self, http, body: bytes, ctype: str):
        self.send_response(http)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        route = parsed.path

        if route == "/api/stock":
            qs = urllib.parse.parse_qs(parsed.query)
            out = hkapi.get_stock((qs.get("code") or [""])[0])
            self._send(out["http"], json.dumps(out["body"], ensure_ascii=False).encode("utf-8"),
                       "application/json; charset=utf-8")
            return

        entry = STATIC.get(route)
        if entry:
            name, ctype = entry
            self._send(200, (ROOT / name).read_bytes(), ctype)
            return

        self._send(404, b"Not found", "text/plain; charset=utf-8")


if __name__ == "__main__":
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"hkslc running at http://localhost:{PORT}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.server_close()

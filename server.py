#!/usr/bin/env python3
"""
HK Stock Liquidity Calculator — local development server.

Serves the static site from ./public and exposes:
    GET /api/stock?code=00700

All data/calculation logic lives in api/hk_core.py, which is shared with the
Vercel serverless function (api/stock.py) so local and deployed behaviour match.

Run:  python3 server.py   →  http://localhost:8765
"""

import json
import os
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT / "public"

# Import the shared logic module from api/
sys.path.insert(0, str(ROOT / "api"))
import hk_core  # noqa: E402

PORT = int(os.environ.get("PORT", "8765"))  # hosting platforms assign PORT

MIME = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
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
            out = hk_core.get_stock((qs.get("code") or [""])[0])
            self._send(out["http"], json.dumps(out["body"], ensure_ascii=False).encode("utf-8"),
                       "application/json; charset=utf-8")
            return

        if route in ("/", "/index.html"):
            f = PUBLIC / "index.html"
        else:
            f = (PUBLIC / route.lstrip("/")).resolve()
            if not str(f).startswith(str(PUBLIC)) or not f.is_file():
                self._send(404, b"Not found", "text/plain; charset=utf-8")
                return
        if f.is_file():
            self._send(200, f.read_bytes(), MIME.get(f.suffix, "application/octet-stream"))
        else:
            self._send(404, b"Not found", "text/plain; charset=utf-8")


if __name__ == "__main__":
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"hkslc running at http://localhost:{PORT}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.server_close()

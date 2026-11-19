#!/usr/bin/env python3
"""Vercel serverless function: GET /api/stock?code=00700

Exposes the same JSON contract as the local dev server's /api/stock route.
"""

import json
import urllib.parse

import hk_core


def app(environ, start_response):
    try:
        qs = urllib.parse.parse_qs(environ.get("QUERY_STRING", ""))
        out = hk_core.get_stock((qs.get("code") or [""])[0])
        body = json.dumps(out["body"], ensure_ascii=False).encode("utf-8")
        status = f"{out['http']} {'OK' if out['http'] == 200 else 'Error'}"
        start_response(status, [
            ("Content-Type", "application/json; charset=utf-8"),
            ("Cache-Control", "no-store"),
        ])
        return [body]
    except Exception as exc:  # noqa: BLE001 - never leak a stack trace to the client
        body = json.dumps({"error": f"Server error: {exc}"}).encode("utf-8")
        start_response("500 Internal Server Error", [
            ("Content-Type", "application/json; charset=utf-8"),
        ])
        return [body]

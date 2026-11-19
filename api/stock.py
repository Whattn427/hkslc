#!/usr/bin/env python3
"""
hkslc API — Vercel serverless function (auto-routed at /api/stock).

Self-contained: Vercel's zero-config Python builder runs this file directly,
so all data fetching and calculation logic lives here. The local dev server
(server.py) imports get_stock() from this module, keeping one source of truth.

Data: Eastmoney public, keyless datacenter API.
"""

import json
import re
import ssl
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
)

API_BASE = (
    "https://datacenter.eastmoney.com/securities/api/data/v1/get"
    "?columns=ALL&pageNumber=1&source=F10&client=PC"
)

# ---- Standardised line items (matched on normalised Chinese ITEM_NAME) ----
INVENTORY = "存货"
RECEIVABLE = "应收帐款"

# Cash-like lines. "default" = included in "total cash" out of the box.
CASH_ITEMS = [
    {"cn": "现金及等价物", "en": "Cash & cash equivalents", "default": True},
    {"cn": "短期存款", "en": "Short-term deposits", "default": False},
    {"cn": "短期投资", "en": "Short-term investments", "default": False},
    {"cn": "受限制存款及现金", "en": "Restricted cash & deposits", "default": False},
    {"cn": "指定以公允价值记帐之金融资产(流动)",
     "en": "Financial assets at fair value (current)", "default": False},
    {"cn": "交易性金融资产(流动)",
     "en": "Trading financial assets (current)", "default": False},
]

CURRENT_LIAB = "流动负债合计"     # total current liabilities
NONCURRENT_LIAB = "非流动负债合计"  # total non-current liabilities
TOTAL_LIAB = "总负债"             # total liabilities (cross-check / fallback)

EN_LABELS = {
    "存货": "Inventory",
    "应收帐款": "Accounts receivable",
    "受限制存款及现金": "Restricted cash & deposits",
    "现金及等价物": "Cash & cash equivalents",
    "短期存款": "Short-term deposits",
    "短期投资": "Short-term investments",
    "指定以公允价值记帐之金融资产(流动)": "Financial assets at fair value (current)",
    "交易性金融资产(流动)": "Trading financial assets (current)",
    "流动负债合计": "Total current liabilities",
    "非流动负债合计": "Total non-current liabilities",
    "总负债": "Total liabilities",
}

CURRENCIES = {
    "人民币": ("RMB", "¥"), "港元": ("HKD", "HK$"), "美元": ("USD", "US$"),
    "新台币": ("TWD", "NT$"), "欧元": ("EUR", "€"), "日元": ("JPY", "¥"),
    "英镑": ("GBP", "£"), "新加坡元": ("SGD", "S$"), "澳元": ("AUD", "A$"),
    "韩国元": ("KRW", "₩"), "瑞士法郎": ("CHF", "CHF"),
}

_cache = {}  # code -> {"t": fetch_time, "payload": ...}
CACHE_TTL = 600  # seconds


def normalize_code(raw: str):
    """'700' / '0700' / '00700' / '0700.HK' -> '00700', or None if invalid."""
    code = (raw or "").strip().upper()
    if code.endswith(".HK"):
        code = code[:-3]
    if not re.fullmatch(r"\d{1,5}", code):
        return None
    return code.zfill(5)


def norm_item(name):
    """Normalise an Eastmoney line-item name (unify 帐/账, strip spaces)."""
    return (name or "").replace("账", "帐").replace(" ", "").strip()


def datacenter_get(report_name: str, filter_expr: str, sort=None, page_size=1):
    """GET one report from the Eastmoney datacenter API."""
    url = API_BASE + f"&reportName={report_name}&pageSize={page_size}"
    if sort:
        col, direction = sort
        url += f"&sortColumns={col}&sortTypes={direction}"
    url += "&filter=" + urllib.parse.quote(filter_expr, safe="")
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    last_err = None
    ctx = ssl.create_default_context()
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=20, context=ctx) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return (data or {}).get("result", {}).get("data") or []
        except Exception as exc:  # noqa: BLE001 - network resilience
            reason = getattr(exc, "reason", exc)
            if isinstance(reason, ssl.SSLCertVerificationError) or "CERTIFICATE_VERIFY_FAILED" in str(reason):
                ctx = ssl._create_unverified_context()  # noqa: SL001 - local fallback
                continue
            last_err = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"Upstream request failed: {last_err}")


def fetch_em_json(secucode: str):
    """Fetch raw Eastmoney balance-sheet rows for one SECURITY_CODE."""
    return datacenter_get(
        "RPT_HKF10_FN_BALANCE",
        f'(SECURITY_CODE="{secucode}")',
        sort=("REPORT_DATE", -1),
        page_size=300,
    )


def fetch_share_info(code5: str):
    """(total issued shares, english company name) or (None, None)."""
    secucode = f"{code5}.HK"
    shares = None
    name_en = None
    try:
        rows = datacenter_get(
            "RPT_HKF10_INFO_EQUITY",
            f'(SECUCODE="{secucode}")',
            sort=("CHANGE_DATE", -1),
        )
        if rows:
            latest = rows[0] or {}
            val = latest.get("TOTAL_SHARES")
            if isinstance(val, (int, float)) and val > 0:
                shares = int(val)
            else:
                hk = latest.get("HK_SHARES")
                dom = latest.get("DOMESTIC_SHARES")
                parts = [v for v in (hk, dom) if isinstance(v, (int, float)) and v > 0]
                if parts:
                    shares = int(sum(parts))
    except Exception:  # noqa: BLE001
        pass
    try:
        rows = datacenter_get("RPT_HKF10_INFO_ORGPROFILE", f'(SECUCODE="{secucode}")')
        if rows:
            name_en = rows[0].get("ORG_EN_ABBR") or None
    except Exception:  # noqa: BLE001
        pass
    return shares, name_en


def analyze(rows):
    """Build the calculator payload from raw line-item rows."""
    if not rows:
        return None
    latest = max(r["REPORT_DATE"][:10] for r in rows)
    period_rows = [r for r in rows if r["REPORT_DATE"][:10] == latest]
    if not period_rows:
        return None

    head = period_rows[0]
    currency_cn = head.get("CURRENCY") or ""
    cur_code, cur_sym = CURRENCIES.get(currency_cn, (currency_cn, currency_cn + " "))

    # Collect latest-period items by normalised Chinese item name.
    by_name = {}
    for r in period_rows:
        nm = norm_item(r.get("ITEM_NAME"))
        if not nm:
            continue
        amt = r.get("AMOUNT")
        if nm not in by_name or amt is not None:
            by_name[nm] = amt

    # Statement-type detection: banks/insurers use unclassified balance
    # sheets with no current / non-current split at all.
    has_split = CURRENT_LIAB in by_name or NONCURRENT_LIAB in by_name
    supported = has_split or INVENTORY in by_name or RECEIVABLE in by_name
    statement_kind = "classified" if has_split else "unclassified"
    if not supported:
        return {
            "supported": False,
            "statementKind": statement_kind,
            "nameCn": head.get("SECURITY_NAME_ABBR") or "",
            "code": head.get("SECURITY_CODE") or "",
            "secucode": head.get("SECUCODE") or "",
            "reportDate": latest,
            "currencyCn": currency_cn,
            "message": (
                "This company's latest balance sheet (bank / insurance style, "
                "unclassified) has no inventory, accounts receivable or "
                "current/non-current liability split, so the formula cannot "
                "be computed."
            ),
        }

    def get(key):
        v = by_name.get(key)
        return v if isinstance(v, (int, float)) else None

    inventory = get(INVENTORY)
    receivable = get(RECEIVABLE)
    current_liab = get(CURRENT_LIAB)
    noncurrent_liab = get(NONCURRENT_LIAB)
    total_liab = get(TOTAL_LIAB)

    derived = []
    if noncurrent_liab is None and current_liab is not None and total_liab is not None:
        noncurrent_liab = total_liab - current_liab
        derived.append("noncurrent_liabilities")

    cash_lines = []
    for item in CASH_ITEMS:
        if item["cn"] not in by_name:
            continue  # company doesn't report this line type
        cash_lines.append({
            "key": item["cn"],
            "nameCn": item["cn"],
            "nameEn": EN_LABELS.get(item["cn"], item["en"]),
            "amount": get(item["cn"]),
            "included": item["default"],
        })

    inventory_val = inventory or 0
    receivable_val = receivable or 0
    cash_val = sum(l["amount"] or 0 for l in cash_lines if l["included"] and l["amount"] is not None)
    cl_val = current_liab or 0
    ncl_val = noncurrent_liab or 0

    result = (
        inventory_val * 0.5
        + receivable_val * 0.7
        + cash_val
        - (cl_val + ncl_val)
    )

    return {
        "supported": True,
        "nameCn": head.get("SECURITY_NAME_ABBR") or "",
        "code": head.get("SECURITY_CODE") or "",
        "secucode": head.get("SECUCODE") or "",
        "reportDate": latest,
        "currencyCn": currency_cn,
        "currencyCode": cur_code,
        "currencySymbol": cur_sym,
        "raw": {
            "inventory": inventory,
            "accountsReceivable": receivable,
            "currentLiabilities": current_liab,
            "nonCurrentLiabilities": noncurrent_liab,
            "totalLiabilities": total_liab,
        },
        "cashLines": cash_lines,
        "derived": derived,
        "result": {
            "inventoryX": inventory_val * 0.5,
            "receivableX": receivable_val * 0.7,
            "cashTotal": cash_val,
            "liabTotal": cl_val + ncl_val,
            "net": result,
        },
    }


def get_stock(code_raw: str):
    """Full API result: {"http": status, "body": payload|error}."""
    code = normalize_code(code_raw)
    if not code:
        return {"http": 400, "body": {"error": "Please enter a valid Hong Kong stock code (1–5 digits, e.g. 700 or 0700)."}}

    now = time.time()
    hit = _cache.get(code)
    if hit and now - hit["t"] < CACHE_TTL:
        return {"http": 200, "body": hit["payload"]}

    try:
        rows = fetch_em_json(code)
    except RuntimeError as exc:
        return {"http": 502, "body": {"error": str(exc)}}

    if not rows:
        return {"http": 404, "body": {"error": f"No financial statement data found for stock code {code}. Check the code and try again."}}

    payload = analyze(rows)
    if not payload:
        return {"http": 404, "body": {"error": f"Could not parse the latest statement for {code}."}}

    if payload.get("supported"):
        shares, name_en = fetch_share_info(code)
        payload["shareCount"] = shares
        payload["nameEn"] = name_en
        net = payload["result"]["net"]
        payload["perShare"] = (net / shares) if shares else None

    payload["formulaNote"] = ("(inventory × 0.5) + (accounts receivable × 0.7) "
                              "+ total cash − (current + non-current liabilities)")
    _cache[code] = {"t": now, "payload": payload}
    return {"http": 200, "body": payload}


# ---- Vercel entrypoint (documented BaseHTTPRequestHandler style) ----
class handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        try:
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            out = get_stock((qs.get("code") or [""])[0])
            body = json.dumps(out["body"], ensure_ascii=False).encode("utf-8")
            status = out["http"]
        except Exception as exc:  # noqa: BLE001 - never leak a stack trace
            body = json.dumps({"error": f"Server error: {exc}"}).encode("utf-8")
            status = 500
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):  # quiet
        pass

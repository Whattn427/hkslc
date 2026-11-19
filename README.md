# hkslc

**hkslc** — HK Stock Liquidity Calculator.

A small local website that pulls the **latest balance sheet** for any Hong Kong-listed
stock and computes:

```
(inventory × 0.5) + (accounts receivable × 0.7) + total cash − (current + non-current liabilities)
```

## Run it

```bash
python3 server.py
```

Then open **http://localhost:8765** in a browser. No dependencies, no API keys —
Python 3 standard library only.

## Deploy to Vercel

The repo is Vercel-ready (`vercel.json` + `api/stock.py` serverless function +
`api/hk_core.py` shared logic — the same code the local server uses):

1. Push this folder to a GitHub repository.
2. Go to [vercel.com](https://vercel.com) → **Add New… → Project** → import the repo.
3. Framework preset: **Other** (leave everything as-is — `vercel.json` drives it).
4. Name the project **hkslc** (edit the "Project Name" field at import time if the repo
   has a different name). You site goes live at `https://hkslc.vercel.app`
   (if that name is taken, Vercel appends a suffix — you can rename the project later
   under Settings → General → Project Name, or attach your own domain).

(Alternatively install the Vercel CLI with Node and run `vercel` from this folder.)

Notes:
- Vercel Hobby (free) plan: fine for personal use; functions have a ~10s timeout,
  which the two upstream API calls fit comfortably.
- The serverless instances are stateless, so the 10-minute response cache only
  helps while an instance stays warm.

## Use it

- Type a stock code (1–5 digits, with or without leading zeros, e.g. `700`, `00700`, `0700.HK`) and press **Calculate**.
- The result card shows every line item used, the substituted formula, and the final figure.
- **Total cash** defaults to *Cash & cash equivalents* (现金及等价物). Other cash-like
  lines the company reports (short-term deposits, restricted cash, current financial
  assets…) are shown with checkboxes — tick any to include them and the result
  recalculates live.
- **Per-share figure**: adjusted net liquidity ÷ total shares issued, shown under the
  headline result (e.g. Tencent 2026 interim: −¥690.68B ÷ 9,092,644,829 shares ≈ −¥75.96
  per share). Share counts come from the latest entry of Eastmoney's share-capital
  history dataset, so A+H dual listings (e.g. BYD) are counted in full.
- Amounts are in the company's own reporting currency as filed (e.g. BYD reports in RMB,
  HKEX in HKD), clearly labelled.

## Notes & limits

- Data comes from Eastmoney's public datacenter API (standardised HK financial
  statements, no key required). Results are cached server-side for 10 minutes.
- "Latest statement" = the most recent period available (annual, interim or quarterly).
- Banks and insurers (e.g. HSBC 00005, Hang Seng Bank 00011, China Life 02628) publish
  unclassified balance sheets with no inventory / receivables / current–non-current
  split, so the formula is not applicable and the site says so.
- Lines a company doesn't report (e.g. inventory for HKEX) are treated as 0 and noted.
- If non-current liabilities aren't stated separately, they're derived as
  total liabilities − current liabilities (noted in the UI).

## Files

| File | Purpose |
| ---- | ------- |
| `server.py` | Local dev server (static files + `/api/stock` route) |
| `api/hk_core.py` | Shared logic: Eastmoney fetch, parse, calculate (used by both) |
| `api/stock.py` | Vercel serverless function for `/api/stock` |
| `vercel.json` | Vercel build & route configuration |
| `public/index.html` | Page markup |
| `public/style.css` | Styling |
| `public/app.js` | Rendering + live recalculation when toggling cash lines |

### Data endpoints (all keyless Eastmoney datacenter API)

| Dataset | Used for |
| ------- | -------- |
| `RPT_HKF10_FN_BALANCE` | Balance sheet line items, latest period |
| `RPT_HKF10_INFO_EQUITY` | Total shares issued (latest share-capital change) |
| `RPT_HKF10_INFO_ORGPROFILE` | English company name |

For research only — not investment advice.

/* HK Stock Liquidity Calculator — frontend logic */

const $ = (id) => document.getElementById(id);
const form = $("lookup");
const codeInput = $("code");
const goBtn = $("go");
const statusEl = $("status");
const spinner = $("spinner");
const card = $("card");

let data = null; // latest API payload

const fmtFull = (n) =>
  n == null ? "—" : n.toLocaleString("en-US", { maximumFractionDigits: 0 });
const fmtCompact = (n) => {
  if (n == null) return "—";
  const abs = Math.abs(n);
  const sign = n < 0 ? "−" : "";
  if (abs >= 1e12) return `${sign}${(abs / 1e12).toFixed(2)}T`;
  if (abs >= 1e9) return `${sign}${(abs / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `${sign}${(abs / 1e6).toFixed(2)}M`;
  if (abs >= 1e3) return `${sign}${(abs / 1e3).toFixed(2)}K`;
  return `${sign}${abs.toLocaleString("en-US")}`;
};

function periodLabel(date) {
  const m = date.slice(5, 7);
  if (m === "12") return "Annual report";
  if (m === "06") return "Interim report";
  return "Quarterly report";
}

function showStatus(msg, info = false) {
  statusEl.textContent = msg;
  statusEl.classList.toggle("info", info);
  statusEl.classList.remove("hidden");
}

function hideStatus() { statusEl.classList.add("hidden"); }

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const code = codeInput.value.trim();
  if (!/^\d{1,5}(\.HK)?$/i.test(code)) {
    showStatus("Please enter a 1–5 digit Hong Kong stock code, e.g. 700 or 0700.");
    return;
  }
  goBtn.disabled = true;
  spinner.classList.remove("hidden");
  hideStatus();
  card.classList.add("hidden");
  try {
    const resp = await fetch(`/api/stock?code=${encodeURIComponent(code)}`);
    const body = await resp.json();
    if (!resp.ok) {
      showStatus(body.error || "Something went wrong. Please try again.");
    } else if (!body.supported) {
      showStatus(`${body.nameCn} (${body.secucode}) — ${body.message}`, true);
    } else {
      data = body;
      render();
    }
  } catch (err) {
    showStatus("Network error: could not reach the calculation service. " + err);
  } finally {
    goBtn.disabled = false;
    spinner.classList.add("hidden");
  }
});

/* ---------- rendering ---------- */

function lineAmount(v) {
  return v == null
    ? `<span class="off">not reported</span>`
    : fmtFull(v);
}

function renderCashRows() {
  const tbody = $("cash-rows");
  tbody.innerHTML = "";
  data.cashLines.forEach((line, i) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>
        <span class="cash-check">
          <input type="checkbox" data-idx="${i}" ${line.included ? "checked" : ""} ${line.amount == null ? "disabled" : ""}>
          <span>${line.nameEn}</span>
        </span>
        <span class="cn">${line.nameCn}</span>
      </td>
      <td class="num">${lineAmount(line.amount)}</td>
      <td class="num" id="cash-x-${i}"></td>`;
    tbody.appendChild(tr);
  });
  tbody.querySelectorAll('input[type="checkbox"]').forEach((cb) =>
    cb.addEventListener("change", () => {
      data.cashLines[Number(cb.dataset.idx)].included = cb.checked;
      recalc();
    })
  );
}

function render() {
  const cur = data.currencySymbol || "";
  $("co-name").textContent =
    `${data.nameCn} (${data.secucode})`;
  $("co-meta").textContent =
    [data.nameEn, periodLabel(data.reportDate), `balance sheet as at ${data.reportDate}`]
      .filter(Boolean).join(" · ");
  $("currency-note").textContent =
    `Amounts in ${data.currencyCode || data.currencyCn}${data.currencyCn ? "" : ""} — as filed by the company`;

  const raw = data.raw;
  $("inv-reported").textContent = lineAmount(raw.inventory);
  $("ar-reported").textContent = lineAmount(raw.accountsReceivable);
  $("cl-reported").textContent = lineAmount(raw.currentLiabilities);
  $("ncl-reported").textContent = lineAmount(raw.nonCurrentLiabilities);

  renderCashRows();

  // notes
  const notes = [];
  if (raw.inventory == null) notes.push("No <b>inventory</b> line in the latest statement — treated as 0.");
  if (raw.accountsReceivable == null) notes.push("No <b>accounts receivable</b> line — treated as 0.");
  if (raw.currentLiabilities == null) notes.push("No <b>total current liabilities</b> line — treated as 0.");
  if (raw.nonCurrentLiabilities == null && data.derived.includes("noncurrent_liabilities"))
    notes.push("<b>Non-current liabilities</b> not stated separately — derived as total liabilities − current liabilities.");
  if (data.cashLines.some((l) => l.amount == null))
    notes.push("Unticked cash-type lines are excluded; tick or untick them to adjust what counts as “total cash”.");
  $("notes").innerHTML = notes.map((n) => `<div>• ${n}</div>`).join("");

  recalc();
  card.classList.remove("hidden");
}

function recalc() {
  const cur = data.currencySymbol || "";
  const r = data.raw;
  const inv = r.inventory ?? 0;
  const ar = r.accountsReceivable ?? 0;
  const cl = r.currentLiabilities ?? 0;
  const ncl = data.derived.includes("noncurrent_liabilities")
    ? (r.totalLiabilities ?? 0) - (r.currentLiabilities ?? 0)
    : (r.nonCurrentLiabilities ?? 0);

  const invX = inv * 0.5;
  const arX = ar * 0.7;
  const cash = data.cashLines
    .filter((l) => l.included && l.amount != null)
    .reduce((s, l) => s + l.amount, 0);

  $("inv-x").innerHTML = `${cur}${fmtCompact(invX)}`;
  $("ar-x").innerHTML = `${cur}${fmtCompact(arX)}`;
  $("cash-total").innerHTML = `${cur}${fmtCompact(cash)}`;
  $("cl-x").innerHTML = `<span class="off">−</span>${cur}${fmtCompact(cl)}`;
  $("ncl-x").innerHTML = `<span class="off">−</span>${cur}${fmtCompact(ncl)}`;
  $("liab-total").innerHTML = `<span class="off">−</span>${cur}${fmtCompact(cl + ncl)}`;

  // per-line "in formula" column for cash lines
  data.cashLines.forEach((line, i) => {
    const cell = document.getElementById(`cash-x-${i}`);
    if (!cell) return;
    cell.innerHTML =
      line.included && line.amount != null
        ? `+${cur}${fmtCompact(line.amount)}`
        : `<span class="off">excluded</span>`;
  });

  const net = invX + arX + cash - (cl + ncl);

  // substituted formula line
  const terms = [];
  terms.push(`0.5×${fmtCompact(inv)}`);
  terms.push(`0.7×${fmtCompact(ar)}`);
  terms.push(fmtCompact(cash));
  const clNcl = ncl === 0 && cl === 0 ? "0" : `${fmtCompact(cl + ncl)}`;
  $("formula-line").innerHTML =
    `(0.5 × ${fmtFull(inv)}) + (0.7 × ${fmtFull(ar)}) + ${fmtFull(cash)} − (${fmtFull(cl + ncl)})<br>` +
    `<span style="opacity:.55">=</span> ${fmtCompact(invX)} + ${fmtCompact(arX)} + ${fmtCompact(cash)} − ${clNcl}` +
    ` <span class="op">=</span> <b>${fmtCompact(net)}</b>`;

  const box = document.querySelector(".result-box");
  const pos = net >= 0;
  box.classList.toggle("pos", pos);
  box.classList.toggle("neg", !pos);
  $("result-value").textContent =
    `${pos ? "+" : "−"}${cur}${fmtCompact(Math.abs(net))} ${data.currencyCode || ""}`.trim();
  $("result-note").textContent = pos
    ? "Adjusted liquid resources exceed total liabilities."
    : "Total liabilities exceed adjusted liquid resources.";

  // per share: adjusted net liquidity / number of shares issued
  const psEl = $("per-share");
  const psNote = $("per-share-note");
  if (data.shareCount) {
    const per = net / data.shareCount;
    psEl.innerHTML =
      `≈ ${per < 0 ? "−" : "+"}${cur}${Math.abs(per).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` +
      ` <span class="per-label">per share</span>`;
    psNote.textContent =
      `Adjusted net liquidity ÷ ${fmtFull(data.shareCount)} shares issued`;
  } else {
    psEl.textContent = "";
    psNote.textContent = "Shares issued unavailable — per-share value not shown.";
  }
}

// Hex tx review: decodes a raw tx and renders a human-readable summary
// comparing actual outputs against expected ones from the position state.
//
// Every signature/broadcast goes through this pane. The user sees what
// they're about to authorize, in plain language, with mismatches flagged
// against agreed terms.

import { decodeRawTx, resolveId, rpc } from "./rpc.js";

// expected: { outputs: [{addr, currency, amount, role}], locktime, expiryheight }
// hex: the raw tx hex to review
export async function review(hex, expected = {}) {
  const tx = await decodeRawTx(hex);
  const lines = [];
  const issues = [];

  lines.push(`<div class="kv">
    <div><span class="k">txid (predicted)</span><span class="v">${tx.txid || "—"}</span></div>
    <div><span class="k">version</span><span class="v">${tx.version}</span></div>
    <div><span class="k">locktime</span><span class="v">${tx.locktime || 0}</span></div>
    <div><span class="k">expiryheight</span><span class="v">${tx.expiryheight ?? "—"}</span></div>
  </div>`);

  if (expected.locktime != null && Number(expected.locktime) !== Number(tx.locktime || 0)) {
    issues.push(`locktime mismatch: expected ${expected.locktime}, got ${tx.locktime || 0}`);
  }
  if (expected.expiryheight != null && Number(expected.expiryheight) !== Number(tx.expiryheight ?? 0)) {
    issues.push(`expiryheight mismatch: expected ${expected.expiryheight}, got ${tx.expiryheight ?? 0}`);
  }

  // Inputs — try to fetch source amounts/addresses for context.
  lines.push(`<div style="margin-top:10px"><strong>Inputs</strong></div>`);
  for (let i = 0; i < tx.vin.length; i++) {
    const vin = tx.vin[i];
    if (vin.coinbase) {
      lines.push(`<div class="kv"><div><span class="k">in[${i}]</span><span class="v">coinbase</span></div></div>`);
      continue;
    }
    let detail = `${vin.txid}:${vin.vout}`;
    try {
      const prev = await rpc("getrawtransaction", [vin.txid, 1]);
      const pv = prev.vout?.[vin.vout];
      if (pv) {
        const addr = pv.scriptPubKey?.addresses?.[0] || "?";
        const friendly = await resolveId(addr);
        const cur = pv.scriptPubKey?.reservebalance
          ? Object.entries(pv.scriptPubKey.reservebalance).map(([k, v]) => `${v} ${k}`).join(" + ")
          : `${pv.value} VRSC`;
        detail = `${friendly} — ${cur}`;
      }
    } catch {}
    lines.push(`<div class="kv"><div><span class="k">in[${i}]</span><span class="v">${detail}</span></div></div>`);
  }

  // Outputs — the load-bearing part. Compare against expected.
  lines.push(`<div style="margin-top:10px"><strong>Outputs</strong></div>`);
  for (let i = 0; i < tx.vout.length; i++) {
    const vout = tx.vout[i];
    const addrs = vout.scriptPubKey?.addresses || [];
    const addr = addrs[0] || "(non-standard)";
    const friendly = await resolveId(addr);
    let amounts = [];
    if (vout.value && vout.value > 0) amounts.push(`${vout.value} VRSC`);
    const reserve = vout.scriptPubKey?.reservebalance;
    if (reserve) {
      for (const [c, v] of Object.entries(reserve)) {
        amounts.push(`${v} ${c}`);
      }
    }
    const amountStr = amounts.join(" + ") || "0";

    let cls = "";
    let note = "";
    const exp = expected.outputs?.[i];
    if (exp) {
      const addrOk = !exp.addr || exp.addr === addr || exp.addr === friendly;
      const ccyOk = !exp.currency || amountStr.includes(exp.currency);
      const amtOk = exp.amount == null || amountStr.includes(String(exp.amount));
      if (addrOk && ccyOk && amtOk) {
        cls = "ok";
        note = ` ✓ ${exp.role || "matches expected"}`;
      } else {
        cls = "bad";
        note = ` ✗ expected ${exp.amount ?? ""} ${exp.currency || ""} → ${exp.addr || ""}`;
        issues.push(`out[${i}] mismatch (${exp.role || ""}): wanted ${exp.amount} ${exp.currency} to ${exp.addr}, got ${amountStr} to ${friendly}`);
      }
    }

    lines.push(`<div class="kv ${cls}"><div><span class="k">out[${i}]</span><span class="v">${friendly} — ${amountStr}${note}</span></div></div>`);
  }

  return {
    ok: issues.length === 0,
    issues,
    html: `<div class="review">${lines.join("")}${
      issues.length
        ? `<div class="bad" style="margin-top:10px"><strong>⚠ ${issues.length} issue(s):</strong><ul>${issues.map((i) => `<li>${i}</li>`).join("")}</ul></div>`
        : `<div class="ok" style="margin-top:10px"><strong>✓ Looks correct.</strong></div>`
    }</div>`,
    decoded: tx,
  };
}

// Render the review pane into a target element with a confirm/cancel button row.
export async function showReview(targetEl, hex, expected, onConfirm) {
  targetEl.innerHTML = `<div class="empty">Decoding…</div>`;
  let result;
  try {
    result = await review(hex, expected);
  } catch (e) {
    targetEl.innerHTML = `<div class="review bad">Decode failed: ${e.message}</div>`;
    return;
  }
  targetEl.innerHTML = `
    ${result.html}
    <div class="row" style="margin-top:12px">
      <button class="primary" id="rv-confirm" ${result.ok ? "" : "disabled"}>Looks right, proceed</button>
      <button class="ghost" id="rv-cancel">Cancel</button>
    </div>
  `;
  targetEl.querySelector("#rv-confirm").onclick = () => onConfirm?.(result);
  targetEl.querySelector("#rv-cancel").onclick = () => (targetEl.innerHTML = "");
}

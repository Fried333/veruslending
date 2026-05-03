import { ping, rpc, resolveId } from "./rpc.js";
import { listPositions, getSettings, saveSettings } from "./state.js";

// Top status bar — periodic verusd ping.
async function refreshStatus() {
  const el = document.getElementById("status");
  const r = await ping();
  if (r.ok) {
    el.innerHTML = `<span class="ok">●</span> verusd v${r.version} · block ${r.blocks}`;
  } else {
    el.innerHTML = `<span class="err">●</span> verusd unreachable: ${r.error}`;
  }
}

// Tab nav.
document.querySelectorAll("nav button").forEach((b) => {
  b.onclick = () => {
    document.querySelectorAll("nav button").forEach((x) => x.classList.remove("active"));
    document.querySelectorAll(".section").forEach((x) => x.classList.remove("active"));
    b.classList.add("active");
    document.getElementById(b.dataset.section).classList.add("active");
  };
});

// Positions list.
function renderPositions() {
  const list = listPositions();
  const el = document.getElementById("positions-list");
  if (!list.length) {
    el.innerHTML = `<div class="empty">No active positions.<br />Browse the <strong>Marketplace</strong> to find an offer, or post your own.</div>`;
    return;
  }
  el.innerHTML = list.map(renderPositionCard).join("");
}

function renderPositionCard(p) {
  const t = p.terms || {};
  const principal = t.principal ? `${t.principal.amount} ${t.principal.currency}` : "—";
  const collateral = t.collateral ? `${t.collateral.amount} ${t.collateral.currency}` : "—";
  const counterparty = t.counterparty || "—";
  return `
    <div class="card">
      <div class="card-title">
        <strong>${p.kind} · ${counterparty}</strong>
        <span class="badge ${p.kind}">${p.state || "?"}</span>
      </div>
      <div class="kv">
        <div><span class="k">principal</span><span class="v">${principal}</span></div>
        <div><span class="k">collateral</span><span class="v">${collateral}</span></div>
        <div><span class="k">id</span><span class="v">${p.id}</span></div>
      </div>
    </div>
  `;
}

// Settings.
function loadSettings() {
  const s = getSettings();
  document.getElementById("set-myid").value = s.myid || "";
  document.getElementById("set-myaddr").value = s.myaddr || "";
  document.getElementById("set-mypub").value = s.mypub || "";
}
document.getElementById("set-save").onclick = () => {
  saveSettings({
    myid: document.getElementById("set-myid").value.trim(),
    myaddr: document.getElementById("set-myaddr").value.trim(),
    mypub: document.getElementById("set-mypub").value.trim(),
  });
  const msg = document.getElementById("set-msg");
  msg.textContent = "Saved.";
  setTimeout(() => (msg.textContent = ""), 1500);
};

// Marketplace browse — read children of a parent ID, look for loan.offer.v1 entries.
const LOAN_OFFER_VDXF = "iDDdeciNHuSiggfZrquEBJAX5TUxkm2Sgy"; // loan.offer.v1

async function loadMarketplace() {
  const parent = document.getElementById("mp-parent").value.trim();
  const out = document.getElementById("mp-results");
  if (!parent) {
    out.innerHTML = `<div class="empty">Enter a parent ID (e.g. <code>lend@</code>) and click Load.</div>`;
    return;
  }
  out.innerHTML = `<div class="empty">Searching under ${parent}…</div>`;

  // Strategy: getidentity on the parent → walk children via listidentities filter
  // (listidentities only returns wallet-local IDs, so this is a best-effort cache).
  // For unknown remote IDs we'd want explorer indexing — TODO.
  let parentInfo;
  try {
    parentInfo = await rpc("getidentity", [parent]);
  } catch (e) {
    out.innerHTML = `<div class="review bad">Cannot resolve ${parent}: ${e.message}</div>`;
    return;
  }
  const parentIaddr = parentInfo?.identity?.identityaddress;
  if (!parentIaddr) {
    out.innerHTML = `<div class="review bad">No identityaddress for ${parent}</div>`;
    return;
  }

  let kids;
  try {
    kids = await rpc("listidentities");
  } catch (e) {
    out.innerHTML = `<div class="review bad">listidentities failed: ${e.message}</div>`;
    return;
  }
  const matching = (kids || []).filter((k) => k?.identity?.parent === parentIaddr);

  if (!matching.length) {
    out.innerHTML = `<div class="empty">No wallet-local sub-IDs under ${parent}.<br/><span style="color:var(--muted);font-size:12px">Discovery of remote IDs requires an explorer index — not yet wired up.</span></div>`;
    return;
  }

  const cards = [];
  for (const k of matching) {
    const id = k.identity;
    const cm = id.contentmultimap || {};
    const entries = cm[LOAN_OFFER_VDXF];
    if (!entries || !entries.length) continue;
    for (const entry of entries) {
      let parsed = null;
      try {
        // entries can be either hex string or {serializedhex:"..."} structures
        let hex;
        if (typeof entry === "string") hex = entry;
        else if (entry.serializedhex) hex = entry.serializedhex;
        else if (entry.message) hex = entry.message;
        if (hex) {
          const json = new TextDecoder().decode(
            new Uint8Array(hex.match(/.{2}/g).map((b) => parseInt(b, 16)))
          );
          parsed = JSON.parse(json);
        }
      } catch {}
      if (!parsed) continue;
      cards.push(renderOfferCard(`${id.name}@`, parsed));
    }
  }

  if (!cards.length) {
    out.innerHTML = `<div class="empty">No <code>loan.offer.v1</code> entries found.</div>`;
    return;
  }
  out.innerHTML = cards.join("");
}

function renderOfferCard(idName, offer) {
  const principal = offer.principal ? `${offer.principal.amount} ${offer.principal.currency}` : "—";
  const collateral = offer.collateral ? `${offer.collateral.amount} ${offer.collateral.currency}` : "—";
  const rate = offer.rate != null ? `${(offer.rate * 100).toFixed(2)}%` : "—";
  const term = offer.term_days != null ? `${offer.term_days}d` : "—";
  return `
    <div class="card">
      <div class="card-title">
        <strong>${idName}</strong>
        <span class="badge lend">${offer.type || "lend"}</span>
      </div>
      <div class="kv">
        <div><span class="k">principal</span><span class="v">${principal}</span></div>
        <div><span class="k">collateral</span><span class="v">${collateral}</span></div>
        <div><span class="k">rate</span><span class="v">${rate}</span></div>
        <div><span class="k">term</span><span class="v">${term}</span></div>
      </div>
      <div class="row" style="margin-top:10px">
        <button class="primary" style="flex:0 0 auto" disabled title="Acceptance flow not wired yet">Accept</button>
        <button class="ghost"   style="flex:0 0 auto">View raw</button>
      </div>
    </div>
  `;
}

document.getElementById("mp-load").onclick = loadMarketplace;

// Init.
loadSettings();
renderPositions();
refreshStatus();
setInterval(refreshStatus, 15000);

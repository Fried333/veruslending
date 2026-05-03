#!/usr/bin/env python3
"""
Generate Twitter-sized PNGs (1200x675) showing each step of the VerusLending protocol.
"""
import cairosvg
import os

OUTDIR = '/home/dev/veruslending/twitter'

# Common style
STYLE = """
.title { font-size: 36px; font-weight: 800; fill: #0f172a; }
.subtitle { font-size: 20px; fill: #475569; font-weight: 500; }
.step-label { font-size: 16px; fill: #64748b; font-weight: 600; }
.box-text { font-size: 18px; fill: #1e293b; font-weight: 500; }
.box-text-bold { font-size: 20px; fill: #0f172a; font-weight: 700; }
.box-small { font-size: 14px; fill: #64748b; font-style: italic; }
.caption { font-size: 18px; fill: #1e293b; font-weight: 500; }
.footer { font-size: 14px; fill: #94a3b8; font-weight: 500; }
.tag { font-size: 13px; font-weight: 700; fill: #fff; }
.borrower-fill { fill: #2563eb; }
.lender-fill { fill: #059669; }
.vault-fill { fill: #7c3aed; }
.chain-fill { fill: #6b7280; }
.amount { font-size: 22px; font-weight: 800; fill: #0f172a; }
"""

DEFS = """
<defs>
  <marker id="arrow-blue" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse">
    <path d="M 0 0 L 10 5 L 0 10 z" fill="#2563eb"/>
  </marker>
  <marker id="arrow-green" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse">
    <path d="M 0 0 L 10 5 L 0 10 z" fill="#059669"/>
  </marker>
  <marker id="arrow-gray" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse">
    <path d="M 0 0 L 10 5 L 0 10 z" fill="#475569"/>
  </marker>
  <marker id="arrow-purple" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse">
    <path d="M 0 0 L 10 5 L 0 10 z" fill="#7c3aed"/>
  </marker>
</defs>
"""

def header(step_num, total, title, subtitle=''):
    return f"""
  <rect x="0" y="0" width="1200" height="675" fill="#f8fafc"/>
  <rect x="0" y="0" width="1200" height="80" fill="#0f172a"/>
  <text x="50" y="50" font-size="22" font-weight="700" fill="#fff">VerusLending</text>
  <text x="1150" y="50" font-size="18" fill="#94a3b8" text-anchor="end">step {step_num} of {total}</text>
  <text x="50" y="135" class="title">{title}</text>
  {f'<text x="50" y="170" class="subtitle">{subtitle}</text>' if subtitle else ''}
"""

def footer():
    return """
  <text x="600" y="650" class="footer" text-anchor="middle">github.com/Fried333/veruslending — empirically validated on Verus mainnet</text>
"""

def party_box(x, y, w, h, color, role, name, sub=''):
    """color: hex string like '#2563eb'"""
    return f"""
  <rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" fill="#fff" stroke="{color}" stroke-width="3"/>
  <rect x="{x}" y="{y}" width="{w}" height="34" rx="12" fill="{color}"/>
  <rect x="{x}" y="{y+24}" width="{w}" height="10" fill="{color}"/>
  <text x="{x+w//2}" y="{y+22}" text-anchor="middle" class="tag">{role}</text>
  <text x="{x+w//2}" y="{y+72}" text-anchor="middle" class="box-text-bold">{name}</text>
  {f'<text x="{x+w//2}" y="{y+100}" text-anchor="middle" class="box-small">{sub}</text>' if sub else ''}
"""

def vault_box(x, y, w, h, label='vault', sub=''):
    return f"""
  <rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" fill="#fff" stroke="#7c3aed" stroke-width="2" stroke-dasharray="6,4"/>
  <rect x="{x}" y="{y}" width="{w}" height="32" rx="12" fill="#7c3aed"/>
  <text x="{x+w//2}" y="{y+22}" text-anchor="middle" class="tag">{label}</text>
  <text x="{x+w//2}" y="{y+62}" text-anchor="middle" class="box-text-bold">2-of-2 p2sh</text>
  {f'<text x="{x+w//2}" y="{y+88}" text-anchor="middle" class="box-small">{sub}</text>' if sub else ''}
"""

# ============================================================================
STEPS = []

# STEP 1 — Two parties want to lend
STEPS.append((
    "Two parties, no middleman",
    "Alice wants to borrow. Bob wants to lend. Both have a Verus wallet.",
    """
  """ + party_box(150, 230, 360, 180, "#2563eb", "BORROWER", "Alice", "Has 10 VRSC collateral") + """
  """ + party_box(690, 230, 360, 180, "#059669", "LENDER", "Bob", "Has 5 DAI to lend") + """
  <path d="M 530 320 L 670 320" stroke="#475569" stroke-width="3" stroke-dasharray="8,6" fill="none"/>
  <text x="600" y="305" text-anchor="middle" class="box-small">agreement off-chain</text>
  <text x="600" y="475" text-anchor="middle" class="caption" font-weight="600">No bank. No platform. No registration.</text>
  <text x="600" y="510" text-anchor="middle" class="caption">Two pubkeys, one chain.</text>
""",
))

# STEP 2 — The vault (deterministic)
STEPS.append((
    "The vault: derived, not registered",
    "Both parties compute the same address independently. No fee. No on-chain step.",
    """
  """ + party_box(50, 280, 280, 130, "#2563eb", "ALICE", "pubkey 03e0...9640") + """
  """ + party_box(870, 280, 280, 130, "#059669", "BOB", "pubkey 0270...8250") + """
  <path d="M 330 345 L 460 345" stroke="#475569" stroke-width="2" marker-end="url(#arrow-gray)" fill="none"/>
  <path d="M 870 345 L 740 345" stroke="#475569" stroke-width="2" marker-end="url(#arrow-gray)" fill="none"/>
  """ + vault_box(460, 280, 280, 130, "VAULT", "bYCcAqB7KfdkfsN8YUipb...") + """
  <text x="600" y="465" text-anchor="middle" class="caption" font-weight="700">2-of-2 p2sh script hash</text>
  <text x="600" y="495" text-anchor="middle" class="caption">Either party can compute. Both must sign to spend.</text>
  <text x="600" y="525" text-anchor="middle" class="box-small">No VerusID needed. No registration tx. Zero cost.</text>
""",
))

# STEP 3 — The offer (Tx-O pre-signed)
STEPS.append((
    "The offer: pre-signed, irrevocable",
    "Bob signs an atomic offer offline. Hands the hex to Alice.",
    """
  """ + party_box(870, 230, 280, 220, "#059669", "BOB (LENDER)", "pre-signs offline") + """
  <text x="1010" y="370" text-anchor="middle" class="box-small">Input 0: 5 DAI UTXO</text>
  <text x="1010" y="392" text-anchor="middle" class="box-small">Output 0: 5 DAI → Alice</text>
  <text x="1010" y="414" text-anchor="middle" class="box-small" fill="#7c3aed" font-weight="700">SIGHASH_SINGLE | ANYONECANPAY</text>
  <path d="M 870 340 L 540 340" stroke="#7c3aed" stroke-width="3" marker-end="url(#arrow-purple)" fill="none"/>
  <text x="700" y="325" text-anchor="middle" class="box-small" fill="#7c3aed">offer hex</text>
  """ + party_box(150, 230, 360, 220, "#2563eb", "ALICE (BORROWER)", "holds offer", "broadcasts when ready") + """
  <text x="600" y="495" text-anchor="middle" class="caption" font-weight="700">Bob's signature locks Output 0 to Alice</text>
  <text x="600" y="525" text-anchor="middle" class="box-small">Bob cannot retract — only cancel by spending Input 0 elsewhere</text>
""",
))

# STEP 4 — Origination broadcast
STEPS.append((
    "Origination: atomic in one transaction",
    "Alice extends the offer with her collateral input + outputs, then broadcasts.",
    """
  """ + party_box(40, 230, 280, 130, "#2563eb", "ALICE", "10 VRSC") + """
  """ + party_box(880, 230, 280, 130, "#059669", "BOB", "5 DAI (signed in)") + """
  <path d="M 320 290 L 460 320" stroke="#2563eb" stroke-width="3" marker-end="url(#arrow-blue)" fill="none"/>
  <path d="M 880 290 L 740 320" stroke="#059669" stroke-width="3" marker-end="url(#arrow-green)" fill="none"/>
  <rect x="350" y="320" width="500" height="180" rx="12" fill="#fff" stroke="#0f172a" stroke-width="3"/>
  <text x="600" y="350" text-anchor="middle" class="box-text-bold">Tx-O — atomic origination</text>
  <text x="600" y="378" text-anchor="middle" class="box-text">Input 0: Bob's 5 DAI (sig-locked)</text>
  <text x="600" y="402" text-anchor="middle" class="box-text">Input 1: Alice's 10 VRSC</text>
  <text x="600" y="426" text-anchor="middle" class="box-text">Output 0: 5 DAI → Alice (principal)</text>
  <text x="600" y="450" text-anchor="middle" class="box-text">Output 1: 10 VRSC → vault (collateral)</text>
  <text x="600" y="474" text-anchor="middle" class="box-text">Output 2: change</text>
  <text x="600" y="555" text-anchor="middle" class="caption">One block. Both sides happen, or neither does.</text>
  <text x="600" y="585" text-anchor="middle" class="box-small">Reorg-safe: if reorged, both inputs return to source. Loan never happened.</text>
""",
))

# STEP 5 — Active loan, three pre-signed settlements
STEPS.append((
    "Loan active: nothing on chain",
    "Three pre-signed settlement transactions are held off-chain. Same SIGHASH discipline in each.",
    """
  """ + party_box(40, 230, 270, 320, "#2563eb", "ALICE", "Tx-Repay (held)", "broadcasts to repay") + """
  """ + vault_box(465, 240, 270, 130, "VAULT", "10 VRSC locked") + """
  <text x="600" y="430" text-anchor="middle" class="box-small">collateral untouched</text>
  <text x="600" y="455" text-anchor="middle" class="box-small">until one of the three</text>
  <text x="600" y="480" text-anchor="middle" class="box-small">pre-signed txs broadcasts</text>
  """ + party_box(890, 230, 270, 320, "#059669", "BOB", "Tx-B (held)", "broadcasts on default") + """
  <rect x="400" y="510" width="400" height="80" rx="8" fill="#fef3c7" stroke="#f59e0b" stroke-width="2"/>
  <text x="600" y="540" text-anchor="middle" class="box-text-bold" fill="#92400e">Tx-C (rescue, held by Alice)</text>
  <text x="600" y="568" text-anchor="middle" class="box-small">far-future fallback if both sides abandon</text>
""",
))

# STEP 6 — Happy path
STEPS.append((
    "Settle: borrower repays unilaterally",
    "Alice extends Tx-Repay with 5.5 DAI strike, broadcasts. Bob never has to sign anything.",
    """
  """ + party_box(40, 230, 270, 240, "#2563eb", "ALICE", "extends Tx-Repay", "+ 5.5 DAI input + change") + """
  <path d="M 310 350 L 455 350" stroke="#2563eb" stroke-width="3" marker-end="url(#arrow-blue)" fill="none"/>
  <rect x="465" y="240" width="270" height="220" rx="12" fill="#fff" stroke="#0f172a" stroke-width="2"/>
  <text x="600" y="270" text-anchor="middle" class="box-text-bold">Tx-Repay broadcast</text>
  <text x="600" y="305" text-anchor="middle" class="box-text">vault → 0</text>
  <text x="600" y="335" text-anchor="middle" class="box-text" fill="#059669">Bob: +5.5 DAI</text>
  <text x="600" y="365" text-anchor="middle" class="box-text" fill="#2563eb">Alice: +10 VRSC back</text>
  <text x="600" y="400" text-anchor="middle" class="box-small">atomic settlement</text>
  <text x="600" y="425" text-anchor="middle" class="box-small">one block</text>
  <path d="M 745 350 L 880 350" stroke="#059669" stroke-width="3" marker-end="url(#arrow-green)" fill="none"/>
  """ + party_box(880, 230, 270, 240, "#059669", "BOB", "receives 5.5 DAI", "no live action needed") + """
  <text x="600" y="540" text-anchor="middle" class="caption" font-weight="700">Lender stonewalling is structurally impossible.</text>
  <text x="600" y="575" text-anchor="middle" class="box-small">Bob's signature was made at origination. The math is final.</text>
""",
))

# STEP 7 — Default path
STEPS.append((
    "Default: lender claims after maturity",
    "If Alice doesn't repay, Bob broadcasts Tx-B once nLockTime is reached.",
    """
  """ + party_box(40, 230, 270, 240, "#2563eb", "ALICE", "(does nothing)", "defaulted") + """
  <rect x="465" y="240" width="270" height="220" rx="12" fill="#fff" stroke="#0f172a" stroke-width="2"/>
  <text x="600" y="270" text-anchor="middle" class="box-text-bold">Tx-B broadcast</text>
  <text x="600" y="295" text-anchor="middle" class="box-small" fill="#dc2626">at maturity + grace</text>
  <text x="600" y="330" text-anchor="middle" class="box-text">vault → 0</text>
  <text x="600" y="360" text-anchor="middle" class="box-text" fill="#059669">Bob: +10 VRSC (collateral)</text>
  <text x="600" y="390" text-anchor="middle" class="box-text" fill="#2563eb">Alice: keeps 5 DAI principal</text>
  <text x="600" y="425" text-anchor="middle" class="box-small">net: collateral → lender</text>
  <path d="M 745 350 L 880 350" stroke="#059669" stroke-width="3" marker-end="url(#arrow-green)" fill="none"/>
  """ + party_box(880, 230, 270, 240, "#059669", "BOB", "extends Tx-B", "+ fee input + change") + """
  <text x="600" y="540" text-anchor="middle" class="caption" font-weight="700">Pre-locktime broadcast rejected by chain consensus.</text>
  <text x="600" y="575" text-anchor="middle" class="box-small">Reorg-safe: 6-10 confirmations and the claim is final.</text>
""",
))

# STEP 8 — Why it matters / general primitive
STEPS.append((
    "The same primitive does much more",
    "Lending is one application. The pattern enables p2p swaps, options, NFTs, ID transfers, escrow.",
    """
  <rect x="40" y="220" width="1120" height="370" rx="12" fill="#fff" stroke="#0f172a" stroke-width="2"/>
  <text x="600" y="262" text-anchor="middle" class="box-text-bold">SIGHASH_SINGLE | ANYONECANPAY pre-commitment</text>

  <rect x="80" y="290" width="220" height="100" rx="8" fill="#dbeafe" stroke="#2563eb" stroke-width="1.5"/>
  <text x="190" y="325" text-anchor="middle" class="box-text-bold">p2p currency swap</text>
  <text x="190" y="354" text-anchor="middle" class="box-small">replaces order-book DEXs</text>

  <rect x="320" y="290" width="220" height="100" rx="8" fill="#dcfce7" stroke="#059669" stroke-width="1.5"/>
  <text x="430" y="325" text-anchor="middle" class="box-text-bold">options market</text>
  <text x="430" y="354" text-anchor="middle" class="box-small">expiryheight = expiration</text>

  <rect x="560" y="290" width="220" height="100" rx="8" fill="#fef3c7" stroke="#f59e0b" stroke-width="1.5"/>
  <text x="670" y="325" text-anchor="middle" class="box-text-bold">NFT marketplace</text>
  <text x="670" y="354" text-anchor="middle" class="box-small">no platform fee</text>

  <rect x="800" y="290" width="320" height="100" rx="8" fill="#ede9fe" stroke="#7c3aed" stroke-width="1.5"/>
  <text x="960" y="325" text-anchor="middle" class="box-text-bold">VerusID transfer / sale</text>
  <text x="960" y="354" text-anchor="middle" class="box-small">atomic ID-for-currency</text>

  <rect x="80" y="410" width="320" height="100" rx="8" fill="#fce7f3" stroke="#db2777" stroke-width="1.5"/>
  <text x="240" y="445" text-anchor="middle" class="box-text-bold">conditional escrow</text>
  <text x="240" y="474" text-anchor="middle" class="box-small">delivery-triggered payment</text>

  <rect x="420" y="410" width="320" height="100" rx="8" fill="#cffafe" stroke="#0891b2" stroke-width="1.5"/>
  <text x="580" y="445" text-anchor="middle" class="box-text-bold">limit orders</text>
  <text x="580" y="474" text-anchor="middle" class="box-small">price-triggered fills</text>

  <rect x="760" y="410" width="360" height="100" rx="8" fill="#e0e7ff" stroke="#4f46e5" stroke-width="1.5"/>
  <text x="940" y="445" text-anchor="middle" class="box-text-bold">collateralized lending</text>
  <text x="940" y="474" text-anchor="middle" class="box-small">this protocol — Tx-O, Tx-Repay, Tx-B, Tx-C</text>

  <text x="600" y="555" text-anchor="middle" class="caption" font-weight="700">No new opcodes. No tokens. No DAOs. No oracles. No custodians.</text>
""",
))

def make_svg(step_num, title, subtitle, body):
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 675" font-family="system-ui, -apple-system, sans-serif">
  <style>{STYLE}</style>
  {DEFS}
  {header(step_num, len(STEPS), title, subtitle)}
  {body}
  {footer()}
</svg>"""

if __name__ == '__main__':
    os.makedirs(OUTDIR, exist_ok=True)
    for i, (title, subtitle, body) in enumerate(STEPS, 1):
        svg = make_svg(i, title, subtitle, body)
        svg_path = os.path.join(OUTDIR, f'step-{i}.svg')
        png_path = os.path.join(OUTDIR, f'step-{i}.png')
        with open(svg_path, 'w') as f:
            f.write(svg)
        cairosvg.svg2png(url=svg_path, write_to=png_path, output_width=2400)
        print(f'wrote {png_path}')
    print(f'\n{len(STEPS)} images generated.')

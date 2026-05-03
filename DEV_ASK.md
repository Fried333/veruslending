# Verus Core — Enhancement Request

**Context:** [VerusLending](./SPEC.md) is a peer-to-peer collateralized credit protocol composed entirely from existing Verus primitives. The protocol's chain-level mechanics are fully validated on Verus mainnet (34 test scenarios, see [TESTING.md](./TESTING.md)).

**The protocol works today on Verus 1.2.16. No chain changes are required for it to function.** This document describes a single small RPC enhancement that would substantially improve the user experience by removing the need for client-side helper code in one specific phase.

---

## Background

The protocol uses `SIGHASH_SINGLE | SIGHASH_ANYONECANPAY` pre-commitment as its foundational primitive. This is the same SIGHASH discipline the Verus marketplace already uses internally for `makeoffer`/`takeoffer`.

**Three of four protocol phases are fully pure-CLI today** using existing RPCs:
- **Tx-O** (atomic origination): `makeoffer` + `takeoffer` (validated TESTING §34)
- **Tx-B** (default-claim): same
- **Tx-C** (rescue): same

**One phase requires a client-side helper:**
- **Tx-Repay** (settlement): the lender pre-commits at origination via a 2-of-2 vault, the borrower takes alone at any time before maturity. The `makeoffer` API does not support multi-sig pre-commitments because it operates on wallet keys only.

We currently work around this with an ~80-line Python helper (`extend_tx.py`) that performs raw-tx serialization to splice signatures. This works perfectly but means wallets implementing the protocol need their own equivalent helper. With one small Verus RPC enhancement, the entire protocol could run on pure CLI with no helper code anywhere.

---

## Proposed enhancement (in order of preference)

### Option A — `extendrawtransaction` RPC (most general)

```
extendrawtransaction "hex" '{
  "add_inputs":  [{"txid": "...", "vout": n, "sequence": n}, ...],
  "add_outputs": {"address": amount, ...} | with currency objects
}'
```

Returns a new hex with the additions appended, **preserving any existing signatures on the original inputs**. Equivalent to manually splicing a signed-input tx with new vins/vouts.

This is the most general primitive. It would let any pre-signed multi-sig template be extended, not just marketplace offers. Useful for:
- VerusLending's Tx-Repay
- Any custom multi-sig escrow built on `SIGHASH_SINGLE | ANYONECANPAY`
- Protocol research generally

**Effort estimate:** small. Exposes existing internal tx-byte manipulation logic.

### Option B — `cosignoffer` RPC

```
cosignoffer "offer-hex"
```

Takes an offer hex (single-signed via `makeoffer`) and adds the wallet's signature, producing a multi-sig cosigned offer hex. Each party calls it sequentially; the final hex is takeable via `takeoffer` like any normal offer.

**Effort estimate:** very small. Reuses existing offer-format signing infrastructure.

### Option C — `makeoffer` with explicit `privkeys` param

```
makeoffer fromaddress '{...}' (returntx) (feeamount) (privkeys)
```

Optional list of explicit privkeys, mirroring `signrawtransaction`. Lets a caller import the second signer's key temporarily (or use a node with both keys). The 2-of-2 vault makeoffer becomes a single RPC call.

**Effort estimate:** very small. Adds one optional parameter.

---

## Why this matters for the broader Verus ecosystem

The enhancement isn't VerusLending-specific. It enables:

1. **Custom multi-sig escrow patterns** — any application requiring "M-of-N parties pre-commit at offer time, taker takes later" can use the marketplace RPCs without needing client code.
2. **Cross-chain atomic swap research** — same primitive applies to PBaaS bridges.
3. **Options market implementations** — VerusLending's `expiryheight`-gated exercise pattern (validated TESTING §26-§27) becomes pure CLI.
4. **NFT marketplace with multi-sig holding** — co-owned NFTs traded via cosigned offers.
5. **Any protocol that wants offer-format on-chain offers signed by 2-of-2 / N-of-M parties.**

This is a small change to surface area, but unlocks a class of patterns that currently require off-chain coordination + helper scripts.

---

## What we already have without this enhancement

The protocol works today using:
- `signrawtransaction <hex> null null "SINGLE|ANYONECANPAY"` (validated TESTING §32)
- A small client-side raw-tx extension helper (`extend_tx.py`, ~80 lines, in this repo)
- `makeoffer` / `takeoffer` for non-multi-sig phases
- `updateidentity` / `getidentity` for marketplace data layer

So the request isn't blocking. It's a polish-and-reach improvement that would let us ship a CLI-only reference implementation usable by anyone with stock Verus.

---

## Validation evidence

All claims above are backed by mainnet test data:

| Claim | Validation reference |
|---|---|
| Protocol works on Verus 1.2.16 | TESTING.md §16-§34 (34 tests, all txids public) |
| `signrawtransaction null null` works for cryptocondition reserve inputs | §32 (txid `086fb3ee...`) |
| `makeoffer`/`takeoffer` works cross-currency | §34 (txid `f2ce9faa...`) |
| Extension via byte-splicing works | §20, §21, §25, §26, §27 (multiple txids) |

The repo is at github.com/Fried333/veruslending. Spec at [SPEC.md](./SPEC.md). Briefing at [BRIEF.md](./BRIEF.md).

---

## What we're asking

If any of the three options above is small enough to fit on a near-term release, we'd implement against it and ship a CLI-only reference. If not, we'll continue with the helper-script approach and the protocol still ships — just with a slightly less elegant UX.

Either way, we're shipping. The question is just whether Verus core wants to bake in support for this class of pattern at the RPC level.

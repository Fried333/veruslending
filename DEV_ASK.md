# Verus Core — Question for the Dev Team

**Repo:** [github.com/Fried333/veruslending](https://github.com/Fried333/veruslending)
**Spec:** [SPEC.md](./SPEC.md)
**Validation:** [TESTING.md](./TESTING.md) — 36 mainnet test scenarios with public txids
**Brief:** [BRIEF.md](./BRIEF.md) — 5-minute summary

---

## What we built

A peer-to-peer collateralized credit protocol composed entirely from existing Verus primitives — same `SIGHASH_SINGLE | SIGHASH_ANYONECANPAY` pattern that the marketplace already uses internally for `makeoffer`/`takeoffer`. No new opcodes, no consensus changes, no protocol token.

The protocol works on Verus 1.2.16 today. The spec also documents how the same primitive supports adjacent applications:

- **Lending** (collateralized loans, async settlement, default-claim, rescue) — full lifecycle validated
- **Options markets** (atomic premium handling, exercise with expiryheight, expiration recovery) — full lifecycle validated
- **Generic p2p atomic swaps** (any currency pair) — validated
- **Conditional escrow** (time-locked + multi-party) — pattern documented
- **VerusID transfer / sale** — same primitive
- **NFT marketplace** — same primitive
- **A chain-native marketplace data layer** for offer discovery and reputation tracking via VerusID contentmultimap — validated

36 distinct mainnet validations cover all of the above, with txids and full procedures in TESTING.md.

---

## What works pure-CLI today (no helper code)

A surprising amount works with stock `verusd` RPCs alone:

| Phase | Mechanism | Validated |
|---|---|---|
| Marketplace data layer (offers, requests, history) | `updateidentity` / `getidentity` + VDXF keys | §33 |
| Tx-O atomic origination | `makeoffer` + `takeoffer` with vault as accept | §25, §36 |
| Tx-B default-claim (collateral-pays-fee) | `makeoffer` + `takeoffer` at maturity | §17, §19 |
| Tx-C rescue (collateral-pays-fee) | `makeoffer` + `takeoffer` after locktime | §23 |
| Cross-currency atomic swap | `makeoffer` + `takeoffer` cross-currency | §34 |
| Atomic premium-plus-option setup | `makeoffer` + `takeoffer` with vault as accept | §36 |
| Pre-signing settlement templates | `signrawtransaction null null "SINGLE\|ANYONECANPAY"` | §32 |
| Output 0 sig-locking | the ECDSA primitive, validated under tampering | §24 |

Three of the four protocol phases are stock CLI. The marketplace data layer is stock CLI. The validated cross-currency, multi-currency-vault, i-address-recipient, and adversarial-tampering rejection are all stock CLI.

---

## The one gap

**Settlement-tx broadcast with extension** — specifically:

- **Tx-Repay (settlement)**: borrower needs to extend a pre-signed Tx-Repay template with their own funding inputs and outputs at broadcast time, while preserving Bob's pre-signed Input 0.
- **Options exercise**: same — buyer extends a pre-signed exercise tx with strike input.
- **Broadcaster-pays-fee variants of Tx-B and Tx-Repay**: same.

These all share one mechanic: take a tx hex with already-signed inputs, append new inputs (with empty scriptSigs) and new outputs, return the resulting hex while preserving existing scriptSigs. Pure tx-byte serialization, no key handling.

We've shipped this as an ~80-line Python helper (`extend_tx.py` in this repo). It works perfectly. But each wallet implementing the protocol needs the equivalent in their language.

---

## Why this gap exists (our reading of the design intent)

Looking at the marketplace's API surface, it's clearly designed for the typical case of P2P trading:

- **Single-signer makeoffer** — one user's wallet, one offer
- **Wallet-key signing** — clean UX for individual traders
- **Atomic settlement** — taker provides their side, no further coordination
- **Permissionless** — no order book, no matching engine

This is a clean, well-scoped design. It covers the vast majority of trading use cases. Multi-sig pre-commitments, predicted-future-UTXO references, and settlement-time tx extension were left to lower-level tools (raw tx + signrawtransaction) — which is reasonable, since those are minority use cases.

What our protocol needs is the lower-level primitive that `takeoffer` already does internally — adding the taker's contribution to a maker's pre-signed offer. We just want to do it on a generic raw tx (multi-sig vault input) rather than on a marketplace-format offer output.

---

## The question

**Is there a way to do raw-tx extension (preserve existing scriptSigs while adding new inputs/outputs) using existing Verus RPCs that we're missing?**

If yes — please point us to it. We'll use it and skip the Python helper.

If no — we ship with the helper script. The protocol works either way, we're not blocked. The question is whether you'd be open to adding a small RPC that exposes this primitive at the CLI level.

---

## If it's open to discussion: three small enhancement options

In rough order of generality (and our preference):

### Option A — `extendrawtransaction` RPC

```
extendrawtransaction "hex" '{
  "add_inputs":  [{"txid": "...", "vout": n, "sequence": n}, ...],
  "add_outputs": <createrawtransaction-style output spec>
}'
returns "<extended hex>"
```

Pure tx-byte manipulation. Adds inputs (with empty scriptSig) and outputs to a tx hex, preserving existing scriptSigs. Equivalent to:
- Parse hex → modify vins/vouts → re-serialize

Doesn't touch crypto, keys, mempool, or chain state. Just byte serialization.

**Effort:** small. The internal logic exists (`takeoffer` does it).

**Generality:** anyone building on `SIGHASH_SINGLE | ANYONECANPAY` patterns benefits. Custom escrow, options markets, multi-sig settlement protocols, anything that needs "pre-sign, extend later" semantics.

### Option B — `cosignoffer` RPC

```
cosignoffer "offer-hex"
returns "<offer-hex with this wallet's signature added>"
```

For an offer hex that requires multi-sig (e.g., from a 2-of-2 vault), each party calls this to add their signature. The result is a fully-cosigned offer hex takeable via `takeoffer`.

**Effort:** very small.

**Use case:** narrower (specifically multi-sig offers) but addresses our core gap directly.

### Option C — `makeoffer` accepts optional `privkeys` param

```
makeoffer fromaddress '{...}' (returntx) (feeamount) (privkeys)
```

Mirrors `signrawtransaction`'s privkeys parameter. Lets a caller pass external keys (e.g., temporary import for a 2-of-2 vault).

**Effort:** very small.

**Use case:** narrowest, but lets makeoffer handle multi-sig inputs natively.

Any of these would close the gap. Option A is the most general; Option C is the smallest API change.

---

## What's NOT being asked

We're explicitly not asking for:
- New cryptographic primitives
- Changes to consensus or chain rules
- New SIGHASH flags or output types
- Special handling for our protocol — these enhancements would help any protocol building on the same pattern

---

## Signaling our commitment

The protocol is fully validated, the spec is stable, the brief is ready for your dev community. We have public Twitter-friendly cards for outreach. The remaining work is wallet implementation, which is application-layer engineering, not Verus core work.

Whether you take any of the three options or not, we're shipping. We'd just rather ship with stock CLI working than with a "gotcha — also requires this Python script" footnote.

---

## Some context on what this enables

If the lending + options + escrow primitive becomes broadly available (with or without your enhancement), Verus has:

- **A permissionless lending market** with chain-enforced credit identity (no centralized credit bureau)
- **A trustless options market** with native expiration and rug-pull-resistant collateral handling
- **A native marketplace data layer** that any wallet/explorer can render without operating infrastructure
- **A primitive set that can be composed** for custom escrow, conditional payments, NFT trading, ID transfers

All on existing chain features. The marketplace's `makeoffer` design philosophy — clean primitives, composable, atomic — extends naturally to these use cases. The protocol's contribution is the multi-phase choreography; the chain's contribution is the primitives.

We think this is a meaningful addition to the Verus ecosystem regardless of whether the enhancement lands. The enhancement just makes the UX cleaner.

---

## Validation evidence

All claims above are backed by mainnet test data. Selected highlights:

| Claim | Validation |
|---|---|
| Cross-currency atomic swap pure CLI | §34 — tx `f2ce9faa20c72bb46d3678bde5f8f2a81eb600af2cc73c61d7e5656ea3875c7a` |
| Output 0 tampering rejected | §24 — `mandatory-script-verify-flag-failed` |
| `signrawtransaction null null` works for cryptocondition reserve inputs | §32 — tx `086fb3eebfe31ef2b3191d5d2f7c48f615988700403ac68d8fdb37c779d985c1` |
| Marketplace data layer cross-node read | §33 — tx `694ed5cfc13d4fb0234d7fa2759a336b163c59b42ee0b71581ff816062bb00a8` |
| Atomic premium + vault deposit pattern | §36 — tx `c419b7fcc001a9e6993112be1e6e6d817928beda9a86867d57a840592ff0bb3c` |
| Tx-Repay invalidates Tx-B (mutex) | §22, §29 — `bad-txns-inputs-spent` |
| Pre-locktime broadcast rejected | §17, §19 — `64: non-final` |
| Pre-expiryheight broadcast rejected | §27 — `tx-expiring-soon` |

Full table of 36 tests with txids in TESTING.md.

---

**Contact:** open an issue on github.com/Fried333/veruslending or reach out via the Verus dev community. Happy to demonstrate any test on a video call or walk through the spec.

# VerusLending — Developer Brief

**Single-page summary for review.** Full spec in [SPEC.md](./SPEC.md), full test results in [TESTING.md](./TESTING.md).

---

## What this is

A peer-to-peer collateralized credit protocol built on **existing Verus signature primitives** — no new opcodes, no consensus changes. It uses the same `SIGHASH_SINGLE | SIGHASH_ANYONECANPAY` pattern that the Verus marketplace already uses internally for offer construction, but lifted to the raw-tx level for direct multi-phase choreography.

**Key claim:** The lending protocol is one specialization of a general primitive. The same primitive — "Maker irrevocably pre-commits to an output, Taker triggers atomically" — also enables p2p currency swaps, NFT marketplaces, VerusID sales, options markets, conditional escrow, and limit orders, all with no protocol token, no smart contract, no oracle, and no custodian.

---

## The core primitive

```
Maker pre-signs offline:
  Input 0:  Maker's UTXO              (signed SIGHASH_SINGLE | ANYONECANPAY)
  Output 0: agreed delivery → Taker   (sig-locked, paired with Input 0)
  [optional] expiryheight             (tx invalid after block N)
  [optional] nLockTime                (tx invalid before block N)

Taker fills atomically:
  Input 1:  Taker's UTXO              (signed SIGHASH_ALL)
  Output 1: agreed payment → Maker    (Taker constructs)
  Output 2: Taker's change

One tx. Atomic. Either both sides happen or neither does.
```

**Properties:**
- Maker pre-commits irreversibly. Cannot retract — except by spending Input 0 elsewhere (cancels offer).
- Taker owns the broadcast moment. Async UX, no synchronous ceremony required.
- Output 0's recipient + amount is signed-locked. Cannot be redirected or reduced. *Validated on mainnet — see §24 below*.
- nLockTime gates the earliest broadcast moment.
- expiryheight gates the latest. Both are chain-enforced by the daemon.
- Reorgs are recoverable: pre-signed txs don't depend on chain state.

---

## The lending protocol — fully symmetric across 4 phases

Every phase uses the same primitive:

| Phase | Tx | Pre-signer(s) | Triggerer | Locks | Notes |
|---|---|---|---|---|---|
| Origination | Tx-O | Lender | Borrower | (none) | Async; lender posts offer, borrower takes when ready |
| Settlement | Tx-Repay | Both | Borrower | expiryheight=maturity | Borrower repays unilaterally |
| Default | Tx-B | Both | Lender | nLockTime=maturity+grace | Lender claims if no repayment |
| Rescue | Tx-C | Both | Borrower | nLockTime=maturity+1yr | Last-resort, both abandoned |

**The vault** (the address holding collateral) can be either:
- **Profile L:** 2-of-2 p2sh from pubkeys. No registration. Zero cost. (validated, all today's tests)
- **Profile V:** 2-of-2 VerusID with null revoke/recover. Costs sub-ID fee (~0.1 VRSC) or 100 VRSC for top-level. Adds naming + multimap UX. (validated, prior tests §16-§17)

Identical cryptographic guarantees. Choice is operational, not security.

---

## Validation table — Verus mainnet

Every claim in the spec is empirically validated. 26 distinct test scenarios — txids verifiable on any explorer.

### Earlier validation (v0.4, with VerusID vault)

| § | Result | Tx |
|---|---|---|
| 16 | Full canonical lifecycle — Tx-A origination → Tx-Repay settlement | `286ba62f6823...` |
| 17 | Default path — Tx-B with nLockTime + pre-locktime rejection | `70eb365d6969...` |

### Today (v0.5, with p2sh vault, cross-currency, all four phases)

Vault: `bYCcAqB7KfdkfsN8YUipb2fuFhKvxmsnne` (p2sh, no VerusID)

| § | Test | Result | Tx |
|---|---|---|---|
| 18 | Cross-currency happy (10 VRSC + 5 DAI principal) | ✅ | Tx-A `3b23258b...`, Tx-Repay `25564b4c...` |
| 19 | Cross-currency default | ✅ | Tx-A `98ce7f2d...`, Tx-B `fb1b58b7...` |
| 20 | Broadcaster-pays-fee Tx-Repay (full collateral return) | ✅ | `59e743d1...` |
| 21 | Broadcaster-pays-fee Tx-B with SIGHASH_SINGLE\|ANYONECANPAY | ✅ | `ab8be393...` |
| 22 | Tx-Repay broadcast invalidates pre-signed Tx-B | ✅ — `bad-txns-inputs-spent` | (rejected) |
| 23 | **Tx-C rescue path** (first mainnet validation ever) | ✅ | `3a2943fb...` |
| 24 | Output 0 tampering (D1 recipient, D2 amount) rejected | ✅ — `mandatory-script-verify-flag-failed` | (rejected) |
| 25 | **Tx-O atomic-swap origination** | ✅ | `023d3256...` |
| 26 | **Options primitive: pre-paid premium + atomic exercise + expiryheight** | ✅ confirmed | `f48ba0c3...` (block `0000000000004a0c...`) |
| 27 | **Options expired path: rejection + writer recovers underlying** | ✅ confirmed | `4c53edf6...` (return); exercise-attempt rejected `tx-expiring-soon` |
| 28 | **SIGHASH-pre-signed Output 0 to a VerusID i-address** | ✅ confirmed | `40104bf7...` |
| 29 | **B4: Tx-Repay rejected after Tx-B (symmetric to A4)** | ✅ rejected `bad-txns-inputs-spent` | (rejected) |
| 30 | **Generic p2p atomic currency swap (no loan structure)** | ✅ confirmed | `9be44e07...` |
| 31 | H1 part 1: non-VRSC collateral via cooperative SIGHASH_ALL | ✅ confirmed | `a454afc2...` |
| 32 | **H1 corrected: non-VRSC collateral works with SIGHASH_SINGLE\|ANYONECANPAY** (wallet key-lookup path required) | ✅ confirmed | `086fb3ee...` |

### What this proves

1. Protocol works without VerusIDs. Just p2sh + raw transactions.
2. Cross-currency is native. VRSC collateral + DAI principal works in one atomic tx.
3. SIGHASH_SINGLE|ANYONECANPAY locks Output 0 immutably. Borrower cannot redirect or short-pay (validated by tampering attempts that all rejected with `mandatory-script-verify-flag-failed`).
4. Pre-locktime broadcasts rejected (`64: non-final`). Pre-expiry broadcasts rejected (`tx-expiring-soon`).
5. Multi-tx mempool chains work (Tx-O + settlement in same block).
6. The same primitive works for non-lending applications — see §26 (options exercise).

---

## What this enables beyond lending

The same primitive (Maker pre-commits, Taker triggers, optionally locktime/expiryheight gated) supports:

| Application | How |
|---|---|
| **Generic p2p currency swap** | Output 0 = currency-A; Taker delivers currency-B. Replaces order book DEXs for any pair. |
| **VerusID sale** | Output 0 = `updateidentity` transferring an ID; Taker pays in any currency. |
| **NFT marketplace** | NFTs are unique-supply Verus tokens. Same swap pattern. |
| **Cross-currency basket trades** | Output 0 = multi-currency cryptocondition. |
| **Options markets** | Maker (writer) pre-signs exercise tx with `expiryheight=expiration`. Taker (buyer) exercises before expiry. American or European via nLockTime. *Premium handled via separate atomic transfer (validated §26).* |
| **Conditional escrow** | Maker releases payment only if Taker delivers a specific output. |
| **Limit orders** | Maker pre-signs at target price; Takers fill when market reaches it. |
| **Bounty payments** | Maker pre-commits; first valid delivery claims. |
| **Lending** | What this spec describes — 4 pre-signed transactions, one per phase. |

---

## Why this matters for Verus

**No new chain-level features needed.** Everything described above runs on Verus 1.2.16 today.

**No tokens, no DAO, no custodial layer.** Pure cryptographic enforcement at the raw-tx level. The marketplace's offer pattern was already this primitive in disguise — we're just exposing it directly.

**Composable.** A wallet that implements the SIGHASH_SINGLE|ANYONECANPAY ceremony for one application (e.g. swaps) gets all of the others for free.

**Reorg-safe.** Pre-signed txs don't depend on chain state. Reorgs trigger rebroadcast or void unconfirmed loans cleanly. No party can lose value to a reorg.

**Profile L is fully VerusID-free.** Important for casual users who don't have IDs and don't want to register one. The protocol's correctness doesn't depend on Verus's identity layer — it just uses standard Bitcoin-compatible signature primitives that Verus inherits.

---

## Open spec questions / areas where dev input would help

1. **Predicted-txid for settlement template references.** The current spec assumes deterministic ECDSA (RFC 6979) makes Tx-O's txid stable from its unsigned form. Is this safe to rely on, or should there be a canonical "compute txid before signing" method?

2. **Options market — atomic premium for hex.** §11.6 sketches Profile-V option transfer (option as sub-ID, sold via atomic ID transfer). Is there a Profile-L equivalent, or does Profile V become required for options?

3. **Cross-chain collateral.** Can Verus PBaaS bridges hold pre-signed templates referencing a UTXO on the bridged chain, or does the entire ceremony need to live on the destination chain?

4. **VerusID multimap as encrypted hex storage.** The spec mentions storing pre-signed hex in the vault's contentmultimap (Profile V) as durable backup. What's the canonical encryption scheme — z-key based, or something else?

5. **Template outputs (mentioned in README's Acknowledgments).** When this lands, would it simplify any of the SIGHASH manipulation we currently use?

---

## What's done vs. what's next

**Done:**
- Spec v0.5 covering all four phases (SPEC.md)
- 26 mainnet validations (TESTING.md)
- Scenario test matrix with execution priority (SCENARIOS.md)
- Step-by-step protocol lifecycle diagram (diagram.svg)

**Next (in order of leverage):**
1. Reference wallet implementation — handles the SIGHASH ceremony, multi-currency tx construction, and storage of pre-signed hex
2. VDXF schema for offer/accept/loan-state messages
3. Browser-based marketplace UX leveraging Tx-O atomic origination
4. Validate non-VRSC collateral in practice (e.g., tBTC.vETH as collateral) — should work per §18 cross-currency results, not directly tested
5. Wallet-level death/inheritance UX (off-chain storage durability)

---

## Repo

- [SPEC.md](./SPEC.md) — formal protocol specification
- [TESTING.md](./TESTING.md) — empirical validation, all txids
- [SCENARIOS.md](./SCENARIOS.md) — full scenario test matrix
- [diagram.svg](./diagram.svg) — visual lifecycle
- [LICENSE](./LICENSE) — MIT

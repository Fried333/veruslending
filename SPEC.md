# VerusLending — Protocol Specification v1.0

**Status:** Chain-level mechanics fully validated on Verus mainnet (36 test scenarios — see [TESTING.md](./TESTING.md) for txids). Reference wallet implementation is v1.x roadmap, outside the spec.
**Date:** 2026-05
**Target chain:** Verus (VRSC), version ≥ 1.2.16

A peer-to-peer collateralized credit protocol composed entirely from existing Verus primitives. No new opcodes, no consensus changes, no protocol token. The full lifecycle — discovery, ceremony coordination, origination, settlement, default, rescue, reputation tracking — runs on chain via a small set of pre-signed transactions plus VerusID contentmultimap as the data layer. Two private parties enter a binding loan agreement on chain, with cryptographic enforcement of all phases.

---

## Table of contents

**Part I — Cryptographic protocol**
1. [Goals and non-goals](#1-goals-and-non-goals)
2. [Roles and identity model](#2-roles-and-identity-model)
3. [The vault](#3-the-vault)
4. [Pre-signed transactions](#4-pre-signed-transactions)
5. [Origination ceremony](#5-origination-ceremony)
6. [Settlement, default, rescue](#6-settlement-default-rescue)
7. [Reorg handling](#7-reorg-handling)
8. [Edge case coverage matrix](#8-edge-case-coverage-matrix)

**Part II — Data layer**
9. [Marketplace via contentmultimap](#9-marketplace-via-contentmultimap)
10. [Reputation and credit history](#10-reputation-and-credit-history)
11. [Encrypted coordination](#11-encrypted-coordination)
12. [VDXF schema registry](#12-vdxf-schema-registry)

**Part III — Implementation guidance**
13. [Wallet UX requirements](#13-wallet-ux-requirements)
14. [Profile choice in practice](#14-profile-choice-in-practice)
15. [Sybil defenses](#15-sybil-defenses)

**Part IV — Reference**
16. [Validated primitives](#16-validated-primitives)
17. [Limitations and known issues](#17-limitations-and-known-issues)
18. [Future work / roadmap](#18-future-work--roadmap)

**Appendices**
- [A. Glossary](#appendix-a-glossary)
- [B. Shielded variants](#appendix-b-shielded-variants)
- [C. The primitive's other applications](#appendix-c-the-primitives-other-applications)

---

# Part I — Cryptographic protocol

## 1. Goals and non-goals

### Goals

- Two-party atomic origination with optional async UX
- Atomic settlement with cryptographic guarantee
- Lender pre-commits at every phase (cannot stonewall mid-flow)
- Borrower repays unilaterally (no live cooperation needed at settlement)
- Time-based default with no live cooperation required
- Reorg-safe by construction (pre-signed txs don't depend on chain state)
- Survives single-party key loss (rescue path)
- Marketplace, reputation, and ceremony all on chain (no off-chain server required)
- Works with existing Verus primitives — no new RPCs or consensus rules

### Non-goals

- On-chain dispute resolution for subjective claims (use real-world courts; the chain is admissible evidence)
- Margin calls / continuous LTV monitoring (this is non-margin lending, by design)
- Cross-chain BTC collateral (separate workstream — Verus Swap atomic swaps)
- Multi-party / syndicated loans
- Loan secondary market (transferable loan positions)
- Variable-rate / floating-interest loans (requires re-cooperation to update terms)
- Joint mid-loan cancellation (parties wait for default or re-sign cooperatively)

---

## 2. Roles and identity model

| Role | Description |
|---|---|
| **Borrower** | Party providing collateral, receiving principal, obligated to repay principal + interest by maturity. |
| **Lender** | Party providing principal, holding rights to claim collateral on default. |

### Identity is in two layers — vault and parties

The protocol has two independent identity choices:

1. **The vault** — the address holding collateral. Can be a 2-of-2 p2sh script hash (Profile L, no VerusID) or a 2-of-2 VerusID i-address (Profile V, with naming + multimap).
2. **The parties** — the borrower and lender as actors. Can be plain R-addresses (anonymous) or VerusIDs (with reputation/credit-identity layer).

These are independent. The recommended configuration for an active lending market is **p2sh vault + party VerusIDs**: cheapest possible vault (zero registration cost), full reputation/multimap features for the parties (see Part II).

---

## 3. The vault

The vault is a 2-of-2 multisig address that holds the collateral until one of the pre-signed transactions releases it.

### 3.1 Profile L — p2sh (lite)

A plain Bitcoin-compatible 2-of-2 p2sh script hash:

```
redeem_script = OP_2 <borrower_pubkey> <lender_pubkey> OP_2 OP_CHECKMULTISIG
vault_address = base58(0x55 || ripemd160(sha256(redeem_script)) || checksum)
```

The vault address has a `b` prefix on Verus mainnet (e.g. `bYCcAqB7KfdkfsN8YUipb2fuFhKvxmsnne`). No on-chain registration. No fee. No name. Both parties exchange pubkeys, derive the address deterministically, proceed.

**Constraints:** Profile L vaults can hold **VRSC only**. Reserve-currency cryptocondition outputs (DAI, tBTC, basket tokens) to a plain p2sh script hash are non-standard and rejected by the chain. For non-VRSC collateral, use Profile V.

Validated mainnet: §18-§30, see TESTING.md.

### 3.2 Profile V — VerusID (with multimap)

A Verus sub-identity with these properties:

```
vault VerusID
  primary:             [borrower_R, lender_R]   M = 2 (2-of-2 multisig)
  revocationauthority: null (or burn address)
  recoveryauthority:   null (or burn address)
  contentmultimap:     loan terms object        (optional)
  timelock:            0
```

Vault address is the VerusID's i-address (e.g. `i7b7Tq8JYXX9iqS7FBevC6LaG3ioh8z3RM`). Cost: sub-ID registration fee (~0.1 VRSC if a parent identity already exists) or 100 VRSC for a fresh top-level identity.

**Profile V buys:**
- Human-readable name (`loan-XXXX.parent@`)
- On-chain encrypted multimap entries on the loan itself
- Support for non-VRSC collateral (validated §32)
- Reputation hooks tied to the loan id

**Authority semantics (Profile V only):**
- **Primary (2-of-2)**: both parties must cosign any normal `updateidentity` action
- **Revocation**: null — no party can unilaterally freeze the loan
- **Recovery**: null — no discretionary recovery path

For Profile L the equivalent semantics are inherent to p2sh: no concept of revoke/recover; funds release only on 2-of-2 sig.

Validated mainnet: §16, §17, §32 (with non-VRSC collateral).

### 3.3 Choosing a vault profile

| Use case | Recommended profile |
|---|---|
| Ad-hoc loan, VRSC collateral, both parties already know each other | L |
| Any non-VRSC collateral | V |
| Lending desk with shared parent ID (`loan-XXX.desk@`) | V |
| Community lending facility issuing branded loans | V |
| Minimal overhead, parties don't want to register anything | L |

The protocol's cryptographic guarantees are identical between profiles. The choice is operational — naming, fees, currency support, ID infrastructure — not security.

### 3.4 Currency support

**Principal, interest, repayment, and (for Profile V) collateral** can be denominated in any Verus-supported currency: VRSC, fractional-reserve currencies, bridged tokens (vETH, DAI.vETH, tBTC.vETH, vUSDC), or PBaaS chain currencies.

Validated cross-currency configurations (§18-§32):
- VRSC collateral + VRSC principal (§16, §17)
- VRSC collateral + DAI principal/interest (§18, §20)
- VRSC collateral + DAI principal, broadcaster-pays-fee variants (§20, §21)
- DAI collateral + VRSC strike on Profile V (§32)

**Tooling note** (per §32): when signing cryptocondition reserve-transfer inputs, `signrawtransaction` requires the wallet key-lookup path:

```
# Correct for cryptocondition reserve inputs
verus signrawtransaction <hex> null null "SINGLE|ANYONECANPAY"

# Fails with "Opcode missing or not understood" on reserve cryptoconditions
verus signrawtransaction <hex> [] ["<priv>"] "SINGLE|ANYONECANPAY"
```

Wallets implementing the protocol must use the `null null` form when the input is a non-VRSC cryptocondition. For VRSC-only inputs (p2sh or i-address with VRSC value), either path works.

---

## 4. Pre-signed transactions

The protocol has four pre-signed transaction templates. **All four use the same signature discipline:** Input 0 is signed with `SIGHASH_SINGLE | SIGHASH_ANYONECANPAY`, locking Output 0 to the agreed payment, leaving the rest of the transaction extensible by the broadcaster.

| Tx | Phase | Held by | Triggered when | Output 0 |
|---|---|---|---|---|
| Tx-O | Origination | Lender | Borrower decides "now" | Principal → borrower |
| Tx-Repay | Settlement | Borrower | Borrower decides "now", before maturity | Principal+interest → lender |
| Tx-B | Default | Lender | After maturity + grace | Collateral → lender |
| Tx-C | Rescue | Borrower | After far-future lockout | Collateral → borrower |

This is fully symmetric: a wallet implementing one phase implements all four with minor variations.

### 4.1 Tx-O — atomic-swap origination (recommended)

Pre-signed by the lender at offer time. Borrower triggers broadcast unilaterally when ready.

```
Lender pre-signs:
  Input 0:  Lender's principal UTXO    (signed SIGHASH_SINGLE|ANYONECANPAY)
  Output 0: principal_amount → borrower (sig-locked, paired)

Borrower extends and signs at takeup:
  Input 1:  Borrower's collateral UTXO  (signed SIGHASH_ALL)
  Output 1: collateral_amount → vault   (loan begins here)
  Output 2: borrower's change           (if any)
  Output 3: lender's change             (if any)
```

**Properties:**
- Lender pre-commits irreversibly. Once Borrower has the hex, Lender cannot retract — except by spending Input 0 elsewhere (which invalidates the offer cleanly).
- Borrower owns the broadcast moment. Suitable for offer boards, async UX, marketplace listings.
- A reorg of an unconfirmed Tx-O simply voids the loan: both parties' funds return to source addresses; rebroadcast or abandon.

Validated mainnet: §25.

### 4.2 Tx-A — cooperative raw tx origination (alternative)

For scenarios where both parties are online together:

```
Inputs:  borrower's collateral UTXO + lender's principal UTXO (+ change/fee)
Outputs: collateral → vault, principal → borrower, change(s)
```

Both parties sign their respective inputs via standard `signrawtransaction`. No SIGHASH_SINGLE involved — purely additive cosigning.

Validated mainnet: §16, §18.

### 4.3 Tx-Repay — pre-signed repayment (canonical)

```
Template (signed at origination):
  Input 0:       vault collateral UTXO     (signed SIGHASH_SINGLE|ANYONECANPAY by both, via redeem script)
  Output 0:      principal+interest → lender (sig-locked, paired)
  expiryheight:  maturity_block            (cannot broadcast after deadline)

Borrower extends at repayment:
  Input 1+:  funding UTXOs (principal+interest currency, plus VRSC for fee)  (signed SIGHASH_ALL)
  Output 1+: collateral return + change    (borrower structures freely)
```

Borrower repays unilaterally. Lender doesn't need to be online or sign anything at repayment. Validated mainnet: §16, §18, §20.

**Two fee-model variants:**

- **R-α (collateral-pays-fee):** Output 1 = `collateral - fee` to borrower. Simple but eats slightly into recovered amount.
- **R-β (broadcaster-pays-fee, recommended):** Borrower attaches a separate VRSC input for fee, gets full collateral back. Required if collateral is non-VRSC. Validated §20.

### 4.4 Tx-B — pre-signed default-claim

```
Template (signed at origination):
  Input 0:       vault collateral UTXO     (signed SIGHASH_SINGLE|ANYONECANPAY by both)
  Output 0:      collateral → lender       (sig-locked)
  nLockTime:     maturity_block + grace_period

Lender extends at default-claim:
  Input 1:       VRSC fee UTXO             (signed SIGHASH_ALL)
  Output 1:      lender's change           (after fee deducted)
```

Cannot be broadcast before nLockTime. After broadcast, the vault UTXO is consumed; Tx-Repay and Tx-C are invalidated. Validated mainnet: §17, §19, §21.

### 4.5 Tx-C — pre-signed rescue (optional)

Borrower's last-resort path. Activates if neither Tx-Repay nor Tx-B is broadcast — i.e., both parties have effectively abandoned the loan.

```
Template (signed at origination):
  Input 0:       vault collateral UTXO     (signed SIGHASH_SINGLE|ANYONECANPAY by both)
  Output 0:      collateral → borrower     (sig-locked)
  nLockTime:     maturity_block + extended_lockout (e.g., +1 year)

Borrower extends at rescue:
  Input 1:       VRSC fee UTXO             (signed SIGHASH_ALL)
  Output 1:      borrower's change
```

Rare. Some implementations may omit Tx-C. Validated mainnet: §23.

### 4.6 Signing operations summary

| Phase | Lender signs | Borrower signs |
|---|---|---|
| Tx-O pre-sign | 1× SIGHASH_SINGLE\|ANYONECANPAY (Input 0, his contribution) | — |
| Tx-Repay pre-sign | 1× SIGHASH_SINGLE\|ANYONECANPAY (Input 0, multisig) | 1× SIGHASH_SINGLE\|ANYONECANPAY (Input 0, multisig) |
| Tx-B pre-sign | 1× SIGHASH_SINGLE\|ANYONECANPAY | 1× SIGHASH_SINGLE\|ANYONECANPAY |
| Tx-C pre-sign (optional) | 1× SIGHASH_SINGLE\|ANYONECANPAY | 1× SIGHASH_SINGLE\|ANYONECANPAY |
| Tx-O broadcast (extension) | — | 1× SIGHASH_ALL (collateral input) |
| Tx-Repay broadcast | — | 1× SIGHASH_ALL (strike + fee inputs) |
| Tx-B broadcast | 1× SIGHASH_ALL (fee input) | — |
| Tx-C broadcast | — | 1× SIGHASH_ALL (fee input) |

About 4-7 signing operations per side per loan, all using existing wallet primitives.

---

## 5. Origination ceremony

The signing order is critical. **All settlement transactions (Tx-Repay, Tx-B, Tx-C) must be fully signed before Tx-O is broadcast.**

```
Step 1: Both parties exchange compressed pubkeys (Profile L)
        OR register the vault VerusID with 2-of-2 + null revoke/recover (Profile V)

Step 2: Construct unsigned Tx-O
        - Determine all inputs and outputs
        - Compute predicted txid (deterministic ECDSA via RFC 6979 makes this stable)

Step 3: Construct and pre-sign Tx-Repay
        - Input 0 references predicted_txid:vault_vout
        - Output 0 = principal + interest to lender
        - expiryheight = maturity_block
        - Both parties sign Input 0 with SIGHASH_SINGLE|ANYONECANPAY
        - Borrower stores resulting hex (encrypted in own multimap, Profile V)

Step 4: Construct and pre-sign Tx-B
        - Input 0 references same predicted_txid:vault_vout
        - Output 0 = collateral to lender
        - nLockTime = maturity_block + grace
        - Both sign with SIGHASH_SINGLE|ANYONECANPAY
        - Lender stores resulting hex

Step 5: (Optional) Pre-sign Tx-C
        - Input 0 references same vault UTXO
        - Output 0 = collateral to borrower
        - nLockTime = maturity_block + extended_lockout
        - Both sign with SIGHASH_SINGLE|ANYONECANPAY
        - Borrower stores resulting hex

Step 6: Verify, then broadcast Tx-O
        - Both parties verify all settlement templates are stored on the appropriate side
        - Lender signs Input 0 with SIGHASH_SINGLE|ANYONECANPAY (his offer hex)
        - Borrower extends with collateral input + outputs, signs with SIGHASH_ALL
        - Borrower broadcasts when ready
```

If the ceremony aborts before step 6, no on-chain state is created. No funds are at risk.

### Predicting the vault-funding txid

Pre-signing settlement templates requires knowing Tx-O's txid before broadcast. With deterministic ECDSA (RFC 6979) the txid is stable from the unsigned form. Wallets compute the predicted txid; if the actual txid differs (rare; signature variation), abort and restart.

---

## 6. Settlement, default, rescue

### 6.1 Repayment (canonical)

The borrower repays unilaterally at any time before Tx-Repay's `expiryheight`. **No live cooperation from the lender is needed.**

```
Day N (any day during loan term, before maturity):
  Borrower's wallet retrieves Tx-Repay template
  Wallet selects UTXO(s) totaling at least (principal + interest + fee_budget)
  Wallet appends those UTXOs as new inputs
  Wallet appends Output 1+ for collateral return + change
  Wallet signs new inputs with SIGHASH_ALL
  Wallet broadcasts the now-complete tx
```

On confirmation:
- Lender's address receives principal + interest (Output 0, signed-locked at origination)
- Borrower's address receives collateral + change
- Vault UTXO is consumed; Tx-B and Tx-C are now invalidated
- Lender did not sign anything at repayment

### 6.2 Why the lender cannot refuse

The lender's signature on Input 0 was made at origination. The signature is hex bytes in the borrower's wallet. There is no mechanism by which the lender can retract or revoke that signature. Once the borrower broadcasts, settlement is automatic.

The lender can be online or offline, alive or dead, willing or unwilling — irrelevant. The signature is final.

### 6.3 Why no third party can front-run

The Tx-Repay template is private — held only by the borrower, never on the public chain until broadcast. There is no offer in mempool that strangers could see and race against.

When the borrower broadcasts, they submit a complete, fully-signed transaction. It either confirms in one block or doesn't. There is no intermediate state for interception.

The signed-paired output (Output 0) cannot be redirected or reduced — empirically validated under tampering attempts in §24 (D1, D2): both rejected with `mandatory-script-verify-flag-failed`.

### 6.4 Default (lender claims)

```
Day 0 to maturity:        borrower never broadcasts Tx-Repay
Day maturity + grace:     Tx-B's nLockTime is reached
Lender extends Tx-B:      attaches own VRSC fee input + change output
Lender broadcasts:        collateral lands at lender's address
                          Tx-Repay and Tx-C now invalidated
```

Validated mainnet: §17, §19, §21.

### 6.5 Borrower disappears / loses keys before maturity

Same as 6.4 — lender broadcasts Tx-B at maturity + grace. Borrower's heirs lose collateral but kept the principal received at origination.

### 6.6 Lender disappears / loses keys before borrower repays

Borrower broadcasts Tx-Repay normally. Lender's pre-signature is in the template — broadcast doesn't require the lender to be alive. Settlement happens unilaterally. The repayment lands at the lender's address; the lender's heirs inherit it via standard wallet succession.

### 6.7 Lender's keys compromised post-origination

If an attacker gains the lender's private key after origination but before maturity:

- Attacker can broadcast Tx-B at maturity + grace, claim collateral
- Borrower's defense: broadcast Tx-Repay before then, atomically settling and invalidating Tx-B
- This is a race against the maturity block, not contention over the same UTXO

The attacker cannot accelerate Tx-B's nLockTime; they must wait for maturity + grace. In practice, the borrower has the entire loan term to detect compromise and repay early.

### 6.8 Both parties die / lose keys

Funds locked on chain. Heirs may eventually find the off-chain pre-signed transactions and broadcast them. If Tx-C exists, after its far-future locktime either party (or their heirs) can broadcast it to recover collateral to the borrower's address. If neither hex survives and Tx-C wasn't pre-signed, collateral is permanently inaccessible.

### 6.9 Rescue (Tx-C)

Borrower's last-resort path. Activates only if neither Tx-Repay nor Tx-B is broadcast — i.e., both parties have effectively abandoned. After Tx-C's far-future nLockTime, borrower extends with fee input and broadcasts. Collateral returns to borrower.

Validated mainnet: §23.

---

## 7. Reorg handling

The protocol is **inherently reorg-resilient** because pre-signed transactions don't depend on chain state for their validity (only on UTXO availability and locktime). A reorg simply means "rebroadcast and try again." There is no scenario where a reorg can cause a party to lose value.

| Reorg scenario | Recovery | Risk |
|---|---|---|
| Tx-O / Tx-A reorged before confirmation | Wallet rebroadcasts; OR either party spends their input elsewhere to cancel (loan never happens) | None — both parties whole |
| Tx-Repay reorged after broadcast | Borrower's wallet rebroadcasts; tx still valid | None — `expiryheight ≤ maturity` blocks broadcasts after deadline |
| Tx-B reorged after broadcast | Lender's wallet rebroadcasts; tx still valid (locktime satisfied) | None — borrower can't broadcast Tx-Repay across maturity if expiryheight set correctly |
| Tx-C reorged after broadcast | Borrower's wallet rebroadcasts; far-future locktime makes contention implausible | None |

**Lender's default-claim procedure (recommended):**

```
1. At maturity + grace, broadcast Tx-B
2. Wait for ≥ 6 confirmations (~6 minutes on Verus) before treating the claim as final
3. If a reorg knocks Tx-B out, wallet detects and rebroadcasts immediately
4. After 10 confirmations, finality is essentially guaranteed (Verus has notarization)
```

**Why no double-claim attack via reorg is possible:**

If Tx-B confirms in block N and gets reorged out, the only competing settlement would be Tx-Repay. But Tx-Repay's `expiryheight = maturity_block` makes it invalid at any height ≥ maturity. So the borrower can't "race" Tx-Repay during the reorg window — the network rejects it as expired.

The only adversarial reorg the protocol can't defend against is a deep (>10-block) reorg that simultaneously affects both Tx-B and the chain's notion of "what's the maturity block." On Verus, with ~1-min blocks and notarization, this is implausible. For high-stakes loans, lender simply waits longer.

---

## 8. Edge case coverage matrix

| Scenario | Outcome | Validated |
|---|---|---|
| Cooperation, normal repayment | Borrower broadcasts Tx-Repay; atomic settlement | §16, §18, §20 |
| Borrower defaults | Tx-B at maturity + grace | §17, §19, §21 |
| Borrower dies/loses keys before maturity | Same as default | implicit |
| **Lender dies/loses keys before borrower repays** | **Borrower broadcasts Tx-Repay normally — pre-signature is sufficient** | structural |
| Both die | Funds locked; if Tx-C pre-signed, recoverable to borrower at extended_lockout | structural |
| Lender attempts to refuse repayment | Cannot — pre-signed Tx-Repay does not require lender's runtime cooperation | structural |
| Lender attempts to claim via Tx-B early | Cannot — nLockTime prevents pre-maturity broadcast | §17, §19 |
| Lender attempts to claim via Tx-B after Tx-Repay broadcast | Cannot — collateral UTXO already consumed | §22 |
| Borrower attempts to repay after Tx-B broadcast | Cannot — collateral UTXO already consumed | §29 |
| Lender's key compromised post-origination | Borrower repays early before attacker's Tx-B | §17 |
| **Stranger or borrower tries to redirect Output 0** | **Cannot — paired output sig-locked** | §24 (D1) |
| **Borrower tries to underpay Output 0** | **Cannot — signature commits to exact amount** | §24 (D2) |
| Stranger tries to intercept Tx-Repay broadcast | Cannot — tx is complete and atomic; no offer in mempool | structural |
| Tx-Repay leaked publicly | Not exploitable — only borrower has matching funding-input keys | structural |
| Tx-B leaked publicly | Output goes to lender only; strangers gain nothing | structural |
| Tx-Repay lost by borrower | Cooperative re-sign; or recover from encrypted multimap backup | §13.1 |
| Reorg of any settlement tx | Wallet rebroadcasts; no value lost | §7 |

---

# Part II — Data layer

## 9. Marketplace via contentmultimap

The contentmultimap of a VerusID functions as a chain-native marketplace data layer. **No separate server, API, or centralized index is required.** Anyone with a Verus node can discover loan offers via the standard `getidentity` RPC.

### Validated end-to-end: §33

A loan offer was published as a multimap entry in a VerusID's contentmultimap (under an early-draft VDXF key `vrsc::loan.offer.v1` = `iDDdeciNHuSiggfZrquEBJAX5TUxkm2Sgy`) and read back identically from two independent Verus nodes (local + .44 in different physical locations). Tx: `694ed5cfc13d4fb0234d7fa2759a336b163c59b42ee0b71581ff816062bb00a8`. The canonical key set has since been finalised in [SCHEMA.md](./SCHEMA.md) under `vrsc::contract.*` — the early-draft key is no longer recognised.

### Standard entry types (Part II §12 defines canonical VDXF keys)

```
contract.loan.offer    — lender publishes terms they'll lend at
contract.loan.request  — borrower publishes terms they need
contract.loan.history  — co-signed loan outcomes (§10)
contract.loan.status   — active loan state (active, settled, defaulted, rescued)
```

Each is a hex-encoded JSON payload under a canonical VDXF key. Wallets write to their owner's multimap when posting; readers parse any VerusID's multimap for these keys.

### Lender offer entry

```json
{
  "version": 1,
  "type": "lend",
  "principal": {"currency": "<currency-id>", "amount": <amount>},
  "collateral": {"currency": "<currency-id>", "amount": <min_amount>},
  "rate": <fraction>,
  "term_days": <number>,
  "lender_pubkey": "<compressed-hex>",
  "lender_address": "<R-address-or-i-address>",
  "valid_until_block": <number>,
  "active": true | false
}
```

### Borrower request entry

```json
{
  "version": 1,
  "type": "borrow",
  "principal_wanted": {"currency": "<currency-id>", "amount_min": ..., "amount_max": ...},
  "collateral_offered": {"currency": "<currency-id>", "amount_max": ...},
  "term_days_max": <number>,
  "interest_rate_max": <fraction>,
  "borrower_pubkey": "<compressed-hex>",
  "active": true | false
}
```

### What an explorer or wallet can show

A page like `/lending/offers` queries known VerusIDs (or a filtered subset) for `vrsc::contract.loan.offer` entries and renders:

| Lender ID | Principal | Collateral | LTV | Rate | Term | Track Record |
|---|---|---|---|---|---|---|
| `bob.lender@` | 5 DAI | 10 VRSC | 50% | 10% | 30d | 47 settled / 2 defaulted |
| `desk.lendingco@` | 1000 DAI | 2000 VRSC | 50% | 8% | 90d | 312 settled / 5 defaulted |

Track record is computed from each lender's `vrsc::contract.loan.history` entries (§10).

### Discovery scaling

Three plausible patterns:

- **A — Walk all VerusIDs.** Doesn't scale; not recommended.
- **B — Convention: register under a known parent.** Lenders register `<random>.lend@` sub-IDs per offer. Browsers query just that parent's children. Bounded set.
- **C — Hybrid: explorers index the chain.** Convention defines schema; explorers maintain caches. Multiple competing explorers possible.

The spec defines the schema but does not mandate a discovery mechanism. **Pattern C is the practical default** — any explorer can index, none is canonical.

---

## 10. Reputation and credit history

For an active lending market — where strangers want to evaluate counterparties and price risk — VerusIDs enable an on-chain credit-identity layer.

### The mechanism

At outcome (settle/default/rescue), each party independently writes a `loan.history.v1` entry to their own VerusID's multimap. The entry references:
- The vault address (canonical loan ID)
- Origination tx (Tx-O or Tx-A)
- Outcome tx (Tx-Repay, Tx-B, or Tx-C)
- Counterparty's VerusID (cross-reference)
- Block heights for ordering
- (Optional) `prev_entry_hash` for tamper-evident hash-chaining

```json
{
  "version":         1,
  "vault_address":   "bYCcAqB7..." or "i6ebreh...",
  "role":            "borrower" | "lender",
  "counterparty_id": "<other-party-VerusID>",
  "principal":       {"currency": "...", "amount": ...},
  "collateral":      {"currency": "...", "amount": ...},
  "rate":            <fraction>,
  "term_days":       <number>,
  "originated_tx":   "<txid>",
  "originated_block": <number>,
  "outcome":         "settled" | "defaulted" | "rescued",
  "outcome_tx":      "<txid>",
  "outcome_block":   <number>,
  "prev_entry_hash": "<sha256 of previous entry on this ID>"
}
```

### Asymmetric writes (no co-signing required)

Each party writes their own entry on their own multimap. **No co-signing needed across IDs** — the truth is the on-chain tx, and both entries reference the same vault address and tx pair. If one party refuses to write their entry as a grief, the chain truth is still verifiable from the actual txs.

### Verifiability properties

When a future counterparty Charlie evaluates Bob's history:

1. **Each entry's txids exist on chain** — Charlie verifies via `getrawtransaction`. Fakes detected immediately.
2. **The vault output really went to / came from Bob** — Charlie checks the txs' outputs.
3. **The counterparty's matching entry exists** — Charlie reads `counterparty_id`'s multimap and finds an entry for the same vault. Both sides agree.
4. **No counterparty entry exists** — suspicious; chain truth still proves the loan but the counterparty refused to attest. Charlie weights accordingly.
5. **Hash-chain integrity** — `prev_entry_hash` makes inserting fake entries between real ones detectable.

### The credit graph

Once enough loans accumulate, the chain hosts a public credit graph: who has lent to whom, when, in what amounts, with what outcomes. Anyone can compute scoring functions over this graph. **No canonical scoring authority.** Multiple wallets/explorers can implement different scoring algorithms; users can choose which to trust.

This shifts the practical envelope of the protocol from "private agreements between known parties" to "permissionless capital market with cryptographic credit identity."

---

## 11. Encrypted coordination

VerusIDs support encrypted contentmultimap entries via identity z-keys. Data encrypted to a specific VerusID can only be decrypted by the holder of that ID.

### Hex backup (durable, seed-recoverable)

The biggest operational risk in any pre-signed-tx protocol is **losing the hex**. Each party encrypts pre-signed templates to their own viewing key and writes them to their own multimap:

```json
{
  "loan.tx-repay.encrypted.v1": {
    "vault_address": "...",
    "encrypted":     "<base64 ciphertext, encrypted to alice@'s viewing key>"
  }
}
```

Recovery: import seed → derive viewing key → decrypt → recover hex. No file backups needed. Works as long as the chain exists.

### Async ceremony coordination

The origination ceremony is a back-and-forth signing dance. With encrypted multimap entries, the chain becomes the message bus:

```
loan.accept.v1                  (borrower → lender, encrypted)
loan.tx-o.draft.v1              (encrypted)
loan.tx-o.signed.v1             (encrypted)
loan.tx-repay.template.v1       (encrypted, pre-signed by both)
loan.tx-b.template.v1           (encrypted, pre-signed by both)
loan.tx-c.template.v1           (encrypted, pre-signed by both)
```

Each entry is one `updateidentity` write. The recipient's wallet polls and processes. Neither party needs to be online simultaneously.

### Encrypted loan terms

Terms can be encrypted, leaving public visibility only to "VerusID alice@ has an active loan" (via `loan.status.v1`). Useful for OTC-style lending where terms are commercially sensitive.

### Trust dependencies

- Identity z-keys are derived from the holder's seed. Lost seed = lost ability to decrypt past entries.
- Encryption uses Verus's existing primitives. No new cryptography introduced.

---

## 12. VDXF schema registry

VDXF (Verus Data Exchange Format) keys are derived deterministically from string identifiers via `getvdxfid`. Anyone computing `getvdxfid "vrsc::contract.loan.offer"` gets the same canonical key.

The canonical key set is namespaced under `vrsc::contract.<usecase>.<entity>` matching Verus's own convention (`vrsc::system.*`, `vrsc::profile.*`, `vrsc::contentmultimap.*`). Versioning lives inside the JSON payload (`{ "version": 1, … }`), not in the key string. See [SCHEMA.md](./SCHEMA.md) for the full registry including options / escrow / swap entries.

### Canonical keys (loan use case)

| Key | VDXF id | Purpose | Visibility |
|---|---|---|---|
| `vrsc::contract.loan.offer`     | `iA1vgVBV5B29h5pxQ67gxqCoEaLDZ8WbmY` | Lender's open offer | public |
| `vrsc::contract.loan.request`   | `iPmnErqWbf5NhhWZEoccuX8yU8CgFt2d28` | Borrower's request | public |
| `vrsc::contract.loan.history`   | `i92jad9CSjBNPCHgnHqQP4hK1facXBFDWb` | Outcome attestation (reputation source) | public |
| `vrsc::contract.loan.status`    | `iP5b6uX8SM7ZSiiMbVWwGj9wG76KuJWZys` | Active loan state | public |
| `vrsc::contract.loan.accept`    | `iLr7w7k8Ty9tVHccBqzXfAud1wXY1QYsBy` | Borrower's acceptance handshake | encrypted |
| `vrsc::contract.loan.template`  | `i7HCaxjju3QRYmbC23g5QD2smMk4PqaXFq` | Pre-signed Tx-A draft + Tx-Repay + Tx-B + Tx-C templates, bundled | encrypted (to self) |

VDXF ids above are deterministic — re-derive at any time via `verus getvdxfid "<key>"`.

### Versioning

VDXF keys are immutable. Schema upgrades happen via the `version` field inside the JSON payload, NOT by introducing a new key (`loan.offer.v2`). Readers handle multiple `version` values gracefully. This matches Verus's own convention — keys like `vrsc::system.currency.notarization` have stable ids while their payload schemas evolve.

### Encoding

Each multimap entry value is a hex-encoded payload (`hex(utf8(JSON.stringify(payload)))`). For public entries: hex-encoded JSON. For encrypted entries: hex-encoded ciphertext (encryption format per Verus's existing identity z-key primitives).

---

# Part III — Implementation guidance

## 13. Wallet UX requirements

A reference wallet implementation should provide:

1. **Marketplace browsing** — query VerusIDs for `vrsc::contract.loan.offer` and `vrsc::contract.loan.request` entries; render as a filterable list.
2. **Reputation aggregation** — for any candidate counterparty, fetch their `vrsc::contract.loan.history` entries and compute a summary (count, default rate, tenure, counterparty diversity).
3. **Reputation gating** — let the user set thresholds (max default rate, min tenure, min loans). Hide or warn on offers below threshold.
4. **Origination ceremony coordinator** — handle the multi-step signing dance via encrypted multimap writes; expose simple "Accept offer" UX.
5. **Encrypted hex storage** — write pre-signed templates to user's own multimap as durable backup.
6. **Settlement helper** — at user's request, retrieve template, attach funding inputs, sign with `SIGHASH_ALL`, broadcast.
7. **Default-claim notification** — prompt lender well before grace period ends.
8. **Tx-Repay expiry warning** — prompt borrower before `expiryheight` passes.
9. **Reorg handling** — detect if a confirmed settlement tx gets reorged out and automatically rebroadcast.
10. **Outcome attestation** — write `loan.history.v1` entry on outcome confirmation.

### Critical implementation note: signing path

Use `signrawtransaction <hex> null null <flags>` for cryptocondition reserve-currency inputs. The explicit-key path (`[] ["<priv>"]`) fails with `Opcode missing or not understood`. See §3.4 and TESTING §32.

### Three of four phases are pure-CLI today

`makeoffer`/`takeoffer` natively handle three of the four protocol phases (Tx-O origination, Tx-B default, Tx-C rescue). All work for any currency combo. Validated TESTING §34 (cross-currency atomic swap via marketplace RPCs).

```
# Tx-O — lender posts offer, borrower takes
ssh lender 'verus makeoffer <addr> "{offer:..., for:...}"'   # broadcasts on chain
verus takeoffer <addr> "{txid: <offer-txid>, deliver:..., accept:...}"   # atomic swap

# Tx-B — lender claims default at maturity
ssh lender 'verus makeoffer ...' followed by ssh lender 'verus takeoffer ...'

# Tx-C — borrower rescues at far-future locktime
verus makeoffer ... ; verus takeoffer ...
```

### Tx-Repay needs either an extension helper or a small Verus RPC enhancement

The settlement phase requires a 2-of-2 vault input where lender pre-commits at origination and borrower takes alone at any time before maturity. `makeoffer`/`takeoffer` doesn't support multi-sig pre-commitments because it operates on wallet keys only.

Two paths today:
- **Client-side extension helper** (~80 lines, `extend_tx.py` in this repo). Validated approach. Each wallet ships its own equivalent.
- **Manual byte-splicing via decoderawtransaction + createrawtransaction + hex copy** — pure CLI but tedious.

A small Verus core RPC enhancement (`extendrawtransaction`, `cosignoffer`, or `makeoffer privkeys` param) would unlock pure-CLI Tx-Repay too. See [DEV_ASK.md](./DEV_ASK.md) for details.

### Critical implementation note: signing path

Use `signrawtransaction <hex> null null <flags>` for cryptocondition reserve-currency inputs. The explicit-key path (`[] ["<priv>"]`) fails with `Opcode missing or not understood`. See §3.4 and TESTING §32.

---

## 14. Profile choice in practice

| Vault | Borrower's identity | Lender's identity | What you get |
|---|---|---|---|
| p2sh (L) | R-address | R-address | Cheapest. Fully anonymous. No reputation. |
| p2sh (L) | VerusID | VerusID | **Recommended for active markets** — cheap vault + reputation/multimap features for both parties |
| VerusID (V) | VerusID | VerusID | Maximum on-chain context (loan also has its own multimap entries) |
| VerusID (V) | R-address | R-address | Possible but unusual — VerusID adds little if neither party has one |

The recommended default is **p2sh vault + party VerusIDs**: zero per-loan registration cost, full reputation/multimap features. Profile V vaults are reserved for cases where the loan itself benefits from being a named on-chain entity (lending desks, branded products, syndicated loans).

---

## 15. Sybil defenses

Reputation is gameable by registering many VerusIDs and faking history. The following heuristics raise the cost of attack and should be implemented in scoring algorithms:

- **Tenure weighting**: a 6-month-old ID weighs more than a 6-day-old one.
- **Counterparty diversity**: 100 loans to 100 different counterparties weighs much more than 100 loans to 3 counterparties (anti-cycling).
- **Stake weighting**: a single $10k loan with clean settlement weighs more than 100 $1 loans.
- **Graph cluster analysis**: the credit graph is public; cycles and clusters of mutual transactions are detectable.
- **Tenure mismatch**: 100 IDs registered in the same week is suspicious.
- **Collateral source tracing**: if a counterparty's collateral originated from the candidate's main address, that's a fingerprint.

These are scoring heuristics, not protocol-level rules. Different wallets can implement different aggressiveness; users choose which scoring they trust.

---

# Part IV — Reference

## 16. Validated primitives

Each item below was directly tested on Verus mainnet. See [TESTING.md](./TESTING.md) for txid references and full procedures.

| # | Primitive | Validation |
|---|---|---|
| Vault | 2-of-2 multisig vault prevents unilateral redirect (Profile V) | ✅ §16 |
| Vault | 2-of-2 p2sh vault prevents unilateral redirect (Profile L) | ✅ §18 |
| Origination | Cooperative raw multi-party tx (Tx-A) | ✅ §16, §18 |
| Origination | **Atomic-swap origination (Tx-O)** | ✅ §25 |
| Settlement | Pre-signed Tx-Repay with `SIGHASH_SINGLE\|ANYONECANPAY` | ✅ §16, §18, §20 |
| Settlement | Cross-currency (VRSC collateral + DAI principal/interest) | ✅ §18, §20 |
| Settlement | Broadcaster-pays-fee variant (collateral returned in full) | ✅ §20 (Tx-Repay), §21 (Tx-B) |
| Default | nLockTime enforcement on Profile V (i-address) input | ✅ §17 |
| Default | nLockTime enforcement on Profile L (p2sh) input | ✅ §19 |
| Default | Pre-signed Tx-B with `SIGHASH_SINGLE\|ANYONECANPAY` + nLockTime | ✅ §21 |
| Rescue | **Tx-C rescue path** | ✅ §23 |
| Mutex | Tx-Repay broadcast invalidates pre-signed Tx-B (UTXO consumption) | ✅ §22 |
| Mutex | Tx-B broadcast invalidates pre-signed Tx-Repay (UTXO consumption) | ✅ §29 |
| Adversarial | Pre-locktime broadcast rejected as `64: non-final` | ✅ §17, §19 |
| Adversarial | Output 0 recipient tampering rejected | ✅ §24 (D1) |
| Adversarial | Output 0 amount tampering rejected | ✅ §24 (D2) |
| Recipient | SIGHASH-pre-signed Output 0 to a VerusID i-address | ✅ §28 |
| Generality | Generic p2p atomic currency swap (no loan structure) | ✅ §30 |
| Currency | **Non-VRSC collateral with SIGHASH_SINGLE\|ANYONECANPAY** | ✅ §32 |
| Tooling | Wallet key-lookup path required for cryptocondition inputs | ✅ §32 |
| Data | **Marketplace data layer (multimap entry cross-node readable)** | ✅ §33 |
| Options | **Pre-paid premium + atomic exercise + expiryheight** | ✅ §26 |
| Options | **Expired-path: rejection + writer recovers underlying** | ✅ §27 |

33 distinct test scenarios, all on Verus mainnet, all txids in TESTING.md.

---

## 17. Limitations and known issues

### What this protocol cannot do

- **Force borrower to repay**. Borrower-side default is the borrower's choice; protocol provides Tx-B for lender's recourse.
- **Protect against private-key compromise**. User-side OPSEC. Use VerusIDs with recovery for personal addresses.
- **Provide instant on-chain dispute resolution**. Pre-signed transactions cover the main cases; subjective disputes go to real-world courts.
- **Support variable-rate or amortizing loans**. Output 0 of each settlement tx is signed-locked at origination. Variable terms require re-signing.
- **Allow joint mid-loan cancellation without re-signing**. There's no protocol-level "abandon" path — parties either cooperate to re-sign or wait for default/Tx-C.
- **Enforce reputation honesty**. Any party can refuse to attest the outcome on their own multimap. Counterparties verify against on-chain truth (the actual settlement tx); absence of a counterparty entry is itself a signal.

### What requires off-chain trust

- **Identifying the counterparty initially** — but reputation reduces this once track records exist
- **Pricing the loan correctly** — counterparties agree off-chain; reputation informs but doesn't dictate
- **Subjective disputes** — real-world legal action, with chain evidence

### Untested aspects (conservative assumptions)

- Behavior under deep chain reorganizations (>10 blocks; reorg-safety reasoned in §7)
- Cross-chain loan denominations involving Verus PBaaS bridges
- Performance characteristics of marketplace browsing at large scale (tens of thousands of active offers)
- Sybil-attack resistance of specific scoring algorithms (these are application-level, not protocol)

---

## 18. Future work / roadmap

| Item | Priority | Effort | Dependencies |
|---|---|---|---|
| Reference wallet implementation (handles ceremony + storage + UX) | **P0** | medium | spec stable |
| VDXF schema canonicalization (formal registry) | P1 | small | none |
| Marketplace explorer (aggregates offers/requests + reputation rendering) | P1 | medium | wallet basics |
| Reputation scoring algorithms (multiple competing approaches) | P1 | medium | history schema |
| Encrypted-multimap ceremony coordinator | P2 | medium | wallet basics |
| Browser-based offer board (no desktop wallet required) | P2 | medium | wallet API |
| Variable-rate / amortizing loan support (via re-signing protocol) | P3 | medium | spec extension |
| Spec for syndicated/multi-party loans | P3 | research | new spec |
| Shielded vault primitive (full bilateral privacy) | research | hard | crypto primitive |

The spec itself is considered stable for v1.0. Implementation is the bottleneck.

---

# Appendices

## Appendix A: Glossary

- **R-address**: Verus's standard transparent address, single-sig public key hash. Prefix `R`.
- **i-address**: Verus identity address, derived from name + parent. Prefix `i`.
- **p2sh address**: Standard Bitcoin pay-to-script-hash address. Prefix `b` on Verus.
- **vault**: Generic term for the address holding the loan's collateral. Either a 2-of-2 p2sh (Profile L) or a 2-of-2 VerusID i-address (Profile V).
- **Tx-O**: Atomic-swap origination tx. Lender pre-signs offline; borrower triggers.
- **Tx-A**: Cooperative raw-tx origination (alternative to Tx-O).
- **Tx-Repay / Tx-B / Tx-C**: Settlement, default-claim, and rescue transactions. All share the same SIGHASH discipline.
- **VDXF**: Verus Data Exchange Format, used for canonical key derivation in contentmultimap.
- **2-of-2 multisig**: A vault requiring 2 signatures from 2 specified parties.
- **nLockTime**: Bitcoin/Verus tx-level timelock — chain rejects broadcast before specified block height.
- **expiryheight**: Verus tx-level expiry — chain rejects broadcast at or after specified block height.
- **SIGHASH flag**: Bitcoin/Verus signature scope specifier.
- **SIGHASH_ALL**: Default; signature covers all inputs and all outputs.
- **SIGHASH_ANYONECANPAY**: Modifier; signature covers only its own input.
- **SIGHASH_SINGLE | SIGHASH_ANYONECANPAY**: Combined; signature covers only its own input + the output at the same index. The protocol's foundational primitive.

## Appendix B: Shielded variants

Verus inherits Sapling z-address shielded transactions. The protocol's transparent-side primitive cannot be ported wholesale to shielded form (Sapling doesn't expose per-input partial signing or shielded multisig), but **one-sided privacy** is achievable with no protocol changes.

### What works

A Verus tx can mix transparent and shielded inputs/outputs. The transparent inputs continue to use SIGHASH flags as in Part I §4. ZIP-0243 sighash includes shielded portion commitments — pre-signing remains valid.

| Variant | What's private | Mechanism |
|---|---|---|
| Lender receives privately | lender's identity, repayment amount as known to outside observers | Tx-Repay's Output 0 is a shielded output to lender's z-address |
| Borrower funds privately | source of borrower's principal/repayment | Tx-Repay's Input 1+ are shielded spends |
| Premium paid privately | source of buyer's premium funds | premium tx is z→z or t→z |
| Strike paid privately | source of buyer's strike at exercise | exercise tx Input 1 is shielded spend |

### What doesn't work

| Wanted | Why not |
|---|---|
| Shielded vault | Sapling has no native multisig — can't have a 2-of-2 shielded address holding collateral |
| Pre-signed shielded settlement template | Shielded portions are proven monolithically; can't be partially constructed and extended later |
| Hidden loan amounts at the vault | Vault is a transparent address; its UTXO value is public |
| Fully bilateral privacy | Vault must be transparent; would need shielded multisig (research direction) |

### Two paths for full bilateral privacy (research)

**Path 1 — Threshold signatures via MPC.** Sapling RedJubjub is Schnorr-like, amenable to multi-party threshold signing. Off-chain MPC protocol produces ONE valid spend signature; chain sees regular shielded spend. Loses async pre-sign property — both parties need to be online at signing time.

**Path 2 — Adaptor signatures.** Maker produces an *incomplete* signature that completes only when a witness is revealed (Lightning PTLC-style). Maintains async-broadcast property. Significant cryptographic engineering required.

For v1, transparent-side + one-sided privacy via shielded recipient outputs is the recommended approach.

---

## Appendix C: The primitive's other applications

The protocol's foundational primitive — "Maker pre-signs an output with `SIGHASH_SINGLE | ANYONECANPAY`; Taker extends and broadcasts atomically" — works on any output the Verus chain accepts. This is the Verus marketplace's internal SIGHASH discipline, lifted to the raw-tx level for direct multi-phase choreography.

| Application | Output 0 type | Example |
|---|---|---|
| **Generic p2p currency swap** | reserve-transfer cryptocondition | DAI for VRSC, no loan structure (validated §30) |
| **VerusID transfer / sale** | `updateidentity` output transferring ID | Buy `alice@` for 50 VRSC |
| **NFT marketplace** | unique-supply token | Sell unique NFT for any currency |
| **Conditional escrow** | currency to maker | Releases only on Taker delivering specific output |
| **Bounty payments** | currency to maker | First valid delivery claims it |
| **Limit orders** | currency to maker | Pre-signed at target price; takers fill when reached |
| **Options markets** | currency to writer (with `expiryheight`) | Buyer exercises before expiration; otherwise writer recovers underlying (validated §26-§27) |
| **Cross-chain swaps** | (via Verus Swap PBaaS bridge) | Same primitive across chains |
| **Lending** | various per phase | This spec — Tx-O, Tx-Repay, Tx-B, Tx-C |

The spec's contribution is the multi-phase choreography that ties together origination, repayment, default, and rescue using the same primitive plus locktime/expiryheight gating. Anything expressible as "Maker irrevocably pre-commits to an output, Taker triggers the trade" works with this primitive on Verus today.

**No new opcodes. No tokens. No DAOs. No oracles. No custodians.**

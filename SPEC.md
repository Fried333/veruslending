# VerusLending — Protocol Specification

**Status:** Draft v0.5 — empirically validated on Verus mainnet (27 distinct test scenarios, including full options market lifecycle)
**Date:** 2026-05
**Target chain:** Verus (VRSC), version ≥ 1.2.16

A peer-to-peer collateralized credit protocol built from existing Verus signature primitives. Two private parties enter a binding loan agreement on chain, with cryptographic enforcement of all four lifecycle phases — origination, repayment, default, rescue — all using the same `SIGHASH_SINGLE | SIGHASH_ANYONECANPAY` pre-commitment pattern. No arbiter. No committee. No third-party intermediary. No panic button. The lender pre-commits at offer time and cannot retract; the borrower can settle unilaterally at any time during the loan term.

**Terminology note:** This spec uses "vault" as the generic term for the address that holds collateral. Two equivalent vault flavors are supported (§2). VerusIDs are *optional* infrastructure — the protocol works without them.

---

## 0. Goals and non-goals

### Goals

- Two-party atomic origination with optional async UX
- Atomic repayment with cryptographic settlement guarantee
- Lender pre-commitment at every phase (cannot stonewall mid-flow)
- Borrower's unilateral repayment power (no live cooperation needed at settlement)
- Time-based default with no live cooperation required
- Reorg-safe by construction (pre-signed txs don't depend on chain state)
- Survives single-party key loss (rescue path)
- Works with existing Verus primitives — no new RPCs or consensus rules
- No mutual-deadlock state ever exists

### Non-goals

- On-chain dispute resolution for subjective claims (use real-world courts; the chain is admissible evidence)
- Margin calls / continuous LTV monitoring (this is non-margin lending, by design)
- Anonymous-stranger lending without external trust (requires reputation/legal infrastructure not in scope)
- Cross-chain BTC collateral (separate workstream — Verus Swap atomic swaps)
- Multi-party / syndicated loans
- Loan secondary market (transferable loan positions)
- Variable-rate / floating-interest loans (requires re-cooperation to update terms)
- Joint mid-loan cancellation (parties wait for default or re-sign cooperatively)

---

## 1. Roles

| Role | Description |
|---|---|
| **Borrower** | Party providing collateral, receiving principal, obligated to repay principal + interest by maturity. |
| **Lender** | Party providing principal, holding rights to claim collateral on default. |

Both are private parties. They identify each other off-chain — the protocol does not provide discovery or matchmaking. Each uses a Verus R-address (Profile L) or VerusID-controlled R-address (Profile V) for sending/receiving funds.

---

## 2. The vault

The **vault** is the address that holds the collateral until one of four pre-signed transactions releases it. Two equivalent flavors:

### 2.1 Profile L (lite, p2sh) — minimal-overhead

The vault is a 2-of-2 p2sh script hash derived deterministically from both parties' compressed public keys:

```
redeem_script = OP_2 <borrower_pubkey> <lender_pubkey> OP_2 OP_CHECKMULTISIG
vault_address = base58(0x55 || ripemd160(sha256(redeem_script)) || checksum)
```

The vault address has a `b` prefix on Verus mainnet (e.g. `bYCcAqB7KfdkfsN8YUipb2fuFhKvxmsnne`). No on-chain registration step. No fee. No name. Both parties exchange pubkeys, derive the address deterministically, proceed.

Validated on mainnet — see TESTING.md §18-§25.

**Use Profile L when:** the parties already know each other off-chain, the loan is one-off, neither party has (or wants to acquire) a VerusID, no on-chain naming or reputation tracking is desired.

### 2.2 Profile V (verusid) — richer UX

The vault is a Verus sub-identity with these properties:

```
vault (VerusID)
  primary:             [borrower_R, lender_R]   M = 2 (2-of-2 multisig)
  revocationauthority: null (or burn address)
  recoveryauthority:   null (or burn address)
  contentmultimap:     loan terms object        (principal, rate, maturity, parties)
  timelock:            0
```

Vault address is the VerusID's i-address (e.g. `i7b7Tq8JYXX9iqS7FBevC6LaG3ioh8z3RM`). Cost: sub-ID registration fee (~0.1 VRSC if a parent identity already exists) or 100 VRSC for a fresh top-level identity.

Profile V buys you:
- Human-readable name (`loan-XXXX.parent@`)
- On-chain encrypted multimap entries (e.g. for hex-backup of pre-signed transactions)
- Reputation hooks for repeat counterparties

Validated on mainnet — see TESTING.md §16, §17.

**Authority semantics (Profile V only):**

- **Primary (2-of-2)**: Both parties must cosign any normal `updateidentity` action. Neither can spend or update unilaterally.
- **Revocation**: null. No party can unilaterally freeze the loan. The protocol provides no panic-button mechanism — and doesn't need one, because the lender cannot stonewall.
- **Recovery**: null. No discretionary recovery path. The vault's collateral can only leave the i-address via one of the four pre-signed transactions in §3.

For Profile L the equivalent semantics are inherent to p2sh: the script has no concept of revoke/recover. Funds release only on 2-of-2 sig.

### 2.3 Choosing a profile

| Use case | Recommended profile |
|---|---|
| Ad-hoc loan between known parties | L |
| Lending desk doing many loans (shared parent ID) | V |
| Community lending facility issuing vault-IDs as a service | V |
| On-chain encrypted hex-backup matters for UX | V |
| Minimal overhead, zero on-chain registration | L |

The protocol's cryptographic guarantees are identical between profiles. The choice is operational — naming, fees, ID infrastructure — not security.

---

## 3. Pre-signed transactions

The protocol has four pre-signed transaction templates. **All four use the same signature discipline:** Input 0 is signed with `SIGHASH_SINGLE | SIGHASH_ANYONECANPAY`, locking Output 0 to the agreed payment, leaving the rest of the transaction extensible by the broadcaster.

| Tx | Phase | Held by | Triggered when | Output 0 |
|---|---|---|---|---|
| Tx-O | Origination | Lender | Borrower decides "now" | Principal → borrower |
| Tx-Repay | Settlement | Borrower | Borrower decides "now", before maturity | Principal+interest → lender |
| Tx-B | Default | Lender | After maturity + grace | Collateral → lender |
| Tx-C | Rescue | Borrower | After far-future lockout | Collateral → borrower |

This is fully symmetric. A wallet implementing one phase implements all four with minor variations.

### 3.1 Tx-O — origination as atomic swap (recommended)

Pre-signed by the lender at offer time. Borrower triggers the broadcast unilaterally when ready.

```
Lender pre-signs:
  Input 0:  Lender's principal UTXO          (signed SIGHASH_SINGLE | ANYONECANPAY)
  Output 0: principal_amount → borrower's R   (sig-locked, paired with Input 0 by index)

Borrower extends and signs at takeup:
  Input 1:  Borrower's collateral UTXO        (signed SIGHASH_ALL)
  Output 1: collateral_amount → vault         (the loan begins here)
  Output 2: borrower's change                 (if any)
  Output 3: lender's change                   (if needed)
```

**Properties:**
- Lender pre-commits irreversibly at offer time. Once Borrower has the hex, Lender cannot retract — except by spending Input 0 elsewhere (which invalidates the offer cleanly).
- Borrower owns the broadcast moment. Suitable for offer boards, async UX, marketplace listings.
- A reorg of an unconfirmed Tx-O simply voids the loan: both parties' funds return to source addresses; rebroadcast or abandon.

Validated on mainnet — see TESTING.md §25.

### 3.2 Tx-A — origination as cooperative raw tx (alternative)

For scenarios where both parties are online together and want a single multi-party signed tx:

```
Inputs:
  - Borrower's UTXO covering collateral + share of fee
  - Lender's UTXO covering principal + share of fee

Outputs:
  - vault address ← collateral amount
  - Borrower's R-address ← principal amount
  - (change outputs as needed)
```

Both parties sign their respective inputs via standard `signrawtransaction`. No SIGHASH_SINGLE involved — purely additive cosigning. Validated on mainnet §16, §18.

Tx-A and Tx-O produce identical post-confirmation state. Choose Tx-A for synchronous ceremony, Tx-O for async.

### 3.3 Tx-Repay — pre-signed repayment (canonical)

The canonical settlement mechanism. Pre-signed at origination by both parties.

```
Template (signed at origination):
  Input 0: vault's collateral UTXO            (signed SIGHASH_SINGLE | ANYONECANPAY by both via redeem script)
  Output 0: principal + interest → lender     (sig-locked, paired with Input 0)
  expiryheight: maturity_block                (cannot broadcast after default deadline)

Borrower extends at repayment:
  Input 1+:  funding UTXOs (principal+interest currency, plus VRSC for fee)
                                              (signed SIGHASH_ALL)
  Output 1+: collateral return + change       (borrower structures freely)
```

The borrower can repay unilaterally. The lender does not need to be online or sign anything at repayment time. Validated on mainnet §16, §18, §20.

**Two fee-model variants:**

- **R-α (collateral-pays-fee):** Output 1 = `collateral - fee` to borrower. Simple but eats slightly into the recovered amount.
- **R-β (broadcaster-pays-fee, recommended):** Borrower attaches a separate VRSC input for fee, gets full collateral back. Required if collateral is non-VRSC (no VRSC in the collateral UTXO to deduct from). Validated §20.

### 3.4 Tx-B — pre-signed default-claim

Lender's recourse if the borrower doesn't repay before maturity.

```
Template (signed at origination):
  Input 0: vault's collateral UTXO            (signed SIGHASH_SINGLE | ANYONECANPAY by both)
  Output 0: collateral → lender               (sig-locked)
  nLockTime: maturity_block + grace_period    (e.g. +30 days)

Lender extends at default-claim:
  Input 1:  lender's VRSC fee UTXO            (signed SIGHASH_ALL)
  Output 1: lender's change                   (after fee deducted from Input 1)
```

Cannot be broadcast before nLockTime. After broadcast, the vault's collateral UTXO is consumed; Tx-Repay and Tx-C are invalidated. Validated on mainnet §17, §19, §21.

**Note:** Earlier drafts (v0.4) used `SIGHASH_ALL` for Tx-B with collateral-pays-fee. v0.5 standardizes on `SIGHASH_SINGLE | ANYONECANPAY` for full symmetry with Tx-Repay and Tx-O. Both work; the v0.5 form gives the lender broadcaster-pays-fee flexibility and matches the protocol's other phases.

### 3.5 Tx-C — pre-signed rescue

Borrower's last-resort path. Activates only if neither Tx-Repay nor Tx-B is broadcast — i.e., both parties have effectively abandoned the loan.

```
Template (signed at origination):
  Input 0: vault's collateral UTXO            (signed SIGHASH_SINGLE | ANYONECANPAY by both)
  Output 0: collateral → borrower             (sig-locked)
  nLockTime: maturity_block + extended_lockout (e.g. +1 year)

Borrower extends at rescue:
  Input 1:  borrower's VRSC fee UTXO          (signed SIGHASH_ALL)
  Output 1: borrower's change
```

Rare. Some implementations may omit Tx-C entirely. With proper backup of Tx-Repay, the borrower's normal recovery path is to repay before maturity, not to rescue. Validated on mainnet §23.

---

## 4. Origination ceremony

The signing order is critical. **All settlement transactions (Tx-Repay, Tx-B, Tx-C) must be fully signed before the origination tx (Tx-O or Tx-A) is broadcast.**

```
Step 1: Both parties exchange compressed pubkeys (Profile L)
        OR register the vault VerusID with 2-of-2 [borrower, lender] (Profile V)

Step 2: Construct unsigned Tx-O (or Tx-A)
        - Determine all inputs and outputs
        - Compute predicted txid (deterministic ECDSA via RFC 6979 makes this stable)

Step 3: Construct and sign Tx-Repay TEMPLATE
        - Input 0 references predicted_txid:vault_vout
        - Output 0 = principal + interest to lender
        - expiryheight = maturity_block
        - Both parties sign Input 0 with SIGHASH_SINGLE | SIGHASH_ANYONECANPAY
        - Borrower stores resulting hex

Step 4: Construct and sign Tx-B TEMPLATE
        - Input 0 references same predicted_txid:vault_vout
        - Output 0 = collateral to lender
        - nLockTime = maturity_block + grace
        - Both parties sign Input 0 with SIGHASH_SINGLE | SIGHASH_ANYONECANPAY
        - Lender stores resulting hex

Step 5: (Optional) Construct and sign Tx-C TEMPLATE
        - Input 0 references same predicted_txid:vault_vout
        - Output 0 = collateral to borrower
        - nLockTime = maturity_block + extended_lockout
        - Both parties sign Input 0 with SIGHASH_SINGLE | SIGHASH_ANYONECANPAY
        - Borrower stores resulting hex

Step 6: Both parties verify Tx-Repay/Tx-B/Tx-C are stored on the appropriate side
        Tx-O: Lender signs Input 0 with SIGHASH_SINGLE | SIGHASH_ANYONECANPAY,
              borrower stores hex; borrower broadcasts when ready
        Tx-A: Both parties sign their inputs and broadcast immediately
```

If the ceremony aborts before step 6, no on-chain state is created. No funds are at risk.

### Predicting the vault-funding txid

Pre-signing settlement txs requires knowing Tx-O/Tx-A's txid before broadcast. With deterministic ECDSA (RFC 6979) the txid is stable from the unsigned form. Wallets compute the predicted txid and use it in Step 3-5. If the actual txid differs (rare; signature variation), abort and restart.

---

## 5. Repayment flow (canonical)

The borrower can repay unilaterally at any time before Tx-Repay's `expiryheight` is reached. **No live cooperation from the lender is needed.**

```
Day N (any day during loan term, before maturity):
  Borrower's wallet retrieves Tx-Repay template from storage
  Wallet selects UTXO(s) totaling at least (principal + interest + fee_budget)
  Wallet appends those UTXOs as new inputs
  Wallet appends Output 1+ for collateral return + change → borrower
  Wallet signs the new inputs with SIGHASH_ALL
  Wallet broadcasts the now-complete tx
```

Result on confirmation:
- Lender's R-address receives principal + interest (Output 0, signed-locked at origination)
- Borrower's R-address receives collateral + change
- Vault's collateral UTXO is consumed; Tx-B and Tx-C are now invalidated
- Lender did not sign anything at repayment time

### Why the lender cannot refuse

The lender's signature on Input 0 was made at origination. The signature is hex bytes in the borrower's wallet. There is no mechanism by which the lender can retract or revoke that signature. Once the borrower broadcasts the complete tx, settlement is automatic.

The lender can:
- Be online or offline at repayment time — irrelevant
- Be alive, dead, or unresponsive — irrelevant
- Want or not want the repayment — irrelevant

The mathematics has been done. The signature is final.

### Why no third party can front-run

The Tx-Repay template is private — held only by the borrower in their wallet, never on the public chain until broadcast. There is no offer in mempool that strangers could see and race against.

When the borrower broadcasts, they submit a complete, fully-signed transaction directly to the network. It either confirms in one block or doesn't. There is no intermediate state where a stranger could intercept.

The signed-paired output (Output 0) cannot be redirected — it specifies the lender's address exactly, and the lender's signature commits to that exact output via SIGHASH_SINGLE pairing. A stranger cannot modify it. **This is empirically validated in TESTING.md §24** (D1, D2 tampering rejected).

---

## 6. Default, rescue, and reorg flows

### 6.1 Normal default (borrower fails to repay)

```
Day 0 to maturity: borrower never broadcasts Tx-Repay
Day maturity + grace: Tx-B's nLockTime is reached
Lender extends Tx-B with own VRSC fee input + change output
Lender broadcasts; collateral lands at lender's R-address
Tx-Repay and Tx-C now invalidated
```

### 6.2 Borrower disappears / loses keys

Same as 6.1 — lender broadcasts Tx-B at maturity + grace. Borrower's heirs lose collateral but kept the principal received at origination.

### 6.3 Lender disappears / loses keys

Borrower broadcasts Tx-Repay normally. Lender's pre-signature is in the template — the broadcast doesn't require lender to be alive or available. Settlement happens unilaterally. The repayment lands at the lender's R-address; the lender's heirs inherit it via standard wallet succession.

### 6.4 Lender's keys compromised post-origination

If an attacker gains the lender's private key after origination but before maturity:

- Attacker can broadcast Tx-B at maturity + grace, claim collateral
- Borrower's defense: broadcast Tx-Repay before then, atomically settling and invalidating Tx-B
- This is a race against the maturity block, not contention over the same UTXO

In practice, the borrower has the entire loan term to detect compromise (lender announces, public alerts) and repay early. The attacker cannot accelerate Tx-B's nLockTime; they must wait for maturity + grace like anyone else.

If the borrower lacks funds to repay early, this becomes a forced default on the borrower's terms. The protocol cannot defend against the lender's own key compromise — that's user-side OPSEC.

### 6.5 Both parties die / lose keys

Funds locked on chain. Heirs may eventually find the off-chain pre-signed transactions and broadcast them. If not, collateral is permanently inaccessible. Acceptable trade-off — the protocol is not responsible for inheritance.

If Tx-C exists, after its far-future locktime either party (or their heirs) can broadcast it to recover collateral to the borrower's address. Lender's heirs would need cooperation from borrower to receive a refund of any unsettled principal.

### 6.6 Chain reorganizations

The protocol is **inherently reorg-resilient** because pre-signed transactions don't depend on chain state for their validity (only on UTXO availability and locktime). A reorg simply means "rebroadcast and try again." There is no scenario where a reorg can cause a party to lose value.

| Reorg scenario | Recovery | Risk |
|---|---|---|
| Tx-O / Tx-A reorged before confirmation | Wallet rebroadcasts; OR either party spends their input elsewhere to cancel (loan never happens) | None — both parties whole |
| Tx-Repay reorged after broadcast | Borrower's wallet rebroadcasts; tx still valid | None — `expiryheight ≤ maturity` blocks broadcasts after deadline |
| Tx-B reorged after broadcast | Lender's wallet rebroadcasts; tx still valid (locktime satisfied) | None — borrower can't broadcast Tx-Repay across maturity if expiryheight set correctly |
| Tx-C reorged after broadcast | Borrower's wallet rebroadcasts; far-future locktime makes contention implausible | None |

**Lender's default-claim procedure:**

```
1. At maturity + grace, broadcast Tx-B
2. Wait for ≥ 6 confirmations (~6 minutes on Verus) before treating the claim as final
3. If a reorg knocks Tx-B out, wallet detects and rebroadcasts immediately
4. After 10 confirmations, finality is essentially guaranteed (Verus has notarization)
```

**Why no double-claim attack via reorg is possible:**

If Tx-B confirms in block N and gets reorged out, the only competing settlement would be Tx-Repay. But Tx-Repay's `expiryheight = maturity_block` makes it invalid at any height ≥ maturity. So the borrower can't "race" Tx-Repay during the reorg window — the network rejects it as expired.

The only adversarial reorg the protocol can't defend against is a deep (>10-block) reorg that simultaneously affects both Tx-B and the chain's notion of "what's the maturity block." On Verus, with ~1-min blocks and notarization, this is implausible. For high-stakes loans, lender simply waits longer (e.g. 100 confirmations).

---

## 7. Edge case coverage matrix

| Scenario | Outcome |
|---|---|
| Cooperation, normal repayment | Borrower broadcasts Tx-Repay; atomic settlement |
| Borrower defaults | Tx-B at maturity + grace |
| Borrower dies/loses keys before maturity | Same as default |
| **Lender dies/loses keys before borrower repays** | **Borrower broadcasts Tx-Repay normally — pre-signature is sufficient** |
| Both die | Funds locked on chain; if Tx-C pre-signed, recoverable to borrower at extended_lockout |
| Lender attempts to refuse repayment | Cannot — pre-signed Tx-Repay does not require lender's runtime cooperation |
| Lender attempts to claim via Tx-B early | Cannot — nLockTime prevents pre-maturity broadcast (validated TESTING §17, §19) |
| Lender attempts to claim via Tx-B after Tx-Repay broadcast | Cannot — collateral UTXO already consumed (validated TESTING §22) |
| Lender's key compromised post-origination | Borrower repays early via Tx-Repay before attacker can broadcast Tx-B at maturity+grace |
| Borrower wants to abandon loan mid-term | Can't unilaterally; defaults at maturity (lender claims) or Tx-C eventually fires |
| Stranger tries to intercept Tx-Repay broadcast | Cannot — tx is complete and atomic; no offer in mempool to race |
| **Stranger / borrower tries to substitute their address into Output 0** | **Cannot — paired output is signed-locked by lender's SIGHASH_SINGLE pre-signature (validated §24, D1)** |
| **Borrower tries to underpay Output 0 amount** | **Cannot — signature commits to exact amount (validated §24, D2)** |
| Subjective dispute (e.g. "lender's address was wrong at origination") | Off-chain courts. Chain record is admissible evidence. |
| Borrower's R-address compromised | User-side OPSEC issue; mitigate with VerusID-controlled R-addresses with proper recovery |
| Tx-Repay leaked publicly | Not exploitable — outputs are locked to lender + borrower; only borrower has UTXOs to add as funding inputs |
| Tx-B leaked publicly | Output goes to lender only; strangers gain nothing |
| Tx-Repay lost by borrower | Borrower can request a re-signing from lender (cooperative). If lender refuses, borrower defaults (cleaner outcome than malicious revoke ever was). |
| Tx-B lost by lender | Lender loses default-claim path; if Tx-C exists, eventually fires for borrower at extended_lockout |
| Reorg of any settlement tx | Wallet rebroadcasts; no value lost (§6.6) |

---

## 8. Off-chain storage requirements

Tx-O (during the offer window), Tx-Repay, Tx-B, and Tx-C must survive their relevant time windows. They are simple hex strings; durability is the holder's responsibility.

### Recommended storage practices

- Multiple copies (cloud encrypted backup, offline storage, trusted third-party hold)
- Both parties may keep copies of all four txs (mutual backup)
- Store the predicted vault-funding txid alongside — needed to validate broadcastability
- Optional: print as paper hex for offline storage
- Profile V loans: store encrypted hex in the vault's contentmultimap for seed-recoverable backup

### Loss scenarios

| Lost item | Consequence |
|---|---|
| Tx-O (lender, before takeup) | Lender can re-sign and re-issue offer; borrower hadn't broadcast yet |
| Tx-Repay (borrower) | Borrower loses canonical repayment path; can request re-signing from lender (cooperation needed). If lender refuses, borrower defaults. |
| Tx-B (lender) | Lender loses default-claim; if Tx-C exists, eventually fires for borrower at extended_lockout |
| Tx-C (borrower) | Last-resort backup gone; if lender broadcasts Tx-B normally, no harm |
| All settlement txs | Depends on cooperation: if both parties online and willing, can re-sign. If not, borrower's option is default; lender's recourse is the chain record + courts. |

---

## 9. Implementation notes

### Wallet UX requirements

A reference wallet implementation should:

1. **Vault discovery**: for Profile L, derive the p2sh address from both parties' pubkeys; for Profile V, register or look up the VerusID.
2. **Origination ceremony coordinator**: walk both parties through the multi-step signing in sequence; warn if any settlement template is skipped.
3. **Pre-signed tx storage**: encrypted backup of Tx-O/Tx-Repay/Tx-B/Tx-C with cloud sync option, paper-export option, status tracking per loan.
4. **Repayment helper**: at borrower's request, automatically consolidate UTXOs and append to Tx-Repay template with correct output structure.
5. **Default-claim notification**: prompt lender well before grace period ends to broadcast Tx-B if no Tx-Repay broadcast.
6. **Tx-Repay expiry warning**: prompt borrower before Tx-Repay's expiryheight passes; once expired, only Tx-C remains as borrower's recovery path.
7. **Reorg handling**: detect if a confirmed settlement tx gets reorged out and automatically rebroadcast.

### Loan terms encoding

Profile V can store loan terms in the vault's contentmultimap under a VDXF key:

```json
{
  "<loan-terms-vdxf-key>": [{
    "<loan-terms-content-vdxf-key>": {
      "version": 1,
      "principal": <amount>,
      "principal_currency": "<currency-id>",
      "interest": <amount>,
      "interest_currency": "<currency-id>",
      "collateral": <amount>,
      "collateral_currency": "<currency-id>",
      "maturity_block": <number>,
      "grace_blocks": <number>,
      "extended_lockout_blocks": <number>,
      "borrower_id": "<borrower-personal-id-or-pubkey>",
      "lender_id": "<lender-personal-id-or-pubkey>",
      "vault_funding_txid": "<predicted-or-actual-txid>"
    }
  }]
}
```

Profile L lacks on-chain storage for loan terms. Keep a signed copy off-chain (e.g. PDF with both parties' signatures) for evidentiary purposes.

### Currency support

The loan can be denominated in any Verus-supported currency: VRSC, fractional-reserve currencies, bridged tokens (vETH, DAI.vETH, tBTC.vETH, vUSDC), or PBaaS chain currencies. The collateral can be a different currency from the principal.

For non-VRSC collateral, use the broadcaster-pays-fee variant (R-β / B-β) so settlement transactions can attach a separate small VRSC input for fees.

### LTV (loan-to-value) recommendations

The pre-signed-Tx-Repay design eliminates lender stonewalling. The remaining concern is borrower default risk:

- **Strangers**: don't lend (no protocol-level reputation system)
- **Reputation-bonded counterparties**: 50-70% LTV common
- **Trusted relationships**: 30-50% LTV acceptable
- **Tight LTV (>80%)**: lower interest justified; minimal default arbitrage incentive remains

Lower LTV = higher temptation for borrower to default and let lender claim collateral. Choose to match counterparty trust level.

---

## 10. Limitations and known issues

### What this protocol cannot do

- **Force borrower to repay**. Borrower-side default is the borrower's choice; protocol provides Tx-B for lender's recourse.
- **Protect against private-key compromise**. User-side OPSEC. Use VerusIDs with recovery for personal addresses.
- **Provide instant on-chain dispute resolution**. Pre-signed transactions cover the main cases; subjective disputes go to real-world courts.
- **Support variable-rate or amortizing loans**. Output 0 of each settlement tx is signed-locked at origination. Variable terms require re-signing.
- **Allow joint mid-loan cancellation without re-signing**. There's no protocol-level "abandon" path — parties either cooperate to re-sign or wait for default/Tx-C.

### What requires off-chain trust

- **Identifying the counterparty**: this is a private agreement between two known parties.
- **Pricing the loan correctly (LTV, interest)**: borrower and lender agree off-chain.
- **Subjective disputes**: real-world legal action, with chain evidence.

### Untested aspects (conservative assumptions)

- Verus mainnet behavior under deep chain-reorg stress for ANYONECANPAY signatures (well-tested in Bitcoin generally, expected to hold on Verus).
- Cross-chain loan denominations involving Verus PBaaS bridges.
- Non-VRSC collateral with VRSC-only fee budget — argued correct via §20-§21 cross-currency results, not directly tested with e.g. tBTC.vETH as collateral.

---

## 11. Reference: empirically validated primitives

Each of the following was directly tested on Verus mainnet during development. See [TESTING.md](./TESTING.md) for txid references.

| Primitive | Validation |
|---|---|
| 2-of-2 multisig vault prevents unilateral redirect (Profile V) | ✅ §16 |
| 2-of-2 multisig vault prevents unilateral redirect (Profile L, p2sh) | ✅ §18 |
| Atomic origination via cooperative raw multi-party tx (Tx-A) | ✅ §16, §18 |
| **Atomic origination via SIGHASH_SINGLE\|ANYONECANPAY pre-signed swap (Tx-O)** | ✅ §25 |
| Pre-signed Tx-Repay with `SIGHASH_SINGLE\|ANYONECANPAY` (canonical) | ✅ §16, §18, §20 |
| Cross-currency settlement (VRSC collateral + DAI principal/interest) | ✅ §18, §20 |
| nLockTime enforcement on Profile V (i-address) input | ✅ §17 |
| nLockTime enforcement on Profile L (p2sh) input | ✅ §19 |
| Pre-signed Tx-B with `SIGHASH_SINGLE\|ANYONECANPAY` + nLockTime | ✅ §21 |
| Broadcaster-pays-fee variant (collateral returned in full) | ✅ §20 (Tx-Repay), §21 (Tx-B) |
| **Tx-C rescue path** | ✅ §23 |
| Tx-Repay broadcast invalidates pre-signed Tx-B (UTXO consumption) | ✅ §22 |
| Pre-locktime broadcast rejected as `64: non-final` | ✅ §17, §19 (diagnostic) |
| **Output 0 recipient tampering rejected (D1)** | ✅ §24 — `mandatory-script-verify-flag-failed` |
| **Output 0 amount tampering rejected (D2)** | ✅ §24 — `mandatory-script-verify-flag-failed` |
| Front-run protection (no offer ever in mempool for Tx-Repay) | ✅ structural |

Negative results from the design phase (ruled out alternative patterns):
- For-clause identity-definition does NOT enforce contents — ❌ ruled out Pay-ID pattern
- Stranger CAN take currency-for-ID offer — ❌ ruled out vault-makes-offer pattern

---

## 11.5 The protocol as a generalization

The four pre-signed transactions in §3 are all instances of the same primitive: **a 2-input atomic swap with one party's contribution sig-locked at offer time**. The lending protocol is one specialization. Other specializations of the same primitive:

### Generic p2p currency swap

The same SIGHASH_SINGLE|ANYONECANPAY pattern enables direct p2p atomic swaps between any two currencies, with no loan attached:

```
Maker pre-signs offline:
  Input 0:  Maker's currency-A UTXO     (signed SIGHASH_SINGLE | ANYONECANPAY)
  Output 0: A_amount → Taker            (sig-locked, paired with Input 0)

Taker fills the offer at takeup:
  Input 1:  Taker's currency-B UTXO     (signed SIGHASH_ALL)
  Output 1: B_amount → Maker            (Taker constructs)
  Output 2: Taker's change

One tx. Atomic. Either both sides happen or neither.
```

This is essentially what Verus's `makeoffer` / `takeoffer` provides at the wallet layer, but at the raw-tx level. It's also the same primitive that this protocol's Tx-O uses — Tx-O is just a swap whose Output 1 is "deposit collateral at vault" rather than "deliver currency-B to maker".

### Conditional payments

A maker can pre-sign an offer that pays out only if a taker delivers a specific output. Useful for atomic services-for-payment exchanges, escrow-less bounties, etc.

### What else the primitive can do

The protocol's foundational primitive — "Maker pre-signs an output with SIGHASH_SINGLE|ANYONECANPAY; Taker extends and broadcasts atomically" — works on any output the Verus chain accepts. Output 0 can be:

| Output type | Application |
|---|---|
| p2pkh / p2sh paying any currency | Generic p2p currency swap |
| Reserve-transfer cryptocondition (any currency, including DAI, tBTC, basket tokens) | Cross-currency swap |
| VerusID `updateidentity` output (changing primary, multimap, etc.) | Atomic ID transfer / sale |
| Single-supply token output (NFT) | NFT sale, NFT-for-NFT swap, NFT-for-currency |
| Multi-currency cryptocondition | Basket-for-basket trade |
| p2sh paying into another vault | What this protocol's Tx-O does |

Combined with `expiryheight` (chain rejects broadcast after a block height) and `nLockTime` (chain rejects broadcast before a block height), the primitive supports:

- **Atomic currency swaps** (replacement for centralized exchanges for any pair Verus supports natively)
- **VerusID sales** (atomic transfer of an ID for payment)
- **NFT marketplace** (sale or trade with no marketplace operator in the loop)
- **Conditional escrow** (Maker releases payment only when Taker delivers a specific output)
- **Bounty payments** (Maker pre-commits; first valid delivery claims)
- **Limit orders** (Maker pre-signs at a target price; Takers fill when market reaches it)
- **Options markets** (Maker pre-signs exercise tx; expiryheight gates exercise window — covered calls, puts, spreads, all natively. See §11.6.)
- **Cross-chain swaps** (Verus Swap already uses this primitive across PBaaS chains)
- **Lending** (this spec — origination + repayment + default + rescue all use the same primitive)

The lending protocol is not introducing new primitives. It's a **structured multi-phase choreography of a pre-existing Verus primitive** — the same SIGHASH_SINGLE|ANYONECANPAY pattern the Verus marketplace uses internally for offers. The contribution is the choreography: predicted-txid coordination, expiryheight to prevent stale settlement, nLockTime to gate default and rescue, and the symmetric sigh disposition across origination, repayment, default, and rescue.

Anything expressible as "Maker irrevocably pre-commits to an output, Taker triggers the trade" works with this primitive on Verus today.

---

## 11.6 Options markets — sketch

A practical design for an options market built on this primitive. The option must be **paid for upfront** (premium delivered before the buyer holds the exercise hex); writers will not accept "pay only if exercised" structures because that exposes them to all of the downside with none of the premium income.

### Option as a tradeable artifact

The cleanest design wraps the exercise transaction as a transferable on-chain artifact:

```
Writer creates a Profile V sub-ID per option:
  Vault VerusID:  option-XXX.writer@
  Primary:        [Writer]   (initially)
  Multimap:       contains encrypted exercise hex (encrypted to whoever currently owns the ID)
  Underlying:     locked in a separate p2sh vault that the exercise hex spends
```

The option is now an identity. Selling the option = transferring the identity, atomically, via the same Tx-O-style swap pattern as in §3.1:

```
Writer pre-signs a "transfer for premium" tx:
  Input 0:   Writer's UTXO authorizing updateidentity        (signed SIGHASH_SINGLE | ANYONECANPAY)
  Output 0:  updateidentity setting primary = Buyer's R-addr (the ID transfer itself, sig-locked)
  expiryheight: option_offer_expiration                       (offer dies if not bought in time)

Buyer takes by adding:
  Input 1:   Buyer's premium UTXO     (signed SIGHASH_ALL)
  Output 1:  premium → Writer's R-addr (the payment for the option)
```

Buyer atomically pays premium and gains control of the option ID. They can now decrypt the exercise hex from the ID's multimap and decide whether to exercise before its `expiryheight`.

Buyer can also resell the option to another party using the same atomic-transfer pattern — secondary market for free.

### Variants

| Style | nLockTime on exercise tx | expiryheight on exercise tx |
|---|---|---|
| American call/put | 0 | option_expiration_block |
| European call/put | option_expiration_block - 1 | option_expiration_block + grace |
| Bermuda (specific dates only) | series of pre-signed exercise txs each with own locktimes | various |

### Properties

- **No custodian.** Underlying is in p2sh vault held by exercise hex; Writer can't touch until ID is back in their control or option expires.
- **No marketplace operator.** Discovery via VerusID multimap (offers as identity entries) or off-chain.
- **Atomic premium-for-option.** Buyer can never receive the option without paying; Writer can never receive premium without delivering. Single tx.
- **Native cancellation.** Writer cancels by spending Input 0 elsewhere before any buyer takes the offer.
- **Native expiration.** After expiryheight on the exercise tx, exercise is impossible. Writer reclaims underlying by broadcasting their pre-signed underlying-return tx (nLockTime = expiration+1).
- **Secondary market.** Option owner can resell using the same primitive (transfer ID for new premium).

### What's still trust-required

- Writer must put the *correct* exercise hex in the multimap (not a fake). Verifiable on-chain by anyone who decrypts: simulate the exercise tx against the underlying p2sh vault and check the strike payment goes to the current ID owner.
- Off-chain consensus on what the option means (which underlying, what strike, what expiration) — written in the multimap as plain JSON, signed by Writer.

### What this is NOT

- Not a substitute for a CEX with margin / leverage / liquidation. This is **fully-collateralized** options only. Writer must lock the underlying (call) or strike-cash (put) for the duration.
- Not an oracle-dependent settlement. Settlement is pure delivery: exercise = exchange of underlying for strike, no oracle needed.

### Mainnet validation

The minimal mechanic — premium paid upfront, underlying locked at 2-of-2 vault, cooperative pre-sign of exercise tx with `expiryheight`, atomic exercise by buyer — is validated on Verus mainnet. See TESTING.md §26 for txids and full procedure.

---

## 12. Future work

- **Reference wallet implementation** (Verus Wallet V2 extension or standalone) speaking the protocol's pre-signed-tx format
- **Origination ceremony tool** (web-based or CLI for guided multi-party signing)
- **Offer-board / marketplace UX** built on Tx-O atomic-swap origination
- **BTC collateral integration** via Verus Swap atomic-swap mechanics (cross-chain)
- **Reputation system** layered on Profile V's contentMultimap for repeat counterparties
- **Variable-rate loan support** via periodic Tx-Repay re-signing protocol
- **Spec for syndicated/multi-party loans** (multiple lenders pool into one vault)

---

## Appendix A: Glossary

- **R-address**: Verus's standard transparent address, single-sig public key hash. Prefix `R`.
- **i-address**: Verus identity address, derived from name + parent. Prefix `i`.
- **p2sh address**: Standard Bitcoin pay-to-script-hash address. Prefix `b` on Verus.
- **vault**: Generic term for the address holding the loan's collateral. Either a 2-of-2 p2sh (Profile L) or a 2-of-2 VerusID i-address (Profile V).
- **Tx-O**: Atomic-swap origination tx. Lender pre-signs offline; borrower triggers.
- **Tx-A**: Cooperative raw-tx origination (alternative to Tx-O for synchronous ceremonies).
- **Tx-Repay / Tx-B / Tx-C**: Settlement, default-claim, and rescue transactions. All share the same SIGHASH discipline.
- **`makeoffer` / `takeoffer`**: Verus's native atomic-swap RPCs. Not used in the canonical design but conceptually similar to Tx-O.
- **VDXF**: Verus Data Exchange Format, used for canonical key derivation in contentmultimap (Profile V only).
- **2-of-2 multisig**: A vault requiring 2 signatures from 2 specified parties.
- **nLockTime**: Bitcoin/Verus tx-level timelock — chain rejects broadcast before specified block height.
- **expiryheight**: Verus tx-level expiry — chain rejects broadcast at or after specified block height.
- **SIGHASH flag**: Bitcoin/Verus signature scope specifier; controls which parts of a tx the signature commits to.
- **SIGHASH_ALL**: Default; signature covers all inputs and all outputs.
- **SIGHASH_ANYONECANPAY**: Modifier; signature covers only its own input (other inputs can be added/changed).
- **SIGHASH_SINGLE | SIGHASH_ANYONECANPAY**: Combined; signature covers only its own input + the output at the same index. The protocol's foundational primitive — used in Tx-O, Tx-Repay, Tx-B, and Tx-C alike.

## Appendix B: Shielded variants (one-sided privacy with z-addresses)

Verus inherits Sapling z-address shielded transactions from Zcash. The protocol's transparent-side primitive cannot be ported wholesale to shielded form (Sapling doesn't expose per-input partial signing or shielded multisig), but **one-sided privacy** is achievable with no changes to the spec — only wallet UX.

### What works

A Verus tx can mix transparent and shielded inputs/outputs. The transparent inputs continue to use SIGHASH flags as in §3, and the sighash computation per ZIP-0243 includes shielded portion commitments — so pre-signing remains valid.

| Variant | What's private | Mechanism |
|---|---|---|
| Lender receives privately | lender's identity, repayment amount as known to outside observers | Tx-Repay's Output 0 is a shielded output to lender's z-address |
| Borrower funds privately | source of borrower's principal repayment | Tx-Repay's Input 1+ are shielded spends |
| Premium paid privately | source of buyer's premium funds | premium tx is z→z or t→z |
| Strike paid privately | source of buyer's strike at exercise | exercise tx Input 1 is shielded spend |

In each case the SIGHASH_SINGLE|ANYONECANPAY pre-commit on the transparent vault input still works — the lender's signature commits to the *commitment* of the shielded output, and the chain enforces that the commitment can't be changed without invalidating the signature.

### What doesn't work

| Wanted | Why it doesn't work |
|---|---|
| Shielded vault | Sapling has no native multisig — can't have a 2-of-2 shielded address holding collateral |
| Pre-signed shielded settlement template | Shielded portions are proven monolithically; can't be partially constructed and extended later |
| Hidden loan amounts at the vault | The vault is a transparent address; its UTXO value is public. The amount can be hidden only at the *inflows* and *outflows*, not at the vault itself |
| Fully bilateral privacy | Vault must be transparent → its state is public, even if endpoint identities are shielded |

### Recommended use

For loans where party identity is sensitive (e.g. private business agreements, OTC desks not wanting to broadcast counterparty list), Profile L + shielded recipient outputs gives meaningful privacy. The vault address and loan amount become observable, but who's lending to whom doesn't.

For full bilateral privacy, wait for a shielded-multisig primitive (potentially via Verus's PBaaS roadmap, Orchard/Halo2 successor schemes, or BLS-based aggregation). Track as v0.6+ direction.

### Not validated on mainnet

The shielded-recipient variant should "just work" given that Sapling/transparent mixing is supported and SIGHASH semantics are well-defined per ZIP-0243. Not directly tested on mainnet during this spec's development. Worth a follow-up validation when the shielded UX is built.

---

## Appendix C: Profile V vs Profile L feature comparison

| Feature | Profile L (p2sh) | Profile V (VerusID) |
|---|---|---|
| Vault address prefix | `b` | `i` |
| Setup cost | $0 | ~$0.05–$30 (sub-ID fee or top-level) |
| Setup steps on chain | None | 1-2 (name commitment + register) |
| Human-readable name | No | Yes |
| On-chain encrypted hex backup | No | Yes (contentmultimap) |
| Reputation hooks | No | Yes (ID activity history) |
| Cryptographic guarantees | Same | Same |
| Reorg-safety | Same | Same |
| Validated mainnet | §18-§25 (this spec, v0.5) | §16-§17 (v0.4) |

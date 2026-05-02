# VerusLending — Protocol Specification

**Status:** Draft v0.3 — empirically validated on Verus mainnet
**Date:** 2026-05
**Target chain:** Verus (VRSC), version ≥ 1.2.16

A peer-to-peer collateralized credit protocol built from existing VerusID and pre-signed transaction primitives. Two private parties enter a binding loan agreement on chain, with cryptographic enforcement of all happy-path and most failure-mode outcomes. No arbiter. No committee. No third-party intermediary. No discretionary recovery authority. No panic button. The lender pre-commits to accepting repayment at origination and cannot retract; the borrower can settle unilaterally at any time during the loan term.

---

## 0. Goals and non-goals

### Goals

- Two-party atomic origination
- Atomic repayment with cryptographic settlement guarantee
- Lender pre-commitment at origination (cannot stonewall at repayment)
- Borrower's unilateral repayment power (no live cooperation needed at settlement)
- Time-based default with no live cooperation required
- Survives single-party key loss (rescue path)
- Works with existing Verus primitives — no new RPCs or consensus rules
- Minimal threat model: only three settlement paths; no mutual-deadlock state ever exists

### Non-goals

- On-chain dispute resolution for subjective claims (use real-world courts; the chain is admissible evidence)
- Margin calls / continuous LTV monitoring (this is non-margin lending, by design)
- Anonymous-stranger lending without external trust (requires reputation/legal infrastructure not in scope)
- Cross-chain BTC collateral (separate workstream — Verus Swap atomic swaps)
- Multi-party / syndicated loans
- Loan secondary market (transferable loan positions)
- Variable-rate / floating-interest loans (requires re-cooperation to update terms)
- Joint mid-loan cancellation (parties must wait for default or re-sign cooperatively)

---

## 1. Roles

| Role | Description |
|---|---|
| **Borrower** | Party providing collateral, receiving principal, obligated to repay principal + interest by maturity. |
| **Lender** | Party providing principal, holding rights to claim collateral on default. |

Both roles are private parties. They identify each other off-chain; the protocol does not provide discovery or matchmaking. Each party uses a VerusID-controlled R-address for sending/receiving funds. Personal ID recovery (heir handling) is the user's own OPSEC, outside protocol scope.

---

## 2. Loan-ID structure

Each loan has exactly one `Loan-ID` — a Verus sub-ID with these properties:

```
Loan-ID
  primary:             [borrower_R, lender_R]   M = 2 (2-of-2 multisig)
  revocationauthority: null (or burn address)
  recoveryauthority:   null (or burn address)
  contentmultimap:     loan terms object        (principal, rate, maturity, parties)
  timelock:            0
```

### Authority semantics

- **Primary (2-of-2)**: Both parties must cosign any normal `updateidentity` action. Neither can spend or update unilaterally.
- **Revocation**: null. No party can unilaterally freeze the loan. The protocol provides no panic-button mechanism — and doesn't need one, because the lender cannot stonewall.
- **Recovery**: null. No discretionary recovery path. The Loan-ID's collateral can only leave the i-address via one of the three pre-signed transactions described in §3.

This is intentional. With Tx-Repay (§3) providing the lender's irrevocable pre-commitment to accept repayment, there's no scenario where revocation/recovery would be load-bearing for the canonical design. Removing them eliminates the malicious-revoke attack surface entirely.

---

## 3. Pre-signed transactions

Three transactions are constructed and signed at origination. One is broadcast immediately; two are held off-chain.

### Tx-A: Origination (broadcast at origination)

A multi-input, multi-output raw transaction signed by both parties:

```
Inputs:
  - Borrower's UTXO covering collateral + share of fee
  - Lender's UTXO covering principal + share of fee

Outputs:
  - Loan-ID's i-address ← collateral amount
  - Borrower's R-address ← principal amount
  - (change outputs as needed)
```

Both parties sign their respective inputs via standard `signrawtransaction`. The Loan-ID is registered in the same tx (or a coordinated companion tx; see §4 for ceremony details).

### Tx-Repay: Pre-signed repayment template (held off-chain by borrower)

The canonical repayment mechanism. Pre-signed at origination by both parties using `SIGHASH_SINGLE | SIGHASH_ANYONECANPAY` on the collateral input.

```
At origination — template construction:
  Inputs:
    Input 0: Loan-ID's collateral UTXO (created by Tx-A)
             Both parties sign with SIGHASH_SINGLE | SIGHASH_ANYONECANPAY
  
  Outputs:
    Output 0: principal + interest → lender's R-address
              (paired with Input 0 by index — signed-locked)
    [Output 1+: borrower fills in at repayment — collateral + change]
  
  expiryheight: maturity_block (so it cannot be broadcast after default deadline)
```

**Signature semantics:**

`SIGHASH_SINGLE | SIGHASH_ANYONECANPAY` on Input 0 means:
- Lender's signature covers ONLY Input 0 itself + Output 0 (the lender's payment, paired by index)
- Does NOT cover other inputs (borrower's funding, added at repayment)
- Does NOT cover other outputs (borrower's collateral return / change — borrower structures freely)

This mirrors how the Verus marketplace itself constructs offers internally (offer's input signed with SIGHASH_SINGLE so it commits exclusively to its paired output). We're using the same SIGHASH discipline at the raw-tx level, bypassing the marketplace's offer/take orchestration to gain explicit control over the structure.

At repayment, the borrower:
- Adds funding inputs from their wallet (any UTXO totaling at least principal+interest+fee)
- Constructs Output 1 (and beyond) for collateral return + change
- Signs new inputs with standard `SIGHASH_ALL`

The lender's pre-commitment is bounded to "I'll release the collateral if exactly principal+interest arrives at my address." Everything else is the borrower's prerogative.

### Tx-B: Lender's default-claim (held off-chain by lender)

Fallback if borrower doesn't broadcast Tx-Repay before maturity.

```
Input:  Loan-ID i-address collateral UTXO (same UTXO as Tx-Repay references)
Output: collateral → lender's R-address (less fee)
nLockTime: maturity_block + grace_period (e.g., +30 days)
Signatures: 2-of-2 [borrower, lender], SIGHASH_ALL, signed at origination
```

Lender broadcasts Tx-B at maturity + grace if the borrower hasn't broadcast Tx-Repay. Cannot be broadcast before nLockTime. Once broadcast, the collateral UTXO is consumed and Tx-Repay/Tx-C are invalidated.

### Tx-C: Borrower's last-resort rescue (optional — held off-chain by borrower)

Mostly redundant given Tx-Repay (which the borrower can already broadcast unilaterally). Exists as a fallback for the case where Tx-Repay was somehow lost AND the lender disappears (so they can't help re-sign), AND the borrower didn't default.

```
Input:  Same Loan-ID i-address collateral UTXO
Output: collateral → borrower's R-address (less fee)
nLockTime: maturity_block + extended_lockout (e.g., +1 year)
Signatures: 2-of-2 [borrower, lender], SIGHASH_ALL, signed at origination
```

Some implementations may omit Tx-C entirely. With proper backup of Tx-Repay, it's almost never needed.

---

## 4. Origination ceremony

The signing order is critical. **All pre-signed transactions must be fully signed before Tx-A is broadcast.**

```
Step 1: Construct unsigned Tx-A (origination)
        - Both parties propose inputs from their wallets
        - Both parties propose outputs (collateral, principal, change)
        - Loan-ID definition prepared (2-of-2 primary, null revoke, null recover)

Step 2: Construct unsigned Tx-Repay template
        - References Tx-A's collateral output (predicted txid:vout)
        - One input (collateral); two outputs minimum (Output 0 = lender's payment; Output 1 = placeholder for borrower's collateral return)
        - Both parties sign collateral input with SIGHASH_SINGLE | SIGHASH_ANYONECANPAY
        - Borrower stores the partial tx hex

Step 3: Construct unsigned Tx-B (lender's default-claim)
        - References Tx-A's collateral output
        - Output to lender's R
        - nLockTime = maturity + grace
        - Both parties sign with SIGHASH_ALL
        - Lender stores

Step 4: (Optional) Construct unsigned Tx-C (borrower's last-resort rescue)
        - References same collateral output
        - Output to borrower's R
        - nLockTime = maturity + extended_lockout
        - Both parties sign with SIGHASH_ALL
        - Borrower stores

Step 5: Both parties verify Tx-Repay/Tx-B/Tx-C are stored on the appropriate side
        Then sign Tx-A and broadcast
```

If the ceremony aborts before step 5, no on-chain state is created. No funds are lost.

### Predicting Tx-A's txid

Verus is a Komodo-fork (legacy Bitcoin tx format). The txid depends on the full signed serialization. To compute Tx-Repay/Tx-B/Tx-C inputs before Tx-A is signed:

- Build Tx-A as fully unsigned with all input/output structure determined
- Compute predicted txid from the unsigned form (deterministic ECDSA via RFC 6979 makes this stable)
- Construct Tx-Repay, Tx-B, Tx-C referencing predicted_txid:collateral_vout
- Sign all of them
- Sign Tx-A; broadcast

If actual txid differs (signature variation), abort and restart. With deterministic signing, this is rare.

---

## 5. Repayment flow (canonical)

The borrower can repay unilaterally at any time before Tx-Repay's expiry block. **No live cooperation from the lender is needed.**

```
Day N (any day during loan term, before maturity):
  Borrower's wallet retrieves Tx-Repay template from storage
  Wallet selects UTXO(s) totaling at least (principal + interest + fee)
  Wallet appends those UTXOs as new inputs to the template
  Wallet appends Output 1+ for collateral return + change → borrower's R
  Wallet signs the new inputs with SIGHASH_ALL
  Wallet broadcasts the now-complete tx
```

Result on confirmation:
- Lender's R-address receives principal + interest (Output 0, signed-locked at origination)
- Borrower's R-address receives collateral + change (Output 1+, structured at repayment)
- Loan-ID's collateral UTXO is consumed
- Tx-B and Tx-C are now invalidated (their input is spent)
- Lender did not sign anything at repayment time

### Why the lender cannot refuse

The lender's signature on the collateral input was made at origination. The signature is hex bytes in the borrower's wallet. There is no mechanism by which the lender can retract or revoke that signature. Once the borrower broadcasts the complete tx, settlement is automatic.

The lender can:
- Be online or offline at repayment time — irrelevant
- Be alive, dead, or unresponsive — irrelevant
- Want or not want the repayment — irrelevant

The mathematics has been done. The signature is final.

### Why no third party can front-run

The Tx-Repay template is private — held only by the borrower in their wallet, never on the public chain until they choose to broadcast. There is no offer in mempool that strangers could see and race against.

When the borrower broadcasts, they submit a complete, fully-signed transaction directly to the network. It either confirms in one block or doesn't. There is no intermediate state where a stranger could intercept.

The signed-paired output (Output 0) cannot be redirected — it specifies the lender's address exactly, and the lender's signature commits to that exact output via SIGHASH_SINGLE pairing. A stranger cannot modify it.

---

## 6. Default and rescue flows

### 6.1 Normal default (borrower fails to repay)

```
Day 0 to maturity: Borrower never broadcasts Tx-Repay
Day maturity + grace: Tx-B's nLockTime is reached
Lender broadcasts Tx-B from off-chain storage
Tx-B confirms; collateral lands at lender's R-address
Tx-Repay and Tx-C now invalidated
```

### 6.2 Borrower disappears / loses keys

Same as 6.1 — lender broadcasts Tx-B at maturity + grace. Borrower's heirs lose collateral but kept the principal at origination.

### 6.3 Lender disappears / loses keys

Borrower broadcasts Tx-Repay normally. Lender's pre-signature is in the template — the broadcast doesn't require lender to be alive or available. Settlement happens unilaterally.

This is a meaningful improvement over `makeoffer`-based designs which would require lender's live participation.

### 6.4 Lender's keys compromised post-origination

The most subtle case worth considering. If an attacker gains the lender's private key after origination but before maturity:

- Attacker can broadcast Tx-B at maturity + grace, claim collateral
- Borrower's defense: broadcast Tx-Repay before then, atomically settling the loan and invalidating Tx-B
- This is a race against the maturity + grace block, not a contention over the same UTXO

In practice, the borrower has the entire loan term to detect compromise (lender announces, public alerts, etc.) and repay early. The attacker cannot accelerate Tx-B's nLockTime; they must wait for maturity + grace like anyone else.

If borrower doesn't have funds to repay early, this is essentially a forced default on the borrower's terms. The protocol cannot defend against the lender's own key compromise — that's user-side OPSEC.

### 6.5 Both parties die / lose keys simultaneously

Funds locked on chain. Heirs may eventually find the off-chain pre-signed transactions and broadcast them. If not, collateral is permanently inaccessible. Acceptable trade-off — the protocol is not responsible for inheritance.

---

## 7. Edge case coverage matrix

| Scenario | Outcome |
|---|---|
| Cooperation, normal repayment | Borrower broadcasts Tx-Repay; atomic settlement |
| Borrower defaults | Tx-B at maturity + grace |
| Borrower dies/loses keys before maturity | Same as default |
| **Lender dies/loses keys before borrower repays** | **Borrower broadcasts Tx-Repay normally — pre-signature is sufficient** |
| Both die | Funds locked on chain; not the protocol's problem |
| Lender attempts to refuse repayment | Cannot — pre-signed Tx-Repay does not require lender's runtime cooperation |
| Lender attempts to claim via Tx-B early | Cannot — nLockTime prevents pre-maturity broadcast |
| Lender attempts to claim via Tx-B after Tx-Repay broadcast | Cannot — collateral UTXO already consumed |
| Lender's key compromised post-origination | Borrower repays early via Tx-Repay before attacker can broadcast Tx-B at maturity+grace |
| Borrower wants to abandon loan mid-term | Can't unilaterally; defaults at maturity (lender claims via Tx-B) or pays back |
| Stranger tries to intercept Tx-Repay broadcast | Cannot — tx is complete and atomic; no offer in mempool to race |
| Stranger tries to substitute their address into Output 0 | Cannot — paired output is signed-locked by lender's SIGHASH_SINGLE pre-signature |
| Subjective dispute (e.g. "lender's address was wrong at origination") | Off-chain courts. Chain record is admissible evidence. |
| Borrower's R-address compromised | User-side OPSEC issue; mitigate with VerusID-controlled R-addresses with proper recovery |
| Tx-Repay leaked publicly | Not exploitable — outputs are locked to lender + borrower; only borrower has UTXOs to add as funding inputs |
| Tx-B leaked publicly | Output goes to lender only; strangers gain nothing |
| Tx-Repay lost by borrower | Borrower can request a re-signing from lender (cooperative). If lender refuses, borrower defaults (cleaner outcome than malicious revoke ever was). |
| Tx-B lost by lender | Lender loses default-claim path; if borrower hasn't broadcast Tx-Repay, lender can broadcast Tx-C if cooperatively re-signed, or default cleanly. |
| Identity primary changed during loan term (cooperative) | Both parties agreed; pre-signed txs may need re-signing (rare; only on agreed renegotiation) |

---

## 8. Off-chain storage requirements

Tx-Repay, Tx-B, and Tx-C must survive the entire loan term. They are simple hex strings; durability is the holder's responsibility.

### Recommended storage practices

- Multiple copies (cloud encrypted backup, offline storage, trusted third party hold)
- Both parties may keep copies of all three txs (mutual backup)
- Store the predicted Tx-A txid alongside — needed to validate broadcastability
- Optional: print as paper hex for offline storage

### Loss scenarios

| Lost item | Consequence |
|---|---|
| Tx-Repay (borrower) | Borrower loses canonical repayment path; can request re-signing from lender (cooperation needed) |
| Tx-B (lender) | Lender loses default-claim; if Tx-C exists, eventually fires for borrower at extended_lockout |
| Tx-C (borrower) | Last-resort backup gone; if lender broadcasts Tx-B normally, no harm |
| All three | Depends on cooperation: if both parties online and willing, can re-sign. If not, borrower's option is default; lender's recourse is the chain record + courts. |

---

## 9. Implementation notes

### Wallet UX requirements

A reference wallet implementation should:

1. **Origination ceremony coordinator**: walk both parties through the multi-step signing in sequence; warn if any pre-signed tx is skipped
2. **Pre-signed tx storage**: encrypted backup of Tx-Repay/Tx-B/Tx-C with cloud sync option, paper-export option, status tracking per loan
3. **Repayment helper**: at borrower's request, automatically consolidate UTXOs and append to Tx-Repay template with correct output structure
4. **Default-claim notification**: prompt lender well before grace period ends to broadcast Tx-B if no Tx-Repay broadcast
5. **Tx-Repay expiry warning**: prompt borrower before Tx-Repay's expiryheight passes; once expired, only Tx-C remains as borrower's recovery path

### Loan terms multimap schema

Stored in the Loan-ID's contentmultimap under a VDXF key. Suggested structure:

```json
{
  "<loan-terms-vdxf-key>": [{
    "<loan-terms-content-vdxf-key>": {
      "version": 1,
      "principal": <amount>,
      "interest": <amount>,
      "maturity_block": <number>,
      "grace_blocks": <number>,
      "extended_lockout_blocks": <number>,
      "currency": "<currency-id>",
      "borrower_id": "<borrower-personal-id>",
      "lender_id": "<lender-personal-id>",
      "tx_a_txid": "<predicted-or-actual-txid>"
    }
  }]
}
```

### Currency support

The loan can be denominated in any Verus-supported currency: VRSC, fractional-reserve currencies, bridged tokens (vETH, vUSDC, etc.), or PBaaS chain currencies. The collateral can be a different currency from the principal.

### LTV (loan-to-value) recommendations

With ANYONECANPAY pre-signed repayment, lender stonewalling is structurally impossible. The remaining concern is borrower default risk:

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
- **Support variable-rate or amortizing loans**. Tx-Repay's outputs are signed-locked at origination. Variable terms require re-signing.
- **Allow joint mid-loan cancellation without re-signing**. There's no protocol-level "abandon" path — parties either cooperate to re-sign or wait for default.

### What requires off-chain trust

- **Identifying the counterparty**: this is a private agreement between two known parties.
- **Pricing the loan correctly (LTV, interest)**: borrower and lender agree off-chain.
- **Subjective disputes**: real-world legal action, with chain evidence.

### Untested aspects (conservative assumptions)

- Verus mainnet behavior under chain-reorg stress for ANYONECANPAY signatures (well-tested in Bitcoin generally, should hold on Verus).
- Behavior of `SIGHASH_SINGLE | SIGHASH_ANYONECANPAY` specifically on cryptocondition-output spends (assumed to work per Bitcoin SIGHASH semantics; the Verus marketplace itself uses SIGHASH_SINGLE for offers, suggesting strong precedent. Empirical test pending).
- Cross-chain loan denominations involving Verus PBaaS bridges.

---

## 11. Reference: empirically validated primitives

Each of the following was directly tested on Verus mainnet during development. See [TESTING.md](./TESTING.md) for txid references and detailed methodology.

| Primitive | Validation status |
|---|---|
| 2-of-2 multisig identity prevents unilateral redirect | ✅ |
| Atomic origination via raw multi-party tx | ✅ |
| nLockTime works on regular tx | ✅ |
| nLockTime works on 2-of-2 i-address spend (Tx-B pattern) | ✅ |
| **`SIGHASH_ALL \| SIGHASH_ANYONECANPAY` accepted on 2-of-2 i-address spend** | ✅ |
| `SIGHASH_SINGLE \| SIGHASH_ANYONECANPAY` on cryptocondition outputs | ⏳ pending direct test (assumed equivalent per Bitcoin semantics + marketplace precedent) |
| Borrower-makes-offer is front-run-safe (alternative pattern) | ✅ |
| Repayment via takeoffer 2-of-2 cosign (alternative pattern) | ✅ |
| For-clause identity-definition does NOT enforce contents | ❌ (ruled out Pay-ID pattern) |
| Stranger CAN take currency-for-ID offer | ❌ (ruled out Loan-ID-makes-offer pattern) |
| Borrower's revoke invalidates pre-signed Tx-B | ✅ (historical — no longer used in canonical design) |
| Verus refuses self-recovery revokes | ✅ (informational — no longer relevant) |
| `closeoffers` works as renege defense | ✅ (relevant only for makeoffer-based fallback pattern) |

Negative results (rows marked ❌) drove the choice of pre-signed Tx-Repay using SIGHASH_ANYONECANPAY over alternative offer-based patterns.

---

## 12. Future work

- **SIGHASH_SINGLE | ANYONECANPAY direct empirical test** to align with Verus marketplace's internal SIGHASH discipline
- **Reference wallet implementation** (Verus Wallet V2 extension or standalone)
- **Origination ceremony tool** (web-based or CLI for guided multi-party signing)
- **BTC collateral integration** via Verus Swap atomic-swap mechanics
- **Reputation system** layered on contentMultimap for repeat counterparties
- **Variable-rate loan support** via periodic Tx-Repay re-signing protocol
- **Spec for syndicated/multi-party loans** (multiple lenders pool into one Loan-ID)

---

## Appendix A: Glossary

- **R-address**: Verus's standard transparent address, single-sig public key hash
- **i-address**: Verus identity address, derived from name + parent
- **Loan-ID**: A VerusID created per loan to hold collateral and serve as the contract notary
- **Tx-A / Tx-Repay / Tx-B / Tx-C**: The four pre-signed transactions of the loan lifecycle
- **`makeoffer`/`takeoffer`**: Verus's native atomic-swap RPCs (alternative to ANYONECANPAY for cooperative settlement)
- **VDXF**: Verus Data Exchange Format, used for canonical key derivation in contentmultimap
- **2-of-2 multisig**: An identity requiring 2 signatures from 2 specified addresses
- **nLockTime**: Bitcoin/Verus tx-level timelock — chain rejects broadcast before specified block height
- **SIGHASH flag**: Bitcoin/Verus signature scope specifier; controls which parts of a tx the signature commits to
- **SIGHASH_ALL**: Default; signature covers all inputs and all outputs
- **SIGHASH_ANYONECANPAY**: Modifier; signature covers only its own input (other inputs can be added/changed)
- **SIGHASH_SINGLE | SIGHASH_ANYONECANPAY**: Combined; signature covers only its own input + the output at the same index. Used in Tx-Repay so lender's signature locks only the lender's payment output, leaving borrower's input/output flexible. This is also how the Verus marketplace constructs offers internally.

## Appendix B: Alternative repayment pattern (legacy / makeoffer-based)

For implementations that cannot use SIGHASH_ANYONECANPAY for some reason, an alternative repayment pattern exists using Verus's makeoffer/takeoffer RPCs:

- Borrower posts `makeoffer` at repayment time (currency for Loan-ID transferred to borrower)
- Lender 2-of-2 cosigns takeoffer; atomic settlement
- Lender CAN stonewall by refusing to cosign

This pattern was empirically validated during development but has a meaningful weakness: the lender can refuse to cosign at repayment time, leaving the borrower's funds locked in the offer escrow until they `closeoffers`.

The earlier draft of this spec (v0.1) used the makeoffer pattern combined with a borrower-controlled revocation authority ("panic button") as a deterrent against lender stonewalling. The panic button was empirically validated (revocation invalidates pre-signed Tx-B). However, the ANYONECANPAY pattern in §3-§5 makes lender stonewalling structurally impossible rather than economically deterred, which is a strict improvement. The panic button is therefore not part of the canonical design.

The makeoffer-based alternative is documented here for completeness and as a fallback for implementations where the canonical pattern is unavailable. It should not be the default choice.

# VerusLending — Protocol Specification

**Status:** Draft v0.1 — empirically validated on Verus mainnet
**Date:** 2026-05
**Target chain:** Verus (VRSC), version ≥ 1.2.16

A peer-to-peer collateralized credit protocol built from existing VerusID and atomic-swap primitives. Two private parties enter a binding loan agreement on chain, with cryptographic enforcement of all happy-path and most failure-mode outcomes. No arbiter. No committee. No third-party intermediary. No discretionary recovery authority.

---

## 0. Goals and non-goals

### Goals

- Two-party atomic origination
- Atomic repayment with cryptographic settlement guarantee
- Time-based default with no live cooperation required
- Borrower-side defense against lender stonewalling (over-collateral arbitrage)
- Survives single-party key loss (rescue path)
- Works with existing Verus primitives — no new RPCs or consensus rules

### Non-goals

- On-chain dispute resolution for subjective claims (use real-world courts; the chain is admissible evidence)
- Margin calls / continuous LTV monitoring (this is non-margin lending, by design)
- Anonymous-stranger lending without external trust (requires reputation/legal infrastructure not in scope)
- Cross-chain BTC collateral (separate workstream — Verus Swap atomic swaps)
- Multi-party / syndicated loans
- Loan secondary market (transferable loan positions)

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
  primary:           [borrower_R, lender_R]   M = 2 (2-of-2 multisig)
  revocationauthority: borrower-personal.@    (panic button — UNILATERAL)
  recoveryauthority:   2-of-2-helper.@        (mutual unfreeze, requires both)
  contentmultimap:   loan terms object        (principal, rate, maturity, parties)
  timelock:          0                        (timelock is at the tx level, not ID level)
```

### Authority semantics

- **Primary (2-of-2)**: Both parties must cosign any normal action (repayment via takeoffer, multimap update, etc.). Neither can spend or update unilaterally.
- **Revocation (borrower-controlled)**: The borrower can unilaterally revoke the Loan-ID at any time. This invalidates pre-signed transactions against the i-address (see §6).
- **Recovery (2-of-2)**: After revocation, both parties must cooperate to assign a new primary. Neither can recover alone. This creates mutual deadlock if revocation is invoked dishonestly.

### Why borrower controls revocation

The borrower's revocation power is the deterrent against **lender stonewalling** (refusing to accept valid repayment in order to claim over-collateralized assets via Tx-B). With this mechanism:

| Lender's action | Outcome |
|---|---|
| Accept valid repayment | Receives principal + interest |
| Refuse repayment, wait for Tx-B | Borrower revokes pre-broadcast → Tx-B invalidated → mutual freeze → lender gets nothing |

Lender's only winning strategy becomes "accept valid repayment." Cheating loses.

The symmetric concern (borrower revokes maliciously to escape default) is addressed by economic disincentive: the borrower's collateral is also frozen post-revoke. Borrower's outcome from malicious revoke equals or exceeds the loss from honest default. Revocation is not a profitable attack.

---

## 3. Pre-signed transactions

Three transactions are constructed and signed at origination. Two are held off-chain, one is broadcast.

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

### Tx-B: Lender's default-claim (held off-chain by lender)

```
Input:  Loan-ID i-address collateral UTXO (created by Tx-A)
Output: collateral → lender's R-address (less fee)
nLockTime: maturity_block + grace_period (e.g., +30 days)
Signatures: 2-of-2 [borrower, lender], signed at origination
```

Held off-chain by the lender. Cannot be broadcast before `nLockTime`. After locktime, lender can broadcast unilaterally — already fully signed by both parties at origination. Borrower's revocation invalidates this pre-signed tx.

### Tx-C: Borrower's rescue (held off-chain by borrower)

```
Input:  Same Loan-ID i-address collateral UTXO
Output: collateral → borrower's R-address (less fee)
nLockTime: maturity_block + lockout (e.g., +1 year)
Signatures: 2-of-2 [borrower, lender], signed at origination
```

Held off-chain by the borrower. The two-pre-signed-txs share the same input; once one is broadcast, the other is invalidated by double-spend protection. Tx-C exists as the borrower's last-resort if the lender disappears entirely.

---

## 4. Origination ceremony

The ordering of signatures is critical. **All three transactions must be fully signed before Tx-A is broadcast.**

```
Step 1: Construct unsigned Tx-A (origination)
        - Both parties propose inputs from their wallets
        - Both parties propose outputs (collateral, principal, change)
        - Loan-ID definition prepared (2-of-2 primary, revoke=borrower, recover=2-of-2 helper)

Step 2: Construct unsigned Tx-B (lender's default-claim)
        - References Tx-A's collateral output (predicted txid:vout)
        - Output to lender's R
        - nLockTime = maturity + grace

Step 3: Construct unsigned Tx-C (borrower's rescue)
        - References same Tx-A collateral output
        - Output to borrower's R
        - nLockTime = maturity + lockout

Step 4: Both parties sign Tx-B and Tx-C
        - Each party adds their signature to both
        - Multi-step coordinated signing via signrawtransaction with returntx=true
        - Lender stores Tx-B; borrower stores Tx-C
        - At this point neither tx is on chain

Step 5: Both parties sign Tx-A
        - Both parties verify Tx-B and Tx-C are stored safely on the holder's side
        - Then sign Tx-A and broadcast

Step 6: Tx-A confirms; loan is active
```

If the ceremony aborts at any step before 5, no on-chain state is created. No funds are lost.

### Predicting Tx-A's txid

Verus is a Komodo-fork (legacy Bitcoin tx format). The txid depends on the full signed serialization. To compute Tx-B and Tx-C inputs before Tx-A is signed:

- Build Tx-A as fully unsigned with all input/output structure determined
- Compute predicted txid from the unsigned form
- Construct Tx-B/C referencing predicted_txid:vout
- Sign Tx-B/C
- Sign Tx-A; if its actual txid matches predicted, Tx-B/C remain valid

If the actual txid differs (e.g., due to signature variation), the parties must abort and restart the ceremony with a fresh prediction. In practice, deterministic ECDSA (RFC 6979) makes this stable.

---

## 5. Repayment flow

The borrower posts a `makeoffer` at any time before maturity. The lender takes via 2-of-2 cosigned `takeoffer`. Atomic settlement.

```
Borrower's makeoffer:
  fromaddress:   borrower's R-address (covers principal + interest payment)
  changeaddress: borrower's R-address
  expiryheight:  some block height before maturity
  offer:         { currency: "VRSC", amount: principal + interest }
  for:           {
                   name: <Loan-ID name>,
                   parent: <Loan-ID parent>,
                   primaryaddresses: [borrower_R],
                   minimumsignatures: 1
                 }
```

The borrower offers principal+interest, asking for the Loan-ID with new primary set to themselves (single-sig, M=1).

### Takeoffer (lender + borrower 2-of-2 cosign)

```
takeoffer fromaddress=lender_R
  txid: <borrower's offer txid>
  deliver: <Loan-ID name>     (the offered identity)
  accept:  { address: lender_R, currency: "VRSC", amount: principal+interest }
```

Because the Loan-ID's primary is 2-of-2, the takeoffer requires both signatures to consume the offer's cryptocondition AND update the Loan-ID's identity record.

Multi-step cosigning:
1. Lender constructs `takeoffer` with returntx=true, signs with their key
2. Lender sends partial hex to borrower
3. Borrower signs with their key via `signrawtransaction`
4. Either party broadcasts the fully-signed tx

### Result on confirmation

- Borrower's R-address: -principal-interest (paid out)
- Lender's R-address: +principal+interest (received)
- Loan-ID: primary changed to [borrower_R], M=1 (single-sig borrower control)
- Collateral inside Loan-ID's i-address: now spendable by borrower

The pre-signed Tx-B and Tx-C are invalidated because the collateral UTXO they reference is consumed by the takeoffer settlement.

### Front-run safety

Because the borrower's `for` clause specifies a particular identity (the Loan-ID), the takeoffer requires authority to deliver that identity. Only the Loan-ID's primary signers (the 2-of-2 set) have that authority. Strangers receive `error -8: This wallet has no authority to sign for any part of delivering the ID specified` and cannot construct a takeoffer.

---

## 6. Default flow

### Normal default (borrower fails to repay)

```
Day 0:           Origination, Tx-A broadcast
Day 0...maturity: Borrower never posts a repayment offer
Day maturity:    Tx-B's nLockTime not yet reached
Day maturity+grace: Tx-B's nLockTime reached
                  Lender broadcasts Tx-B from off-chain storage
                  Tx-B confirms; collateral lands at lender's R-address
```

The lender takes no actions during the loan term. Default-claim is unilateral via the pre-signed Tx-B at maturity+grace.

If the lender forgets/loses Tx-B and never broadcasts, the borrower's Tx-C becomes valid at maturity+lockout (1 year by default) and the borrower can recover collateral instead.

### Lender disappeared (rescue path)

```
Day 0:           Origination
Borrower attempts repayment offer → lender doesn't cosign (dead, lost keys, etc.)
Borrower closes own offer (closeoffers) → recovers attempted-payment funds
Time passes...
Day maturity:    Tx-B's nLockTime reached, but lender never broadcasts
Day maturity+lockout (1 year):  Tx-C's nLockTime reached
                  Borrower broadcasts Tx-C from off-chain storage
                  Tx-C confirms; collateral lands at borrower's R-address
```

### Lender stonewalling (panic button activation)

```
Borrower posts valid repayment offer
Lender refuses to cosign takeoffer (intends to claim collateral via Tx-B at maturity)
Borrower closes own offer (recovers attempted payment)

At/before maturity+grace:
  Borrower invokes revokeidentity on Loan-ID via borrower-personal.@
  Loan-ID transitions to "revoked" state
  Pre-signed Tx-B becomes invalid (script-verify-flag-failed on broadcast)
  Pre-signed Tx-C also becomes invalid

Both parties stuck:
  Recovery requires 2-of-2 [borrower, lender] cooperation
  Neither can act unilaterally
  Forced to negotiate or both lose
```

If they negotiate: 2-of-2 recovery transaction unfreezes the Loan-ID, parties redistribute as agreed. Off-chain renegotiation; on-chain settlement.

If they don't: collateral is frozen forever. Lender lost their entire claim (worse than honest default for them). Borrower also lost collateral access (worse than honest default for them). Mutual destruction outcome.

---

## 7. Edge case coverage matrix

| Scenario | Outcome |
|---|---|
| Cooperation, normal repayment | takeoffer atomic settlement |
| Borrower defaults | Tx-B at maturity + grace |
| Borrower dies/loses keys before maturity | Same as default — lender claims via Tx-B |
| Lender dies/loses keys before borrower repays | Tx-C at maturity + 1 year |
| Both die | Funds locked on chain; not the protocol's problem |
| Lender refuses valid repayment | Borrower revokes → mutual freeze → forced negotiation |
| Borrower revokes maliciously | Mutual freeze; borrower also loses collateral access; worse than default |
| Stranger tries to take repayment offer | Rejected: `error -8: no authority to deliver Loan-ID` |
| Stranger attempts other front-run | Cannot deliver Loan-ID without 2-of-2 authority |
| Subjective dispute (lender claims borrower didn't pay; borrower claims lender refused) | Off-chain courts. Chain record is admissible evidence. |
| Borrower's R-address compromised | User-side OPSEC issue; mitigate with VerusID-controlled R-addresses with proper recovery |
| Lender's R-address compromised | Same |
| Tx-B leaked publicly | Output goes to lender only; strangers gain nothing by broadcasting |
| Tx-C leaked publicly | Output goes to borrower only; strangers gain nothing |
| Tx-B lost by lender | Tx-C eventually fires at maturity + 1 year; borrower wins |
| Tx-C lost by borrower | If lender broadcasts Tx-B, settled; if both lose: stuck |
| Identity primary changed during loan term (cooperative) | Both parties agreed; new state; pre-signed txs may need re-signing on new state |
| Forking attack / chain reorg | Standard handling; low-confirmation settlement risk only |
| Lender's R-address itself is compromised, attacker tries to receive payment | If lender's R is controlled by an ID with proper recovery, lender's heirs can claim back via personal-ID recovery |

---

## 8. Off-chain storage requirements

Tx-B and Tx-C must survive the entire loan term. They are simple hex strings; durability is the holder's responsibility.

### Recommended storage practices

- Multiple copies (cloud encrypted backup, offline storage, trusted third party hold)
- Both parties may keep copies of both txs (mutual backup)
- Store the predicted Tx-A txid alongside Tx-B/Tx-C — needed to validate they remain broadcastable
- Optional: print as paper hex for offline storage

### Loss scenarios

| Lost item | Consequence |
|---|---|
| Tx-B | Lender loses default-claim path; Tx-C eventually fires for borrower |
| Tx-C | Borrower loses rescue path; if lender broadcasts Tx-B normally, no harm |
| Both | Borrower's collateral is stranded if lender disappears AND borrower defaults |
| Loan-ID multimap (loan terms) | On-chain, cannot be lost; just look up via getidentity |

---

## 9. Implementation notes

### Wallet UX requirements

A reference wallet implementation should:

1. **Origination ceremony coordinator**: walk both parties through the multi-step signing in sequence, warn if Tx-B/Tx-C signing is skipped
2. **Rescue tx storage**: encrypted backup of Tx-B/Tx-C with cloud sync option, paper-export option, status tracking (which loans have which txs stored)
3. **Pending action notification**: prompt borrower well before maturity to either repay or default; prompt lender well before grace to broadcast Tx-B if no repayment
4. **Race condition watcher**: borrower-side automation to revoke if lender broadcasts Tx-B while borrower's repayment offer is still pending

### Loan terms multimap schema

Stored in the Loan-ID's contentmultimap under a VDXF key (one possibility):

```json
{
  "<loan-terms-vdxf-key>": [{
    "<loan-terms-content-vdxf-key>": {
      "version": 1,
      "principal": <amount>,
      "interest": <amount>,
      "maturity_block": <number>,
      "grace_blocks": <number>,
      "lockout_blocks": <number>,
      "currency": "<currency-id>",
      "borrower_id": "<borrower-personal-id>",
      "lender_id": "<lender-personal-id>",
      "tx_a_txid": "<predicted-or-actual-txid>"
    }
  }]
}
```

The schema is flexible; what matters is consistent recording for off-chain tooling and dispute evidence.

### Currency support

The loan can be denominated in any Verus-supported currency: VRSC, fractional-reserve currencies, bridged tokens (vETH, vUSDC, etc.), or PBaaS chain currencies. Both parties just agree on the currency at origination and structure Tx-A/Tx-B accordingly.

The collateral can be a different currency from the principal (e.g., principal in vUSDC, collateral in VRSC).

### LTV (loan-to-value) recommendations

Higher LTV reduces lender's incentive to stonewall (smaller arbitrage gain). Recommended ranges:

- **Strangers**: don't lend
- **Reputation-bonded counterparties**: 50-70% LTV typical
- **Trusted relationships**: 30-50% LTV acceptable
- **Tight LTV (>80%)**: lower interest justified; minimal arbitrage incentive

Lower LTV = larger temptation for lender to grab collateral despite borrower offering valid repayment. The panic button defends against this, but operationally borrower must be vigilant about revoking before Tx-B fires if lender stonewalls.

---

## 10. Limitations and known issues

### What this protocol cannot do

- **Force a stonewalling lender to accept payment**. The panic button creates a deterrent (mutual destruction), but if both parties are willing to mutually destroy, borrower cannot force settlement. Real-world courts handle subjective disputes.
- **Eliminate the borrower's option to maliciously revoke**. The deterrent is economic (borrower loses just as much as honest default). Bad actors can still freeze loans for spite.
- **Protect against private-key compromise**. User-side OPSEC. Use VerusIDs with recovery for personal addresses.
- **Provide instant on-chain dispute resolution**. The 1-year rescue period is the longest fallback. Faster resolution requires arbiters (excluded by design).

### What requires off-chain trust

- **Identifying the counterparty**: this is a private agreement between two known parties. The protocol doesn't help find or vet counterparties.
- **Pricing the loan correctly (LTV, interest)**: borrower and lender agree off-chain.
- **Subjective disputes**: real-world legal action, with chain evidence.

### Untested aspects (conservative assumptions)

- Verus mainnet behavior under chain-reorg stress for the panic button mechanism
- Behavior when the Loan-ID's parent identity itself is revoked during a loan term
- Coordinated multi-loan ceremonies (e.g., refinancing one loan with proceeds of another)

---

## 11. Reference: empirically validated primitives

Each of the following was directly tested on Verus mainnet during development:

| Primitive | Validation |
|---|---|
| 2-of-2 multisig identity prevents unilateral redirect | Confirmed via takeoffer cosigning behavior |
| Atomic origination via `createrawtransaction` + multi-party `signrawtransaction` | Confirmed: tx 83500de4...0802e2 broadcast and confirmed |
| Repayment via `makeoffer`/`takeoffer` 2-of-2 cosign | Confirmed: tx a47bb608...153833 broadcast and confirmed |
| Borrower-makes-offer is front-run-safe (stranger cannot deliver) | Confirmed: stranger source returns `error -8: no authority to sign for delivering ID` |
| `closeoffers` works as renege defense | Confirmed across multiple test offers |
| Recovery overrides 2-of-2 (when revoke and recover paired) | Confirmed via VLotto test ID redirect |
| Verus refuses self-recovery revokes | Confirmed: `error -8: Cannot revoke an identity with self as the recovery authority` |
| nLockTime works on regular tx | Confirmed: tx 4bdb627f...79e64 rejected pre-locktime, accepted post-locktime |
| nLockTime works on 2-of-2 i-address spend (Tx-B pattern) | Confirmed: tx 7daa9277...3a6162a — same hex rejected at block 4049178, accepted at block 4049183 |
| Borrower's revokeidentity invalidates pre-signed Tx-B | Confirmed: post-revoke broadcast returns `error 16: mandatory-script-verify-flag-failed (Script evaluated without error but finished with a false/empty top stack element)` |
| For-clause identity-definition does NOT enforce contents | Confirmed: empty Pay-ID delivery succeeded in tx f9d49b26...589f32dc3 — borrower received Loan-ID with collateral despite empty Pay-ID |
| For-clause cannot combine identity + currency | Confirmed: extra fields silently ignored; resulting hex byte-identical with or without them |
| Stranger CAN take currency-for-ID offer | Confirmed: tx d53c8d45...12fcff98c3 — wallet without offerer's keys successfully broadcast takeoffer |

The negative results (last three rows) drove the choice of borrower-makes-offer pattern over Loan-ID-makes-offer pattern.

---

## 12. Future work

- **Reference wallet implementation** (Verus Wallet V2 extension or standalone)
- **Origination ceremony tool** (web-based or CLI for guided multi-party signing)
- **BTC collateral integration** via Verus Swap atomic-swap mechanics
- **Reputation system** layered on contentMultimap for repeat counterparties
- **Spec for syndicated/multi-party loans** (multiple lenders pool into one Loan-ID)
- **Investigation of for-clause hidden fields** to determine if a constrained Pay-ID pattern is achievable

---

## Appendix A: Glossary

- **R-address**: Verus's standard transparent address, single-sig public key hash
- **i-address**: Verus identity address, derived from name + parent
- **Loan-ID**: A VerusID created per loan to hold collateral and serve as the contract notary
- **Tx-A / Tx-B / Tx-C**: The three pre-signed transactions of the loan lifecycle
- **`makeoffer`/`takeoffer`**: Verus's native atomic-swap RPCs
- **VDXF**: Verus Data Exchange Format, used for canonical key derivation in contentmultimap
- **2-of-2 multisig**: An identity requiring 2 signatures from 2 specified addresses
- **nLockTime**: Bitcoin/Verus tx-level timelock — chain rejects broadcast before specified block height

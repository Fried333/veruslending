# Empirical validation log

All tests run on Verus mainnet (chain `i5w5MuNik5NtLcYmNzcvaoixooEebB6MGV`, daemon version 1.2.16). Every load-bearing mechanism in the spec was directly verified before the design was finalized.

## Test environment

- **Local wallet**: developer's wallet, controls multiple R-addresses including RUd7..., RJ6Xejo..., RKirf...
- **Remote wallet (.44)**: separate Verus daemon on remote host, controls RHze... independently. Used to simulate a counterparty that does NOT have access to local's keys.
- **Test ID**: VLotto sub-IDs (`3965555_*.vlotto@`) — pre-existing identities in the local wallet, used as Loan-IDs / Pay-IDs in tests.

## Validation matrix

### 1. 2-of-2 multisig identity prevents unilateral redirect
Identity converted from single-sig to 2-of-2 [RHze, RJ6Xejo]. Subsequent updateidentity attempts from one signer return incomplete signatures via `signrawtransaction` (`complete: False`).

### 2. Atomic origination via raw multi-party tx
- **Tx**: `83500de40a8ec785bc92d9c997912dc72830fcacf38f108748cbb098758802e2`
- **Inputs**: borrower's UTXO (73.9973 VRSC) + lender's UTXO from .44 (10.0 VRSC)
- **Outputs**: 0.5 VRSC collateral → Loan-ID i-address; 0.5 VRSC principal → borrower; change to both
- **Method**: `createrawtransaction` → local partial sign → ship to .44 → cosign → broadcast
- Confirmed in single block; collateral and principal moved atomically.

### 3. Repayment via takeoffer 2-of-2 cosign (alternative pattern)
- **Tx**: `a47bb608e06275f753af0cad779bb4bdb8960ae6bfe35f25a237e6fdbd153833`
- Borrower (RJ6Xejo) posted `makeoffer` (0.55 VRSC for VLotto 108 transferred to borrower)
- Lender (.44) constructed partial takeoffer with returntx=true → 1692 bytes, complete=False
- Local cosigned → 1892 bytes, complete=True
- Broadcast confirmed; collateral returned to borrower's control, lender received payment

### 4. Borrower-makes-offer is front-run-safe
Stranger source (RAhD) attempted takeoffer of borrower's offer for VLotto 108. Result:
```
error code: -8
error message: This wallet has no authority to sign for any part of delivering the ID specified
```
Stranger cannot construct a valid takeoffer because they lack signing authority over the offered Loan-ID.

### 5. closeoffers as renege defense
Multiple test offers closed cleanly via `closeoffers` invocation by offerer. Offered assets returned to source; no third party able to claim closed offers.

### 6. Recovery overrides 2-of-2
With VLotto 108 in 2-of-2 [RHze, RJ6Xejo] state, recovery authority steve.bitcoins@ (controlled by local) revoked + recovered the identity, redirecting it to a fresh single-sig R-address. Confirmed: revoke and recovery overcome the 2-of-2 primary completely.

### 7. Verus refuses self-recovery revokes
Attempting to revoke an identity whose recovery authority is itself returns:
```
error code: -8
error message: Cannot revoke an identity with self as the recovery authority, unless the ID has tokenized ID control
```
This is a protocol-level safeguard against trivial revoke-then-self-recover seizure attacks.

### 8. nLockTime works on regular tx
- **Tx**: `4bdb627fda0a98298c88f2bdf0dedc40feeacf4219a5c2e780500d1047679e64`
- nLockTime = block 4049064; constructed at block 4049061
- Pre-locktime broadcast: `error 64: non-final`
- Same hex broadcast at block 4049064: accepted, confirmed
- Validates Verus consensus enforces nLockTime on standard P2PKH transactions.

### 9. nLockTime works on 2-of-2 i-address spend (Tx-B pattern)
- **Tx**: `7daa92773368d5ae53643dfaa71a5f433da8dea1e99b2561a9d1b3c893a6162a`
- 2-of-2 cosigned (local + .44), spending 0.5 VRSC UTXO from i44CxAB i-address
- nLockTime = block 4049183
- At block 4049178: rejected (`64: non-final`)
- At block 4049183: same hex accepted, confirmed
- Validates the pre-signed default-claim mechanism.

### 10. Borrower's revoke invalidates pre-signed Tx-B (historical — no longer used in canonical design)
- VLotto 108 configured with revocation = steve.bitcoins@ (borrower-controlled), recovery = steve.bitcoins@ (non-self)
- Tx-B pre-signed (2-of-2 cosigned) with future nLockTime
- nLockTime reached, Tx-B is broadcast-eligible
- Borrower invokes `revokeidentity` from steve.bitcoins@ (single-sig, unilateral)
- After revoke confirms, attempt to broadcast saved Tx-B:
  ```
  error code: -26
  error message: 16: mandatory-script-verify-flag-failed
                  (Script evaluated without error but finished with a false/empty top stack element)
  ```
- The pre-signed signatures, valid at sign-time, are no longer accepted by consensus while the identity is revoked.

**Note (v0.3):** This test validated the panic button mechanism. With the introduction of the SIGHASH_ANYONECANPAY canonical repayment pattern (test 14 below), lender stonewalling becomes structurally impossible rather than economically deterred. The panic button is no longer part of the canonical design — Loan-IDs in v0.3 have null revocation/recovery authorities. This test result remains useful empirical knowledge about Verus revocation semantics but is not load-bearing for the protocol.

### 11. For-clause identity-definition does NOT enforce contents
Test of the "Pay-ID" pattern:
- **Tx**: `f9d49b266373f115051030418387e129ab27abf3a97b56189025e2f589f32dc3`
- VLotto 103 (with 0.5 VRSC inside, mock collateral) posted offer:
  - offer: VLotto 103
  - for: VLotto 107 with primary=RHze (mock lender)
- VLotto 107 was empty
- Takeoffer constructed delivering empty VLotto 107, accepting VLotto 103 → broadcast accepted
- Result: VLotto 103 transferred to taker (with collateral inside); VLotto 107 transferred to RHze (still empty)
- The "lender" (RHze) received an empty Pay-ID; the "borrower" (taker) walked away with the collateral
- **Verus does NOT enforce contents in identity-definition for-clauses.** Rules out the naive Pay-ID pattern.

### 12. For-clause cannot combine identity + currency
Tested adding currency/amount/address fields to an identity-definition for-clause. Verus accepts the JSON syntax without error, but the resulting hex is byte-identical to the same offer without those fields. Extra fields are silently ignored.

Also tested for-clause as a JSON array `[{identity}, {currency}]`:
```
error code: -8
error message: Both "offer" and "for" must be valid objects in the first parameter object
```

### 13. Stranger CAN take currency-for-ID offer (front-run risk)
Conclusive test of the front-run vulnerability for currency-for-ID offers:
- **Tx**: `d53c8d451dd94da25b8d278e332ea5a20190fa08dc45dbcb55e94b12fcff98c3`
- Local (RUd7) created offer: offer=VLotto 104, for=0.5 VRSC paid to RJ6Xejo
- .44 wallet (no access to RUd7's keys) constructed takeoffer:
  - deliver: 0.5 VRSC currency
  - accept: VLotto 104 with new primary = RHze (.44's address)
- Takeoffer broadcast successfully from .44; resulting hex accepted by network
- Result: VLotto 104 owned by RHze; 0.5 VRSC paid to RJ6Xejo
- **A stranger without the offerer's signing keys took an offer that the offerer made.** The cryptocondition pre-authorizes consumption; takers don't need offerer's runtime signature.
- Empirically rules out Loan-ID-makes-offer-for-currency at origination as a viable pattern.

### 14. SIGHASH_ALL | SIGHASH_ANYONECANPAY accepted on 2-of-2 i-address spend
- **Tx**: `792b12d25cf5dab5a101ea5162623564f2b792cb872e8f4e09610b28f345e6a4`
- Inputs: borrower's RJ6Xejo UTXO (0.9998 VRSC) + 2-of-2 cosigned i-address UTXO (0.5 VRSC)
- Both 2-of-2 sigs on the i-address input use `ALL|ANYONECANPAY` sighash
- Borrower's input also signed with `ALL|ANYONECANPAY`
- `signrawtransaction` reports `complete: True, errors: 0`
- Broadcast accepted; tx confirmed
- Outputs: 0.6 VRSC → lender; 0.8997 VRSC → borrower (combined collateral + change)
- First validation that ANYONECANPAY semantics work on cryptocondition outputs (collateral i-addresses).
- The ALL flag locks all outputs, restricting borrower's flexibility; the SINGLE variant in test 15 below is the canonical pattern.

### 15. SIGHASH_SINGLE | SIGHASH_ANYONECANPAY on 2-of-2 i-address spend (canonical Tx-Repay)
- **Tx**: `967d509d38d8e81ad6450921e6f7b49dfbd527e918a940c5f0a4c3041cc7e723`
- Setup: VLotto 103 in 2-of-2 [RJ6Xejo, RHze] state, refunded with 0.5 VRSC at i-address (i6ebrehQ...)
- Inputs:
  - Input 0: collateral UTXO at i6ebrehQ (0.5 VRSC)
  - Input 1: borrower's RJ6Xejo UTXO (0.5 VRSC)
- Outputs:
  - Output 0: 0.4 VRSC → RHze (lender's payment, paired with input 0)
  - Output 1: 0.5999 VRSC → RJ6Xejo (collateral + change, paired with input 1)
- Sign sequence:
  - Local signed with `sighashtype="SINGLE|ANYONECANPAY"` → covers input 0 + input 1 against their respective paired outputs
  - .44 cosigned with same sighash (completes 2-of-2 on input 0)
  - `signrawtransaction` confirmed `complete: True, errors: 0`
- Broadcast accepted at block 4049322; confirmed.
- **Validates the canonical Tx-Repay mechanism specified in SPEC.md §3**.
- Verus marketplace uses SIGHASH_SINGLE for offers internally (per main dev). Our raw-tx pattern uses the same SIGHASH discipline.
- Lender's pre-commitment at origination locks ONLY their paired output (Output 0). Borrower has full flexibility for Output 1+ (collateral return + change structure).
- This is the empirically-confirmed canonical pattern for v0.4+.

## Summary of design implications

| Pattern tried | Empirical result | Used? |
|---|---|---|
| Borrower-makes-offer at repayment | Front-run safe; lender stonewall possible | ✅ alternative pattern (legacy / fallback) |
| Loan-ID-makes-offer (currency-for-ID) at origination | Front-run vulnerable | ❌ rejected |
| Loan-ID-makes-offer (Pay-ID swap) at origination | Empty Pay-ID delivery accepted | ❌ rejected |
| Pre-signed Tx-B with nLockTime | Works | ✅ default-claim mechanism |
| Pre-signed Tx-C with nLockTime (same shape as Tx-B) | Works (by extension) | ✅ optional last-resort rescue |
| Borrower's revoke invalidates pre-signed Tx-B | Works | ⚠️ historical — no longer used (canonical design has null revoke/recover) |
| Verus refuses self-recovery revokes | True (protocol-level) | n/a — informational only |
| Pre-signed Tx-Repay with SIGHASH_ALL\|ANYONECANPAY | Works | ✅ early validation (heavier-handed variant) |
| **Pre-signed Tx-Repay with SIGHASH_SINGLE\|ANYONECANPAY** | **Works** | ✅ **canonical repayment mechanism — matches marketplace SIGHASH discipline** |

## State on chain after tests

Some VLotto sub-IDs were mutated during testing and remain in non-original states:
- VLotto 103: 2-of-2 [RJ6Xejo, RHze], 0 VRSC inside (collateral consumed by Tx-Repay test)
- VLotto 104: owned by RHze (.44), empty
- VLotto 107: owned by RHze (.44), empty
- VLotto 108: revoked, recovery=steve.bitcoins@ (recoverable to clean state)

These are test artifacts; not consequential to the protocol design.

### 16. Full canonical end-to-end lifecycle

Complete loan lifecycle from origination through repayment, using only the canonical SIGHASH_SINGLE|ANYONECANPAY pattern, no panic button.

**Setup (Phase 1):**
- VLotto 101 converted to 2-of-2 [RJ6Xejo, RHze], revoke=recover=self (effectively null)
- Conversion tx: `082ca1a302eef507114bf123f9803bc6262b598fd9dccd82d666a4710a162f9d`

**Origination (Phase 2 — Tx-A):**
- Tx: `53c020389a48cf13d22ff2efd0891e9389287745502b487c800999937d4b913d`
- Inputs: borrower 0.5999 VRSC (RJ6Xejo) + lender 0.4999 VRSC (RHze on .44)
- Outputs: 0.5 VRSC → VLotto 101 i-address (collateral); 0.3998 → RJ6Xejo (borrower change + 0.3 principal); 0.1999 → RHze (lender change)
- Multi-party signed via raw tx workflow; broadcast and confirmed
- Loan terms: principal 0.3, interest 0.05, repayment 0.35

**Pre-sign Tx-Repay template (Phase 3 — at origination):**
- Input 0: collateral UTXO at i7b7Tq8JYXX9iqS7FBevC6LaG3ioh8z3RM
- Output 0: 0.35 VRSC → RHze (paired with Input 0 by index)
- Output 1: 0.1499 VRSC → RJ6Xejo (borrower's collateral return)
- Both 2-of-2 signers sign Input 0 with `SINGLE|ANYONECANPAY`
- `signrawtransaction` reports `complete: True, errors: 0`
- Resulting hex held by borrower (in real flow); for this test, executed immediately

**Repayment (Phase 4 — Tx-Repay):**
- Tx: `286ba62f68239b59e713b91fb9a92509e01366975cb8c48fd1e5f858f1b95d55`
- Borrower broadcasts the complete pre-signed Tx-Repay
- Lender's signature made at origination is sufficient; lender does not sign anything at repayment time
- Confirmed in chain (5+ confirmations as of test capture)

**Verification (Phase 5 — final state):**
- Loan-ID i-address: 0 VRSC (collateral consumed)
- RHze (lender): received +0.35 VRSC (matches signed-locked Output 0)
- RJ6Xejo (borrower): received +0.1499 VRSC (collateral return via Output 1)
- VLotto 101 still 2-of-2 active but dormant (no funds; loan complete)

**Validates:**
- ✅ Canonical Tx-Repay flow with SIGHASH_SINGLE|ANYONECANPAY
- ✅ Lender's pre-commitment at origination is final (cannot retract or refuse)
- ✅ Borrower's unilateral broadcast capability (no live cooperation needed)
- ✅ Atomic settlement in single transaction
- ✅ Full lifecycle works end-to-end with no panic button, no recovery authority, no third party
- ✅ Output 0 (lender's payment) locked exactly to specified amount
- ✅ Output 1 (borrower's collateral return) NOT covered by lender's signature; borrower can structure freely

This is the canonical demonstration of the v0.4 protocol design.

## What remains untested (conservative assumptions)

- Behavior of pre-signed transactions across chain reorganizations
- Behavior when input 0 (borrower's funding input) is added at repayment time vs included as a placeholder at origination — assumed equivalent per ANYONECANPAY semantics
- Cross-chain loan denominations involving Verus PBaaS bridges

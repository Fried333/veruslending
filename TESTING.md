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

### 17. Full default-path E2E lifecycle

Companion to test §16. Demonstrates the complete loan lifecycle when the borrower DOES NOT repay — the default path where lender broadcasts pre-signed Tx-B at maturity + grace.

**Setup (Phase 1):**
- VLotto 102 converted to 2-of-2 [RJ6Xejo, RHze], revoke=recover=self
- Conversion tx: `cf6c63945335898009f9d9199d2662aedad356393af5778329603a0b544d187d`

**Origination (Phase 2 — Tx-A):**
- Tx: `944cf8331c318af6b96ca42956e01863b6309773c9a1f28749eb56ad7eff5568`
- Inputs: borrower 0.4487 VRSC + lender 0.55 VRSC
- Outputs: 0.4 → VLotto 102 i-address (collateral); 0.2986 → RJ6Xejo; 0.3 → RHze

**Pre-sign Tx-B (Phase 3 — at origination):**
- Input 0: collateral UTXO (0.4 VRSC)
- Output 0: 0.3999 → RHze (lender claims, less fee)
- nLockTime = block 4049384 (current+10 at sign time)
- Both 2-of-2 signers sign with SIGHASH_ALL
- Resulting hex held by lender

**Pre-locktime sanity check:**
- Attempted broadcast at block 4049374 → rejected with `error 64: non-final` ✅
- Confirms nLockTime enforcement on cryptocondition input

**Default trigger (Phase 4):**
- Borrower never broadcast Tx-Repay (simulated default)
- Block 4049384 reached → Tx-B's nLockTime satisfied
- Lender broadcast saved Tx-B hex
- Tx: `70eb365d6969912bfa2d221ea52a58673cc484970d0eb5d85c11cb071236fa20`
- Confirmed in chain

**Verification (Phase 5):**
- Loan-ID i-address: 0 VRSC (collateral consumed by default-claim)
- RHze (lender): received +0.3999 VRSC (entire collateral, less fee)
- Borrower (RJ6Xejo): received nothing — defaulted; kept their 0.3 principal from origination

**Validates:**
- ✅ Pre-signed Tx-B with future nLockTime, held off-chain by lender
- ✅ Pre-locktime broadcast rejected at consensus
- ✅ Post-locktime unilateral broadcast by lender — no borrower cooperation
- ✅ Atomic settlement: collateral → lender in single transaction
- ✅ Borrower's loss = collateral; gain = principal kept (cleanly defaulted)

Together with test §16, this demonstrates both canonical settlement paths (repay or default) work end-to-end with no third-party involvement.

### 18. Cross-currency p2sh happy path (Loan-ID without VerusID)

Demonstrates the protocol works without any VerusID. Loan-ID is a pure 2-of-2 p2sh derived from both parties' pubkeys — no on-chain registration, no fee for "creating" the Loan-ID.

**Loan terms:**
- Collateral: 10 VRSC (Alice → p2sh)
- Principal: 5 DAI.vETH (Bob → Alice at origination)
- Repayment: 5.5 DAI.vETH (10% interest, due unilaterally by Alice)
- Loan-ID: p2sh `bYCcAqB7KfdkfsN8YUipb2fuFhKvxmsnne` (derived from Alice + Bob's pubkeys)

**Origination (Tx-A):**
- Tx: `3b23258b3d21a9e2ca45f7c73762f9790bb488a8fbf0a8aeb1bd9dcdeace168b`
- Inputs: Alice 73.9972 VRSC + Bob 5 DAI + Bob 0.4 VRSC fee budget
- Outputs: 10 VRSC → p2sh, 5 DAI → Alice (RJ6Xejo), 63.9972 VRSC → Alice change, 0.3998 VRSC → Bob change
- Multi-currency tx confirmed cleanly

**Pre-signed Tx-Repay template** (held by Alice off-chain):
- Input 0: collateral UTXO (10 VRSC at p2sh), signed `SIGHASH_SINGLE | ANYONECANPAY` by both parties via redeem script
- Output 0: 5.5 DAI → Bob (sig-locked, paired with Input 0 by index)

**Repayment (Tx-Repay):**
- Tx: `25564b4cee8dcf39002c44aca442907ef1f666fb582cbb5f767b8a1f181f78de`
- Alice extended template: added inputs (Tx-A's 5 DAI vout + her 0.5 DAI from setup) signed `SIGHASH_ALL`, added Output 1 = 9.9999 VRSC collateral return
- Confirmed cleanly with Tx-A in same block (chained mempool)

**Final state:**
- p2sh: 0 VRSC (consumed)
- Bob (.44): +5.5 DAI received
- Alice (RBV6Z3w2 change addr): +9.9999 VRSC collateral return + her existing 63.9972 VRSC change

**Validates:**
- ✅ p2sh 2-of-2 multisig works as Loan-ID (no VerusID needed)
- ✅ Cross-currency Tx-A (VRSC + DAI in one atomic tx)
- ✅ SIGHASH_SINGLE|ANYONECANPAY pre-signed input survives extension by additional inputs/outputs
- ✅ Lender's pre-commitment is irrevocable across currency boundaries
- ✅ Same protocol mechanics as VerusID flavor (§16) but without the registration ceremony

### 19. Cross-currency p2sh default path

Companion to §18. Same Loan-ID p2sh, fresh UTXOs, default outcome.

**Origination (Tx-A2):**
- Tx: `98ce7f2d403605fdca9bbabacb318ec29f69e7cf48b5d000c2373bb5896e46ea`
- Same 10 VRSC collateral / 5 DAI principal structure

**Default (Tx-B):**
- Tx: `fb1b58b7ac61b008fb5352109cc181635536854a28918fa9beee871d78b5ec9a`
- Alice never broadcast Tx-Repay
- Bob broadcast pre-signed Tx-B post-locktime
- Bob received 9.9999 VRSC (collateral less 0.0001 fee)
- Alice kept the 5 DAI principal she received at origination, lost the collateral

**Pre-locktime rejection (separate diagnostic):**
- Standalone tx with locktime 4050324 broadcast at block 4050224
- Rejected: `error code: -26 — 64: non-final` ✅
- Confirms nLockTime enforcement on p2sh-flavor txs (mirrors §17 which validated this for VerusID-flavor)

**Validates:**
- ✅ Default path on p2sh
- ✅ nLockTime enforcement on p2sh inputs (not just cryptocondition / VerusID)

### 20. Broadcaster-pays-fee variant — happy path (Test C)

Refinement: instead of taking the fee out of the collateral output, the broadcaster (Alice) supplies her own VRSC fee input. Collateral returns to her in full.

**Origination (Tx-A3):**
- Tx: `cba6fcc017e1e30e119f85d272b2b896c8c329b26eed1a7b699e912c4a2da3d5`
- Same 10 VRSC / 5 DAI structure

**Pre-signed Tx-Repay template:**
- Input 0: collateral, signed `SIGHASH_SINGLE | ANYONECANPAY` by both
- Output 0: 5.5 DAI → Bob (sig-locked)

**Repayment (Tx-Repay):**
- Tx: `59e743d1cac41c63312c90ef40ee179268c2049ef4f73457cb1ac7cc6a62775e`
- Alice extended with: 5 DAI from origination + 0.5 DAI from setup + 0.3998 VRSC fee budget (signed SIGHASH_ALL)
- New outputs: **10.0 VRSC (FULL) → Alice**, 0.3997 VRSC change → Alice
- Final state: collateral returned exact-amount, Alice paid 0.0001 VRSC fee from her own pocket

**Validates:**
- ✅ Broadcaster can pay fee externally instead of from collateral
- ✅ Collateral can be returned in full (cleaner UX, especially for non-VRSC collateral)
- ✅ SIGHASH_SINGLE|ANYONECANPAY does not require any specific output beyond Output 0

### 21. Broadcaster-pays-fee variant — default path (Test D)

Companion to §20 for default path. Tx-B uses `SIGHASH_SINGLE | ANYONECANPAY` (instead of plain `SIGHASH_ALL`) so Bob can attach his own fee input + change output at default-claim broadcast time.

**Origination (Tx-A4):**
- Tx: `009d12e4045f9ea88141a171ede2bb382c7932ea239dc11a17e3c2f6f735277e`

**Default (Tx-B):**
- Tx: `ab8be393ca2907137a5719eeac955bc2f3942ae976f2f4378284e200da626926`
- Pre-signed: Input 0 (collateral) signed `SIGHASH_SINGLE | ANYONECANPAY`, Output 0 = 10 VRSC to Bob (full), nLockTime = block+5
- Bob extended at broadcast: added his 0.3999 VRSC fee input (signed SIGHASH_ALL), added Output 1 = 0.3998 VRSC change to himself
- Final: Bob received exactly 10 VRSC (collateral, no fee erosion); Bob paid 0.0001 VRSC fee from his own input

**Spec note:** This proves the SAME sighash discipline (`SIGHASH_SINGLE | ANYONECANPAY`) works for BOTH Tx-Repay and Tx-B. Symmetric protocol — both settlement paths use the same signature flag.

**Validates:**
- ✅ Tx-B with `SIGHASH_SINGLE | ANYONECANPAY` and nLockTime
- ✅ Default-path broadcaster (Bob) can attach own fee input
- ✅ Collateral fully claimed without erosion

### 22. Tx-Repay broadcast invalidates pre-signed Tx-B (A4)

Sanity test: once Alice broadcasts Tx-Repay, Bob's pre-signed Tx-B (which spends the same collateral UTXO) becomes unbroadcastable.

**Setup:**
- Origination Tx-A5: `9668bba3d4baf647760be93b3940d2be7c2f605c66c575eb08bab4b39854125e`
- Pre-signed both Tx-Repay and Tx-B for the same collateral UTXO
- Tx-B nLockTime = current (immediately broadcastable as far as locktime is concerned)

**Test:**
- Broadcast Tx-Repay: `e59c6cc312a28f3ab6d8b12fea42ca75b490bc903dc67ff813701bd26c473dcc` ✓
- Attempt Tx-B broadcast on local: rejected `error code: -26 — 16: bad-txns-inputs-spent`
- Attempt Tx-B broadcast on .44 (different mempool): same rejection

**Validates:**
- ✅ UTXO double-spend protection enforced at chain level (not just per-mempool)
- ✅ Once a settlement path is exercised, all alternative settlement paths are dead

### 23. Tx-C rescue path (F1)

First on-mainnet validation of Tx-C. The rescue path is for "both parties have abandoned the loan" scenarios — collateral returns to the borrower at a far-future nLockTime.

**Setup:**
- Origination Tx-A6: `ae30c9f7f92ab9d5f399b4ddddb7ed0ecd053c57bb57435222e6b9934d387873`
- Pre-signed Tx-Repay (Output 0 = 5.5 DAI to Bob, no nLockTime, held by Alice)
- Pre-signed Tx-B (Output 0 = 10 VRSC to Bob, nLockTime = block+5, held by Bob)
- Pre-signed Tx-C (Output 0 = 10 VRSC to Alice, nLockTime = block+15, held by Alice)
- All three settlement templates signed with same `SIGHASH_SINGLE | ANYONECANPAY` discipline

**Test:**
- Did NOT broadcast Tx-Repay or Tx-B (simulating both-parties-abandon)
- Waited for Tx-C's nLockTime (block 4050274)
- Alice extended Tx-C with her own VRSC fee input + change output, broadcast
- Tx: `3a2943fb83762849c631cd055dd84a94185d6acce684125f608097592339663d`
- Confirmed: Alice received the full 10 VRSC collateral back

**Validates:**
- ✅ Tx-C rescue mechanic with `SIGHASH_SINGLE | ANYONECANPAY` and nLockTime
- ✅ Tx-Repay, Tx-B, Tx-C can coexist as pre-signed alternatives, only one wins
- ✅ Borrower can recover collateral if both parties abandon (subject to far-future nLockTime delay)
- ✅ Same sighash discipline across all three settlement paths — symmetric protocol

### 24. Output 0 tampering rejected (D1, D2)

Validates that `SIGHASH_SINGLE` truly locks Output 0 — neither recipient nor amount can be changed without invalidating the lender's pre-signature.

**Setup:**
- Origination Tx-A7: `b0aba4a88385a109c492c720e5186d94270e889a2afa076e4e2fa0022d44e7a7` (small loan: 2 VRSC collateral, 1 DAI principal, 1.1 DAI repayment)
- Pre-signed Tx-Repay template normally: Output 0 = 1.1 DAI → Bob (RHze)

**D1 — recipient tamper:**
- Hex-substituted Output 0's recipient hash160 from Bob's `5f97b5d514076f9d1dd975d05023d76f742f78b4` to Alice's `60b4e52096c92cd41e83848d142861244b764d21`
- Decoder confirmed Output 0 now read `RJ6XejoGrH9TAX5grUmNfKSqBmW1dmg8V9` (Alice)
- Added Alice's funding inputs and broadcast
- Rejected: `error code: -26 — 16: mandatory-script-verify-flag-failed (Script evaluated without error but finished with a false/empty top stack element)` ✅

**D2 — amount tamper:**
- Hex-substituted Output 0's amount from 1.1 DAI to 0.5 DAI (borrower trying to underpay interest)
- Decoder confirmed Output 0 still went to Bob, just at smaller amount
- Same broadcast attempt → same rejection: `mandatory-script-verify-flag-failed` ✅

**Validates:**
- ✅ Borrower cannot redirect lender's payment to anywhere else (D1)
- ✅ Borrower cannot underpay the agreed amount (D2)
- ✅ Verus's ECDSA signature verification correctly enforces SIGHASH_SINGLE's commitment over Output 0
- ✅ Pre-commitment is robust under realistic adversarial conditions

## What remains untested (conservative assumptions)

- Behavior of pre-signed transactions across chain reorganizations (G1–G3)
- Behavior when input 0 (borrower's funding input) is added at repayment time vs included as a placeholder at origination — assumed equivalent per ANYONECANPAY semantics
- Cross-chain loan denominations involving Verus PBaaS bridges
- Race-at-maturity-boundary (C1) — Tx-Repay and Tx-B broadcast simultaneously, first miner wins
- Death/inheritance scenarios (E1–E6) — primarily about wallet UX, not protocol mechanics
- Non-VRSC collateral in practice (H1) — should work per the cross-currency results in §18-§21 but not directly tested with e.g. tBTC.vETH as collateral
- D3 (broadcaster adds extra outputs to steal extra value) — argued safe by accounting (tx must balance, broadcaster's added inputs must fund their added outputs). Not directly tested.

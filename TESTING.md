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

### 25. Tx-O atomic-swap origination

First mainnet validation of the v0.5 spec's Pattern A2 — origination as an atomic swap, mirroring Tx-Repay's signature discipline. Lender pre-commits offline; borrower triggers the broadcast unilaterally when ready.

**Loan terms (small, just to validate the mechanic):**
- Collateral: 2 VRSC (Alice → p2sh)
- Principal: 0.5 DAI (Bob → Alice via pre-signed atomic swap)
- Loan-ID: same p2sh `bYCcAqB7KfdkfsN8YUipb2fuFhKvxmsnne`

**Phase 1 — Bob pre-signs offer offline:**
- Built skeleton tx: 1 input (Bob's 0.5 DAI UTXO `98ce7f2d...` vout 3), 1 output (0.5 DAI → Alice)
- Bob signed Input 0 with `SIGHASH_SINGLE | SIGHASH_ANYONECANPAY`
- Resulting hex (532 bytes) handed to Alice

**Phase 2 — Alice extends and broadcasts at takeup:**
- Added Input 1: Alice's 2.7997 VRSC UTXO at RBV6Z3w2
- Added Output 1: 2 VRSC → p2sh Loan-ID (the collateral)
- Added Output 2: 0.7996 VRSC → Alice's change
- Alice signed Input 1 with `SIGHASH_ALL`
- Broadcast: `023d3256f383e747846f132afe7a125899602fa300942aa34bc414e9b39ac033`
- Confirmed in block `00000000000138b08285d05106a8c30b1bb6c448bae7140343a905bece8d9b6c`

**Final state:**
- p2sh: +2 VRSC (collateral now in custody)
- Alice: +0.5 DAI received (principal, from Bob's pre-committed input)
- Bob: -0.5 DAI (his offer was taken)
- Fee: 0.0001 VRSC

**Validates:**
- ✅ Atomic-swap origination via SIGHASH_SINGLE|ANYONECANPAY (same discipline as Tx-Repay)
- ✅ Lender can pre-commit offline; borrower triggers broadcast unilaterally
- ✅ Borrower can choose the broadcast moment (e.g., favorable conditions, async UX)
- ✅ Lender's pre-commitment is irrevocable in mempool — cannot retract once Alice broadcasts
- ✅ Lender's only "cancellation" path is to spend his Input 0 elsewhere before Alice broadcasts

**Why this matters:**

This makes the protocol fully symmetric across all four phases. The same SIGHASH_SINGLE|ANYONECANPAY pre-commitment + broadcaster-extends-and-triggers pattern is now validated for:

| Phase | Pre-signer | Trigger party | Tx |
|---|---|---|---|
| Tx-O — origination | Lender | Borrower | §25 (this test) |
| Tx-Repay — settlement | Lender (& borrower) | Borrower | §16, §18, §20 |
| Tx-B — default | Both | Lender | §17, §19, §21 |
| Tx-C — rescue | Both | Borrower | §23 |

Origination ceremony is no longer a synchronous-online event. It can be: lender posts offer → borrower takes when ready → loan exists. Same UX as a marketplace listing.

### 26. Options primitive — pre-paid premium + atomic exercise + expiryheight

First mainnet validation of the options-market mechanic described in SPEC.md §11.6. Same SIGHASH_SINGLE|ANYONECANPAY primitive as Tx-O / Tx-Repay, but with `expiryheight` instead of `nLockTime` to gate the EXERCISE WINDOW from above (rather than below).

**Setup — call option:**
- Writer: Bob (RHze on .44)
- Buyer: Alice (RJ6Xejo locally)
- Underlying: 1 VRSC
- Strike: 1 DAI
- Premium: 0.1 DAI (paid upfront)
- Expiration: block 4050321 (current+10 at exercise time)

**Phase 1 — Premium payment (Alice → Bob, paid first):**
- Tx: `70ccdbfea6df5a9ccd36c48593cd000e903c761dd420ef014860153afb859d87`
- 0.1 DAI from Alice to Bob via standard `sendcurrency`
- Validates: pay-first model is just a regular tx; no new mechanic needed for premium leg

**Phase 2 — Underlying lock (Bob → vault):**
- Tx: `97d720403011d6a5c205a238dedab45455aa4f73d4580f7e14dfcd767e258f55`
- 1 VRSC from Bob to p2sh vault (vout 1)
- Underlying now locked at 2-of-2 — neither party can spend unilaterally

**Phase 3 — Cooperative pre-sign of exercise tx:**
- Input 0: vault's 1 VRSC UTXO (signed `SIGHASH_SINGLE | ANYONECANPAY` by both Alice and Bob)
- Output 0: 1 DAI → Bob (sig-locked, the strike payment)
- expiryheight: 4050321 (block beyond which exercise tx is invalid)
- Resulting hex (758 bytes) held by Alice (the buyer)

**Phase 4 — Exercise (Alice broadcasts before expiration):**
- Alice extended template: added Input 1 (her 1 DAI strike) and Output 1 (0.9999 VRSC underlying receipt)
- Signed Input 1 with `SIGHASH_ALL`
- Tx: `f48ba0c3b39aa3b6d414fbe06a81ac65c3205687d096ef5080ce8ea34a79f39c`
- Block 4050311 (10 blocks before expiry)
- Confirmed in block `0000000000004a0c454c36fab2a0ab33147d42bc1c619303e8b6c795d55fb40c`

**Final state:**
- Vault (p2sh): underlying consumed
- Bob (writer): +1 DAI strike (sig-locked Output 0) + 0.1 DAI premium (already received in Phase 1) = +1.1 DAI net
- Alice (buyer): -1 DAI strike, +0.9999 VRSC underlying, -0.1 DAI premium = net acquired 0.9999 VRSC at effective price 1.1 DAI
- Fee: 0.0001 VRSC (deducted from underlying)

**Validates:**
- ✅ Pay-first premium model works as a separate `sendcurrency` (no special chain mechanic needed)
- ✅ Underlying lock at 2-of-2 vault prevents writer rug-pull during the option window
- ✅ Cooperative pre-signed exercise tx with `expiryheight` enforces the expiration window
- ✅ Buyer-triggered atomic exercise (strike-for-underlying in one tx)
- ✅ Same SIGHASH_SINGLE|ANYONECANPAY primitive as the lending protocol — fully reusable
- ✅ Output 0 sig-lock prevents buyer from underpaying the strike (same protection as Tx-Repay D2 §24)

**Why this matters:**

The options primitive is **the same building block as the loan primitive, with `expiryheight` substituted for `nLockTime`.** A wallet that supports VerusLending can support options markets with no new chain mechanics — just different parameters in the same ceremony. Verus already has fully-collateralized, oracle-free, custodian-free options today. The only missing piece is wallet UX.

After expiration (block ≥ 4050321), the exercise tx becomes unbroadcastable (`tx-expiring-soon` rejection — already validated in §F1 cleanup). Writer's separate "underlying-return" tx with `nLockTime = expiration+1` recovers the underlying. (Underlying-return path validated by extension; same nLockTime mechanic as Tx-B in §17, §19, §21.)

### 27. Options primitive — expired-and-recovered path

Companion to §26. Validates that an unexercised option correctly expires and the writer recovers the underlying. Closes the lifecycle.

**Setup — premium paid first, then underlying locked:**
- Premium: `22eea6d0554d00e36feee947320fee75822a172267c97e103f4491536450d54f` (Alice → Bob, 0.05 DAI)
- Underlying lock: `3f59d6635be79b6b67ef31b08b898487a652ad9fb639c851203c8e6200893913` (Bob → vault, 0.5 VRSC at vout 1)

**Cooperative pre-sign of two templates:**

*Exercise template* (held by Alice, the buyer):
- Input 0: vault's 0.5 VRSC UTXO (signed `SIGHASH_SINGLE | ANYONECANPAY` by both)
- Output 0: 0.5 DAI → Bob (sig-locked, the strike)
- expiryheight: block 4050336 (5 blocks after pre-signing)

*Underlying-return template* (held by Bob, the writer):
- Input 0: same vault UTXO (signed `SIGHASH_SINGLE | ANYONECANPAY` by both)
- Output 0: 0.5 VRSC → Bob (sig-locked, recovery)
- nLockTime: block 4050337 (1 block after exercise expires)

**Phase 1 — Alice does NOT exercise.** Lets the option expire.

**Phase 2 — Test expired-exercise rejection (block 4050338, past expiry):**
- Attempted broadcast of exercise template on local node:
- Result: `error code: -26, tx-expiring-soon: expiryheight is 4050336 but should be at least 4050344 to avoid transaction expiring soon`
- Same rejection on .44 ✅
- Verus enforces an 8-block buffer past expiryheight; once reached, the tx is dead

**Phase 3 — Bob recovers underlying (post nLockTime):**
- Bob extended underlying-return template: added Input 1 (his 0.35 VRSC fee budget UTXO) and Output 1 (0.3499 VRSC change)
- Signed Input 1 with `SIGHASH_ALL`
- Tx: `4c53edf63f85dc370d2ba3aec97bced6fe33445bf8693cf5a1c84ccf9b9331d8`
- Confirmed cleanly

**Final state:**
- Vault: 0.5 VRSC consumed by return tx (vault still holds 4 VRSC from prior unrelated tests)
- Bob: +0.5 VRSC underlying recovered + 0.05 DAI premium kept (Alice's premium became Bob's profit for taking on the option-writing obligation)
- Alice: -0.05 DAI premium (sunk cost of holding the option that wasn't exercised)
- Fee: 0.0001 VRSC paid by Bob's broadcast input

**Validates:**
- ✅ `expiryheight` enforcement on pre-signed exercise tx — broadcast attempt rejected once block ≥ expiryheight (with 8-block buffer)
- ✅ Writer's underlying-return tx with `nLockTime > expiryheight` broadcasts cleanly post-expiration
- ✅ The same UTXO can be the spend target of multiple pre-signed alternative txs (exercise OR return); whichever broadcasts first consumes it
- ✅ Premium economics: writer keeps premium regardless of exercise — this is the writer's compensation for locking up underlying
- ✅ Pay-first ordering enforced naturally — buyer's premium is a separate confirmed tx before the option becomes "active" (the underlying lock + pre-signed templates exist)

**Why this matters:**

§26 + §27 together cover the **full options lifecycle**: pre-paid premium, atomic exercise OR atomic expiration, writer recovery on no-exercise. With §24's tampering rejection (Output 0 amount/recipient locked), the chain enforces all the load-bearing properties an options market needs:

- Buyer cannot underpay strike (§24 D2)
- Buyer cannot redirect strike payment (§24 D1)
- Buyer cannot exercise after expiration (§27)
- Writer cannot reclaim underlying before expiration (would fail nLockTime)
- Writer cannot rug-pull (underlying is at 2-of-2 vault)
- Writer keeps premium whether or not buyer exercises (§27)
- Atomic strike-for-underlying delivery on exercise (§26)

This is a complete, oracle-free, custodian-free options primitive on Verus today using only existing transparent transaction features.

### 28. SIGHASH-pre-signed Output 0 to a VerusID i-address

Validates that the protocol's primitive works when the sig-locked Output 0 is a VerusID i-address (not just an R-address). Important because lender/borrower may want loan payments to land at their VerusID's i-address (so the multimap reputation system in §13 sees activity at that ID).

**Setup:**
- Pre-existing VerusID: `i65fv1p21V6UeXMcCsE4HmQPxHo8usUKCV` (single-primary, controlled via RKirf)

**Atomic swap mini-test:**
- Bob's offer template: Input 0 = his 0.1 DAI UTXO, Output 0 = 0.1 DAI → `i65fv1p21V6UeXMcCsE4HmQPxHo8usUKCV` (i-address)
- Bob signs Input 0 with `SIGHASH_SINGLE | SIGHASH_ANYONECANPAY`
- Alice extends with her VRSC fee input + change output
- Alice signs and broadcasts

**Tx:** `40104bf7b5eb0d04b429c317a70172d0ac73ddf2dd380b5bdf26f02954c9a409`
**Confirmed in chain.**

**Final state:**
- `i65fv1p21V6UeXMcCsE4HmQPxHo8usUKCV` balance: +0.1 DAI ✓ (verified via getaddressbalance)

**Validates:**
- ✅ Output 0 sig-lock works when recipient is a VerusID i-address (cryptocondition output type)
- ✅ Verus's signrawtransaction handles SIGHASH_SINGLE|ANYONECANPAY identically for R-address and i-address recipients
- ✅ Wallets can sig-lock payments to a VerusID without changing the protocol
- ✅ Enables the §13 reputation flow where loan outcomes credit the parties' VerusIDs directly

This unlocks the recommended Profile L vault + Profile-V parties configuration (§2.4): the vault is a cheap p2sh, but loan payments flow to/from the parties' personal VerusIDs, where reputation accumulates.

### 29. B4: Tx-Repay rejected after Tx-B broadcast (symmetric to A4)

Mirror of §22 (A4). Validates that the UTXO double-spend protection works in both directions: once *either* settlement path has consumed the vault, the other is dead.

**Setup:**
- Vault lock: `7a5e5aec128d81a014ba0eff4d93f0c68484ddef946efe32fd8918dd135ef54e` vout 1 (1 VRSC at p2sh)
- Pre-signed Tx-Repay: Output 0 = 0.5 DAI → Bob, no locktime
- Pre-signed Tx-B: Output 0 = 1 VRSC → Bob, nLockTime = current

**Test:**
- Bob extends Tx-B with fee input + change, broadcasts: `4081015b9dffc9f45339726a0797751a274c5dc5e823cac614585640295366c1` ✓
- Alice attempts to broadcast Tx-Repay (with her DAI input added) on local: rejected `error code: -26 — 16: bad-txns-inputs-spent`
- Same rejection on .44 ✅

**Validates:**
- ✅ Symmetric to A4 (§22): once either Tx-Repay OR Tx-B consumes the vault UTXO, the other becomes invalid
- ✅ Both lender's claim and borrower's repayment are mutually exclusive at chain-consensus level
- ✅ No double-spend or two-track settlement is possible

Together with §22, this proves: **the protocol's settlement is final when any settlement tx confirms; no race window exists where both could claim.**

### 30. Generic p2p atomic currency swap (validates SPEC §11.5)

Validates that the SIGHASH_SINGLE|ANYONECANPAY primitive works for **non-lending applications** — pure currency-for-currency atomic swap with no loan structure, no vault, no settlement templates. Same building block, different application.

**Setup — Alice swaps 0.2 DAI for 0.05 VRSC from Bob:**
- Bob's offer template:
  - Input 0: Bob's 0.5 VRSC UTXO (`4c53edf6...` vout 0)
  - Output 0: 0.05 VRSC → Alice (sig-locked, paired)
- Bob signs Input 0 with `SIGHASH_SINGLE | SIGHASH_ANYONECANPAY`. Hands hex to Alice.

**Alice extends and broadcasts:**
- Input 1: Alice's 5 DAI UTXO (signed `SIGHASH_ALL`)
- Output 1: 0.2 DAI → Bob (Alice's payment)
- Output 2: 4.8 DAI → Alice (DAI change)
- Output 3: 0.4499 VRSC → Bob (his VRSC change after fee)
- Tx: `9be44e0782416fa8a978e7df71c85fa5290f62146c1e8eb1f07e00b7ac4d7dee`
- Confirmed cleanly

**Final state:**
- Alice: -0.2 DAI, +0.05 VRSC (acquired VRSC at price 4 DAI per VRSC)
- Bob: +0.2 DAI, -0.05 VRSC, -0.0001 VRSC fee
- Atomic — no counterparty risk, no order book, no platform

**Validates:**
- ✅ The SIGHASH_SINGLE|ANYONECANPAY primitive supports generic p2p currency swaps
- ✅ No vault, no Profile L/V choice — just two parties trading directly
- ✅ Maker (Bob) pre-commits offline; taker (Alice) triggers when ready
- ✅ Maker can cancel by spending Input 0 elsewhere before taker broadcasts
- ✅ SPEC §11.5's claim that "lending is one specialization of a general primitive" is empirically grounded

**Why this matters:**

This is the same primitive the Verus marketplace uses internally for offer construction, exposed at the raw-tx level. Combined with the lending validations (§16-§29) and options (§26-§27), the test set demonstrates the primitive's **generality**: same building block, multiple applications. A wallet that implements the SIGHASH ceremony for one application gets the others for free.

### 31. H1: non-VRSC collateral — discoveries and validated cooperative settlement

Attempted: full lending lifecycle with DAI as collateral and VRSC as principal. Surfaced two important Verus implementation findings.

**Tx-A — DAI collateral to vault:**

Attempt 1: vault = p2sh `bYCcAqB7KfdkfsN8YUipb2fuFhKvxmsnne`.
- Output 0: 5 DAI → p2sh
- Decoded output type: `nonstandard`, addrs: None
- Broadcast attempt: `error code: -26 — 16: bad-txns-failed-params-precheck`
- **Finding 1: reserve-currency cryptocondition outputs to plain p2sh are non-standard.** Reserve transfers must target an R-address or VerusID i-address. Profile L (pure p2sh vault) cannot hold non-VRSC reserves.

Attempt 2: vault = VerusID `i6ebrehQ6dyJGjy8LoxkaPfJ2Vo7dXGbHy` (Profile V).
- Tx: `982f302c32cbeb964077036c7d88756d19bd2153d3840d667d0c1c63b9ef4bf8`
- 5 DAI deposited at vault i-address ✓ (cryptocondition output, standard)

**Pre-signing Tx-Repay attempt (SIGHASH_SINGLE|ANYONECANPAY):**

- Input 0: vault's 5 DAI UTXO (cryptocondition reserve-transfer output)
- Output 0: 0.55 VRSC → Bob (sig-locked, cross-currency pairing)
- Result: `complete: False, error: 'Opcode missing or not understood'`
- **Finding 2: SIGHASH_SINGLE|ANYONECANPAY signing fails on reserve-currency-only cryptocondition inputs.** The Verus signer can't compute the pairing SIGHASH when Input 0 has zero VRSC value (only reserve currency). Default SIGHASH_ALL signing works fine on the same input.

**Validated cooperative-settlement fallback:**
- Tx: `a454afc256a2436e379c11b4708279579f8fcb53f898da5d973c225412fce899`
- Inputs: vault 5 DAI + Alice's 0.9999 VRSC (for strike + fee)
- Outputs: 0.55 VRSC → Bob (strike), 5 DAI → Alice (collateral return), 0.4498 VRSC → Alice (change)
- Both parties signed at settlement time with default SIGHASH_ALL
- Confirmed cleanly

**Final state:**
- Vault: 5 DAI consumed
- Bob: +0.55 VRSC (effective interest: -0.5 VRSC principal + 0.55 VRSC repayment = +0.05 VRSC)
- Alice: collateral returned in full, paid 0.05 VRSC interest

**Spec implications:**

- ✅ Cross-currency loans with **VRSC collateral + non-VRSC principal/repayment** = works fully (§18-§21)
- ⚠️ **Non-VRSC-only collateral** = settlement requires cooperative SIGHASH_ALL (both parties online) — loses the unilateral-broadcast property of the canonical primitive
- ❌ **Profile L vault + non-VRSC collateral** = impossible (non-standard output rejected at broadcast)
- ❌ **Tested workaround that does NOT work:** mixed-currency vault output (0.01 VRSC + 1 DAI) at i-address vault `i6ebreh...`, tx `d4d518f6e814cd1df8bee421f2f593cedcf88661ed9ff6b05f4de9cdb3ca2dec`. Attempted SIGHASH_SINGLE|ANYONECANPAY signing with VRSC value in the output → still fails with `Opcode missing or not understood`. The issue is the reserve-transfer cryptocondition opcode itself, not the input's VRSC value. **Adding dust does not unlock async pre-sign for reserve-currency vaults.**

For the canonical loan design, the recommendation is unchanged: **collateral in VRSC, principal/repayment in any currency**. This matches all existing validated tests (§16-§30).

### 32. H1 corrected: non-VRSC collateral DOES work with SIGHASH_SINGLE|ANYONECANPAY

**Correction to §31's conclusion.** The earlier finding that "SIGHASH_SINGLE|ANYONECANPAY fails on reserve-currency-only cryptocondition inputs" was a tooling bug, not a protocol limitation.

**Discovery:**

`signrawtransaction` has two key-handling paths:
- **Explicit privkey path** (when `privkeys` is a non-empty array, e.g. `["KxWVD..."]`): fails for cryptocondition reserve-transfer inputs with `Opcode missing or not understood`. The signer evaluates the prevtx scriptPubKey to determine signing requirements and doesn't understand the reserve-transfer cryptocondition opcode.
- **Wallet key-lookup path** (when `privkeys` is `null` or omitted): the wallet associates input scriptPubKeys to addresses to keys directly. Works correctly on cryptocondition reserve-transfer inputs.

The earlier §31 tests passed `[]` (empty array) and `["..."]` (explicit), both of which take the explicit path and fail. Passing `null` instead routes through the wallet's key-lookup path which handles the cryptocondition correctly.

**Validated mainnet:**

Setup: same vault `i6ebrehQ6dyJGjy8LoxkaPfJ2Vo7dXGbHy` (2-of-2 [Alice, Bob], null revoke/recover) holding the mixed-currency UTXO from §31 (`d4d518f6...` vout 0 = 0.01 VRSC + 1 DAI).

**Pre-sign Tx-Repay-style template:**
- Input 0: vault's mixed-currency UTXO (cryptocondition with reserve transfer)
- Output 0: 0.005 VRSC → Bob (sig-locked, the strike)
- Both Alice (local) and Bob (.44) signed Input 0 with `SIGHASH_SINGLE | SIGHASH_ANYONECANPAY` using `signrawtransaction <hex> 'null' 'null' "SINGLE|ANYONECANPAY"` — both reported `complete: True`

**Extended and broadcast (no further signing needed):**
- Output 1: 1 DAI → Alice (collateral return)
- Output 2: 0.0049 VRSC → Alice (change)
- Tx: `086fb3eebfe31ef2b3191d5d2f7c48f615988700403ac68d8fdb37c779d985c1`
- Confirmed cleanly

**Validates:**
- ✅ Reserve-currency cryptocondition vault inputs CAN be pre-signed with `SIGHASH_SINGLE | ANYONECANPAY` via the wallet key-lookup path
- ✅ Non-VRSC collateral works with the canonical async-pre-sign primitive
- ✅ The protocol's load-bearing properties (lender-offline-at-repayment, broadcaster-pays-fee, sig-locked Output 0) all hold for non-VRSC collateral in Profile V vaults
- ✅ Profile V (i-address vault) is the correct choice for non-VRSC collateral; Profile L (p2sh) remains unable to hold reserve currencies due to non-standard output rejection

**Spec updates:**
- SPEC §9 currency-support section corrected
- §31's earlier "VRSC-only collateral" recommendation reversed
- The clean position is now: **any Verus currency works as collateral if using Profile V vault**

### 33. Marketplace data layer — loan offer published & cross-node readable

Demonstrates that the **chain itself is the marketplace**. A loan offer is a `loan.offer.v1` entry in a VerusID's contentmultimap. Anyone with a Verus node can read it via `getidentity` — no server, no API, no centralized index needed.

**Setup:**
- VDXF key for `loan.offer.v1`: `iDDdeciNHuSiggfZrquEBJAX5TUxkm2Sgy` (generated via `getvdxfid "loan.offer.v1"`; namespace defaults to VRSC chain)
- Test ID: `i44CxABWkVnUhoPMjuM2ViJDDu2icd7jg7` (a controllable VerusID with empty multimap, primary RUd7fPjUYj27qTjamieXAYiJ2NcSVCBekF)

**Offer payload (hex-encoded JSON in the multimap entry):**
```json
{
  "version": 1,
  "type": "lend",
  "principal": {"currency": "VRSC", "amount": 5},
  "collateral": {"currency": "VRSC", "amount": 10},
  "rate": 0.10,
  "term_days": 30,
  "lender_pubkey": "0270b46dc0dcfe28b35cbd76ba54c5560c88b64b80ebc3cf515b7035b0891c8250",
  "lender_address": "RHze1kkgaWkLzXtu3wB8kAN6UJe7GLzqG8",
  "valid_until_block": 4070000,
  "active": true
}
```

**Write to chain:**
- `updateidentity` with `contentmultimap = { "<vdxf_id>": ["<hex_blob>"] }`
- Tx: `694ed5cfc13d4fb0234d7fa2759a336b163c59b42ee0b71581ff816062bb00a8`
- Confirmed cleanly

**Cross-node readability validation:**
- Read from local node: ✅ same JSON returned
- Read from .44 (independent node, different physical location): ✅ same JSON returned

**Validates:**
- ✅ The contentmultimap is the marketplace data layer — no separate server required
- ✅ Anyone with a Verus node can discover offers via `getidentity`
- ✅ VDXF keys provide canonical schema addressing (anyone computing `getvdxfid "loan.offer.v1"` gets the same key)
- ✅ Hex-encoded JSON in the multimap entry is the simplest viable encoding
- ✅ Offers are public, queryable, censorship-resistant

**What this means architecturally:**

The protocol doesn't need a marketplace operator. The **explorer's role is rendering, not gatekeeping** — every wallet can implement its own discovery/filtering on top of the same chain data. Any explorer, marketplace, or wallet can show the same set of offers because they're all reading from the same chain.

Combined with §13 (reputation) and §13.1 (encrypted multimap), the protocol's full lifecycle — discovery, ceremony coordination, settlement, reputation — runs entirely on chain. No off-chain infrastructure required.

### 34. Cross-currency `makeoffer`/`takeoffer` validated for pure-CLI atomic swap

Validates that Verus's marketplace primitive (`makeoffer` + `takeoffer`) handles cross-currency atomic swaps via pure CLI. This is the same SIGHASH_SINGLE|ANYONECANPAY primitive as our protocol, exposed via marketplace RPCs that handle extension natively (no helper script needed).

**Setup — Bob offers VRSC for DAI:**
```
makeoffer "RHze..." '{
  "changeaddress": "RHze...",
  "offer": {"currency": "VRSC", "amount": 0.05},
  "for":   {"address": "RHze...", "currency": "DAI.vETH", "amount": 0.1}
}'
```

**Result:** offer broadcast tx `4baf95df0cec9fd415fa3daf8c1ee0853219606d460982bec0cc71f4552e2940`.

**Take by txid (Alice on local node):**
```
takeoffer "RJ6Xejo..." '{
  "changeaddress": "RJ6Xejo...",
  "txid":   "4baf95df0cec9fd415fa3daf8c1ee0853219606d460982bec0cc71f4552e2940",
  "deliver": {"currency": "DAI.vETH", "amount": 0.1},
  "accept":  {"address": "RJ6Xejo...", "currency": "VRSC", "amount": 0.05}
}'
```

**Result:** take tx `f2ce9faa20c72bb46d3678bde5f8f2a81eb600af2cc73c61d7e5656ea3875c7a`, confirmed in block `000000000000e8bac9180f2a5a493b686eba792bc3b488f833ba076f2923267c`.

**Final state:**
- Bob: +0.1 DAI received (the FOR clause)
- Alice: +0.05 VRSC received (the OFFER clause)
- Atomic, single tx

**Validates:**
- ✅ Cross-currency atomic swaps work via marketplace RPCs
- ✅ Pure CLI sufficient (no Python helper, no extend_tx.py)
- ✅ `takeoffer` handles tx extension natively when offer is on chain (taken by txid)
- ✅ Same primitive as our SIGHASH_SINGLE|ANYONECANPAY — exposed via marketplace API

**One important caveat:**
- ❌ `takeoffer` with the `tx:<hex>` form (off-chain offer hex) returned `mandatory-script-verify-flag-failed` on broadcast. The on-chain path (broadcast offer first, take by txid) was required. Off-chain hex passing requires further investigation or possibly the on-chain path is canonical.

**Implication for the protocol:**

For atomic swaps with single-party-signed inputs (origination Tx-O, default Tx-B, rescue Tx-C), `makeoffer`/`takeoffer` is a viable pure-CLI implementation. For Tx-Repay specifically — where the input is a 2-of-2 vault and both parties pre-sign at origination — the marketplace primitive doesn't directly support multi-sig pre-commitment.

A small Verus core enhancement (`cosignoffer` RPC, `extendrawtransaction` RPC, or `makeoffer` with optional privkeys param) would unlock pure-CLI Tx-Repay too. See [DEV_ASK.md](./DEV_ASK.md).

### 35. Finding: makeoffer's expiryheight does NOT gate the take window

Tested whether `makeoffer`'s `expiryheight` parameter prevents `takeoffer` after that block height. **It does not** — `expiryheight` on makeoffer is the offer-tx's broadcast expiry, governing when the offer tx itself can be admitted to mempool. After confirmation, the offer's outputs are spendable (takeable) indefinitely until taken or `closeoffers` cancels them.

**Setup:**
- Bob's offer with `expiryheight = current+5` (block 4050458): tx `35c90cce02d98bd6d9ce069833eccb9638015e47c6bf39fffa51693252d0bdb0`
- Confirmed before its expiryheight

**Test:**
- Waited until block 4050460 (past offer's expiryheight 4050458)
- Alice ran `takeoffer` with the offer's txid
- Result: **take succeeded**, tx `190c80ad4aa6127cccb56f25828b348c7556815fa804bc78c8999151a13523f6` confirmed in block 0000000000001dcc95b0ce8d0be4fccfbad85975eb8328f2df3d404a7af4946a

**Implications:**
- Stock `makeoffer` cannot natively express "this offer auto-expires at block X" semantics
- Marketplace offers are takeable until taken or canceled, regardless of their tx-creation expiryheight
- For options markets requiring true expiration, use 2-of-2 vault + pre-signed exercise tx with `expiryheight` (validated §26-§27) — that's the working mechanism for time-limited exercise rights
- Or use `expiryheight` on the OFFER TX itself + accept that the offer simply broadcasts late from a stale hex (limited utility)

This caveats the "trusted-seller options via stock makeoffer" framing in earlier conversation. For real options markets with expiration, the protocol's 2-of-2 vault + pre-signed exercise tx is the correct mechanism.

### 36. Atomic premium-plus-option-creation pattern

Validates that `takeoffer`'s `accept` field can deliver to a 2-of-2 vault address (not just a buyer's R-address). This unlocks an atomic premium-plus-option-creation primitive: in a single tx, premium goes to seller AND underlying lands at vault. No separate premium-then-deposit sequence.

**Setup:**
- Bob's offer: `6960174a51a57afa6eee14cc8298c251561260f4cadcbcf787e4cb5e02c3fcba` — GIVE 0.05 VRSC, FOR 0.05 DAI to seller
- Alice's takeoffer with `accept.address = bYCcAqB7KfdkfsN8YUipb2fuFhKvxmsnne` (the 2-of-2 vault)

**Result:**
- Tx: `c419b7fcc001a9e6993112be1e6e6d817928beda9a86867d57a840592ff0bb3c`
- Confirmed in block `000000000001a8a2c049615dfc131c2a775c20b870d71dd30e70307dade05eb5`
- vout 0: 0.05 DAI → seller (premium delivered)
- vout 1: 0.05 VRSC → vault (underlying locked at 2-of-2)
- vout 2: change

Vault balance increased from 4.0 to 4.05 VRSC. Atomic. Pure stock CLI.

**Validates:**
- ✅ takeoffer's `accept` accepts p2sh vault addresses (not just R-addresses)
- ✅ Atomic premium-plus-option-creation pattern works on stock Verus CLI
- ✅ Eliminates the "buyer pays premium first, seller doesn't deliver" trust risk
- ✅ Combined with pre-signed exercise/return txs (§26-§27), enables a fully-trustless options market: chain enforces both premium handling AND no-rug-pull

**Practical implication:**

For options markets, the recommended pattern is:
1. **Setup phase**: cooperative atomic tx via makeoffer/takeoffer with vault as accept address — premium → seller, underlying → vault. **Pure stock CLI.**
2. **Pre-signed exercise + return**: cooperative pre-sign of the settlement templates with `SIGHASH_SINGLE | ANYONECANPAY` — needs the wallet key-lookup signing path (§32). Pure CLI.
3. **Exercise broadcast**: borrower extends template with strike input. **Needs extension helper** (same gap as Tx-Repay).
4. **Expiration recovery**: seller extends underlying-return template with fee input. **Needs extension helper** (same gap as Tx-B).

Three of four phases are pure stock CLI. One gap remains — the same gap as the lending protocol's Tx-Repay.

## What remains untested (conservative assumptions)

- Behavior of pre-signed transactions across chain reorganizations (G1–G3)
- Behavior when input 0 (borrower's funding input) is added at repayment time vs included as a placeholder at origination — assumed equivalent per ANYONECANPAY semantics
- Cross-chain loan denominations involving Verus PBaaS bridges
- Race-at-maturity-boundary (C1) — Tx-Repay and Tx-B broadcast simultaneously, first miner wins
- Death/inheritance scenarios (E1–E6) — primarily about wallet UX, not protocol mechanics
- Non-VRSC collateral in practice (H1) — should work per the cross-currency results in §18-§21 but not directly tested with e.g. tBTC.vETH as collateral
- D3 (broadcaster adds extra outputs to steal extra value) — argued safe by accounting (tx must balance, broadcaster's added inputs must fund their added outputs). Not directly tested.

### 37. End-to-end GUI scenario suite (v3 protocol, Playwright on mainnet)

A 9-scenario Playwright harness drives the borrower + lender GUIs end-to-end on Verus mainnet, exercising the full v3 protocol surface. The harness lives at [`verus_contract_gui/test/e2e_v3_scenarios.mjs`](https://github.com/Fried333/verus_contract_gui/blob/main/test/e2e_v3_scenarios.mjs) (mirror of `app/` in this repo).

Setup: borrower GUI on `http://127.0.0.1:7777` with local daemon (controls `i7b7Tq8JYXX9iqS7FBevC6LaG3ioh8z3RM`); lender GUI on `:7778` reverse-tunneled to a remote daemon (controls `i7A9fa8c3xZnA3uLK3SLYa58cUipganewg`). Both wallets hold real funds; every scenario broadcasts.

**Scenarios validated:**

| # | Name | What it validates |
|---|------|-------------------|
| 1 | happy path | request → match → auto-accept (Tx-A broadcast) → repay (Tx-Repay) → vault drained |
| 2 | borrower cancels request | post request → click Cancel → multimap purged + UTXO unlocked |
| 3 | lender cancels match | request → match → click Cancel match → multimap purged |
| 4 | manual accept | `auto_accept=false` → borrower clicks Accept → loan opens → repay |
| 5 | repay with localStorage missing | repay handler recovers Tx-Repay from `loan.status.tx_repay_signed` on chain |
| 6 | repay double recovery | localStorage AND `loan.status.tx_repay_signed` cleared → falls through to lender's `match.tx_repay_partial` and re-cosigns |
| 7 | match safety probe | `verifyMatchSafety` is window-exposed for unit testing of corrupted match payloads |
| 8 | lender insufficient principal | GUI shows insufficient warning, no Confirm button |
| 9 | borrower insufficient collateral | Preview & sign disabled, validation message shown |

Each scenario passed end-to-end on mainnet with real fees, real confirmations. Scenario 1 (happy path) typically completes in ~5–8 minutes; scenarios that wait for the explorer's `/contracts/loans` view (3–6) can take longer because that endpoint is confirmed-state-only.

**Observations from running the suite that fed back into the spec / GUI:**

1. **Multimap script-element size limit.** Verus enforces a per-stack-element cap on `updateidentity` payloads. Once `loan.history` accumulated ~5–6 entries (≈5.7 KB hex), the daemon rejected updates with `bad-txns-script-element-too-large`. Implication for the spec: **history must be trimmed**, either by the writer or by a periodic compaction transaction. The test harness drops history between scenarios for this reason. SCHEMA does not currently specify a retention policy.

2. **Identity-update mempool serialization.** A second `updateidentity` on the same identity while the previous is unconfirmed gets rejected by the daemon. More subtly, the wallet's coin selection may pick a UTXO from the in-flight tx, producing `bad-txns-inputs-spent` even if the second update wouldn't conflict at the multimap level. The harness gates on `confirmed.txid === tip.txid` AND empty mempool deltas on the identity's funding R-address before issuing any update. A wallet that wants to enqueue rapid identity updates needs the same gate.

3. **Address-index lag for repay-balance checks.** `getaddressbalance` is confirmed-only; right after Tx-A is broadcast the borrower's R-address shows the pre-Tx-A balance and the GUI's `have ≥ repay` check fails. The fix is to sum `getaddressutxos` (confirmed) **plus** `getaddressmempool` (mempool deltas) — what's now wired into `enrichActiveLoanBalances`. The pattern generalizes: any "do you have enough yet" check on a freshly-spent address must include mempool deltas.

4. **Auto-accept watcher must open the panel before clicking Confirm.** The match row's outer "Accept this loan" button populates the `.accept-panel` async (after fetching request terms from the explorer / local daemon); only then does the inner `[data-mp-row-act="accept-v2"]` Confirm button render. The watcher previously raced ahead and queried for the inner button immediately after `loadMarket()`, never finding it. Fixed by clicking the outer Accept then polling for the inner Confirm.

5. **Explorer's `posted_tx` references the latest identity revision, not the txid that introduced the entry.** The lender's `match.request.txid` was originally pinned to `posted_tx`. Each subsequent borrower-side identity update advances `posted_tx`, so a stale match referenced a revision that no longer carried the loan.request payload, breaking the borrower's accept flow. `matchKey` is now `match-{match_iaddr}-{request.iaddr}` instead.

6. **Cooperative vault recovery is the right cleanup for half-finished tests.** When a scenario fails after Tx-A confirms but before Tx-Repay broadcasts, the vault holds the borrower's collateral. A pre-signed Tx-Repay would settle this, but if the test harness corrupted state (cleared loan.status, dropped match) the GUI can't reconstruct it. `recover_vault.sh` does the cooperative path: borrower sends repay to lender via `sendcurrency`, then both parties sign a fresh vault drain. Idempotent — exits 0 if the vault is empty.

### 38. Chain-only recovery (e2e scenario 12)

Validates the audit-trail fallback when the live multimap has been wiped: the borrower's GUI walks `getidentityhistory` for prior `loan.match` revisions on the lender's identity, finds the last revision with `tx_repay_partial` matching the active `loan_id`, re-cosigns the borrower's vault-half from scratch, and broadcasts.

**Setup:** open a fresh loan, then:
- wipe lender's `loan.match` (entire VDXF key removed via `updateidentity`, other keys preserved)
- strip `tx_repay_signed` from borrower's `loan.status` (keep the entry so the loan card still renders)
- clear borrower's localStorage `vl_tx_repay_<loanId>`

The tier 4 / tier 4.5 fallback in the repay handler (main.js:4305 + 4368) walks identity history. Validated end-to-end on mainnet — repay completes without any live-multimap copy of the partial.

**Implication for SCHEMA `loan.template`:** the encrypted-self backup primitive is unnecessary. All settlement-path data (vault address, redeem script, partials) is recoverable from chain via past identity revisions. SCHEMA's "encrypted (self)" loan.template note can be relaxed or dropped.

### 39. Replay safety across loans on a reused vault (e2e scenario 13)

Vault P2SH is deterministic from `(borrower_pubkey, lender_pubkey)`, so the same address services every loan between the same pair. We tested whether old settlement txs from past loans can be replayed against fresh vault UTXOs.

**Test:** walk borrower's `getidentityhistory` for a past `loan.history(outcome=repaid)` entry. Fetch the actual broadcast Tx-Repay raw hex via `getrawtransaction <tx_repay_txid>`. Try to rebroadcast against current chain.

**Result:** rejected with **`tx-expiring-soon`** (`expiryheight is X but should be at least Y to avoid transaction expiring soon`). Verus's `expiryheight` field caps the reuse window to ~20 blocks — old Tx-Repays from days/weeks-ago loans can't be rebroadcast at all.

**Two independent layers of replay protection:**

1. **Verus `expiryheight`** (validated): every Tx-Repay carries an expiryheight set ~20 blocks ahead of broadcast time. After that height, the daemon refuses the tx outright. Replay window is small enough that even within-window replay needs the vault UTXO to still exist.
2. **Spent-input commitment** (logical, not directly tested): even if expiryheight allowed it, the Tx-Repay's signature commits to a specific `(vault_txid, vault_vout)` via SIGHASH_SINGLE\|ANYONECANPAY. Once that UTXO is consumed by the original Tx-Repay, no other tx can spend it. Replacing the input with a fresh vault UTXO from a different Tx-A invalidates the signature.

**Implication for SPEC:** vault P2SH reuse between the same parties is safe. No need for per-loan vault randomization (option C tweaked-key scheme reverted in `verus_contract_gui` commit `e329954` was overcautious). Determinism is fine.

### 40. Lender decline — public "polite no" via loan.decline

Validates the marketplace UX flow where a lender publicly declines a borrower's request instead of silently ignoring it. Reserves VDXF id `iEgciB3u2GwTxzShQR4eFhtj4k8Zv6frNb` for `make.vrsc::contract.loan.decline`.

**Test (e2e scenario 14):** borrower posts request with `auto_accept=false` and `target_lender_iaddr=lender`. Lender's GUI renders the Fund panel automatically. Lender clicks **Decline** instead of **Confirm**. Asserts:

- Lender's identity gets a fresh `loan.decline` entry pointing at borrower's `request_txid`
- All other VDXF keys on lender's identity (offers, etc.) preserved (read-modify-write)
- Borrower's loan.request stays unchanged on chain (lender has no authority to write to borrower's identity)
- Borrower-side decline watcher (30s poll on each `target_lender_iaddr` in borrower's active requests) finds the new entry
- Borrower's GUI surfaces a yellow banner: *"Lender X declined your request — try another lender or adjust terms"*

**Result:** passed in 73 seconds end-to-end on mainnet — well under one block of typical confirmation lag, indicating the new mempool-merge path in `fetchMarketBundle` (poll counterparties via `getidentity -1`) successfully bypassed the explorer's confirmed-only `/contracts/loans/requests` view.

**Design notes:**

- `loan.decline` is a **UX signal, not a cryptographic veto.** The borrower can still re-target a different lender or adjust terms; nothing about the chain prevents that. The banner is a courtesy nudge.
- The borrower's request is not auto-cancelled on decline. Other lenders can still match it. Decline is per-lender, not protocol-level termination.
- Same retention pattern as `loan.history` — live multimap holds the latest decline as a beacon; older entries persist in past identity revisions.

**Implication for SCHEMA:** the existing `loan.template` "encrypted (self)" backup primitive (§37 marked as unused) can be formally deprecated. All settlement data is recoverable from past identity revisions (proven by §38 chain-only recovery scenario).

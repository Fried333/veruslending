# VerusLending — Scenario Test Matrix

Goal: enumerate every protocol scenario (happy, default, deaths, hex loss, adversarial, race, reorg, rescue) and validate each end-to-end on Verus mainnet with a fresh loan per test. State is reset between tests.

This document is in draft form. The tests below are the plan; checkmarks indicate the ones already validated on mainnet (with txids in TESTING.md and the table at the top of this doc once filled in).

## Setup axes

A scenario is parameterized along these dimensions. Each test fixes one combination.

| Axis | Values |
|---|---|
| **vault flavor** | `verusid` (2-of-2 + null revoke/recover) — `p2sh` (2-of-2 multisig script) |
| **Currency** | `vrsc-only` — `cross-currency` (e.g. VRSC collateral + DAI principal) |
| **Fee model** | `collateral-pays` — `broadcaster-pays` |
| **Tx-Repay sighash** | `SIGHASH_SINGLE\|ANYONECANPAY` (canonical) |
| **Tx-B sighash** | `SIGHASH_ALL` (collateral-pays) — `SIGHASH_SINGLE\|ANYONECANPAY` (broadcaster-pays) |
| **Tx-C sighash** | TBD — likely `SIGHASH_SINGLE\|ANYONECANPAY` for symmetry |

The protocol's *correctness* shouldn't depend on these choices, but each combination has subtly different UX and resource flows. We test the boundary cases.

---

## Scenario list

### A. Settlement scenarios — happy paths

- **A1**. Alice repays normally, collateral-pays fee. ✅ §16, §A (today's p2sh).
- **A2**. Alice repays, broadcaster (Alice) pays fee, collateral fully returned. ✅ §C (today).
- **A3**. Alice repays at the last possible block before maturity. (Edge of timing.)
- **A4**. Alice repays, then Bob *also* attempts to broadcast Tx-B (post-locktime). Tx-B should fail because the collateral UTXO is already consumed.

### B. Settlement scenarios — default paths

- **B1**. Alice never broadcasts; Bob broadcasts Tx-B at maturity+grace, collateral-pays fee. ✅ §17, §B (today's p2sh).
- **B2**. Alice never broadcasts; Bob broadcasts Tx-B, broadcaster (Bob) pays fee, collateral fully claimed. ✅ §D (today).
- **B3**. Bob doesn't broadcast Tx-B even after maturity+grace. Collateral stays in p2sh until Tx-C is broadcast.
- **B4**. Alice tries to broadcast Tx-Repay AFTER Bob already broadcast Tx-B. Should fail (UTXO already spent).

### C. Race conditions

- **C1**. Alice and Bob simultaneously broadcast Tx-Repay and Tx-B at maturity. First miner wins; the other tx becomes invalid. (Tests double-spend handling.)
- **C2**. Alice broadcasts Tx-Repay BEFORE Tx-A confirms (chained mempool). Should propagate. ✅ implicitly validated today (Test A — both txs in mempool, mined same block).
- **C3**. Pre-locktime broadcast attempt for Tx-B. Must reject as `64: non-final`. ✅ validated today.
- **C4**. Pre-locktime broadcast attempt for Tx-C. Must reject.

### D. Adversarial / signature integrity

- **D1**. Alice tries to redirect Output 0 (Bob's payment) to a different address. Signature on Input 0 should fail validation.
- **D2**. Alice tries to reduce Output 0's amount (claim partial repayment satisfies). Signature should fail.
- **D3**. Bob tries to claim more than Output 0 in Tx-B (e.g., adds extra outputs to himself paying from collateral). With SIGHASH_SINGLE|ANYONECANPAY (Test D variant), Output 0 is locked; can he add Output 2 also stealing more? This needs careful test.
- **D4**. Third party in mempool tries to insert their own input into Tx-Repay (front-running). Should fail because their input's added scriptSig wouldn't satisfy any output binding.
- **D5**. Either party tries to spend the collateral via a brand-new tx (not Tx-Repay or Tx-B). Should fail because they only have 1-of-2 sig.

### E. Death / key loss / hex loss scenarios

- **E1**. Lender dies before maturity. Borrower broadcasts Tx-Repay normally — Bob's pre-sig is sufficient. Lender's estate inherits the principal payment via Bob's wallet seed.
- **E2**. Borrower dies before repayment. Tx-Repay hex preserved in her estate. Estate broadcasts Tx-Repay (using Alice's funding-input keys from her wallet) — settlement completes. Estate gets collateral back.
- **E3**. Borrower dies AND Tx-Repay hex is lost. Forced default → Bob broadcasts Tx-B at maturity. Borrower's estate loses collateral but keeps principal she'd already spent.
- **E4**. Lender dies AND Tx-B hex is lost. If Alice doesn't repay, collateral is stuck until Tx-C is broadcast (assuming Tx-C was set up).
- **E5**. Both die. If both hex preserved by estates → normal flow possible. If both hex lost → Tx-C is the only escape (if pre-signed).
- **E6**. Borrower's *funding-input keys* are lost but Tx-Repay hex preserved. She can broadcast Input 0 alone, but cannot add the funding inputs needed to make tx balance. Forced default.

### F. Tx-C (rescue) scenarios

- **F1**. Both parties cooperate mid-term to abandon, but rather than build a custom tx, they wait for Tx-C's far-future nLockTime. (Slow path.)
- **F2**. Tx-C broadcast after nLockTime by the borrower (recovers collateral). Cross-currency variant.
- **F3**. Tx-C with broadcaster-pays-fee (same SIGHASH_SINGLE|ANYONECANPAY mechanic as Tx-Repay/Tx-B).

### G. Reorg scenarios

- **G1**. Tx-A and Tx-Repay both confirmed in same block; that block gets reorged. Both txs return to mempool, re-mine cleanly.
- **G2**. Tx-A in block X confirms; Tx-Repay broadcast and confirms in block X+1; block X+1 gets reorged. Tx-Repay returns to mempool, can be re-mined.
- **G3**. Adversarial reorg attempt: Bob tries to broadcast Tx-B during a reorg window where Tx-Repay's confirmation got knocked out. (Mostly theoretical — Tx-B has nLockTime requirement so this only matters near maturity.)

### H. Cross-currency edge cases

- **H1**. Collateral in non-VRSC token (e.g., tBTC.vETH). Broadcaster supplies VRSC for fee. Collateral returns intact in tBTC.
- **H2**. Repayment in a third currency (different from collateral and from initial principal). E.g., collateral VRSC, principal DAI, repayment in tBTC. (Stretch test; not required.)
- **H3**. Output 0 has a *currency conversion* operation (`convertto:`). Validates whether SIGHASH locking still binds correctly through a conversion. (Stretch.)

### I. vault flavor variations

- **I1**. Same scenarios run with VerusID vault instead of p2sh, to confirm parity. Most validated already in §16/§17.
- **I2**. VerusID vault with multimap-stored encrypted hex backup. Tests the "lose your laptop, recover from seed" UX. (Wallet feature; not chain feature.)

---

## Reset procedure between tests

For p2sh-flavor tests:
- p2sh address is purely deterministic from pubkeys; no on-chain reset needed.
- Just use a fresh collateral UTXO. (Each Tx-A creates a new one.)

For VerusID-flavor tests:
- After test, if vault is no longer needed, can leave it (2-of-2 idle is fine).
- For a fresh test, register a new sub-ID or reuse one already in 2-of-2 + null state.

For both flavors:
- Track funding for both Alice and Bob: if one runs low, send from RKirf (DAI) or any wallet (VRSC).
- Document each test's txids in TESTING.md.

---

## Execution priority

These are the 12 highest-leverage tests, ordered by what we should run first. Skip duplicates of what's already validated.

| Order | Test | Why |
|---|---|---|
| 1 | A4 | Verifies that broadcasting Tx-Repay invalidates Tx-B (UTXO consumption) |
| 2 | B3 | Validates Tx-B never broadcast → collateral stuck behavior, sets up Tx-C tests |
| 3 | B4 | Bob's Tx-B fails after Alice already repaid (mirror of A4) |
| 4 | F1/F2/F3 | Tx-C rescue flow (we have NOT tested Tx-C yet on mainnet at all) |
| 5 | D1, D2 | Verify signature commitments on Output 0 actually hold under tampering |
| 6 | D3 | Critical: with SIGHASH_SINGLE\|ANYONECANPAY on Tx-B, can broadcaster steal extra? |
| 7 | C1 | Race between Tx-Repay and Tx-B at exact maturity boundary |
| 8 | E2 | Key continuity — broadcaster's funding-input keys inherited correctly |
| 9 | E6 | Borrower hex preserved but funding key lost — test forced-default path |
| 10 | H1 | tBTC.vETH (or another non-VRSC) as collateral |
| 11 | G1 | Reorg recovery — harder to artificially trigger; document reasoning instead |
| 12 | I1 | One full VerusID-flavor run for parity confirmation |

D3 is the spec-critical test — if SIGHASH_SINGLE\|ANYONECANPAY allows Bob to add additional outputs paying himself from collateral, that's a vulnerability we need to know about and probably a reason to require Tx-B to use plain SIGHASH_ALL (and accept the small fee erosion).

## Open spec questions surfaced by this matrix

1. Should the canonical Tx-B use `SIGHASH_ALL` (no broadcaster-pays-fee) or `SIGHASH_SINGLE|ANYONECANPAY`? D3 may decide this.
2. What's the canonical Tx-C structure? nLockTime far in future (1 year?), output structure (back to borrower? both parties? split?), sighash discipline?
3. For non-VRSC collateral, should the spec mandate a tiny "fee-budget" output in Tx-A so the broadcaster doesn't have to scrounge for VRSC at settlement time?

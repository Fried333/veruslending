# VerusLending

A peer-to-peer collateralized credit protocol on Verus.

## In one sentence

Two private parties enter a binding loan agreement on chain, with cryptographic enforcement of repayment, default, and rescue paths — no arbiter, no committee, no third-party intermediary, no liquidation bots.

## In one paragraph

VerusLending is a credit primitive built from existing Verus features: 2-of-2 multisig identities, atomic raw transactions, and pre-signed time-locked transactions using SIGHASH_ANYONECANPAY. At origination, both parties cooperatively create a Loan-ID holding the borrower's collateral, plus three pre-signed transactions: one for the borrower's atomic repayment (held privately by the borrower, broadcast unilaterally at any time during the loan term), one for the lender's default-claim at maturity+grace, and one for the borrower's last-resort rescue. The lender's pre-commitment at origination is irrevocable — the borrower can settle without any live cooperation from the lender. Lender stonewalling is structurally impossible. Subjective disputes go to real-world courts with the chain record as admissible evidence.

## What's here

- **[SPEC.md](./SPEC.md)** — formal protocol specification (validated)
- **[TESTING.md](./TESTING.md)** — empirical test results from Verus mainnet, with txid references
- **[LICENSE](./LICENSE)** — MIT

## Status

**Spec is empirically validated.** Every load-bearing mechanism was tested on Verus mainnet during design. Reference wallet implementation is future work.

| Mechanism | Status |
|---|---|
| Loan-ID structure (2-of-2 multisig) | ✅ validated |
| Atomic origination (raw multi-party tx) | ✅ validated |
| **Pre-signed Tx-Repay (SIGHASH_ANYONECANPAY)** — canonical | ✅ validated |
| Default claim (Tx-B with nLockTime) | ✅ validated |
| Borrower's rescue (Tx-C structurally identical to Tx-B) | ✅ validated by extension |
| Optional panic button (revoke invalidates Tx-B) | ✅ validated |
| Front-run protection (no offer ever in mempool) | ✅ structural |

See [TESTING.md](./TESTING.md) for txid references.

## Why it matters

This is what private secured lending looked like before banks: two parties, a notarized agreement, time-based defaults. Existing crypto lending products that work today (Ledn, Unchained, Arch) re-create that model with corporate operators. VerusLending re-creates it with cryptographic enforcement instead — the chain is the notary, the parties are themselves, and the lender's commitment is enforced by signature mechanics rather than by external accountability.

The protocol is intentionally minimal:

- No on-chain dispute resolution (use courts; chain provides evidence)
- No oracle dependency (no margin calls, no liquidation bots)
- No protocol-controlled treasury or fee
- No DAO governance
- No proprietary token

## Use cases

- Peer-to-peer Bitcoin/VRSC-collateralized loans between known parties
- Collateralized swaps within communities (members lending to other members)
- Private loans between businesses or individuals who already have a trust relationship
- Reputation-bonded lending in identity-aware communities

## What it is NOT for

- Lending to anonymous strangers without external trust mechanisms
- High-frequency margin trading
- Public lending platforms with retail users (regulatory complications)
- Variable-rate or amortizing loans (Tx-Repay outputs are fixed at origination)

## Architecture summary

```
Origination ceremony (one-time, cooperative):
  Tx-A:       atomic origination — collateral → Loan-ID, principal → borrower
  Tx-Repay:   pre-signed atomic repayment template (SIGHASH_ANYONECANPAY)
              Held privately by borrower
              Borrower can broadcast unilaterally any time before maturity
  Tx-B:       pre-signed lender's default-claim (nLockTime = maturity + grace)
              Held by lender; broadcast at maturity if no Tx-Repay broadcast
  Tx-C:       pre-signed borrower's last-resort rescue (nLockTime = maturity + 1 year)
              Held by borrower; rare fallback

Loan-ID:
  primary: 2-of-2 [borrower, lender]
  revocation: borrower (optional safety net)
  recovery: 2-of-2 [borrower, lender]

Repayment (canonical):
  Borrower's wallet appends funding inputs to Tx-Repay template
  Borrower signs the new inputs with SIGHASH_ALL
  Borrower broadcasts → atomic settlement
  Lender does not need to sign anything at repayment time

Default:
  Borrower never broadcasts Tx-Repay
  Lender broadcasts Tx-B at maturity + grace

Lender disappeared:
  Borrower broadcasts Tx-Repay normally — pre-signature is sufficient
  No reliance on lender being alive or available
```

See [SPEC.md](./SPEC.md) for the full protocol.

## Relationship to other Verus lending efforts

This protocol is a **peer-to-peer fixed-term primitive**. It's complementary to other lending models the Verus ecosystem may support:

- **Basket-based pool lending** (a future Verus direction): currency baskets become lending pools with dynamic interest rates based on collateral/loan ratios; LPs earn fees by holding basket tokens; margin call enforcement via import rollup or validator-incentivized redemption. Best fit for retail / anonymous / market-rate lending. This is a different model than VerusLending — they serve different use cases.

- **Template outputs** (a future Verus feature): non-spending outputs that act as cross-tx constraints requiring a matching companion output with specified fields. When this lands, it would simplify some of the patterns we currently express via SIGHASH manipulation, and could enable cleaner Loan-ID-makes-offer designs that solve the empty-Pay-ID problem we encountered during testing.

VerusLending serves the use case where two known parties want to enter a private, fixed-term, fixed-rate loan with cryptographic atomic settlement. Mike's basket-based lending vision would serve the use case where anyone wants to borrow at market rates from a pooled liquidity source. Both should exist.

## Contributing

This is a working draft. Spec contributions, implementation work, and security reviews are welcome. Issues and PRs encouraged.

## Acknowledgments

Built on Verus's identity, currency, raw-transaction, and SIGHASH primitives. Design borrows ideas from Bitcoin's nLockTime semantics, Lightning Network's pre-signed transaction patterns (HTLCs), and Bisq's atomic-swap escrow patterns.

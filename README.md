# VerusLending

A peer-to-peer collateralized credit protocol on Verus.

## In one sentence

Two private parties enter a binding loan agreement on chain, with cryptographic enforcement of repayment, default, and rescue paths — no arbiter, no committee, no third-party intermediary, no liquidation bots.

## In one paragraph

VerusLending is a credit primitive built from existing Verus features: 2-of-2 multisig identities, atomic offer/take swaps, and time-locked pre-signed transactions. At origination, both parties cooperatively create a Loan-ID holding the borrower's collateral, plus two pre-signed escape transactions held off-chain — one for the lender's default-claim at maturity+grace, one for the borrower's rescue if the lender disappears (maturity + 1 year). Repayment happens via an atomic 2-of-2 cosigned takeoffer. If the lender refuses valid repayment, the borrower has a unilateral revocation power (the panic button) that invalidates the lender's default-claim, creating mutual deadlock that forces honest negotiation. Subjective disputes go to real-world courts with the chain record as admissible evidence.

## What's here

- **[SPEC.md](./SPEC.md)** — formal protocol specification (validated)
- **[TESTING.md](./TESTING.md)** — empirical test results from Verus mainnet
- **[LICENSE](./LICENSE)** — MIT

## Status

**Spec is empirically validated.** Every load-bearing mechanism was tested on Verus mainnet during design. Reference wallet implementation is future work.

| Mechanism | Status |
|---|---|
| Loan-ID structure (2-of-2 multisig + revoke + recover) | ✅ validated |
| Atomic origination (raw multi-party tx) | ✅ validated |
| Repayment (makeoffer/takeoffer with 2-of-2 cosign) | ✅ validated |
| Default claim (Tx-B with nLockTime) | ✅ validated |
| Borrower's rescue (Tx-C structurally identical to Tx-B) | ✅ validated by extension |
| Panic button (revoke invalidates pre-signed Tx-B) | ✅ validated |
| Front-run protection (stranger cannot deliver Loan-ID) | ✅ validated |

See [TESTING.md](./TESTING.md) for txid references on Verus mainnet.

## Why it matters

This is what private secured lending looked like before banks: two parties, a notarized agreement, time-based defaults. Existing crypto lending products that work today (Ledn, Unchained, Arch) re-create that model with corporate operators. VerusLending re-creates it with cryptographic enforcement instead — the chain is the notary, the parties are themselves.

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

## Architecture summary

```
Origination (one ceremony):
  Tx-A: atomic multi-party tx — collateral → Loan-ID, principal → borrower
  Tx-B: pre-signed lender's default-claim (nLockTime = maturity + grace)
  Tx-C: pre-signed borrower's rescue (nLockTime = maturity + 1 year)

Loan-ID:
  primary: 2-of-2 [borrower, lender]
  revocation: borrower (panic button)
  recovery: 2-of-2 [borrower, lender]

Repayment:
  borrower's makeoffer + lender's 2-of-2 cosigned takeoffer = atomic settlement

Default:
  lender broadcasts Tx-B at maturity + grace

Lender disappeared:
  borrower broadcasts Tx-C at maturity + 1 year

Lender refuses valid repayment:
  borrower revokes Loan-ID → Tx-B invalidated → mutual freeze → forced negotiation
```

See [SPEC.md](./SPEC.md) for the full protocol.

## Contributing

This is a working draft. Spec contributions, implementation work, and security reviews are welcome. Issues and PRs encouraged.

## Acknowledgments

Built on Verus's identity, currency, and offer/swap primitives. The design borrows ideas from Bisq's atomic-swap escrow patterns and Bitcoin's nLockTime semantics.

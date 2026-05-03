# VerusLending

A peer-to-peer collateralized credit protocol on Verus.

![VerusLending Protocol Lifecycle](https://raw.githubusercontent.com/Fried333/veruslending/main/diagram.svg)

## In one sentence

Two private parties enter a binding loan agreement on chain, with cryptographic enforcement of repayment, default, and rescue paths — no arbiter, no committee, no third-party intermediary, no liquidation bots, no panic button.

## In one paragraph

VerusLending is a credit primitive built from existing Verus features: **P2SH 2-of-2 multisig** (no identity registration required), atomic raw transactions, and pre-signed time-locked transactions using `SIGHASH_SINGLE|ANYONECANPAY`. At origination, both parties cooperatively create a vault holding the borrower's collateral, plus three pre-signed transactions: one for the borrower's atomic repayment (held privately by the borrower, broadcast unilaterally at any time during the loan term), one for the lender's default-claim at maturity+grace, and one optional last-resort rescue. The lender's pre-commitment at origination is irrevocable — the borrower can settle without any live cooperation from the lender. Lender stonewalling is structurally impossible. Subjective disputes go to real-world courts with the chain record as admissible evidence. VerusIDs are not required for the cryptographic protocol but provide the marketplace data layer (offer discovery + on-chain reputation) for unknown-party flows.

## What's here

- **[SPEC.md](./SPEC.md)** — formal protocol specification (v1.0)
- **[TESTING.md](./TESTING.md)** — empirical test results from Verus mainnet (txid references)
- **[SCHEMA.md](./SCHEMA.md)** — canonical chain data layer (VDXF keys, payload schemas, indexer API spec)
- **[recipes/](./recipes/)** — practical how-to guides per use case (lending, options, swap, escrow, marketplace)
- **[helpers/](./helpers/)** — short Python utilities supporting the recipes
- **[BRIEF.md](./BRIEF.md)** — single-page summary
- **[SCENARIOS.md](./SCENARIOS.md)** — full scenario test matrix
- **[diagram.svg](./diagram.svg)** — protocol lifecycle diagram
- **[LICENSE](./LICENSE)** — MIT

The same primitive (SIGHASH_SINGLE|ANYONECANPAY pre-commit) supports multiple use cases:

| Use case | Recipe | Purely CLI? |
|---|---|---|
| Lending (collateralized loans) | [recipes/lending.md](./recipes/lending.md) | ✅ pure CLI for collateral-pays-fee variant (any currencies); broadcaster-pays-fee variant needs `extend_tx.py` |
| Options markets | [recipes/options.md](./recipes/options.md) | setup + pre-sign yes; exercise/expiry-recovery need helper for fee inputs |
| Atomic p2p currency swaps | [recipes/swap.md](./recipes/swap.md) | ✅ pure CLI |
| Escrow (time-locked, multi-party) | [recipes/escrow.md](./recipes/escrow.md) | depends on pattern |
| Marketplace data layer | [recipes/marketplace.md](./recipes/marketplace.md) | ✅ pure CLI |

## Status

**Spec is empirically validated.** Every load-bearing mechanism was tested on Verus mainnet during design. Reference wallet implementation is future work.

| Mechanism | Status |
|---|---|
| **Vault — P2SH 2-of-2 multisig (canonical, no VerusID needed)** | ✅ validated |
| Vault — VerusID flavor (i-address, 2-of-2 primary, null revoke/recover) — required for non-VRSC collateral | ✅ validated |
| Atomic origination (raw multi-party tx) | ✅ validated |
| **Cross-currency origination + repayment (e.g. VRSC collateral + DAI principal)** | ✅ validated |
| **Pre-signed Tx-Repay (SIGHASH_SINGLE\|ANYONECANPAY)** — canonical | ✅ validated |
| **Pre-signed Tx-B (SIGHASH_SINGLE\|ANYONECANPAY + nLockTime)** — symmetric default-claim | ✅ validated |
| **Pre-signed Tx-C (rescue, far-future nLockTime, output to borrower)** | ✅ validated on mainnet |
| Broadcaster-pays-fee variant (collateral returned in full) | ✅ validated for both Tx-Repay and Tx-B |
| Pre-locktime broadcast rejection (`64: non-final`) | ✅ validated for both VerusID and p2sh |
| Tx-Repay broadcast invalidates pre-signed Tx-B (UTXO consumption) | ✅ validated |
| Output 0 tampering (recipient or amount change) rejected | ✅ validated — `mandatory-script-verify-flag-failed` |
| **Options primitive — full lifecycle (premium, exercise, expiry, recovery)** | ✅ validated on mainnet (TESTING.md §26 + §27) |
| Front-run protection (no offer ever in mempool) | ✅ structural |

See [TESTING.md](./TESTING.md) for txid references and [SCENARIOS.md](./SCENARIOS.md) for the full scenario test matrix.

## Why it matters

This is what private secured lending looked like before banks: two parties, a notarized agreement, time-based defaults. Existing crypto lending products that work today (Ledn, Unchained, Arch) re-create that model with corporate operators. VerusLending re-creates it with cryptographic enforcement instead — the chain is the notary, the parties are themselves, and the lender's commitment is enforced by signature mechanics rather than by external accountability.

The protocol is intentionally minimal:

- No on-chain dispute resolution (use courts; chain provides evidence)
- No oracle dependency (no margin calls, no liquidation bots)
- No protocol-controlled treasury or fee
- No DAO governance
- No proprietary token
- No panic button or recovery authority — the protocol does exactly three things: settle, default, or rescue

## Use cases

- Peer-to-peer collateralized loans between any two parties — pseudonymous via VerusIDs, fully private via R-addresses
- Reputation-scored marketplace lending: lenders post offers to their VerusID multimap; borrowers filter by on-chain history (`loan.history.v1`)
- Cross-currency loans (e.g. VRSC collateral, DAI principal) — any currency Verus's currency layer supports
- Collateralized lending within communities (members lending to other members under a shared parent ID convention)
- Private loans between businesses or individuals who already know each other

## What it is NOT for

- High-frequency margin trading
- Variable-rate or amortizing loans (pre-signed Tx-Repay output amounts are fixed at origination)
- Loans where parties may want to renegotiate or abandon mid-term without cooperation
- Custodial lending platforms with retail users (regulatory complications — the protocol explicitly avoids custody)

## Architecture summary

```
Origination ceremony (one-time, cooperative):
  Tx-A:       atomic origination — collateral → vault, principal → borrower
  Tx-Repay:   pre-signed atomic repayment template (SIGHASH_SINGLE|ANYONECANPAY)
              Held privately by borrower
              Borrower can broadcast unilaterally any time before maturity
  Tx-B:       pre-signed lender's default-claim (nLockTime = maturity + grace)
              Held by lender; broadcast at maturity if no Tx-Repay broadcast
  Tx-C:       (optional) pre-signed borrower's last-resort rescue
              nLockTime = maturity + 1 year; rare fallback

Vault:
  Default: P2SH 2-of-2 multisig of [borrower_pubkey, lender_pubkey]
           — derived via createmultisig, no registration required, zero cost.
           Holds VRSC collateral.
  Optional: VerusID (i-address) flavor with the same 2-of-2 primary,
            null revocation/recovery — required for non-VRSC collateral
            because the chain enforces non-VRSC outputs go to i-addresses.
            Costs a sub-ID registration (~0.1 VRSC).

Repayment (canonical, collateral-pays-fee):
  Borrower broadcasts the pre-signed Tx-Repay as-is.
  Output 0 (the sig-locked payment to lender) cannot be modified.
  A small tx fee is deducted from the collateral output.
  Lender does not need to sign anything at repayment time.

Repayment (broadcaster-pays-fee variant):
  Borrower extends Tx-Repay with their own VRSC fee inputs and a
  matching change output, then signs the new inputs with SIGHASH_ALL.
  Output 0 is still untouchable. Collateral returns in full.
  Requires helpers/extend_tx.py (only place a helper is unavoidable).

Default:
  Borrower never broadcasts Tx-Repay.
  Lender broadcasts Tx-B at maturity + grace.

Lender disappeared:
  Borrower broadcasts Tx-Repay normally — pre-signature is sufficient.
  No reliance on lender being alive or available.
```

Three settlement paths total. No mutual-deadlock state ever exists. Either the loan is settled (Tx-Repay), defaulted (Tx-B), or rescued (Tx-C, rare).

See [SPEC.md](./SPEC.md) for the full protocol.

## Wallet integration

The recipes are written so they can be run from a stock Verus daemon, but the natural home for this protocol is a wallet. The recipes' multi-step ceremonies (origination, cooperative pre-signing, template storage, exercise/repay, expiration) map cleanly onto wallet UX:

- **Posting / browsing offers** → marketplace tab reading VerusID `vrsc::contract.loan.offer` multimap entries (see [marketplace.md](./recipes/marketplace.md) and [SCHEMA.md](./SCHEMA.md) for canonical VDXF ids)
- **Origination ceremony** → coordinated via encrypted multimap entries between counterparties
- **Template storage** → encrypted in user's own VerusID multimap, recoverable from seed
- **Repay / exercise / claim** → one-click broadcast of pre-signed templates

Verus Wallet V2 (Chrome extension, non-custodial, direct daemon RPC) is the reference target. The `extend_tx.py` helper logic (~80 lines of tx serialization) ports directly to the wallet's TypeScript codebase. The recipes serve as both a runnable reference for power users and the spec a wallet implementor would follow.

## Relationship to other Verus lending efforts

This protocol is a **peer-to-peer fixed-term primitive**. It's complementary to other lending models the Verus ecosystem may support:

- **Basket-based pool lending** (a future Verus direction): currency baskets become lending pools with dynamic interest rates based on collateral/loan ratios; LPs earn fees by holding basket tokens; margin call enforcement via import rollup or validator-incentivized redemption. Best fit for retail / anonymous / market-rate lending. Different model from VerusLending — different use case.

- **Template outputs** (a future Verus feature): non-spending outputs that act as cross-tx constraints requiring a matching companion output with specified fields. When this lands, it would simplify some of the patterns we currently express via SIGHASH manipulation, and could enable cleaner vault-makes-offer designs that solve the empty-Pay-ID problem we encountered during testing.

VerusLending serves the use case where two known parties want to enter a private, fixed-term, fixed-rate loan with cryptographic atomic settlement. Mike's basket-based lending vision serves the use case where anyone wants to borrow at market rates from a pooled liquidity source. Both should exist.

## Contributing

This is a working draft. Spec contributions, implementation work, and security reviews are welcome. Issues and PRs encouraged.

## Acknowledgments

Built on Verus's identity, currency, raw-transaction, and SIGHASH primitives. The Verus marketplace's `makeoffer` / `takeoffer` mechanism uses `SIGHASH_SINGLE | ANYONECANPAY` for offer construction; the canonical Tx-Repay / Tx-B / Tx-C templates in this spec use the same SIGHASH flag at the raw-tx level — no marketplace dependency. Origination Tx-A uses default `SIGHASH_ALL` cooperative cosign. Design also borrows ideas from Bitcoin's `nLockTime` semantics and Lightning Network's pre-signed transaction patterns (HTLCs).

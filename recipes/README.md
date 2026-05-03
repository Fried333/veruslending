# Recipes — practical how-to guides

Each recipe walks through one use case end-to-end, with the actual CLI commands you'd run on a Verus node. Recipes are designed to be **runnable** — copy the commands, replace addresses/amounts with your own, and you have a working flow.

The recipes use the same primitives validated across [TESTING.md](../TESTING.md)'s 36 mainnet test scenarios. Each recipe references the relevant test sections for proof.

## Structure of each recipe

Every recipe document has the same sections:

1. **What this is** — the use case in plain language
2. **Roles** — the parties involved (e.g., borrower, lender)
3. **What the protocol does** — the mechanics on chain
4. **What the user does** — the buttons / CLI commands they run
5. **Helper code needed** — references to the `helpers/` directory
6. **Walkthrough** — a complete worked example with real txids
7. **Security considerations** — common pitfalls and how to avoid them
8. **Pure CLI vs helper-required** — what works with stock Verus and what needs glue

## Available recipes

| Recipe | Use case | Status |
|---|---|---|
| [lending.md](./lending.md) | Peer-to-peer collateralized credit | ✅ |
| [options.md](./options.md) | Options markets (covered calls, puts) | ✅ |
| [swap.md](./swap.md) | Atomic p2p currency swaps | ✅ |
| [escrow.md](./escrow.md) | Time-locked and multi-party escrow | ✅ |
| [marketplace.md](./marketplace.md) | Posting and discovering offers via VerusID multimap | ✅ |

## Helpers

Code in [`../helpers/`](../helpers/) supports the recipes:

| Helper | Purpose |
|---|---|
| `extend_tx.py` | Add inputs/outputs to a pre-signed tx while preserving existing scriptSigs |
| `verus_lend.py` | High-level CLI wrapping the helpers + Verus RPCs (one command per recipe phase) |

These are short, audited Python scripts. They're protocol-aware (they validate the tx structure they're handling) — that's the safety wrapper that a generic chain-level RPC wouldn't provide.

## How to run a recipe

Prerequisites:
- A running Verus daemon (`verusd`) at version 1.2.16 or later
- Wallet has funds (VRSC for fees + whichever currencies are involved)
- Python 3 for the helper scripts

Each recipe walks through commands sequentially. You can either:
- **Manual mode**: type each `verus` command yourself, copy hex between steps
- **Wrapped mode**: use `helpers/verus_lend.py` to bundle the steps

Both work. Manual mode shows you exactly what's happening; wrapped mode is faster.

## Trust model

All recipes operate on the principle that **chain-level enforcement beats off-chain trust**. Where a recipe says "no trust required," that means cryptographic enforcement covers the relevant scenario. Where it says "trust required," reputation or off-chain agreement is the only protection.

The recipes are explicit about which is which. Don't run a recipe without reading its security section.

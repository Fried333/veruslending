# Helpers

Small utilities for running the protocol's recipes from a Verus node. These are protocol-aware: they validate the tx structures they handle so callers can't accidentally produce malformed extensions.

## Available helpers

### `recover_vault.sh`

Cooperative 2-of-2 vault drain used to recover from a half-finished settlement (e.g., a test that crashed after Tx-A confirmed but before Tx-Repay broadcast). Idempotent — exits 0 immediately if the vault is empty.

```bash
bash recover_vault.sh
```

Steps:
1. Borrower → lender: 5.05 DAI repay via `sendcurrency`
2. Both sign + broadcast a fresh vault drain (10 VRSC → borrower)
3. Wait for confirmation

Hardcoded for the test wallets (`bSe1gaBoZJqcBTMuTi6VYevXrRLz5XZ8Kj` vault, `RSiyiZ92…` borrower, `RKGN34Uh…` lender via SSH to `86.107.168.44:2400`). Adapt for other party pairs by editing the constants at the top of the script.

Used by the GUI repo's e2e suite ([`verus_contract_gui/test/e2e_v3_scenarios.mjs`](https://github.com/Fried333/verus_contract_gui/blob/main/test/e2e_v3_scenarios.mjs)) — invoked via `bash /home/dev/veruslending/helpers/recover_vault.sh` (override path with `RECOVER_VAULT` env var).

### `extend_tx.py`

Core utility. Takes a pre-signed tx hex and adds new inputs/outputs while preserving existing scriptSigs.

```bash
python3 extend_tx.py \
  --template <hex_or_path_to_hex> \
  --add-input <txid:vout> \
  --add-output <address:amount[:currency]> \
  > extended.hex

# Then sign the new inputs with stock CLI:
verus signrawtransaction $(cat extended.hex)
verus sendrawtransaction <signed_hex>
```

Used in:
- [recipes/lending.md](../recipes/lending.md) — Tx-Repay broadcaster-pays-fee variant
- [recipes/options.md](../recipes/options.md) — exercise + expiration recovery
- [recipes/escrow.md](../recipes/escrow.md) — broadcaster-pays-fee variants

### What `extend_tx.py` does NOT do

- It doesn't sign anything (use `verus signrawtransaction` after extending)
- It doesn't broadcast (use `verus sendrawtransaction` after signing)
- It doesn't validate that the resulting tx is *protocol-correct* — it just preserves existing scriptSigs while adding bytes. Callers must validate their additions are sensible for their protocol.

This narrow scope is intentional. Each protocol implementing on top of this primitive owns its own protocol-correctness validation.

## Why scripts not RPCs

We considered asking Verus core to add an `extendrawtransaction` RPC. The dev's design philosophy for makeoffer/takeoffer suggests bundling extension + validation + signing + broadcasting into safe wrappers, rather than exposing low-level byte primitives at the RPC layer. Exposing a generic extension RPC would create footguns for callers that don't validate the input tx structure (see [SPEC.md §17 limitations](../SPEC.md#17-limitations-and-known-issues)).

By keeping the byte manipulation in protocol-specific helper scripts/wallet code, each implementer takes responsibility for their own protocol-correctness. Smaller blast radius if something goes wrong; wider auditability.

## For wallet implementors

The `extend_tx.py` logic is ~80 lines of pure tx serialization. Porting to JavaScript / Rust / any language is straightforward:

```
parseHex(hex) → tx_object
  read varint vinCount
  read each vin (32-byte txid_LE + 4-byte vout + varint scriptSig + 4-byte sequence)
  read varint voutCount
  read each vout (8-byte value + varint scriptPubKey)
  read remainder (locktime, expiryheight, sapling-specific)

extend(tx, [new_inputs], [new_outputs]) → tx_object
  append vins (with empty scriptSig)
  append vouts

serialize(tx_object) → hex
  reverse of parse, byte-for-byte preserving existing scriptSigs
```

For Verus Wallet V2 (JavaScript/TypeScript), this is a small module that ships with the wallet.


# Recipe — atomic p2p currency swap

Two parties trade currencies directly, no order book, no exchange, no escrow. One party posts an offer; the other takes it. Single atomic tx — both sides happen or neither does.

This is **the Verus marketplace `makeoffer`/`takeoffer` flow**. Recipe documents it for completeness; nothing protocol-specific to VerusLending.

## Roles

- **Maker** (Bob): wants to give currency A, get currency B in exchange
- **Taker** (Alice): wants to give currency B, get currency A

## What the protocol does

`makeoffer` constructs an atomic-swap offer from one party. `takeoffer` extends and broadcasts when another party agrees.

The marketplace internally uses `SIGHASH_SINGLE | ANYONECANPAY` — same primitive as VerusLending's lending and options protocols, just exposed as a wallet-friendly RPC.

---

## Walkthrough — DAI ↔ VRSC swap

**Trade**: Bob gives 0.05 VRSC, wants 0.1 DAI. Alice agrees.

### Maker (Bob) posts offer

```bash
verus makeoffer "BOB_R_ADDRESS" '{
  "changeaddress": "BOB_R_ADDRESS",
  "offer": {"currency":"VRSC", "amount":0.05},
  "for":   {"address":"BOB_R_ADDRESS", "currency":"DAI.vETH", "amount":0.1}
}'
# Returns: {"txid":"<offer-txid>"}
```

The offer broadcasts to chain. Bob's 0.05 VRSC is now committed via SIGHASH_SINGLE|ANYONECANPAY signature. Anyone matching the FOR clause can take it.

### Taker (Alice) takes the offer

After offer confirms:

```bash
verus takeoffer "ALICE_R_ADDRESS" '{
  "changeaddress": "ALICE_R_ADDRESS",
  "txid": "<offer-txid>",
  "deliver": {"currency":"DAI.vETH", "amount":0.1},
  "accept":  {"address":"ALICE_R_ADDRESS", "currency":"VRSC", "amount":0.05}
}'
# Returns: {"txid":"<take-txid>"}
```

Atomic. Bob receives 0.1 DAI; Alice receives 0.05 VRSC. Single tx.

**Validated mainnet — TESTING §34 (txid `f2ce9faa...`).**

---

## Variants

### Optional offer expiry

Set `expiryheight` on the offer:

```bash
verus makeoffer ... '{
  ...
  "expiryheight": <block_number>,
  ...
}'
```

**Caveat (TESTING §35)**: `expiryheight` on `makeoffer` controls when the OFFER TX itself can be broadcast, NOT when `takeoffer` can take it. Once the offer is on chain, it remains takeable indefinitely until taken or canceled via `closeoffers`.

For "this offer expires at block X" semantics with chain enforcement, you'd need different mechanisms — see [options.md](./options.md) for the pre-signed-exercise-with-expiryheight pattern.

### Maker cancels

Maker can cancel an unbroadcast offer by spending the input UTXO elsewhere, OR cancel an on-chain offer via:

```bash
verus closeoffers
```

This recovers the maker's offer-locked funds.

### Cross-chain swaps (Verus Swap)

Verus supports atomic swaps across PBaaS chains using the same primitive. See Verus Swap documentation; same makeoffer/takeoffer pattern with cross-chain awareness.

---

## What works pure CLI

| Phase | Pure CLI? |
|---|---|
| Make offer | ✅ `makeoffer` |
| Take offer | ✅ `takeoffer` |
| Cancel offer | ✅ `closeoffers` |

**100% pure stock CLI for atomic swaps.** No helpers, no helpers script, no protocol-specific code. This is the marketplace working as designed.

---

## What the wallet does

Verus Wallet V2 already supports `makeoffer`/`takeoffer`. The wallet:

1. UI for posting offers (Maker)
2. UI for browsing on-chain offers (Taker)
3. One-click "Take" with auto-fee calculation
4. History rendering (if maker has VerusID with `loan.history.v1` entries — see [marketplace.md](./marketplace.md))

Generic swaps don't need any new wallet code beyond what already exists.

---

## Security considerations

### Trust profile

**Zero trust required for the swap itself.** The atomic tx ensures both sides happen or neither does. Same security as Bitcoin's atomic swaps, with single-tx settlement (no HTLC complexity).

### What still requires trust / attention

- **Counterparty matching** — if you take a stranger's offer, you only need to trust that the offer is what it claims (verify via `getrawtransaction` decode). The trade itself is atomic.
- **Price discovery** — out of scope. Wallets and explorers can render market prices from various sources, but the protocol doesn't enforce fair pricing.
- **Mempool-watching for offer cancellation race** — maker could spend their input to cancel just before taker tries to take. Worst case: taker's tx fails to broadcast (no funds lost). Mitigation: check offer is still active before taking.
- **`expiryheight` semantics** — does NOT gate take window (per §35). Offers stay takeable until taken or canceled.

### Validated mainnet

- Cross-currency atomic swap (VRSC ↔ DAI) — TESTING §34
- Pure CLI atomic swap with i-address recipient — TESTING §28
- Atomic swap with vault as accept (used by options + lending) — TESTING §36

---

## Relationship to other recipes

The makeoffer/takeoffer primitive is the foundation for:

- [lending.md](./lending.md) origination phase (Tx-O)
- [options.md](./options.md) atomic setup phase
- [escrow.md](./escrow.md) two-party time-locked escrow

All those recipes use this primitive plus additional pre-signed transactions for their multi-phase logic.

---

## References

- Verus marketplace docs (in main Verus documentation)
- [TESTING.md §28, §34, §35, §36](../TESTING.md)

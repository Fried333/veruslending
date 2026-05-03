# Recipe — escrow patterns

Escrow is "I'll pay X if condition Y is met." Verus supports several patterns natively. This recipe covers the three main cases.

## Pattern 1 — Two-party time-locked escrow (pure CLI)

A makes a payment commitment that B can claim before deadline; otherwise A recovers the funds.

**Use cases**: bounty payments, time-limited service contracts, "pay-on-delivery before deadline."

### Mechanic

This is just `makeoffer` with a hard caveat about `expiryheight`. Per TESTING §35, makeoffer's `expiryheight` doesn't gate take-window. So this pattern works only as long as A actively cancels the offer when expired:

```bash
# A posts offer
verus makeoffer "A_R_ADDRESS" '{
  "changeaddress": "A_R_ADDRESS",
  "offer": {"currency":"VRSC", "amount":100},
  "for":   {"address":"A_R_ADDRESS", "currency":"DAI", "amount":50}
}'

# B can take any time before A cancels
verus takeoffer "B_R_ADDRESS" '{
  "txid": "<offer-txid>",
  "deliver": {"currency":"DAI", "amount":50},
  "accept":  {"address":"B_R_ADDRESS", "currency":"VRSC", "amount":100}
}'

# OR if B doesn't take by deadline, A cancels:
verus closeoffers
```

**Limitation**: A must remember to cancel. If A forgets, B can take indefinitely. For automated cancellation, use Pattern 2.

### Pure CLI ✅

---

## Pattern 2 — Time-locked escrow with auto-refund (needs helper for some flows)

Buyer commits funds at a 2-of-2 vault; seller claims by delivering goods/service before time T; otherwise auto-refunds to buyer.

### Mechanic

Same as the lending protocol's vault + Tx-B + Tx-C structure:

```
At creation:
  Buyer's funds → 2-of-2 vault [buyer, seller]
  Both pre-sign:
    - Tx-Claim: vault → seller (no locktime, can broadcast any time)
    - Tx-Refund: vault → buyer (nLockTime = T, post-deadline only)

If seller delivers:
  Buyer broadcasts Tx-Claim — seller gets the funds

If seller doesn't deliver by time T:
  Buyer broadcasts Tx-Refund — buyer gets funds back
```

### CLI status

| Phase | Pure CLI? |
|---|---|
| Vault funding (atomic via Tx-O pattern) | ✅ via `makeoffer`/`takeoffer` |
| Pre-sign Tx-Claim and Tx-Refund | ✅ `signrawtransaction null null "SINGLE\|ANYONECANPAY"` |
| Broadcast Tx-Claim (collateral-pays-fee) | ✅ |
| Broadcast Tx-Refund (collateral-pays-fee) | ✅ |
| Broadcaster-pays-fee variants | ❌ needs `helpers/extend_tx.py` |

For VRSC-denominated escrow with collateral-pays-fee, **pure CLI works end-to-end**. For non-VRSC currencies, broadcaster-pays-fee is needed (vault has no VRSC for fee), needing the helper.

### Trust profile

After vault is funded:
- Seller cannot rug-pull (vault is 2-of-2)
- Buyer cannot reclaim before deadline (Tx-Refund nLockTime)
- Seller cannot keep both funds AND fail to deliver — they get funds via Tx-Claim, but only by delivering off-chain (the chain doesn't verify delivery; that's the trust point)

The chain enforces the time-locked refund. The "seller delivered" condition is off-chain. For chain-verifiable conditions, use Pattern 3.

---

## Pattern 3 — Hash-time-locked escrow (HTLC-style)

Funds locked with: "reveal hash preimage to claim, OR wait until time T then refund."

Common in cross-chain atomic swaps. Verus supports this via `OP_CHECKCRYPTOCONDITION` with hash-locking.

### Mechanic

```
At creation:
  Buyer's funds → conditional output:
    - Spendable by seller IF they reveal preimage of hash H
    - Spendable by buyer IF nLockTime ≥ T
  
Seller's claim path:
  Seller broadcasts a tx that includes preimage P (where hash(P) == H)
  Chain verifies hash, releases funds to seller

Buyer's refund path:
  After T, buyer broadcasts refund tx
  Chain verifies locktime, releases funds back to buyer
```

### CLI status

This is a **different primitive** — uses cryptocondition hash-locking, not just SIGHASH. Construction is more complex. Verus supports it for cross-chain swaps; for general HTLC use, see Verus's atomic-swap documentation.

Not directly part of VerusLending's primitive set, but mentioned here for completeness.

---

## Pattern 4 — Three-party arbiter escrow (2-of-3 multisig)

For cases where neither party should unilaterally control release (high-trust transactions, dispute resolution).

### Mechanic

```
Buyer + Seller + Arbiter each have keys
Funds locked at 2-of-3 multisig address
Normal release: Buyer + Seller cosign payment to seller
Disputed release: Arbiter + (Buyer OR Seller) cosign appropriate path
```

### Construction

```bash
# Derive 2-of-3 address
verus createmultisig 2 '["<buyer_pub>","<seller_pub>","<arbiter_pub>"]'
# Returns: {"address":"b...", "redeemScript":"..."}

# Buyer deposits funds via sendtoaddress to the 2-of-3 address

# Release path: any 2 of 3 cooperate to construct a spending tx
verus createrawtransaction \
  '[{"txid":"<deposit_txid>","vout":0}]' \
  '{"<recipient>":<amount>}'

# Each party signs in turn
verus signrawtransaction <hex>
ssh other_party 'verus signrawtransaction <hex>'
# Once 2-of-3 sigs present, broadcast
verus sendrawtransaction <fully-signed-hex>
```

### CLI status

Pure stock CLI for the funding + cooperative spending paths. ✅

The cooperative-signing requires both signers to be online together, which is fine for this use case (arbiter is engaged precisely when there's a dispute).

### Trust profile

- Single party can't release funds (requires 2-of-3 sigs)
- Arbiter has discretion in disputes — counterparties trust the arbiter
- Use case: regulated marketplaces, real-estate transactions, B2B agreements where arbitration is acceptable

---

## What the wallet does

In a Verus Wallet V2 implementation:

```
[Escrow tab]

  My active escrows
    "Logo design from designer.id@" — 100 DAI committed, 7 days remaining
    [ Mark complete ]   [ Refund (after deadline) ]
    
  Create escrow
    [ Time-locked ]   [ Multi-party arbiter ]   [ HTLC ]
```

For Pattern 1 (offer-based), it's just makeoffer/takeoffer with a different label.
For Pattern 2 (time-locked with refund), uses the same vault + pre-signed tx infrastructure as lending.
For Pattern 4 (multi-party), constructs cooperative tx with all parties' wallets.

---

## Security considerations

### Pattern selection matters

- **Pattern 1**: simplest, most permissive, requires explicit cancellation
- **Pattern 2**: chain-enforced refund, but conditional release is off-chain (trust seller delivered)
- **Pattern 3**: chain-enforced both paths, conditional via cryptographic preimage (e.g., proof of payment on another chain)
- **Pattern 4**: arbiter discretion, manual disputes

### Common pitfalls

- **Forgetting to cancel Pattern 1** — funds stay takeable indefinitely
- **Wrong locktime** — too short (no time for delivery), too long (funds locked too long)
- **Lost arbiter key (Pattern 4)** — disputes become unresolvable; choose arbiters with good key management
- **Hash-preimage discovery (Pattern 3)** — if preimage leaks, anyone can claim. Use single-use random preimages.

### What's chain-enforced

- Pattern 1: nothing automatic; requires explicit close
- Pattern 2: time-locked refund
- Pattern 3: hash AND time both chain-enforced
- Pattern 4: 2-of-3 sig requirement

---

## References

- [SPEC.md Part I §3](../SPEC.md) — same vault + Tx-B/Tx-C primitive used in lending
- [TESTING.md §17, §19, §27, §35](../TESTING.md) — relevant validations
- Verus atomic-swap documentation (for Pattern 3 / cross-chain)

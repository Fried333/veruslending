# Recipe — peer-to-peer lending

Two parties enter a binding loan: borrower puts up collateral, lender provides principal, borrower repays with interest by maturity or defaults and loses collateral. Cryptographically enforced; no third party needed at runtime.

## Roles

- **Borrower** (Alice): provides collateral, receives principal at origination, obligated to repay by maturity
- **Lender** (Bob): provides principal, receives repayment if borrower repays, claims collateral if borrower defaults

## What the protocol does

Five-phase lifecycle:

| Phase | When | Who | What | Channel |
|---|---|---|---|---|
| 1. Discovery | Lender publishes terms | Lender | `loan.offer` multimap entry on lender's VerusID | chain (VerusID multimap) |
| 2. Coordination | Borrower wants to take | Both | Exchange pubkeys, derive vault | encrypted multimap entry, or paste |
| 3. Atomic origination (Tx-A) | Both ready | Both | Atomic: principal → borrower; collateral → vault | cooperative `createrawtransaction` + cosign |
| 4. Pre-sign templates | At setup | Both | Cooperatively pre-sign Tx-Repay (borrower's) + Tx-B (lender's default-claim) + optional Tx-C (rescue) | cooperative cosign with `SIGHASH_SINGLE\|ANYONECANPAY` |
| 5. Active / settlement | Anytime / after maturity | Borrower or lender | Unilateral broadcast of the relevant template | `sendrawtransaction` |

The four transactions:

| Tx | When | Who broadcasts | Effect |
|---|---|---|---|
| **Tx-A** | At origination | Either party (cooperative tx) | Lender's principal → borrower; borrower's collateral → vault |
| **Tx-Repay** | Any time before maturity | Borrower | Repayment → lender; collateral → borrower |
| **Tx-B** | After maturity + grace, if no repayment | Lender | Collateral → lender |
| **Tx-C** (optional) | After far-future lockout | Borrower | Collateral → borrower (rescue if both abandoned) |

The **vault** is a 2-of-2 multisig holding the collateral:

- **Profile L** (P2SH) — VRSC collateral only, zero registration cost. Default.
- **Profile V** (VerusID i-address) — any currency collateral, sub-ID registration cost (~0.1 VRSC). Required for non-VRSC collateral because the chain enforces non-VRSC outputs go to i-addresses.

## What the user does

In a wallet UI: browse offers → click "Accept" → click "Repay" at maturity. Two clicks total. The wallet handles everything else.

In raw CLI: ~10 RPC calls per loan lifetime. Walked through below.

---

## Walkthrough — VRSC-collateralized loan, pure CLI

This is the simplest case. Everything works with stock `verus` CLI; no helper script needed.

**Loan terms**: Alice (borrower) borrows 5 VRSC from Bob (lender), putting up 10 VRSC as collateral. Repays 5.5 VRSC by block N+1000. Profile L vault.

### Phase 1 — Discovery (lender publishes the offer)

Bob posts his terms to his VerusID's multimap so anyone scanning the chain (or an explorer indexer) can find him. No borrower involved yet.

```bash
# Build the offer JSON
OFFER='{
  "version": 1,
  "type": "lend",
  "principal":  {"currency":"VRSC", "amount":5},
  "collateral": {"currency":"VRSC", "amount":10},
  "rate": 0.10,
  "term_days": 30,
  "lender_pubkey":  "<bob_compressed_pubkey>",
  "lender_address": "BOB_R_ADDRESS",
  "valid_until_block": '"$(($(verus getblockcount) + 10000))"',
  "active": true
}'
HEX=$(echo -n "$OFFER" | python3 -c "import sys; print(sys.stdin.read().encode().hex())")

# VDXF id for make.vrsc::contract.loan.offer (canonical, see SCHEMA.md)
verus getvdxfid "make.vrsc::contract.loan.offer"
# Returns: {"vdxfid":"iMey7Y2idT6dt7jJvRiPXgtYcfAaKCQbHz", ...}

# Write to Bob's VerusID
verus updateidentity '{
  "name": "bob.lender@",
  "contentmultimap": {
    "iMey7Y2idT6dt7jJvRiPXgtYcfAaKCQbHz": ["'$HEX'"]
  }
}'
```

The offer is now publicly readable on chain. Borrowers find it via direct ID lookup (`getidentity bob.lender@`) or via a chain indexer that scans for `make.vrsc::contract.loan.offer` entries. See [marketplace.md](./marketplace.md).

### Phase 2 — Coordination (vault derivation)

Alice reads Bob's offer (chain-native, no comms required) and gets `lender_pubkey`. She then needs Bob to know HER pubkey so they can both compute the same 2-of-2 vault.

Two ways to send the borrower's pubkey:

- **Encrypted `loan.accept` multimap entry on Alice's own VerusID**, addressed to Bob's z-key (chain-native, asynchronous)
- **Out-of-band paste** (Discord, email, QR — fine for known parties)

Once Bob has Alice's pubkey, both compute the same vault deterministically:

```bash
ALICE_PUB=03e05933ec81c219e9aef5e5da4ea636f80864c8db9466e9cf090a26f6ca639640
BOB_PUB=0270b46dc0dcfe28b35cbd76ba54c5560c88b64b80ebc3cf515b7035b0891c8250

# Profile L (VRSC collateral): pure P2SH
verus createmultisig 2 "[\"$ALICE_PUB\",\"$BOB_PUB\"]"
# Returns: {"address":"bYCcAqB7KfdkfsN8YUipb2fuFhKvxmsnne", "redeemScript":"..."}

# Profile V (non-VRSC collateral): cooperatively register a sub-ID with
#   primaryaddresses=[both R-addrs] and minsig=2.
# The i-address of that ID is the vault.
```

The `b...` (P2SH) or `i...` (VerusID) address is the vault. P2SH exists deterministically — no registration, no fee. Both parties compute it independently and verify they match.

### Phase 3 — Atomic origination (Tx-A)

Loans use a **cooperative `createrawtransaction`** with both parties contributing inputs and signing their own input with default `SIGHASH_ALL`. **Not** `makeoffer`/`takeoffer` — that's the marketplace primitive used for atomic swaps and options, not loans.

```bash
# Both parties build the unsigned Tx-A together
INPUTS='[{"txid":"<bob_principal_utxo_txid>",  "vout":<vout>},
         {"txid":"<alice_collateral_utxo_txid>","vout":<vout>}]'
OUTPUTS='{"<alice_R_address>": 5,
          "<vault_address>":   10,
          "<bob_change_addr>": <change>,
          "<alice_change_addr>": <change>}'

# Step 1: Alice signs her collateral input (her node)
verus createrawtransaction "$INPUTS" "$OUTPUTS" \
  | verus signrawtransaction
# (saves intermediate hex, partially signed)

# Step 2: Ship hex to Bob, Bob signs his principal input (his node)
ssh bob "verus signrawtransaction <hex>"

# Step 3: Either party broadcasts
verus sendrawtransaction <fully-signed-hex>
```

After confirmation:
- Vault has the collateral (locked under 2-of-2)
- Alice has the principal in her R-address
- Tx-A's txid is referenced by all subsequent templates

### Phase 4 — Pre-sign settlement templates

Three templates: Tx-Repay, Tx-B, optionally Tx-C. Each input from the vault is pre-signed with `SIGHASH_SINGLE|ANYONECANPAY` so the broadcaster can extend with their own fee inputs (or skip extension if using collateral-pays-fee).

**Tx-Repay template** (borrower's repayment, no nLockTime — broadcastable any time):

```bash
TXA_TXID=<from Phase 3>
EXPIRY=$((CURRENT_BLOCK + 1000))       # Tx-Repay's own expiryheight = maturity

INPUTS='[{"txid":"'$TXA_TXID'","vout":<vault_vout>}]'
OUTPUTS='{"BOB_R_ADDRESS":5.5}'        # Output 0: repayment to Bob (sig-locked)

verus createrawtransaction "$INPUTS" "$OUTPUTS" 0 $EXPIRY > /tmp/repay_unsigned.hex

# Both parties cosign the vault input with SIGHASH_SINGLE|ANYONECANPAY
verus signrawtransaction $(cat /tmp/repay_unsigned.hex) null null "SINGLE|ANYONECANPAY" \
  > /tmp/repay_alice.json

ssh bob "verus signrawtransaction $(jq -r .hex /tmp/repay_alice.json) null null 'SINGLE|ANYONECANPAY'" \
  > /tmp/repay_signed.json

# Final hex held by ALICE (the borrower)
jq -r .hex /tmp/repay_signed.json > /tmp/tx_repay_template.hex
```

**Tx-B template** (lender's default-claim, with `nLockTime = maturity + grace`):

```bash
LOCKTIME=$((CURRENT_BLOCK + 1100))      # maturity + grace blocks

verus createrawtransaction \
  '[{"txid":"'$TXA_TXID'","vout":<vault_vout>}]' \
  '{"BOB_R_ADDRESS":9.9999}' \
  $LOCKTIME > /tmp/txb_unsigned.hex

# Cosign as above with SIGHASH_SINGLE|ANYONECANPAY
# Final hex held by BOB (the lender)
```

**Tx-C template** (optional, far-future locktime, output to borrower) — same pattern with a long-tail `nLockTime` for catastrophic recovery.

### Phase 5 — Active period + settlement

During the loan term, nothing happens on chain. Both parties hold their respective hex.

**5a. Happy path: borrower repays**

Any time before Tx-Repay's `expiryheight`:

```bash
# Alice broadcasts the pre-signed Tx-Repay as-is
verus sendrawtransaction $(cat /tmp/tx_repay_template.hex)
```

Pure CLI, no extension needed. Lender receives 5.5 VRSC; borrower's collateral comes back via the change output (collateral - tx fee).

**5b. Default path: lender claims after maturity**

After block `LOCKTIME` (maturity + grace):

```bash
# Bob broadcasts the pre-signed Tx-B
verus sendrawtransaction $(cat /tmp/tx_b_template.hex)
```

Pure CLI. Lender claims `collateral - fee`; borrower's collateral is gone.

---

## Walkthrough — broadcaster-pays-fee variant

If the broadcaster wants the **full** counter-asset returned (not `amount - fee`), they extend the pre-signed template with their own VRSC fee inputs. This is the only place a helper script is required.

**Phase 5 alternative (broadcaster-pays-fee Tx-Repay):**

```bash
python3 helpers/extend_tx.py \
  --template /tmp/tx_repay_template.hex \
  --add-input "<borrower_vrsc_fee_utxo>" \
  --add-output "<borrower_full_collateral_address>:<full_collateral>" \
  --add-output "<borrower_change>:<fee_change>" \
  > /tmp/tx_repay_extended.hex

verus signrawtransaction $(cat /tmp/tx_repay_extended.hex) > /tmp/tx_repay_signed.json
verus sendrawtransaction $(jq -r .hex /tmp/tx_repay_signed.json)
```

For non-VRSC collateral (Profile V vault holding DAI etc.), broadcaster-pays-fee is required because the vault has no VRSC for the broadcast tx fee. Same helper handles it.

---

## What works with pure stock CLI

| Phase | Pure CLI? |
|---|---|
| Phase 1: discovery (post offer to multimap) | ✅ `updateidentity` |
| Phase 2: coordination (vault derivation) | ✅ `createmultisig` (Profile L); Profile V needs sub-ID registration |
| Phase 3: atomic origination Tx-A | ✅ `createrawtransaction` + cooperative `signrawtransaction` |
| Phase 4: pre-sign templates | ✅ `signrawtransaction null null "SINGLE\|ANYONECANPAY"` |
| Phase 5: collateral-pays-fee broadcast (Tx-Repay or Tx-B) | ✅ `sendrawtransaction <hex>` |
| Phase 5: broadcaster-pays-fee broadcast | ❌ needs `helpers/extend_tx.py` |

For a loan accepting the small fee deduction from collateral, **everything is pure stock CLI** — any currencies, any vault flavor.

---

## What the wallet does

In a Verus Wallet V2 implementation, all of the above is hidden behind UI. The user sees:

```
[Lending tab]

  Available offers
    bob.lender@   5 VRSC for 10 VRSC, 10% rate, 30 days
                  47 settled / 2 defaulted (96% rate)
                  [ Accept ]
    
  My active loans (none)
  
  My loan history (none yet)
```

The wallet:
1. Reads VerusID multimaps for `make.vrsc::contract.loan.offer` entries (see [marketplace.md](./marketplace.md))
2. Renders offers with reputation summary aggregated from `make.vrsc::contract.loan.history` entries
3. On "Accept", coordinates the multi-step ceremony via encrypted multimap entries
4. Stores templates as encrypted multimap entries on user's own VerusID for seed-recovery
5. Displays "Repay" button when active; broadcasts Tx-Repay
6. Shows outcome in user's loan history after settlement

All complexity is hidden. User clicks two buttons total.

---

## Security considerations

### Key risks

1. **Lost templates** — if a party loses the pre-signed hex AND doesn't have multimap backup, they can't broadcast. Mitigation: store templates encrypted in own VerusID's multimap (`make.vrsc::contract.loan.template`) for seed-recovery.
2. **Predicted txid mismatch** — if Tx-A's actual txid differs from what the templates referenced (rare with deterministic ECDSA), the templates point at a non-existent UTXO and won't broadcast. Mitigation: abort and restart the ceremony if Tx-A's txid changes after template signing.
3. **Validate received templates before signing** — when one party receives the other's pre-signed Tx-Repay or Tx-B template, the wallet MUST verify Output 0 has the agreed amount and is paying the agreed party. The chain enforces what's signed; the wallet must verify what gets signed.
4. **Cross-currency tooling caveat** — for non-VRSC inputs in templates, signing requires `signrawtransaction null null "SINGLE|ANYONECANPAY"` (the wallet key-lookup path). Explicit-key path fails. See [TESTING §32](../TESTING.md).

### What's chain-enforced (not trust)

- Borrower can repay unilaterally — no live cooperation from lender needed
- Lender can claim default unilaterally after maturity — no live cooperation from borrower
- Output 0 (the sig-locked payment) cannot be redirected or reduced — validated TESTING §24
- Settlement is atomic — either Tx-Repay or Tx-B, never both (validated §22, §29)
- Lender stonewalling at repayment is structurally impossible — the pre-signature settles unilaterally

### What still requires off-chain trust (or chain-native equivalents)

- **Counterparty discovery** — solved by VerusID multimap + reputation (`make.vrsc::contract.loan.history`)
- **Agreeing on terms before origination** — discovery + acceptance handshake covers this
- **Subjective dispute resolution** — use real-world courts; chain is admissible evidence

---

## References

- [SPEC.md](../SPEC.md) — formal protocol specification
- [SCHEMA.md](../SCHEMA.md) — canonical VDXF keys + payload schemas
- [TESTING.md §16-§32](../TESTING.md) — mainnet validations of every primitive

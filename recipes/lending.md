# Recipe — peer-to-peer lending

Two parties enter a binding loan: borrower puts up collateral, lender provides principal, borrower repays with interest by maturity or defaults and loses collateral. Cryptographically enforced; no third party needed at runtime.

## Roles

- **Borrower** (Alice): provides collateral, receives principal at origination, obligated to repay by maturity
- **Lender** (Bob): provides principal, receives repayment if borrower repays, claims collateral if borrower defaults

## What the protocol does

Four pre-signed transactions form the loan's lifecycle:

| Tx | When | Who broadcasts | Effect |
|---|---|---|---|
| Tx-O | At origination | Borrower (atomic-swap take) | Lender's principal → borrower; borrower's collateral → vault |
| Tx-Repay | Any time before maturity | Borrower | Repayment → lender; collateral → borrower |
| Tx-B | After maturity + grace, if no repayment | Lender | Collateral → lender |
| Tx-C (optional) | After far-future lockout | Borrower | Collateral → borrower (rescue if both abandoned) |

The **vault** is a 2-of-2 multisig holding the collateral. Two flavors:
- **Profile L** (p2sh) — VRSC collateral only, zero registration cost
- **Profile V** (VerusID i-address) — any currency collateral, sub-ID registration cost (~0.1 VRSC)

## What the user does

In a wallet UI: browse offers → click "Accept" → click "Repay" at maturity. Two clicks total. The wallet handles everything else.

In raw CLI / helper-script mode: 4 phases with ~10 RPC calls total per loan. Walked through below.

---

## Walkthrough — VRSC-collateralized loan, pure CLI

This is the simplest case. Everything works with stock `verus` CLI; no helper script needed.

**Loan terms**: Alice borrows 5 VRSC from Bob, putting up 10 VRSC as collateral. Repays 5.5 VRSC by block N+1000. Profile L vault.

### Step 1 — Derive the vault address

Both parties exchange compressed pubkeys (off-chain — DM, email, paper).

```bash
# Each party derives the same vault address from both pubkeys
ALICE_PUB=03e05933ec81c219e9aef5e5da4ea636f80864c8db9466e9cf090a26f6ca639640
BOB_PUB=0270b46dc0dcfe28b35cbd76ba54c5560c88b64b80ebc3cf515b7035b0891c8250

verus createmultisig 2 "[\"$ALICE_PUB\",\"$BOB_PUB\"]"
# Returns: {"address":"bYCcAqB7KfdkfsN8YUipb2fuFhKvxmsnne", "redeemScript":"..."}
```

The `b...` address is the vault. It exists deterministically on chain — no registration, no fee.

### Step 2 — Origination via makeoffer/takeoffer

Bob posts an offer giving 5 VRSC for 10 VRSC delivered to vault:

```bash
# Bob (lender)
verus makeoffer "BOB_R_ADDRESS" '{
  "changeaddress": "BOB_R_ADDRESS",
  "offer": {"currency":"VRSC", "amount":5},
  "for":   {"address":"BOB_R_ADDRESS", "currency":"VRSC", "amount":10}
}'
# (Note: same currency on both sides for VRSC-only loans is unusual;
#  a real loan would have different terms — this is just the mechanic)
```

Hmm — actually VRSC-for-VRSC isn't a useful trade. Let me redo with actual loan economics.

### Step 2 (corrected) — Origination

For a real loan, lender's principal is in one form; borrower's collateral is another (or same currency, different amounts).

Realistic VRSC-for-VRSC mechanic: lender lends 5 VRSC, borrower deposits 10 VRSC at vault. Same currency (VRSC) but different amounts. We can't do this via `makeoffer`/`takeoffer` (which expects different currencies), so we use the cooperative Tx-A approach:

```bash
# Both parties build Tx-A together
INPUTS='[{"txid":"<alice_collateral_utxo_txid>","vout":0},
         {"txid":"<bob_principal_utxo_txid>","vout":0}]'
OUTPUTS='{"<vault_address>":10,
          "<alice_R_address>":5,
          "<alice_change_address>":<change>,
          "<bob_change_address>":<change>}'

# Alice signs her input
verus createrawtransaction "$INPUTS" "$OUTPUTS" | \
  verus signrawtransaction
# (saves intermediate hex)

# Send hex to Bob, Bob signs his input
ssh bob 'verus signrawtransaction <hex>'

# Broadcast
verus sendrawtransaction <fully-signed-hex>
```

For a more interesting loan with actual cross-currency (e.g. VRSC collateral for DAI principal), `makeoffer`/`takeoffer` works directly. See [swap.md](./swap.md) for the swap mechanics.

### Step 3 — Cooperatively pre-sign settlement templates

Three templates: Tx-Repay, Tx-B, optionally Tx-C. Each follows the same pattern.

**Tx-Repay template:**

```bash
TXA_TXID=<from step 2>
REDEEM_SCRIPT=<from step 1>

# Build the unsigned template
INPUTS='[{"txid":"'$TXA_TXID'","vout":0}]'
OUTPUTS='{"BOB_R_ADDRESS":5.5}'        # repayment to Bob (sig-locked)
EXPIRY=$((CURRENT_BLOCK + 1000))       # Tx-Repay expires at maturity

verus createrawtransaction "$INPUTS" "$OUTPUTS" 0 $EXPIRY > /tmp/repay_unsigned.hex

# Alice cosigns
verus signrawtransaction $(cat /tmp/repay_unsigned.hex) null null "SINGLE|ANYONECANPAY" \
  > /tmp/repay_alice.json

# Bob cosigns (ship hex to bob's node)
ssh bob "verus signrawtransaction $(jq -r .hex /tmp/repay_alice.json) null null 'SINGLE|ANYONECANPAY'" \
  > /tmp/repay_signed.json

# Resulting hex held by ALICE (the borrower)
jq -r .hex /tmp/repay_signed.json > /tmp/tx_repay_template.hex
```

**Tx-B template** (similar, with `nLockTime = maturity + grace` and Output 0 = collateral to lender):

```bash
LOCKTIME=$((CURRENT_BLOCK + 1100))      # maturity + grace

verus createrawtransaction \
  '[{"txid":"'$TXA_TXID'","vout":0}]' \
  '{"BOB_R_ADDRESS":9.9999}' \
  $LOCKTIME > /tmp/txb_unsigned.hex

# Cosign as above
# ... (same pattern)

# Resulting hex held by BOB (the lender)
```

**Tx-C template** (optional, far-future locktime, output to borrower).

### Step 4 — Active loan period

Nothing happens on chain. Both parties hold their hex. Borrower uses the principal.

### Step 5a — Happy path: borrower repays

Any time before `expiryheight` of Tx-Repay:

```bash
# Alice broadcasts the pre-signed Tx-Repay as-is
verus sendrawtransaction $(cat /tmp/tx_repay_template.hex)
```

That's it. Pure CLI, no extension needed (since the collateral-pays-fee model has Output 1 fixed at origination). Lender receives 5.5 VRSC; borrower's collateral comes back via Output 1.

### Step 5b — Default path: lender claims after maturity

After block `LOCKTIME` (maturity + grace):

```bash
# Bob broadcasts the pre-signed Tx-B
verus sendrawtransaction $(cat /tmp/tx_b_template.hex)
```

Pure CLI. Lender claims 9.9999 VRSC; borrower's collateral is gone.

---

## Walkthrough — non-VRSC collateral or broadcaster-pays-fee variants

These need the helper script for the broadcast step. Recipe steps 1, 3, 5a/5b are identical to above; only the broadcast step differs.

**Step 5a alternative (broadcaster-pays-fee):**

Borrower wants the FULL collateral back (not `collateral - fee`). They attach their own VRSC fee input at broadcast time:

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

For non-VRSC collateral (Profile V vault holding DAI etc.), the broadcaster-pays-fee variant is REQUIRED because the vault has no VRSC for fees. Same helper script handles it.

---

## What works with pure stock CLI

| Phase | Pure CLI? |
|---|---|
| Step 1: vault derivation | ✅ `createmultisig` |
| Step 2: origination | ✅ `createrawtransaction` + cooperative `signrawtransaction` |
| Step 3: pre-sign templates | ✅ `signrawtransaction null null "SINGLE\|ANYONECANPAY"` |
| Step 5a: collateral-pays-fee Tx-Repay broadcast | ✅ `sendrawtransaction <hex>` |
| Step 5a: broadcaster-pays-fee Tx-Repay broadcast | ❌ needs `helpers/extend_tx.py` |
| Step 5b: collateral-pays-fee Tx-B broadcast | ✅ `sendrawtransaction <hex>` |
| Step 5b: broadcaster-pays-fee Tx-B broadcast | ❌ needs `helpers/extend_tx.py` |

For a purely VRSC-collateralized loan accepting the small fee deduction, **everything is pure stock CLI**.

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
1. Reads VerusID multimaps for `loan.offer.v1` entries (see [marketplace.md](./marketplace.md))
2. Renders offers with reputation summary
3. On "Accept", coordinates the multi-step ceremony via encrypted multimap entries
4. Stores templates as encrypted multimap entries on user's own VerusID
5. Displays "Repay" button when active; broadcasts Tx-Repay
6. Shows outcome in user's loan history after settlement

All complexity is hidden. User clicks two buttons total.

---

## Security considerations

### Key risks

1. **Lost templates** — if a party loses the pre-signed hex AND doesn't have multimap backup, they can't broadcast. Mitigation: store templates encrypted in own VerusID's multimap (Profile V) for seed-recovery.
2. **Predicted txid mismatch** — if Tx-A's actual txid differs from predicted (rare with deterministic ECDSA), the templates reference a non-existent UTXO and won't broadcast. Mitigation: abort and restart the ceremony.
3. **Validate received templates before signing** — when Alice receives Bob's pre-signed Tx-Repay template, her wallet MUST validate that Output 0 has the correct amount and is paying the agreed lender. The chain enforces what's signed; the wallet verifies what gets signed.
4. **Cross-currency tooling caveat** — for non-VRSC collateral inputs in templates, signing requires `signrawtransaction null null "SINGLE|ANYONECANPAY"` (the wallet key-lookup path). Explicit-key path fails. See [TESTING §32](../TESTING.md).

### What's chain-enforced (not trust)

- Borrower can repay unilaterally — no live cooperation from lender needed
- Lender can claim default unilaterally after maturity — no live cooperation from borrower
- Output 0 (the sig-locked payment) cannot be redirected or reduced — validated TESTING §24
- Settlement is atomic — either Tx-Repay or Tx-B, never both (validated §22, §29)
- Lender stonewalling at repayment is structurally impossible — the pre-signature settles unilaterally

### What still requires off-chain trust

- Identifying the counterparty in the first place (or use reputation — see [marketplace.md](./marketplace.md))
- Agreeing on terms before origination
- Subjective dispute resolution (use real-world courts; chain is admissible evidence)

---

## References

- [SPEC.md Part I](../SPEC.md) — formal protocol specification
- [TESTING.md §16-§32](../TESTING.md) — mainnet validations of every primitive
- Test txids: §16 `286ba62f...`, §18 `25564b4c...`, §22 (rejection), §32 `086fb3ee...`

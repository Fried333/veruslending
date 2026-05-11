# Recipe — options markets

Cryptographically-enforced fully-collateralized options. Writer locks underlying at vault; buyer pays premium upfront; before expiration buyer can exercise (atomic strike-for-underlying); after expiration writer recovers underlying. No oracle, no custodian, no platform.

## Roles

- **Writer** (Bob): provides underlying (e.g., 1 BTC), receives premium upfront, obligated to deliver if buyer exercises before expiration
- **Buyer** (Alice): pays premium, has the right (not obligation) to exercise — pay strike, receive underlying — before expiration

## What the protocol does

Five-phase lifecycle:

| Phase | When | Who | What | Channel |
|---|---|---|---|---|
| 1. Discovery | Writer publishes terms | Writer | `option.offer` multimap entry on writer's VerusID | chain (VerusID multimap) |
| 2. Coordination | Buyer wants to take | Both | Exchange pubkeys, derive vault | encrypted multimap entry, or paste |
| 3. Atomic setup | Both ready | Both | Atomic: premium → writer; underlying → vault | `makeoffer` / `takeoffer` |
| 4. Pre-sign templates | At setup | Both | Cooperatively pre-sign exercise + return | cooperative cosign |
| 5. Exercise / expire | Anytime / after locktime | Buyer or Writer | Settlement | unilateral broadcast |

The vault is a **2-of-2** between writer and buyer:
- **Profile L** (p2sh) — VRSC underlying only, zero registration cost
- **Profile V** (VerusID i-address) — any currency underlying, sub-ID registration cost (~0.1 VRSC). Required for non-VRSC underlying because the chain enforces non-VRSC outputs go to i-addresses.

## What the user does

In a wallet UI: writer clicks "Write call option" with terms; buyer browses options, clicks "Buy", later clicks "Exercise" or lets it expire. Two clicks for buyer; one click + waiting for writer.

In CLI mode: ~6 RPC calls per option lifetime.

---

## Walkthrough — covered call

**Terms**: Writer (Bob) sells a call on 1 VRSC. Strike = 0.5 DAI. Premium = 0.05 DAI. Expiration = block N+1000.

### Phase 1 — Discovery (writer publishes the option)

Bob posts his terms to his VerusID's multimap so anyone scanning the chain (or an explorer indexer) can find him. No buyer involved yet.

```bash
# Build the offer JSON
OFFER='{
  "version": 1,
  "type": "call",
  "underlying": {"currency":"VRSC",     "amount":1},
  "strike":     {"currency":"DAI.vETH", "amount":0.5},
  "premium":    {"currency":"DAI.vETH", "amount":0.05},
  "expiration_block": '"$(($(verus getblockcount) + 1000))"',
  "writer_pubkey": "<bob_compressed_pubkey>",
  "writer_address": "BOB_R_ADDRESS",
  "active": true
}'
HEX=$(echo -n "$OFFER" | python3 -c "import sys; print(sys.stdin.read().encode().hex())")

# Get the VDXF id for make.vrsc::contract.option.offer
verus getvdxfid "make.vrsc::contract.option.offer"
# Returns: {"vdxfid":"i5L8vkz9xsnM8yEDiXzPbP4Kix3SnJSsv5", ...}

# Write to Bob's VerusID
verus updateidentity '{
  "name": "bob.writer@",
  "contentmultimap": {
    "i5L8vkz9xsnM8yEDiXzPbP4Kix3SnJSsv5": ["'$HEX'"]
  }
}'
```

The offer is now publicly readable on chain. Buyers find it via direct ID lookup (`getidentity bob.writer@`) or via a chain indexer that scans for `make.vrsc::contract.option.offer` entries. See [marketplace.md](./marketplace.md).

### Phase 2 — Coordination (vault derivation)

Alice reads Bob's offer (chain-native, no comms required) and gets `writer_pubkey`. She then needs Bob to know HER pubkey so they can both compute the same 2-of-2 vault.

Two ways to send the buyer's pubkey:

- **Encrypted `option.accept` multimap entry on Alice's own VerusID**, addressed to Bob's z-key (chain-native, asynchronous)
- **Out-of-band paste** (Discord, email, QR — fine for known parties)

Once Bob has Alice's pubkey, both compute the same vault:

```bash
WRITER_PUB=<from offer>
BUYER_PUB=<from acceptance>

# For VRSC underlying (Profile L vault):
verus createmultisig 2 "[\"$WRITER_PUB\",\"$BUYER_PUB\"]"
# Returns: {"address":"b...", "redeemScript":"..."}

# For non-VRSC underlying (Profile V vault required):
# Cooperatively register a sub-ID with primaryaddresses=[both R-addrs] and minsig=2.
# The i-address of that ID is the vault.
```

Both parties now have the vault address.

### Phase 3 — Atomic setup (premium + underlying lock)

Single atomic tx via `makeoffer`/`takeoffer` with the vault as accept address (validated TESTING §36):

```bash
# Bob (writer) makes offer: GIVE 1 VRSC, FOR 0.05 DAI premium to Bob's address
ssh bob "verus makeoffer 'BOB_R_ADDRESS' '{
  \"changeaddress\": \"BOB_R_ADDRESS\",
  \"offer\": {\"currency\":\"VRSC\", \"amount\":1},
  \"for\":   {\"address\":\"BOB_R_ADDRESS\", \"currency\":\"DAI.vETH\", \"amount\":0.05}
}'"
# Returns: {"txid":"<offer-txid>"}

# Wait for offer to confirm

# Alice (buyer) takes the offer, ACCEPTING the underlying at the VAULT (computed in Phase 2)
verus takeoffer "ALICE_R_ADDRESS" '{
  "changeaddress": "ALICE_R_ADDRESS",
  "txid": "<offer-txid>",
  "deliver": {"currency":"DAI.vETH", "amount":0.05},
  "accept":  {"address":"VAULT_ADDRESS", "currency":"VRSC", "amount":1}
}'
# Returns: {"txid":"<setup-txid>"}
```

**Result**:
- Bob has +0.05 DAI premium (in his wallet, immediately)
- Vault has +1 VRSC (the underlying, locked under 2-of-2)
- Atomic: either both happen or neither
- Buyer can't pay premium without underlying being locked
- Writer can't pocket premium without underlying being committed

Pure stock CLI. No helper. **Validated mainnet — TESTING §36 (txid `c419b7fc...`).**

### Phase 4 — Cooperatively pre-sign exercise + return templates

```bash
TXSETUP=<setup-txid from step 1>

# Identify which vout has the 1 VRSC at vault (typically vout 1)
verus getrawtransaction $TXSETUP 1 | jq '.vout'

# Pre-sign EXERCISE tx: vault → strike to writer, with expiryheight = expiration_block
EXPIRATION_BLOCK=$((CURRENT + 1000))

verus createrawtransaction \
  '[{"txid":"'$TXSETUP'","vout":<vault_vout>}]' \
  '{"BOB_R_ADDRESS":{"DAI.vETH":0.5}}' \
  0 $EXPIRATION_BLOCK > /tmp/exercise_unsigned.hex

# Both parties cosign Input 0 with SIGHASH_SINGLE|ANYONECANPAY
verus signrawtransaction $(cat /tmp/exercise_unsigned.hex) null null "SINGLE|ANYONECANPAY" \
  > /tmp/exercise_alice.json

ssh bob "verus signrawtransaction $(jq -r .hex /tmp/exercise_alice.json) null null 'SINGLE|ANYONECANPAY'" \
  > /tmp/exercise_signed.json

# Held by ALICE (buyer)
jq -r .hex /tmp/exercise_signed.json > /tmp/exercise_template.hex


# Pre-sign UNDERLYING-RETURN tx: vault → underlying back to writer, nLockTime = expiration+1
LOCKTIME=$((EXPIRATION_BLOCK + 1))

verus createrawtransaction \
  '[{"txid":"'$TXSETUP'","vout":<vault_vout>}]' \
  '{"BOB_R_ADDRESS":1}' \
  $LOCKTIME > /tmp/return_unsigned.hex

# Cosign as above

# Held by BOB (writer)
```

### Phase 5 — Active period

Nothing happens on chain. Both parties hold their hex. Buyer holds exercise; writer holds return.

### Phase 6a — Exercise (buyer triggers, before expiration)

Buyer adds her DAI strike input to the template and broadcasts. **Needs the helper script** (broadcaster-pays-fee variant):

```bash
python3 helpers/extend_tx.py \
  --template /tmp/exercise_template.hex \
  --add-input "<alice_dai_strike_utxo>" \
  --add-input "<alice_vrsc_fee_utxo>" \
  --add-output "ALICE_R_ADDRESS:1.0:VRSC" \
  --add-output "ALICE_CHANGE:<dai_change>:DAI.vETH" \
  --add-output "ALICE_CHANGE:<vrsc_change>:VRSC" \
  > /tmp/exercise_extended.hex

verus signrawtransaction $(cat /tmp/exercise_extended.hex) > /tmp/exercise_complete.json
verus sendrawtransaction $(jq -r .hex /tmp/exercise_complete.json)
```

**Result**: Bob receives 0.5 DAI strike; Alice receives 1 VRSC underlying; vault is consumed.

### Phase 6b — Expiration (writer triggers, after locktime)

Writer adds VRSC fee input and broadcasts the return template:

```bash
python3 helpers/extend_tx.py \
  --template /tmp/return_template.hex \
  --add-input "<bob_vrsc_fee_utxo>" \
  --add-output "BOB_R_ADDRESS:<vrsc_change>" \
  > /tmp/return_extended.hex

ssh bob "verus signrawtransaction $(cat /tmp/return_extended.hex) | verus sendrawtransaction"
```

**Result**: Bob receives the underlying back; vault is consumed; Alice already lost the premium at setup.

---

## What works pure CLI

| Phase | Pure CLI? |
|---|---|
| Phase 1: discovery (post offer to multimap) | ✅ `updateidentity` |
| Phase 2: coordination (vault derivation) | ✅ `createmultisig` (Profile L) — Profile V needs sub-ID registration |
| Phase 3: atomic setup | ✅ `makeoffer` + `takeoffer` |
| Phase 4: pre-sign templates | ✅ `signrawtransaction null null "SINGLE\|ANYONECANPAY"` |
| Phase 6a: exercise | ❌ needs `helpers/extend_tx.py` |
| Phase 6b: expiration recovery | ❌ needs `helpers/extend_tx.py` |

Phases 1-4 are pure CLI. Phases 6a/6b need the helper for tx extension at broadcast time. Same gap as the lending protocol's Tx-Repay.

---

## What the wallet does

```
[Options tab]

  Available calls
    1 VRSC at strike 0.5 DAI, 30-day exp     premium 0.05 DAI
    bob.writer@   ✓ 47 settled / 2 defaulted   [ Buy ]
    
  My options (after buying)
    Long 1 VRSC call @ 0.5 DAI, expires in 7 days
    [ Exercise ]   |   [ Let expire ]
```

The wallet handles:
1. Browsing offers via VerusID multimap (see [marketplace.md](./marketplace.md))
2. Atomic setup (makeoffer + takeoffer with vault as accept)
3. Cooperative ceremony for exercise + return templates
4. Storing templates encrypted in user's own multimap
5. Notification + one-click exercise before expiration
6. Auto-broadcast return for writer after expiration

---

## Security considerations

### Trust profile

Single trust point: **buyer pays premium upfront in the same atomic tx as vault funding**. After that single tx confirms, NO further trust is required:

- Writer cannot rug-pull (underlying is locked at 2-of-2, can't unilaterally release)
- Writer cannot pocket premium without the option being created (atomic at setup)
- Buyer cannot underpay strike (pre-signed Output 0 sig-lock)
- Buyer cannot exercise after expiration (`expiryheight` enforced)
- Writer cannot reclaim underlying before expiration (`nLockTime` enforced)

Compare: traditional options markets need a custodian (or smart contract code) to enforce these properties. Here the chain enforces them via existing primitives.

### What still requires trust

- Counterparty discovery (use trade history via VerusID multimap; see [marketplace.md](./marketplace.md))
- Agreeing on terms (premium, strike, expiration) before setup
- Pricing / market-making — out of scope

### Validated edge cases

- ✅ Exercise before expiration — TESTING §26 (txid `f48ba0c3...`)
- ✅ Expiration without exercise — writer recovers underlying via return tx — TESTING §27 (txid `4c53edf6...`)
- ✅ Exercise broadcast attempt after expiration rejected with `tx-expiring-soon` — TESTING §27
- ✅ Output 0 tampering rejected (buyer can't redirect or underpay strike) — TESTING §24

---

## References

- [SPEC.md Appendix C](../SPEC.md) — primitive's general applications
- [TESTING.md §26, §27, §36](../TESTING.md) — full options lifecycle validation
- [recipes/marketplace.md](./marketplace.md) — discovering options offers

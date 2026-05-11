# Recipe — chain-native marketplace data layer

The Verus contentmultimap is a key-value store on every VerusID. With standardized VDXF keys, it functions as a fully decentralized marketplace data layer — anyone can post offers, anyone can read them, no server required.

## What this is

A **chain-native marketplace** for any of the protocol's use cases — lending, options, escrow, swaps, ID transfers. Posters write offers as multimap entries; browsers read entries from any VerusID.

No platform operator. No matching engine. No API. Just `getidentity` and `updateidentity`.

**Validated mainnet — TESTING §33** (txid `694ed5cf...` — loan offer published, read identically from two independent nodes).

## Roles

- **Poster**: writes an offer/request entry to their VerusID's multimap
- **Browser**: queries any VerusID's multimap for offer/request entries
- **Acceptor**: matches with an offer; initiates the cooperative ceremony

## What the protocol provides

Standard VDXF keys for marketplace entries (full registry in [SCHEMA.md](../SCHEMA.md)):

| Key | VDXF id | Purpose |
|---|---|---|
| `make.vrsc::contract.loan.offer`     | `iMey7Y2idT6dt7jJvRiPXgtYcfAaKCQbHz` | Lender publishes terms |
| `make.vrsc::contract.loan.request`   | `iF7Ax6QpdwvTTqDJpNzDXVj1GpUSQX6vH5` | Borrower publishes terms |
| `make.vrsc::contract.loan.history`   | `i5qBwi3KWXfyo1UKuUBC3yyq67JagVennW` | Outcome attestations (trade history) |
| `make.vrsc::contract.loan.status`    | `iRzM96sNYj95mUiJebzBnFwirjfws2q6o4` | Active loan state |
| `make.vrsc::contract.loan.accept`    | `iLr7w7k8Ty9tVHccBqzXfAud1wXY1QYsBy` | Borrower's acceptance (encrypted) |

Equivalent keys exist for options / escrow / swap (`make.vrsc::contract.option.offer`, `make.vrsc::contract.escrow.offer`, `make.vrsc::contract.swap.offer` etc). All use the same `make.vrsc::contract.<usecase>.<entity>` convention. See SCHEMA.md for the full set.

## What the user does

**Posters** click "Post offer" in their wallet; specify terms; wallet writes the multimap entry.

**Browsers** open the wallet's marketplace tab; see filtered, offers from various VerusIDs filtered against on-chain trade history; click "Accept" to initiate the ceremony with one party.

In CLI mode: 2 commands — `updateidentity` to post, `getidentity` to read.

---

## Walkthrough — post a loan offer

### Step 1 — Build the offer JSON

```json
{
  "version": 1,
  "type": "lend",
  "principal": {"currency":"VRSC", "amount":5},
  "collateral": {"currency":"VRSC", "amount":10},
  "rate": 0.10,
  "term_days": 30,
  "lender_pubkey": "<your_compressed_pubkey>",
  "lender_address": "<your_R_address>",
  "valid_until_block": <future_block>,
  "active": true
}
```

### Step 2 — Hex-encode the JSON

```bash
OFFER_JSON='{"version":1,"type":"lend",...}'
OFFER_HEX=$(echo -n "$OFFER_JSON" | python3 -c "import sys; print(sys.stdin.read().encode().hex())")
```

### Step 3 — Get the VDXF key

```bash
verus getvdxfid "make.vrsc::contract.loan.offer"
# Returns: {"vdxfid":"iMey7Y2idT6dt7jJvRiPXgtYcfAaKCQbHz", ...}
```

The VDXF id is deterministic; everyone computing it gets the same result.

### Step 4 — Write to your VerusID's multimap

```bash
VDXF_KEY=iMey7Y2idT6dt7jJvRiPXgtYcfAaKCQbHz

verus updateidentity "{
  \"name\": \"<your_id_name>\",
  \"parent\": \"<your_id_parent>\",
  \"contentmultimap\": {
    \"$VDXF_KEY\": [\"$OFFER_HEX\"]
  }
}"
# Returns: <txid>
```

After this confirms, your offer is live on chain. Anyone running a Verus node can see it.

### Step 5 — Browser reads the offer

From any Verus node, anywhere:

```bash
verus getidentity "<your_id>" | jq '.identity.contentmultimap'
# Returns:
# {
#   "iMey7Y2idT6dt7jJvRiPXgtYcfAaKCQbHz": [
#     "7b2276657273696f6e..."   # hex-encoded JSON
#   ]
# }

# Decode:
echo "7b2276657273696f6e..." | python3 -c "import sys; print(bytes.fromhex(sys.stdin.read().strip()).decode('utf-8'))"
# Returns the original offer JSON
```

That's the marketplace. **Pure stock CLI on both sides.**

---

## Walkthrough — write trade history history entry

After a loan settles, both parties write a history entry to their own multimap. **Asymmetric writes — no co-signing across IDs needed**; the truth is the on-chain settlement tx, the multimap entry is just a queryable index.

```json
{
  "version": 1,
  "vault_address": "bYCcAqB7...",
  "role": "lender",
  "counterparty_id": "borrower.alice@",
  "principal": {"currency":"VRSC", "amount":5},
  "collateral": {"currency":"VRSC", "amount":10},
  "rate": 0.10,
  "term_days": 30,
  "originated_tx": "<txid>",
  "originated_block": <number>,
  "outcome": "settled",
  "outcome_tx": "<txid>",
  "outcome_block": <number>
}
```

Same `updateidentity` flow as above, with VDXF key for `make.vrsc::contract.loan.history`.

---

## What the wallet does

```
[Marketplace tab]

  Filters: [VRSC ▼] [< 10% rate] [≥ 30d] [trade history ≥ 95%]
  
  bob.lender@         5 VRSC for 10 VRSC, 8% / 30d
                      47 settled / 2 defaulted (96%) | tenure 487d
                      [ Accept ]
  
  desk.lendingco@     1000 DAI for 2k VRSC, 8% / 90d  
                      312 settled / 5 defaulted (98%) | tenure 942d
                      [ Accept ]
```

The wallet:
1. Queries known/discovered VerusIDs for `make.vrsc::contract.loan.offer` (or `make.vrsc::contract.option.offer`, etc.)
2. Decodes hex JSON
3. Aggregates each lender's `make.vrsc::contract.loan.history` entries → trade history summary
4. Renders with filtering/sorting
5. On "Accept", initiates the cooperative ceremony (more multimap writes, encrypted)

For a wallet implementing this, the work is:
- Write a multimap browser (~50 lines of code per wallet)
- Implement trade-history summary (~50 lines)
- Reuse existing Verus daemon RPC for read/write

---

## Discovery scaling

### Pattern A — walk all VerusIDs (doesn't scale)

You can't easily query "all VerusIDs with a `make.vrsc::contract.loan.offer` entry." Verus's `listidentities` returns local wallet IDs only.

### Pattern B — known parent ID convention

Lenders register sub-IDs under a well-known parent (e.g., `loan001.lend@`, `loan002.lend@`). Browsers query the parent's children:

```bash
# Get all sub-IDs under "lend@"
verus listidentities | jq '.[] | select(.identity.parent == "<lend_iaddr>")'
```

This gives a bounded set to query. **Recommended pattern**.

### Pattern C — explorer indexing (most scalable)

Block explorers index the chain for `updateidentity` calls with marketplace-relevant VDXF keys, maintain searchable caches. Multiple competing explorers possible. Wallets can hit them as a discovery API while still verifying entries directly via daemon.

---

## Encrypted multimap entries

Some entries are public (`make.vrsc::contract.loan.offer`); others should be encrypted (acceptance, ceremony coordination, settlement templates).

### Public entries

```json
{ "make.vrsc::contract.loan.offer": ["<hex of JSON>"] }
```

Anyone can decode. Use for offers, requests, public history.

### Encrypted entries

Encrypt the payload to the recipient's identity z-key, then hex-encode the ciphertext:

```bash
# Pseudocode (Verus has identity-based z-encryption primitives)
PAYLOAD_JSON='{"target_offer":"...","borrower_pubkey":"..."}'
CIPHERTEXT=$(verus z_encrypt_to_identity "<recipient_id>" "$PAYLOAD_JSON")
HEX_CIPHERTEXT=$(echo -n "$CIPHERTEXT" | xxd -p | tr -d '\n')

verus updateidentity "{ \"contentmultimap\": { \"<encrypted_vdxf_key>\": [\"$HEX_CIPHERTEXT\"] } }"
```

Recipient decrypts using their identity z-key (derived from their seed).

### Use cases for encrypted entries

- **Acceptance**: borrower's "I'll take your offer, here's my pubkey" — encrypted to lender
- **Ceremony coordination**: half-signed tx hex — encrypted between parties
- **Settlement template backup**: pre-signed Tx-Repay/B/C — encrypted to self for seed-recovery

---

## Security considerations

### What multimap entries can and can't enforce

- ✅ **Posting an offer** — anyone can post; the multimap is permissionless
- ✅ **Reading an offer** — anyone can read; everything's public
- ✅ **Writing trade history history** — any party can write to their own multimap; the chain enforces who controls which ID
- ❌ **Truthful posting** — the multimap doesn't validate that an offer's claims are honest; trade-history summary is the trust layer

### Anti-spam considerations

- Each multimap write is an `updateidentity` tx — costs tx fees
- Spam offers exist but can be filtered by trade history
- Wallets should sort by trade history/freshness, not just by recency

### Sybil defenses

Trade history gaming via fake VerusID networks is possible but observable on chain. See [SPEC §15](../SPEC.md#15-sybil-resistance-signals) for the observable signals.

---

## References

- [SPEC.md Part II](../SPEC.md) — full data layer specification
- [TESTING.md §33](../TESTING.md) — cross-node readability validated
- [SPEC.md §13](../SPEC.md) — trade history/credit identity layer

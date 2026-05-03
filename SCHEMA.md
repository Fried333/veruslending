# SCHEMA — chain data layer

Canonical reference for the on-chain data layer used by VerusLending and
related contract primitives. This is the *interop contract*: any wallet,
indexer, or library that follows this spec can read/write the same
entries as the reference implementation.

The chain is the source of truth. Indexers (`.85`, others) cache and
expose this data, but never amend or override what's on chain.

---

## 1. VDXF key namespace

All keys live under the VRSC system namespace (`vrsc::`) under the
top-level category `contract`. This sits at the same level as Verus's
existing `system`, `profile`, and `contentmultimap` categories.

```
vrsc::contract.<usecase>.<entity>
```

Singular `contract` matches Verus's own convention (`system`, `profile`,
`contentmultimap` are all singular).

### Locked VDXF keys

| Key | VDXF id | Purpose | Visibility |
|---|---|---|---|
| `vrsc::contract.loan.offer`     | `iA1vgVBV5B29h5pxQ67gxqCoEaLDZ8WbmY` | lender's terms | public |
| `vrsc::contract.loan.request`   | `iPmnErqWbf5NhhWZEoccuX8yU8CgFt2d28` | borrower's terms | public |
| `vrsc::contract.loan.history`   | `i92jad9CSjBNPCHgnHqQP4hK1facXBFDWb` | settled outcome attestation | public |
| `vrsc::contract.loan.status`    | `iP5b6uX8SM7ZSiiMbVWwGj9wG76KuJWZys` | active loan state | public |
| `vrsc::contract.loan.accept`    | `iLr7w7k8Ty9tVHccBqzXfAud1wXY1QYsBy` | acceptance handshake | encrypted |
| `vrsc::contract.loan.template`  | `i7HCaxjju3QRYmbC23g5QD2smMk4PqaXFq` | pre-signed tx backup | encrypted (self) |
| `vrsc::contract.option.offer`   | `i4a42EUWLvJTHYGW7F8RifY1Rvs5AQGioY` | option writer's terms | public |
| `vrsc::contract.option.history` | `iEdahQZgGRhECPfHTvb1P8C7y5LVaqKvjt` | option outcome | public |
| `vrsc::contract.option.status`  | `iK8rYBePsedzPGA1Hi9vnu6Q2KKegfKqcU` | active option state | public |
| `vrsc::contract.option.accept`  | `iFHZXqCZotgb2KnBWx2tXZTsBrNSdiuNh8` | option acceptance | encrypted |
| `vrsc::contract.option.template`| `iPUF3WuEdz8UMZERrifLL5xDujVDvr8EwA` | option templates | encrypted (self) |
| `vrsc::contract.escrow.offer`   | `iHpajXqKrTDDMo7JQwzjuxkiSExhkWM3hZ` | escrow service offer | public |
| `vrsc::contract.escrow.history` | `iDUTbfMdv6h1M6pufxMT6Q6DTVGSDH1c5K` | escrow outcome | public |
| `vrsc::contract.escrow.status`  | `i5ymyC5CX47okFKhLzjd1jws3A6c4zA4TZ` | active escrow state | public |
| `vrsc::contract.escrow.accept`  | `iL6CknRLami1deqoA7QgcTA74jQZZ1aNm6` | escrow acceptance | encrypted |
| `vrsc::contract.escrow.template`| `iN7tcUBzvJcNKjgdSXquiKKLoX36TkpZfM` | escrow templates | encrypted (self) |
| `vrsc::contract.swap.offer`     | `iMJXdbEqZ1wS4SGKSJGFp4vzcDUhhciZGV` | atomic swap offer | public |

VDXF ids are deterministic from the key string. Re-derive via
`verus getvdxfid "vrsc::contract.loan.offer"`.

### Versioning

Versioning happens **inside the JSON payload**, not in the key name.
Verus keys never use `.vN` suffixes — the key id is stable, payloads
embed `version: <int>`. Schema upgrades bump the internal version;
readers handle multiple versions gracefully.

```json
{ "version": 1, "type": "lend", … }
```

---

## 2. Storage format

Each multimap entry is a **hex-encoded UTF-8 JSON string** stored in the
identity's `contentmultimap` array under the appropriate VDXF id.

```
contentmultimap:
  iA1vgVBV5B29h5pxQ67gxqCoEaLDZ8WbmY:
    - "7b2276657273696f6e223a312c..."   # hex(JSON.stringify(payload))
    - "7b2276657273696f6e223a322c..."   # additional offer (multimap = array)
```

### Encoding rules

- Compact JSON (no whitespace, sorted keys preferred but not required)
- UTF-8
- Hex (lowercase)
- One entry per offer/state. Multiple offers per ID = multiple array elements.

### Encrypted entries

For `*.accept` and `*.template` keys:

1. Build payload JSON
2. Encrypt to recipient's identity z-key (or self for templates)
3. Hex-encode the ciphertext
4. Store same as public entries

Encryption uses Verus's identity z-encryption primitives. Recipients
decrypt with their seed-derived z-key.

### Updates and deletes

- **Update**: write the entire array back with the modified entry
- **Delete**: write the array without the entry, OR set `active: false`
  in the payload to soft-delete (preserves history while signaling stale)
- **Replace**: same as update — chain only sees the latest array

---

## 3. Payload schemas

### `contract.loan.offer` — lender posts terms

```json
{
  "version": 1,
  "type": "lend",
  "principal":  { "currency": "VRSC", "amount": 5 },
  "collateral": { "currency": "VRSC", "amount": 10 },
  "rate": 0.10,
  "term_days": 30,
  "lender_pubkey": "03...",
  "lender_address": "R...",
  "valid_until_block": 4070000,
  "active": true,
  "posted_block": 4050546,
  "memo": "optional human note"
}
```

### `contract.loan.request` — borrower posts request

```json
{
  "version": 1,
  "type": "borrow",
  "principal_wanted":   { "currency": "VRSC", "amount": 5 },
  "collateral_offered": { "currency": "VRSC", "amount": 10 },
  "max_rate": 0.15,
  "term_days": 30,
  "borrower_pubkey": "03...",
  "borrower_address": "R...",
  "valid_until_block": 4070000,
  "active": true,
  "posted_block": 4050546
}
```

### `contract.loan.status` — active loan (one entry per role per loan)

Posted at origination, removed/marked-settled at settlement.

```json
{
  "version": 1,
  "vault_address": "b...",
  "role": "lender" | "borrower",
  "counterparty_id": "alice.foo@",
  "counterparty_address": "R...",
  "counterparty_pubkey": "03...",
  "principal":  { "currency": "VRSC", "amount": 5 },
  "collateral": { "currency": "VRSC", "amount": 10 },
  "rate": 0.10,
  "term_days": 30,
  "originated_tx": "...",
  "originated_block": ...,
  "maturity_block": ...,
  "grace_blocks": 100
}
```

### `contract.loan.history` — outcome attestation

Both parties write at settlement. Truth is the on-chain settlement tx;
this is just an indexable summary for reputation.

```json
{
  "version": 1,
  "vault_address": "b...",
  "role": "lender" | "borrower",
  "counterparty_id": "alice.foo@",
  "counterparty_address": "R...",
  "principal":  { "currency": "VRSC", "amount": 5 },
  "collateral": { "currency": "VRSC", "amount": 10 },
  "rate": 0.10,
  "term_days": 30,
  "originated_tx": "...",
  "originated_block": ...,
  "outcome": "settled" | "defaulted" | "rescued",
  "outcome_tx": "...",
  "outcome_block": ...
}
```

### `contract.loan.accept` — encrypted

Borrower → lender after deciding to take an offer. Contains borrower's
pubkey + R-addr so lender can derive the vault and proceed.

```json
{
  "version": 1,
  "target_offer_txid": "...",
  "target_offer_index": 0,
  "borrower_pubkey": "03...",
  "borrower_address": "R...",
  "proposed_block": 4050600
}
```

Encrypted to lender's identity z-key, hex-encoded ciphertext.

### `contract.loan.template` — encrypted (self)

Backup of pre-signed Tx-Repay / Tx-B / Tx-C templates so they survive a
wiped browser. Encrypted to self.

```json
{
  "version": 1,
  "vault_address": "b...",
  "tx_repay_hex": "...",
  "tx_b_hex": "...",
  "tx_c_hex": "..."
}
```

### Options / Escrow / Swap

Same shape, different fields. Schemas TBD as those flows mature. Key
ids are pre-allocated above to avoid future churn.

---

## 4. Indexer requirements (e.g., `.85` and any alternative)

An indexer SHOULD:

- Track new blocks; for each, scan `updateidentity` txs
- Extract `contentmultimap` entries against the locked VDXF ids
- Decode hex → UTF-8 → JSON; validate against the published schema
- Store with metadata: source iaddress + friendly, vdxf_key, entry_index,
  block height/timestamp, txid
- Mark previous entries with same `(source, vdxf_key, entry_index)` as
  `replaced` when superseded
- Auto-mark `expired` when `valid_until_block` (or equivalent) passes
- Expose query API (see API spec below)

An indexer MUST NOT:

- Hold funds or facilitate transactions
- Match counterparties on its server
- Charge fees per offer / take / settlement
- Rewrite or curate chain content (filtering for display is fine; the
  underlying data must remain queryable)

The indexer is a **passive directory**. Same legal profile as a block
explorer.

---

## 5. API spec (any compliant indexer)

```
GET  /api/contract.loan.offer
       ?currency=VRSC&min_principal=1&max_term=90&active=true&limit=50&offset=0
GET  /api/contract.loan.offer/{id_or_iaddress}
GET  /api/contract.loan.history/{id_or_iaddress}
GET  /api/contract.loan.status/{vault_address_or_id}
GET  /api/contract.option.offer
GET  /api/contract.escrow.offer
GET  /api/contract.swap.offer
GET  /api/vdxf/{vdxf_key_or_id}            # generic — any tracked key
```

### Response shape (uniform)

```json
{
  "results": [
    {
      "source": {
        "id": "108of200.vlotto@",
        "iaddress": "i44CxABWkVnUhoPMjuM2ViJDDu2icd7jg7",
        "friendly": "3965555_108of200.vlotto@"
      },
      "vdxf_key": "vrsc::contract.loan.offer",
      "vdxf_id": "iA1vgVBV5B29h5pxQ67gxqCoEaLDZ8WbmY",
      "entry_index": 0,
      "payload": { "...decoded JSON..." },
      "raw_hex": "7b22...",
      "chain": {
        "txid": "...",
        "block": 4050546,
        "timestamp": 1746245678
      },
      "status": "active" | "replaced" | "expired"
    }
  ],
  "next_offset": 50,
  "indexed_through_block": 4050591
}
```

### Conventions

- No POST endpoints — read-only
- No auth
- CORS-enabled
- 200 OK with empty `results: []` when nothing matches
- 4xx for malformed queries; 5xx for indexer errors

---

## 6. Reference schema for postgres (suggested)

```sql
CREATE TABLE chain_entries (
  id SERIAL PRIMARY KEY,
  vdxf_key TEXT NOT NULL,
  vdxf_id  TEXT NOT NULL,
  source_iaddress TEXT NOT NULL,
  source_friendly TEXT,
  entry_index INT NOT NULL,
  payload JSONB NOT NULL,
  raw_hex TEXT NOT NULL,
  block_height INT NOT NULL,
  block_timestamp BIGINT,
  txid TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active',
  observed_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX ON chain_entries (vdxf_key, status, block_height DESC);
CREATE INDEX ON chain_entries (source_iaddress);
CREATE INDEX ON chain_entries (txid);
```

---

## 7. Open questions / future

- **Project namespace**: should `contract.*` move under a registered
  `contracts@` or `verus-contracts@` parent ID for stronger isolation?
  Costs ~100 VRSC for the top-level. Defer until something forces it.
- **Encrypted entry indexing**: should the API expose encrypted entries
  in raw form, or omit them? Currently SHOULD include — readability
  by recipient is up to them.
- **Schema validation**: should indexers reject entries failing schema?
  Currently SHOULD store-and-mark-malformed, not drop, so authors can
  see their bad data in the API.

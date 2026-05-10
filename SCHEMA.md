# SCHEMA — chain data layer

Canonical reference for the on-chain data layer used by VerusLending and
related contract primitives. This is the *interop contract*: any wallet,
indexer, or library that follows this spec can read/write the same
entries as the reference implementation.

The chain is the source of truth. Indexers (`.85`, others) cache and
expose this data, but never amend or override what's on chain.

---

## 1. VDXF key namespace

All keys live under the registered standard owner **`make.VRSC@`**
(`iLWvRsiWVCEuFYhCSt2Qba7LxWksrgVerX`) — sub-namespace of VRSC's identity
system. Format:

```
make.vrsc::contract.<usecase>.<entity>
```

The `make@` identity is the published owner of this standard. Anyone
verifying the canonical VDXF id for a slug computes
`verus getvdxfid "make.vrsc::contract.<slug>"` and gets the
deterministic i-address listed below.

### Locked VDXF keys

| Key | VDXF id | Purpose | Visibility |
|---|---|---|---|
| `make.vrsc::contract.loan.offer`     | `iMey7Y2idT6dt7jJvRiPXgtYcfAaKCQbHz` | lender's rate sheet | public |
| `make.vrsc::contract.loan.request`   | `iF7Ax6QpdwvTTqDJpNzDXVj1GpUSQX6vH5` | borrower's specific request | public |
| `make.vrsc::contract.loan.match`     | `iKVShS5o56BLn8BpysrmfvUJbWCrgyio8U` | lender's pre-signed funding offer for a specific request | public |
| `make.vrsc::contract.loan.status`    | `iRzM96sNYj95mUiJebzBnFwirjfws2q6o4` | active loan state (per party) — dropped on settle | public |
| `make.vrsc::contract.loan.history`   | `i5qBwi3KWXfyo1UKuUBC3yyq67JagVennW` | settled outcome attestation (terminal record) | public |
| `make.vrsc::contract.loan.decline`   | `iEgciB3u2GwTxzShQR4eFhtj4k8Zv6frNb` | lender's "polite no" to a request | public |
| `make.vrsc::contract.option.offer`   | `i5L8vkz9xsnM8yEDiXzPbP4Kix3SnJSsv5` | option writer's terms | public |
| `make.vrsc::contract.option.history` | `iEpGx4EYQhyisfmavGcRdEBvBeTo8eV2vj` | option outcome | public |
| `make.vrsc::contract.option.status`  | `iG2byqSwFf4aABPgyMNUEiqPEKrrzYxDxA` | active option state | public |
| `make.vrsc::contract.option.accept`  | `i8wykTMkYtmWD5Kj9xvA2yDTuBM9GCf615` | option acceptance | encrypted |
| `make.vrsc::contract.option.template`| `iNpgbdquf8nahoaxypQReNhmWQ4ACxHy5i` | option templates | encrypted (self) |
| `make.vrsc::contract.escrow.offer`   | `iKc8vAPTCaRDdPFa1CRbinByDCCtgXDnc4` | escrow service offer | public |
| `make.vrsc::contract.escrow.history` | `iNY8KSoyvbJEuGc6Ji7qFmGkC3Zs15ehLe` | escrow outcome | public |
| `make.vrsc::contract.escrow.status`  | `iFAqSsJ5Gk6meJhBmo8FoyJZdEzHDBZuXU` | active escrow state | public |
| `make.vrsc::contract.escrow.accept`  | `i8kjTVynpRb2TtgHdbCEo1GJSqysm421ec` | escrow acceptance | encrypted |
| `make.vrsc::contract.escrow.template`| `iA6iyv6DgXv8mBPmzejo33hqbVCuFqMjHj` | escrow templates | encrypted (self) |
| `make.vrsc::contract.swap.offer`     | `iPCV1rCMCJuBey8Ntu9f6x9JVehzqbBMUD` | atomic swap offer | public |

VDXF ids are deterministic from the key string. Re-derive via
`verus getvdxfid "make.vrsc::contract.loan.offer"`.

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
- **Delete**: write the array without the entry. Past revisions are
  preserved in `getidentityhistory` — the chain remembers everything.
- **Replace**: same as update — chain only sees the latest array

### Lifecycle convention: live entries describe open positions

`loan.status` (and analogously `loan.match`, future `option.position`,
future `margin.position`) are **live entries** — they describe an
*open* position. When that position closes (`Tx-Repay` for a loan,
`Tx-B` claim for default, exercise / expiry for an option), the live
entry is **dropped** from the multimap. The companion **`loan.history`**
(or `option.history` / `margin.history`) entry is the canonical
terminal record.

In other words: presence of `loan.status` for a `loan_id` ⇔ the loan
is open. Absence ⇔ either it never existed or it has settled (check
`loan.history` for the outcome).

The earlier "soft-delete with `active: false`" pattern is **deprecated**.
On-chain entries with `active: false` exist from before this convention
landed; readers should treat them as terminal-state markers (lookup
companion `loan.history` for the outcome) but not produce new ones.

> **Rationale.** A live entry advertising that it's no longer live is a
> contradiction. The original soft-delete was a workaround for readers
> that didn't know about `loan.history`; with `loan.history` always
> written on settle, dropping the live entry is cleaner, prevents
> indefinite multimap growth, and keeps "is X currently active?"
> queries honest.

---

## 3. Payload schemas

### `contract.loan.offer` — lender posts a rate sheet

A lender's *advertising material*: "I'll lend up to X, accepting these
collateral currencies, requiring this collateralization, at this rate."
Borrowers post `loan.request` against this; lenders pre-sign `loan.match`
against specific requests they want to fund.

```json
{
  "version": 1,
  "max_principal":        { "currency": "DAI", "amount": 100 },
  "accepted_collateral":  ["VRSC", "DAI", "BTC"],
  "min_collateral_ratio": 2.0,
  "rate":                 0.01,
  "term_days":            30,
  "active":               true,
  "memo":                 "optional human note"
}
```

### `contract.loan.request` — borrower posts a specific request

A borrower's exact terms: "I want to borrow X, willing to put up Y, will
repay Z by maturity." No `max_rate` — the borrower pre-states the
repayment they're willing to honor; the implied rate is `(repay/principal − 1)`.

**v2 (current)** — adds the borrower's pre-signed Tx-A input plus the
target lender. The borrower constructs the full Tx-A skeleton (their input,
their change output, the principal output going to themselves, and the
collateral output going to the 2-of-2 vault P2SH derived from both pubkeys)
and signs their own input with `SIGHASH_ALL|ANYONECANPAY`. The lender can
then add their own input and pre-sign all three settlement templates (Tx-A,
Tx-Repay, Tx-B) in one shot at match-post time, then go offline forever.

Required fields:
- `target_lender_iaddr` — the borrower picked a specific lender to direct
  this request at; the lender's pubkey is resolved from this iaddr's
  primary R-address.
- `borrower_input_signed_hex` — Tx-A skeleton hex with the borrower's
  input signed `SIGHASH_ALL|ANYONECANPAY`. The hex contains:
    - 1 input: borrower's collateral UTXO (signed)
    - 3 outputs: principal → borrower's R, collateral → vault P2SH, change
  The lender extends by adding input 0 (their principal UTXO) before
  signing their own portion.

```json
{
  "version": 2,
  "principal":  { "currency": "DAI",  "amount": 5 },
  "collateral": { "currency": "VRSC", "amount": 10 },
  "repay":      { "currency": "DAI",  "amount": 5.05 },
  "term_days":  30,
  "target_lender_iaddr":      "i7A9fa…",
  "borrower_input_signed_hex": "0400008085202f8901…",
  "active":     true
}
```

**v1 (legacy)** — terms only, no UTXO commitment, no signed input. Indexers
and GUIs should still read v1 entries (older requests on chain remain valid),
but matches against v1 requests can't be fully pre-signed — they need a
cooperative cosigning handshake at accept time, which is an older flow not
maintained here.

### `contract.loan.match` — lender pre-signs a funding offer

Posted on the lender's identity, points at a specific borrower's request,
and contains all three pre-signed partial transactions needed for the
borrower to atomically originate the loan with one click.

The lender's principal UTXO is committed via `SIGHASH_SINGLE|ANYONECANPAY`
on `tx_a_partial`. The lender's vault-half signatures on Tx-Repay and Tx-B
templates ensure the loan can be settled cooperatively or defaulted on at
maturity, even if the lender never comes online again.

```json
{
  "version": 1,
  "request": {
    "iaddr": "iFmi…goy",
    "txid":  "5ea5ad…",
    "block": 4051726
  },
  "lender_address":      "R...",
  "vault_address":       "b...",
  "vault_redeem_script": "<hex of OP_2 <lender_pubkey> <borrower_pubkey> OP_2 OP_CHECKMULTISIG>",
  "tx_a_partial":        "<hex, lender input signed SIGHASH_SINGLE|ANYONECANPAY>",
  "tx_repay_partial":    "<hex, lender vault-half signed SIGHASH_SINGLE|ANYONECANPAY>",
  "tx_b_partial":        "<hex, lender vault-half signed SIGHASH_SINGLE|ANYONECANPAY, locktime=maturity>",
  "expires_block":       4060000,
  "active":              true
}
```

The lender's bound UTXO can be verified as still-unspent by checking
on chain — explorer endpoints (`/api/contracts/loans/matches`) include
this verification in their response so the borrower's wallet can flag
stale matches.

### `contract.loan.status` — active loan (one entry per role)

Posted by both parties to their own identities after Tx-A confirms.
The pair of entries (one per role) makes the loan publicly visible
and correlatable. `loan_id` is the Tx-A txid (shared identifier).

`request_txid` (v3+) is the txid of the borrower's `loan.request` post.
It propagates from the request through `loan.match.request.txid` into
the status entry — letting any consumer join all four lifecycle entries
(request, match, status, history) by a single key regardless of stage.

```json
{
  "version": 3,
  "loan_id":          "5e386061…cda4bd",
  "request_txid":     "65a578f6…eaa93",
  "role":             "lender" | "borrower",
  "counterparty":     "i7A9…wg" | "iFmi…goy",
  "vault_address":    "b...",
  "principal":        { "currency": "VRSC", "amount": 5 },
  "collateral":       { "currency": "VRSC", "amount": 10 },
  "repay":            { "currency": "VRSC", "amount": 5.05 },
  "term_days":        30,
  "originated_block": 4051862,
  "maturity_block":   4095062,
  "settled":          false,
  "settled_tx":       null
}
```

When the loan settles (Tx-Repay broadcast, Tx-B broadcast, or rescue),
each party flips `settled: true` and writes `settled_tx: <txid>` so
indexers can derive outcome.

### `contract.loan.history` — outcome attestation

Both parties write at settlement. Truth is the on-chain settlement tx;
this is just an indexable summary for reputation.

**Retention.** Verus enforces a per-stack-element cap on `updateidentity`
payloads (see TESTING.md §37): the per-VDXF-key blob in the *current*
multimap can hold roughly 5–6 entries before the daemon rejects the
update with `bad-txns-script-element-too-large`.

This only bounds the **live** multimap. Every prior identity revision
is preserved on chain (via `getidentityhistory`), the explorer's
`/identity/events?type=loan.history&history=true` returns the full
union across revisions, and the GUI persists a local cache at
`~/.verus_contract_gui/history_cache.json` that holds every historical
row. So full history is recoverable from at least three places — the
chain itself, the explorer index, and the local cache.

- **Writers** trim the live `loan.history` array when posting a new
  entry (keep the most recent N, drop older ones from the new revision).
  Dropped entries persist forever in prior revisions; nothing is lost.
- **Readers** read from the local cache (instant) or walk the daemon /
  explorer to populate it. The GUI filters the cache by date for
  display: default last 7 days, "Show all" expander removes the filter.

No digest, no archive sub-ID needed — the existing cache + chain history
are sufficient.

**Both parties must write.** Per the symmetry principle, both borrower and lender post their own `loan.history` entry at settlement (see SPEC §10). A counterparty's entry is not authoritative for your reputation. The current GUI implementation only writes on the borrower side at repay-time; the lender-side watcher is open work.

`request_txid` (v2+) is propagated from `loan.status.request_txid` so
the history entry joins to the same loan via a single key.

```json
{
  "version": 2,
  "loan_id": "...",
  "request_txid": "65a578f6…eaa93",
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

### `contract.loan.decline` — public

Lender's public "polite no" to a specific borrower request. Lets the borrower's GUI surface a banner instead of leaving a request hanging while the lender silently moves on. Optional — lenders who prefer not to publish explicit declines can simply ignore requests, and the GUI will eventually time out the display.

```json
{
  "version": 1,
  "request_txid": "...",          // the borrower's loan.request.posted_tx
  "borrower_iaddr": "i7b7Tq8...", // who's being declined (so multiple
                                  //   readers each know "is this for me?")
  "reason": null | "insufficient_balance" | "terms" | "passing",
  "declined_at_block": <int>
}
```

**Retention.** Same pattern as `loan.history`: writer always overwrites the live multimap entry to size 1 (latest decline), older declines persist in past identity revisions via `getidentityhistory`. Borrowers reading their decline cache it locally on first sighting (`vl_seen_declines` localStorage) so the banner doesn't re-fire even if the entry rotates out.

**Posted by:** lender (on their own identity). Borrower has no authority to write here.

**Read by:** borrower's GUI watcher (polls each `target_lender_iaddr` from the borrower's active requests every ~30s).

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
      "vdxf_key": "make.vrsc::contract.loan.offer",
      "vdxf_id": "iMey7Y2idT6dt7jJvRiPXgtYcfAaKCQbHz",
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

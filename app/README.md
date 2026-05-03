# app — local web UI

A small Python server + static HTML/JS that runs on your machine, talks
to your local `verusd` via RPC, and walks you through the recipes with
a flow-driven UI and human-readable validation at every signing step.

## Run

```bash
python3 app/server.py
# Default: http://127.0.0.1:7777/
# Default RPC config: ~/.komodo/VRSC/VRSC.conf
```

Override:

```bash
python3 app/server.py --port 8080 --conf /path/to/VRSC.conf
```

Open the URL in any browser. No installation, no extension.

## What's here

- `server.py` — stdlib HTTP server. Serves `static/`, proxies `/rpc` to
  `verusd` so the browser can speak to the daemon under one origin.
- `static/index.html` — dashboard shell with three tabs: Positions,
  Marketplace, Settings.
- `static/js/rpc.js` — thin RPC client + i-address → friendly name resolver.
- `static/js/state.js` — localStorage-backed position cache.
- `static/js/validator.js` — decode + human-readable review pane that
  every signature/broadcast must pass through.
- `static/js/main.js` — dashboard / marketplace logic.

## State model

- **Browser localStorage**: ephemeral UI state, position list cache.
- **User's VerusID multimap (encrypted)**: persistent templates,
  ceremony coordination, history. Recovers from seed.
- **Chain**: source of truth. The other two are derivative.

No local database. Server is pure plumbing.

## What's wired today

- Status bar: pings `getinfo` to show chain tip
- Marketplace: walks wallet-local children of a parent ID, decodes
  `loan.offer.v1` multimap entries
- Settings: store your VerusID / R-address / pubkey for use later

## What's next

- Acceptance ceremony screen (cooperative origination + pre-sign)
- Active loan detail view (countdown + repay/default actions)
- extend_tx port to JS for broadcaster-pays-fee variants
- Encrypted multimap read/write for ceremony coordination
- Discovery beyond wallet-local IDs (needs explorer index)

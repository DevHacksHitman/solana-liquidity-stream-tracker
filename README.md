# Solana Liquidity Stream Tracker

A transparent, zero-alpha market-data monitor for Solana pump.fun activity.

It subscribes to on-chain trade events over a WebSocket, parses transaction
metadata, and persists every event through a versioned SQLite schema. The
repository contains no wallet logic and no key material — it observes the
market; it does not act on it.

## Architecture

    ┌────────────────┐   logsSubscribe    ┌──────────────────┐
    │  Solana JSON-  │ ─────────────────▶ │  tracker/        │
    │  RPC WebSocket │                    │  listener.py     │
    └────────────────┘                    └───────┬──────────┘
                                                 │ parse + record
                                                 ▼
                                          ┌──────────────┐
                                          │ SQLite store │
                                          │  (init_db)   │
                                          └──────────────┘

    web/ — an optional React + Vite dashboard that renders the live trade
           stream straight from a public WebSocket, browser-side.

## Layout

    config.py              env-driven runtime configuration (endpoints, storage)
    init_db.py             SQLite schema bootstrap + row helpers + CLI
    tracker/listener.py    async WebSocket listener: subscribe, parse, persist
    tracker/__main__.py    python -m tracker entry point
    upload_metadata.py     stdlib-only token metadata upload helper
    test_setup.py          environment sanity check
    verify_dependencies.py dependency report
    web/                   React + Vite + Tailwind dashboard
    githooks/pre-push      sensitivity gate (self-avoidant needles)

## Quickstart

    python3 test_setup.py
    pip install websockets
    python3 verify_dependencies.py

    python3 init_db.py --init            # creates ./data/stream.db
    python3 -m tracker                   # listens until Ctrl+C

Configuration is environment-driven (see config.py):

    SOLANA_RPC            https RPC endpoint (default: api.mainnet-beta.solana.com)
    SOLANA_WS             websocket RPC endpoint
    PROGRAM_ID            program under observation
    DATA_DIR / DB_PATH    storage location

## Tests

    python3 -m unittest discover -s tests -t .

All listener tests are zero-network: WebSocket frames are canned, the
connection factory and the metadata fetch are injected fakes, and nothing
dials out. The suite runs on the standard library alone; the `websockets`
package is only required to actually dial. The absent-package path is
covered by a conditional test that skips while `websockets` is installed.

## Frontend (optional)

    cd web
    cp .env.example .env      # then fill in your own values
    npm install
    npm run dev

## Repository hygiene

- Commits use the GitHub noreply email; no personal addresses in history.
- `githooks/pre-push` is a blocking sensitivity gate. Enable it once per
  clone:

      git config core.hooksPath githooks

  Its needles are written self-avoidantly (character-class breaks) so the
  hook can never match its own source and block every push forever.
- Never commit `.env`, keypair files, or wallet directories; `.gitignore`
  blocks them, and `*.example` placeholder files are the only env-shaped
  files in the tree.

## Honest limitations

- Trade side is derived from program log lines (`Instruction: Buy/Sell`);
  amounts and counterparties are stored from fetched metadata when the RPC
  provides it, otherwise as NULL.
- There is no historical backfill: the listener records what arrives live.
- The default public RPC endpoints are rate-limited; point `SOLANA_RPC`
  and `SOLANA_WS` at a provider of your choice for sustained use.

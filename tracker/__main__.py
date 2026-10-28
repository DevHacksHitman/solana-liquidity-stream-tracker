"""Run the tracker with configuration defaults.

Usage:
    python -m tracker
    python -m tracker --ws-url wss://... --rpc https://... --db data/stream.db
"""

import argparse
import asyncio

import config
from tracker.listener import StreamTracker


def main() -> int:
    parser = argparse.ArgumentParser(description="stream tracker listener")
    parser.add_argument("--ws-url", default=config.SOLANA_WS)
    parser.add_argument("--rpc", default=config.SOLANA_RPC)
    parser.add_argument("--db", default=str(config.DB_PATH))
    parser.add_argument("--program-id", default=config.PROGRAM_ID)
    args = parser.parse_args()

    tracker = StreamTracker(
        ws_url=args.ws_url,
        rpc_url=args.rpc,
        db_path=args.db,
        program_id=args.program_id,
    )
    try:
        asyncio.run(tracker.run())
    except KeyboardInterrupt:
        print("stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

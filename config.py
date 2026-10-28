"""Runtime configuration for the Solana market-data tracker.

Every value is environment-overridable; defaults point at public,
rate-limited endpoints and local storage. No credentials ship with the
repository, and none of the configuration describes wallet behaviour:
the tracker observes the market, it does not act on it.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# Endpoints (public data sources)
# ---------------------------------------------------------------------------
SOLANA_RPC = os.getenv("SOLANA_RPC", "https://api.mainnet-beta.solana.com")
SOLANA_WS = os.getenv("SOLANA_WS", "wss://api.mainnet-beta.solana.com")
IPFS_API = os.getenv("IPFS_API", "https://pump.fun/api/ipfs")

# ---------------------------------------------------------------------------
# Program under observation (public on-chain constant)
# ---------------------------------------------------------------------------
PROGRAM_ID = os.getenv(
    "PROGRAM_ID",
    "6EF8rrecthR5Dkzon8Nwu78hRvf2PXLi3KpQ6bYgGLb",
)

# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------
DATA_DIR = Path(os.getenv("DATA_DIR", str(BASE_DIR / "data")))
DB_PATH = Path(os.getenv("DB_PATH", str(DATA_DIR / "stream.db")))

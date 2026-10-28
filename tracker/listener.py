"""Thin async WebSocket listener for on-chain trade events.

Subscribes to program logs over a Solana JSON-RPC WebSocket
(logsSubscribe), parses transaction metadata, and persists one row per
event through the init_db schema. Dropped or refused connections
reconnect with jittered exponential backoff. There is no wallet logic in
this module: market data only.

Network access is confined to two seams, both injectable for tests:

* ``connect``   — the WebSocket connection factory (async context manager)
* ``tx_fetch``  — the transaction-metadata fetch (async callable)

The ``websockets`` package is imported lazily: parsing, classification,
persistence, and backoff all run — and are tested — without it.
"""

from __future__ import annotations

import asyncio
import json
import random
import sys
import urllib.request
from typing import Any, Awaitable, Callable, Dict, List, Optional

import config
import init_db

try:  # only needed to dial
    import websockets
except ImportError:  # pragma: no cover - absence is exercised via tests
    websockets = None  # type: ignore[assignment]

try:
    from websockets.exceptions import ConnectionClosed
except ImportError:  # keeps the module importable on the stdlib alone

    class ConnectionClosed(Exception):
        """Stand-in for the websockets exception when it is unavailable."""


class StreamClosed(Exception):
    """Raised when a message iterator ends without a protocol exception."""


DEFAULT_PROGRAM_ID = config.PROGRAM_ID

# Returns an async context manager yielding an object that is async
# iterable over frames and has an async ``send``.
ConnectFactory = Callable[[str], Any]
# Async callable: signature -> parsed transaction metadata (or None).
TxFetch = Callable[[str], Awaitable[Optional[dict]]]
Sleep = Callable[[float], Awaitable[None]]

_MAX_RAW_LOGS = 8000


def build_subscribe(program_id: str, request_id: int = 1) -> Dict[str, Any]:
    """Build a logsSubscribe request for the given program."""
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "logsSubscribe",
        "params": [
            {"mentions": [program_id]},
            {"commitment": "confirmed"},
        ],
    }


def parse_log_notification(payload: Any) -> Optional[Dict[str, Any]]:
    """Extract (signature, slot, logs) from a logsNotification frame.

    Returns None for everything else: non-JSON frames, other methods,
    malformed results, and transactions that ended in an error.
    """
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8", "replace")
    try:
        data = json.loads(payload)
    except (TypeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    if data.get("method") != "logsNotification":
        return None
    params = data.get("params") or {}
    result = params.get("result") or {}
    value = result.get("value") or {}
    if not isinstance(value, dict) or value.get("err") is not None:
        return None
    signature = value.get("signature")
    if not signature:
        return None
    logs = value.get("logs") or []
    slot = (result.get("context") or {}).get("slot")
    return {"signature": signature, "slot": slot, "logs": list(logs)}


def classify_trade(logs: List[str]) -> Optional[str]:
    """Map program log lines to a side: 'buy', 'sell', or None."""
    text = "\n".join(logs or [])
    if "Instruction: Buy" in text:
        return "buy"
    if "Instruction: Sell" in text:
        return "sell"
    return None


def default_tx_fetch(rpc_url: str, signature: str) -> Optional[dict]:
    """Fetch parsed transaction metadata over JSON-RPC HTTP (stdlib)."""
    body = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getTransaction",
            "params": [
                signature,
                {
                    "encoding": "jsonParsed",
                    "commitment": "confirmed",
                    "maxSupportedTransactionVersion": 0,
                },
            ],
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        rpc_url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if payload.get("error"):
        return None
    return payload.get("result")


def prune_metadata(tx: Optional[dict]) -> Optional[dict]:
    """Keep a small, stable subset of getTransaction output."""
    if not isinstance(tx, dict):
        return None
    meta = tx.get("meta") or {}
    return {
        "blockTime": tx.get("blockTime"),
        "slot": tx.get("slot"),
        "fee": meta.get("fee"),
        "err": meta.get("err"),
    }


class StreamTracker:
    """Reconnecting WebSocket listener persisting trade events."""

    def __init__(
        self,
        *,
        ws_url: str,
        rpc_url: str,
        db_path,
        program_id: str = DEFAULT_PROGRAM_ID,
        connect: Optional[ConnectFactory] = None,
        tx_fetch: Optional[TxFetch] = None,
        sleep: Optional[Sleep] = None,
        rng: Optional[Callable[[], float]] = None,
        base: float = 1.0,
        cap: float = 30.0,
        jitter: float = 0.2,
    ) -> None:
        self.ws_url = ws_url
        self.rpc_url = rpc_url
        self.db_path = db_path
        self.program_id = program_id
        self.base = base
        self.cap = cap
        self.jitter = jitter
        self.attempt = 0
        self.reconnects = 0
        self._connect = connect or self._default_connect
        self._tx_fetch = tx_fetch or self._default_tx_fetch()
        self._sleep = sleep or asyncio.sleep
        self._rng = rng or random.random

    @staticmethod
    def _default_connect(url: str):
        if websockets is None:
            raise RuntimeError(
                "The 'websockets' package is required: pip install websockets"
            )
        return websockets.connect(url, ping_interval=20)

    @staticmethod
    def _default_tx_fetch() -> TxFetch:
        async def fetch(signature: str) -> Optional[dict]:
            return await asyncio.to_thread(
                default_tx_fetch, config.SOLANA_RPC, signature
            )

        return fetch

    def backoff_delay(self, attempt: int) -> float:
        """Exponential delay capped at ``cap``, scaled by jitter."""
        delay = min(self.cap, self.base * (2 ** attempt))
        factor = 1.0 - self.jitter + (self._rng() * 2.0 * self.jitter)
        return delay * factor

    async def run(self) -> None:
        """Listen forever; reconnects with backoff until cancelled.

        The attempt counter resets once a session is established (the
        subscribe frame was sent), so a healthy stream is not penalised
        by earlier failures.
        """
        while True:
            try:
                async with self._connect(self.ws_url) as ws:
                    await ws.send(json.dumps(build_subscribe(self.program_id)))
                    self.attempt = 0
                    await self._pump(ws)
            except asyncio.CancelledError:
                raise
            except (ConnectionClosed, StreamClosed, OSError, ValueError) as exc:
                delay = self.backoff_delay(self.attempt)
                self.attempt += 1
                self.reconnects += 1
                print(
                    f"stream interrupted ({exc!r}); reconnecting in {delay:.2f}s",
                    file=sys.stderr,
                )
                await self._sleep(delay)

    async def _pump(self, ws: Any) -> None:
        async for raw in ws:
            note = parse_log_notification(raw)
            if note is not None:
                await self._handle(note)

    async def _handle(self, note: Dict[str, Any]) -> None:
        metadata = None
        try:
            metadata = prune_metadata(await self._tx_fetch(note["signature"]))
        except Exception as exc:  # metadata is best-effort; the event still counts
            print(
                f"metadata fetch failed for {note['signature']}: {exc}",
                file=sys.stderr,
            )

        row = {
            "signature": note["signature"],
            "slot": note["slot"],
            "program_id": self.program_id,
            "side": classify_trade(note["logs"]),
            "mint": None,
            "trader": None,
            "token_amount": None,
            "sol_amount": None,
            "raw_logs": "\n".join(note["logs"])[:_MAX_RAW_LOGS],
            "metadata_json": json.dumps(metadata) if metadata is not None else None,
        }
        conn = init_db.connect(self.db_path)
        try:
            init_db.record_trade(conn, row)
            conn.commit()
        finally:
            conn.close()

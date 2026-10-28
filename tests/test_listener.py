"""Zero-network tests for the stream listener.

Canned WebSocket payloads exercise parsing, classification, persistence,
and reconnect/backoff behaviour through injected fakes; nothing dials
out. Fixture identifiers are deliberately non-canonical strings so the
repository stays free of key-shaped literals.
"""

import asyncio
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from tracker import listener
from tracker.listener import (
    StreamTracker,
    build_subscribe,
    classify_trade,
    parse_log_notification,
    prune_metadata,
)

import init_db


def notification(signature, slot, logs, err=None):
    value = {"signature": signature, "err": err, "logs": logs}
    return {
        "jsonrpc": "2.0",
        "method": "logsNotification",
        "params": {"result": {"context": {"slot": slot}, "value": value}},
    }


BUY_LOGS = [
    "Program 11111111111111111111111111111111 invoke [1]",
    "Program log: Instruction: Buy",
    "Program log: InitializeAccount2 Success",
]
SELL_LOGS = ["Program log: Instruction: Sell"]
CREATE_LOGS = ["Program log: Instruction: Create"]


class TestSubscribeBuilder(unittest.TestCase):
    def test_shape(self):
        payload = build_subscribe("prog-test-1", request_id=7)
        self.assertEqual(payload["method"], "logsSubscribe")
        self.assertEqual(payload["id"], 7)
        self.assertEqual(payload["params"][0], {"mentions": ["prog-test-1"]})
        self.assertEqual(payload["params"][1], {"commitment": "confirmed"})


class TestParseNotification(unittest.TestCase):
    def test_valid(self):
        note = parse_log_notification(
            json.dumps(notification("sig-test-0001", 42, BUY_LOGS))
        )
        self.assertEqual(note["signature"], "sig-test-0001")
        self.assertEqual(note["slot"], 42)
        self.assertEqual(note["logs"], BUY_LOGS)

    def test_non_json(self):
        self.assertIsNone(parse_log_notification("not json"))

    def test_other_method(self):
        self.assertIsNone(
            parse_log_notification(
                json.dumps({"jsonrpc": "2.0", "method": "accountNotification"})
            )
        )

    def test_errored_transaction_skipped(self):
        frame = notification(
            "sig-test-0002", 43, ["x"], err={"InstructionError": {}}
        )
        self.assertIsNone(parse_log_notification(json.dumps(frame)))

    def test_missing_signature(self):
        frame = notification("", 44, BUY_LOGS)
        self.assertIsNone(parse_log_notification(json.dumps(frame)))

    def test_bytes_input(self):
        note = parse_log_notification(
            json.dumps(notification("sig-test-0003", 45, SELL_LOGS)).encode()
        )
        self.assertEqual(note["signature"], "sig-test-0003")


class TestClassify(unittest.TestCase):
    def test_buy(self):
        self.assertEqual(classify_trade(BUY_LOGS), "buy")

    def test_sell(self):
        self.assertEqual(classify_trade(SELL_LOGS), "sell")

    def test_unrelated(self):
        self.assertIsNone(classify_trade(CREATE_LOGS))
        self.assertIsNone(classify_trade([]))


class TestBackoff(unittest.TestCase):
    def _tracker(self, **kwargs):
        defaults = dict(
            ws_url="wss://rpc.test/ws",
            rpc_url="https://rpc.test",
            db_path=":memory:",
        )
        defaults.update(kwargs)
        return StreamTracker(**defaults)

    def test_exact_without_jitter(self):
        tracker = self._tracker(jitter=0.0, rng=lambda: 0.0)
        delays = [tracker.backoff_delay(a) for a in range(7)]
        self.assertEqual(delays, [1.0, 2.0, 4.0, 8.0, 16.0, 30.0, 30.0])

    def test_jitter_bounds(self):
        low = self._tracker(jitter=0.2, rng=lambda: 0.0)
        high = self._tracker(jitter=0.2, rng=lambda: 1.0)
        self.assertEqual(low.backoff_delay(0), 0.8)
        self.assertAlmostEqual(high.backoff_delay(0), 1.2, delta=1e-9)

    def test_custom_base_and_cap(self):
        tracker = self._tracker(
            base=0.5, cap=4.0, jitter=0.0, rng=lambda: 0.0
        )
        delays = [tracker.backoff_delay(a) for a in range(5)]
        self.assertEqual(delays, [0.5, 1.0, 2.0, 4.0, 4.0])


class TestPersistence(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db = Path(tmp.name) / "stream.db"

    def test_record_and_dedupe(self):
        init_db.init_database(self.db)
        row = {
            "signature": "sig-test-0004",
            "slot": 46,
            "program_id": "prog-test",
            "side": "buy",
            "mint": "MINT-TEST-0001",
            "trader": "TRADER-TEST-0001",
            "token_amount": 1000.0,
            "sol_amount": 0.5,
            "raw_logs": "Program log: Instruction: Buy",
            "metadata_json": None,
        }
        conn = init_db.connect(self.db)
        try:
            self.assertTrue(init_db.record_trade(conn, row))
            self.assertFalse(init_db.record_trade(conn, row))
            conn.commit()
        finally:
            conn.close()

        stats = init_db.stats(self.db)
        self.assertEqual(stats["total"], 1)
        self.assertEqual(stats["first_slot"], 46)
        self.assertEqual(stats["last_slot"], 46)

    def test_prune_metadata(self):
        self.assertIsNone(prune_metadata(None))
        self.assertIsNone(prune_metadata("nope"))
        pruned = prune_metadata(
            {
                "blockTime": 1_700_000_000,
                "slot": 5,
                "meta": {"fee": 5000, "err": None, "junk": "x"},
            }
        )
        self.assertEqual(
            pruned,
            {"blockTime": 1_700_000_000, "slot": 5, "fee": 5000, "err": None},
        )


class FakeWS:
    """Minimal async context manager yielding canned frames."""

    def __init__(self, frames):
        self.sent = []
        self.closed = False
        self._frames = list(frames)

    async def send(self, data):
        self.sent.append(data)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._frames:
            raise listener.StreamClosed("stream closed")
        return self._frames.pop(0)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        self.closed = True
        return False


class FlakyConnect:
    """Refuses the first N calls, then yields a fresh FakeWS each time."""

    def __init__(self, failures, frames):
        self.failures = failures
        self.calls = 0
        self.instances = []
        self._frames = frames

    def __call__(self, url):
        self.calls += 1
        if self.calls <= self.failures:
            raise ConnectionRefusedError("refused")
        ws = FakeWS(self._frames)
        self.instances.append(ws)
        return ws


class AlwaysFailing:
    def __init__(self):
        self.calls = 0

    def __call__(self, url):
        self.calls += 1
        raise ConnectionRefusedError("refused")


class TestStreamTrackerCanned(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db = Path(tmp.name) / "stream.db"

    def make_tracker(self, connect, sleeps, stop_after):
        async def fake_sleep(delay):
            sleeps.append(delay)
            if len(sleeps) >= stop_after:
                raise asyncio.CancelledError()

        async def fake_fetch(signature):
            if signature == "sig-test-0007":
                raise OSError("rpc down")
            return {
                "blockTime": 1_700_000_001,
                "slot": 50,
                "meta": {"fee": 5000, "err": None},
            }

        tracker = StreamTracker(
            ws_url="wss://rpc.test/ws",
            rpc_url="https://rpc.test",
            db_path=self.db,
            program_id="prog-test-1",
            connect=connect,
            tx_fetch=fake_fetch,
            sleep=fake_sleep,
            jitter=0.0,
            rng=lambda: 0.0,
        )
        return tracker

    async def test_canned_stream_persists_and_reconnects(self):
        frames = [
            json.dumps(notification("sig-test-0005", 50, BUY_LOGS)),
            "garbage-frame",
            json.dumps(
                {"jsonrpc": "2.0", "method": "accountNotification", "params": {}}
            ),
            json.dumps(
                notification(
                    "sig-test-0006", 51, SELL_LOGS, err={"InstructionError": {}}
                )
            ),
            json.dumps(notification("sig-test-0007", 52, BUY_LOGS)),
        ]
        connect = FlakyConnect(failures=2, frames=frames)
        sleeps = []
        tracker = self.make_tracker(connect, sleeps, stop_after=3)

        with self.assertRaises(asyncio.CancelledError):
            await tracker.run()

        # two refused dials, then a good session; the stream ending later
        # triggers exactly one more backoff — at 1.0s, proving the attempt
        # counter reset after the successful session
        self.assertEqual(connect.calls, 3)
        self.assertEqual(sleeps, [1.0, 2.0, 1.0])
        self.assertEqual(tracker.reconnects, 3)

        # the subscribe frame went out once, on the established session
        self.assertEqual(
            connect.instances[0].sent,
            [json.dumps(build_subscribe("prog-test-1"))],
        )

        stats = init_db.stats(self.db)
        self.assertEqual(stats["total"], 2)
        self.assertEqual(stats["first_slot"], 50)
        self.assertEqual(stats["last_slot"], 52)

        cursor = sqlite3.connect(self.db).execute(
            "SELECT signature, side, metadata_json FROM trades"
        )
        rows = {r[0]: (r[1], r[2]) for r in cursor}
        self.assertEqual(set(rows), {"sig-test-0005", "sig-test-0007"})
        self.assertEqual(rows["sig-test-0005"][0], "buy")
        self.assertIn("blockTime", rows["sig-test-0005"][1])
        # metadata fetch failed for this one; the event is still stored
        self.assertIsNone(rows["sig-test-0007"][1])

    async def test_backoff_ramps_to_cap(self):
        connect = AlwaysFailing()
        sleeps = []
        tracker = self.make_tracker(connect, sleeps, stop_after=6)

        with self.assertRaises(asyncio.CancelledError):
            await tracker.run()

        self.assertEqual(sleeps, [1.0, 2.0, 4.0, 8.0, 16.0, 30.0])
        self.assertEqual(connect.calls, 6)

    @unittest.skipIf(
        listener.websockets is not None,
        "websockets is installed; the absent-package path cannot be exercised",
    )
    async def test_missing_websockets_raises(self):
        tracker = self.make_tracker(StreamTracker._default_connect, [], 1)
        with self.assertRaises(RuntimeError):
            await tracker.run()


if __name__ == "__main__":
    unittest.main()

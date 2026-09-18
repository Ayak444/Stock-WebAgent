import asyncio
import unittest

import numpy as np
import pandas as pd
from pydantic import ValidationError

from analyzer import TechnicalAnalyzer
from cache_layer import MemoryCache
from database import _hash_password, _public_user, _verify_password
from ml_features import FeatureEngineer
from models import AuthRequest, TradeRequest
from task_queue import TaskQueue


class RegressionTests(unittest.TestCase):
    def setUp(self):
        close = np.arange(100.0, 420.0)
        self.prices = pd.DataFrame(
            {
                "Open": close,
                "High": close + 2,
                "Low": close - 2,
                "Close": close,
                "Volume": np.arange(1000, 1320),
            },
            index=pd.date_range("2024-01-01", periods=len(close)),
        )

    def test_rsi_handles_zero_average_loss(self):
        result = TechnicalAnalyzer.calculate_indicators(self.prices)
        self.assertEqual(result["RSI"].iloc[-1], 100)

    def test_oscillator_features_accept_series_ranges(self):
        result = FeatureEngineer.extract_oscillator_features(self.prices)
        self.assertEqual(len(result), len(self.prices))

    def test_cache_never_exceeds_capacity(self):
        cache = MemoryCache(max_size=1)
        cache.set("expired", 1, ttl_seconds=-1)
        cache.set("first", 2)
        cache.set("second", 3)
        self.assertEqual(len(cache.store), 1)

    def test_passwords_are_hashed_and_private(self):
        hashed = _hash_password("correct horse battery staple")
        self.assertNotEqual(hashed, "correct horse battery staple")
        self.assertEqual(
            _verify_password("correct horse battery staple", hashed),
            (True, False),
        )
        self.assertEqual(_verify_password("legacy", "legacy"), (True, True))
        self.assertNotIn(
            "password_hash",
            _public_user({"id": "1", "password_hash": hashed}),
        )

    def test_invalid_trade_and_email_are_rejected(self):
        with self.assertRaises(ValidationError):
            TradeRequest(
                user_id="user",
                action="anything",
                ticker="2330.TW",
                amount=-1,
                price=-1,
            )
        with self.assertRaises(ValidationError):
            AuthRequest(email="invalid", password="password")

    def test_cancelled_task_is_not_executed(self):
        async def scenario():
            queue = TaskQueue(max_workers=0)
            await queue.initialize()
            calls = []

            def handler():
                calls.append(True)

            task_id = await queue.submit("cancelled", handler)
            await queue.cancel_task(task_id)
            queue.running = True
            worker = asyncio.create_task(queue._worker(0))
            await asyncio.sleep(0.05)
            queue.running = False
            await worker
            return calls, queue.tasks[task_id].status.value

        calls, status = asyncio.run(scenario())
        self.assertEqual(calls, [])
        self.assertEqual(status, "cancelled")


if __name__ == "__main__":
    unittest.main()

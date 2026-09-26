import contextlib
import io
import unittest
from datetime import datetime
from unittest.mock import Mock

import pandas as pd

from holder_volume_alerts import TAIPEI
from notifier import DiscordNotifier
from volume_alerts import VolumeAlertConfig, VolumeAlertMonitor, should_startup_catchup


NOW = datetime(2026, 9, 21, 20, 30, tzinfo=TAIPEI)


def market_frame(*, date="2026-09-21", latest=150, previous=None):
    previous = [100] * 20 if previous is None else previous
    index = pd.bdate_range(end=date, periods=len(previous) + 1)
    frame = pd.DataFrame({"Volume": previous + [latest]}, index=index)
    frame.attrs["route"] = {"source": "yahoo"}
    return frame


class ConfigAndScheduleTests(unittest.TestCase):
    def test_disabled_default_validated_settings_and_catchup_window(self):
        self.assertFalse(VolumeAlertConfig.from_env({}).ready)
        valid = VolumeAlertConfig.from_env({
            "VOLUME_ALERT_ENABLED": "true",
            "VOLUME_ALERT_TICKERS": "2330.tw, 6488.TWO,2330.TW",
            "DISCORD_WEBHOOK_URL": "https://example.invalid/hook",
        })
        self.assertTrue(valid.ready)
        self.assertEqual(valid.tickers, ("2330.TW", "6488.TWO"))
        self.assertEqual(valid.multiplier, 1.5)
        for override in (
            {"VOLUME_ALERT_MULTIPLIER": "nan"},
            {"VOLUME_ALERT_MULTIPLIER": "1"},
            {"VOLUME_ALERT_TICKERS": "2330.TW,invalid"},
            {"DISCORD_WEBHOOK_URL": ""},
        ):
            settings = {
                "VOLUME_ALERT_ENABLED": "true",
                "VOLUME_ALERT_TICKERS": "2330.TW",
                "DISCORD_WEBHOOK_URL": "https://example.invalid/hook",
                **override,
            }
            self.assertFalse(VolumeAlertConfig.from_env(settings).ready)
        self.assertTrue(should_startup_catchup(NOW))
        self.assertFalse(should_startup_catchup(NOW.replace(hour=20, minute=29)))
        self.assertFalse(should_startup_catchup(NOW.replace(hour=21, minute=30)))


class MonitorTests(unittest.IsolatedAsyncioTestCase):
    async def test_today_threshold_and_one_send_per_ticker_date(self):
        sent = []
        notifier = Mock()
        notifier.send_volume_alert.side_effect = lambda ticker, data: sent.append((ticker, data)) or True
        config = VolumeAlertConfig(enabled=True, tickers=("2330.TW",), multiplier=1.5)
        monitor = VolumeAlertMonitor(config, lambda _: market_frame(), notifier, clock=lambda: NOW)
        first = await monitor.run()
        second = await monitor.run()
        self.assertEqual(first["results"][0]["reason"], "sent")
        self.assertEqual(second["results"][0]["reason"], "already_sent")
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0][1]["market_date"], "2026-09-21")
        self.assertEqual(sent[0][1]["baseline_sessions"], 20)
        self.assertEqual(sent[0][1]["baseline_median_volume"], 100)

    async def test_stale_insufficient_and_below_threshold_never_send(self):
        notifier = Mock()
        config = VolumeAlertConfig(enabled=True, tickers=("2330.TW",), multiplier=1.5)
        for frame, expected in (
            (market_frame(date="2026-09-18"), "market_data_not_today"),
            (market_frame(previous=[100] * 14), "volume_history_insufficient"),
            (market_frame(latest=149), "below_threshold"),
            (market_frame(latest=0), "latest_volume_not_positive"),
        ):
            monitor = VolumeAlertMonitor(config, lambda _: frame, notifier, clock=lambda: NOW)
            result = await monitor.run()
            self.assertEqual(result["results"][0]["reason"], expected)
        notifier.send_volume_alert.assert_not_called()

    async def test_ticker_failure_does_not_block_other_tickers(self):
        def load(ticker):
            if ticker == "2330.TW":
                raise RuntimeError("market offline")
            return market_frame()

        notifier = Mock()
        notifier.send_volume_alert.return_value = True
        config = VolumeAlertConfig(enabled=True, tickers=("2330.TW", "6488.TWO"))
        result = await VolumeAlertMonitor(config, load, notifier, clock=lambda: NOW).run()
        self.assertEqual([item["reason"] for item in result["results"]], ["ticker_processing_failed", "sent"])
        self.assertEqual(result["status"], "partial")
        notifier.send_volume_alert.assert_called_once()


class DiscordTests(unittest.TestCase):
    def test_message_fields_no_mentions_and_redacted_transport_failure(self):
        response = Mock(status_code=204)
        transport = Mock(return_value=response)
        notifier = DiscordNotifier("https://secret.invalid/webhook", transport=transport)
        volume = {
            "market_date": "2026-09-21", "latest_volume": 150,
            "baseline_sessions": 20, "baseline_median_volume": 100,
            "volume_multiple": 1.5, "route": {"source": "yahoo"},
        }
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertTrue(notifier.send_volume_alert("2330.TW", volume))
        kwargs = transport.call_args.kwargs
        self.assertEqual(kwargs["timeout"], (3, 7))
        self.assertFalse(kwargs["allow_redirects"])
        self.assertEqual(kwargs["json"]["allowed_mentions"], {"parse": []})
        description = kwargs["json"]["embeds"][0]["description"]
        for text in ("2330.TW", "2026-09-21", "150", "100", "1.50x", "yahoo", "不構成投資建議"):
            self.assertIn(text, description)
        transport.side_effect = RuntimeError("https://secret.invalid/webhook")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertFalse(notifier.send_volume_alert("2330.TW", volume))
        self.assertNotIn("secret.invalid", output.getvalue())


if __name__ == "__main__":
    unittest.main()

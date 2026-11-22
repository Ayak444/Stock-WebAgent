"""Offline coverage for the ETF golden-cross notification path."""

import asyncio
import unittest
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pandas as pd

import etf_golden_cross_alerts as alerts


MARKET_DATE = date(2024, 6, 14)
AFTER_CLOSE = datetime(2024, 6, 14, 20, 30, tzinfo=alerts.TAIPEI)
FAKE_ENV = {
    "ETF_ALERT_ENABLED": "true",
    "ETF_ALERT_TICKERS": " 0050,00937b.two,0050.tw ",
    "ETF_ALERT_EMAIL_FROM": "sender@example.test",
    "ETF_ALERT_EMAIL_TO": "recipient@example.test",
    "ETF_ALERT_RESEND_API_KEY": "offline_fake_key",
}
PRIVATE_SETTINGS = ("ETF_ALERT_EMAIL_FROM", "ETF_ALERT_EMAIL_TO", "ETF_ALERT_RESEND_API_KEY")


def matching_bars(market_date=MARKET_DATE):
    closes = pd.Series(
        [*range(150, 90, -1), 94],
        index=pd.bdate_range(end=market_date, periods=61),
    )
    return pd.DataFrame({
        "Close": closes,
        "High": closes + 1,
        "Low": closes - 1,
        "Volume": 100,
    })


class ConfigurationTests(unittest.TestCase):
    def test_defaults_off_and_normalizes_taiwan_etf_symbols(self):
        self.assertFalse(alerts.ETFAlertConfig.from_env({}).ready)
        config = alerts.ETFAlertConfig.from_env(FAKE_ENV)
        self.assertTrue(config.ready)
        self.assertEqual(config.tickers, ("0050.TW", "00937B.TWO"))
        for name in PRIVATE_SETTINGS:
            self.assertNotIn(FAKE_ENV[name], repr(config))

    def test_invalid_flag_watchlist_and_transport_fail_closed(self):
        cases = (
            ("ETF_ALERT_ENABLED", "yes", "invalid_enabled"),
            ("ETF_ALERT_TICKERS", "", "invalid_tickers"),
            ("ETF_ALERT_TICKERS", "0050.TW,2330.TW", "invalid_tickers"),
            ("ETF_ALERT_TICKERS", ",".join(f"00{code:02}" for code in range(21)), "too_many_tickers"),
            ("ETF_ALERT_EMAIL_FROM", "one@example.test,two@example.test", "invalid_sender"),
            ("ETF_ALERT_EMAIL_TO", "recipient@.example.test", "invalid_recipient"),
            ("ETF_ALERT_RESEND_API_KEY", "invalid key", "invalid_api_key"),
        )
        for name, value, error in cases:
            with self.subTest(name=name, error=error):
                config = alerts.ETFAlertConfig.from_env({**FAKE_ENV, name: value})
                self.assertFalse(config.ready)
                self.assertIn(error, config.errors)


class SignalTests(unittest.TestCase):
    def test_real_analyzer_crosses_as_k_leaves_oversold_range(self):
        bars = matching_bars()
        bars.index = bars.index.tz_localize(alerts.TAIPEI).tz_convert("UTC")
        signal = alerts.find_golden_cross(bars.iloc[::-1], MARKET_DATE)
        self.assertIsNotNone(signal)
        self.assertEqual(signal.market_date, MARKET_DATE)
        self.assertEqual(signal.close, 94)
        self.assertLess(signal.signal, signal.macd)
        self.assertLess(signal.macd, 0)
        self.assertGreater(signal.k, 20)
        self.assertGreater(signal.k, signal.d)
        self.assertAlmostEqual(signal.j, 3 * signal.k - 2 * signal.d)

    def test_both_indicators_must_cross_from_low_zone_on_same_bar(self):
        bars = matching_bars()
        columns = ["MACD", "Signal", "K", "D"]
        prior, current = (-2, -2, 19, 19), (-1, -2, 23, 20)
        cases = (
            ("equal before and strictly crossing", prior, current, True),
            ("MACD crossed earlier", (-1, -2, 19, 19), current, False),
            ("KD crossed earlier", (-2, -2, 19, 18), current, False),
            ("MACD touches signal", prior, (-2, -2, 23, 20), False),
            ("KD touches signal", prior, (-1, -2, 20, 20), False),
            ("MACD crosses zero", prior, (0, -2, 23, 20), False),
            ("D starts at threshold", (-2, -2, 19, 20), current, False),
            ("missing indicator", prior, (-1, -2, float("nan"), 20), False),
        )
        for name, previous, latest, expected in cases:
            with self.subTest(name=name):
                indicators = pd.DataFrame([previous, latest], columns=columns)
                with patch.object(alerts.TechnicalAnalyzer, "calculate_indicators", return_value=indicators):
                    self.assertEqual(alerts.find_golden_cross(bars, MARKET_DATE) is not None, expected)

    def test_rejects_stale_future_short_and_invalid_bars(self):
        bars = matching_bars()
        cases = {
            "stale": bars.iloc[:-1],
            "future": matching_bars(date(2024, 6, 17)),
            "short": bars.tail(alerts.MINIMUM_BARS - 1),
            "missing": bars.drop(columns="Volume"),
            "nonfinite": bars.assign(Close=float("inf")),
            "out of range": bars.assign(High=1),
            "zero volume": bars.assign(Volume=0),
            "duplicate date": pd.concat([bars, bars.tail(1)]),
            "non-date index": bars.reset_index(drop=True),
            "flat KD range": bars.assign(High=100, Low=100, Close=100),
        }
        for name, data in cases.items():
            with self.subTest(name=name):
                self.assertIsNone(alerts.find_golden_cross(data, MARKET_DATE))


class MonitorTests(unittest.IsolatedAsyncioTestCase):
    async def test_disabled_invalid_early_and_weekend_runs_skip_history_and_email(self):
        loader = AsyncMock()
        sender = MagicMock(send=AsyncMock())
        config = alerts.ETFAlertConfig.from_env(FAKE_ENV)
        invalid = alerts.ETFAlertConfig.from_env({"ETF_ALERT_ENABLED": "true"})
        cases = (
            (alerts.ETFAlertConfig(), AFTER_CLOSE, "disabled"),
            (invalid, AFTER_CLOSE, "invalid_config"),
            (config, AFTER_CLOSE - timedelta(minutes=1), "outside_scan_window"),
            (config, AFTER_CLOSE + timedelta(days=1), "outside_scan_window"),
        )
        for settings, when, status in cases:
            with self.subTest(status=status, when=when):
                monitor = alerts.ETFGoldenCrossMonitor(settings, loader, sender, clock=lambda: when)
                self.assertEqual((await monitor.run())["status"], status)
        loader.assert_not_awaited()
        sender.send.assert_not_awaited()

    async def test_fresh_match_sends_while_a_ticker_error_stays_isolated(self):
        config = alerts.ETFAlertConfig.from_env(FAKE_ENV)
        loader = AsyncMock(side_effect=[ValueError(FAKE_ENV["ETF_ALERT_RESEND_API_KEY"]), matching_bars()])
        sender = MagicMock(send=AsyncMock(return_value=True))
        monitor = alerts.ETFGoldenCrossMonitor(
            config, loader, sender, clock=lambda: AFTER_CLOSE.astimezone(timezone.utc),
        )
        with self.assertLogs(alerts.LOGGER, "WARNING") as logs:
            result = await monitor.run()
        self.assertEqual(result, {"status": "partial", "checked": 2, "matched": 1, "sent": 1, "failed": 1})
        self.assertNotIn(FAKE_ENV["ETF_ALERT_RESEND_API_KEY"], " ".join(logs.output))
        sender.send.assert_awaited_once_with("00937B.TWO", alerts.find_golden_cross(matching_bars(), MARKET_DATE))

    async def test_empty_provider_failure_is_reported_and_stale_history_skips_mail(self):
        config = alerts.ETFAlertConfig.from_env(FAKE_ENV)
        loader = AsyncMock(side_effect=[pd.DataFrame(), matching_bars().iloc[:-1]])
        sender = MagicMock(send=AsyncMock())
        monitor = alerts.ETFGoldenCrossMonitor(config, loader, sender, clock=lambda: AFTER_CLOSE)
        with self.assertLogs(alerts.LOGGER, "WARNING") as logs:
            result = await monitor.run()
        self.assertIn("history_unavailable", logs.output[0])
        self.assertEqual(result, {"status": "partial", "checked": 2, "matched": 0, "sent": 0, "failed": 1})
        sender.send.assert_not_awaited()

    async def test_loader_falls_back_to_shorter_history_only_after_empty(self):
        current = matching_bars()
        provider = MagicMock(get_stock_history=AsyncMock(side_effect=[pd.DataFrame(), current, current]))
        with patch("async_data_provider.get_async_provider", AsyncMock(return_value=provider)):
            self.assertIs(await alerts.load_etf_alert_history("0050.TW"), current)
            self.assertIs(await alerts.load_etf_alert_history("0050.TW"), current)
        self.assertEqual(
            [request.kwargs["days"] for request in provider.get_stock_history.await_args_list],
            [180, 60, 180],
        )

    async def test_one_shot_propagates_failure_and_closes_market_provider(self):
        config = alerts.ETFAlertConfig.from_env(FAKE_ENV)
        close = AsyncMock()
        monitor = MagicMock(run=AsyncMock(side_effect=[{"status": "partial"}, {"status": "success"}]))
        with (
            patch.object(alerts.ETFAlertConfig, "from_env", return_value=config),
            patch.object(alerts, "ETFGoldenCrossMonitor", return_value=monitor),
            patch("async_data_provider.close_async_provider", close),
        ):
            self.assertEqual(await alerts._run_once(), 1)
            self.assertEqual(await alerts._run_once(), 0)
        self.assertEqual(close.await_count, 2)


class EmailTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.signal = alerts.GoldenCross(MARKET_DATE, 94, -1.1, -1.2, 18, 16)
        self.config = alerts.ETFAlertConfig.from_env(FAKE_ENV)
        self.session = MagicMock()
        self.client = MagicMock()
        self.client.__aenter__.return_value = self.session

    def respond(self, status):
        response = MagicMock()
        response.__aenter__.return_value.status = status
        return response

    async def test_https_payload_retry_and_independent_event_keys(self):
        self.session.post.side_effect = [
            aiohttp.ClientConnectionError("synthetic transport error"),
            self.respond(202),
            self.respond(202),
            self.respond(202),
            self.respond(202),
            self.respond(202),
        ]
        pause = AsyncMock()
        other_recipient = alerts.ETFAlertConfig.from_env({**FAKE_ENV, "ETF_ALERT_EMAIL_TO": "other@example.test"})
        with (
            patch.object(alerts.aiohttp, "ClientSession", return_value=self.client),
            patch.object(alerts.asyncio, "sleep", pause),
        ):
            self.assertTrue(await alerts.ResendEmailSender(self.config).send("0050.TW", self.signal))
            outcomes = await asyncio.gather(
                alerts.ResendEmailSender(self.config).send("0050.TW", self.signal),
                alerts.ResendEmailSender(self.config).send("00878.TW", self.signal),
                alerts.ResendEmailSender(self.config).send(
                    "0050.TW", alerts.GoldenCross(date(2024, 6, 17), 94, -1.1, -1.2, 18, 16),
                ),
                alerts.ResendEmailSender(other_recipient).send("0050.TW", self.signal),
            )
        self.assertEqual(outcomes, [True] * 4)
        pause.assert_awaited_once()
        first, retry, repeated, *other_events = self.session.post.call_args_list
        self.assertEqual(first, retry)
        self.assertEqual(first, repeated)
        self.assertEqual(first.args[0], "https://api.resend.com/emails")
        self.assertFalse(first.kwargs["allow_redirects"])
        headers = first.kwargs["headers"]
        self.assertEqual(headers["Authorization"], f"Bearer {FAKE_ENV['ETF_ALERT_RESEND_API_KEY']}")
        key = headers["Idempotency-Key"]
        self.assertNotIn(FAKE_ENV["ETF_ALERT_EMAIL_TO"], key)
        for other in other_events:
            self.assertNotEqual(other.kwargs["headers"]["Idempotency-Key"], key)
        payload = first.kwargs["json"]
        self.assertEqual(payload["from"], FAKE_ENV["ETF_ALERT_EMAIL_FROM"])
        self.assertEqual(payload["to"], [FAKE_ENV["ETF_ALERT_EMAIL_TO"]])
        self.assertIn("ETF 黃金交叉通知｜0050.TW｜2024-06-14", payload["subject"])
        for detail in ("94.00", "-1.1000", "-1.2000", "K：18.00", "D：16.00", "J：22.00"):
            self.assertIn(detail, payload["text"])

    async def test_permanent_delivery_error_is_not_retried_or_logged_with_addresses(self):
        self.session.post.return_value = self.respond(403)
        with (
            patch.object(alerts.aiohttp, "ClientSession", return_value=self.client),
            self.assertLogs(alerts.LOGGER, "WARNING") as logs,
        ):
            self.assertFalse(await alerts.ResendEmailSender(self.config).send("0050.TW", self.signal))
        self.session.post.assert_called_once()
        self.assertIn("status=403", logs.output[0])
        for name in PRIVATE_SETTINGS:
            self.assertNotIn(FAKE_ENV[name], logs.output[0])


class SchedulingTests(unittest.IsolatedAsyncioTestCase):
    async def test_application_lifespan_wires_daily_handler_and_conditional_catchup(self):
        import main

        configured = alerts.ETFAlertConfig.from_env(FAKE_ENV)
        for config, after_close in ((configured, True), (configured, False), (alerts.ETFAlertConfig(), True)):
            with self.subTest(ready=config.ready, after_close=after_close):
                job_runner = MagicMock(start=AsyncMock(), stop=AsyncMock(), run_high_priority=AsyncMock())
                monitor = MagicMock(run=AsyncMock())
                with patch.multiple(
                    main,
                    get_async_provider=AsyncMock(),
                    initialize_websocket_system=AsyncMock(),
                    shutdown_websocket_system=AsyncMock(),
                    close_async_provider=AsyncMock(),
                    job_runner=job_runner,
                    holder_alert_config=MagicMock(ready=False),
                    volume_alert_config=MagicMock(ready=False),
                    etf_alert_config=config,
                    etf_alert_monitor=monitor,
                    is_etf_alert_time=MagicMock(return_value=after_close),
                ):
                    async with main.lifespan(main.app):
                        pass
                job_runner.start.assert_awaited_once()
                job_runner.stop.assert_awaited_once()
                scheduled = [
                    call for call in job_runner.schedule_daily.call_args_list
                    if call.args[0] == "daily_etf_golden_cross"
                ]
                self.assertEqual(len(scheduled), int(config.ready))
                if config.ready:
                    self.assertIs(scheduled[0].args[2], monitor.run)
                    self.assertEqual(scheduled[0].kwargs, {
                        "hour": 20, "minute": 30, "timezone_name": "Asia/Taipei",
                    })
                self.assertEqual(job_runner.run_high_priority.await_count, int(config.ready and after_close))
                if config.ready and after_close:
                    self.assertIs(job_runner.run_high_priority.await_args.args[1], monitor.run)

"""Offline coverage for the ETF golden-cross notification path."""

import asyncio
import io
import logging
import unittest
from contextlib import redirect_stdout
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pandas as pd
from cryptography.fernet import Fernet

import etf_golden_cross_alerts as alerts
from account_alert_security import encrypt_webhook
from database import AccountAlertStoreError, Database
from notifier import DiscordNotifier


MARKET_DATE = date(2024, 6, 14)
AFTER_CLOSE = datetime(2024, 6, 14, 20, 30, tzinfo=alerts.TAIPEI)
ACCOUNT_EMAIL = "recipient@example.test"
ACCOUNT_ID = "test-account-id"
PRIVATE_HOOK = "https://discord.com/api/webhooks/1234/test_only_account_destination"
GLOBAL_HOOK = "https://discord.com/api/webhooks/5678/test_only_global_destination"
FAKE_ENV = {
    "ETF_ALERT_ENABLED": "true",
    "ETF_ALERT_TICKERS": " 0050,00937b.two,0050.tw ",
    "ETF_ALERT_DISCORD_ACCOUNT_EMAIL": " Recipient@Example.Test ",
    "ETF_ALERT_EMAIL_TO": "legacy@example.test",
    "VOLUME_ALERT_ENABLED": "false",
    "VOLUME_ALERT_TICKERS": "2330.TW",
    "DISCORD_WEBHOOK_URL": GLOBAL_HOOK,
}


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
        self.assertEqual(config.account_email, ACCOUNT_EMAIL)
        self.assertNotIn(ACCOUNT_EMAIL, repr(config))

    def test_empty_destination_uses_legacy_lookup_and_invalid_explicit_value_fails_closed(self):
        setting = "ETF_ALERT_DISCORD_ACCOUNT_EMAIL"
        legacy = alerts.ETFAlertConfig.from_env({**FAKE_ENV, setting: " "})
        self.assertTrue(legacy.ready)
        self.assertEqual(legacy.account_email, "legacy@example.test")
        invalid = alerts.ETFAlertConfig.from_env({**FAKE_ENV, setting: "recipient@.example.test"})
        self.assertFalse(invalid.ready)
        self.assertEqual(invalid.errors, ("invalid_account_email",))

    def test_invalid_flag_missing_etf_watchlist_and_missing_email_fail_closed(self):
        cases = (
            ("ETF_ALERT_ENABLED", "yes", "invalid_enabled"),
            ("ETF_ALERT_TICKERS", "", "invalid_tickers"),
            ("ETF_ALERT_TICKERS", "0050.TW,2330.TW", "invalid_tickers"),
            ("ETF_ALERT_TICKERS", ",".join(f"00{code:02}" for code in range(21)), "too_many_tickers"),
        )
        for name, value, error in cases:
            with self.subTest(name=name, error=error):
                config = alerts.ETFAlertConfig.from_env({**FAKE_ENV, name: value})
                self.assertFalse(config.ready)
                self.assertIn(error, config.errors)
        no_account = alerts.ETFAlertConfig.from_env({
            **FAKE_ENV, "ETF_ALERT_DISCORD_ACCOUNT_EMAIL": "", "ETF_ALERT_EMAIL_TO": "",
        })
        self.assertEqual(no_account.errors, ("invalid_account_email",))


class AccountLookupTests(unittest.TestCase):
    def test_lookup_normalizes_and_queries_only_id_for_the_exact_email(self):
        store = Database.__new__(Database)
        store.supabase = Mock()
        query = store.supabase.table.return_value.select.return_value.eq.return_value.limit
        query.return_value.execute.return_value = SimpleNamespace(data=[{"id": ACCOUNT_ID}])
        self.assertEqual(store.get_account_user_id_by_email(" Recipient@Example.Test "), ACCOUNT_ID)
        store.supabase.table.assert_called_once_with("users")
        store.supabase.table.return_value.select.assert_called_once_with("id")
        store.supabase.table.return_value.select.return_value.eq.assert_called_once_with("email", ACCOUNT_EMAIL)
        query.assert_called_once_with(2)

    def test_lookup_rejects_duplicate_missing_and_invalid_ids(self):
        store = Database.__new__(Database)
        store.supabase = Mock()
        execute = store.supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute
        for rows in ([], [{"id": ACCOUNT_ID}, {"id": "other"}], [{"id": 2}], [{}]):
            with self.subTest(rows=rows):
                execute.return_value = SimpleNamespace(data=rows)
                self.assertIsNone(store.get_account_user_id_by_email(ACCOUNT_EMAIL))
        execute.side_effect = RuntimeError(f"mock request failed for {ACCOUNT_EMAIL}")
        with self.assertRaises(AccountAlertStoreError) as error:
            store.get_account_user_id_by_email(ACCOUNT_EMAIL)
        self.assertNotIn(ACCOUNT_EMAIL, str(error.exception))
        self.assertGreaterEqual(logging.getLogger("httpx").getEffectiveLevel(), logging.WARNING)


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


class FakeAccountStore:
    def __init__(self, encrypted_webhook):
        self.get_account_user_id_by_email = AsyncMock(return_value=ACCOUNT_ID)
        self.get_account_volume_settings = AsyncMock(return_value={
            "tickers": ["2330.TW"],
            "webhook_ciphertext": encrypted_webhook,
        })
        self.events = {}
        self.claim_account_volume_event = AsyncMock(side_effect=self.claim)
        self.finish_account_volume_event = AsyncMock(side_effect=self.finish)

    def claim(self, user_id, ticker, market_date, _now):
        key = (user_id, ticker, market_date)
        if self.events.get(key) in {"sent", "claimed"}:
            return False
        self.events[key] = "claimed"
        return True

    def finish(self, user_id, ticker, market_date, state, _now):
        key = (user_id, ticker, market_date)
        if self.events[key] != "claimed":
            raise AssertionError("event completion requires an active claim")
        self.events[key] = state


class MonitorTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.key = Fernet.generate_key().decode("ascii")
        self.env = patch.dict("os.environ", {
            **FAKE_ENV, "ALERT_WEBHOOK_ENCRYPTION_KEY": self.key,
        }, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.config = alerts.ETFAlertConfig.from_env()
        self.encrypted_webhook = encrypt_webhook(PRIVATE_HOOK)
        self.store = FakeAccountStore(self.encrypted_webhook)
        self.loader = AsyncMock(return_value=matching_bars())
        self.transport = Mock(return_value=SimpleNamespace(status_code=204))
        self.notifier_factory = Mock(side_effect=lambda url: DiscordNotifier(url, transport=self.transport))

    def monitor(self, *, config=None, clock=lambda: AFTER_CLOSE, notifier_factory=None):
        return alerts.ETFGoldenCrossMonitor(
            config if config is not None else self.config, self.store, self.loader,
            notifier_factory if notifier_factory is not None else self.notifier_factory, clock=clock,
        )

    def contents_are_private(self, output):
        for value in (ACCOUNT_EMAIL, ACCOUNT_ID, PRIVATE_HOOK, GLOBAL_HOOK, self.encrypted_webhook, self.key):
            self.assertNotIn(value, output)

    async def test_disabled_invalid_early_and_weekend_runs_do_not_query_or_send(self):
        invalid = alerts.ETFAlertConfig.from_env({"ETF_ALERT_ENABLED": "true"})
        cases = (
            (alerts.ETFAlertConfig(), AFTER_CLOSE, "disabled"),
            (invalid, AFTER_CLOSE, "invalid_config"),
            (self.config, AFTER_CLOSE - timedelta(minutes=1), "outside_scan_window"),
            (self.config, AFTER_CLOSE + timedelta(days=1), "outside_scan_window"),
        )
        for settings, when, status in cases:
            with self.subTest(status=status, when=when):
                self.assertEqual((await self.monitor(config=settings, clock=lambda: when).run())["status"], status)
        self.store.get_account_user_id_by_email.assert_not_awaited()
        self.loader.assert_not_awaited()
        self.transport.assert_not_called()

    async def test_matching_etf_uses_only_designated_accounts_encrypted_webhook_and_own_watchlist(self):
        self.loader.side_effect = [ValueError(f"offline fixture failure for {ACCOUNT_EMAIL}"), matching_bars()]
        stdout = io.StringIO()
        with self.assertLogs(alerts.LOGGER, "INFO") as logs, redirect_stdout(stdout):
            result = await self.monitor(clock=lambda: AFTER_CLOSE.astimezone(timezone.utc)).run()
        self.assertEqual(result, {
            "status": "partial", "checked": 2, "matched": 1, "sent": 1, "failed": 1, "suppressed": 0,
        })
        self.contents_are_private(" ".join(logs.output) + stdout.getvalue() + str(result))
        self.store.get_account_user_id_by_email.assert_awaited_once_with(ACCOUNT_EMAIL)
        self.store.get_account_volume_settings.assert_awaited_once_with(ACCOUNT_ID)
        self.assertEqual([call.args[0] for call in self.loader.await_args_list], ["0050.TW", "00937B.TWO"])
        self.notifier_factory.assert_called_once_with(PRIVATE_HOOK)
        self.transport.assert_called_once()
        self.assertEqual(self.transport.call_args.args, (PRIVATE_HOOK,))
        request = self.transport.call_args.kwargs
        self.assertFalse(request["allow_redirects"])
        self.assertEqual(request["json"]["allowed_mentions"], {"parse": []})
        embeds = request["json"]["embeds"]
        self.assertEqual(len(embeds), 1)
        self.assertEqual(embeds[0]["title"], "ETF 低檔黃金交叉通知")
        signal = alerts.find_golden_cross(matching_bars(), MARKET_DATE)
        for detail in (
            "標的：00937B.TWO", f"交易日：{MARKET_DATE}", "收盤價：94.00",
            f"MACD：{signal.macd:.4f}", f"訊號線：{signal.signal:.4f}",
            f"K：{signal.k:.2f}", f"D：{signal.d:.2f}", f"J：{signal.j:.2f}",
        ):
            self.assertIn(detail, embeds[0]["description"])
        self.contents_are_private(str(request["json"]))

    async def test_unavailable_history_fails_and_stale_history_skips_discord(self):
        self.loader.side_effect = [pd.DataFrame(), matching_bars().iloc[:-1]]
        with self.assertLogs(alerts.LOGGER, "WARNING") as logs:
            result = await self.monitor().run()
        self.assertIn("history_unavailable", logs.output[0])
        self.assertEqual(result, {
            "status": "partial", "checked": 2, "matched": 0, "sent": 0, "failed": 1, "suppressed": 0,
        })
        self.store.claim_account_volume_event.assert_not_awaited()
        self.transport.assert_not_called()

    async def test_missing_account_store_or_webhook_never_falls_back_to_global_destination(self):
        for case, status in (
            ("missing account", "account_unavailable"),
            ("store error", "store_unavailable"),
            ("missing webhook", "webhook_unavailable"),
            ("invalid webhook", "webhook_unavailable"),
            ("missing encryption key", "webhook_unavailable"),
        ):
            with self.subTest(case=case):
                lookup = self.store.get_account_user_id_by_email
                settings = self.store.get_account_volume_settings
                lookup.reset_mock(side_effect=True, return_value=True)
                settings.reset_mock(side_effect=True, return_value=True)
                lookup.return_value = None if case == "missing account" else ACCOUNT_ID
                if case == "store error":
                    settings.side_effect = RuntimeError(f"offline failure: {PRIVATE_HOOK}")
                ciphertext = {
                    "missing webhook": "",
                    "invalid webhook": Fernet(self.key.encode("ascii")).encrypt(
                        b"https://example.test/not-discord"
                    ).decode("ascii"),
                }.get(case, self.encrypted_webhook)
                settings.return_value = {"webhook_ciphertext": ciphertext}
                key = "" if case == "missing encryption key" else self.key
                with patch.dict("os.environ", {"ALERT_WEBHOOK_ENCRYPTION_KEY": key}):
                    with self.assertLogs(alerts.LOGGER, "WARNING") as logs:
                        self.assertEqual((await self.monitor().run())["status"], status)
                    self.contents_are_private(" ".join(logs.output))
                if case == "missing account":
                    settings.assert_not_awaited()
        self.loader.assert_not_awaited()
        self.store.claim_account_volume_event.assert_not_awaited()
        self.notifier_factory.assert_not_called()

    async def test_destination_readiness_never_reads_history_claims_or_sends(self):
        self.assertEqual(await self.monitor().check_destination(), {"status": "ready"})
        self.store.get_account_volume_settings.assert_awaited_once_with(ACCOUNT_ID)
        self.loader.assert_not_awaited()
        self.store.claim_account_volume_event.assert_not_awaited()
        self.notifier_factory.assert_not_called()

    async def test_cross_is_claimed_once_across_workers_without_touching_volume_event(self):
        self.config = alerts.ETFAlertConfig.from_env({**FAKE_ENV, "ETF_ALERT_TICKERS": "0050.TW"})
        volume_key = (ACCOUNT_ID, "0050.TW", str(MARKET_DATE))
        etf_key = (ACCOUNT_ID, "etf-golden-cross:0050.TW", str(MARKET_DATE))
        self.store.events[volume_key] = "sent"
        entered = asyncio.Event()
        released = asyncio.Event()

        async def send(*_args):
            entered.set()
            await released.wait()
            return True

        notifier_factory = Mock(return_value=Mock(send_alert=AsyncMock(side_effect=send)))
        first = asyncio.create_task(self.monitor(notifier_factory=notifier_factory).run())
        try:
            await asyncio.wait_for(entered.wait(), timeout=2)
            during = await self.monitor(notifier_factory=notifier_factory).run()
            self.assertEqual(during["suppressed"], 1)
        finally:
            released.set()
            sent = await asyncio.wait_for(first, timeout=2)
        repeated = await self.monitor(notifier_factory=notifier_factory).run()
        self.assertEqual(sent["sent"], 1)
        self.assertEqual(repeated["suppressed"], 1)
        notifier_factory.return_value.send_alert.assert_awaited_once()
        self.assertEqual(self.store.events, {volume_key: "sent", etf_key: "sent"})
        self.assertTrue(all(call.args[:3] == etf_key for call in self.store.claim_account_volume_event.await_args_list))

    async def test_confirmed_discord_failure_releases_event_for_same_day_retry(self):
        self.config = alerts.ETFAlertConfig.from_env({**FAKE_ENV, "ETF_ALERT_TICKERS": "0050.TW"})
        self.transport.side_effect = [SimpleNamespace(status_code=503), SimpleNamespace(status_code=204)]
        monitor = self.monitor()
        self.assertEqual((await monitor.run())["failed"], 1)
        self.assertEqual(list(self.store.events.values()), ["failed"])
        self.assertEqual((await monitor.run())["sent"], 1)
        self.assertEqual(list(self.store.events.values()), ["sent"])
        self.assertEqual((await monitor.run())["suppressed"], 1)
        self.assertEqual(self.transport.call_count, 2)

    async def test_claim_failure_fails_closed_before_transport(self):
        self.store.claim_account_volume_event.side_effect = RuntimeError(f"offline failure: {PRIVATE_HOOK}")
        with self.assertLogs(alerts.LOGGER, "WARNING") as logs:
            result = await self.monitor().run()
        self.assertEqual(result["status"], "store_unavailable")
        self.assertEqual(result["failed"], 1)
        self.contents_are_private(" ".join(logs.output))
        self.notifier_factory.assert_not_called()

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

    async def test_one_shot_check_uses_real_readiness_path_and_never_sends(self):
        close = AsyncMock()
        with (
            patch("database.Database", return_value=self.store),
            patch("async_data_provider.close_async_provider", close),
            patch("async_data_provider.get_async_provider", AsyncMock()) as provider,
            patch("notifier.requests.post") as transport,
        ):
            self.assertEqual(await alerts._run_once(check=True), 0)
            self.store.get_account_user_id_by_email.return_value = None
            self.assertEqual(await alerts._run_once(check=True), 1)
        self.assertEqual(close.await_count, 2)
        provider.assert_not_awaited()
        self.store.claim_account_volume_event.assert_not_awaited()
        transport.assert_not_called()

    async def test_one_shot_scan_propagates_failure_and_closes_market_provider(self):
        close = AsyncMock()
        monitor = Mock(run=AsyncMock(side_effect=[{"status": "partial"}, {"status": "success"}]))
        with (
            patch("database.Database", return_value=self.store),
            patch.object(alerts, "ETFGoldenCrossMonitor", return_value=monitor),
            patch("async_data_provider.close_async_provider", close),
        ):
            self.assertEqual(await alerts._run_once(), 1)
            self.assertEqual(await alerts._run_once(), 0)
        self.assertEqual(close.await_count, 2)


class SchedulingTests(unittest.IsolatedAsyncioTestCase):
    async def test_application_lifespan_wires_daily_handler_catchup_and_non_sending_probe(self):
        import main

        configured = alerts.ETFAlertConfig.from_env(FAKE_ENV)
        for config, after_close in ((configured, True), (configured, False), (alerts.ETFAlertConfig(), True)):
            with self.subTest(ready=config.ready, after_close=after_close):
                job_runner = MagicMock(
                    start=AsyncMock(), stop=AsyncMock(), run_high_priority=AsyncMock(), run_background=AsyncMock(),
                )
                monitor = MagicMock(run=AsyncMock(), check_destination=AsyncMock())
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
                self.assertEqual(job_runner.run_background.await_count, int(config.ready and not after_close))
                if config.ready and not after_close:
                    self.assertIs(job_runner.run_background.await_args.args[1], monitor.check_destination)

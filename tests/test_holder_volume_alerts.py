import asyncio
import contextlib
import io
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock

import pandas as pd
import requests
from requests.adapters import BaseAdapter

from holder_volume_alerts import (
    HolderAlertConfig,
    HolderVolumeAlertMonitor,
    TAIPEI,
    aggregate_large_holder_history,
    evaluate_holder_volume_signal,
    event_key_for,
    parse_alert_tickers,
    merge_holder_history,
    should_startup_catchup,
)
from notifier import DiscordNotifier


NOW = datetime(2026, 9, 21, 20, 30, tzinfo=TAIPEI)


def tdcc_rows(ticker="2330.TW", ratios=(10.0, 10.25, 10.5), dates=None):
    dates = dates or ("2026-09-05", "2026-09-12", "2026-09-19")
    rows = []
    for data_date, ratio in zip(dates, ratios):
        rows.append({
            "證券代號": ticker.split(".")[0],
            "資料日期": data_date,
            "持股分級": "12",
            "占集保庫存數比例%": str(ratio),
        })
    return rows


def market_frame(
    ticker="2330.TW", *, latest=150, baseline=100, sessions=20,
    market_date="2026-09-21", source="yahoo",
):
    end = pd.Timestamp(market_date)
    index = pd.bdate_range(end=end, periods=sessions + 1)
    frame = pd.DataFrame({
        "Open": [100.0] * len(index),
        "High": [101.0] * len(index),
        "Low": [99.0] * len(index),
        "Close": [100.0] * len(index),
        "Volume": [baseline] * sessions + [latest],
    }, index=index)
    frame.attrs["route"] = {
        "source": source,
        "asof": market_date,
        "degraded": False,
        "price_basis": "unadjusted_daily",
    }
    return frame


class FakeRepository:
    def __init__(self):
        self.snapshots = []
        self.states = []
        self.events = {}
        self.sent = {}
        self.calls = []
        self.locked = False
        self.fail_snapshot = False
        self.last_run = {}
        self.holder_history = {}

    def acquire_holder_alert_lock(self, owner, now):
        self.calls.append("acquire")
        if self.locked:
            return False
        self.locked = True
        return True

    def release_holder_alert_lock(self, owner):
        self.calls.append("release")
        self.locked = False
        return True

    def upsert_holder_alert_snapshot(self, snapshot):
        self.calls.append("snapshot")
        if self.fail_snapshot:
            raise RuntimeError("secret provider error")
        self.snapshots.append(snapshot)
        history = self.holder_history.setdefault(snapshot["ticker"], [])
        history[:] = [
            item for item in history if item["holder_date"] != snapshot["holder_date"]
        ]
        history.append({
            "holder_date": snapshot["holder_date"],
            "large_holder_ratio": snapshot["large_holder_ratio"],
        })

    def get_holder_alert_history(self, ticker, limit=3):
        self.calls.append("history")
        return sorted(
            self.holder_history.get(ticker, []),
            key=lambda item: item["holder_date"],
            reverse=True,
        )[:limit]

    def set_holder_alert_state(self, key, value, now):
        self.calls.append("state")
        self.states.append((key, value))
        if key == "last_run":
            self.last_run = dict(value)

    def get_holder_alert_state(self, key):
        self.calls.append("get_state")
        return dict(self.last_run) if key == "last_run" else {}

    def has_recent_sent_holder_alert(self, ticker, since):
        self.calls.append("cooldown")
        return ticker in self.sent and self.sent[ticker] >= since

    def claim_holder_alert_event(self, key, ticker, holder_date, now):
        self.calls.append("claim")
        event = self.events.get(key)
        if event is None:
            self.events[key] = {"status": "claimed", "attempts": 1, "ticker": ticker}
            return True
        if event["status"] == "failed" and event["retry_after"] <= now:
            event.update(status="claimed", attempts=event["attempts"] + 1)
            return True
        return False

    def mark_holder_alert_sent(self, key, now):
        self.calls.append("sent")
        self.events[key]["status"] = "sent"
        self.sent[self.events[key]["ticker"]] = now

    def mark_holder_alert_failed(self, key, now, retry_after):
        self.calls.append("failed")
        self.events[key].update(status="failed", retry_after=retry_after)


class FakeNotifier:
    def __init__(self, succeeds=True):
        self.succeeds = succeeds
        self.sent = []

    def send_holder_volume_alert(self, result, key):
        self.sent.append((result, key))
        return self.succeeds


def make_monitor(config=None, repo=None, notifier=None, rows=None, frames=None, clock=None):
    repo = repo or FakeRepository()
    notifier = notifier or FakeNotifier()
    rows = rows if rows is not None else tdcc_rows()
    frames = frames or {"2330.TW": market_frame()}

    async def load_market(ticker):
        value = frames[ticker]
        if isinstance(value, Exception):
            raise value
        return value

    monitor = HolderVolumeAlertMonitor(
        config or HolderAlertConfig(True, True, ("2330.TW",)),
        repo,
        lambda: rows,
        load_market,
        notifier,
        clock=clock or (lambda: NOW),
    )
    return monitor, repo, notifier


class ConfigurationTests(unittest.TestCase):
    def test_tickers_require_suffix_deduplicate_and_limit_twenty(self):
        self.assertEqual(parse_alert_tickers("2330.tw,6488.TWO,2330.TW"), ("2330.TW", "6488.TWO"))
        self.assertEqual(parse_alert_tickers(",".join(["2330.TW"] * 21)), ("2330.TW",))
        for invalid in ("2330", "ABC.TW", "123.TW", "1234567.TWO"):
            with self.assertRaises(ValueError):
                parse_alert_tickers(invalid)
        with self.assertRaises(ValueError):
            parse_alert_tickers(",".join(f"{1000 + item}.TW" for item in range(21)))

    def test_defaults_are_disabled_and_dry_run(self):
        config = HolderAlertConfig.from_env({})
        self.assertFalse(config.enabled)
        self.assertTrue(config.dry_run)
        self.assertFalse(config.ready)
        invalid = HolderAlertConfig.from_env({
            "HOLDER_ALERT_ENABLED": "true",
            "HOLDER_ALERT_DRY_RUN": "false",
            "HOLDER_ALERT_TICKERS": "2330",
        })
        self.assertIn("invalid_ticker", invalid.errors)
        self.assertIn("tickers_required", invalid.errors)

    def test_startup_catchup_uses_taipei_2030_boundary(self):
        self.assertFalse(should_startup_catchup(datetime(2026, 9, 21, 20, 29, tzinfo=TAIPEI)))
        self.assertTrue(should_startup_catchup(datetime(2026, 9, 21, 20, 30, tzinfo=TAIPEI)))


class SignalTests(unittest.TestCase):
    def test_levels_12_to_15_are_summed_per_distinct_date(self):
        rows = tdcc_rows(ratios=(1, 2, 3))
        rows.extend({
            "證券代號": "2330", "資料日期": data_date,
            "持股分級": "15", "占集保庫存數比例%": "4",
        } for data_date in ("2026-09-05", "2026-09-12", "2026-09-19"))
        self.assertEqual(
            [item["ratio"] for item in aggregate_large_holder_history(rows, "2330.TW")],
            [5.0, 6.0, 7.0],
        )

    def test_persisted_weekly_snapshots_complete_three_period_history(self):
        current = aggregate_large_holder_history(
            tdcc_rows(ratios=(10.5,), dates=("2026-09-19",)), "2330.TW"
        )
        merged = merge_holder_history(current, [
            {"holder_date": "2026-09-12", "large_holder_ratio": 10.25},
            {"holder_date": "2026-09-05", "large_holder_ratio": 10.0},
        ])
        self.assertEqual([item["ratio"] for item in merged], [10.0, 10.25, 10.5])
        result = evaluate_holder_volume_signal(
            "2330.TW",
            tdcc_rows(ratios=(10.5,), dates=("2026-09-19",)),
            market_frame(),
            now=NOW,
            stored_history=merged[:2],
        )
        self.assertTrue(result["eligible"])

    def test_exact_thresholds_and_minimum_history_are_eligible(self):
        result = evaluate_holder_volume_signal(
            "2330.TW", tdcc_rows(), market_frame(sessions=15), now=NOW
        )
        self.assertTrue(result["eligible"])
        self.assertEqual(result["holder_increase_pp"], 0.5)
        self.assertEqual(result["volume"]["volume_multiple"], 1.5)
        self.assertEqual(result["volume"]["baseline_sessions"], 15)

    def test_strict_increase_and_threshold_failures_have_stable_reasons(self):
        flat = evaluate_holder_volume_signal(
            "2330.TW", tdcc_rows(ratios=(10, 10, 10.6)), market_frame(), now=NOW
        )
        self.assertEqual(flat["reason"], "holder_ratio_not_strictly_increasing")
        low_holder = evaluate_holder_volume_signal(
            "2330.TW", tdcc_rows(ratios=(10, 10.2, 10.49)), market_frame(), now=NOW
        )
        self.assertEqual(low_holder["reason"], "holder_increase_below_threshold")
        low_volume = evaluate_holder_volume_signal(
            "2330.TW", tdcc_rows(), market_frame(latest=149), now=NOW
        )
        self.assertEqual(low_volume["reason"], "volume_multiple_below_threshold")

    def test_volume_uses_previous_twenty_positive_median(self):
        frame = market_frame(sessions=25)
        frame.loc[frame.index[0:5], "Volume"] = [10000, 10000, 10000, 10000, 10000]
        result = evaluate_holder_volume_signal("2330.TW", tdcc_rows(), frame, now=NOW)
        self.assertEqual(result["volume"]["baseline_sessions"], 20)
        self.assertEqual(result["volume"]["baseline_median_volume"], 100.0)

    def test_stale_mismatch_and_insufficient_volume_are_rejected(self):
        stale = evaluate_holder_volume_signal(
            "2330.TW",
            tdcc_rows(dates=("2026-08-20", "2026-08-27", "2026-09-06")),
            market_frame(), now=NOW,
        )
        self.assertEqual(stale["reason"], "holder_data_stale")
        mismatch = evaluate_holder_volume_signal(
            "2330.TW", tdcc_rows(dates=("2026-09-03", "2026-09-08", "2026-09-13")),
            market_frame(market_date="2026-09-21"), now=NOW,
        )
        self.assertEqual(mismatch["reason"], "market_holder_date_mismatch")
        insufficient = evaluate_holder_volume_signal(
            "2330.TW", tdcc_rows(), market_frame(sessions=14), now=NOW
        )
        self.assertEqual(insufficient["reason"], "volume_history_insufficient")


class MonitorTests(unittest.IsolatedAsyncioTestCase):
    async def test_dry_run_writes_snapshot_state_but_never_claims_or_sends(self):
        monitor, repo, notifier = make_monitor()
        result = await monitor.run(trigger="test")
        self.assertEqual(result["results"][0]["action"], "would_alert")
        self.assertEqual(len(repo.snapshots), 1)
        self.assertEqual(len(repo.states), 1)
        self.assertNotIn("claim", repo.calls)
        self.assertEqual(notifier.sent, [])

    async def test_single_tdcc_period_accumulates_snapshot_without_alert(self):
        monitor, repo, notifier = make_monitor(
            rows=tdcc_rows(ratios=(10.5,), dates=("2026-09-19",))
        )
        result = await monitor.run(trigger="test")
        self.assertEqual(result["results"][0]["reason"], "holder_history_insufficient")
        self.assertEqual(repo.snapshots[0]["large_holder_ratio"], 10.5)
        self.assertEqual(notifier.sent, [])

    async def test_sent_event_is_idempotent_and_seven_day_cooldown_applies(self):
        config = HolderAlertConfig(True, False, ("2330.TW",))
        monitor, repo, notifier = make_monitor(config=config)
        first = await monitor.run()
        second = await monitor.run()
        self.assertEqual(first["results"][0]["action"], "sent")
        self.assertEqual(second["results"][0]["reason"], "cooldown_active")
        self.assertEqual(len(notifier.sent), 1)
        self.assertEqual(next(iter(repo.events)), event_key_for("2330.TW", "2026-09-19"))

    async def test_failed_event_waits_six_hours_then_retries(self):
        current = [NOW]
        repo = FakeRepository()
        notifier = FakeNotifier(succeeds=False)
        monitor, _, _ = make_monitor(
            config=HolderAlertConfig(True, False, ("2330.TW",)),
            repo=repo, notifier=notifier, clock=lambda: current[0],
        )
        first = await monitor.run()
        current[0] += timedelta(hours=5, minutes=59)
        deferred = await monitor.run()
        current[0] += timedelta(minutes=1)
        retried = await monitor.run()
        self.assertEqual(first["results"][0]["reason"], "notification_failed")
        self.assertEqual(deferred["results"][0]["reason"], "duplicate_or_retry_deferred")
        self.assertEqual(retried["results"][0]["reason"], "notification_failed")
        self.assertEqual(len(notifier.sent), 2)

    async def test_redirect_is_failed_and_retries_after_six_hours_without_cooldown(self):
        current = [NOW]
        redirect = Mock(status_code=302)
        accepted = Mock(status_code=204)
        accepted.raise_for_status.side_effect = AssertionError("must not inspect response")
        transport = Mock(side_effect=[redirect, accepted])
        notifier = DiscordNotifier("https://example.invalid/hook", transport=transport)
        repo = FakeRepository()
        monitor, _, _ = make_monitor(
            config=HolderAlertConfig(True, False, ("2330.TW",)),
            repo=repo,
            notifier=notifier,
            clock=lambda: current[0],
        )

        first = await monitor.run()
        current[0] += timedelta(hours=5, minutes=59)
        deferred = await monitor.run()
        current[0] += timedelta(minutes=1)
        retried = await monitor.run()

        self.assertEqual(first["results"][0]["reason"], "notification_failed")
        self.assertEqual(deferred["results"][0]["reason"], "duplicate_or_retry_deferred")
        self.assertEqual(retried["results"][0]["action"], "sent")
        self.assertEqual(transport.call_count, 2)
        self.assertTrue(all(call.kwargs["allow_redirects"] is False for call in transport.call_args_list))
        self.assertEqual(repo.events[event_key_for("2330.TW", "2026-09-19")]["attempts"], 2)
        self.assertIn("2330.TW", repo.sent)
        redirect.raise_for_status.assert_not_called()
        accepted.raise_for_status.assert_not_called()

    async def test_database_failure_is_fail_closed_before_notification(self):
        repo = FakeRepository()
        repo.fail_snapshot = True
        monitor, _, notifier = make_monitor(
            config=HolderAlertConfig(True, False, ("2330.TW",)), repo=repo
        )
        result = await monitor.run()
        self.assertEqual(result["results"][0]["reason"], "database_unavailable")
        self.assertNotIn("claim", repo.calls)
        self.assertEqual(notifier.sent, [])
        self.assertNotIn("secret provider error", str(result))

    async def test_one_ticker_failure_does_not_stop_the_other(self):
        config = HolderAlertConfig(True, True, ("2330.TW", "6488.TWO"))
        rows = tdcc_rows() + tdcc_rows("6488.TWO")
        monitor, repo, _ = make_monitor(
            config=config,
            rows=rows,
            frames={"2330.TW": RuntimeError("private upstream"), "6488.TWO": market_frame("6488.TWO")},
        )
        result = await monitor.run()
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["results"][0]["reason"], "market_upstream_unavailable")
        self.assertEqual(result["results"][1]["action"], "would_alert")
        self.assertNotIn("private upstream", str(result))
        self.assertEqual(len(repo.snapshots), 1)

    async def test_process_lock_failure_stops_before_upstream_io(self):
        repo = FakeRepository()
        repo.locked = True
        tdcc_loader = Mock(side_effect=AssertionError("must not load TDCC"))
        market_loader = Mock(side_effect=AssertionError("must not load market"))
        monitor = HolderVolumeAlertMonitor(
            HolderAlertConfig(True, False, ("2330.TW",)),
            repo,
            tdcc_loader,
            market_loader,
            FakeNotifier(),
            clock=lambda: NOW,
        )
        result = await monitor.run()
        self.assertEqual(result["status"], "lock_unavailable")
        tdcc_loader.assert_not_called()
        market_loader.assert_not_called()

    async def test_status_is_memory_only_and_secret_safe(self):
        monitor, repo, _ = make_monitor()
        before = list(repo.calls)
        status = monitor.status()
        health = monitor.health_summary()
        self.assertEqual(repo.calls, before)
        self.assertNotIn("webhook", str(status).lower())
        self.assertNotIn("supabase", str(health).lower())

    async def test_startup_catchup_skips_a_completed_local_date(self):
        monitor, repo, _ = make_monitor()
        self.assertTrue(await monitor.needs_startup_catchup())
        repo.last_run = {"date": NOW.date().isoformat(), "status": "success"}
        self.assertFalse(await monitor.needs_startup_catchup())


class NotifierAndMigrationTests(unittest.TestCase):
    def test_notifier_disables_mentions_uses_timeout_and_keeps_legacy_api(self):
        response = Mock()
        response.status_code = 204
        response.raise_for_status.side_effect = AssertionError("must not inspect response")
        transport = Mock(return_value=response)
        notifier = DiscordNotifier("https://example.invalid/hook", transport=transport)
        result = evaluate_holder_volume_signal("2330.TW", tdcc_rows(), market_frame(), now=NOW)
        self.assertTrue(notifier.send_holder_volume_alert(result, event_key_for("2330.TW", "2026-09-19")))
        payload = transport.call_args.kwargs["json"]
        self.assertEqual(transport.call_args.kwargs["timeout"], (3, 7))
        self.assertIs(transport.call_args.kwargs["allow_redirects"], False)
        self.assertEqual(payload["allowed_mentions"], {"parse": []})
        description = payload["embeds"][0]["description"]
        for expected in ("2026-09-05", "0.50", "1.50x", "yahoo", "v1:2330.TW:2026-09-19", "不構成投資建議"):
            self.assertIn(expected, description)
        self.assertTrue(notifier.send("legacy", "compatible"))
        response.raise_for_status.assert_not_called()

        failed_transport = Mock(side_effect=RuntimeError("https://secret.invalid/hook token-value"))
        failed_notifier = DiscordNotifier("https://secret.invalid/hook", transport=failed_transport)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertFalse(failed_notifier.send("safe", "message"))
        self.assertNotIn("secret.invalid", output.getvalue())
        self.assertNotIn("token-value", output.getvalue())

    def test_notifier_accepts_only_2xx_without_leaking_response_details(self):
        responses = []
        for status in (204, 302, 429, True, None):
            response = Mock(status_code=status)
            response.raise_for_status.side_effect = AssertionError("must not inspect response")
            responses.append(response)
        transport = Mock(side_effect=responses)
        notifier = DiscordNotifier("https://secret.invalid/hook", transport=transport)

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            outcomes = [
                notifier.send("status", str(code))
                for code in (204, 302, 429, True, None)
            ]

        self.assertEqual(outcomes, [True, False, False, False, False])
        self.assertTrue(all(call.kwargs["allow_redirects"] is False for call in transport.call_args_list))
        for response in responses:
            response.raise_for_status.assert_not_called()
        self.assertNotIn("secret.invalid", output.getvalue())
        self.assertNotIn("hook", output.getvalue())

    def test_requests_adapter_does_not_follow_307_or_repost_json(self):
        class RedirectAdapter(BaseAdapter):
            def __init__(self):
                self.requests = []

            def send(self, request, **kwargs):
                self.requests.append(request)
                response = requests.Response()
                response.status_code = 307 if len(self.requests) == 1 else 204
                response.url = request.url
                response.request = request
                response.headers["Location"] = "https://redirect.invalid/elsewhere"
                return response

            def close(self):
                pass

        adapter = RedirectAdapter()
        with requests.Session() as session:
            session.mount("https://", adapter)
            notifier = DiscordNotifier(
                "https://discord.invalid/webhook",
                transport=session.post,
            )
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertFalse(notifier.send("redirect", "sensitive payload"))

        self.assertEqual(len(adapter.requests), 1)
        self.assertEqual(adapter.requests[0].method, "POST")
        self.assertIn(b"sensitive payload", adapter.requests[0].body)
        self.assertNotIn("redirect.invalid", output.getvalue())
        self.assertNotIn("discord.invalid", output.getvalue())

    def test_migration_has_three_rls_tables_and_atomic_claims(self):
        sql = Path("migrations/002_holder_volume_alerts.sql").read_text(encoding="utf-8").lower()
        for table in ("holder_alert_snapshots", "holder_alert_events", "holder_alert_state"):
            self.assertIn(f"create table if not exists public.{table}", sql)
            self.assertIn(f"alter table public.{table} enable row level security", sql)
        self.assertIn("primary key (ticker, holder_date)", sql)
        self.assertIn("event_key text primary key", sql)
        self.assertIn("claim_holder_alert_run", sql)
        self.assertIn("claim_holder_alert_event", sql)
        self.assertIn("get diagnostics affected = row_count", sql)
        self.assertIn("grant execute on function public.claim_holder_alert_event", sql)
        self.assertNotIn("create policy", sql)

    def test_main_wires_taipei_schedule_startup_status_and_health(self):
        source = Path("main.py").read_text(encoding="utf-8")
        self.assertIn('"holder_volume_alerts"', source)
        self.assertIn('hour=20', source)
        self.assertIn('minute=30', source)
        self.assertIn('timezone_name="Asia/Taipei"', source)
        self.assertIn("await holder_alert_monitor.needs_startup_catchup()", source)
        self.assertIn('@app.get("/api/holder-alerts/status")', source)
        self.assertIn('"holder_alerts": holder_alert_monitor.health_summary()', source)

    def test_deployment_defaults_and_manual_free_plan_limit_are_documented(self):
        env_example = Path(".env.example").read_text(encoding="utf-8")
        render = Path("render.yaml").read_text(encoding="utf-8")
        manual = Path("MANUAL_SETUP.md").read_text(encoding="utf-8")
        self.assertIn("HOLDER_ALERT_ENABLED=false", env_example)
        self.assertIn("HOLDER_ALERT_DRY_RUN=true", env_example)
        self.assertIn("HOLDER_ALERT_ENABLED", render)
        self.assertIn('value: "false"', render)
        self.assertIn("Render Free", manual)
        self.assertIn("migrations/002_holder_volume_alerts.sql", manual)


if __name__ == "__main__":
    unittest.main()

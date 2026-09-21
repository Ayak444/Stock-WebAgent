"""Offline fixture tests for the cash-only next-open backtest."""
import asyncio
import ast
import json
import importlib
import threading
import time
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch
from types import SimpleNamespace

import pandas as pd
from fastapi.responses import JSONResponse

from backtest import Backtester, SUPPORTED_BACKTEST_DAYS, _cost, _max_affordable, _signal
from data_provider import BACKTEST_HISTORY_PLAN, BACKTEST_MAX_SOURCE_SECONDS, DataProvider, _bounded_json_get
import data_provider


TODAY = date(2026, 9, 21)


def fixture(count=60, *, source="twse", end="2026-09-21"):
    dates = pd.bdate_range(end=end, periods=count)
    frame = pd.DataFrame({
        "Open": [100.0] * count, "High": [200.0] * count,
        "Low": [50.0] * count, "Close": [100.0] * count,
        "Volume": [1000] * count, "signal_ma": [100.0] * count,
        "signal_rsi": [50.0] * count,
    }, index=dates)
    frame.attrs["route"] = {
        "source": source, "asof": dates[-1].date().isoformat(),
        "price_basis": "unadjusted_daily",
    }
    return frame


def indicators(frame):
    result = frame.copy()
    result["MA20"] = result["signal_ma"]
    result["RSI"] = result["signal_rsi"]
    return result


def run(frame, days=30, **kwargs):
    with patch("backtest.TechnicalAnalyzer.calculate_indicators", side_effect=indicators):
        return Backtester.run("2330.TW", days, frame=frame, now=TODAY, **kwargs)


class CashBacktestTests(TestCase):
    def test_bounded_yahoo_loader_covers_each_window_in_one_request(self):
        self.assertEqual(set(BACKTEST_HISTORY_PLAN), {60, 120, 210, 395})
        for required, (history_range, _) in BACKTEST_HISTORY_PLAN.items():
            dates = pd.bdate_range(end="2026-09-21", periods=required)
            payload = {"chart": {"result": [{
                "timestamp": [int(stamp.timestamp()) for stamp in dates],
                "indicators": {"quote": [{key: [100.0] * required for key in
                                           ("open", "high", "low", "close", "volume")}]},
            }]}}
            response = SimpleNamespace(iter_content=lambda chunk_size: [json.dumps(payload).encode()], close=lambda: None)
            with patch("data_provider.requests.get", return_value=response) as get, \
                 patch("data_provider.DataProvider._fetch_twse_month", side_effect=AssertionError("unneeded official")):
                data = DataProvider.get_backtest_history("2330.TW", required)
            self.assertGreaterEqual(len(data), required)
            self.assertEqual(data.attrs["route"]["source"], "yahoo")
            self.assertIn("range=" + history_range, get.call_args.args[0])
            self.assertEqual(get.call_count, 1)
            self.assertEqual(get.call_args.kwargs["timeout"], (1, 1.5))
            self.assertTrue(get.call_args.kwargs["stream"])

    def test_official_fallback_has_distinct_bounded_months_and_workers(self):
        active = 0
        maximum = 0
        calls = []
        guard = threading.Lock()

        def fake_month(stock_id, target, bounded):
            nonlocal active, maximum
            with guard:
                active += 1
                maximum = max(maximum, active)
                calls.append((stock_id, target.strftime("%Y-%m"), bounded))
            time.sleep(0.01)
            with guard:
                active -= 1
            return []

        with patch("data_provider.requests.get", side_effect=RuntimeError("offline")) as get, \
             patch("data_provider.DataProvider._fetch_twse_month", side_effect=fake_month):
            result = DataProvider.get_backtest_history("2330.TW", 395)
        self.assertTrue(result.empty)
        self.assertEqual(get.call_count, 1)
        self.assertEqual(len(calls), 24)
        self.assertEqual(len({month for _, month, _ in calls}), 24)
        self.assertTrue(all(bounded for _, _, bounded in calls))
        self.assertGreater(maximum, 1)
        self.assertLessEqual(maximum, 6)
        self.assertEqual(active, 0)

    def test_loader_rejects_unplanned_bars_without_network(self):
        with patch("data_provider.requests.get", side_effect=AssertionError("network")) as get:
            with self.assertRaises(ValueError):
                DataProvider.get_backtest_history("2330.TW", 3680)
        get.assert_not_called()

    def test_provider_import_does_not_request_network(self):
        with patch("requests.get", side_effect=AssertionError("import requested network")) as get:
            importlib.reload(data_provider)
        get.assert_not_called()

    def test_trickling_source_hits_deadline_and_closes_response(self):
        closed = []
        response = SimpleNamespace(iter_content=lambda chunk_size: [b"{", b"}"],
                                   close=lambda: closed.append(True))
        with patch("data_provider.requests.get", return_value=response) as get, \
             patch("data_provider.time.monotonic", side_effect=[0, 1, 3]):
            with self.assertRaises(TimeoutError):
                _bounded_json_get("https://example.invalid/fixture")
        self.assertEqual(closed, [True])
        self.assertEqual(get.call_args.kwargs["timeout"], (1, 1.5))
        self.assertEqual(BACKTEST_MAX_SOURCE_SECONDS, 20)

    def test_next_open_gap_and_affordable_whole_shares(self):
        frame = fixture()
        frame.iloc[28, frame.columns.get_loc("Close")] = 99
        frame.iloc[29, frame.columns.get_loc("Close")] = 101
        frame.iloc[30, frame.columns.get_loc("Open")] = 150
        result = run(frame)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["trades"][0]["date"], frame.index[30].date().isoformat())
        self.assertEqual(result["trades"][0]["price"], 150)
        self.assertEqual(result["trades"][0]["shares"], 665)
        self.assertEqual(result["trades"][0]["commission"], 142)
        self.assertEqual(result["trades"][0]["cash_after"], 108)
        self.assertEqual(result["ending_shares"], 665)
        self.assertEqual(result["win_rate"], None)
        self.assertEqual(result["buy_hold_shares"], 665)
        self.assertEqual(result["window_start"], frame.index[30].date().isoformat())
        self.assertEqual(result["window_end"], frame.index[59].date().isoformat())

    def test_last_bar_signal_is_not_executed(self):
        frame = fixture()
        frame.iloc[58, frame.columns.get_loc("Close")] = 99
        frame.iloc[59, frame.columns.get_loc("Close")] = 101
        result = run(frame)
        self.assertEqual(result["latest_signal"], "BUY")
        self.assertEqual(result["trades"], [])
        self.assertEqual(result["win_rate"], None)
        self.assertEqual(result["final_value"], 100000)
        self.assertEqual(result["max_drawdown"], 0)

    def test_sell_cost_tax_roundtrip_and_win_rate(self):
        frame = fixture()
        frame.iloc[28, frame.columns.get_loc("Close")] = 99
        frame.iloc[29, frame.columns.get_loc("Close")] = 101
        frame.iloc[30, frame.columns.get_loc("Close")] = 101
        frame.iloc[31, frame.columns.get_loc("Close")] = 99
        frame.iloc[32, frame.columns.get_loc("Open")] = 120
        result = run(frame)
        self.assertEqual([trade["action"] for trade in result["trades"]], ["BUY", "SELL"])
        self.assertEqual(result["trades"][1]["date"], frame.index[32].date().isoformat())
        self.assertEqual(result["trades"][1]["tax"], 359)
        self.assertEqual(result["closed_trade_count"], 1)
        self.assertEqual(result["win_rate"], 100.0)
        self.assertEqual(result["ending_shares"], 0)
        self.assertEqual(result["outperformance"],
                         round(result["strategy_return"] - result["buy_hold_return"], 2))
        self.assertGreaterEqual(result["ending_cash"], 0)
        self.assertTrue(all(trade["cash_after"] >= 0 for trade in result["trades"]))

    def test_unfunded_sale_fee_fails_closed_without_negative_cash_success(self):
        frame = fixture()
        frame.iloc[28, frame.columns.get_loc("Close")] = 99
        frame.iloc[29, frame.columns.get_loc("Close")] = 101
        frame.iloc[30, frame.columns.get_loc("Open")] = 99.98
        frame.iloc[30, frame.columns.get_loc("Close")] = 101
        frame.iloc[31, frame.columns.get_loc("Close")] = 99
        frame.iloc[32, frame.columns.get_loc("Open")] = 0.01
        frame.iloc[32, frame.columns.get_loc("Low")] = 0.01
        result = run(frame, commission_rate=0, min_commission=20, sell_tax_rate=0)
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["code"], "sale_cost_unfunded")
        self.assertEqual(result["trade_date"], frame.index[32].date().isoformat())
        self.assertEqual(result["available_cash"], 0)
        self.assertEqual(result["sale_gross"], 10)
        self.assertEqual(result["sale_commission"], 20)
        self.assertEqual(result["shortfall"], 10)
        self.assertNotIn("trades", result)

    def test_unaffordable_buy_is_zero_shares_and_cash_stays_nonnegative(self):
        frame = fixture()
        frame.iloc[28, frame.columns.get_loc("Close")] = 99
        frame.iloc[29, frame.columns.get_loc("Close")] = 101
        frame.iloc[30, frame.columns.get_loc("Open")] = 100001
        frame.iloc[30, frame.columns.get_loc("High")] = 100001
        result = run(frame)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["trades"], [])
        self.assertEqual(result["ending_shares"], 0)
        self.assertEqual(result["ending_cash"], 100000)
        self.assertEqual(result["buy_hold_shares"], 0)
        self.assertEqual(result["buy_hold_final_value"], 100000)

    def test_warmup_window_and_requested_days(self):
        self.assertEqual(run(fixture(59))["code"], "insufficient_data")
        frame = fixture(121)
        thirty = run(frame, days=30)
        ninety = run(frame, days=90)
        self.assertEqual(thirty["window_start"], frame.index[91].date().isoformat())
        self.assertEqual(ninety["window_start"], frame.index[31].date().isoformat())
        self.assertEqual(thirty["days"], 30)
        self.assertEqual(ninety["days"], 90)

    def test_fee_rounding_minimum_and_affordability(self):
        self.assertEqual(_cost(Decimal("1000"), Decimal("0.001425"), Decimal("20")), Decimal("20"))
        self.assertEqual(_cost(Decimal("1000"), Decimal("0.0255"), Decimal("0")), Decimal("26"))
        self.assertEqual(_cost(Decimal("1000"), Decimal("0"), Decimal("20.5")), Decimal("21"))
        self.assertEqual(_max_affordable(Decimal("100000"), Decimal("100.50"),
                                         Decimal("0.001425"), Decimal("20")), 993)
        frame = fixture()
        base = run(frame)
        high_cost = run(frame, commission_rate=0.02, min_commission=50, sell_tax_rate=0.01)
        self.assertLess(high_cost["buy_hold_shares"], base["buy_hold_shares"])
        self.assertLess(high_cost["buy_hold_return"], base["buy_hold_return"])
        self.assertEqual(high_cost["costs"]["sell_tax_rate"], 0.01)

    def test_drawdown_includes_fee_and_buy_hold_same_window(self):
        frame = fixture()
        frame.iloc[28, frame.columns.get_loc("Close")] = 99
        frame.iloc[29, frame.columns.get_loc("Close")] = 101
        result = run(frame)
        self.assertGreater(result["max_drawdown"], 0)
        self.assertEqual(result["final_value"], result["buy_hold_final_value"])
        self.assertEqual(result["outperformance"], 0)

    def test_source_stale_date_and_validation_errors(self):
        frame = fixture()
        frame.attrs["route"]["source"] = ""
        self.assertEqual(run(frame)["code"], "source_unverified")
        frame.attrs["route"]["source"] = "twse"
        frame.attrs["route"]["asof"] = "2026-09-20"
        self.assertEqual(run(frame)["code"], "source_date_mismatch")
        frame.attrs["route"]["asof"] = "2026-09-21"
        frame.attrs["route"]["price_basis"] = "adjusted"
        self.assertEqual(run(frame)["code"], "price_basis_unverified")
        frame.attrs["route"]["price_basis"] = "unadjusted_daily"
        frame.iloc[0, frame.columns.get_loc("Open")] = -1
        self.assertEqual(run(frame)["code"], "invalid_data")
        self.assertEqual(run(fixture(end="2026-09-01"))["code"], "stale_data")
        self.assertEqual(run(fixture(end="2026-09-22"))["code"], "stale_data")
        with patch("backtest.DataProvider.get_backtest_history", side_effect=RuntimeError("sensitive upstream")):
            result = Backtester.run("2330.TW", 30, now=TODAY)
        self.assertEqual(result["code"], "source_unavailable")
        self.assertNotIn("sensitive", result["message"])

    def test_supported_windows_and_oversized_cost_or_bars(self):
        for days in SUPPORTED_BACKTEST_DAYS:
            result = run(fixture(days + 30), days=days)
            self.assertEqual(result["status"], "success")
            self.assertEqual(result["days"], days)
        self.assertEqual(run(fixture(), days=3650)["code"], "unsupported_window")
        self.assertEqual(run(fixture(), min_commission=1e308)["code"], "invalid_cost")
        frame = fixture()
        frame.iloc[30, frame.columns.get_loc("Open")] = 1e308
        self.assertEqual(run(frame)["code"], "invalid_data")
        frame.iloc[30, frame.columns.get_loc("Open")] = 0.001
        self.assertEqual(run(frame)["code"], "invalid_data")

    def test_endpoint_returns_400_before_loading_unsupported_window(self):
        tree = ast.parse(Path("main.py").read_text(encoding="utf-8"))
        endpoint = next(node for node in tree.body if isinstance(node, ast.AsyncFunctionDef)
                        and node.name == "backtest")
        endpoint.decorator_list = []
        namespace = {"BacktestRequest": object, "SUPPORTED_BACKTEST_DAYS": SUPPORTED_BACKTEST_DAYS,
                     "JSONResponse": JSONResponse, "asyncio": asyncio, "Backtester": Backtester}
        exec(compile(ast.Module(body=[endpoint], type_ignores=[]), "main.py", "exec"), namespace)
        response = asyncio.run(namespace["backtest"](SimpleNamespace(days=3650)))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(json.loads(response.body)["code"], "unsupported_window")

    def test_legacy_cache_is_not_used_by_endpoint(self):
        source = Path("main.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        endpoint = next(node for node in tree.body if isinstance(node, ast.AsyncFunctionDef)
                        and node.name == "backtest")
        called = {ast.unparse(node.func) for node in ast.walk(endpoint) if isinstance(node, ast.Call)}
        self.assertNotIn("db.get_backtest_results", called)
        self.assertIn("Backtester.run", ast.unparse(endpoint))
        self.assertIn("asyncio.to_thread", called)
        self.assertNotIn("run_backtest_hydration_task", source)

    def test_ui_copy_units_and_escaping(self):
        html = Path("static/index.html").read_text(encoding="utf-8")
        self.assertIn("backtest-commission", html)
        self.assertIn("backtest-min-commission", html)
        self.assertIn("backtest-sell-tax", html)
        self.assertIn("outperformance, ' %pt'", html)
        self.assertIn("escapeRoutingText(res.message", html)
        self.assertIn("escapeRoutingText(t.action)", html)
        self.assertIn("此窗口沒有成交；勝率不適用", html)
        self.assertNotIn("明天：台積電", html)
        self.assertNotIn("後天：", html)
        self.assertNotIn("下週：", html)

import unittest
import time
import threading
from contextlib import ExitStack
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from market_insights import (
    MarketInsightsService,
    _display_date,
    analyze_stock_news_attention,
    aggregate_holder_rows,
    aggregate_industry_performance,
    calculate_price_change,
    normalize_taiwan_ticker,
    rank_trending_stocks,
)
from news_crawler import NewsCrawler


class HolderAggregationTests(unittest.TestCase):
    def test_formats_tdcc_and_twse_dates(self):
        self.assertEqual(_display_date("20260911"), "2026-09-11")
        self.assertEqual(_display_date("1150918"), "2026-09-18")

    def test_aggregates_large_and_small_holder_buckets(self):
        rows = [
            {"\ufeff資料日期": "20260911", "證券代號": "2330", "持股分級": "1", "人數": "10", "股數": "500", "占集保庫存數比例%": "0.10"},
            {"資料日期": "20260911", "證券代號": "2330", "持股分級": "2", "人數": "5", "股數": "10,000", "占集保庫存數比例%": "0.20"},
            {"資料日期": "20260911", "證券代號": "2330", "持股分級": "3", "人數": "3", "股數": "20,000", "占集保庫存數比例%": "0.30"},
            {"資料日期": "20260911", "證券代號": "2330", "持股分級": "12", "人數": "2", "股數": "900,000", "占集保庫存數比例%": "10.00"},
            {"資料日期": "20260911", "證券代號": "2330", "持股分級": "15", "人數": "1", "股數": "5,000,000", "占集保庫存數比例%": "60.00"},
            {"資料日期": "20260911", "證券代號": "2330", "持股分級": "17", "人數": "21", "股數": "6,000,000", "占集保庫存數比例%": "100.00"},
        ]
        item = aggregate_holder_rows(rows)["2330"]
        self.assertEqual(item["data_date"], "2026-09-11")
        self.assertEqual(item["large_holder_accounts"], 3)
        self.assertEqual(item["large_holder_ratio"], 70.0)
        self.assertEqual(item["small_holder_ratio"], 0.6)
        self.assertEqual(item["total_shares"], 6_000_000)


class IndustryAggregationTests(unittest.TestCase):
    def test_ranks_industries_by_equal_weight_return(self):
        companies = [
            {"公司代號": "1001", "公司簡稱": "甲", "產業別": "24"},
            {"公司代號": "1002", "公司簡稱": "乙", "產業別": "24"},
            {"公司代號": "1003", "公司簡稱": "丙", "產業別": "24"},
            {"公司代號": "2001", "公司簡稱": "丁", "產業別": "15"},
            {"公司代號": "2002", "公司簡稱": "戊", "產業別": "15"},
            {"公司代號": "2003", "公司簡稱": "己", "產業別": "15"},
        ]
        daily = [
            {"Code": "1001", "ClosingPrice": "110", "Change": "10"},
            {"Code": "1002", "ClosingPrice": "105", "Change": "5"},
            {"Code": "1003", "ClosingPrice": "100", "Change": "0"},
            {"Code": "2001", "ClosingPrice": "99", "Change": "-1"},
            {"Code": "2002", "ClosingPrice": "98", "Change": "-2"},
            {"Code": "2003", "ClosingPrice": "100", "Change": "0"},
            {"Code": "0050", "ClosingPrice": "200", "Change": "20"},
        ]
        result = aggregate_industry_performance(daily, companies)
        self.assertEqual(result[0]["industry"], "半導體業")
        self.assertEqual(result[0]["company_count"], 3)
        self.assertEqual(result[0]["advancers"], 2)
        self.assertEqual(result[0]["leaders"][0]["ticker"], "1001")

    def test_service_combines_listed_and_otc_rows(self):
        listed_companies = [
            {"公司代號": f"10{i}", "公司簡稱": f"上市{i}", "產業別": "24"}
            for i in range(3)
        ]
        otc_companies = [
            {"SecuritiesCompanyCode": f"20{i}", "CompanyAbbreviation": f"上櫃{i}", "SecuritiesIndustryCode": "24"}
            for i in range(3)
        ]
        listed_daily = [
            {"Date": "1150918", "Code": f"10{i}", "ClosingPrice": "101", "Change": "1"}
            for i in range(3)
        ]
        otc_daily = [
            {"Date": "1150918", "SecuritiesCompanyCode": f"20{i}", "CompanyName": f"上櫃{i}", "Close": "102", "Change": "+2"}
            for i in range(3)
        ]
        datasets = {
            "twse_daily": listed_daily,
            "listed_companies": listed_companies,
            "tpex_daily": otc_daily,
            "tpex_companies": otc_companies,
        }
        service = MarketInsightsService()
        with patch.object(service, "_cached", side_effect=lambda key, ttl, loader: datasets[key]):
            result = service.industry_performance()
        self.assertEqual(result["market"], "上市櫃普通股")
        self.assertEqual(result["as_of"], "2026-09-18")
        self.assertEqual(result["items"][0]["company_count"], 6)


class TrendingAggregationTests(unittest.TestCase):
    def test_counts_each_stock_once_per_article_and_boosts_multiple_sources(self):
        companies = [
            {"公司代號": "2330", "公司簡稱": "台積電"},
            {"公司代號": "2317", "公司簡稱": "鴻海"},
        ]
        now = 2_000_000.0
        news = [
            {"title": "台積電 2330 法說", "summary": "台積電展望", "source": "甲", "published_ts": now - 3600, "link": "https://example.com/a"},
            {"title": "台積電與鴻海合作", "summary": "", "source": "乙", "published_ts": now - 7200, "link": "https://example.com/b"},
            {"title": "鴻海新產品", "summary": "", "source": "乙", "published_ts": now - 10000, "link": "https://example.com/c"},
        ]
        result = rank_trending_stocks(news, companies, now_ts=now)
        self.assertEqual(result[0]["ticker"], "2330")
        self.assertEqual(result[0]["mention_count"], 2)
        self.assertEqual(result[0]["source_count"], 2)
        self.assertEqual(result[1]["mention_count"], 2)

    def test_ambiguous_company_name_requires_ticker(self):
        companies = [{"公司代號": "5007", "公司簡稱": "三星"}]
        news = [
            {"title": "韓國三星發表新手機", "source": "甲"},
            {"title": "5007 三星公布財報", "source": "乙"},
        ]
        result = rank_trending_stocks(news, companies, now_ts=2_000_000)
        self.assertEqual(result[0]["ticker"], "5007")
        self.assertEqual(result[0]["mention_count"], 1)


class StockSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.now = time.time()
        self.listed_companies = [
            {"公司代號": "2330", "公司簡稱": "台積電", "產業別": "24"},
            {"公司代號": "2303", "公司簡稱": "聯電", "產業別": "24"},
            {"公司代號": "2454", "公司簡稱": "聯發科", "產業別": "24"},
        ]
        self.tpex_companies = [
            {"公司代號": "6488", "公司簡稱": "環球晶", "產業別": "24"},
        ]
        self.twse_daily = [
            {"Date": "1150918", "Code": "2330", "Name": "台積電", "ClosingPrice": "110", "Change": "10"},
            {"Date": "1150918", "Code": "2303", "Name": "聯電", "ClosingPrice": "105", "Change": "5"},
            {"Date": "1150918", "Code": "2454", "Name": "聯發科", "ClosingPrice": "100", "Change": "0"},
        ]
        self.tpex_daily = [
            {"Date": "1150918", "Code": "6488", "Name": "環球晶", "ClosingPrice": "98", "Change": "-2"},
        ]
        self.holders = {
            "2330": {
                "ticker": "2330",
                "data_date": "2026-09-11",
                "large_holder_threshold": "400 張以上（400,001 股以上）",
                "large_holder_ratio": 70.0,
                "large_holder_accounts": 3,
                "small_holder_ratio": 0.6,
                "total_accounts": 21,
                "total_shares": 6_000_000,
                "breakdown": [],
                "source": "TDCC",
            }
        }
        self.news = {
            "items": [
                {
                    "title": "台積電 2330 法說",
                    "summary": "台積電展望",
                    "source": "來源甲",
                    "published_ts": self.now - 3600,
                    "published": "2026-09-20 10:00",
                    "link": "https://example.com/a",
                },
                {
                    "title": "台積電擴充先進製程",
                    "summary": "",
                    "source": "來源乙",
                    "published_ts": self.now - 7200,
                    "published": "2026-09-20 09:00",
                    "link": "https://example.com/b",
                },
            ],
            "successful_sources": ["來源甲", "來源乙"],
            "unavailable_sources": [],
        }

    def _snapshot(self, ticker="2330", **overrides):
        service = MarketInsightsService()
        datasets = {
            "_listed_companies": self.listed_companies,
            "_tpex_companies": self.tpex_companies,
            "_twse_daily": self.twse_daily,
            "_tpex_daily": self.tpex_daily,
            "_holder_distribution": self.holders,
            "_recent_news": self.news,
            **overrides,
        }
        with ExitStack() as stack:
            mocks = {}
            for method, value in datasets.items():
                if isinstance(value, Exception):
                    mocks[method] = stack.enter_context(
                        patch.object(service, method, side_effect=value)
                    )
                else:
                    mocks[method] = stack.enter_context(
                        patch.object(service, method, return_value=value)
                    )
            result = service.stock_snapshot(ticker)
        return result, mocks

    def test_ticker_normalization_and_validation(self):
        self.assertEqual(normalize_taiwan_ticker("2330.tw"), ("2330", "TW"))
        self.assertEqual(normalize_taiwan_ticker("6488.TWO"), ("6488", "TWO"))
        self.assertEqual(normalize_taiwan_ticker(" 2330 "), ("2330", ""))
        for invalid in ("", "2330.US", "23", "2330.TW.extra", "../2330"):
            with self.assertRaises(ValueError):
                normalize_taiwan_ticker(invalid)

    def test_price_formula_and_invalid_previous_close(self):
        self.assertEqual(
            calculate_price_change("110", "10"),
            {
                "close": 110.0,
                "change": 10.0,
                "previous_close": 100.0,
                "change_percent": 10.0,
            },
        )
        self.assertIsNone(calculate_price_change("10", "10"))
        self.assertIsNone(calculate_price_change("--", "1"))

    def test_complete_snapshot_has_explainable_sections(self):
        result, mocks = self._snapshot("2330.TW")
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["ticker"], "2330")
        for section in (
            "identity", "price", "industry_context", "ownership", "news_attention"
        ):
            payload = result["data"][section]
            self.assertTrue(payload["available"])
            self.assertIn("as_of", payload)
            self.assertTrue(payload["source"])
            self.assertTrue(payload["methodology"])
        self.assertEqual(result["data"]["price"]["change_percent"], 10.0)
        context = result["data"]["industry_context"]
        self.assertEqual(context["rank"], 1)
        self.assertEqual(context["total_industries"], 1)
        self.assertEqual(context["advancers"], 2)
        self.assertEqual(context["company_count"], 4)
        self.assertAlmostEqual(
            context["stock_minus_industry"],
            10.0 - context["mean_change"],
            places=2,
        )
        self.assertEqual(result["data"]["news_attention"]["mention_count"], 2)
        self.assertEqual(result["data"]["news_attention"]["source_count"], 2)
        for loader in mocks.values():
            loader.assert_called_once()

    def test_etf_without_industry_is_partial(self):
        etf_daily = self.twse_daily + [
            {"Date": "1150918", "Code": "0050", "Name": "元大台灣50", "ClosingPrice": "200", "Change": "2"}
        ]
        holders = {"0050": {**self.holders["2330"], "ticker": "0050"}}
        result, _ = self._snapshot(
            "0050.TW",
            _twse_daily=etf_daily,
            _holder_distribution=holders,
        )
        self.assertEqual(result["status"], "partial")
        self.assertTrue(result["data"]["identity"]["available"])
        self.assertTrue(result["data"]["price"]["available"])
        self.assertEqual(
            result["data"]["industry_context"]["code"],
            "industry_not_applicable",
        )

    def test_zero_news_mentions_is_available(self):
        news = {
            **self.news,
            "items": [{
                "title": "大盤成交量回升",
                "summary": "",
                "source": "來源甲",
                "published_ts": self.now - 60,
                "link": "https://example.com/market",
            }],
        }
        result, _ = self._snapshot(_recent_news=news)
        attention = result["data"]["news_attention"]
        self.assertTrue(attention["available"])
        self.assertEqual(attention["mention_count"], 0)
        self.assertEqual(attention["articles"], [])

    def test_single_news_source_failure_returns_partial(self):
        news = {
            **self.news,
            "successful_sources": ["來源甲"],
            "unavailable_sources": ["來源乙"],
        }
        result, _ = self._snapshot(_recent_news=news)
        self.assertEqual(result["status"], "partial")
        self.assertTrue(result["data"]["news_attention"]["available"])
        self.assertIn(
            {"section": "news_attention", "code": "news_sources_partial"},
            result["warnings"],
        )

    def test_tw_suffix_uses_only_twse_loader_health(self):
        daily_failure, _ = self._snapshot(
            "2330.TW",
            _twse_daily=RuntimeError("TWSE daily unavailable"),
        )
        self.assertEqual(daily_failure["status"], "partial")
        self.assertEqual(
            daily_failure["data"]["price"]["code"],
            "price_upstream_unavailable",
        )
        self.assertEqual(
            daily_failure["data"]["industry_context"]["code"],
            "industry_upstream_unavailable",
        )

        company_failure, _ = self._snapshot(
            "2330.TW",
            _listed_companies=RuntimeError("TWSE company unavailable"),
        )
        self.assertTrue(company_failure["data"]["price"]["available"])
        self.assertEqual(
            company_failure["data"]["industry_context"]["code"],
            "industry_upstream_unavailable",
        )

    def test_two_suffix_uses_only_tpex_loader_health(self):
        daily_failure, _ = self._snapshot(
            "6488.TWO",
            _tpex_daily=RuntimeError("TPEx daily unavailable"),
        )
        self.assertEqual(daily_failure["status"], "partial")
        self.assertEqual(
            daily_failure["data"]["price"]["code"],
            "price_upstream_unavailable",
        )
        self.assertEqual(
            daily_failure["data"]["industry_context"]["code"],
            "industry_upstream_unavailable",
        )

        company_failure, _ = self._snapshot(
            "6488.TWO",
            _tpex_companies=RuntimeError("TPEx company unavailable"),
        )
        self.assertTrue(company_failure["data"]["price"]["available"])
        self.assertEqual(
            company_failure["data"]["industry_context"]["code"],
            "industry_upstream_unavailable",
        )

    def test_suffixless_ticker_uses_matched_market_health(self):
        result, _ = self._snapshot(
            "2330",
            _twse_daily=RuntimeError("TWSE daily unavailable"),
        )
        self.assertTrue(result["data"]["identity"]["available"])
        self.assertEqual(result["data"]["identity"]["market"], "上市")
        self.assertEqual(
            result["data"]["price"]["code"],
            "price_upstream_unavailable",
        )

    def test_all_upstreams_fail_without_leaking_errors(self):
        failure = RuntimeError("secret upstream detail")
        result, _ = self._snapshot(
            _listed_companies=failure,
            _tpex_companies=failure,
            _twse_daily=failure,
            _tpex_daily=failure,
            _holder_distribution=failure,
            _recent_news=failure,
        )
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(len(result["unavailable"]), 5)
        self.assertNotIn("secret upstream detail", str(result))

    def test_cached_loader_runs_once(self):
        service = MarketInsightsService()
        calls = []

        def loader():
            calls.append(True)
            return {"value": 1}

        first = service._cached("example", 60, loader)
        second = service._cached("example", 60, loader)
        self.assertIs(first, second)
        self.assertEqual(calls, [True])

    def test_cached_loader_is_single_flight_across_threads(self):
        service = MarketInsightsService()
        started = threading.Event()
        release = threading.Event()
        calls = []
        value = {"value": 1}

        def loader():
            calls.append(True)
            started.set()
            release.wait(1)
            return value

        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(service._cached, "shared", 60, loader)
            self.assertTrue(started.wait(1))
            second = executor.submit(service._cached, "shared", 60, loader)
            time.sleep(0.02)
            release.set()
            self.assertIs(first.result(timeout=1), value)
            self.assertIs(second.result(timeout=1), value)
        self.assertEqual(calls, [True])

    def test_failed_cache_loader_is_not_cached_or_left_locked(self):
        service = MarketInsightsService()
        calls = []

        def loader():
            calls.append(True)
            if len(calls) == 1:
                raise RuntimeError("temporary loader failure")
            return "recovered"

        with self.assertRaises(RuntimeError):
            service._cached("retry", 60, loader)
        self.assertEqual(service._cached("retry", 60, loader), "recovered")
        self.assertEqual(service._cached("retry", 60, loader), "recovered")
        self.assertEqual(calls, [True, True])

    def test_slow_optional_loader_returns_partial_within_deadline(self):
        service = MarketInsightsService()
        release = threading.Event()
        finished = threading.Event()

        def slow_holder_loader():
            try:
                release.wait(1)
                raise RuntimeError("late private upstream detail")
            finally:
                finished.set()

        with ExitStack() as stack:
            stack.enter_context(patch.object(service, "_listed_companies", return_value=self.listed_companies))
            stack.enter_context(patch.object(service, "_tpex_companies", return_value=self.tpex_companies))
            stack.enter_context(patch.object(service, "_twse_daily", return_value=self.twse_daily))
            stack.enter_context(patch.object(service, "_tpex_daily", return_value=self.tpex_daily))
            stack.enter_context(patch.object(service, "_holder_distribution", side_effect=slow_holder_loader))
            stack.enter_context(patch.object(service, "_recent_news", return_value=self.news))
            started_at = time.monotonic()
            result = service.stock_snapshot("2330.TW", deadline_seconds=0.04)
            elapsed = time.monotonic() - started_at
            self.assertLess(elapsed, 0.25)
            self.assertEqual(result["status"], "partial")
            self.assertEqual(
                result["data"]["ownership"]["code"],
                "ownership_upstream_timeout",
            )
            self.assertNotIn("late private upstream detail", str(result))
            release.set()
            self.assertTrue(finished.wait(1))

    def test_all_slow_loaders_return_unavailable_and_settle(self):
        service = MarketInsightsService()
        release = threading.Event()
        finished = threading.Event()
        state_lock = threading.Lock()
        active = 0

        def slow_loader():
            nonlocal active
            with state_lock:
                active += 1
            try:
                release.wait(1)
                raise RuntimeError("late upstream detail")
            finally:
                with state_lock:
                    active -= 1
                    if active == 0:
                        finished.set()

        with ExitStack() as stack:
            for method in (
                "_listed_companies",
                "_tpex_companies",
                "_twse_daily",
                "_tpex_daily",
                "_holder_distribution",
                "_recent_news",
            ):
                stack.enter_context(patch.object(service, method, side_effect=slow_loader))
            started_at = time.monotonic()
            result = service.stock_snapshot("2330.TW", deadline_seconds=0.04)
            elapsed = time.monotonic() - started_at
            self.assertLess(elapsed, 0.25)
            self.assertEqual(result["status"], "unavailable")
            self.assertTrue(
                all(item["code"].endswith("_timeout") for item in result["unavailable"])
            )
            self.assertNotIn("late upstream detail", str(result))
            release.set()
            self.assertTrue(finished.wait(1))

    def test_news_window_and_ambiguous_names(self):
        news = [
            {"title": "台積電 2330 同篇重複台積電", "source": "甲", "published_ts": self.now - 60},
            {"title": "2330 過期新聞", "source": "乙", "published_ts": self.now - 73 * 3600},
            {"title": "韓國三星新品", "source": "甲", "published_ts": self.now - 60},
        ]
        result = analyze_stock_news_attention(news, "2330", "台積電", now_ts=self.now)
        self.assertEqual(result["mention_count"], 1)
        ambiguous = analyze_stock_news_attention(news, "5007", "三星", now_ts=self.now)
        self.assertEqual(ambiguous["mention_count"], 0)


class NewsCrawlerTimeoutTests(unittest.TestCase):
    class FeedEntry(dict):
        def __getattr__(self, name):
            try:
                return self[name]
            except KeyError as exc:
                raise AttributeError(name) from exc

    @patch("news_crawler.feedparser.parse")
    @patch("news_crawler.requests.get")
    def test_rss_is_fetched_with_timeout_before_bytes_are_parsed(self, get, parse):
        get.return_value.content = b"<rss></rss>"
        get.return_value.raise_for_status.return_value = None
        parse.return_value.entries = []
        parse.return_value.bozo = False

        self.assertEqual(NewsCrawler.fetch_rss("yahoo_finance", timeout=4), [])

        self.assertEqual(get.call_args.kwargs["timeout"], (3, 4))
        parse.assert_called_once_with(b"<rss></rss>")

    @patch("news_crawler.feedparser.parse")
    @patch("news_crawler.requests.get")
    def test_rss_utc_timestamp_preserves_72_hour_news_boundary(self, get, parse):
        now = 2_000_000_000
        get.return_value.content = b"<rss>mock boundary feed</rss>"
        get.return_value.raise_for_status.return_value = None
        parse.return_value.entries = [
            self.FeedEntry(
                title="2330 台積電 70 小時前消息",
                summary="",
                link="https://example.com/within-window",
                published_parsed=time.gmtime(now - 70 * 3600),
            ),
            self.FeedEntry(
                title="2330 台積電 73 小時前消息",
                summary="",
                link="https://example.com/outside-window",
                published_parsed=time.gmtime(now - 73 * 3600),
            ),
        ]
        parse.return_value.bozo = False

        rss_items = NewsCrawler.fetch_rss("yahoo_finance", limit=5, timeout=4)
        result = analyze_stock_news_attention(
            rss_items,
            "2330",
            "台積電",
            now_ts=now,
        )

        self.assertEqual(
            [item["published_ts"] for item in rss_items],
            [now - 70 * 3600, now - 73 * 3600],
        )
        self.assertEqual(result["mention_count"], 1)
        self.assertEqual(result["articles"][0]["title"], "2330 台積電 70 小時前消息")
        self.assertNotIn("73 小時", str(result))
        parse.assert_called_once_with(b"<rss>mock boundary feed</rss>")


if __name__ == "__main__":
    unittest.main()

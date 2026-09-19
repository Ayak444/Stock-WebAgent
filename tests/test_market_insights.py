import unittest
from unittest.mock import patch

from market_insights import (
    MarketInsightsService,
    _display_date,
    aggregate_holder_rows,
    aggregate_industry_performance,
    rank_trending_stocks,
)


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


if __name__ == "__main__":
    unittest.main()

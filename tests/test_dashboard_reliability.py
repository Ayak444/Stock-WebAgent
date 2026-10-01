"""Bounded dashboard regressions with fake providers and test-only credentials."""
import asyncio
import shutil
import subprocess
import time
import unittest
from concurrent.futures import Future
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from database import AccountAlertStoreError, Database, account_store_failure_category
from market_insights import MarketInsightsService, rank_trending_stocks, recent_unique_news, same_date_market_rows, upcoming_calendar
from supabase import ClientOptions, create_client


class DashboardReliabilityTests(unittest.TestCase):
    def test_calendar_uses_taipei_day_and_excludes_trading_markers(self):
        events = upcoming_calendar([
            {'Date': '1150930', 'Code': '2330', 'Name': 'old'},
            {'Date': '1151001', 'Code': '2330', 'Name': 'current'},
            {'Date': 'bad', 'Code': '2330'},
        ], [
            {'Date': '20261001', 'Name': '農曆春節後開始交易日'},
            {'Date': '20261002', 'Name': '市場無交易，僅辦理結算交割作業'},
        ], now=datetime(2026, 9, 30, 16, tzinfo=timezone.utc))
        self.assertEqual([e['date'] for e in events], ['2026-10-01', '2026-10-02'])
        self.assertTrue(all(e['source_url'].startswith('https://openapi.twse.com.tw/') for e in events))

    def test_market_dates_are_not_mixed(self):
        rows, coverage = same_date_market_rows([
            ('上市', [{'Date': '1150929', 'Code': '2330'}]),
            ('上櫃', [{'Date': '1150930', 'Code': '6488'}]),
        ])
        self.assertEqual([r['Code'] for r in rows], ['6488'])
        self.assertEqual(coverage['as_of'], '2026-09-30')
        self.assertEqual(coverage['excluded_markets'], ['上市'])

    def test_news_excludes_stale_future_undated_and_duplicates(self):
        now = 2_000_000
        items = [{'title': title, 'published_ts': ts, 'link': link} for title, ts, link in [
            ('current', now - 10, 'https://example.test/a'),
            ('current', now - 20, 'https://example.test/b'),
            ('same link', now - 30, 'https://example.test/a'),
            ('stale', now - 72 * 3600 - 1, ''),
            ('future', now + 1, ''), ('undated', 0, ''),
        ]]
        self.assertEqual([i['title'] for i in recent_unique_news(items, now)], ['current'])

    def test_price_outage_does_not_remove_company_names_from_news(self):
        service = MarketInsightsService()
        resources = {key: (False, None, False) for key in ('twse_daily', 'tpex_daily', 'tpex_companies')}
        resources['listed_companies'] = (True, [{'公司代號': '2330', '公司簡稱': '台積電'}], False)
        resources['news'] = (True, {'items': [{'title': '台積電 2330', 'published_ts': time.time() - 10}],
                                   'successful_sources': ['fake'], 'unavailable_sources': []}, False)
        with patch.object(service, '_snapshot_resources', return_value=resources):
            result = service.overview()
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(result['data']['trending']['items'][0]['ticker'], '2330')

    def test_large_profile_set_bounds_news_regex_work(self):
        import re
        companies = [{'公司代號': str(10000 + i), '公司簡稱': f'company{i}'} for i in range(2100)]
        now = time.time()
        news = [{'title': f'10000 update {i}', 'published_ts': now - i} for i in range(100)]
        with patch('market_insights.re.compile', wraps=re.compile) as compile_pattern:
            result = rank_trending_stocks(news, companies, now_ts=now)
        self.assertEqual(result[0]['ticker'], '10000')
        self.assertEqual(result[0]['mention_count'], 100)
        self.assertLessEqual(compile_pattern.call_count, len(companies))

    def test_slow_feed_does_not_discard_healthy_feed(self):
        good, slow = Future(), Future()
        good.set_result([{'title': 'current', 'published_ts': time.time() - 10}])
        service = MarketInsightsService()
        with patch('market_insights.RSS_SOURCES', {'good': {'name': 'good'}, 'slow': {'name': 'slow'}}), \
             patch('market_insights.NEWS_EXECUTOR.submit', side_effect=[good, slow]), \
             patch('market_insights.wait'):
            result = service._recent_news()
        self.assertEqual(len(result['items']), 1)
        self.assertEqual(result['unavailable_sources'], ['slow'])

    def test_read_retries_once_but_write_and_permission_failure_do_not(self):
        db = Database.__new__(Database)
        query = Mock()
        query.table.return_value = query
        query.select.return_value = query
        query.eq.return_value = query
        query.limit.return_value = query
        query.upsert.return_value = query
        db.supabase = query
        # Use a supported transport timeout type, not a generic application error.
        import requests
        query.execute.side_effect = [requests.exceptions.Timeout('test-only'), SimpleNamespace(data=[])]
        with patch('database.time.sleep'):
            self.assertEqual(db.get_account_volume_settings('fake-user')['tickers'], [])
        self.assertEqual(query.execute.call_count, 2)
        query.execute.reset_mock(side_effect=True)
        query.execute.side_effect = requests.exceptions.Timeout('test-only')
        with self.assertLogs('database', 'ERROR'), self.assertRaises(AccountAlertStoreError):
            db.save_account_volume_settings('fake-user', {'tickers': []})
        self.assertEqual(query.execute.call_count, 1)
        error = RuntimeError('test-only')
        error.code = '42501'
        error.response = SimpleNamespace(status_code=401)
        self.assertEqual(account_store_failure_category(error), 'permission_auth')

    def test_sync_supabase_options_construct_without_network(self):
        client = create_client('https://unit-test.invalid', 'sb_secret_test_only_placeholder',
                               options=ClientOptions(postgrest_client_timeout=8))
        self.assertEqual(client.options.postgrest_client_timeout, 8)
        self.assertIsNotNone(client.auth)

    def test_analysis_response_survives_history_save_failure(self):
        import main
        req = SimpleNamespace(targets=[], mode='quick')
        async def scenario():
            with patch.object(main, '_analyze_targets_async', AsyncMock(return_value=([], 'fake-fx'))), \
                 patch.object(main.db, 'save_analysis', side_effect=RuntimeError('test-only')), \
                 patch.object(main.websocket_system, 'price_broadcaster', None):
                result = await main.analyze(req)
                self.assertEqual(result['status'], 'success')
                await asyncio.gather(*list(main._analysis_save_tasks))
        with self.assertLogs('main', 'WARNING'):
            asyncio.run(scenario())

    def test_analysis_timeout_returns_retryable_504(self):
        import main
        from fastapi import HTTPException
        async def timeout(awaitable, timeout):
            self.assertEqual(timeout, 55)
            awaitable.close()
            raise asyncio.TimeoutError()
        with patch.object(main, '_analyze_targets_async', AsyncMock()), \
             patch.object(main.asyncio, 'wait_for', side_effect=timeout):
            with self.assertRaises(HTTPException) as caught:
                asyncio.run(main.analyze(SimpleNamespace(targets=[], mode='quick')))
        self.assertEqual(caught.exception.status_code, 504)

    @unittest.skipUnless(shutil.which('node'), 'Node optional; standalone browser check available')
    def test_actual_browser_helpers_without_network(self):
        result = subprocess.run(['node', 'tests/dashboard_browser_checks.js'], capture_output=True,
                                text=True, encoding='utf-8', timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()

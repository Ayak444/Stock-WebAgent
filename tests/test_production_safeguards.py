"""Offline privacy, financial storage and dated-source regressions."""
import asyncio
import base64
import os
import time
import unittest
from concurrent.futures import Future
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pandas as pd
from fastapi.testclient import TestClient

from account_alert_security import SESSION_COOKIE, issue_session
from database import AccountAlertStoreError, Database
from market_provenance import (InstitutionalProvider, macro_quote,
                               normalize_twse_institutional, normalize_tpex_institutional)

OWNER = '11111111-1111-1111-1111-111111111111'
OTHER = '22222222-2222-2222-2222-222222222222'
PRIVATE = 'test-only-private-marker'


class PrivateEndpointTests(unittest.TestCase):
    def setUp(self):
        import main
        self.main = main
        self.env = patch.dict(os.environ, {'AUTH_SESSION_SECRET': 'test-only-session-secret-' * 3})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.store = Mock()
        self.store.get_public_user.side_effect = lambda uid: {'id': uid, 'name': 'test'}
        self.store.get_portfolio.return_value = [{'code': '2330.TW'}]
        self.store.get_trade_history.return_value = []
        self.store.get_stress_test_history.return_value = []
        self.store.record_trade.return_value = {'ok': True}
        self.db_patch = patch.object(main, 'db', self.store)
        self.db_patch.start()
        self.addCleanup(self.db_patch.stop)
        self.client = TestClient(main.app)
        self.addCleanup(self.client.close)

    def login(self):
        self.client.cookies.set(SESSION_COOKIE, issue_session(OWNER))

    def test_missing_invalid_and_expired_sessions_are_denied(self):
        requests = [('GET', '/portfolio', None), ('GET', '/trades', None),
                    ('GET', '/stress_test/history', None),
                    ('POST', '/screener/analyze', {'source': 'portfolio', 'user_id': OTHER}),
                    ('POST', '/portfolio', {'portfolio': []}),
                    ('POST', '/stress_test/save', {'result': {}}),
                    ('POST', '/trade', {'action': '買入', 'ticker': '2330', 'amount': 1, 'price': 1})]
        with patch('itsdangerous.timed.TimestampSigner.get_timestamp', return_value=int(time.time()) - 8 * 86400):
            expired = issue_session(OWNER)
        for cookie in (None, 'test-only-invalid', expired):
            self.client.cookies.clear()
            if cookie:
                self.client.cookies.set(SESSION_COOKIE, cookie)
            for method, url, body in requests:
                with self.subTest(cookie=cookie is not None, url=url):
                    result = self.client.request(method, url, json=body, headers={'origin': 'http://testserver'})
                    self.assertEqual(result.status_code, 401)
        self.store.get_portfolio.assert_not_called()
        self.store.record_trade.assert_not_called()

    def test_forged_user_identity_never_controls_private_operations(self):
        self.login()
        for url, method in (('/portfolio', 'get_portfolio'), ('/trades', 'get_trade_history'),
                            ('/stress_test/history', 'get_stress_test_history')):
            self.assertEqual(self.client.get(url, params={'user_id': OTHER}).status_code, 200)
            getattr(self.store, method).assert_called_with(OWNER)
        headers = {'origin': 'http://testserver'}
        self.assertEqual(self.client.post('/portfolio', json={'user_id': OTHER, 'portfolio': []}, headers=headers).status_code, 200)
        self.store.save_portfolio.assert_called_with(OWNER, [])
        self.assertEqual(self.client.post('/trade', json={'user_id': OTHER, 'action': '買入', 'ticker': '2330', 'amount': '0.1', 'price': '0.2'}, headers=headers).status_code, 200)
        self.store.record_trade.assert_called_with(OWNER, '買入', '2330.TW', Decimal('0.1'), Decimal('0.2'))
        self.assertEqual(self.client.post('/stress_test/save', json={'user_id': OTHER, 'result': {'x': 1}}, headers=headers).status_code, 200)
        self.store.save_stress_test_record.assert_called_with(OWNER, '常規測試', {'x': 1})
        with patch.object(self.main, 'analyze_related_stocks', return_value=[]):
            self.assertEqual(self.client.post('/screener/analyze', json={'source': 'portfolio', 'user_id': OTHER}, headers=headers).status_code, 200)
            self.store.get_portfolio.assert_called_with(OWNER)

    def test_cross_origin_writes_validation_and_storage_failures(self):
        self.login()
        for origin in ('https://foreign.invalid', None):
            for url, body in [('/portfolio', {'portfolio': []}),
                              ('/stress_test/save', {'result': {}}),
                              ('/trade', {'action': '買入', 'ticker': '2330', 'amount': 1, 'price': 1}),
                              ('/screener/analyze', {'source': 'portfolio'})]:
                result = self.client.post(url, json=body, headers={'origin': origin} if origin else {})
                self.assertEqual(result.status_code, 403)
        headers = {'origin': 'http://testserver'}
        item = {'code': '2330', 'type': '台股', 'cost': 1, 'shares': 1}
        self.assertEqual(self.client.post('/portfolio', json={'portfolio': [item, item]}, headers=headers).status_code, 422)
        self.assertEqual(self.client.post('/stress_test/save', content='{"result":{"x":NaN}}', headers={**headers, 'content-type': 'application/json'}).status_code, 422)
        self.store.save_portfolio.assert_not_called()
        self.store.save_stress_test_record.assert_not_called()
        for method, url, body in [('GET', '/portfolio', None), ('POST', '/portfolio', {'portfolio': []}), ('POST', '/stress_test/save', {'result': {}}), ('POST', '/trade', {'action': '買入', 'ticker': '2330', 'amount': 1, 'price': 1})]:
            for name in ('get_portfolio', 'save_portfolio', 'save_stress_test_record', 'record_trade'):
                getattr(self.store, name).side_effect = RuntimeError(PRIVATE)
            response = self.client.request(method, url, json=body, headers=headers)
            self.assertEqual(response.status_code, 503)
            self.assertNotIn(PRIVATE, response.text)

    def test_alert_categories_are_actionable_and_contain_no_configuration_values(self):
        self.login()
        categories = ['missing_schema', 'permission_auth', 'key_rejected', 'connectivity',
                      'encryption_not_configured', 'encryption_unavailable', 'not_configured']
        for category in categories:
            self.store.get_account_volume_settings.side_effect = AccountAlertStoreError(category)
            result = self.client.get('/api/account/volume-alerts')
            self.assertEqual(result.status_code, 503)
            self.assertIn(category, result.text)
            for forbidden in (PRIVATE, 'SUPABASE_', 'ALERT_WEBHOOK_ENCRYPTION_KEY', 'AUTH_SESSION_SECRET', 'Render', '.sql'):
                self.assertNotIn(forbidden, result.text)

    def test_rpc_adapter_preserves_decimals_and_does_not_fallback_to_partial_writes(self):
        db = Database.__new__(Database)
        db.supabase = Mock()
        db.supabase.rpc.return_value.execute.return_value = SimpleNamespace(data={'ok': True})
        db.record_trade(OWNER, '買入', '2330.TW', Decimal('0.123456'), Decimal('12.345678'))
        self.assertEqual(db.supabase.rpc.call_args.args[1]['p_amount'], '0.123456')
        db.supabase.rpc.return_value.execute.side_effect = RuntimeError(PRIVATE)
        with self.assertRaises(RuntimeError):
            db.save_portfolio(OWNER, [])
        db.supabase.table.assert_not_called()

    def test_real_encryption_errors_are_static_and_never_expose_ciphertext(self):
        self.login()
        self.store.get_account_volume_settings.return_value = {'tickers': [], 'webhook_ciphertext': PRIVATE}
        for key, category in [('not-a-key-測試', 'encryption_not_configured'),
                              (base64.urlsafe_b64encode(b't' * 32).decode(), 'encryption_unavailable')]:
            with patch.dict(os.environ, {'ALERT_WEBHOOK_ENCRYPTION_KEY': key}):
                result = self.client.get('/api/account/volume-alerts')
            self.assertEqual(result.status_code, 503)
            self.assertIn(category, result.text)
            self.assertNotIn(PRIVATE, result.text)
            self.assertNotIn(key, result.text)

    def test_private_capability_probe_has_static_labels_and_no_payload(self):
        import database as database_module
        db = Database.__new__(Database)
        db.supabase = Mock()
        db.supabase.rpc.return_value.execute.return_value = SimpleNamespace(data=PRIVATE)
        with patch.object(database_module, 'SUPABASE_KEY', 'sb_secret_' + PRIVATE):
            result = db.check_private_account_store()
        self.assertEqual(result, {'ready': False, 'reason': 'permission_auth', 'credential_kind': 'backend_secret'})
        self.assertNotIn(PRIVATE, str(result))


class ProvenanceTests(unittest.IsolatedAsyncioTestCase):
    def test_macro_missing_invalid_stale_and_single_bar(self):
        now = time.time() - 60
        def payload(closes, times=None):
            return {'chart': {'result': [{'timestamp': times or [now] * len(closes), 'indicators': {'quote': [{'close': closes}]}}]}}
        for value in (None, 0, -1, 'bad', float('nan'), float('inf')):
            result = macro_quote(payload([value]))
            self.assertFalse(result['available'])
            self.assertIsNone(result['price'])
            self.assertIsNone(result['pct_change'])
        for stamp in (time.time() + 86400, time.time() - 11 * 86400):
            self.assertFalse(macro_quote(payload([10], [stamp]))['available'])
        result = macro_quote(payload([12]))
        self.assertTrue(result['available'])
        self.assertIsNone(result['change'])
        self.assertIsNotNone(datetime.fromisoformat(result['as_of']).tzinfo)
        self.assertEqual(macro_quote(payload([10, 12]))['pct_change'], 20)

    def test_official_chip_parsing_units_dates_and_warrant_exclusion(self):
        date = datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d')
        payload = {'stat': 'OK', 'date': date, 'fields': ['證券代號', '外陸資買賣超股數(不含外資自營商)', '投信買賣超股數'],
                   'data': [['2330', '1,500', '-2,000'], ['00935', '3,000', '0'], ['030001', '999999', '10'], ['6488', 'NaN', '10']]}
        rows = normalize_twse_institutional(payload)
        self.assertEqual(set(rows), {'2330.TW', '00935.TW'})
        self.assertEqual((rows['2330.TW']['Foreign'], rows['2330.TW']['Trust'], rows['2330.TW']['unit']), (1500, -2000, 'shares'))
        self.assertTrue(rows['2330.TW']['source'].startswith('https://www.twse.com.tw/'))
        self.assertEqual(normalize_twse_institutional({**payload, 'date': '20010101'}), {})
        self.assertEqual(normalize_tpex_institutional([{'Date': date, 'SecuritiesCompanyCode': '6488', 'ForeignInvestorsIncludeMainlandAreaInvestors-Difference': '2000', 'SecuritiesInvestmentTrustCompanies-Difference': '-500'}])['6488.TWO']['Foreign'], 2000)

    def test_twse_monday_and_holiday_fallback_is_bounded_and_newest(self):
        import market_provenance as mp
        monday = datetime(2026, 10, 5, 8, tzinfo=mp.TW_TZ)
        class Clock(datetime):
            @classmethod
            def now(cls, tz=None):
                return monday.astimezone(tz or timezone.utc)
        class ImmediatePool:
            def submit(self, method, offset):
                future = Future()
                future.set_result(method(offset))
                return future
        provider = InstitutionalProvider()
        self.addCleanup(provider._pool.shutdown, wait=True)
        for age in (3, 7):
            expected = (monday - timedelta(days=age)).strftime('%Y%m%d')
            def response(url):
                if f'date={expected}' not in url:
                    return {'stat': 'no data'}
                return {'stat': 'OK', 'date': expected, 'fields': ['證券代號', '外陸資買賣超股數(不含外資自營商)', '投信買賣超股數'], 'data': [['2330', '1000', '0']]}
            with patch.object(mp, 'datetime', Clock), patch.object(mp, 'TWSE_CHIP_EXECUTOR', ImmediatePool()), patch.object(provider, '_json', side_effect=response) as query, patch.object(mp, 'wait', wraps=mp.wait) as waiter:
                self.assertIn('2330.TW', provider._twse())
                self.assertEqual(query.call_count, 8)
                self.assertEqual(waiter.call_args.kwargs['timeout'], 8)

    async def test_async_analysis_preserves_official_provenance_but_not_misdated_score(self):
        import main
        date = '2026-10-01'
        frame = pd.DataFrame({'Close': [100], 'Volume': [1000]}, index=pd.to_datetime([date]))
        chips = {'2330.TW': {'Foreign': 2000, 'Trust': 1000, 'as_of': '2026-09-30', 'unit': 'shares', 'source': 'https://official.invalid'}}
        provider = SimpleNamespace(get_chip_data=AsyncMock(return_value=chips), get_fx_status=AsyncMock(return_value=(0, 'test')), get_stock_history=AsyncMock(return_value=frame))
        evaluation = {'score': 50, 'advice': 'test', 'valuation': 'test', 'signals': [], 'exit_note': '-', 'stop_loss': 0}
        with patch.object(main, 'get_async_provider', AsyncMock(return_value=provider)), patch.object(main.TechnicalAnalyzer, 'calculate_indicators', return_value=frame), patch.object(main.StrategyEngine, 'evaluate', return_value=evaluation) as evaluate:
            results, _ = await main._analyze_targets_async([SimpleNamespace(id='2330.TW', name='test', cost=0, shares=0)])
        self.assertEqual(evaluate.call_args.args[2], chips)
        self.assertFalse(results[0]['institutional']['used_in_score'])
        self.assertEqual(results[0]['institutional']['unit'], 'shares')

    async def test_ai_summary_filters_old_future_undated_and_reports_generation_time(self):
        import main
        now = time.time()
        news = [{'title': title, 'source': 'test source', 'published_ts': stamp} for title, stamp in
                [('recent', now - 600), ('old', now - 73 * 3600), ('future', now + 86400), ('undated', 0)]]
        client = SimpleNamespace(enabled=True, chat_async=AsyncMock(return_value={'status': 'success', 'reply': 'safe summary'}))
        before = datetime.now(timezone.utc)
        with patch.object(main.NewsCrawler, 'fetch_all', return_value=news), patch.object(main, 'mai_client', client):
            result = await main.auto_news()
        after = datetime.now(timezone.utc)
        self.assertEqual(result['news_count'], 1)
        generated = datetime.fromisoformat(result['generated_at'])
        self.assertLessEqual(before, generated)
        self.assertLessEqual(generated, after)
        self.assertEqual(generated.utcoffset(), timedelta(hours=8))
        self.assertLess(datetime.fromisoformat(result['news_published_to']), generated)
        prompt = client.chat_async.call_args.args[0]
        self.assertIn(result['news_published_from'], prompt)
        self.assertIn('recent', prompt)
        for excluded in ('old', 'future', 'undated'):
            self.assertNotIn(excluded, prompt)


if __name__ == '__main__':
    unittest.main()

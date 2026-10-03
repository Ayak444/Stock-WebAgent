"""Bounded official-source tests with fake transports, futures and clocks."""
import json
import socket
import unittest
from concurrent.futures import Future
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import requests
from urllib3.exceptions import ConnectTimeoutError, MaxRetryError, NameResolutionError, ReadTimeoutError

import market_provenance as mp

PRIVATE = 'test-only-private-source-query-and-payload'


class ImmediatePool:
    def submit(self, method, *args):
        future = Future()
        try:
            future.set_result(method(*args))
        except Exception as exc:
            future.set_exception(exc)
        return future


def official_payload(date):
    return {'stat': 'OK', 'date': date.strftime('%Y%m%d'),
            'fields': ['證券代號', '外陸資買賣超股數(不含外資自營商)', '投信買賣超股數'],
            'data': [['2330', '1,500', '-3,000'], ['00935', '2000', '0'],
                     ['030001', '999999', '999999']]}


def official_row(date, market='上市'):
    return {'Foreign': 1500, 'Trust': -3000, 'unit': 'shares',
            'as_of': date.isoformat(), 'source': mp.TWSE_INSTITUTIONAL_URL if market == '上市' else mp.TPEX_INSTITUTIONAL_URL,
            'market': market}


class InstitutionalReliabilityTests(unittest.TestCase):
    def provider(self):
        provider = mp.InstitutionalProvider()
        self.addCleanup(provider._pool.shutdown, wait=True)
        return provider

    def test_reduced_selector_preserves_supported_rows_and_latest_recent_date(self):
        provider = self.provider()
        today = datetime.now(mp.TW_TZ).date()
        newest = today - timedelta(days=1)
        older = today - timedelta(days=3)
        def response(url):
            if f'date={newest.strftime("%Y%m%d")}' in url:
                return official_payload(newest)
            if f'date={older.strftime("%Y%m%d")}' in url:
                return official_payload(older)
            return {'stat': 'no data'}
        with patch.object(mp, 'TWSE_CHIP_EXECUTOR', ImmediatePool()), patch.object(provider, '_json', side_effect=response) as load, patch.object(mp, 'wait', wraps=mp.wait) as wait:
            rows, reason = provider._twse_result()
        self.assertIsNone(reason)
        self.assertEqual(rows, mp.normalize_twse_institutional(official_payload(newest)))
        self.assertEqual(set(rows), {'2330.TW', '00935.TW'})
        self.assertEqual(rows['2330.TW']['Foreign'], 1500)
        self.assertEqual(rows['2330.TW']['unit'], 'shares')
        self.assertTrue(all(row['as_of'] == newest.isoformat() for row in rows.values()))
        self.assertEqual(load.call_count, 8)
        self.assertTrue(all('selectType=ALLBUT0999&response=json' in call.args[0] for call in load.call_args_list))
        self.assertEqual(wait.call_args.kwargs['timeout'], 8)
        self.assertTrue(mp.normalize_twse_institutional(official_payload(today - timedelta(days=7))))
        self.assertEqual(mp.normalize_twse_institutional(official_payload(today - timedelta(days=8))), {})

    def test_real_exception_chains_and_schema_failures_have_static_private_reasons(self):
        provider = self.provider()
        dns = NameResolutionError(PRIVATE, None, socket.gaierror(-2, PRIVATE))
        cases = [(requests.ConnectionError(MaxRetryError(None, PRIVATE, dns)), 'dns'),
                 (requests.ConnectionError(ReadTimeoutError(None, PRIVATE, PRIVATE)), 'read'),
                 (requests.ConnectionError(ConnectTimeoutError(PRIVATE)), 'connect'),
                 (requests.ConnectTimeout(PRIVATE), 'connect'),
                 (requests.ReadTimeout(PRIVATE), 'read'),
                 (TimeoutError(PRIVATE), 'deadline'), (ValueError(PRIVATE), 'schema')]
        for error, reason in cases:
            with self.subTest(reason=reason), patch.object(provider, '_json', side_effect=error):
                self.assertEqual(mp.institutional_failure_reason(error), reason)
                result = provider._tpex_result()
                self.assertEqual(result, ({}, reason))
                self.assertNotIn(PRIVATE, str(result))
        for payload, reason in [([], 'no_data'), ({'private': PRIVATE}, 'schema'),
                                ([{'private': PRIVATE}], 'schema')]:
            with patch.object(provider, '_json', return_value=payload):
                self.assertEqual(provider._tpex_result(), ({}, reason))

    def test_deadline_failure_is_independent_of_healthy_market_and_redacted(self):
        provider = self.provider()
        today = datetime.now(mp.TW_TZ).date()
        pending, success = Future(), Future()
        success.set_result(({'6488.TWO': official_row(today, '上櫃')}, None))
        pool = Mock()
        pool.submit.side_effect = [pending, success]
        with patch.object(provider, '_pool', pool), patch.object(mp, 'wait', return_value=({success}, {pending})) as wait:
            result = provider.get()
        self.assertTrue(pending.cancelled())
        self.assertEqual(wait.call_args.kwargs['timeout'], 12)
        self.assertEqual(result['_coverage']['上市'], {'available': False, 'as_of': None, 'reason': 'deadline'})
        self.assertEqual(result['_coverage']['上櫃'], {'available': True, 'as_of': today.isoformat(), 'reason': None})
        self.assertEqual(result['6488.TWO']['Foreign'], 1500)
        self.assertNotIn(PRIVATE, json.dumps(result))

    def test_per_market_failure_retries_early_and_preserves_success_until_300_seconds(self):
        provider = self.provider()
        today = datetime.now(mp.TW_TZ).date()
        twse = {'2330.TW': official_row(today)}
        tpex = {'6488.TWO': official_row(today, '上櫃')}
        clock = [0.0]
        with patch.object(provider, '_pool', ImmediatePool()), patch.object(mp.time, 'monotonic', side_effect=lambda: clock[0]), \
             patch.object(provider, '_twse_result', return_value=(twse, None)) as listed, \
             patch.object(provider, '_tpex_result', side_effect=[({}, 'dns'), (tpex, None)]) as otc:
            initial = provider.get()
            self.assertEqual(initial['_coverage']['上櫃']['reason'], 'dns')
            self.assertEqual(provider._market_cache['上市']['expires'], 300)
            self.assertGreaterEqual(provider._market_cache['上櫃']['expires'], 15)
            self.assertLessEqual(provider._market_cache['上櫃']['expires'], 30)
            clock[0] = 19
            provider.get()
            self.assertEqual((listed.call_count, otc.call_count), (1, 1))
            clock[0] = 21
            recovered = provider.get()
            self.assertEqual((listed.call_count, otc.call_count), (1, 2))
            self.assertEqual(recovered['2330.TW'], initial['2330.TW'])
            self.assertTrue(recovered['_coverage']['上櫃']['available'])
            clock[0] = 299
            provider.get()
            self.assertEqual(listed.call_count, 1)
            clock[0] = 301
            provider.get()
            self.assertEqual((listed.call_count, otc.call_count), (2, 2))
        empty = self.provider()
        clock[0] = 0
        with patch.object(empty, '_pool', ImmediatePool()), patch.object(mp.time, 'monotonic', side_effect=lambda: clock[0]), \
             patch.object(empty, '_twse_result', return_value=({}, 'no_data')) as listed, \
             patch.object(empty, '_tpex_result', return_value=({}, 'schema')):
            self.assertEqual(set(empty.get()), {'_coverage'})
            clock[0] = 21
            self.assertEqual(set(empty.get()), {'_coverage'})
            self.assertEqual(listed.call_count, 2)


if __name__ == '__main__':
    unittest.main()

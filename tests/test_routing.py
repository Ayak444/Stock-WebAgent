import os
import unittest
from unittest.mock import patch, Mock, AsyncMock
import pandas as pd
from market_routing import MarketRouter
from route_gateway import AIGateway, AIUnavailable
from routing_policy import deep_analysis

def bars():
    end = pd.Timestamp.now(tz='Asia/Taipei').normalize()
    return pd.DataFrame({'Open': 10., 'High': 12., 'Low': 9., 'Close': 11., 'Volume': 100},
                        index=pd.date_range(end-pd.Timedelta(days=30), end, freq='D'))

class RoutingTests(unittest.IsolatedAsyncioTestCase):
    async def test_fallback_cache_and_provenance(self):
        router = MarketRouter()
        router.yahoo = AsyncMock(side_effect=ValueError('unavailable'))
        router.twse = AsyncMock(return_value=bars())
        frame = await router.history(None, '2330.TW', 30)
        self.assertEqual(frame.attrs['route']['source'], 'twse')
        self.assertTrue(frame.attrs['route']['degraded'])
        cached = await router.history(None, '2330.TW', 30)
        self.assertTrue(cached.attrs['route']['from_cache'])
        self.assertEqual(router.twse.await_count, 1)

    async def test_wrong_exchange_never_falls_back_to_twse(self):
        router = MarketRouter()
        router.yahoo = AsyncMock(side_effect=ValueError())
        router.twse = AsyncMock()
        self.assertTrue((await router.history(None, '6488.TWO', 30)).empty)
        router.twse.assert_not_called()

    def test_invalid_stale_and_incomplete_rejected(self):
        for kind in ('invalid', 'stale', 'short'):
            frame = bars()
            if kind == 'invalid': frame.iloc[-1, 1] = 1
            if kind == 'stale': frame.index -= pd.Timedelta(days=20)
            if kind == 'short': frame = frame.iloc[-3:]
            with self.assertRaises(ValueError): MarketRouter.validate(frame, 30)

    async def test_yahoo_uses_requested_range(self):
        router = MarketRouter()
        fetch = AsyncMock(return_value={'chart': {'result': [{'timestamp': [], 'indicators': {
            'quote': [{'open': [], 'high': [], 'low': [], 'close': [], 'volume': []}]}}]}})
        await router.yahoo(fetch, 'TSM', 1000)
        url = fetch.call_args.args[0]
        self.assertIn('period1=', url)
        self.assertNotIn('range=1y', url)

class AITests(unittest.TestCase):
    @patch.dict(os.environ, {'GROQ_API_KEY': 'test-only-key'})
    @patch('route_gateway.requests.post')
    def test_auth_failure_blocks_following_requests(self, post):
        post.return_value = Mock(status_code=401)
        gateway = AIGateway()
        for _ in range(2):
            with self.assertRaises(AIUnavailable): gateway.complete({})
        self.assertEqual(post.call_count, 1)
        with patch.dict(os.environ, {'GROQ_API_KEY': 'replacement-test-key'}):
            with self.assertRaises(AIUnavailable): gateway.complete({})
        self.assertEqual(post.call_count, 2)

    @patch.dict(os.environ, {'GROQ_API_KEY': 'test-only-key'})
    @patch('route_gateway.requests.post')
    def test_rate_limit_cooldown(self, post):
        post.return_value = Mock(status_code=429, headers={'Retry-After': '60'})
        gateway = AIGateway()
        for _ in range(2):
            with self.assertRaises(AIUnavailable): gateway.complete({})
        self.assertEqual(post.call_count, 1)

    @patch('routing_policy.ai_gateway.complete', return_value='{"score": 999, "advice":"bad"}')
    def test_invalid_ai_score_rejected(self, complete):
        with self.assertRaises(ValueError): deep_analysis('2330.TW', {'RSI': 50.}, '')

class AnalysisIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_quick_duplicate_tickers_and_deep_failure(self):
        # Isolate this orchestration function from legacy import-time network I/O.
        import ast
        import asyncio
        import logging
        import traceback
        from pathlib import Path
        from types import SimpleNamespace
        from models import StockTarget
        tree = ast.parse(Path('main.py').read_text(encoding='utf-8'))
        function = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef)
                        and n.name == '_analyze_targets_async')
        provider = SimpleNamespace(get_chip_data=AsyncMock(return_value={}),
            get_fx_status=AsyncMock(return_value=(0, 'flat')),
            get_stock_history=AsyncMock(return_value=bars()))
        news = Mock(return_value=[{'title': 'test'}])
        env = {'asyncio': asyncio, 'get_async_provider': AsyncMock(return_value=provider),
            'mai_client': SimpleNamespace(enabled=True), 'audit': Mock(),
            'logger': logging.getLogger('test'), 'traceback': traceback,
            'NewsCrawler': SimpleNamespace(fetch_all=news),
            'TechnicalAnalyzer': SimpleNamespace(calculate_indicators=lambda frame: frame),
            'StrategyEngine': SimpleNamespace(evaluate=Mock(return_value={
                'score': 50, 'advice': 'technical', 'valuation': '-', 'signals': [],
                'exit_note': '-', 'stop_loss': 0}))}
        exec(compile(ast.Module(body=[function], type_ignores=[]), 'main.py', 'exec'), env)
        targets = [StockTarget('2330.TW', 'one', '', 10, 1),
                   StockTarget('2330.TW', 'two', '', 20, 2)]
        with patch('routing_policy.deep_analysis', side_effect=ValueError('invalid')) as deep:
            results, _ = await env['_analyze_targets_async'](targets)
            self.assertEqual(len(results), 2)
            self.assertNotEqual(results[0]['pl'], results[1]['pl'])
            self.assertEqual(provider.get_stock_history.await_count, 1)
            deep.assert_not_called()
            news.assert_not_called()
            results, _ = await env['_analyze_targets_async'](targets, 'deep')
            self.assertEqual(news.call_count, 1)
            self.assertTrue(all(r['advice'] == 'technical' for r in results))
            self.assertTrue(all(r['ai_route']['reason'] == 'ai_failed_using_technical' for r in results))

"""
異步數據提供者
使用 asyncio + aiohttp 實現高效的並發數據獲取
替代原本的同步 requests 調用
"""
import asyncio
import aiohttp
import pandas as pd
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, List, Tuple
import json
from cache_layer import cache_manager

TW_TZ = timezone(timedelta(hours=8))

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

class AsyncDataProvider:
    """
    異步數據提供者
    - 並行請求多個數據源
    - 結果自動緩存
    - 線程安全的 asyncio 操作
    """
    
    def __init__(self, session: Optional[aiohttp.ClientSession] = None):
        self.session = session
        self._session_owned = session is None  # 是否由本類管理 session
    
    async def __aenter__(self):
        if self._session_owned and self.session is None:
            self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._session_owned and self.session:
            await self.session.close()
    
    async def _ensure_session(self):
        """確保 session 存在"""
        if self.session is None:
            self.session = aiohttp.ClientSession()
    
    async def _get_json(self, url: str, timeout: int = 10) -> Optional[dict]:
        """異步 GET 請求 JSON"""
        await self._ensure_session()
        try:
            async with self.session.get(url, headers=HEADERS, timeout=timeout) as resp:
                if resp.status == 200:
                    return await resp.json()
        except asyncio.TimeoutError:
            print(f"超時：{url}")
        except Exception as e:
            print(f"請求失敗 {url}: {e}")
        return None
    
    async def is_market_open(self) -> bool:
        """檢查市場是否開盤"""
        now = datetime.now(TW_TZ)
        if now.weekday() >= 5:  # 週末
            return False
        start = now.replace(hour=9, minute=0, second=0, microsecond=0)
        end = now.replace(hour=13, minute=30, second=0, microsecond=0)
        return start <= now <= end
    
    async def get_macro_indices(self) -> Dict[str, Dict]:
        """
        並行獲取多個總體經濟指標
        返回：{指標名稱: {price, change, pct_change}}
        """
        # 檢查緩存
        cached = cache_manager.memory_cache.get("macro_indices")
        if cached:
            return cached
        
        result = {}
        tickers = {
            "^TWII": "台灣加權",
            "^SOX": "費城半導體",
            "^GSPC": "S&P 500",
            "TSM": "台積電 ADR",
            "NVDA": "輝達",
            "^N225": "日經 225",
            "^KS11": "韓國綜合",
            "^VIX": "VIX 恐慌"
        }
        
        # 並行請求
        tasks = [
            self._fetch_macro_symbol(symbol, name)
            for symbol, name in tickers.items()
        ]
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        
        for symbol, name in tickers.items():
            result[name] = {"price": 0, "change": 0, "pct_change": 0}
        
        for idx, (symbol, name) in enumerate(tickers.items()):
            if idx < len(responses) and isinstance(responses[idx], dict):
                result[name] = responses[idx]
        
        # 緩存 5 分鐘
        cache_manager.memory_cache.set("macro_indices", result, ttl_seconds=300)
        return result
    
    async def _fetch_macro_symbol(self, symbol: str, name: str) -> Dict:
        """獲取單個宏觀指標"""
        try:
            url = f"https://query2.finance.yahoo.com/v8/finance/chart/{symbol}?range=5d&interval=1d"
            data = await self._get_json(url, timeout=8)
            
            if data and 'chart' in data and data['chart']['result']:
                result_data = data['chart']['result'][0]
                quote = result_data['indicators']['quote'][0]
                closes = [c for c in quote.get('close', []) if c is not None]
                
                if len(closes) >= 1:
                    current = float(closes[-1])
                    prev = float(closes[-2]) if len(closes) > 1 else current
                    change = current - prev
                    pct_change = (change / prev * 100) if prev else 0
                    
                    return {
                        "price": round(current, 2),
                        "change": round(change, 2),
                        "pct_change": round(pct_change, 2)
                    }
        except Exception as e:
            print(f"獲取 {symbol} 失敗: {e}")
        
        return {"price": 0, "change": 0, "pct_change": 0}
    
    async def get_stock_history(self, ticker: str, days: int = 180) -> pd.DataFrame:
        """
        獲取股票歷史價格
        先查緩存，無則從 Yahoo Finance 取得
        """
        # 檢查緩存
        cached_df_dict = cache_manager.get_kline(ticker, days)
        if cached_df_dict:
            df = pd.DataFrame(cached_df_dict)
            if 'Date' not in df.columns and 'index' in df.columns:
                df = df.rename(columns={'index': 'Date'})
            if 'Date' in df.columns:
                df['Date'] = pd.to_datetime(df['Date'])
                return df.set_index('Date')
            else:
                return df
        
        try:
            url = (f"https://query2.finance.yahoo.com/v8/finance/chart/{ticker}"
                   f"?range=1y&interval=1d")
            data = await self._get_json(url, timeout=10)
            
            if not data or 'chart' not in data:
                return pd.DataFrame()
            
            result = data['chart']['result'][0]
            timestamps = result['timestamp']
            quote = result['indicators']['quote'][0]
            
            df = pd.DataFrame({
                'Date': pd.to_datetime(timestamps, unit='s'),
                'Open': quote['open'],
                'High': quote['high'],
                'Low': quote['low'],
                'Close': quote['close'],
                'Volume': quote['volume']
            })
            
            df = df.dropna().set_index('Date')
            cutoff = pd.Timestamp.now(tz='UTC').tz_localize(None) - pd.Timedelta(days=days)
            df = df[df.index >= cutoff]
            
            # 存入緩存（24 小時）
            cache_manager.set_kline(ticker, days, df, ttl=86400)
            
            return df
        except Exception as e:
            print(f"獲取 {ticker} 歷史數據失敗: {e}")
            return pd.DataFrame()
    
    async def get_realtime_price(self, ticker: str) -> Optional[float]:
        """獲取實時價格"""
        try:
            url = f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{ticker}"
            data = await self._get_json(url, timeout=5)
            
            if data and 'quoteSummary' in data and 'result' in data['quoteSummary']:
                price = data['quoteSummary']['result'][0]['price']['regularMarketPrice']
                return float(price)
        except Exception as e:
            print(f"獲取 {ticker} 實時價格失敗: {e}")
        
        return None
    
    async def get_multiple_prices(self, tickers: List[str]) -> Dict[str, float]:
        """
        並行獲取多個股票的實時價格
        """
        tasks = [self.get_realtime_price(ticker) for ticker in tickers]
        prices = await asyncio.gather(*tasks, return_exceptions=True)
        
        result = {}
        for ticker, price in zip(tickers, prices):
            result[ticker] = price if isinstance(price, (int, float)) else None
        
        return result
    
    async def get_fx_status(self) -> Tuple[int, str]:
        """
        獲取外匯狀況（台幣升貶）
        返回：(狀態值: -1升1貶0平, 說明文字)
        """
        try:
            url = "https://query2.finance.yahoo.com/v8/finance/chart/USDTWD=X?range=30d&interval=1d"
            data = await self._get_json(url, timeout=8)
            
            if data and 'chart' in data and data['chart']['result']:
                result_data = data['chart']['result'][0]
                closes = result_data['indicators']['quote'][0]['close']
                closes = [c for c in closes if c is not None]
                
                if len(closes) >= 10:
                    current = closes[-1]
                    prev = closes[-10]
                    change_pct = (current - prev) / prev * 100
                    
                    if change_pct > 0.5:
                        return 1, "台幣貶值（對出口股有利）"
                    elif change_pct < -0.5:
                        return -1, "台幣升值（對出口股不利）"
                    else:
                        return 0, "台幣波動不大"
        except Exception as e:
            print(f"獲取匯率失敗: {e}")
        
        return 0, "無法判斷"
    
    async def get_chip_data(self) -> Dict:
        """
        獲取籌碼面數據（外資、投信、自營商）
        注：此示例返回格式，實際需連接真實數據源
        """
        # TODO: 連接真實籌碼面 API（例如 TWSE 或第三方服務）
        cached = cache_manager.memory_cache.get("chip_data")
        if cached:
            return cached
        
        return {}
    
    async def close(self):
        """關閉 session"""
        if self._session_owned and self.session:
            await self.session.close()


# 便利函數：創建全局異步數據提供者
_async_provider_session = None


async def get_async_provider() -> AsyncDataProvider:
    """取得全局異步數據提供者"""
    global _async_provider_session
    if _async_provider_session is None:
        _async_provider_session = aiohttp.ClientSession()
    return AsyncDataProvider(_async_provider_session)


async def close_async_provider():
    """關閉全局異步數據提供者"""
    global _async_provider_session
    if _async_provider_session:
        await _async_provider_session.close()
        _async_provider_session = None

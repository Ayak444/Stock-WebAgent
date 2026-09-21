import requests
import pandas as pd
from datetime import datetime, timedelta, timezone
import time
import re
import json
from concurrent.futures import ThreadPoolExecutor

# 台灣時區 UTC+8
TW_TZ = timezone(timedelta(hours=8))

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
}

# Each supported backtest window includes 30 warmup bars. Yahoo is one bounded
# request; the official fallback uses at most 24 distinct months / six workers.
BACKTEST_HISTORY_PLAN = {
    60: ('6mo', 6),
    120: ('1y', 9),
    210: ('1y', 14),
    395: ('2y', 24),
}
BACKTEST_MAX_RESPONSE_BYTES = 500_000
BACKTEST_MAX_SOURCE_SECONDS = 20  # 4s Yahoo + four 4s official waves


def _bounded_json_get(url: str):
    """Bound each history request by bytes and wall time, including slow streams."""
    started = time.monotonic()
    response = requests.get(url, headers=HEADERS, timeout=(1, 1.5), stream=True)
    try:
        chunks = bytearray()
        # One-byte chunks ensure a trickling server cannot defer the deadline
        # check while a large read waits to fill its buffer.
        for chunk in response.iter_content(chunk_size=1):
            if time.monotonic() - started > 2.5:
                raise TimeoutError('history response deadline')
            chunks.extend(chunk)
            if len(chunks) > BACKTEST_MAX_RESPONSE_BYTES:
                raise ValueError('history response too large')
        return json.loads(chunks)
    finally:
        close = getattr(response, 'close', None)
        if callable(close):
            close()

class DataProvider:
    @staticmethod
    def get_backtest_history(ticker: str, required_bars: int) -> pd.DataFrame:
        if required_bars not in BACKTEST_HISTORY_PLAN:
            raise ValueError('unsupported backtest window')
        history_range, months = BACKTEST_HISTORY_PLAN[required_bars]
        yahoo = pd.DataFrame()
        try:
            url = f"https://query2.finance.yahoo.com/v8/finance/chart/{ticker}?range={history_range}&interval=1d"
            result = _bounded_json_get(url)['chart']['result'][0]
            quote = result['indicators']['quote'][0]
            yahoo = pd.DataFrame({
                'Date': pd.to_datetime(result['timestamp'], unit='s'),
                'Open': quote['open'], 'High': quote['high'], 'Low': quote['low'],
                'Close': quote['close'], 'Volume': quote['volume'],
            }).dropna().set_index('Date').sort_index()
            if len(yahoo) >= required_bars:
                yahoo.attrs['route'] = {
                    'source': 'yahoo', 'asof': yahoo.index[-1].date().isoformat(),
                    'price_basis': 'unadjusted_daily',
                }
                return yahoo
        except Exception:
            pass

        stock_id = ticker.split('.')[0]
        fetch_month = DataProvider._fetch_tpex_month if ticker.upper().endswith('.TWO') else DataProvider._fetch_twse_month
        first_month = pd.Timestamp.now(tz=TW_TZ).replace(day=1)
        targets = [(first_month - pd.DateOffset(months=i)).to_pydatetime() for i in range(months)]

        def load_month(target):
            try:
                return fetch_month(stock_id, target, bounded=True)
            except Exception:
                return []

        with ThreadPoolExecutor(max_workers=6) as pool:
            month_rows = list(pool.map(load_month, targets))
        rows = [row for group in month_rows for row in group]
        official = pd.DataFrame()
        if rows:
            official = pd.DataFrame(rows, columns=['Date', 'Open', 'High', 'Low', 'Close', 'Volume'])
            official['Date'] = pd.to_datetime(official['Date'])
            official = official.drop_duplicates('Date').sort_values('Date').set_index('Date')
            official.attrs['route'] = {
                'source': 'tpex' if ticker.upper().endswith('.TWO') else 'twse',
                'asof': official.index[-1].date().isoformat(),
                'price_basis': 'unadjusted_daily',
            }
        if len(official) >= required_bars:
            return official
        if len(yahoo) > len(official):
            yahoo.attrs['route'] = {
                'source': 'yahoo', 'asof': yahoo.index[-1].date().isoformat(),
                'price_basis': 'unadjusted_daily',
            }
            return yahoo
        return official

    @staticmethod
    def is_market_open():
        now = datetime.now(TW_TZ)
        if now.weekday() >= 5:
            return False
        start = now.replace(hour=9, minute=0, second=0)
        end = now.replace(hour=13, minute=30, second=0)
        return start <= now <= end

    @staticmethod
    def get_macro_indices():
        result = {}
        tickers = {
            "^TWII": "台灣加權", "^SOX": "費城半導體", "^GSPC": "S&P 500", "TSM": "台積電 ADR",
            "NVDA": "輝達 NVDA", "^N225": "日經 225", "^KS11": "韓國綜合", "^VIX": "VIX 恐慌"
        }
        for symbol, name in tickers.items():
            try:
                url = f"https://query2.finance.yahoo.com/v8/finance/chart/{symbol}?range=5d&interval=1d"
                r = requests.get(url, headers=HEADERS, timeout=5)
                data = r.json()
                if 'chart' in data and data['chart']['result']:
                    result_data = data['chart']['result'][0]
                    quote = result_data['indicators']['quote'][0]
                    closes = [c for c in quote.get('close', []) if c is not None]
                    if len(closes) >= 1:
                        current = float(closes[-1])
                        prev = float(closes[-2]) if len(closes) > 1 else current
                        change = current - prev
                        pct_change = (change / prev) * 100 if prev else 0
                        result[name] = {"price": round(current, 2), "change": round(change, 2), "pct_change": round(pct_change, 2)}
                        continue
            except Exception:
                pass
            result[name] = {"price": 0, "change": 0, "pct_change": 0}
            
        return result

    @staticmethod
    def get_stock_history(ticker: str, days: int = 180) -> pd.DataFrame:
        try:
            df = DataProvider._fetch_twse_history(ticker, days)
            if not df.empty:
                df.attrs['route'] = {
                    'source': 'tpex' if ticker.upper().endswith('.TWO') else 'twse',
                    'asof': df.index[-1].date().isoformat(),
                    'price_basis': 'unadjusted_daily',
                }
                return df
        except Exception:
            pass

        try:
            history_range = '1y' if days <= 365 else '5y' if days <= 1825 else '10y' if days <= 3650 else 'max'
            url = f"https://query2.finance.yahoo.com/v8/finance/chart/{ticker}?range={history_range}&interval=1d"
            r = requests.get(url, headers=HEADERS, timeout=10)
            data = r.json()
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
            df.index = df.index.tz_localize(None)
            df = df[df.index >= cutoff]
            if not df.empty:
                df.attrs['route'] = {
                    'source': 'yahoo',
                    'asof': df.index[-1].date().isoformat(),
                    'price_basis': 'unadjusted_daily',
                }
                return df
        except Exception:
            pass

        return pd.DataFrame()

    @staticmethod
    def _fetch_twse_history(ticker: str, days: int) -> pd.DataFrame:
        stock_id = ticker.split('.')[0]
        is_otc = ticker.upper().endswith('.TWO')
        months_needed = max(2, (days // 25) + 1)
        all_rows = []
        now = datetime.now()

        for i in range(months_needed):
            target = now - timedelta(days=30 * i)
            if is_otc:
                rows = DataProvider._fetch_tpex_month(stock_id, target)
            else:
                rows = DataProvider._fetch_twse_month(stock_id, target)
            all_rows.extend(rows)
            time.sleep(0.3)

        if not all_rows:
            return pd.DataFrame()

        df = pd.DataFrame(all_rows, columns=['Date', 'Open', 'High', 'Low', 'Close', 'Volume'])
        df['Date'] = pd.to_datetime(df['Date'])
        df = df.drop_duplicates('Date').sort_values('Date').set_index('Date')
        cutoff = datetime.now() - timedelta(days=days)
        df = df[df.index >= cutoff]
        return df

    @staticmethod
    def _fetch_twse_month(stock_id: str, date_obj: datetime, timeout=10, bounded=False):
        date_str = date_obj.strftime("%Y%m") + "01"
        url = f"https://www.twse.com.tw/exchangeReport/STOCK_DAY?response=json&date={date_str}&stockNo={stock_id}"
        if bounded:
            data = _bounded_json_get(url)
        else:
            r = requests.get(url, headers=HEADERS, timeout=timeout)
            data = r.json()
        if data.get("stat") != "OK":
            return []

        result = []
        for row in data.get("data", []):
            try:
                parts = row[0].split('/')
                year = int(parts[0]) + 1911
                date = f"{year}-{parts[1]}-{parts[2]}"
                o = float(row[3].replace(',', ''))
                h = float(row[4].replace(',', ''))
                low = float(row[5].replace(',', ''))
                c = float(row[6].replace(',', ''))
                v = int(row[1].replace(',', '')) if row[1] != '--' else 0
                result.append([date, o, h, low, c, v])
            except (ValueError, IndexError):
                continue
        return result

    @staticmethod
    def _fetch_tpex_month(stock_id: str, date_obj: datetime, timeout=10, bounded=False):
        roc_year = date_obj.year - 1911
        date_str = f"{roc_year}/{date_obj.strftime('%m')}"
        url = f"https://www.tpex.org.tw/web/stock/aftertrading/daily_trading_info/st43_result.php?l=zh-tw&d={date_str}&stkno={stock_id}"
        try:
            if bounded:
                data = _bounded_json_get(url)
            else:
                r = requests.get(url, headers=HEADERS, timeout=timeout)
                data = r.json()
        except Exception:
            return []

        result = []
        for row in data.get("aaData", []):
            try:
                parts = row[0].split('/')
                year = int(parts[0]) + 1911
                date = f"{year}-{parts[1]}-{parts[2]}"
                o = float(row[3].replace(',', ''))
                h = float(row[4].replace(',', ''))
                low = float(row[5].replace(',', ''))
                c = float(row[6].replace(',', ''))
                v = int(row[7].replace(',', '')) if len(row) > 7 else 0
                result.append([date, o, h, low, c, v])
            except (ValueError, IndexError):
                continue
        return result

    @staticmethod
    def get_realtime_price(ticker: str):
        try:
            stock_id = ticker.split('.')[0]
            market = "otc" if ticker.upper().endswith('.TWO') else "tse"
            url = f"https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch={market}_{stock_id}.tw"
            r = requests.get(url, timeout=5, headers=HEADERS)
            data = r.json()
            if data.get("msgArray"):
                info = data["msgArray"][0]
                z = info.get("z", "-")
                if z != "-" and z != "":
                    return float(z)
                y = info.get("y", "-")
                if y != "-" and y != "":
                    return float(y)
        except Exception:
            pass
        
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=1d&interval=1d"
            r = requests.get(url, headers=HEADERS, timeout=5)
            data = r.json()
            price = data['chart']['result'][0]['meta']['regularMarketPrice']
            if price:
                return float(price)
        except Exception:
            pass
            
        return None

    @staticmethod
    def get_fx_status():
        try:
            url = "https://rate.bot.com.tw/xrt/flcsv/0/day"
            r = requests.get(url, timeout=10, headers=HEADERS)
            lines = r.text.strip().split('\n')
            for line in lines[1:]:
                parts = line.split(',')
                if parts[0] == 'USD':
                    rate = float(parts[2])
                    if rate > 32.5:
                        return 1, f"台幣走弱 ({rate:.2f})"
                    elif rate < 31.0:
                        return -1, f"台幣走強 ({rate:.2f})"
                    return 0, f"匯率平穩 ({rate:.2f})"
        except Exception:
            pass
        return 0, ""

    @staticmethod
    def get_rankings():
        try:
            url = "https://openapi.twse.com.tw/v1/exchangeReport/MI_INDEX20"
            r = requests.get(url, timeout=5, headers=HEADERS)
            data = r.json()
            vol_top = []
            if isinstance(data, list):
                for row in data[:5]:
                    vol_top.append({
                        "ticker": f"{row.get('證券代號')}.TW",
                        "name": row.get('證券名稱'),
                        "volume": int(row.get('成交股數', '0').replace(',', '')) // 1000,
                        "price": row.get('收盤價')
                    })
            return {"volume": vol_top}
        except Exception as e:
            return {"volume": []}

    @staticmethod
    def get_fundamentals(ticker: str):
        try:
            import yfinance as yf
            stock = yf.Ticker(ticker)
            info = stock.info
            return {
                "eps": info.get("trailingEps", "-"),
                "pe": info.get("trailingPE", "-"),
                "dividendYield": info.get("dividendYield", "-"),
                "revenueGrowth": info.get("revenueGrowth", "-"),
                "marketCap": info.get("marketCap", "-"),
                "sector": info.get("sector", "-"),
                "industry": info.get("industry", "-")
            }
        except Exception:
            return {}

    @staticmethod
    def get_chip_data():
        try:
            for i in range(5):
                date = (datetime.now() - timedelta(days=i)).strftime("%Y%m%d")
                url = f"https://www.twse.com.tw/rwd/zh/fund/T86?date={date}&selectType=ALL&response=json"
                r = requests.get(url, timeout=10, headers=HEADERS)
                data = r.json()
                if data.get("stat") == "OK" and data.get("data"):
                    result = {}
                    for row in data["data"]:
                        try:
                            sid = row[0].strip()
                            foreign = int(row[4].replace(",", ""))
                            trust = int(row[10].replace(",", ""))
                            result[sid] = {"Foreign": foreign, "Trust": trust}
                        except (ValueError, IndexError):
                            continue
                    if result:
                        return result
                time.sleep(0.3)
        except Exception:
            pass
        return {}

MarketDataProvider = DataProvider

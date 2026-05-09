import requests
import pandas as pd
from datetime import datetime, timedelta
import time
import re
import json

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
}

class DataProvider:
    @staticmethod
    def is_market_open():
        now = datetime.now()
        if now.weekday() >= 5:
            return False
        start = now.replace(hour=9, minute=0, second=0)
        end = now.replace(hour=13, minute=30, second=0)
        return start <= now <= end

    @staticmethod
    def get_macro_indices():
        result = {}
        tickers = {"^TWII": "加權指數", "CL=F": "油價", "GC=F": "金價"}
        
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

        result["台指期"] = {"price": 0, "change": 0, "pct_change": 0}
        try:
            url = "https://mis.taifex.com.tw/futures/api/getQuoteList"
            payload = {"MarketType":"0", "SymbolType":"F", "KindID":"1", "CID":"TXF", "ExpireMonths":"", "Shrink":""}
            r = requests.post(url, json=payload, headers=HEADERS, timeout=5)
            data = r.json()
            if data.get('RtData', {}).get('QuoteList'):
                q = data['RtData']['QuoteList'][0]
                price = float(q.get('CLastPrice') or q.get('CPrice') or 0)
                change = float(q.get('CDiff') or 0)
                if price > 0:
                    prev = price - change
                    pct = (change / prev * 100) if prev else 0
                    result["台指期"] = {"price": round(price, 2), "change": round(change, 2), "pct_change": round(pct, 2)}
        except Exception:
            try:
                r = requests.get("https://tw.stock.yahoo.com/quote/WTX%26T.EX", headers=HEADERS, timeout=5)
                match = re.search(r'window\.__PRELOADED_STATE__\s*=\s*({.*?});</script>', r.text)
                if match:
                    state = json.loads(match.group(1))
                    def find_quote(d, target="WTX&T.EX"):
                        if isinstance(d, dict):
                            if d.get('symbol') == target and 'price' in d:
                                return d
                            for k, v in d.items():
                                res = find_quote(v, target)
                                if res: return res
                        elif isinstance(d, list):
                            for item in d:
                                res = find_quote(item, target)
                                if res: return res
                        return None
                    
                    quote = find_quote(state)
                    if quote:
                        price = float(quote.get('price', 0))
                        change = float(quote.get('change', 0))
                        if price > 0:
                            prev = price - change
                            pct = (change / prev * 100) if prev else 0
                            result["台指期"] = {"price": round(price, 2), "change": round(change, 2), "pct_change": round(pct, 2)}
            except Exception:
                pass

        return result

    @staticmethod
    def get_stock_history(ticker: str, days: int = 180) -> pd.DataFrame:
        try:
            df = DataProvider._fetch_twse_history(ticker, days)
            if not df.empty:
                return df
        except Exception:
            pass

        try:
            url = f"https://query2.finance.yahoo.com/v8/finance/chart/{ticker}?range=1y&interval=1d"
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
    def _fetch_twse_month(stock_id: str, date_obj: datetime):
        date_str = date_obj.strftime("%Y%m") + "01"
        url = f"https://www.twse.com.tw/exchangeReport/STOCK_DAY?response=json&date={date_str}&stockNo={stock_id}"
        r = requests.get(url, headers=HEADERS, timeout=10)
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
    def _fetch_tpex_month(stock_id: str, date_obj: datetime):
        roc_year = date_obj.year - 1911
        date_str = f"{roc_year}/{date_obj.strftime('%m')}"
        url = f"https://www.tpex.org.tw/web/stock/aftertrading/daily_trading_info/st43_result.php?l=zh-tw&d={date_str}&stkno={stock_id}"
        try:
            r = requests.get(url, headers=HEADERS, timeout=10)
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
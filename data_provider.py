import requests
import pandas as pd
from datetime import datetime, timedelta
import time

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
}


class DataProvider:
    # ========== 市場狀態 ==========
    @staticmethod
    def is_market_open():
        now = datetime.now()
        if now.weekday() >= 5:
            return False
        start = now.replace(hour=9, minute=0, second=0)
        end = now.replace(hour=13, minute=30, second=0)
        return start <= now <= end

    # ========== 歷史 K 線 ==========
    @staticmethod
    def get_stock_history(ticker: str, days: int = 180) -> pd.DataFrame:
        """優先 TWSE API，失敗才 fallback 到 yfinance"""
        try:
            df = DataProvider._fetch_twse_history(ticker, days)
            if not df.empty:
                return df
        except Exception as e:
            print(f"[TWSE] {ticker} 失敗: {e}")

        # 備援 yfinance
        try:
            import yfinance as yf
            period = "1y" if days > 60 else f"{days}d"
            df = yf.Ticker(ticker).history(period=period)
            if not df.empty:
                return df
        except Exception as e:
            print(f"[yfinance] {ticker} 失敗: {e}")

        return pd.DataFrame()

    @staticmethod
    def _fetch_twse_history(ticker: str, days: int) -> pd.DataFrame:
        """證交所官方 API"""
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
        """TWSE 上市單月資料"""
        date_str = date_obj.strftime("%Y%m") + "01"
        url = (f"https://www.twse.com.tw/exchangeReport/STOCK_DAY"
               f"?response=json&date={date_str}&stockNo={stock_id}")
        r = requests.get(url, headers=HEADERS, timeout=10)
        data = r.json()
        if data.get("stat") != "OK":
            return []

        result = []
        for row in data.get("data", []):
            try:
                parts = row[0].split('/')
                year = int(parts[0]) + 1911  # 民國轉西元
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
        """TPEX 上櫃單月資料"""
        roc_year = date_obj.year - 1911
        date_str = f"{roc_year}/{date_obj.strftime('%m')}"
        url = (f"https://www.tpex.org.tw/web/stock/aftertrading/"
               f"daily_trading_info/st43_result.php?l=zh-tw&d={date_str}&stkno={stock_id}")
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

    # ========== 即時價格 ==========
    @staticmethod
    def get_realtime_price(ticker: str):
        try:
            stock_id = ticker.split('.')[0]
            market = "otc" if ticker.upper().endswith('.TWO') else "tse"
            url = (f"https://mis.twse.com.tw/stock/api/getStockInfo.jsp"
                   f"?ex_ch={market}_{stock_id}.tw")
            r = requests.get(url, timeout=5, headers=HEADERS)
            data = r.json()
            if data.get("msgArray"):
                info = data["msgArray"][0]
                z = info.get("z", "-")
                if z != "-" and z != "":
                    return float(z)
                y = info.get("y", "-")  # 昨收
                if y != "-" and y != "":
                    return float(y)
        except Exception as e:
            print(f"[Realtime] {ticker} 失敗: {e}")
        return None

    # ========== 匯率 ==========
    @staticmethod
    def get_fx_status():
        """台銀美元匯率"""
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
        except Exception as e:
            print(f"[FX] 失敗: {e}")
        return 0, ""

    # ========== 三大法人籌碼 ==========
    @staticmethod
    def get_chip_data():
        try:
            for i in range(5):
                date = (datetime.now() - timedelta(days=i)).strftime("%Y%m%d")
                url = (f"https://www.twse.com.tw/rwd/zh/fund/T86"
                       f"?date={date}&selectType=ALL&response=json")
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
        except Exception as e:
            print(f"[Chip] 失敗: {e}")
        return {}


# 別名相容
MarketDataProvider = DataProvider

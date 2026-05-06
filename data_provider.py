"""
data_provider.py - 台股資料源（TWSE 官方 API + yfinance 備援）
專為 Render / 雲端環境優化，解決 yfinance 被鎖 IP 問題
"""
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import time

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}


class DataProvider:
    # ========== 歷史 K 線（TWSE 官方 API，最穩定）==========
    @staticmethod
    def get_stock_history(ticker, days=180):
        """取得歷史 K 線，優先用 TWSE，失敗才用 yfinance"""
        try:
            return DataProvider._get_history_twse(ticker, days)
        except Exception as e:
            print(f"[TWSE] 失敗 {ticker}: {e}，改用 yfinance")
            try:
                return DataProvider._get_history_yfinance(ticker, days)
            except Exception as e2:
                print(f"[yfinance] 也失敗 {ticker}: {e2}")
                return pd.DataFrame()

    @staticmethod
    def _get_history_twse(ticker, days=180):
        """用證交所官方 API 抓歷史資料（不會被鎖 IP）"""
        stock_id = ticker.split('.')[0]
        
        # 需要抓幾個月
        months_needed = max(2, (days // 30) + 1)
        all_data = []
        
        now = datetime.now()
        for i in range(months_needed):
            target = now - timedelta(days=30 * i)
            date_str = target.strftime("%Y%m") + "01"
            
            # 判斷是上市(TWSE)還是上櫃(TPEX)
            if ticker.upper().endswith('.TWO'):
                url = f"https://www.tpex.org.tw/web/stock/aftertrading/daily_trading_info/st43_result.php?l=zh-tw&d={target.strftime('%Y/%m').replace(str(target.year), str(target.year-1911))}&stkno={stock_id}"
                data = DataProvider._fetch_tpex(url, stock_id)
            else:
                url = f"https://www.twse.com.tw/exchangeReport/STOCK_DAY?response=json&date={date_str}&stockNo={stock_id}"
                data = DataProvider._fetch_twse(url)
            
            all_data.extend(data)
            time.sleep(0.3)  # 避免被擋
        
        if not all_data:
            raise Exception("TWSE 無資料")
        
        df = pd.DataFrame(all_data, columns=['Date', 'Open', 'High', 'Low', 'Close', 'Volume'])
        df['Date'] = pd.to_datetime(df['Date'])
        df = df.drop_duplicates('Date').sort_values('Date').reset_index(drop=True)
        df = df.set_index('Date')
        
        # 只保留最近 N 天
        cutoff = datetime.now() - timedelta(days=days)
        df = df[df.index >= cutoff]
        
        return df

    @staticmethod
    def _fetch_twse(url):
        """抓 TWSE 上市股票"""
        r = requests.get(url, headers=HEADERS, timeout=10)
        data = r.json()
        if data.get("stat") != "OK":
            return []
        
        result = []
        for row in data.get("data", []):
            try:
                # 民國轉西元
                date_str = row[0].replace('/', '-')
                parts = date_str.split('-')
                year = int(parts[0]) + 1911
                date = f"{year}-{parts[1]}-{parts[2]}"
                
                open_p = float(row[3].replace(',', ''))
                high = float(row[4].replace(',', ''))
                low = float(row[5].replace(',', ''))
                close = float(row[6].replace(',', ''))
                volume = int(row[1].replace(',', '')) if row[1] != '--' else 0
                
                result.append([date, open_p, high, low, close, volume])
            except (ValueError, IndexError):
                continue
        return result

    @staticmethod
    def _fetch_tpex(url, stock_id):
        """抓 TPEX 上櫃股票"""
        r = requests.get(url, headers=HEADERS, timeout=10)
        data = r.json()
        result = []
        for row in data.get("aaData", []):
            try:
                date_str = row[0].replace('/', '-')
                parts = date_str.split('-')
                year = int(parts[0]) + 1911
                date = f"{year}-{parts[1]}-{parts[2]}"
                
                open_p = float(row[3].replace(',', ''))
                high = float(row[4].replace(',', ''))
                low = float(row[5].replace(',', ''))
                close = float(row[6].replace(',', ''))
                volume = int(row[7].replace(',', '')) if row[7] else 0
                
                result.append([date, open_p, high, low, close, volume])
            except (ValueError, IndexError):
                continue
        return result

    @staticmethod
    def _get_history_yfinance(ticker, days=180):
        """yfinance 備援方案"""
        import yfinance as yf
        period = f"{days}d" if days <= 60 else "1y"
        df = yf.Ticker(ticker).history(period=period)
        if df.empty:
            raise Exception("yfinance 無資料")
        return df

    # ========== 即時價格（TWSE MIS API）==========
    @staticmethod
    def is_market_open():
        now = datetime.now()
        if now.weekday() >= 5:
            return False
        start = now.replace(hour=9, minute=0, second=0)
        end = now.replace(hour=13, minute=30, second=0)
        return start <= now <= end

    @staticmethod
    def get_realtime_price(ticker):
        try:
            stock_id = ticker.split('.')[0]
            market = "otc" if ticker.upper().endswith('.TWO') else "tse"
            url = f"https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch={market}_{stock_id}.tw"
            r = requests.get(url, timeout=5, headers=HEADERS)
            data = r.json()
            if data.get("msgArray"):
                z = data["msgArray"][0].get("z", "-")
                if z != "-":
                    return float(z)
                # 若 z 沒值，試試昨收
                y = data["msgArray"][0].get("y", "-")
                if y != "-":
                    return float(y)
        except Exception as e:
            print(f"[Realtime] 失敗 {ticker}: {e}")
        return None

    # ========== 匯率狀態 ==========
    @staticmethod
    def get_fx_status():
        try:
            # 改用台銀匯率 API（更穩定）
            url = "https://rate.bot.com.tw/xrt/flcsv/0/day"
            r = requests.get(url, timeout=10, headers=HEADERS)
            lines = r.text.strip().split('\n')
            if len(lines) < 2:
                return 0, "無匯率數據"
            # 簡化版：只判斷美元
            for line in lines[1:]:
                parts = line.split(',')
                if parts[0] == 'USD':
                    rate = float(parts[2])  # 即期買入
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
            # 試過去 5 天，找到有資料的那天
            for i in range(5):
                date = (datetime.now() - timedelta(days=i)).strftime("%Y%m%d")
                url = f"https://www.twse.com.tw/rwd/zh/fund/T86?date={date}&selectType=ALL&response=json"
                r = requests.get(url, timeout=10, headers=HEADERS)
                data = r.json()
                if data.get("stat") == "OK" and data.get("data"):
                    result = {}
                    for row in data.get("data", []):
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

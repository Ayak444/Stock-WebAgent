"""技術指標計算"""
import pandas as pd
import numpy as np


class TechnicalAnalyzer:
    @staticmethod
    def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
        """計算 MA / RSI / MACD / KD / 布林通道"""
        if df.empty or len(df) < 20:
            return df

        df = df.copy()
        close = df['Close']

        # 均線
        df['MA5'] = close.rolling(5).mean()
        df['MA20'] = close.rolling(20).mean()
        df['MA60'] = close.rolling(60).mean()

        # RSI (14)
        delta = close.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        rsi = rsi.mask((avg_loss == 0) & (avg_gain > 0), 100)
        rsi = rsi.mask((avg_loss == 0) & (avg_gain == 0), 50)
        df['RSI'] = rsi

        # MACD
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        df['MACD'] = ema12 - ema26
        df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
        df['Histogram'] = df['MACD'] - df['Signal']

        # 布林通道
        std20 = close.rolling(20).std()
        df['BB_upper'] = df['MA20'] + 2 * std20
        df['BB_lower'] = df['MA20'] - 2 * std20

        # KD
        low_min = df['Low'].rolling(9).min()
        high_max = df['High'].rolling(9).max()
        rsv = (close - low_min) / (high_max - low_min) * 100
        df['K'] = rsv.ewm(com=2, adjust=False).mean()
        df['D'] = df['K'].ewm(com=2, adjust=False).mean()

        # 成交量均線
        df['VolMA5'] = df['Volume'].rolling(5).mean()

        return df

    @staticmethod
    def get_signals(df: pd.DataFrame):
        """從最新資料抓取訊號"""
        if df.empty or len(df) < 2:
            return []

        signals = []
        last = df.iloc[-1]
        prev = df.iloc[-2]

        # 均線訊號
        if last['Close'] > last.get('MA20', 0):
            signals.append("✅ 站上 20 日均線")
        else:
            signals.append("⚠️ 跌破 20 日均線")

        # RSI
        rsi = last.get('RSI', 50)
        if not pd.isna(rsi):
            if rsi > 70:
                signals.append(f"⚠️ RSI 超買 ({rsi:.1f})")
            elif rsi < 30:
                signals.append(f"✅ RSI 超賣 ({rsi:.1f})")

        # MACD 交叉
        if not pd.isna(last.get('MACD')) and not pd.isna(prev.get('MACD')):
            if prev['MACD'] < prev['Signal'] and last['MACD'] > last['Signal']:
                signals.append("🚀 MACD 黃金交叉")
            elif prev['MACD'] > prev['Signal'] and last['MACD'] < last['Signal']:
                signals.append("📉 MACD 死亡交叉")

        # 成交量
        if not pd.isna(last.get('VolMA5')) and last['VolMA5'] > 0:
            if last['Volume'] > last['VolMA5'] * 1.5:
                signals.append("🔥 爆量")

        return signals

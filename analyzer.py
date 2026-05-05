import pandas as pd
import numpy as np
import math

class TechnicalAnalyzer:
    @staticmethod
    def calculate_indicators(df):
        c, v = df['Close'], df['Volume']
        df['MA5'], df['MA20'], df['MA60'] = c.rolling(5).mean(), c.rolling(20).mean(), c.rolling(60).mean()
        df['MA20_Slope'], df['VMA5'] = df['MA20'].diff(), v.rolling(5).mean()
        delta = c.diff()
        g, l = delta.where(delta > 0, 0).rolling(14).mean(), (-delta.where(delta < 0, 0)).rolling(14).mean()
        df['RSI'] = 100 - (100 / (1 + g/l))
        low, high = df['Low'].rolling(9).min(), df['High'].rolling(9).max()
        rsv = (c - low) / (high - low) * 100
        k_l, d_l, k, d = [], [], 50, 50
        for r in rsv:
            if np.isnan(r): k_l.append(np.nan); d_l.append(np.nan)
            else: k = (2/3)*k + (1/3)*r; d = (2/3)*d + (1/3)*k; k_l.append(k); d_l.append(d)
        df['K'], df['D'] = k_l, d_l
        return TechnicalAnalyzer.identify_patterns(df)

    @staticmethod
    def identify_patterns(df):
        o, c, h, l = df['Open'], df['Close'], df['High'], df['Low']
        body = abs(c - o)
        patterns = [None, None]
        for i in range(2, len(df)):
            sig = []
            if (l.iloc[i] - min(o.iloc[i], c.iloc[i])) > body.iloc[i]*2: sig.append("錘子線")
            if c.iloc[i-1] < o.iloc[i-1] and c.iloc[i] > o.iloc[i] and c.iloc[i] > (c.iloc[i-1] + (o.iloc[i-1]-c.iloc[i-1])/2): sig.append("刺透")
            if c.iloc[i-1] < o.iloc[i-1] and c.iloc[i] > o.iloc[i] and c.iloc[i] > o.iloc[i-1] and o.iloc[i] < c.iloc[i-1]: sig.append("吞噬")
            patterns.append(",".join(sig) if sig else None)
        df['Pattern'] = patterns
        return df

    @staticmethod
    def get_valuation(stock_obj, df, price):
        try:
            yh = df['High'].tail(250).max()
            yl = df['Low'].tail(250).min()
            
            if pd.isna(yh) or pd.isna(yl) or pd.isna(price) or yh == yl:
                return "無法計算位階"
                
            raw_pct = ((price - yl) / (yh - yl)) * 100
            
            if math.isnan(raw_pct) or math.isinf(raw_pct):
                return "無法計算位階"
                
            pct = int(raw_pct)
            status = "便宜" if pct < 20 else "昂貴" if pct > 80 else "合理"
            
            return f"{status} ({pct}%)"
                
        except Exception as e:
            return "數據缺失"

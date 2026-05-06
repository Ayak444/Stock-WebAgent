# 回測引擎：策略 vs Buy & Hold
import yfinance as yf
import pandas as pd
import numpy as np
from analyzer import TechnicalAnalyzer

class Backtester:
    @staticmethod
    def run(ticker, days=365, initial_capital=100000):
        """
        執行回測，比較策略 vs Buy & Hold
        - 策略：訊號評分 >= 3 買進，< 0 賣出 （簡化版 StrategyEngine）
        - Buy & Hold：第一天買進持有到最後
        """
        try:
            period = f"{max(days+90, 400)}d"  # 多抓一些以計算指標
            df = yf.Ticker(ticker).history(period=period)
            if df.empty or len(df) < 60:
                return {"status": "error", "message": "資料不足"}
            
            df = TechnicalAnalyzer.calculate_indicators(df)
            df = df.dropna().tail(days).reset_index()
            if len(df) < 30:
                return {"status": "error", "message": "有效資料不足"}
            
            # ========== Buy & Hold ==========
            bh_entry = df['Close'].iloc[0]
            bh_shares = initial_capital / bh_entry
            df['BH_Value'] = df['Close'] * bh_shares
            
            # ========== 策略回測 ==========
            cash = initial_capital
            shares = 0
            trades = []
            strategy_values = []
            
            for i in range(len(df)):
                row = df.iloc[i]
                price = row['Close']
                score = Backtester._calc_score(df, i)
                
                # 決策
                if shares == 0 and score >= 3:  # 進場
                    shares = cash / price
                    cash = 0
                    trades.append({
                        "date": str(row['Date'])[:10] if 'Date' in df.columns else str(i),
                        "action": "買進", "price": round(price, 2), "score": score
                    })
                elif shares > 0 and score <= -2:  # 出場
                    cash = shares * price
                    trades.append({
                        "date": str(row['Date'])[:10] if 'Date' in df.columns else str(i),
                        "action": "賣出", "price": round(price, 2), "score": score
                    })
                    shares = 0
                
                strategy_values.append(cash + shares * price)
            
            df['Strategy_Value'] = strategy_values
            
            # ========== 統計 ==========
            final_strategy = strategy_values[-1]
            final_bh = float(df['BH_Value'].iloc[-1])
            
            strategy_return = (final_strategy - initial_capital) / initial_capital * 100
            bh_return = (final_bh - initial_capital) / initial_capital * 100
            
            # 最大回撤
            def max_drawdown(values):
                peak = values[0]
                mdd = 0
                for v in values:
                    if v > peak: peak = v
                    dd = (peak - v) / peak * 100
                    if dd > mdd: mdd = dd
                return round(mdd, 2)
            
            # 時間序列（前端繪圖用）
            dates = [str(d)[:10] for d in df['Date']] if 'Date' in df.columns else list(range(len(df)))
            
            return {
                "status": "success",
                "ticker": ticker,
                "period_days": len(df),
                "initial_capital": initial_capital,
                "strategy": {
                    "final_value": round(final_strategy, 2),
                    "return_pct": round(strategy_return, 2),
                    "trade_count": len(trades),
                    "max_drawdown": max_drawdown(strategy_values),
                    "trades": trades[-20:]  # 最後 20 筆
                },
                "buy_hold": {
                    "final_value": round(final_bh, 2),
                    "return_pct": round(bh_return, 2),
                    "max_drawdown": max_drawdown(df['BH_Value'].tolist())
                },
                "winner": "策略" if strategy_return > bh_return else "Buy & Hold",
                "chart": {
                    "dates": dates,
                    "strategy": [round(v, 2) for v in strategy_values],
                    "buy_hold": [round(v, 2) for v in df['BH_Value'].tolist()],
                    "price": [round(v, 2) for v in df['Close'].tolist()]
                }
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    @staticmethod
    def _calc_score(df, i):
        """簡化版評分（用於回測）"""
        if i < 2: return 0
        row = df.iloc[i]
        prev = df.iloc[i-1]
        score = 0
        
        if row['Close'] < row['MA5']: score -= 2
        if row['Close'] < row['MA20']: score -= 3
        if row['Close'] > row['MA5'] > row['MA20']: score += 3
        
        pattern = str(row.get('Pattern', '')) if row.get('Pattern') is not None else ''
        if pattern and pattern != 'nan':
            score += 4 if '吞噬' in pattern else 2
        
        # 量價齊揚
        if row['Close'] > prev['Close'] and row['Volume'] > row.get('VMA5', 0) * 1.2:
            score += 2
        
        # RSI 極值
        rsi = row.get('RSI', 50)
        if not pd.isna(rsi):
            if rsi < 30: score += 1
            elif rsi > 75: score -= 1
        
        return score

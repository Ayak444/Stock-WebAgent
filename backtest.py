"""策略回測：策略 vs Buy & Hold"""
from data_provider import DataProvider
from analyzer import TechnicalAnalyzer


class Backtester:
    @staticmethod
    def run(ticker: str, days: int = 180):
        df = DataProvider.get_stock_history(ticker, days)
        if df.empty or len(df) < 30:
            return {"status": "error", "message": "資料不足"}

        df = TechnicalAnalyzer.calculate_indicators(df).dropna()
        if df.empty:
            return {"status": "error", "message": "計算指標後無資料"}

        cash = 100000
        shares = 0
        trades = []
        portfolio_value = []
        peak_value = 100000
        max_drawdown = 0
        winning_trades = 0
        total_closed_trades = 0
        latest_signal = "NEUTRAL"

        for i in range(len(df)):
            row = df.iloc[i]
            price = row['Close']

            # 策略：MA20 上穿 + RSI < 70 買進；MA20 下穿 or RSI > 75 賣出
            if i > 0:
                prev = df.iloc[i-1]
                # 黃金交叉 + RSI 健康
                if (prev['Close'] < prev['MA20'] and price > row['MA20']
                        and row['RSI'] < 70 and cash > price):
                    buy_shares = int(cash // price)
                    if buy_shares > 0:
                        cash -= buy_shares * price
                        shares += buy_shares
                        trades.append({
                            "date": str(row.name.date()),
                            "action": "BUY", "price": round(price, 2),
                            "shares": buy_shares,
                            "return_pct": 0
                        })
                        last_buy_price = price
                # 死亡交叉 or RSI 過熱
                elif ((prev['Close'] > prev['MA20'] and price < row['MA20']) or
                      row['RSI'] > 75) and shares > 0:
                    cash += shares * price
                    ret_pct = ((price / last_buy_price) - 1) * 100 if 'last_buy_price' in locals() and last_buy_price > 0 else 0
                    
                    total_closed_trades += 1
                    if ret_pct > 0:
                        winning_trades += 1
                        
                    trades.append({
                        "date": str(row.name.date()),
                        "action": "SELL", "price": round(price, 2),
                        "shares": shares,
                        "return_pct": round(ret_pct, 2)
                    })
                    shares = 0

            # Calculate current portfolio value and drawdown
            current_value = cash + shares * price
            portfolio_value.append(current_value)
            
            if current_value > peak_value:
                peak_value = current_value
            
            drawdown = (peak_value - current_value) / peak_value * 100
            if drawdown > max_drawdown:
                max_drawdown = drawdown
                
        # Determine latest signal
        if len(df) > 1:
            last_row = df.iloc[-1]
            prev_row = df.iloc[-2]
            if prev_row['Close'] < prev_row['MA20'] and last_row['Close'] > last_row['MA20'] and last_row['RSI'] < 70:
                latest_signal = "BUY"
            elif (prev_row['Close'] > prev_row['MA20'] and last_row['Close'] < last_row['MA20']) or last_row['RSI'] > 75:
                latest_signal = "SELL"

        # 最終清算
        final_price = df.iloc[-1]['Close']
        final_value = cash + shares * final_price
        strategy_return = (final_value / 100000 - 1) * 100

        # Buy & Hold
        bh_shares = 100000 // df.iloc[0]['Close']
        bh_final = bh_shares * final_price + (100000 - bh_shares * df.iloc[0]['Close'])
        bh_return = (bh_final / 100000 - 1) * 100

        win_rate = (winning_trades / total_closed_trades * 100) if total_closed_trades > 0 else 0

        return {
            "status": "success",
            "ticker": ticker,
            "days": days,
            "strategy_return": round(strategy_return, 2),
            "buy_hold_return": round(bh_return, 2),
            "outperformance": round(strategy_return - bh_return, 2),
            "trade_count": len(trades),
            "final_value": round(final_value, 0),
            "win_rate": round(win_rate, 2),
            "max_drawdown": round(max_drawdown, 2),
            "latest_signal": latest_signal,
            "trades": trades[-10:]  # 最近 10 筆
        }

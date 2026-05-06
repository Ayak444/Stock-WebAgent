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
                            "type": "BUY", "price": round(price, 2),
                            "shares": buy_shares
                        })
                # 死亡交叉 or RSI 過熱
                elif ((prev['Close'] > prev['MA20'] and price < row['MA20']) or
                      row['RSI'] > 75) and shares > 0:
                    cash += shares * price
                    trades.append({
                        "date": str(row.name.date()),
                        "type": "SELL", "price": round(price, 2),
                        "shares": shares
                    })
                    shares = 0

            portfolio_value.append(cash + shares * price)

        # 最終清算
        final_price = df.iloc[-1]['Close']
        final_value = cash + shares * final_price
        strategy_return = (final_value / 100000 - 1) * 100

        # Buy & Hold
        bh_shares = 100000 // df.iloc[0]['Close']
        bh_final = bh_shares * final_price + (100000 - bh_shares * df.iloc[0]['Close'])
        bh_return = (bh_final / 100000 - 1) * 100

        return {
            "status": "success",
            "ticker": ticker,
            "days": days,
            "strategy_return": round(strategy_return, 2),
            "buyhold_return": round(bh_return, 2),
            "outperform": round(strategy_return - bh_return, 2),
            "total_trades": len(trades),
            "final_value": round(final_value, 0),
            "trades": trades[-10:]  # 最近 10 筆
        }

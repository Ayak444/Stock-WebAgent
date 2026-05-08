"""投資策略決策引擎"""
import pandas as pd
from analyzer import TechnicalAnalyzer


class StrategyEngine:
    @staticmethod
    def evaluate(ticker: str, df: pd.DataFrame, chip: dict = None,
                 fx_status: int = 0, cost: float = 0, shares: int = 0):
        """
        綜合評估股票
        回傳: {score, advice, signals, exit_note, stop_loss, valuation, pl_percent}
        """
        if df.empty or len(df) < 20:
            return {
                "score": 0, "advice": "資料不足", "signals": ["無法取得歷史資料"],
                "exit_note": "-", "stop_loss": 0, "valuation": "無數據", "pl_percent": 0
            }

        df = TechnicalAnalyzer.calculate_indicators(df)
        last = df.iloc[-1]
        price = float(last['Close'])

        score = 50  # 基礎分
        signals = TechnicalAnalyzer.get_signals(df)

        # 技術分析加減分
        if price > last.get('MA20', price):
            score += 10
        else:
            score -= 10

        if price > last.get('MA60', price):
            score += 5

        rsi = last.get('RSI', 50)
        if not pd.isna(rsi):
            if rsi > 70:
                score -= 15
            elif rsi < 30:
                score += 15

        if last.get('MACD', 0) > last.get('Signal', 0):
            score += 10
        else:
            score -= 5

        # 籌碼面
        if chip:
            stock_id = ticker.split('.')[0]
            if stock_id in chip:
                foreign = chip[stock_id].get('Foreign', 0)
                trust = chip[stock_id].get('Trust', 0)
                if foreign > 1000000:
                    score += 10
                    signals.append(f"💰 外資買超 {foreign/1000:.0f}張")
                elif foreign < -1000000:
                    score -= 10
                    signals.append(f"💸 外資賣超 {abs(foreign)/1000:.0f}張")
                if trust > 500000:
                    score += 5
                    signals.append(f"📈 投信買超")

        # 匯率影響（出口股）
        if fx_status == -1:  # 台幣升值
            score -= 3
        elif fx_status == 1:
            score += 3

        # 評分上下限
        score = max(0, min(100, score))

        # 決策建議
        if score >= 75:
            advice = "強力買進"
        elif score >= 60:
            advice = "偏多"
        elif score >= 40:
            advice = "觀察"
        elif score >= 25:
            advice = "避險"
        else:
            advice = "鎖倉"

        # 停損點
        stop_loss = round(price * 0.93, 2)  # -7%
        exit_note = f"跌破 {stop_loss} 建議停損"

        # 估值
        ma60 = last.get('MA60', price)
        if not pd.isna(ma60) and ma60 > 0:
            premium = (price / ma60 - 1) * 100
            if premium > 15:
                valuation = f"偏高 (+{premium:.1f}%)"
            elif premium < -10:
                valuation = f"偏低 ({premium:.1f}%)"
            else:
                valuation = f"合理 ({premium:+.1f}%)"
        else:
            valuation = "無數據"

        # 損益
        pl_percent = round((price - cost) / cost * 100, 2) if cost > 0 else 0

        return {
            "score": score,
            "advice": advice,
            "signals": signals,
            "exit_note": exit_note,
            "stop_loss": stop_loss,
            "valuation": valuation,
            "pl_percent": pl_percent,
            "price": price
        }

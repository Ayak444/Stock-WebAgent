#主程式
from fastapi import FastAPI
import uvicorn
import os
from models import StockTarget
from data_provider import MarketDataProvider
from analyzer import TechnicalAnalyzer
from strategy import StrategyEngine
from notifier import TelegramNotifier
from keep_alive import keep_alive

app = FastAPI()
notifier = TelegramNotifier()

def get_targets():
    return [
        StockTarget("0050.TW", "元大台灣50", "ETF", 76.18, 250),
        StockTarget("00631L.TW", "正2", "ETF", 537.0, 10),
        StockTarget("2308.TW", "台達電", "STOCK", 0, 0),
        StockTarget("2368.TW", "金像電", "STOCK", 0, 0)
    ]

@app.get("/report")
def generate_report():
    try:
        targets = get_targets()
        chip_data, _ = MarketDataProvider.get_chip_data()
        market_df, fx_val, fx_note = MarketDataProvider.get_market_context()
        
        results = []
        for t in targets:
            df, obj = MarketDataProvider.get_stock_history(t.id)
            if df is None: continue
            price = MarketDataProvider.get_realtime_price(t.id)
            if price: df.iloc[-1, df.columns.get_loc('Close')] = price
            
            df = TechnicalAnalyzer.calculate_indicators(df)
            
            # 這裡最容易出錯，請確保名稱與 analyzer.py 一致
            advice, sigs, score, pl = StrategyEngine.evaluate(df, t, chip_data, market_df, fx_val)
            sl, note = StrategyEngine.get_exit_point(df, t.cost)
            
            # 請檢查你的 analyzer.py 裡到底是叫 get_valuation 還是 analyze_valuation
            # 如果還是報錯，可以先暫時註解掉這一行測試
            val = TechnicalAnalyzer.analyze_valuation(obj, df, df['Close'].iloc[-1])
            
            results.append({
                "name": t.name, "ticker": t.id, "price": float(df['Close'].iloc[-1]),
                "score": score, "advice": advice, "pl": round(pl, 2),
                "valuation": val, "signals": sigs, "exit": note, "sl": round(sl, 1)
            })
        return {"status": "success", "data": results, "fx": fx_note}
        
    except Exception as e:
        # 如果出錯，會直接在瀏覽器顯示錯誤原因
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)

from fastapi import FastAPI
from pydantic import BaseModel
from typing import List
import uvicorn
import os
from models import StockTarget
from data_provider import MarketDataProvider
from analyzer import TechnicalAnalyzer
from strategy import StrategyEngine
from notifier import TelegramNotifier

app = FastAPI()
notifier = TelegramNotifier()

class TargetItem(BaseModel):
    id: str
    name: str
    type: str
    cost: float
    shares: int

# --- 新增這個端點來取代原本的 keep_alive ---
@app.get("/")
def home():
    return {"status": "Bot is alive and running!"}
# ----------------------------------------

@app.post("/analyze")
def analyze_custom(targets: List[TargetItem]):
    chip_data, _ = MarketDataProvider.get_chip_data()
    market_df, fx_val, fx_note = MarketDataProvider.get_market_context()
    
    results = []
    for t_item in targets:
        t = StockTarget(t_item.id, t_item.name, t_item.type, t_item.cost, t_item.shares)
        df, obj = MarketDataProvider.get_stock_history(t.id)
        if df is None: continue
        price = MarketDataProvider.get_realtime_price(t.id)
        if price: df.iloc[-1, df.columns.get_loc('Close')] = price
        
        df = TechnicalAnalyzer.calculate_indicators(df)
        advice, sigs, score, pl = StrategyEngine.evaluate(df, t, chip_data, market_df, fx_val)
        sl, note = StrategyEngine.get_exit_point(df, t.cost)
        val = TechnicalAnalyzer.get_valuation(obj, df, df['Close'].iloc[-1]) # 注意這裡改叫 get_valuation
        
        results.append({
            "name": t.name, "ticker": t.id, "price": float(df['Close'].iloc[-1]),
            "score": score, "advice": advice, "pl": round(pl, 2),
            "valuation": val, "signals": sigs, "exit": note, "sl": round(sl, 1)
        })
    return {"status": "success", "data": results, "fx": fx_note}

if __name__ == "__main__":
    # Render 會自動提供 PORT 環境變數，如果沒有才退回使用 8080
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)

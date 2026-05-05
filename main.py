import os
from typing import List
import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel
import google.generativeai as genai
from models import StockTarget
from data_provider import MarketDataProvider
from analyzer import TechnicalAnalyzer
from strategy import StrategyEngine
from notifier import TelegramNotifier

app = FastAPI()
notifier = TelegramNotifier()

genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
model = genai.GenerativeModel('gemini-2.5-flash')

class TargetItem(BaseModel):
    id: str
    name: str
    type: str
    cost: float
    shares: int

class ChatRequest(BaseModel):
    message: str

class NewsRequest(BaseModel):
    news_content: str

@app.get("/")
def home():
    return {"status": "Bot is alive and running!"}

@app.post("/chat")
def handle_chat(req: ChatRequest):
    system_prompt = "你是一位專業的台灣股市投資助理。請用簡明扼要、客觀的語氣回答使用者的問題。請勿提供絕對的投資建議。"
    full_prompt = f"{system_prompt}\n\n使用者問題：{req.message}"
    
    try:
        response = model.generate_content(full_prompt)
        return {"status": "success", "reply": response.text}
    except Exception as e:
        return {"status": "error", "reply": "AI 目前無法回應，請稍後再試。"}

@app.post("/analyze_news")
def analyze_business_news(req: NewsRequest):
    analysis_prompt = f"""
    請閱讀以下財經新聞，並嚴格按照以下 JSON 格式回傳分析結果，不要加入任何其他文字：
    {{
        "summary": "一句話總結新聞核心",
        "sentiment": "利多 / 利空 / 中立",
        "impact_stocks": ["股票代號1", "股票代號2"],
        "reasoning": "簡述判斷原因"
    }}
    
    新聞內容：
    {req.news_content}
    """
    
    try:
        response = model.generate_content(analysis_prompt)
        return {"status": "success", "analysis": response.text}
    except Exception as e:
        return {"status": "error"}

@app.post("/analyze")
def analyze_custom(targets: List[TargetItem]):
    chip_data, _ = MarketDataProvider.get_chip_data()
    market_df, fx_val, fx_note = MarketDataProvider.get_market_context()
    
    results = []
    for t_item in targets:
        t = StockTarget(t_item.id, t_item.name, t_item.type, t_item.cost, t_item.shares)
        
        try:
            df, obj = MarketDataProvider.get_stock_history(t.id)
            
            if df is None or df.empty:
                results.append({
                    "name": t.name, "ticker": t.id, "price": 0.0,
                    "score": 0, "advice": "資料讀取失敗", "pl": 0.0,
                    "valuation": "無數據", "signals": ["API無回應或代號錯誤"], "exit": "-", "sl": 0.0
                })
                continue
                
            price = MarketDataProvider.get_realtime_price(t.id)
            if price: 
                df.iloc[-1, df.columns.get_loc('Close')] = price
            
            df = TechnicalAnalyzer.calculate_indicators(df)
            advice, sigs, score, pl = StrategyEngine.evaluate(df, t, chip_data, market_df, fx_val)
            sl, note = StrategyEngine.get_exit_point(df, t.cost)
            val = TechnicalAnalyzer.get_valuation(obj, df, df['Close'].iloc[-1])
            
            results.append({
                "name": t.name, "ticker": t.id, "price": float(df['Close'].iloc[-1]),
                "score": score, "advice": advice, "pl": round(pl, 2),
                "valuation": val, "signals": sigs, "exit": note, "sl": round(sl, 1)
            })
        except Exception as e:
            results.append({
                "name": t.name, "ticker": t.id, "price": 0.0,
                "score": 0, "advice": "運算錯誤", "pl": 0.0,
                "valuation": "無數據", "signals": ["系統發生例外狀況"], "exit": "-", "sl": 0.0
            })
            print(f"Error analyzing {t.id}: {e}")
            
    return {"status": "success", "data": results, "fx": fx_note}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)

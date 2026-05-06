import os
import time
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
        return {"status": "error", "reply": f"AI 模型錯誤: {str(e)}"}

@app.get("/auto_news")
def get_auto_news():
    try:
        import yfinance as yf
        
        vix_df = yf.Ticker("^VIX").history(period="1d")
        vix_current = round(vix_df['Close'].iloc[-1], 2) if not vix_df.empty else "無數據"
        
        ticker = yf.Ticker("0050.TW")
        news_list = ticker.news
        
        news_text = "目前無最新新聞。"
        if news_list:
            news_text = "\n".join([f"標題: {n.get('title', '')} (來源: {n.get('publisher', '')})" for n in news_list[:5]])
            
        analysis_prompt = f"""
        請閱讀以下台灣股市最新新聞與當前全球恐慌指數(VIX)，並嚴格按照以下 JSON 格式回傳分析結果，不要加入任何其他文字：
        {{
            "summary": "一句話總結新聞與市場氛圍",
            "sentiment": "利多 / 利空 / 中立",
            "vix_analysis": "針對當前 VIX 指數的簡短解讀",
            "impact_stocks": ["股票代號1", "股票代號2"],
            "reasoning": "簡述判斷原因"
        }}
        
        當前恐慌指數 (VIX): {vix_current}
        
        新聞內容：
        {news_text}
        """
        response = model.generate_content(analysis_prompt)
        return {"status": "success", "analysis": response.text}
    except Exception as e:
        return {"status": "error", "analysis": f"伺服器錯誤: {str(e)}"}

@app.post("/analyze")
def analyze_custom(targets: List[TargetItem]):
    chip_data, _ = MarketDataProvider.get_chip_data()
    market_df, fx_val, fx_note = MarketDataProvider.get_market_context()
    
    results = []
    for t_item in targets:
        time.sleep(0.5)
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
            
    return {"status": "success", "data": results, "fx": fx_note}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)

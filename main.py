# FastAPI 主程式
import os
import uvicorn
import google.generativeai as genai
import yfinance as yf
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from apscheduler.schedulers.background import BackgroundScheduler
from contextlib import asynccontextmanager

from models import (
    StockTarget, TargetItem, AnalyzeRequest,
    NewsRequest, ChatRequest, BacktestRequest
)
from analyzer import TechnicalAnalyzer
from data_provider import MarketDataProvider
from strategy import StrategyEngine
from notifier import TelegramNotifier
from backtest import Backtester
import database as db

# ========== Gemini ==========
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-2.5-flash')
else:
    model = None

notifier = TelegramNotifier()

# ========== 排程工作：每日自動分析 ==========
def daily_auto_analysis():
    """每個交易日下午 2 點執行（台股收盤後）"""
    print("[排程] 執行每日自動分析...")
    try:
        default_targets = [
            StockTarget("2330.TW", "台積電", "STOCK", 0, 0),
            StockTarget("0050.TW", "元大台灣50", "ETF", 0, 0),
            StockTarget("2454.TW", "聯發科", "STOCK", 0, 0),
        ]
        results = _analyze_targets(default_targets)
        db.save_analysis(results)
        
        msg = "📊 <b>每日自動分析</b>\n\n"
        for r in results:
            msg += f"• <b>{r['name']}</b> ({r['ticker']}): {r['advice']} | 評分 {r['score']}\n"
        notifier.send(msg)
    except Exception as e:
        print(f"[排程] 錯誤: {e}")

scheduler = BackgroundScheduler(timezone="Asia/Taipei")

@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    scheduler.add_job(daily_auto_analysis, 'cron', day_of_week='mon-fri', hour=14, minute=0)
    scheduler.start()
    print("✅ 服務啟動完成")
    yield
    scheduler.shutdown()

# ========== FastAPI ==========
app = FastAPI(title="台股智能分析 API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ========== 核心分析函數 ==========
def _analyze_targets(targets):
    fx_val, fx_note = MarketDataProvider.get_fx_status() if hasattr(MarketDataProvider, 'get_fx_status') else (0, "")
    chip_data = MarketDataProvider.get_chip_data() if hasattr(MarketDataProvider, 'get_chip_data') else {}
    market_df = None
    
    results = []
    for t in targets:
        try:
            obj = yf.Ticker(t.id)
            df = obj.history(period="1y")
            if df.empty:
                results.append({
                    "name": t.name, "ticker": t.id, "price": 0.0,
                    "score": 0, "advice": "資料讀取失敗", "pl": 0.0,
                    "valuation": "無數據", "signals": ["無法取得歷史資料"],
                    "exit": "-", "sl": 0
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
                "valuation": "無數據", "signals": [f"例外: {str(e)[:50]}"],
                "exit": "-", "sl": 0
            })
    return results

# ========== API Endpoints ==========
@app.get("/")
def root():
    return FileResponse("static/index.html")

@app.get("/health")
def health():
    return {"status": "ok", "gemini": model is not None}

@app.post("/analyze")
def analyze(req: AnalyzeRequest):
    targets = [StockTarget(t.id, t.name, t.type, t.cost, t.shares) for t in req.targets]
    results = _analyze_targets(targets)
    db.save_analysis(results)  # 自動存歷史
    return {"status": "success", "data": results, "fx": ""}

@app.post("/analyze_news")
def analyze_business_news(req: NewsRequest):
    if not model:
        return {"status": "error", "message": "Gemini 未設定"}
    prompt = f"""
請閱讀以下財經新聞，嚴格按照 JSON 格式回傳（純 JSON，勿加其他文字）：
{{
  "summary": "一句話總結",
  "sentiment": "利多 / 利空 / 中立",
  "impact_stocks": ["代號1", "代號2"],
  "reasoning": "判斷原因"
}}

新聞內容：
{req.news_content}
"""
    try:
        response = model.generate_content(prompt)
        return {"status": "success", "analysis": response.text}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/chat")
def chat(req: ChatRequest):
    if not model:
        return {"status": "error", "message": "Gemini 未設定"}
    try:
        prompt = f"你是專業的台股投資助理，請用繁體中文回答。\n\n使用者問題：{req.message}"
        response = model.generate_content(prompt)
        return {"status": "success", "reply": response.text}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/auto_news")
def auto_news():
    if not model:
        return {"status": "error", "message": "Gemini 未設定"}
    try:
        prompt = "請提供今日台股最重要的 3 則財經新聞摘要，並分析對大盤影響。用繁體中文。"
        response = model.generate_content(prompt)
        return {"status": "success", "news": response.text}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# ========== 🆕 K 線資料 API ==========
@app.get("/kline/{ticker}")
def get_kline(ticker: str, days: int = 180):
    try:
        df = yf.Ticker(ticker).history(period=f"{days}d")
        if df.empty:
            raise HTTPException(404, "找不到資料")
        df = TechnicalAnalyzer.calculate_indicators(df).reset_index()
        
        candles = []
        volumes = []
        ma5, ma20, ma60 = [], [], []
        
        for _, row in df.iterrows():
            ts = int(row['Date'].timestamp()) if 'Date' in df.columns else 0
            candles.append({
                "time": ts,
                "open": round(float(row['Open']), 2),
                "high": round(float(row['High']), 2),
                "low": round(float(row['Low']), 2),
                "close": round(float(row['Close']), 2),
            })
            volumes.append({
                "time": ts,
                "value": float(row['Volume']),
                "color": "#26a69a" if row['Close'] >= row['Open'] else "#ef5350"
            })
            if not pd.isna(row.get('MA5')): ma5.append({"time": ts, "value": round(float(row['MA5']), 2)})
            if not pd.isna(row.get('MA20')): ma20.append({"time": ts, "value": round(float(row['MA20']), 2)})
            if not pd.isna(row.get('MA60')): ma60.append({"time": ts, "value": round(float(row['MA60']), 2)})
        
        return {
            "status": "success", "ticker": ticker,
            "candles": candles, "volumes": volumes,
            "ma5": ma5, "ma20": ma20, "ma60": ma60
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

# ========== 🆕 歷史紀錄 API ==========
@app.get("/history")
def history(ticker: str = None, limit: int = 100):
    data = db.get_history(ticker, limit)
    return {"status": "success", "data": data}

@app.get("/history/tickers")
def history_tickers():
    return {"status": "success", "data": db.get_all_tickers()}

# ========== 🆕 回測 API ==========
@app.post("/backtest")
def backtest(req: BacktestRequest):
    result = Backtester.run(req.ticker, req.days)
    return result

# ========== 靜態檔案 ==========
if os.path.isdir("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

import pandas as pd  # 用於 kline

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)

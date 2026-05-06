"""
FastAPI 主程式
整合：股票分析 + AI 對話 + 新聞爬蟲 + 利多利空分析
"""
import os
import json
import traceback
from datetime import datetime
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from models import (
    TargetItem, AnalyzeRequest, ChatRequest, NewsRequest,
    BacktestRequest, NewsSourceRequest, StockTarget
)
from data_provider import DataProvider
from analyzer import TechnicalAnalyzer
from strategy import StrategyEngine
from news_crawler import NewsCrawler
from database import Database
from backtest import Backtester
from notifier import EmailNotifier

# ========== Gemini 初始化 ==========
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
model = None

if GEMINI_KEY:
    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_KEY)
        # ⚠️ 使用 1.5 Flash（免費額度最寬鬆：15 RPM / 1500 RPD）
        model = genai.GenerativeModel('gemini-1.5-flash')
        print("✅ Gemini 1.5 Flash 已啟用")
    except Exception as e:
        print(f"❌ Gemini 初始化失敗: {e}")
        model = None
else:
    print("⚠️ GEMINI_API_KEY 未設定")


# ========== 排程任務 ==========
scheduler = None
try:
    from apscheduler.schedulers.background import BackgroundScheduler
    scheduler = BackgroundScheduler(timezone='Asia/Taipei')
except ImportError:
    print("⚠️ apscheduler 未安裝，排程功能停用")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if scheduler:
        scheduler.add_job(daily_analysis_task, 'cron', hour=14, minute=0, id='daily')
        scheduler.start()
        print("✅ 排程已啟動（每日 14:00 自動分析）")
    yield
    if scheduler:
        scheduler.shutdown()


app = FastAPI(title="台股智能分析 API", version="3.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

db = Database()
notifier = EmailNotifier()


# ========== 核心分析邏輯 ==========
def _analyze_targets(targets):
    """分析多檔股票"""
    chip = DataProvider.get_chip_data()
    fx_val, fx_note = DataProvider.get_fx_status()
    results = []

    for t in targets:
        try:
            df = DataProvider.get_stock_history(t.id, days=180)
            if df.empty:
                results.append({
                    "name": t.name, "ticker": t.id, "price": 0,
                    "score": 0, "advice": "資料讀取失敗", "pl": 0,
                    "valuation": "無數據", "signals": ["無法取得歷史資料"],
                    "exit": "-", "sl": 0
                })
                continue

            # 優先用即時價格，沒有就用歷史最新價
            rt_price = DataProvider.get_realtime_price(t.id)
            eval_result = StrategyEngine.evaluate(
                t.id, df, chip, fx_val, t.cost, t.shares
            )
            price = rt_price or eval_result['price']
            pl = round((price - t.cost) / t.cost * 100, 2) if t.cost > 0 else 0

            results.append({
                "name": t.name, "ticker": t.id,
                "price": round(price, 2), "score": eval_result['score'],
                "advice": eval_result['advice'], "pl": pl,
                "valuation": eval_result['valuation'],
                "signals": eval_result['signals'],
                "exit": eval_result['exit_note'],
                "sl": eval_result['stop_loss']
            })
        except Exception as e:
            traceback.print_exc()
            results.append({
                "name": t.name, "ticker": t.id, "price": 0,
                "score": 0, "advice": "運算錯誤", "pl": 0,
                "valuation": "無數據", "signals": [f"例外: {str(e)[:80]}"],
                "exit": "-", "sl": 0
            })

    return results, fx_note


def daily_analysis_task():
    """每日自動分析任務"""
    print(f"[Scheduler] 執行每日分析 {datetime.now()}")
    default_targets = [
        StockTarget("2330.TW", "台積電", "台股", 1000, 1000),
        StockTarget("0050.TW", "元大台灣50", "ETF", 180, 1000),
    ]
    results, _ = _analyze_targets(default_targets)
    db.save_analysis(results)
    html = notifier.format_analysis(results)
    notifier.send(f"📊 台股分析 {datetime.now().strftime('%Y-%m-%d')}", html)


# ========== API Endpoints ==========
@app.get("/")
def root():
    if os.path.exists("static/index.html"):
        return FileResponse("static/index.html")
    return {"status": "alive", "message": "API 運作中", "docs": "/docs"}


@app.get("/ping")
def ping():
    return {"status": "alive", "time": datetime.now().isoformat()}


@app.get("/health")
def health():
    return {
        "status": "ok",
        "gemini": model is not None,
        "email": notifier.enabled,
        "scheduler": scheduler is not None and scheduler.running if scheduler else False,
        "time": datetime.now().isoformat()
    }


@app.post("/analyze")
def analyze(req: AnalyzeRequest):
    targets = [StockTarget(t.id, t.name, t.type, t.cost, t.shares) for t in req.targets]
    results, fx_note = _analyze_targets(targets)
    db.save_analysis(results)
    return {"status": "success", "data": results, "fx": fx_note}


@app.post("/chat")
def chat(req: ChatRequest):
    if not model:
        return {"status": "error", "message": "Gemini 未設定 GEMINI_API_KEY"}
    try:
        prompt = f"""你是專業的台股投資助理，請用繁體中文簡明扼要回答。
使用者問題：{req.message}"""
        response = model.generate_content(prompt)
        return {"status": "success", "reply": response.text}
    except Exception as e:
        msg = str(e)
        if "429" in msg or "quota" in msg.lower():
            return {"status": "error", "message": "AI 請求過於頻繁，請稍等 30 秒再試"}
        return {"status": "error", "message": msg[:200]}


@app.post("/analyze_news")
def analyze_news(req: NewsRequest):
    """分析單篇新聞利多利空"""
    if not model:
        return {"status": "error", "message": "Gemini 未設定"}
    prompt = f"""請閱讀以下財經新聞，嚴格以 JSON 格式回傳（純 JSON，不要 markdown）：
{{
  "summary": "一句話總結（20字內）",
  "sentiment": "利多/利空/中立",
  "impact_level": "高/中/低",
  "impact_stocks": ["代號或產業1", "代號或產業2"],
  "reasoning": "判斷原因（50字內）"
}}

新聞：
{req.news_content[:2000]}"""
    try:
        response = model.generate_content(prompt)
        text = response.text.strip()
        # 移除可能的 markdown code block
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return {"status": "success", "analysis": text.strip()}
    except Exception as e:
        return {"status": "error", "message": str(e)[:200]}


# ========== 🆕 新聞爬蟲 API ==========
@app.get("/news")
def get_news(sources: str = "", limit: int = 5):
    """
    抓取新聞
    sources: 逗號分隔，例如 'bloomberg,investing,ctee,udn_money'
    """
    source_list = [s.strip() for s in sources.split(",") if s.strip()] if sources else None
    news = NewsCrawler.fetch_all(sources=source_list, limit_per_source=limit)
    return {"status": "success", "count": len(news), "data": news}


@app.post("/news/analyze_batch")
def analyze_news_batch(req: NewsSourceRequest):
    """一次抓取新聞並用 AI 分析利多利空"""
    if not model:
        return {"status": "error", "message": "Gemini 未設定，無法分析"}

    news_list = NewsCrawler.fetch_all(
        sources=req.sources, limit_per_source=req.limit
    )[:15]  # 最多 15 則避免超過 AI 限額

    if not news_list:
        return {"status": "error", "message": "沒有抓到新聞"}

    # 組合成一段文字讓 AI 一次判斷
    combined = "\n".join([
        f"{i+1}. [{n['source']}] {n['title']}"
        for i, n in enumerate(news_list)
    ])

    prompt = f"""你是專業財經分析師，請分析以下今日財經新聞，針對**每則**新聞回傳 JSON 陣列：
[
  {{"index": 1, "sentiment": "利多/利空/中立", "impact": "高/中/低", "reason": "簡短說明(30字內)"}},
  ...
]

只回傳 JSON 陣列，不要其他文字。

新聞列表：
{combined}"""

    try:
        response = model.generate_content(prompt)
        text = response.text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        text = text.strip()

        try:
            analysis = json.loads(text)
        except json.JSONDecodeError:
            analysis = []

        # 合併新聞與分析
        for i, item in enumerate(news_list):
            matched = next((a for a in analysis if a.get("index") == i+1), None)
            if matched:
                item['sentiment'] = matched.get('sentiment', '中立')
                item['impact'] = matched.get('impact', '低')
                item['ai_reason'] = matched.get('reason', '')
            else:
                item['sentiment'] = '中立'
                item['impact'] = '低'
                item['ai_reason'] = ''

            # 儲存進資料庫
            db.save_news_analysis({
                "source": item['source'],
                "title": item['title'],
                "sentiment": item['sentiment'],
                "summary": item.get('ai_reason', ''),
                "link": item.get('link', '')
            })

        # 統計
        stats = {
            "利多": sum(1 for n in news_list if n.get('sentiment') == '利多'),
            "利空": sum(1 for n in news_list if n.get('sentiment') == '利空'),
            "中立": sum(1 for n in news_list if n.get('sentiment') == '中立')
        }

        return {
            "status": "success",
            "count": len(news_list),
            "stats": stats,
            "data": news_list
        }
    except Exception as e:
        traceback.print_exc()
        return {"status": "error", "message": str(e)[:200]}


@app.get("/auto_news")
def auto_news():
    """今日重點新聞 AI 總結"""
    if not model:
        return {"status": "error", "message": "Gemini 未設定"}
    try:
        news = NewsCrawler.fetch_all(limit_per_source=3)[:10]
        if not news:
            return {"status": "error", "message": "無新聞資料"}

        titles = "\n".join([f"- [{n['source']}] {n['title']}" for n in news])
        prompt = f"""根據以下今日財經新聞標題，撰寫一份 200 字內的台股每日摘要，
包含：(1) 今日大盤氛圍 (2) 主要利多利空 (3) 操作建議。用繁體中文。

新聞：
{titles}"""

        response = model.generate_content(prompt)
        return {
            "status": "success",
            "summary": response.text,
            "news_count": len(news),
            "sources_used": list(set(n['source'] for n in news))
        }
    except Exception as e:
        return {"status": "error", "message": str(e)[:200]}


# ========== K 線 / 歷史 / 回測 ==========
@app.get("/kline/{ticker}")
def get_kline(ticker: str, days: int = 180):
    try:
        df = DataProvider.get_stock_history(ticker, days)
        if df.empty:
            return JSONResponse({"status": "error", "message": "找不到資料"}, status_code=404)

        df = TechnicalAnalyzer.calculate_indicators(df).reset_index()

        candles, volumes, ma5, ma20, ma60 = [], [], [], [], []
        date_col = 'Date' if 'Date' in df.columns else df.columns[0]

        for _, row in df.iterrows():
            import pandas as pd
            ts = int(row[date_col].timestamp()) if not pd.isna(row[date_col]) else 0
            candles.append({
                "time": ts,
                "open": round(float(row['Open']), 2),
                "high": round(float(row['High']), 2),
                "low": round(float(row['Low']), 2),
                "close": round(float(row['Close']), 2),
            })
            volumes.append({
                "time": ts, "value": float(row['Volume']),
                "color": "#26a69a" if row['Close'] >= row['Open'] else "#ef5350"
            })
            if not pd.isna(row.get('MA5')):
                ma5.append({"time": ts, "value": round(float(row['MA5']), 2)})
            if not pd.isna(row.get('MA20')):
                ma20.append({"time": ts, "value": round(float(row['MA20']), 2)})
            if not pd.isna(row.get('MA60')):
                ma60.append({"time": ts, "value": round(float(row['MA60']), 2)})

        return {
            "status": "success", "ticker": ticker,
            "candles": candles, "volumes": volumes,
            "ma5": ma5, "ma20": ma20, "ma60": ma60
        }
    except Exception as e:
        traceback.print_exc()
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@app.get("/history")
def history(ticker: str = None, limit: int = 100):
    return {"status": "success", "data": db.get_history(ticker, limit)}


@app.get("/history/tickers")
def history_tickers():
    return {"status": "success", "data": db.get_all_tickers()}


@app.post("/backtest")
def backtest(req: BacktestRequest):
    return Backtester.run(req.ticker, req.days)


# ========== 靜態檔案 ==========
if os.path.isdir("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)

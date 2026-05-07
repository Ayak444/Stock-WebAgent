import os
import json
import traceback
import requests as http_requests
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


# ============================================================
# MaiAgent API 設定（從 Render 環境變數讀取）
# ============================================================
MAIAGENT_API_KEY = os.environ.get("MAIAGENT_API_KEY", "")
MAIAGENT_CHATBOT_ID = os.environ.get("MAIAGENT_CHATBOT_ID", "")
MAIAGENT_WEBCHAT_ID = os.environ.get("MAIAGENT_WEBCHAT_ID", "")
MAIAGENT_BASE_URL = "https://api.maiagent.ai/api/v1"


class MaiAgentClient:
    """MaiAgent API 客戶端"""

    def __init__(self, api_key: str, chatbot_id: str, webchat_id: str):
        self.api_key = api_key
        self.chatbot_id = chatbot_id
        self.webchat_id = webchat_id
        self.base_url = MAIAGENT_BASE_URL
        self.headers = {
            "Authorization": f"Api-Key {self.api_key}",
            "Content-Type": "application/json"
        }
        self.enabled = bool(api_key and chatbot_id and webchat_id)

    def create_conversation(self) -> str:
        """建立新對話，回傳 conversation_id"""
        url = f"{self.base_url}/conversations/"
        payload = {"webChat": self.webchat_id}
        response = http_requests.post(url, headers=self.headers, json=payload)
        response.raise_for_status()
        data = response.json()
        return data.get("id", "")

    def send_message(self, content: str, conversation_id: str = None) -> str:
        """
        發送訊息給 MaiAgent AI 助理並取得同步回覆
        端點: POST /api/v1/chatbots/{chatbot_id}/completions
        """
        url = f"{self.base_url}/chatbots/{self.chatbot_id}/completions"
        payload = {
            "message": {
                "content": content
            }
        }

        # 如果有 conversation_id，延續對話
        if conversation_id:
            payload["conversation"] = conversation_id

        response = http_requests.post(
            url, headers=self.headers, json=payload, timeout=60
        )
        response.raise_for_status()
        data = response.json()

        # 根據 MaiAgent API 回傳格式取得回覆內容
        # 可能的回傳欄位: message.content, reply, content 等
        if isinstance(data, dict):
            # 嘗試多種可能的回傳格式
            if "message" in data and isinstance(data["message"], dict):
                return data["message"].get("content", str(data))
            elif "reply" in data:
                return data["reply"]
            elif "content" in data:
                return data["content"]
            elif "choices" in data:
                # 類 OpenAI 格式
                choices = data["choices"]
                if choices and isinstance(choices[0], dict):
                    msg = choices[0].get("message", {})
                    return msg.get("content", str(data))
            else:
                return str(data)
        return str(data)

    def chat(self, user_message: str, conversation_id: str = None) -> dict:
        """
        完整的聊天流程：建立對話（如需要）→ 發送訊息 → 回傳結果
        """
        try:
            # 如果沒有提供 conversation_id，建立新對話
            if not conversation_id:
                conversation_id = self.create_conversation()

            reply = self.send_message(user_message, conversation_id)
            return {
                "status": "success",
                "reply": reply,
                "conversation_id": conversation_id
            }
        except http_requests.exceptions.HTTPError as e:
            status_code = e.response.status_code if e.response else 0
            if status_code == 429:
                return {"status": "error", "message": "AI 請求過於頻繁，請稍等再試"}
            elif status_code == 401:
                return {"status": "error", "message": "API 金鑰無效，請檢查 MAIAGENT_API_KEY"}
            elif status_code == 404:
                return {"status": "error", "message": "找不到 Chatbot，請檢查 MAIAGENT_CHATBOT_ID"}
            else:
                return {"status": "error", "message": f"API 錯誤 ({status_code}): {str(e)[:200]}"}
        except http_requests.exceptions.Timeout:
            return {"status": "error", "message": "AI 回覆逾時，請稍後再試"}
        except Exception as e:
            return {"status": "error", "message": str(e)[:200]}


# 初始化 MaiAgent 客戶端
mai_client = MaiAgentClient(MAIAGENT_API_KEY, MAIAGENT_CHATBOT_ID, MAIAGENT_WEBCHAT_ID)

if mai_client.enabled:
    print("✅ MaiAgent API 已啟用")
    print(f"   Chatbot ID: {MAIAGENT_CHATBOT_ID[:8]}...")
else:
    missing = []
    if not MAIAGENT_API_KEY:
        missing.append("MAIAGENT_API_KEY")
    if not MAIAGENT_CHATBOT_ID:
        missing.append("MAIAGENT_CHATBOT_ID")
    if not MAIAGENT_WEBCHAT_ID:
        missing.append("MAIAGENT_WEBCHAT_ID")
    print(f"⚠️ MaiAgent 未完整設定，缺少: {', '.join(missing)}")


# ============================================================
# 排程器
# ============================================================
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


# ============================================================
# 核心分析邏輯
# ============================================================
def _analyze_targets(targets):
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
    print(f"[Scheduler] 執行每日分析 {datetime.now()}")
    default_targets = [
        StockTarget("2330.TW", "台積電", "台股", 1000, 1000),
        StockTarget("0050.TW", "元大台灣50", "ETF", 180, 1000),
    ]
    results, _ = _analyze_targets(default_targets)
    db.save_analysis(results)
    html = notifier.format_analysis(results)
    notifier.send(f"📊 台股分析 {datetime.now().strftime('%Y-%m-%d')}", html)


# ============================================================
# API 端點
# ============================================================
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
        "maiagent": mai_client.enabled,
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
    """使用 MaiAgent AI 助理進行對話"""
    if not mai_client.enabled:
        return {"status": "error", "message": "MaiAgent 未設定，請檢查環境變數 MAIAGENT_API_KEY, MAIAGENT_CHATBOT_ID, MAIAGENT_WEBCHAT_ID"}

    # 如果 ChatRequest 有 conversation_id 欄位可以延續對話
    conversation_id = getattr(req, 'conversation_id', None)
    result = mai_client.chat(req.message, conversation_id)
    return result


@app.post("/analyze_news")
def analyze_news(req: NewsRequest):
    """使用 MaiAgent 分析新聞"""
    if not mai_client.enabled:
        return {"status": "error", "message": "MaiAgent 未設定"}

    prompt = (
        "請分析以下新聞，並以 JSON 格式回覆：\n"
        '{"summary": "一句話總結（20字內）", "sentiment": "利多/利空/中立", '
        '"impact_level": "高/中/低", "impact_stocks": ["代號或產業1"], '
        '"reasoning": "判斷原因（50字內）"}\n\n'
        f"新聞：\n{req.news_content[:2000]}"
    )

    result = mai_client.chat(prompt)
    if result["status"] == "success":
        text = result["reply"].strip()
        # 嘗試清理 markdown 格式
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return {"status": "success", "analysis": text.strip()}
    else:
        return result


@app.get("/news")
def get_news(sources: str = "", limit: int = 5):
    source_list = [s.strip() for s in sources.split(",")] if sources else None
    news = NewsCrawler.fetch_all(sources=source_list, limit_per_source=limit)
    return {"status": "success", "count": len(news), "data": news}


@app.post("/news/analyze_batch")
def analyze_news_batch(req: NewsSourceRequest):
    """使用 MaiAgent 批次分析新聞"""
    if not mai_client.enabled:
        return {"status": "error", "message": "MaiAgent 未設定"}

    news_list = NewsCrawler.fetch_all(
        sources=req.sources, limit_per_source=req.limit
    )[:15]

    if not news_list:
        return {"status": "error", "message": "沒有抓到新聞"}

    combined = "\n".join([
        f"{i+1}. [{n['source']}] {n['title']}"
        for i, n in enumerate(news_list)
    ])

    prompt = (
        "請分析以下新聞列表的情緒，以 JSON 陣列格式回覆：\n"
        '[{"index": 1, "sentiment": "利多/利空/中立", "impact": "高/中/低", "reason": "簡短說明(30字內)"}]\n\n'
        f"新聞列表：\n{combined}"
    )

    result = mai_client.chat(prompt)
    if result["status"] != "success":
        return result

    text = result["reply"].strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    text = text.strip()

    try:
        analysis = json.loads(text)
    except json.JSONDecodeError:
        analysis = []

    for i, item in enumerate(news_list):
        matched = next((a for a in analysis if a.get("index") == i + 1), None)
        if matched:
            item['sentiment'] = matched.get('sentiment', '中立')
            item['impact'] = matched.get('impact', '低')
            item['ai_reason'] = matched.get('reason', '')
        else:
            item['sentiment'] = '中立'
            item['impact'] = '低'
            item['ai_reason'] = ''

        db.save_news_analysis({
            "source": item['source'],
            "title": item['title'],
            "sentiment": item['sentiment'],
            "summary": item.get('ai_reason', ''),
            "link": item.get('link', '')
        })

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


@app.get("/auto_news")
def auto_news():
    """使用 MaiAgent 自動產生每日新聞摘要"""
    if not mai_client.enabled:
        return {"status": "error", "message": "MaiAgent 未設定"}

    try:
        news = NewsCrawler.fetch_all(limit_per_source=3)[:10]
        if not news:
            return {"status": "error", "message": "無新聞資料"}

        titles = "\n".join([f"- [{n['source']}] {n['title']}" for n in news])
        prompt = (
            "根據以下今日財經新聞標題，撰寫一份 200 字內的台股每日摘要，\n"
            "包含：(1) 今日大盤氛圍 (2) 主要利多利空 (3) 操作建議。用繁體中文。\n\n"
            f"新聞：\n{titles}"
        )

        result = mai_client.chat(prompt)
        if result["status"] == "success":
            return {
                "status": "success",
                "summary": result["reply"],
                "news_count": len(news),
                "sources_used": list(set(n['source'] for n in news))
            }
        else:
            return result
    except Exception as e:
        return {"status": "error", "message": str(e)[:200]}


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


if os.path.isdir("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)

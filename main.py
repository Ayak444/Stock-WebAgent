import os
from dotenv import load_dotenv
load_dotenv()

import json
import re
import traceback
import asyncio
import logging
import pandas as pd
import requests as http_requests
from datetime import datetime, timezone, timedelta
from contextlib import asynccontextmanager
from uuid import uuid4
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

# 新的核心模塊
from cache_layer import cache_manager
from crew_workflow import stock_crew_orchestrator
from async_data_provider import AsyncDataProvider, get_async_provider, close_async_provider
from task_queue import job_runner, ScheduledTaskManager
from websocket_system import ws_manager, msg_handler, initialize_websocket_system, shutdown_websocket_system
import websocket_system
# 原有模塊
from agent import get_sentiment_analysis
from models import (
    TargetItem, AnalyzeRequest, ChatRequest, NewsRequest,
    BacktestRequest, NewsSourceRequest, StockTarget, SentimentResponse,
    ScreenerAnalyzeRequest, SyncPortfolioRequest, StressTestRecordRequest,
    TradeRequest, AuthRequest
)
from data_provider import DataProvider
from analyzer import TechnicalAnalyzer
from strategy import StrategyEngine
from news_crawler import NewsCrawler
from database import Database
from backtest import Backtester
from screener_engine import analyze_related_stocks
from notifier import DiscordNotifier

def extract_json_object(text: str) -> str:
    """Extracts the first valid JSON object from a string using brace counting."""
    start_idx = text.find('{')
    if start_idx == -1: return ""
    
    brace_count = 0
    for i in range(start_idx, len(text)):
        if text[i] == '{': brace_count += 1
        elif text[i] == '}':
            brace_count -= 1
            if brace_count == 0:
                return text[start_idx:i+1]
    return ""

# 設置日誌
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


MAIAGENT_API_KEY = os.environ.get("MAIAGENT_API_KEY", "")
MAIAGENT_CHATBOT_ID = os.environ.get("MAIAGENT_CHATBOT_ID", "")
MAIAGENT_WEBCHAT_ID = os.environ.get("MAIAGENT_WEBCHAT_ID", "")
MAIAGENT_BASE_URL = "https://api.maiagent.ai/api"

# 舊版 MaiAgentClient（保留以支持舊 API）
class MaiAgentClient:
    def __init__(self, api_key: str, chatbot_id: str, webchat_id: str):
        self.api_key = api_key
        self.base_url = "https://api.groq.com/openai/v1"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        self.enabled = bool(api_key)

    def create_conversation(self) -> str:
        return "groq-session"

    def send_message(self, content: str, conversation_id: str = None) -> str:
        url = "https://api.groq.com/openai/v1/chat/completions"
        payload = {
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {"role": "user", "content": content}
            ],
            "temperature": 0.2
        }
        
        response = http_requests.post(
            url, headers=self.headers, json=payload, timeout=120
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]

    def chat(self, user_message: str, conversation_id: str = None) -> dict:
        try:
            if not conversation_id:
                conversation_id = self.create_conversation()
            reply = self.send_message(user_message, conversation_id)
            return {
                "status": "success",
                "reply": reply,
                "conversation_id": conversation_id
            }
        except http_requests.exceptions.HTTPError as e:
            status_code = e.response.status_code if e.response is not None else 0
            error_details = e.response.text if e.response is not None else str(e)
            return {"status": "error", "message": f"API 錯誤 ({status_code}): {error_details}"}
        except http_requests.exceptions.Timeout:
            return {"status": "error", "message": "AI 回覆逾時，請稍後再試"}
        except Exception as e:
            return {"status": "error", "message": str(e)[:200]}

    async def send_message_async(self, content: str, conversation_id: str = None) -> str:
        return await asyncio.to_thread(self.send_message, content, conversation_id)

    async def chat_async(self, user_message: str, conversation_id: str = None) -> dict:
        return await asyncio.to_thread(self.chat, user_message, conversation_id)

mai_client = MaiAgentClient(MAIAGENT_API_KEY, MAIAGENT_CHATBOT_ID, MAIAGENT_WEBCHAT_ID)

# 後台任務調度器
scheduler = None
try:
    from apscheduler.schedulers.background import BackgroundScheduler
    scheduler = BackgroundScheduler(timezone='Asia/Taipei')
except ImportError:
    pass
from cron_jobs import run_backtest_hydration_task


async def daily_analysis_task_async():
    """非同步每日分析與資產配置報告任務"""
    # 嘗試抓取預設使用者的資產配置
    portfolio = db.get_portfolio(DEFAULT_USER_ID)
    
    targets = []
    if portfolio:
        for item in portfolio:
            code = item.get("code", "")
            if code:
                if not code.endswith(".TW") and not code.endswith(".TWO"):
                    code += ".TW"
                cost = float(item.get("cost", 0)) if item.get("cost") else 0
                shares = int(item.get("shares", 0)) if item.get("shares") else 0
                targets.append(StockTarget(code, item.get("name", code), "自選", cost, shares))
    
    # 若無資產配置，退回預設名單
    if not targets:
        targets = [
            StockTarget("2330.TW", "台積電", "台股", 1000, 1000),
            StockTarget("0050.TW", "元大台灣50", "ETF", 180, 1000),
        ]
        
    results, _ = await _analyze_targets_async(targets)
    db.save_analysis(results)
    desc = notifier.format_analysis(results)
    notifier.send(f"📊 每日投資組合與台股分析 {datetime.now().strftime('%Y-%m-%d')}", desc)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 初始化資料庫連線與 WebSocket 系統 (需在任務隊列前完成)
    async_provider = await get_async_provider()
    await initialize_websocket_system(async_provider)
    logger.info("✓ WebSocket 實時推送已啟動")

    # 啟動異步任務隊列
    await job_runner.start()
    logger.info("✓ 異步任務隊列已啟動")
    
    # 啟動定時任務
    job_runner.schedule_daily(
        "daily_analysis",
        "每日股票與資產配置分析",
        daily_analysis_task_async,
        hour=22,  # 晚上 10 點發送
        minute=0
    )
    
    # 回測快取運算任務 (排在每日收盤後，如凌晨 2:00)
    job_runner.schedule_daily(
        "backtest_hydration",
        "預先計算回測結果",
        run_backtest_hydration_task,
        hour=2,
        minute=0
    )
    
    logger.info("✓ 定時任務已排程（每日 22:00 與 02:00）")
    
    yield
    
    # 清理
    await job_runner.stop()
    await shutdown_websocket_system()
    await close_async_provider()
    logger.info("✓ 應用清理完成")

app = FastAPI(title="台股智能分析 API", version="4.0（多代理升級版）", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

db = Database()
notifier = DiscordNotifier()

async def _analyze_targets_async(targets):
    """
    異步目標分析 - 使用新的多代理系統
    並行獲取數據、計算指標、執行 AI 分析
    """
    async_provider = await get_async_provider()
    
    # 並行獲取籌碼、匯率和所有股票的歷史數據
    chip_task = asyncio.create_task(async_provider.get_chip_data())
    fx_task = asyncio.create_task(async_provider.get_fx_status())
    
    # 為所有目標並行獲取歷史數據
    history_tasks = {
        t.id: asyncio.create_task(async_provider.get_stock_history(t.id, days=180))
        for t in targets
    }
    
    # 等待所有初始任務完成
    chip = await chip_task
    fx_val, fx_note = await fx_task
    histories = await asyncio.gather(*history_tasks.values())
    
    results = []
    consecutive_errors = 0
    
    for t, df in zip(targets, histories):
        try:
            if df.empty:
                results.append({
                    "name": t.name, "ticker": t.id, "price": 0,
                    "score": 0, "advice": "資料讀取失敗", "pl": 0,
                    "valuation": "無數據", "signals": ["無法取得歷史資料"],
                    "exit": "-", "sl": 0
                })
                continue
            
            # 計算技術指標
            df_with_indicators = TechnicalAnalyzer.calculate_indicators(df)
            last = df_with_indicators.iloc[-1]
            price = float(last['Close'])
            
            # 組合技術指標數據
            indicators = {
                'MA5': float(last.get('MA5', price)),
                'MA20': float(last.get('MA20', price)),
                'MA60': float(last.get('MA60', price)),
                'RSI': float(last.get('RSI', 50)),
                'MACD': float(last.get('MACD', 0)),
                'Signal': float(last.get('Signal', 0)),
                'K': float(last.get('K', 50)),
                'D': float(last.get('D', 50)),
                'Volume': float(last.get('Volume', 0))
            }
            
            # 獲取實時價格
            rt_price = await async_provider.get_realtime_price(t.id)
            final_price = rt_price if rt_price else price
            
            # 傳統策略評估（快速通道）
            eval_result = StrategyEngine.evaluate(
                t.id, df_with_indicators, chip, fx_val, t.cost, t.shares
            )
            
            # 獲取新聞進行多代理分析
            news_list = (await asyncio.to_thread(NewsCrawler.fetch_all, limit_per_source=3))[:5]
            news_text = "\n".join([f"- {n['title']}" for n in news_list])
            
            # 使用多代理系統進行綜合分析（可選，取決於 AI 可用性）
            if mai_client.enabled:
                try:
                    crew_result_str = await stock_crew_orchestrator.run_analysis(
                        ticker=t.id,
                        name=t.name,
                        price=final_price,
                        cost=t.cost,
                        news_content=news_text,
                        indicators=indicators
                    )
                    
                    import json
                    import re
                    
                    clean_json = re.sub(r'```json\s*', '', str(crew_result_str), flags=re.IGNORECASE)
                    clean_json = re.sub(r'```\s*', '', clean_json)
                    extracted = extract_json_object(clean_json)
                    if extracted:
                        clean_json = extracted
                    
                    multi_agent_result = json.loads(clean_json, strict=False)
                    combined_advice = multi_agent_result.get('final_advice', eval_result['advice'])
                    combined_score = int(multi_agent_result.get('score', eval_result['score']))
                except Exception as e:
                    logger.warning(f"CrewAI 多代理分析失敗 {t.id}: {e}")
                    combined_advice = eval_result['advice']
                    combined_score = eval_result['score']
            else:
                combined_advice = eval_result['advice']
                combined_score = eval_result['score']
            
            pl = round((final_price - t.cost) / t.cost * 100, 2) if t.cost > 0 else 0
            results.append({
                "name": t.name, "ticker": t.id,
                "price": round(final_price, 2), "score": combined_score,
                "advice": combined_advice, "pl": pl,
                "valuation": eval_result['valuation'],
                "signals": eval_result['signals'],
                "exit": eval_result['exit_note'],
                "sl": eval_result['stop_loss']
            })
            consecutive_errors = 0
        
        except Exception as e:
            consecutive_errors += 1
            if consecutive_errors >= 3:
                logger.error(f"全域例外熔斷：連續 {consecutive_errors} 次出現異常，中止分析。")
                raise Exception(f"Circuit Breaker triggered: {e}")
            logger.error(f"分析 {t.id} 出現異常: {e}")
            traceback.print_exc()
            results.append({
                "name": t.name, "ticker": t.id, "price": 0,
                "score": 0, "advice": "運算錯誤", "pl": 0,
                "valuation": "無數據", "signals": [f"例外: {str(e)[:80]}"],
                "exit": "-", "sl": 0
            })
    
    return results, fx_note


def _analyze_targets(targets):
    """
    同步版本（保留以支持舊 API）
    使用傳統的同步調用
    """
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

def _extract_screener_prompt_payload(message: str):
    if not message:
        return None
    if "深度關聯分析" not in message or "使用者勾選的篩選條件為" not in message:
        return None

    targets = []
    filters = []

    m_targets = re.search(r"分析：(.+?)。", message, re.DOTALL)
    if m_targets:
        targets = [x.strip() for x in m_targets.group(1).split(",") if x.strip()]

    m_filters = re.search(r"使用者勾選的篩選條件為：(.+?)。", message, re.DOTALL)
    if m_filters:
        filters = [x.strip() for x in m_filters.group(1).split(",") if x.strip()]

    if not targets or not filters:
        return None
    return {"targets": targets, "filters": filters}

def _to_legacy_screener_shape(items: list):
    out = []
    for item in items:
        target = item.get("target", {})
        supply = item.get("supply_chain", {})
        supply_lines = [
            f"上游: {'、'.join(supply.get('upstream', [])) or '無'}",
            f"中游: {'、'.join(supply.get('midstream', [])) or '無'}",
            f"下游: {'、'.join(supply.get('downstream', [])) or '無'}",
        ]
        matched = []
        for s in item.get("evaluated_stocks", []):
            reasons = s.get("tags", [])
            main_force = s.get("main_force", {})
            mf_text = ""
            if main_force:
                mf_text = (
                    f"｜主力:{main_force.get('bias', '無法判斷')}"
                    f"({main_force.get('score', 0)}/100)"
                )
            matched.append({
                "name": f"{s.get('ticker', '')} {s.get('name', '')}".strip(),
                "reason": (
                    f"近5日漲跌 {s.get('pct_5d', 0)}%，現價 {s.get('price', 0)}；"
                    f"條件：{'、'.join(reasons) if reasons else '無特殊標籤'}{mf_text}"
                )
            })
        out.append({
            "target": f"{target.get('ticker', '')} {target.get('name', '')}".strip(),
            "group": item.get("group", "未分類"),
            "concepts": item.get("concepts", []),
            "supply_chain": supply_lines,
            "filtered_stocks": matched
        })
    return out

def _ai_enrich_relation_profile(ticker: str, name: str, industry: str):
    if not mai_client.enabled:
        return None

    # 1. 攔截器：瞬間從 Yahoo Finance 抓取該標的最新新聞
    recent_news = []
    try:
        url = f"https://query2.finance.yahoo.com/v1/finance/search?q={ticker}&newsCount=5"
        headers = {"User-Agent": "Mozilla/5.0"}
        r = http_requests.get(url, headers=headers, timeout=5)
        data = r.json()
        if "news" in data:
            recent_news = [item.get("title", "") for item in data["news"] if item.get("title")]
    except Exception as e:
        print(f"Fetch Ticker News Error: {e}")

    news_text = "\n".join([f"- {title}" for title in recent_news]) if recent_news else "近期無重大新聞"

    # 2. 組合新聞與思考鏈的 Prompt
    prompt = (
        "你是一位資深的台股產業研究員，擅長挖掘隱藏供應鏈與最新市場題材。\n"
        f"請針對標的「{ticker} {name}」進行深度分析，並參考以下最新新聞動態來定義其最新概念標籤：\n"
        f"【近期新聞】：\n{news_text}\n\n"
        "請依照以下步驟思考：\n"
        "1. 識別該公司的核心營收來源。\n"
        "2. 判斷其在產業鏈中的位置（上/中/下游）。\n"
        "3. 找出與該公司業務高度連動的真實台股標的。\n"
        "4. 根據近期新聞與科技趨勢，標記其所屬概念。\n\n"
        "【嚴格規定】\n"
        "1. 只能輸出合法 JSON 格式，絕對不可包含任何 Markdown 標記 (如 ```json) 或其他廢話。\n"
        '2. 格式：{"name":"公司中文簡稱","group":"精確產業族群","concepts":["概念1","概念2"],"related":["2330.TW"],"supply_chain":{"upstream":["2303.TW"],"midstream":["xxxx.TW"],"downstream":["xxxx.TW"]}}\n'
        "3. name、group 與 concepts 絕對不可留空或填未分類。若缺乏資訊請根據常理推斷。\n"
        "4. related 與 supply_chain 內只能填寫真實存在的台股代號 (4碼+.TW 或 .TWO，如 2330.TW)。\n"
    )
    
    result = mai_client.chat(prompt)
    if result.get("status") != "success":
        return None
        
    text = (result.get("reply") or "").strip()
    
    # 3. 雙重去殼法：強制剝離 Markdown 標記
    text = re.sub(r'```json\s*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'```\s*', '', text)
    
    extracted = extract_json_object(text)
    if extracted:
        clean_json = extracted
    else:
        clean_json = text
        
    try:
        data = json.loads(clean_json, strict=False)
        if isinstance(data, dict) and "name" in data:
            return data
    except Exception as e:
        print(f"AI Enricher JSON Parse Error: {e}\nRaw Content: {clean_json}")
    
    return None

def daily_analysis_task():
    default_targets = [
        StockTarget("2330.TW", "台積電", "台股", 1000, 1000),
        StockTarget("0050.TW", "元大台灣50", "ETF", 180, 1000),
    ]
    results, _ = _analyze_targets(default_targets)
    db.save_analysis(results)
    desc = notifier.format_analysis(results)
    notifier.send(f"📊 台股分析 {datetime.now().strftime('%Y-%m-%d')}", desc)

@app.get("/")
@app.head("/")
def root():
    if os.path.exists("static/index.html"):
        return FileResponse("static/index.html", headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        })
    return {"status": "alive", "message": "API 運作中", "docs": "/docs"}

# ===== WebSocket 實時推送端點 =====
@app.websocket("/ws/live")
async def websocket_live(websocket: WebSocket):
    """
    實時行情推送 WebSocket 端點
    客戶端可訂閱特定股票的實時報價
    """
    client_id = str(uuid4())
    await ws_manager.connect(websocket, room_id="live")
    
    try:
        # 歡迎消息
        await ws_manager.send_to_client(websocket, {
            "type": "connection_established",
            "client_id": client_id,
            "message": "已連接到實時推送服務"
        })
        
        # 監聽客戶端消息
        while True:
            data = await websocket.receive_text()
            await msg_handler.handle_message(websocket, client_id, data)
    
    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket, room_id="live")
        logger.info(f"客戶端 {client_id} 已斷開連接")
    except Exception as e:
        logger.error(f"WebSocket 錯誤 {client_id}: {e}")
        await ws_manager.disconnect(websocket, room_id="live")

@app.websocket("/ws/prices")
async def websocket_prices(websocket: WebSocket):
    """實時價格推送頻道"""
    await ws_manager.connect(websocket, room_id="prices")
    try:
        while True:
            data = await websocket.receive_text()
            if "ping" in data.lower():
                await websocket.send_json({"type": "pong", "timestamp": datetime.now().isoformat()})
    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket, room_id="prices")

@app.websocket("/ws/analysis")
async def websocket_analysis(websocket: WebSocket):
    """分析結果推送頻道"""
    await ws_manager.connect(websocket, room_id="analysis")
    try:
        while True:
            data = await websocket.receive_text()
            if "ping" in data.lower():
                await websocket.send_json({"type": "pong", "timestamp": datetime.now().isoformat()})
    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket, room_id="analysis")

# ===== WebSocket 統計和管理端點 =====
@app.get("/ws/stats")
def websocket_stats():
    """取得 WebSocket 連接統計"""
    return ws_manager.get_stats()

@app.get("/ws/queue-stats")
def queue_stats():
    """取得任務隊列統計"""
    return job_runner.get_stats()

@app.get("/cache/stats")
def cache_stats():
    """取得緩存統計"""
    return cache_manager.get_stats()

@app.get("/ping")
@app.head("/ping")
def ping():
    return {"status": "alive", "time": datetime.now().isoformat()}

@app.get("/health")
@app.head("/health")
def health():
    """系統健康檢查（包含新系統狀態）"""
    queue_stats = job_runner.get_stats()
    ws_stats = ws_manager.get_stats()
    cache_stats_data = cache_manager.get_stats()
    
    return {
        "status": "ok",
        "version": "4.0",
        "timestamp": datetime.now().isoformat(),
        
        # 傳統系統
        "maiagent": mai_client.enabled,
        "discord": notifier.enabled,
        "database": True if db.supabase else False,
        
        # 新系統狀態
        "systems": {
            "task_queue": {
                "running": True,
                "pending_tasks": queue_stats['pending'],
                "active_workers": queue_stats['workers'],
                "total_processed": queue_stats['success']
            },
            "websocket": {
                "active_connections": ws_stats['total_connections'],
                "subscriptions": ws_stats['total_subscriptions']
            },
            "cache": {
                "usage_percent": cache_stats_data['usage_percent'],
                "items": cache_stats_data['total_items']
            }
        }
    }

@app.get("/macro")
async def macro_data():
    """
    獲取宏觀經濟指標
    使用異步數據提供者並結合緩存
    """
    async_provider = await get_async_provider()
    data = await async_provider.get_macro_indices()
    return {"status": "success", "data": data}

@app.post("/analyze")
async def analyze(req: AnalyzeRequest):
    """
    異步分析端點
    使用新的多代理系統進行綜合分析
    """
    targets = [StockTarget(t.id, t.name, t.type, t.cost, t.shares) for t in req.targets]
    
    try:
        results, fx_note = await _analyze_targets_async(targets)
        db.save_analysis(results)
        
        # 並行推送到 WebSocket 客戶端
        for result in results:
            if websocket_system.price_broadcaster:
                await websocket_system.price_broadcaster.push_analysis_result(result['ticker'], result)
        
        return {
            "status": "success",
            "data": results,
            "fx": fx_note,
            "cached_at": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"分析失敗: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/chat")
async def chat(req: ChatRequest):
    payload = _extract_screener_prompt_payload(req.message)
    if payload:
        # 移至 Thread Pool 執行，避免阻塞主迴圈
        data = await asyncio.to_thread(
            analyze_related_stocks,
            payload["targets"],
            payload["filters"],
            ai_enricher=_ai_enrich_relation_profile if mai_client.enabled else None
        )
        legacy_data = _to_legacy_screener_shape(data)
        return {
            "status": "success",
            "reply": json.dumps(legacy_data, ensure_ascii=False),
            "conversation_id": "local-screener"
        }

    if not mai_client.enabled:
        return {"status": "error", "message": "MaiAgent 未設定，請檢查環境變數"}
        
    conversation_id = getattr(req, 'conversation_id', None)
    user_msg = req.message
    
    rag_keywords = ["財報", "法說會", "資本支出", "營收", "毛利率", "淨利", "展望", "報告", "支出"]
    if any(kw in user_msg for kw in rag_keywords):
        context_chunks = db.search_corporate_reports(user_msg)
        if context_chunks:
            context_str = "\n".join(context_chunks)
            user_msg = (
                f"請根據以下企業官方財報與法說會文獻內容，深入且精確地回答使用者的問題。"
                f"如果文獻內容與問題無關，請結合您的金融知識回答。\n\n"
                f"【官方文獻背景資料】:\n{context_str}\n\n"
                f"【使用者問題】:\n{user_msg}"
            )

    result = await mai_client.chat_async(user_msg, conversation_id)
    return result

@app.post("/analyze_news")
async def analyze_news(req: NewsRequest):
    if not mai_client.enabled:
        return {"status": "error", "message": "MaiAgent 未設定"}
    prompt = (
        "請分析以下新聞，並以 JSON 格式回覆：\n"
        '{"summary": "一句話總結（20字內）", "sentiment": "利多/利空/中立", '
        '"impact_level": "高/中/低", "impact_stocks": ["代號或產業1"], '
        '"reasoning": "判斷原因（50字內）"}\n\n'
        f"新聞：\n{req.news_content[:2000]}"
    )
    result = await mai_client.chat_async(prompt)
    if result["status"] == "success":
        text = result["reply"].strip()
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
async def analyze_news_batch(req: NewsSourceRequest):
    if not mai_client.enabled:
        return {"status": "error", "message": "MaiAgent 未設定"}
    
    source_list = req.sources if req.sources else ['investing', 'ctee', 'cnyes']
    limit = req.limit if req.limit and req.limit > 0 else 5
    
    news_list = await asyncio.to_thread(NewsCrawler.fetch_all, sources=source_list, limit_per_source=limit)
    news_list = news_list[:15]
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
    result = await mai_client.chat_async(prompt)
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
async def auto_news():
    if not mai_client.enabled:
        return {"status": "error", "message": "MaiAgent 未設定"}
    try:
        news = await asyncio.to_thread(NewsCrawler.fetch_all, limit_per_source=3)
        news = news[:10]
        if not news:
            return {"status": "error", "message": "無新聞資料"}
        titles = "\n".join([f"- [{n['source']}] {n['title']}" for n in news])
        prompt = (
            "根據以下今日財經新聞標題，撰寫一份 200 字內的台股每日摘要，\n"
            "包含：(1) 今日大盤氛圍 (2) 主要利多利空 (3) 操作建議。用繁體中文。\n\n"
            f"新聞：\n{titles}"
        )
        result = await mai_client.chat_async(prompt)
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
async def get_kline(ticker: str, days: int = 180):
    """
    獲取 K 線數據
    結合緩存和異步數據獲取
    """
    try:
        # 先檢查緩存
        cached_kline = cache_manager.get_kline(ticker, days)
        if cached_kline:
            logger.debug(f"使用緩存 K 線: {ticker}")
            df = pd.DataFrame(cached_kline)
            if 'Date' not in df.columns and 'index' in df.columns:
                df = df.rename(columns={'index': 'Date'})
            if 'Date' in df.columns:
                df['Date'] = pd.to_datetime(df['Date'])
        else:
            # 異步獲取
            async_provider = await get_async_provider()
            df = await async_provider.get_stock_history(ticker, days)
        
        if df.empty:
            return JSONResponse(
                {"status": "error", "message": "找不到資料"},
                status_code=404
            )
        
        # 計算技術指標
        df = TechnicalAnalyzer.calculate_indicators(df).reset_index()
        
        candles, volumes, ma5, ma20, ma60 = [], [], [], [], []
        date_col = 'Date' if 'Date' in df.columns else df.columns[0]
        
        for _, row in df.iterrows():
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
            "ma5": ma5, "ma20": ma20, "ma60": ma60,
            "from_cache": cached_kline is not None
        }
    except Exception as e:
        logger.error(f"獲取 K 線失敗: {e}")
        traceback.print_exc()
        return JSONResponse(
            {"status": "error", "message": str(e)},
            status_code=500
        )

@app.get("/history")
def history(ticker: str = None, limit: int = 100):
    return {"status": "success", "data": db.get_history(ticker, limit)}

@app.get("/history/tickers")
def history_tickers():
    return {"status": "success", "data": db.get_all_tickers()}

@app.post("/backtest")
async def backtest(req: BacktestRequest):
    """
    修改為從資料庫讀取預先計算好的結果 (Database-Driven)
    以達到毫秒級回應，不再即時運算
    """
    cached_result = db.get_backtest_results(req.ticker, strategy_name="default_ma_rsi")
    if cached_result:
        # 將 Supabase 回傳的資料結構轉為原本前端預期的格式
        return {
            "status": "success",
            "ticker": cached_result.get("symbol", req.ticker),
            "win_rate": cached_result.get("win_rate", 0),
            "max_drawdown": cached_result.get("max_drawdown", 0),
            "strategy_return": cached_result.get("total_return", 0),
            "latest_signal": cached_result.get("latest_signal", "NEUTRAL"),
            # 以下給予預設值以避免前端報錯
            "buy_hold_return": 0,
            "outperformance": 0,
            "trade_count": 0,
            "final_value": 0,
            "trades": []
        }
    
    # Fallback: 若資料庫還沒有預算資料，為了防止前端報錯，回傳等待中訊息或即時算一次
    # 這裡選擇即時運算一次作為 fallback
    return await asyncio.to_thread(Backtester.run, req.ticker, req.days)

DEFAULT_USER_ID = "00000000-0000-0000-0000-000000000000"

@app.get("/portfolio")
def get_user_portfolio(user_id: str):
    data = db.get_portfolio(user_id)
    return {"status": "success", "data": data}

@app.post("/portfolio")
def sync_user_portfolio(req: SyncPortfolioRequest):
    user_id = req.user_id
    if not user_id: return {"status": "error", "message": "Missing user_id"}
    db.save_portfolio(user_id, req.portfolio)
    return {"status": "success"}

@app.post("/stress_test/save")
def save_stress_test_final(req: StressTestRecordRequest):
    db.save_stress_test_record(
        req.user_id, 
        req.scenario, 
        req.result
    )
    return {"status": "success"}

@app.post("/screener/analyze")
def screener_analyze(req: ScreenerAnalyzeRequest):
    targets = req.targets or []
    source = req.source
    if source == "portfolio":
        user_id = req.user_id or DEFAULT_USER_ID
        portfolio = db.get_portfolio(user_id)
        targets = [p.get("code", "").strip() for p in portfolio if p.get("code")]

    targets = [t for t in targets if t]
    if not targets:
        return {"status": "error", "message": "沒有可分析的標的，請先輸入代號或匯入持股"}

    default_conditions = [
        "近5日跌幅超過10%", "近5日漲幅超過10%", "外資或投信近期連續買超",
        "預估殖利率大於5%", "本益比低於同業平均", "營收連續三個月年月雙增"
    ]

    data = analyze_related_stocks(
        targets,
        default_conditions,
        ai_enricher=_ai_enrich_relation_profile if mai_client.enabled else None
    )
    return {
        "status": "success",
        "source": source,
        "targets_count": len(targets),
        "data": data
    }

@app.get("/stress_test/history")
def get_stress_test_history_final(user_id: str = DEFAULT_USER_ID):
    data = db.get_stress_test_history(user_id)
    return {"status": "success", "data": data}

@app.post("/trade")
def execute_trade(req: TradeRequest):
    success = db.record_trade(
        req.user_id, req.action, req.ticker, 
        float(req.amount), float(req.price)
    )
    if success:
        return {"status": "success", "message": "交易已記錄"}
    return {"status": "error", "message": "交易失敗"}

@app.post("/auth/signup")
def signup(req: AuthRequest):
    try:
        user = db.create_user(req.email, req.password, req.name)
        if user:
            return {"status": "success", "user": user}
        raise HTTPException(status_code=400, detail="註冊失敗")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/auth/login")
def login(req: AuthRequest):
    user = db.verify_user(req.email, req.password)
    if user:
        return {"status": "success", "user": user}
    raise HTTPException(status_code=401, detail="信箱或密碼錯誤")

@app.get("/api/sentiment", response_model=SentimentResponse)
async def get_sentiment():
    news_list = (await asyncio.to_thread(NewsCrawler.fetch_all, limit_per_source=3))[:5]
    if not news_list:
        return {
            "score": 50, "label": "中立", "definition": "無數據", 
            "reasoning": "目前無新聞", "recommendations": [], "news_analysis": []
        }
    
    combined_news = "\n".join([f"新聞{i+1}: {n['title']} - {n['summary']}" for i, n in enumerate(news_list)])
    result = get_sentiment_analysis(combined_news)
    return result

@app.get("/market_status")
def market_status():
    is_open = DataProvider.is_market_open()
    tw_tz = timezone(timedelta(hours=8))
    return {"status": "success", "is_open": is_open, "time": datetime.now(tw_tz).isoformat()}

@app.get("/api/rankings")
async def get_rankings():
    data = await asyncio.to_thread(DataProvider.get_rankings)
    return {"status": "success", "data": data}

@app.get("/api/fundamentals/{ticker}")
def get_fundamentals(ticker: str):
    data = DataProvider.get_fundamentals(ticker)
    return {"status": "success", "data": data}

@app.get("/api/chips")
def get_chips():
    data = DataProvider.get_chip_data()
    return {"status": "success", "data": data}

@app.get("/api/stock_names")
def get_stock_names():
    from screener_engine import OPENAPI_CACHE
    return {"status": "success", "data": OPENAPI_CACHE.get("mapping", {})}

@app.get("/trades")
def get_trades(user_id: str):
    data = db.get_trade_history(user_id)
    return {"status": "success", "data": data}

if os.path.isdir("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
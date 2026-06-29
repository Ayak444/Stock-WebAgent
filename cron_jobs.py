import asyncio
from database import Database
from backtest import Backtester
import logging

logger = logging.getLogger(__name__)
db = Database()

DEFAULT_USER_ID = "00000000-0000-0000-0000-000000000000"
DEFAULT_TICKERS = ["2330.TW", "0050.TW", "2317.TW", "2454.TW", "2308.TW"]

async def run_backtest_hydration_task():
    """背景任務：定期計算回測並寫入資料庫快取"""
    logger.info("開始執行背景回測資料計算任務 (Hydration)...")
    
    # 1. 蒐集需要運算的股票清單 (從預設名單 + 用戶自選股)
    tickers_to_calc = set(DEFAULT_TICKERS)
    
    portfolio = db.get_portfolio(DEFAULT_USER_ID)
    if portfolio:
        for item in portfolio:
            code = item.get("code", "")
            if code:
                if not code.endswith(".TW") and not code.endswith(".TWO"):
                    code += ".TW"
                tickers_to_calc.add(code)
                
    logger.info(f"本次預計回測 {len(tickers_to_calc)} 檔股票: {tickers_to_calc}")
    
    # 2. 依序執行回測並儲存結果
    records = []
    for ticker in tickers_to_calc:
        try:
            # 跑 2 年 (約 750 天) 的回測
            res = await asyncio.to_thread(Backtester.run, ticker, 750)
            if res.get("status") == "success":
                records.append({
                    "symbol": ticker,
                    "strategy_name": "default_ma_rsi",
                    "win_rate": res.get("win_rate", 0),
                    "max_drawdown": res.get("max_drawdown", 0),
                    "total_return": res.get("strategy_return", 0),
                    "latest_signal": res.get("latest_signal", "NEUTRAL")
                })
                logger.info(f"[{ticker}] 回測計算完成")
            else:
                logger.warning(f"[{ticker}] 回測失敗: {res.get('message')}")
        except Exception as e:
            logger.error(f"[{ticker}] 回測發生未預期錯誤: {e}")
            
    # 3. 寫入資料庫
    if records:
        db.save_backtest_results(records)
        logger.info(f"成功將 {len(records)} 筆回測結果寫入資料庫。")
    else:
        logger.info("沒有任何回測結果需要寫入資料庫。")

from fastapi import FastAPI, BackgroundTasks, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import psycopg2
from psycopg2.extras import RealDictCursor
import os
from dotenv import load_dotenv

# Load env
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
CRON_SECRET = os.getenv("CRON_SECRET", "default-secret-key")

app = FastAPI(title="Nexus Quant API")

# CORS Setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Helper function for DB connection
def get_db_connection():
    if not DATABASE_URL:
        raise Exception("DATABASE_URL is not set")
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

@app.get("/")
def read_root():
    return {"status": "Nexus Quant API is running", "version": "1.0.0"}

@app.get("/api/stocks")
def get_stocks_list():
    """Fetch list of tracked stocks with their latest basic info and backtest summary."""
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 
                    s.symbol, 
                    s.name, 
                    b.latest_signal,
                    b.win_rate
                FROM stock_info s
                LEFT JOIN backtest_results b ON s.symbol = b.symbol
                ORDER BY s.symbol
            """)
            stocks = cur.fetchall()
        conn.close()
        return {"data": stocks}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/stocks/{symbol}")
def get_stock_data(symbol: str):
    """Fetch historical daily quotes and indicator data for a specific stock."""
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            # Get latest 100 days for charting
            cur.execute("""
                SELECT date, open_price as open, high_price as high, low_price as low, close_price as close, volume
                FROM daily_quotes
                WHERE symbol = %s
                ORDER BY date DESC
                LIMIT 100
            """, (symbol.upper(),))
            quotes = cur.fetchall()
            
            # Reverse to chronological order for charts
            quotes.reverse()
            
            cur.execute("""
                SELECT * FROM backtest_results
                WHERE symbol = %s
            """, (symbol.upper(),))
            backtest = cur.fetchone()
            
        conn.close()
        return {
            "symbol": symbol.upper(),
            "quotes": quotes,
            "backtest": backtest
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Background Task Mock
def run_daily_hydration_task():
    print("Background Task: Running daily data hydration...")
    # In reality, this would import hydrate_data.main() and run it,
    # and update job_status table.
    import time
    time.sleep(5)
    print("Background Task: Hydration complete.")

@app.post("/api/cron/update")
def trigger_daily_update(background_tasks: BackgroundTasks, authorization: str = Header(None)):
    """Triggered by Render Cron Job daily."""
    if authorization != f"Bearer {CRON_SECRET}":
        raise HTTPException(status_code=401, detail="Unauthorized cron trigger")
    
    # 1. (Optional) Insert 'pending' status into job_status table here
    
    # 2. Add heavy task to background to prevent Render timeout
    background_tasks.add_task(run_daily_hydration_task)
    
    # 3. Immediately return 200 OK
    return {"status": "Update process started in background", "job_id": "mock-uuid-1234"}

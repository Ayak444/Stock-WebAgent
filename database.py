# 歷史分析紀錄儲存 (SQLite)
import sqlite3
import json
import os
from datetime import datetime
from contextlib import contextmanager

DB_PATH = os.environ.get("DB_PATH", "history.db")

def init_db():
    """初始化資料庫"""
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS analysis_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                ticker TEXT NOT NULL,
                name TEXT,
                price REAL,
                score INTEGER,
                advice TEXT,
                pl REAL,
                valuation TEXT,
                signals TEXT,
                exit_note TEXT,
                sl REAL
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_ticker_time 
            ON analysis_history(ticker, timestamp DESC)
        """)
        conn.commit()

@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def save_analysis(results):
    """儲存一批分析結果"""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as conn:
        for r in results:
            conn.execute("""
                INSERT INTO analysis_history
                (timestamp, ticker, name, price, score, advice, pl, valuation, signals, exit_note, sl)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                ts, r.get("ticker",""), r.get("name",""), r.get("price",0),
                r.get("score",0), r.get("advice",""), r.get("pl",0),
                r.get("valuation",""), json.dumps(r.get("signals",[]), ensure_ascii=False),
                r.get("exit",""), r.get("sl",0)
            ))
        conn.commit()

def get_history(ticker=None, limit=100):
    """取得歷史紀錄"""
    with get_conn() as conn:
        if ticker:
            rows = conn.execute("""
                SELECT * FROM analysis_history
                WHERE ticker = ? ORDER BY timestamp DESC LIMIT ?
            """, (ticker, limit)).fetchall()
        else:
            rows = conn.execute("""
                SELECT * FROM analysis_history
                ORDER BY timestamp DESC LIMIT ?
            """, (limit,)).fetchall()
        
        results = []
        for r in rows:
            d = dict(r)
            try:
                d["signals"] = json.loads(d["signals"]) if d["signals"] else []
            except:
                d["signals"] = []
            results.append(d)
        return results

def get_all_tickers():
    """取得歷史紀錄中所有的股票代號"""
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT DISTINCT ticker, name FROM analysis_history
            ORDER BY ticker
        """).fetchall()
        return [dict(r) for r in rows]

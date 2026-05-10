import sqlite3
import os
import json
from datetime import datetime
import pandas as pd
from supabase import create_client, Client

DB_PATH = os.environ.get("DB_PATH", "history.db")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

class Database:
    def __init__(self):
        self._init_db()
        self.supabase: Client = None
        if SUPABASE_URL and SUPABASE_KEY:
            self.supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

    def _init_db(self):
        conn = sqlite3.connect(DB_PATH)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS analysis_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                ticker TEXT NOT NULL,
                name TEXT,
                price REAL,
                score INTEGER,
                advice TEXT,
                pl_percent REAL,
                signals TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS news_analysis (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                source TEXT,
                title TEXT,
                sentiment TEXT,
                summary TEXT,
                link TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS daily_kline (
                ticker TEXT NOT NULL,
                date TEXT NOT NULL,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume INTEGER,
                PRIMARY KEY (ticker, date)
            )
        """)
        conn.commit()
        conn.close()

    def save_analysis(self, results: list):
        conn = sqlite3.connect(DB_PATH)
        ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for r in results:
            conn.execute("""
                INSERT INTO analysis_history
                (timestamp, ticker, name, price, score, advice, pl_percent, signals)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                ts, r.get('ticker', ''), r.get('name', ''),
                r.get('price', 0), r.get('score', 0),
                r.get('advice', ''), r.get('pl', 0),
                json.dumps(r.get('signals', []), ensure_ascii=False)
            ))
        conn.commit()
        conn.close()

    def get_history(self, ticker=None, limit=100):
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        if ticker:
            cursor = conn.execute(
                "SELECT * FROM analysis_history WHERE ticker=? ORDER BY id DESC LIMIT ?",
                (ticker, limit)
            )
        else:
            cursor = conn.execute(
                "SELECT * FROM analysis_history ORDER BY id DESC LIMIT ?", (limit,)
            )
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return rows

    def get_all_tickers(self):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.execute("SELECT DISTINCT ticker, name FROM analysis_history")
        result = [{"ticker": r[0], "name": r[1]} for r in cursor.fetchall()]
        conn.close()
        return result

    def save_news_analysis(self, item: dict):
        conn = sqlite3.connect(DB_PATH)
        conn.execute("""
            INSERT INTO news_analysis (timestamp, source, title, sentiment, summary, link)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            item.get('source', ''), item.get('title', ''),
            item.get('sentiment', ''), item.get('summary', ''),
            item.get('link', '')
        ))
        conn.commit()
        conn.close()

    def save_kline_batch(self, df: pd.DataFrame, ticker: str):
        if df.empty:
            return
        conn = sqlite3.connect(DB_PATH)
        df_save = df.copy()
        df_save['ticker'] = ticker
        df_save['date'] = df_save.index.strftime('%Y-%m-%d')
        df_save = df_save[['ticker', 'date', 'Open', 'High', 'Low', 'Close', 'Volume']]
        df_save.columns = ['ticker', 'date', 'open', 'high', 'low', 'close', 'volume']
        
        df_save.to_sql('daily_kline', conn, if_exists='append', index=False)
        
        conn.execute("""
            DELETE FROM daily_kline 
            WHERE rowid NOT IN (
                SELECT MIN(rowid) 
                FROM daily_kline 
                GROUP BY ticker, date
            )
        """)
        conn.commit()
        conn.close()

    def get_kline(self, ticker: str, days: int) -> pd.DataFrame:
        conn = sqlite3.connect(DB_PATH)
        query = "SELECT date, open, high, low, close, volume FROM daily_kline WHERE ticker = ? ORDER BY date DESC LIMIT ?"
        df = pd.read_sql_query(query, conn, params=(ticker, days))
        conn.close()
        if df.empty:
            return pd.DataFrame()
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date').set_index('date')
        df.columns = ['Open', 'High', 'Low', 'Close', 'Volume']
        return df

    def save_stress_test(self, total_cost: float, total_value: float, total_pl: float, portfolio: list):
        if not self.supabase:
            return
        ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        data = {
            "timestamp": ts,
            "total_cost": total_cost,
            "total_value": total_value,
            "total_pl_percent": total_pl,
            "portfolio_json": portfolio
        }
        try:
            self.supabase.table("stress_test_records").insert(data).execute()
        except Exception:
            pass

    def get_stress_tests(self, limit: int = 50):
        if not self.supabase:
            return []
        try:
            response = self.supabase.table("stress_test_records").select("*").order("id", desc=True).limit(limit).execute()
            rows = response.data
            for row in rows:
                row['portfolio'] = row.pop('portfolio_json', [])
            return rows
        except Exception:
            return []
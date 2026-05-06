"""SQLite 歷史紀錄"""
import sqlite3
import os
import json
from datetime import datetime

DB_PATH = os.environ.get("DB_PATH", "history.db")


class Database:
    def __init__(self):
        self._init_db()

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

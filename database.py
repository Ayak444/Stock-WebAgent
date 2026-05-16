import os
import json
from datetime import datetime
import pandas as pd
from supabase import create_client, Client

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

class Database:
    def __init__(self):
        self.supabase: Client = None
        if SUPABASE_URL and SUPABASE_KEY:
            self.supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        else:
            print("警告：未設定 SUPABASE_URL 或 SUPABASE_KEY")

    def save_analysis(self, results: list):
        if not self.supabase: return
        records = []
        for r in results:
            records.append({
                "ticker": r.get('ticker', ''),
                "name": r.get('name', ''),
                "price": float(r.get('price', 0)),
                "score": int(r.get('score', 0)),
                "advice": r.get('advice', ''),
                "pl_percent": float(r.get('pl', 0)),
                "signals": r.get('signals', [])
            })
        if records:
            try:
                self.supabase.table("analysis_history").insert(records).execute()
            except Exception as e:
                print(f"Save analysis error: {e}")

    def get_history(self, ticker=None, limit=100):
        if not self.supabase: return []
        try:
            query = self.supabase.table("analysis_history").select("*").order("id", desc=True)
            if ticker:
                query = query.eq("ticker", ticker)
            res = query.limit(limit).execute()
            return res.data
        except Exception as e:
            print(f"Get history error: {e}")
            return []

    def get_all_tickers(self):
        if not self.supabase: return []
        try:
            res = self.supabase.table("analysis_history").select("ticker, name").execute()
            seen = set()
            result = []
            for r in res.data:
                if r['ticker'] not in seen:
                    seen.add(r['ticker'])
                    result.append({"ticker": r['ticker'], "name": r['name']})
            return result
        except Exception as e:
            print(f"Get tickers error: {e}")
            return []

    def save_news_analysis(self, item: dict):
        if not self.supabase: return
        try:
            record = {
                "source": item.get('source', ''),
                "title": item.get('title', ''),
                "sentiment": item.get('sentiment', ''),
                "summary": item.get('summary', ''),
                "link": item.get('link', '')
            }
            self.supabase.table("news_analysis").insert(record).execute()
        except Exception as e:
            print(f"Save news error: {e}")

    def save_kline_batch(self, df: pd.DataFrame, ticker: str):
        if not self.supabase or df.empty: return
        try:
            records = []
            for date, row in df.iterrows():
                records.append({
                    "ticker": ticker,
                    "date": date.strftime('%Y-%m-%d'),
                    "open": float(row['Open']),
                    "high": float(row['High']),
                    "low": float(row['Low']),
                    "close": float(row['Close']),
                    "volume": int(row['Volume'])
                })
            self.supabase.table("daily_kline").upsert(records).execute()
        except Exception as e:
            print(f"Save kline error: {e}")

    def get_kline(self, ticker: str, days: int) -> pd.DataFrame:
        if not self.supabase: return pd.DataFrame()
        try:
            res = self.supabase.table("daily_kline").select("*").eq("ticker", ticker).order("date", desc=True).limit(days).execute()
            if not res.data: return pd.DataFrame()
            df = pd.DataFrame(res.data)
            df['date'] = pd.to_datetime(df['date'])
            df = df.sort_values('date').set_index('date')
            df = df[['open', 'high', 'low', 'close', 'volume']]
            df.columns = ['Open', 'High', 'Low', 'Close', 'Volume']
            return df
        except Exception as e:
            print(f"Get kline error: {e}")
            return pd.DataFrame()

    def save_portfolio(self, user_id: str, portfolio_list: list):
        if not self.supabase: return
        try:
            self.supabase.table("portfolios").delete().eq("user_id", user_id).execute()
            records = []
            for p in portfolio_list:
                records.append({
                    "user_id": user_id,
                    "asset_name": p['code'],
                    "asset_type": p['type'],
                    "amount": float(p['shares'] or 0),
                    "avg_price": float(p['cost'] or 0)
                })
            if records:
                self.supabase.table("portfolios").insert(records).execute()
        except Exception as e:
            print(e)

    def get_portfolio(self, user_id: str):
        if not self.supabase: return []
        res = self.supabase.table("portfolios").select("*").eq("user_id", user_id).execute()
        return [{"code": r['asset_name'], "type": r['asset_type'], "cost": str(r['avg_price']), "shares": str(r['amount'])} for r in res.data]

    def save_stress_test_record(self, user_id: str, scenario: str, result_data: dict):
        if not self.supabase: return
        data = {
            "user_id": user_id,
            "scenario": scenario,
            "result": result_data
        }
        try:
            self.supabase.table("stress_tests").insert(data).execute()
        except Exception as e:
            print(e)

    def get_stress_test_history(self, user_id: str, limit: int = 50):
        if not self.supabase: return []
        try:
            res = self.supabase.table("stress_tests").select("*").eq("user_id", user_id).order("created_at", desc=True).limit(limit).execute()
            return res.data
        except Exception as e:
            print(e)
            return []
    
    def get_or_create_user(self, email: str, name: str):
        if not self.supabase: return None
        try:
            res = self.supabase.table("users").select("*").eq("email", email).execute()
            if res.data:
                return res.data[0]
            
            new_user = {"email": email, "name": name, "virtual_balance": 500000}
            res = self.supabase.table("users").insert(new_user).execute()
            return res.data[0]
        except Exception as e:
            print(f"Error in get_or_create_user: {e}")
            return None
    
    def record_trade(self, user_id: str, action: str, ticker: str, amount: float, price: float):
        if not self.supabase: return False
        try:
            total = amount * price
            trade_data = {
                "user_id": user_id,
                "action": action,
                "asset_name": ticker,
                "amount": amount,
                "price": price,
                "total": total
            }
            self.supabase.table("trades").insert(trade_data).execute()

            user_res = self.supabase.table("users").select("virtual_balance").eq("id", user_id).execute()
            current_balance = float(user_res.data[0]['virtual_balance'])
            new_balance = current_balance - total if action == '買入' else current_balance + total
            
            self.supabase.table("users").update({"virtual_balance": new_balance}).eq("id", user_id).execute()
            return True
        except Exception as e:
            print(f"Trade Error: {e}")
            return False
    
    def create_user(self, email, password, name):
        if not self.supabase: 
            raise Exception("Supabase 連線失敗：遺失 SUPABASE_URL 或 SUPABASE_KEY")
            
        data = {
            "email": email,
            "name": name,
            "password_hash": password,
            "virtual_balance": 500000
        }
        
        try:
            res = self.supabase.table("users").insert(data).execute()
            if not res.data:
                raise Exception("寫入成功但未回傳資料，請檢查 Supabase RLS 設定")
            return res.data[0]
        except Exception as e:
            print(f"\\n[⚠️ 註冊錯誤] {str(e)}\\n")
            raise Exception(f"資料庫錯誤: {str(e)}")

    def verify_user(self, email, password):
        if not self.supabase: return None
        res = self.supabase.table("users").select("*").eq("email", email).execute()
        if res.data:
            user = res.data[0]
            if user['password_hash'] == password:
                return user
        return None

    def search_corporate_reports(self, query: str, limit: int = 3):
        if not self.supabase:
            return []
        try:
            res = self.supabase.table("corporate_reports").select("content").text_search("content", query).limit(limit).execute()
            if res.data:
                return [r["content"] for r in res.data]
        except Exception as e:
            print(f"RAG Search Error: {e}")
        return []
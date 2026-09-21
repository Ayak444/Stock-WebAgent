import os
import json
import base64
import hashlib
import hmac
import secrets
from datetime import datetime
import pandas as pd
from supabase import create_client, Client

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

PASSWORD_SCHEME = "pbkdf2_sha256"
PASSWORD_ITERATIONS = 600_000


def _hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS
    )
    return "$".join((
        PASSWORD_SCHEME,
        str(PASSWORD_ITERATIONS),
        base64.b64encode(salt).decode("ascii"),
        base64.b64encode(digest).decode("ascii"),
    ))


def _verify_password(password: str, stored: str) -> tuple[bool, bool]:
    """Return (matches, needs_upgrade), supporting legacy plaintext rows."""
    if not stored.startswith(f"{PASSWORD_SCHEME}$"):
        return hmac.compare_digest(password, stored), True
    try:
        _, iterations, salt_b64, digest_b64 = stored.split("$", 3)
        actual = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            base64.b64decode(salt_b64),
            int(iterations),
        )
        return hmac.compare_digest(actual, base64.b64decode(digest_b64)), False
    except (ValueError, TypeError):
        return False, False


def _public_user(user: dict) -> dict:
    return {key: value for key, value in user.items() if key != "password_hash"}

class Database:
    def __init__(self):
        self.supabase: Client = None
        if SUPABASE_URL and SUPABASE_KEY:
            self.supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        else:
            print("警告：未設定 SUPABASE_URL 或 SUPABASE_KEY")

    def check_auth_store(self) -> dict:
        if not self.supabase:
            return {"ok": False, "reason": "not_configured"}
        try:
            self.supabase.table("users").select("id").limit(1).execute()
            return {"ok": True, "reason": "ready"}
        except Exception as exc:
            print(f"Auth store health check failed: {type(exc).__name__}")
            return {"ok": False, "reason": "query_failed"}

    def _require_holder_alert_store(self):
        if not self.supabase:
            raise RuntimeError("holder_alert_store_unavailable")
        return self.supabase

    def acquire_holder_alert_lock(self, owner: str, now: datetime) -> bool:
        try:
            result = self._require_holder_alert_store().rpc("claim_holder_alert_run", {
                "p_owner": owner, "p_now": now.isoformat(), "p_lease_seconds": 900,
            }).execute()
            return bool(result.data)
        except Exception as exc:
            raise RuntimeError("holder_alert_store_unavailable") from exc

    def release_holder_alert_lock(self, owner: str) -> bool:
        try:
            result = self._require_holder_alert_store().rpc(
                "release_holder_alert_run", {"p_owner": owner}
            ).execute()
            return bool(result.data)
        except Exception as exc:
            raise RuntimeError("holder_alert_store_unavailable") from exc

    def upsert_holder_alert_snapshot(self, snapshot: dict) -> None:
        try:
            self._require_holder_alert_store().table("holder_alert_snapshots").upsert(
                snapshot, on_conflict="ticker,holder_date"
            ).execute()
        except Exception as exc:
            raise RuntimeError("holder_alert_store_unavailable") from exc

    def get_holder_alert_history(self, ticker: str, limit: int = 3) -> list:
        try:
            result = (
                self._require_holder_alert_store().table("holder_alert_snapshots")
                .select("holder_date,large_holder_ratio")
                .eq("ticker", ticker).order("holder_date", desc=True)
                .limit(max(1, min(int(limit), 3))).execute()
            )
            return list(result.data or [])
        except Exception as exc:
            raise RuntimeError("holder_alert_store_unavailable") from exc

    def set_holder_alert_state(self, key: str, value: dict, now: datetime) -> None:
        try:
            self._require_holder_alert_store().table("holder_alert_state").upsert({
                "state_key": key,
                "state_value": value,
                "updated_at": now.isoformat(),
            }, on_conflict="state_key").execute()
        except Exception as exc:
            raise RuntimeError("holder_alert_store_unavailable") from exc

    def get_holder_alert_state(self, key: str) -> dict:
        try:
            result = (
                self._require_holder_alert_store().table("holder_alert_state")
                .select("state_value").eq("state_key", key).limit(1).execute()
            )
            return dict(result.data[0].get("state_value") or {}) if result.data else {}
        except Exception as exc:
            raise RuntimeError("holder_alert_store_unavailable") from exc

    def has_recent_sent_holder_alert(self, ticker: str, since: datetime) -> bool:
        try:
            result = (
                self._require_holder_alert_store().table("holder_alert_events")
                .select("event_key").eq("ticker", ticker).eq("status", "sent")
                .gte("sent_at", since.isoformat()).limit(1).execute()
            )
            return bool(result.data)
        except Exception as exc:
            raise RuntimeError("holder_alert_store_unavailable") from exc

    def claim_holder_alert_event(
        self, event_key: str, ticker: str, holder_date: str, now: datetime
    ) -> bool:
        try:
            result = self._require_holder_alert_store().rpc("claim_holder_alert_event", {
                "p_event_key": event_key,
                "p_ticker": ticker,
                "p_holder_date": holder_date,
                "p_now": now.isoformat(),
            }).execute()
            return bool(result.data)
        except Exception as exc:
            raise RuntimeError("holder_alert_store_unavailable") from exc

    def mark_holder_alert_sent(self, event_key: str, now: datetime) -> None:
        try:
            result = self._require_holder_alert_store().table("holder_alert_events").update({
                "status": "sent", "sent_at": now.isoformat(),
                "retry_after": None, "updated_at": now.isoformat(),
            }).eq("event_key", event_key).eq("status", "claimed").execute()
            if not result.data:
                raise RuntimeError("event_claim_lost")
        except Exception as exc:
            raise RuntimeError("holder_alert_store_unavailable") from exc

    def mark_holder_alert_failed(
        self, event_key: str, now: datetime, retry_after: datetime
    ) -> None:
        try:
            result = self._require_holder_alert_store().table("holder_alert_events").update({
                "status": "failed", "retry_after": retry_after.isoformat(),
                "updated_at": now.isoformat(),
            }).eq("event_key", event_key).eq("status", "claimed").execute()
            if not result.data:
                raise RuntimeError("event_claim_lost")
        except Exception as exc:
            raise RuntimeError("holder_alert_store_unavailable") from exc

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
    
    def get_trade_history(self, user_id: str, limit: int = 50):
        """讀取交易歷史"""
        if not self.supabase: return []
        try:
            res = self.supabase.table("trades").select("*").eq("user_id", user_id).order("created_at", desc=True).limit(limit).execute()
            return res.data
        except Exception as e:
            print(f"Get trade history error: {e}")
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
            
        if len(password) < 8:
            raise ValueError("密碼至少需要 8 個字元")

        data = {
            "email": email.strip().lower(),
            "name": name,
            "password_hash": _hash_password(password),
            "virtual_balance": 500000
        }
        
        try:
            res = self.supabase.table("users").insert(data).execute()
            if not res.data:
                raise Exception("寫入成功但未回傳資料，請檢查 Supabase RLS 設定")
            return _public_user(res.data[0])
        except Exception as e:
            print(f"\\n[⚠️ 註冊錯誤] {str(e)}\\n")
            raise Exception(f"資料庫錯誤: {str(e)}")

    def verify_user(self, email, password):
        if not self.supabase:
            raise RuntimeError("登入資料庫尚未設定")
        try:
            res = self.supabase.table("users").select("*").eq(
                "email", email.strip().lower()
            ).limit(1).execute()
        except Exception as exc:
            raise RuntimeError("登入資料庫查詢失敗") from exc
        if res.data:
            user = res.data[0]
            matches, needs_upgrade = _verify_password(
                password, str(user.get("password_hash", ""))
            )
            if matches:
                if needs_upgrade:
                    try:
                        self.supabase.table("users").update({
                            "password_hash": _hash_password(password)
                        }).eq("id", user["id"]).execute()
                    except Exception:
                        pass
                return _public_user(user)
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

    def save_backtest_results(self, records: list):
        """儲存背景預算好的回測結果"""
        if not self.supabase or not records: return
        try:
            self.supabase.table("backtest_results").upsert(records).execute()
        except Exception as e:
            print(f"Save backtest results error: {e}")

    def get_backtest_results(self, symbol: str, strategy_name: str = 'default'):
        """讀取預先計算好的回測結果"""
        if not self.supabase: return None
        try:
            res = self.supabase.table("backtest_results").select("*").eq("symbol", symbol).eq("strategy_name", strategy_name).execute()
            if res.data:
                return res.data[0]
        except Exception as e:
            print(f"Get backtest results error: {e}")
        return None

import os
import json
import base64
import hashlib
import hmac
import secrets
import logging
import re
import time
from datetime import datetime
import pandas as pd
from supabase import create_client, Client, ClientOptions

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

PASSWORD_SCHEME = "pbkdf2_sha256"
PASSWORD_ITERATIONS = 600_000
logger = logging.getLogger(__name__)

# Only these static labels may reach notification-store diagnostics. Never log
# exception messages or PostgREST details: they can contain user settings.
_ACCOUNT_STORE_CODES = {
    "42P01": "missing_schema", "42703": "missing_schema",
    "PGRST200": "missing_schema", "PGRST202": "missing_schema",
    "PGRST204": "missing_schema", "PGRST205": "missing_schema",
    "42501": "permission_auth", "28000": "permission_auth",
    "28P01": "permission_auth", "PGRST301": "permission_auth",
    "PGRST302": "permission_auth", "PGRST303": "permission_auth",
    "401": "permission_auth", "403": "permission_auth",
    "08000": "connectivity", "08001": "connectivity",
    "08003": "connectivity", "08004": "connectivity",
    "08006": "connectivity", "08007": "connectivity",
    "08P01": "connectivity", "PGRST000": "connectivity",
    "PGRST001": "connectivity", "PGRST002": "connectivity",
    "PGRST003": "connectivity",
}
_ACCOUNT_STORE_EXCEPTION_TYPES = frozenset({
    "APIError", "RuntimeError", "HTTPError", "HTTPStatusError",
    "RequestException", "ConnectionError", "Timeout", "TimeoutException",
    "ConnectError", "ConnectTimeout", "ReadTimeout", "WriteTimeout",
    "PoolTimeout", "NetworkError", "ReadError", "WriteError",
    "RemoteProtocolError",
})
_ACCOUNT_STORE_NETWORK_TYPES = _ACCOUNT_STORE_EXCEPTION_TYPES - {
    "APIError", "RuntimeError", "HTTPError", "HTTPStatusError",
}


def _log_account_volume_store_failure(operation: str, exc: Exception) -> None:
    operation = operation if operation in {"probe", "get", "save"} else "unknown"
    exception_type = type(exc).__name__
    exception_type = (exception_type if exception_type in
                      _ACCOUNT_STORE_EXCEPTION_TYPES else "unknown")
    code = getattr(exc, "code", None)
    code = str(code) if isinstance(code, (str, int)) else "unknown"
    code = code if code in _ACCOUNT_STORE_CODES else "unknown"
    category = _ACCOUNT_STORE_CODES.get(code, "unknown")
    if category == "unknown":
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status in (401, 403):
            code, category = str(status), "permission_auth"
        elif exception_type in _ACCOUNT_STORE_NETWORK_TYPES:
            category = "connectivity"
    logger.error(
        "account_volume_store operation=%s exception_type=%s code=%s category=%s credential_kind=%s",
        operation, exception_type, code, category, backend_credential_kind(SUPABASE_KEY),
    )


class DuplicateEmailError(ValueError):
    """The email already belongs to an account."""


class RegistrationStoreError(RuntimeError):
    """Registration could not write to the account database."""


class VirtualTradeRejected(ValueError):
    """Only pre-approved static virtual-trade validation messages."""


def account_store_failure_category(exc):
    if isinstance(exc, AccountAlertStoreError):
        return exc.category
    code = str(getattr(exc, "code", ""))
    status = getattr(getattr(exc, "response", None), "status_code", None)
    if code in {"401", "PGRST301", "PGRST302", "PGRST303"}:
        return "key_rejected"
    category = _ACCOUNT_STORE_CODES.get(code, "unknown")
    if category != "unknown":
        return category
    if status == 401:
        return "key_rejected"
    if category == "unknown" and status == 403:
        return "permission_auth"
    if category == "unknown" and (type(exc).__name__ in _ACCOUNT_STORE_NETWORK_TYPES or
                                   status in {429, 500, 502, 503, 504}):
        return "connectivity"
    return category


class AccountAlertStoreError(RuntimeError):
    def __init__(self, category="unknown"):
        self.category = category
        super().__init__("account_alert_store_unavailable")


def backend_credential_kind(value):
    """Return an allowlisted label only; this is type detection, not validation."""
    if not value:
        return "not_configured"
    if value.startswith("sb_secret_"):
        return "backend_secret"
    if value.startswith("sb_publishable_"):
        return "public_key"
    try:
        segment = value.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4)))
        return {"service_role": "legacy_service_role", "anon": "public_key"}.get(
            claims.get("role"), "unknown")
    except Exception:
        return "unknown"


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
            self.supabase = create_client(SUPABASE_URL, SUPABASE_KEY,
                                          options=ClientOptions(postgrest_client_timeout=8))
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

    def check_private_account_store(self):
        try:
            response = self._require_account_store().rpc("private_account_capability", {}).execute()
            return {"ready": response.data is True,
                    "reason": "ready" if response.data is True else "permission_auth",
                    "credential_kind": backend_credential_kind(SUPABASE_KEY)}
        except Exception as exc:
            return {"ready": False, "reason": account_store_failure_category(exc),
                    "credential_kind": backend_credential_kind(SUPABASE_KEY)}

    def _require_account_store(self):
        if not self.supabase:
            raise AccountAlertStoreError("not_configured")
        return self.supabase

    def check_account_volume_store(self) -> bool:
        try:
            self._require_account_store().table("account_volume_alert_settings").select(
                "user_id,tickers,webhook_ciphertext,updated_at"
            ).limit(0).execute()
            return True
        except Exception as exc:
            _log_account_volume_store_failure("probe", exc)
            return False

    def get_public_user(self, user_id: str) -> dict | None:
        try:
            result = self._require_account_store().table("users").select(
                "id,name,email,virtual_balance,created_at"
            ).eq("id", user_id).limit(1).execute()
            return dict(result.data[0]) if result.data else None
        except Exception as exc:
            raise RuntimeError("account_alert_store_unavailable") from exc

    def get_account_volume_settings(self, user_id: str) -> dict:
        # Retry only an idempotent read, once, for transient transport failures.
        for attempt in range(2):
            try:
                result = self._require_account_store().table("account_volume_alert_settings").select(
                    "tickers,webhook_ciphertext"
                ).eq("user_id", user_id).limit(1).execute()
                return dict(result.data[0]) if result.data else {"tickers": [], "webhook_ciphertext": None}
            except Exception as exc:
                category = account_store_failure_category(exc)
                if category == "connectivity" and attempt == 0:
                    time.sleep(0.15)
                    continue
                _log_account_volume_store_failure("get", exc)
                raise AccountAlertStoreError(category) from None

    def save_account_volume_settings(self, user_id: str, settings: dict) -> None:
        try:
            self._require_account_store().table("account_volume_alert_settings").upsert(
                {"user_id": user_id, **settings}, on_conflict="user_id"
            ).execute()
        except Exception as exc:
            _log_account_volume_store_failure("save", exc)
            raise AccountAlertStoreError(account_store_failure_category(exc)) from None

    def list_account_volume_settings(self) -> list[dict]:
        try:
            client = self._require_account_store()
            rows: list[dict] = []
            page_size = 500
            for start in range(0, 100000, page_size):
                result = client.table("account_volume_alert_settings").select(
                    "user_id,tickers,webhook_ciphertext"
                ).range(start, start + page_size - 1).execute()
                batch = list(result.data or [])
                rows.extend(item for item in batch if item.get("webhook_ciphertext"))
                if len(batch) < page_size:
                    return rows
            raise RuntimeError("account_alert_store_unavailable")
        except Exception as exc:
            raise RuntimeError("account_alert_store_unavailable") from exc

    def claim_account_volume_event(self, user_id: str, ticker: str, market_date: str, now: datetime) -> bool:
        try:
            result = self._require_account_store().rpc("claim_account_volume_event", {
                "p_user_id": user_id, "p_ticker": ticker,
                "p_market_date": market_date, "p_now": now.isoformat(),
            }).execute()
            return bool(result.data)
        except Exception as exc:
            raise RuntimeError("account_alert_store_unavailable") from exc

    def finish_account_volume_event(self, user_id: str, ticker: str, market_date: str,
                                    status: str, now: datetime) -> None:
        if status not in {"sent", "failed"}:
            raise ValueError("invalid_event_status")
        try:
            result = self._require_account_store().table("account_volume_alert_events").update({
                "status": status, "sent_at": now.isoformat() if status == "sent" else None,
                "updated_at": now.isoformat(),
            }).eq("user_id", user_id).eq("ticker", ticker).eq(
                "market_date", market_date
            ).eq("status", "claimed").execute()
            if not result.data:
                raise RuntimeError("event_claim_lost")
        except Exception as exc:
            raise RuntimeError("account_alert_store_unavailable") from exc

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
        try:
            response = self._require_account_store().rpc("replace_watch_portfolio", {
                "p_user_id": user_id, "p_items": portfolio_list,
            }).execute()
            if response.data is not True:
                raise RuntimeError("private_store_unavailable")
        except Exception:
            raise RuntimeError("private_store_unavailable") from None

    def get_portfolio(self, user_id: str):
        try:
            res = self._require_account_store().table("portfolios").select("*").eq("user_id", user_id).execute()
            return [{"code": r['asset_name'], "type": r['asset_type'], "cost": str(r['avg_price']), "shares": str(r['amount'])} for r in res.data]
        except Exception:
            raise RuntimeError("private_store_unavailable") from None

    def save_stress_test_record(self, user_id: str, scenario: str, result_data: dict):
        data = {
            "user_id": user_id,
            "scenario": scenario,
            "result": result_data
        }
        try:
            self._require_account_store().table("stress_tests").insert(data).execute()
        except Exception:
            raise RuntimeError("private_store_unavailable") from None

    def get_stress_test_history(self, user_id: str, limit: int = 50):
        try:
            res = self._require_account_store().table("stress_tests").select("*").eq("user_id", user_id).order("created_at", desc=True).limit(limit).execute()
            return res.data
        except Exception:
            raise RuntimeError("private_store_unavailable") from None
    
    def get_trade_history(self, user_id: str, limit: int = 50):
        """讀取交易歷史"""
        try:
            res = self._require_account_store().table("trades").select("*").eq("user_id", user_id).order("created_at", desc=True).limit(limit).execute()
            return res.data
        except Exception:
            raise RuntimeError("private_store_unavailable") from None

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
        try:
            response = self._require_account_store().rpc("execute_virtual_trade", {
                "p_user_id": user_id, "p_action": action, "p_ticker": ticker,
                "p_amount": str(amount), "p_price": str(price),
            }).execute()
            data = response.data
            if not isinstance(data, dict) or data.get("ok") is not True:
                code = data.get("code") if isinstance(data, dict) else None
                message = {"insufficient_balance": "模擬餘額不足", "insufficient_position": "模擬交易持股不足；手動持股清單不能用來賣出",
                           "invalid_trade": "交易輸入無效", "account_missing": "帳號不存在"}.get(code)
                if message:
                    raise VirtualTradeRejected(message)
                raise RuntimeError("private_store_unavailable")
            return data
        except VirtualTradeRejected:
            raise
        except Exception:
            raise RuntimeError("private_store_unavailable") from None
    
    def create_user(self, email, password, name):
        if not isinstance(name, str) or not name.strip():
            raise ValueError("請輸入名稱")
        name = name.strip()
        if not self.supabase:
            raise RegistrationStoreError("not_configured")
            
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
                raise RegistrationStoreError("empty_insert_result")
            return _public_user(res.data[0])
        except RegistrationStoreError:
            raise
        except Exception as exc:
            code = getattr(exc, "code", None)
            if code == "23505":
                raise DuplicateEmailError("此電子郵件已註冊") from None
            safe_code = code if isinstance(code, str) and re.fullmatch(r"[A-Z0-9]{5}", code) else "unknown"
            logger.error("Registration insert failed: type=%s code=%s", type(exc).__name__, safe_code)
            raise RegistrationStoreError("insert_failed") from None

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

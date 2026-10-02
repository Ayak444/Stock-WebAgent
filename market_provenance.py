"""Shared quote and official institutional provenance for sync/async callers."""
from __future__ import annotations

import math
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime, timezone, timedelta

import requests

TW_TZ = timezone(timedelta(hours=8))
TPEX_INSTITUTIONAL_URL = "https://www.tpex.org.tw/openapi/v1/tpex_3insti_daily_trading"
TWSE_INSTITUTIONAL_URL = "https://www.twse.com.tw/rwd/zh/fund/T86"
TWSE_CHIP_EXECUTOR = ThreadPoolExecutor(max_workers=3, thread_name_prefix="twse-institutional")
ORDINARY_OR_ETF_CODE = r"(?:[1-9][0-9]{3}|00[0-9]{3,4}[A-Z]?)"


def finite_number(value, positive=False):
    try:
        number = float(str(value).replace(",", "").replace("−", "-").strip())
        return number if math.isfinite(number) and (not positive or number > 0) else None
    except (TypeError, ValueError):
        return None


def unavailable_quote(reason="source_unavailable"):
    return {"available": False, "price": None, "change": None, "pct_change": None,
            "reason": reason, "source": "Yahoo Finance daily chart", "as_of": None}


def macro_quote(payload):
    try:
        chart = payload['chart']['result'][0]
        closes = chart['indicators']['quote'][0]['close']
        timestamps = chart['timestamp']
        if not closes or not timestamps or len(closes) != len(timestamps):
            return unavailable_quote("missing_quote")
        price = finite_number(closes[-1], positive=True)
        ts = finite_number(timestamps[-1], positive=True)
        if price is None or ts is None:
            return unavailable_quote("invalid_quote")
        now = datetime.now(timezone.utc).timestamp()
        if not 0 <= now - ts <= 10 * 86400:
            return unavailable_quote("stale_or_future_quote")
        previous = finite_number(closes[-2], positive=True) if len(closes) > 1 else None
        change = price - previous if previous is not None else None
        return {"available": True, "price": round(price,2),
                "change": round(change,2) if change is not None else None,
                "pct_change": round(change / previous * 100,2) if previous else None,
                "reason": None if previous else "previous_quote_unavailable",
                "source": "Yahoo Finance daily chart",
                "as_of": datetime.fromtimestamp(ts, timezone.utc).isoformat()}
    except (TypeError, ValueError, KeyError, IndexError, OverflowError):
        return unavailable_quote("invalid_response")


def official_date(value):
    raw = str(value or "").strip().replace("/", "").replace("-", "")
    if len(raw) == 7 and raw.isdigit():
        raw = str(int(raw[:3]) + 1911) + raw[3:]
    try:
        date = datetime.strptime(raw, "%Y%m%d").date()
    except ValueError:
        return None
    today = datetime.now(TW_TZ).date()
    return date.isoformat() if 0 <= (today - date).days <= 7 else None


def normalize_twse_institutional(payload):
    if not isinstance(payload, dict) or payload.get("stat") != "OK":
        return {}
    as_of = official_date(payload.get("date"))
    headers = [str(field).replace(" ", "") for field in payload.get("fields", [])]
    foreign_name = "外陸資買賣超股數(不含外資自營商)"
    if not as_of or foreign_name not in headers or "投信買賣超股數" not in headers:
        return {}
    fi, ti = headers.index(foreign_name), headers.index("投信買賣超股數")
    code_index = headers.index("證券代號") if "證券代號" in headers else 0
    result = {}
    for row in payload.get("data", []):
        if len(row) <= max(fi, ti, code_index):
            continue
        code = str(row[code_index]).strip()
        foreign, trust = finite_number(row[fi]), finite_number(row[ti])
        if not re.fullmatch(ORDINARY_OR_ETF_CODE, code) or foreign is None or trust is None:
            continue
        result[code + ".TW"] = {"Foreign": foreign, "Trust": trust, "unit": "shares",
                                 "as_of": as_of, "source": TWSE_INSTITUTIONAL_URL, "market": "上市"}
    return result


def normalize_tpex_institutional(rows):
    result = {}
    for row in rows if isinstance(rows, list) else []:
        clean = {str(key).replace(" ", ""): value for key, value in row.items()}
        code = str(clean.get("SecuritiesCompanyCode", "")).strip()
        as_of = official_date(clean.get("Date"))
        foreign = finite_number(clean.get("ForeignInvestorsIncludeMainlandAreaInvestors-Difference"))
        trust = finite_number(clean.get("SecuritiesInvestmentTrustCompanies-Difference"))
        if not re.fullmatch(ORDINARY_OR_ETF_CODE, code) or not as_of or foreign is None or trust is None:
            continue
        result[code + ".TWO"] = {"Foreign": foreign, "Trust": trust, "unit": "shares",
                                  "as_of": as_of, "source": TPEX_INSTITUTIONAL_URL, "market": "上櫃"}
    return result


class InstitutionalProvider:
    def __init__(self):
        self._lock = threading.Lock()
        self._cache = None
        self._expires = 0
        self._pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="institutional")

    @staticmethod
    def _json(url):
        response = requests.get(url, timeout=(2,4), headers={"User-Agent": "Stock-WebAgent"})
        response.raise_for_status()
        return response.json()

    def _twse(self):
        def load(offset):
            date = (datetime.now(TW_TZ) - timedelta(days=offset)).strftime("%Y%m%d")
            try:
                return normalize_twse_institutional(self._json(
                    f"{TWSE_INSTITUTIONAL_URL}?date={date}&selectType=ALL&response=json"))
            except Exception:
                return {}
        futures = [TWSE_CHIP_EXECUTOR.submit(load, offset) for offset in range(8)]
        done, pending = wait(futures, timeout=8)
        for future in pending:
            future.cancel()
        candidates = [future.result() for future in done]
        candidates = [rows for rows in candidates if rows]
        return max(candidates, key=lambda rows: max(row['as_of'] for row in rows.values()), default={})

    def get(self):
        with self._lock:
            if self._cache is not None and time.monotonic() < self._expires:
                return dict(self._cache)
            futures = {"上市": self._pool.submit(self._twse),
                       "上櫃": self._pool.submit(lambda: normalize_tpex_institutional(self._json(TPEX_INSTITUTIONAL_URL)))}
            wait(futures.values(), timeout=12)
            result, coverage = {}, {}
            for market, future in futures.items():
                try:
                    if not future.done():
                        future.cancel()
                        raise TimeoutError
                    rows = future.result()
                except Exception:
                    rows = {}
                result.update(rows)
                coverage[market] = {"available": bool(rows), "as_of": max((r["as_of"] for r in rows.values()), default=None),
                                    "reason": None if rows else "official_source_unavailable"}
            result["_coverage"] = coverage
            self._cache, self._expires = result, time.monotonic() + 300
            return dict(result)


institutional_provider = InstitutionalProvider()

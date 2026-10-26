"""Sourced Taiwan price metrics and deterministic, explicitly conditional valuation.

Importing this module never fetches data. Official YTD, vendor trailing EPS and
an eligible four-quarter approximation are deliberately different sections.
"""
from __future__ import annotations

import calendar
import json
import math
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

import requests

from market_insights import (
    TWSE_COMPANY_URL, TPEX_COMPANY_URL, TWSE_DAILY_URL, TPEX_DAILY_URL,
    TWSE_HOLIDAY_URL, normalize_taiwan_ticker, normalize_tpex_companies,
)

TAIPEI = timezone(timedelta(hours=8))
MAX_WEIGHTED_SHARE_RATIO = 1.01
OFFICIAL = {
    "TW": {"companies": TWSE_COMPANY_URL, "quote": TWSE_DAILY_URL,
           "pe": "https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL",
           "eps": "https://openapi.twse.com.tw/v1/opendata/t187ap06_L_ci"},
    "TWO": {"companies": TPEX_COMPANY_URL, "quote": TPEX_DAILY_URL,
            "pe": "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_peratio_analysis",
            "eps": "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap14_O"},
}


def number(value):
    if isinstance(value, bool):
        return None
    try:
        result = float(str(value).replace(",", "").strip())
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def iso_date(value):
    raw = str(value or "").strip()
    try:
        if re.fullmatch(r"\d{7}", raw):
            raw = f"{int(raw[:3]) + 1911}-{raw[3:5]}-{raw[5:7]}"
        elif re.fullmatch(r"\d{8}", raw):
            raw = f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
        elif re.fullmatch(r"\d{2,3}/\d{2}/\d{2}", raw):
            year, month, day = raw.split("/")
            raw = f"{int(year) + 1911}-{month}-{day}"
        return date.fromisoformat(raw).isoformat()
    except ValueError:
        return None


def finite_ratio(numerator, denominator):
    if numerator is None or denominator is None or denominator <= 0:
        return None
    result = numerator / denominator
    return result if math.isfinite(result) else None


def section(value=None, *, reason=None, **meta):
    return {"value": value, "status": "available" if value is not None else "unavailable",
            "reason_code": reason, "published_at": None, **meta}


def ordinary_company(code, profile):
    """Require a company-profile match, not merely a Yahoo suffix or price row."""
    name = str((profile or {}).get("公司名稱", ""))
    industry = str((profile or {}).get("產業別", "")).strip().zfill(2)
    return bool(profile and re.fullmatch(r"[1-9]\d{3}", code) and not code.startswith("91")
                and re.fullmatch(r"\d{2}", industry) and industry not in ("00", "91")
                and not any(word in name.upper() for word in ("ETF", "REIT", "特別股", "受益", "存託", "TDR", "-DR")))


def load_calendar_exceptions():
    """Read only this versioned, reviewed public-data file; never fetch notices."""
    try:
        payload = json.loads(Path(__file__).with_name("market_calendar_exceptions.json").read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, ValueError):
        return {}


def validated_calendar_exceptions(payload, market, today):
    """Validate curated provenance structurally, including evidence for each scope.

    This does not independently verify notice contents. The versioned record is
    added only after human/agent source research; its verified_at is date precision.
    """
    if (not isinstance(payload, dict) or type(payload.get("schemaVersion")) is not int or payload.get("schemaVersion") != 1
            or not isinstance(payload.get("version"), str)
            or not re.fullmatch(r"[A-Za-z0-9._-]{1,80}", payload["version"])
            or not isinstance(payload.get("records"), list) or len(payload["records"]) > 256):
        return []
    allowed_hosts = {"TW": {"www.twse.com.tw", "twse.com.tw", "stock.concords.com.tw"},
                     "TWO": {"www.tpex.org.tw", "tpex.org.tw", "stock.concords.com.tw"}}
    accepted = []
    for row in payload["records"]:
        if not isinstance(row, dict):
            continue
        day, announced, verified = [iso_date(row.get(key)) for key in ("date", "announced_at", "verified_at")]
        scopes, sources = row.get("market_scope"), row.get("sources")
        if (not day or not announced or not verified or announced > day or announced > verified
                or verified > today.isoformat() or row.get("kind") != "full_day_closure"
                or not isinstance(row.get("reason"), str) or not row["reason"].strip()
                or len(row["reason"]) > 500 or not isinstance(scopes, list) or not scopes
                or any(not isinstance(scope, str) or scope not in allowed_hosts for scope in scopes) or market not in scopes
                or not isinstance(sources, list)):
            continue
        valid_sources, covered = [], set()
        for source in sources:
            if not isinstance(source, dict) or not isinstance(source.get("source_url"), str):
                continue
            url, source_scopes = source["source_url"], source.get("market_scope")
            try:
                parsed = urlsplit(url)
                valid_url = (parsed.scheme == "https" and parsed.username is None and parsed.password is None
                             and parsed.port in (None, 443) and parsed.path not in ("", "/")
                             and not any(ord(c) < 32 for c in url))
            except ValueError:
                valid_url = False
            if not valid_url or not isinstance(source_scopes, list) or not source_scopes:
                continue
            supported = [scope for scope in source_scopes if scope in scopes
                         and parsed.hostname in allowed_hosts.get(scope, set())]
            if supported:
                covered.update(supported)
                valid_sources.append({"market_scope": supported, "source_url": url})
        if not set(scopes).issubset(covered):
            continue
        accepted.append({"date": day, "market_scope": scopes, "kind": "full_day_closure",
                         "reason": row["reason"], "announced_at": announced, "verified_at": verified,
                         "sources": valid_sources})
    return accepted


def quote_calendar_evidence(as_of, holiday_rows, now, market="TW", exception_calendar=None):
    """Combine a known annual schedule with explicitly verified full-day closures.

    Default is annual-only for deterministic callers/tests. Production service
    explicitly supplies its versioned exception loader. Matching feeds are never
    evidence of a trading day, and unknown calendars remain unknown.
    """
    result = {"freshness": "unknown", "market": market, "expected_completed_trading_day": None,
              "annual_calendar_source_url": TWSE_HOLIDAY_URL, "exception_version": None,
              "used_exceptions": [], "reason_code": "annual_calendar_unavailable",
              "methodology": "年度休市表＋已逐筆核對的臨時全日休市；未收錄的特殊事件仍可能使最新交易日無法確認"}
    if market not in ("TW", "TWO"):
        result["reason_code"] = "unsupported_calendar_market"
        return result
    if not iso_date(as_of):
        result["reason_code"] = "quote_date_unavailable"
        return result
    local = now.astimezone(TAIPEI)
    valid = [(iso_date(row.get("Date")), str(row.get("Name") or row.get("Description") or ""))
             for row in (holiday_rows or []) if isinstance(row, dict)]
    if not any(day and day.startswith(str(local.year)) for day, _ in valid):
        return result
    holidays = {day for day, title in valid if day and not any(
        token in title for token in ("開始交易", "最後交易", "恢復交易"))}
    exceptions = validated_calendar_exceptions(exception_calendar, market, local.date())
    by_date = {row["date"]: row for row in exceptions}
    if exceptions:
        result["exception_version"] = exception_calendar["version"]
    expected = local.date() if local.hour >= 15 else local.date() - timedelta(days=1)
    for _ in range(30):
        exceptional = by_date.get(expected.isoformat())
        if exceptional:
            result["used_exceptions"].append(exceptional)
        if expected.weekday() < 5 and expected.isoformat() not in holidays and not exceptional:
            break
        expected -= timedelta(days=1)
    else:
        result["reason_code"] = "completed_trading_day_unconfirmed"
        return result
    result["expected_completed_trading_day"] = expected.isoformat()
    result["freshness"] = "fresh" if iso_date(as_of) == expected.isoformat() else "stale"
    result["reason_code"] = "matches_completed_trading_day" if result["freshness"] == "fresh" else "latest_day_unconfirmed"
    return result


def quote_freshness(as_of, holiday_rows, now, market="TW", exception_calendar=None):
    return quote_calendar_evidence(as_of, holiday_rows, now, market, exception_calendar)["freshness"]


def quarterly_ttm(payload, now=None):
    """Validate four standalone quarters; sum is an approximation, never filed TTM."""
    now = now or datetime.now(TAIPEI)
    source = payload.get("source_url")
    meta = {"source": "Yahoo Finance 季度損益表", "source_url": source,
            "fetched_at": payload.get("fetched_at"), "currency": payload.get("currency"),
            "methodology": "最近四個獨立季度 EPS 加總估算；非公司直接公布 TTM",
            "basis": None, "warnings": [], "quarters": [],
            "max_weighted_share_ratio": MAX_WEIGHTED_SHARE_RATIO}
    def unavailable(reason):
        return section(reason=reason, **meta)
    if payload.get("currency") != "TWD":
        return unavailable("eps_currency_unverified")
    rows = sorted(payload.get("quarters", []), key=lambda r: str(r.get("period_end", "")), reverse=True)[:4]
    ends = [iso_date(row.get("period_end")) for row in rows]
    if len(rows) != 4 or None in ends or len(set(ends)) != 4:
        return unavailable("four_quarters_unavailable")
    parsed = [date.fromisoformat(day) for day in ends]
    if any(d.day != calendar.monthrange(d.year, d.month)[1] or d.month not in (3, 6, 9, 12) for d in parsed):
        return unavailable("quarter_periods_unverified")
    if any((a.year * 12 + a.month) - (b.year * 12 + b.month) != 3 for a, b in zip(parsed, parsed[1:])):
        return unavailable("quarter_gap")
    if parsed[0] > now.date() or (now.date() - parsed[0]).days > 190:
        return unavailable("eps_period_stale_or_future")
    basis = next((key for key in ("diluted_eps", "basic_eps")
                  if all(number(row.get(key)) is not None for row in rows)), None)
    if not basis or any(row.get("period_type") != "standalone_quarter" for row in rows):
        return unavailable("eps_basis_incomplete")
    share_key = "diluted_shares" if basis == "diluted_eps" else "basic_shares"
    shares = [number(row.get(share_key)) for row in rows]
    if any(value is None or value <= 0 for value in shares):
        return unavailable("share_basis_unverified")
    if max(shares) / min(shares) > MAX_WEIGHTED_SHARE_RATIO:
        return unavailable("material_share_change")
    if max(shares) != min(shares):
        meta["warnings"].append("small_weighted_share_variation_approximation")
    start = date(parsed[-1].year, parsed[-1].month - 2, 1)
    if any(iso_date(day) and start <= date.fromisoformat(iso_date(day)) <= now.date()
           for day in payload.get("split_dates", [])):
        return unavailable("corporate_action_in_period")
    if not payload.get("actions_verified"):
        meta["warnings"].append("corporate_actions_unknown_approximation")
        meta["methodology"] += "；公司行動未知，僅以四季加權股數變動 ≤1% 作保守工程近似檢查，非會計規則"
    values = [number(row[basis]) for row in rows]
    try:
        total = math.fsum(values)
    except OverflowError:
        return unavailable("invalid_eps_total")
    if not math.isfinite(total):
        return unavailable("invalid_eps_total")
    meta.update(basis="diluted" if basis == "diluted_eps" else "basic",
                period_start=start.isoformat(), period_end=ends[0], as_of=ends[0],
                quarters=[{"period_end": end, "eps": value, "weighted_shares": share}
                          for end, value, share in zip(ends, values, shares)])
    meta["warnings"].append("quarter_sum_approximation")
    return section(total, **meta)


def percentile(values, p):
    ordered = sorted(values)
    position = (len(ordered) - 1) * p
    lo, hi = math.floor(position), math.ceil(position)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (position - lo)


def peer_reference(code, profile, companies, rows, quote_date, pe_date, market, freshness):
    industry = str((profile or {}).get("產業別", "")).strip().zfill(2)
    base = {"origin": "official_industry_pe_percentiles", "industry_code": industry,
            "market": market, "currency": "TWD", "as_of": quote_date,
            "source_url": OFFICIAL[market]["pe"], "peers": [], "count": 0,
            "methodology": "同交易所官方產業代碼；排除自身；正本益比；線性分位 (n−1)×p"}
    if not profile or not industry.strip("0") or freshness != "fresh" or quote_date != pe_date:
        return {**base, "status": "unavailable", "reason_code": "peer_context_unverified"}
    profiles = {str(p.get("公司代號", "")).strip(): p for p in companies}
    peers = {}
    for row in rows:
        peer = str(row.get("Code") or row.get("SecuritiesCompanyCode") or "").strip()
        peer_profile = profiles.get(peer)
        value = number(row.get("PEratio") if market == "TW" else row.get("PriceEarningRatio"))
        if (peer == code or not ordinary_company(peer, peer_profile) or value is None or value <= 0
                or iso_date(row.get("Date")) != quote_date
                or str(peer_profile.get("產業別", "")).strip().zfill(2) != industry):
            continue
        peers[peer] = {"ticker": f"{peer}.{market}", "pe": value}
    items = sorted(peers.values(), key=lambda x: x["ticker"])
    base.update(peers=items, count=len(items))
    if len(items) < 5:
        return {**base, "status": "unavailable", "reason_code": "insufficient_peers"}
    values = [item["pe"] for item in items]
    return {**base, "status": "available", "reason_code": None,
            "pe_low": percentile(values, .25), "pe_mid": percentile(values, .5),
            "pe_high": percentile(values, .75)}


def calculate_valuation(snapshot, current_pe=None, scenarios=None):
    """Pure calculation API, independently testable without providers or LLMs."""
    data = snapshot.get("data", snapshot)
    quote, eps = data.get("quote", {}), data.get("eps_ttm", {})
    price = number(quote.get("value"))
    eps_value = number(eps.get("value"))
    eligible = bool(data.get("identity", {}).get("ordinary") and price and price > 0
                    and eps_value is not None and eps_value > 0 and eps.get("status") == "available"
                    and quote.get("freshness") == "fresh")
    model = {"status": "unavailable", "reason_code": "valuation_inputs_ineligible"}
    if not data.get("identity", {}).get("ordinary"):
        model["reason_code"] = "not_ordinary_stock"
    elif price is None or price <= 0:
        model["reason_code"] = "quote_unavailable"
    elif quote.get("freshness") != "fresh":
        model["reason_code"] = "quote_stale" if quote.get("freshness") == "stale" else "quote_freshness_unknown"
    elif eps_value is None or eps.get("status") != "available":
        model["reason_code"] = eps.get("reason_code") or "eps_unavailable"
    elif eps_value <= 0:
        model["reason_code"] = "nonpositive_eps"
    if current_pe is not None:
        values = [number(current_pe.get(key)) for key in ("low", "mid", "high")]
        if any(value is None or value <= 0 or value > 10000 for value in values) or values != sorted(values):
            raise ValueError("請填入正數且依下界、中位、上界排列的本益比（上限 10000）。")
        origin = "user_assumption"
    else:
        peer = data.get("peer_reference", {})
        values = [peer.get(key) for key in ("pe_low", "pe_mid", "pe_high")] if peer.get("status") == "available" else None
        origin = "official_industry_pe_percentiles"
    if values and eligible:
        low, mid, high = [eps_value * value for value in values]
        model = {"status": "available", "origin": origin, "low": low, "mid": mid, "high": high,
                 "pe_low": values[0], "pe_mid": values[1], "pe_high": values[2],
                 "classification": "below" if price < low else "above" if price > high else "within",
                 "methodology": "季度加總估算 EPS × 倍數；相對假設區間，非客觀合理價"}
        if not all(math.isfinite(value) for value in (low, mid, high)):
            model = {"status": "unavailable", "reason_code": "nonfinite_calculation"}
    elif not values and eligible:
        model["reason_code"] = "pe_assumptions_required"
    result = {"current_model": model, "scenarios": [], "forward_pe": None, "horizon_months": 12}
    if scenarios is not None:
        if not data.get("identity", {}).get("ordinary"):
            raise ValueError("此商品不適用普通股 EPS × PE 情境。")
        if len(scenarios) != 3:
            raise ValueError("請完整填寫悲觀、基準、樂觀三種情境。")
        for name, row in zip(("bear", "base", "bull"), scenarios):
            e, pe = number(row.get("eps")), number(row.get("pe"))
            if e is None or pe is None or not 0 < e <= 1000000 or not 0 < pe <= 10000:
                raise ValueError("情境 EPS 與本益比須為有限正數，EPS 上限 1000000、倍數上限 10000。")
            target = e * pe
            ratio = finite_ratio(target, price)
            change = (ratio - 1) * 100 if ratio is not None else None
            if change is not None and not math.isfinite(change):
                change = None
            result["scenarios"].append({"name": name, "eps": e, "pe": pe, "price": target,
                "origin": "user_assumption", "price_change_pct": change,
                "comparison_reason": None if change is not None else "price_comparison_unavailable"})
        targets = [row["price"] for row in result["scenarios"]]
        if targets != sorted(targets):
            raise ValueError("悲觀、基準、樂觀情境價格須依序不減。")
        result["forward_pe"] = finite_ratio(price, result["scenarios"][1]["eps"])
    return result


class ValuationService:
    """Fixed-size work pool, single-flight source cache and a caller deadline."""
    def __init__(self, json_loader=None, yahoo_loader=None, now=None, exception_calendar=None):
        self.json_loader = json_loader or self._json
        self.yahoo_loader = yahoo_loader or self._yahoo
        self.now = now or (lambda: datetime.now(TAIPEI))
        self.exception_calendar = exception_calendar
        self._executor = ThreadPoolExecutor(max_workers=10, thread_name_prefix="valuation")
        self._slots = threading.BoundedSemaphore(10)
        self._lock = threading.Lock()
        self._cache, self._flights = {}, {}

    @staticmethod
    def _json(url):
        response = requests.get(url, timeout=(2, 5), headers={"Accept": "application/json", "User-Agent": "Stock-WebAgent/valuation"})
        response.raise_for_status()
        rows = response.json()
        if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
            raise ValueError("invalid official dataset")
        return rows

    @staticmethod
    def _yahoo(ticker):
        import yfinance as yf
        stock = yf.Ticker(ticker)
        info = stock.get_info()
        try:
            frame = stock.get_income_stmt(freq="quarterly")
        except Exception:
            frame = None
        rows = []
        fields = {"DilutedEPS": "diluted_eps", "BasicEPS": "basic_eps",
                  "DilutedAverageShares": "diluted_shares", "BasicAverageShares": "basic_shares"}
        for column in ([] if frame is None else frame.columns):
            row = {"period_end": str(column.date()), "period_type": "standalone_quarter"}
            for field, key in fields.items():
                row[key] = number(frame.loc[field, column]) if field in frame.index else None
            rows.append(row)
        actions_verified, split_dates = False, []
        try:
            splits = stock.get_splits(period="5y")
            split_dates = [str(index.date()) for index, value in splits.items() if number(value) not in (None, 0, 1)]
            metadata = stock.get_history_metadata()
            actions_verified = bool(metadata and metadata.get("currency") == "TWD"
                                    and metadata.get("instrumentType") == "EQUITY")
        except Exception:
            pass
        return {"currency": info.get("financialCurrency"), "quote_currency": info.get("currency"),
                "vendor_ttm": number(info.get("trailingEps")), "most_recent_quarter": info.get("mostRecentQuarter"),
                "quarters": rows, "split_dates": split_dates, "actions_verified": actions_verified,
                "source_url": f"https://finance.yahoo.com/quote/{ticker}/financials/"}

    def _start(self, key, ttl, loader):
        with self._lock:
            cached = self._cache.get(key)
            if cached and time.monotonic() - cached[0] < ttl:
                return None, cached[1]
            if key in self._flights:
                return self._flights[key], None
            if not self._slots.acquire(blocking=False):
                return None, None
            def run():
                try:
                    value = loader()
                    stamp = self.now().isoformat()
                    wrapped = {"payload": value, "fetched_at": stamp}
                    with self._lock:
                        self._cache[key] = (time.monotonic(), wrapped)
                    return wrapped
                finally:
                    with self._lock:
                        self._flights.pop(key, None)
                    self._slots.release()
            future = self._executor.submit(run)
            self._flights[key] = future
            return future, None

    def snapshot(self, ticker, deadline_seconds=12):
        code, requested_market = normalize_taiwan_ticker(ticker)
        now = self.now()
        jobs, loaded = {}, {}
        for market, sources in OFFICIAL.items():
            for kind, url in sources.items():
                future, cached = self._start(url, 21600 if kind == "companies" else 600, lambda url=url: self.json_loader(url))
                key = (market, kind)
                if cached:
                    loaded[key] = cached
                elif future:
                    jobs[key] = future
        future, cached = self._start(TWSE_HOLIDAY_URL, 3600, lambda: self.json_loader(TWSE_HOLIDAY_URL))
        if cached:
            loaded[("all", "holiday")] = cached
        elif future:
            jobs[("all", "holiday")] = future
        start = time.monotonic()
        wait(list(jobs.values()), timeout=max(0, deadline_seconds - 3))
        for key, future in jobs.items():
            if future.done():
                try:
                    loaded[key] = future.result()
                except Exception:
                    pass
        def rows(market, kind):
            return loaded.get((market, kind), {}).get("payload", [])
        profiles = {}
        for market in OFFICIAL:
            companies = rows(market, "companies")
            if market == "TWO":
                companies = normalize_tpex_companies(companies)
            profiles[market] = companies
        # A company-profile match resolves bare codes and incorrectly defaulted workspace suffixes.
        matches = [(market, next((p for p in profiles[market] if str(p.get("公司代號", "")).strip() == code), None))
                   for market in OFFICIAL]
        market, profile = next(((m, p) for m, p in matches if p), (requested_market or "TW", None))
        quote_row = next((r for r in rows(market, "quote") if str(r.get("Code") or r.get("SecuritiesCompanyCode") or "").strip() == code), {})
        pe_row = next((r for r in rows(market, "pe") if str(r.get("Code") or r.get("SecuritiesCompanyCode") or "").strip() == code), {})
        eps_row = next((r for r in rows(market, "eps") if str(r.get("公司代號") or r.get("SecuritiesCompanyCode") or "").strip() == code), {})
        symbol = f"{code}.{market}"
        ordinary = ordinary_company(code, profile)
        name = (profile or {}).get("公司簡稱") or quote_row.get("Name") or quote_row.get("CompanyName") or code
        quote_date = iso_date(quote_row.get("Date"))
        price = number(quote_row.get("ClosingPrice") or quote_row.get("Close"))
        if price is not None and price <= 0:
            price = None
        exceptions = self.exception_calendar() if callable(self.exception_calendar) else self.exception_calendar
        calendar_evidence = quote_calendar_evidence(quote_date, rows("all", "holiday"), now, market, exceptions)
        quote = section(price, reason=None if price is not None else "quote_unavailable", currency="TWD", kind="close",
                        source="TWSE 每日行情" if market == "TW" else "TPEx 每日行情", source_url=OFFICIAL[market]["quote"],
                        as_of=quote_date, fetched_at=loaded.get((market, "quote"), {}).get("fetched_at"),
                        freshness=calendar_evidence["freshness"], calendar_evidence=calendar_evidence,
                        methodology="交易所日收盤價；非即時行情")
        pe = number(pe_row.get("PEratio") if market == "TW" else pe_row.get("PriceEarningRatio"))
        if pe is not None and pe <= 0:
            pe = None
        pe_date = iso_date(pe_row.get("Date"))
        official_pe = section(pe, reason=None if pe is not None else "official_pe_unavailable", source="交易所公告參考本益比",
            source_url=OFFICIAL[market]["pe"], as_of=pe_date, fetched_at=loaded.get((market, "pe"), {}).get("fetched_at"),
            methodology="官方參考 EPS 口徑可能與季度稀釋 EPS 加總不同；不反推公布 EPS")
        year, quarter = number(eps_row.get("年度") or eps_row.get("Year")), number(eps_row.get("季別"))
        period_start = period_end = None
        if year and quarter and year.is_integer() and quarter in (1, 2, 3, 4):
            y = int(year) + 1911 if year < 1911 else int(year)
            month = int(quarter) * 3
            period_start, period_end = f"{y}-01-01", f"{y}-{month:02d}-{calendar.monthrange(y, month)[1]:02d}"
        ytd = number(eps_row.get("基本每股盈餘（元）") if market == "TW" else eps_row.get("基本每股盈餘"))
        official_ytd = section(ytd if period_end else None, reason="cumulative_not_ttm", basis="basic", period_type="cumulative_ytd",
            period_start=period_start, period_end=period_end, as_of=period_end, currency="TWD", source="公開資訊觀測站／交易所財報彙總",
            source_url=OFFICIAL[market]["eps"], exported_at=iso_date(eps_row.get("出表日期") or eps_row.get("Date")),
            fetched_at=loaded.get((market, "eps"), {}).get("fetched_at"), methodology="年初至當季累計基本 EPS；出表日期為匯出日，非財報公布日，不年化")
        yahoo = {}
        if ordinary:
            future, cached = self._start("yahoo:" + symbol, 3600, lambda: self.yahoo_loader(symbol))
            if cached:
                yahoo = {**cached["payload"], "fetched_at": cached["fetched_at"]}
            elif future:
                wait([future], timeout=max(0, deadline_seconds - (time.monotonic() - start)))
                if future.done():
                    try:
                        value = future.result()
                        yahoo = {**value["payload"], "fetched_at": value["fetched_at"]}
                    except Exception:
                        pass
        ttm = quarterly_ttm(yahoo, now) if ordinary else section(reason="not_ordinary_stock")
        vendor = section(number(yahoo.get("vendor_ttm")), reason="vendor_period_and_basis_incomplete",
                         source="Yahoo Finance trailingEps 參考值", source_url=yahoo.get("source_url"),
                         currency=yahoo.get("currency"), fetched_at=yahoo.get("fetched_at"),
                         methodology="供應商 TTM；完整四季期間／基本或稀釋口徑未驗證，不作估值分母")
        if ttm.get("value") is not None and vendor.get("value") is not None and abs(ttm["value"] - vendor["value"]) > .01:
            ttm["warnings"].append("vendor_trailing_eps_differs")
        if yahoo and yahoo.get("quote_currency") != "TWD":
            ttm = section(reason="quote_currency_unverified")
        peers = peer_reference(code, profile, profiles[market], rows(market, "pe"), quote_date, pe_date, market, quote["freshness"])
        data = {"identity": {"ticker": symbol, "code": code, "name": name, "market": market, "ordinary": ordinary,
                             "reason_code": None if ordinary else "ordinary_company_unverified", "currency": "TWD"},
                "quote": quote, "official_pe": official_pe, "official_ytd_eps": official_ytd,
                "eps_ttm": ttm, "vendor_ttm_eps": vendor, "peer_reference": peers,
                "calculated_pe": finite_ratio(price, ttm.get("value"))}
        data["identity"]["methodology"] = "官方公司名錄精確代號＋四位非零開頭公司代碼＋有效產業碼，排除91存託憑證及特殊商品名稱；EPS另外核對台幣口徑"
        data.update(calculate_valuation(data))
        today = now.date()
        try:
            end = today.replace(year=today.year + 1)
        except ValueError:
            end = today.replace(year=today.year + 1, day=28)
        data.update(valuation_as_of=today.isoformat(), horizon_end=end.isoformat(),
                    eps_period_start=today.isoformat(), eps_period_end=(end - timedelta(days=1)).isoformat())
        available = any(item.get("value") is not None for item in (quote, official_pe, official_ytd, ttm, vendor))
        return {"status": "partial" if available else "unavailable", "ticker": symbol,
                "model_version": "quarter-sum-peer-pe-v1", "data": data,
                "unavailable_sections": [key for key, value in data.items() if isinstance(value, dict) and value.get("status") == "unavailable"]}


valuation_service = ValuationService(exception_calendar=load_calendar_exceptions)

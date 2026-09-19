"""Official-data market insights used by the dashboard.

Network access is deliberately lazy: importing this module never calls an
external service.  The pure aggregation helpers are also kept public enough
to be tested without relying on live market data.
"""

from __future__ import annotations

import math
import re
import statistics
import threading
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Sequence

import requests

from news_crawler import NewsCrawler


TDCC_DISTRIBUTION_URL = "https://openapi.tdcc.com.tw/v1/opendata/1-5"
TWSE_DAILY_URL = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
TWSE_COMPANY_URL = "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"
TPEX_COMPANY_URL = "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O"
TPEX_DAILY_URL = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes"

REQUEST_HEADERS = {
    "Accept": "application/json",
    "User-Agent": "Stock-WebAgent/4.1 (+market-insights)",
}

# TWSE industry codes used by the listed-company profile dataset.
INDUSTRY_NAMES = {
    "01": "水泥工業", "02": "食品工業", "03": "塑膠工業", "04": "紡織纖維",
    "05": "電機機械", "06": "電器電纜", "07": "化學生技醫療", "08": "玻璃陶瓷",
    "09": "造紙工業", "10": "鋼鐵工業", "11": "橡膠工業", "12": "汽車工業",
    "14": "建材營造", "15": "航運業", "16": "觀光餐旅", "17": "金融保險",
    "18": "貿易百貨", "19": "綜合企業", "20": "其他", "21": "化學工業",
    "22": "生技醫療業", "23": "油電燃氣業", "24": "半導體業",
    "25": "電腦及週邊設備業", "26": "光電業", "27": "通信網路業",
    "28": "電子零組件業", "29": "電子通路業", "30": "資訊服務業",
    "31": "其他電子業", "32": "文化創意業", "33": "農業科技業",
    "34": "電子商務", "35": "綠能環保", "36": "數位雲端",
    "37": "運動休閒", "38": "居家生活", "80": "管理股票",
}

# TDCC levels: 12-15 are 400,001 shares and above; 17 is the total row.
HOLDER_GROUPS = (
    ("未滿 1 張", frozenset({1})),
    ("1–10 張", frozenset({2, 3})),
    ("10–100 張", frozenset(range(4, 10))),
    ("100–400 張", frozenset({10, 11})),
    ("400 張以上", frozenset({12, 13, 14, 15})),
)

# These short names are common words or global brands in financial news.  A
# numeric ticker is required for them so, for example, Samsung Electronics is
# not counted as Taiwan-listed San Shing Fastech (5007).
AMBIGUOUS_STOCK_NAMES = {
    "三星", "世界", "材料", "統一", "聯合", "中華", "台灣", "國際",
    "大成", "大同", "巨大", "環球", "東方", "第一", "全國",
}


def _number(value: Any, default: float = 0.0) -> float:
    try:
        number = float(str(value).replace(",", "").strip())
        return number if math.isfinite(number) else default
    except (TypeError, ValueError):
        return default


def _clean_row(row: Mapping[str, Any]) -> Dict[str, Any]:
    """Remove BOMs occasionally included in the first TDCC field name."""
    return {str(key).lstrip("\ufeff"): value for key, value in row.items()}


def _display_date(value: Any) -> str:
    raw = str(value or "").strip()
    if re.fullmatch(r"\d{7}", raw):  # TWSE Republic of China year (YYYMMDD)
        return f"{int(raw[:3]) + 1911:04d}-{raw[3:5]}-{raw[5:7]}"
    if re.fullmatch(r"\d{8}", raw):
        return f"{int(raw[:4]):04d}-{raw[4:6]}-{raw[6:8]}"
    return raw


def aggregate_holder_rows(rows: Iterable[Mapping[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Aggregate the latest TDCC distribution rows for every security."""
    securities: Dict[str, Dict[str, Any]] = {}
    for raw_row in rows:
        row = _clean_row(raw_row)
        code = str(row.get("證券代號", "")).strip()
        if not code:
            continue
        try:
            level = int(str(row.get("持股分級", "")).strip())
        except ValueError:
            continue
        item = securities.setdefault(code, {
            "ticker": code,
            "data_date": _display_date(row.get("資料日期")),
            "levels": {},
        })
        item["data_date"] = max(item["data_date"], _display_date(row.get("資料日期")))
        item["levels"][level] = {
            "accounts": int(_number(row.get("人數"))),
            "shares": int(_number(row.get("股數"))),
            "ratio": round(_number(row.get("占集保庫存數比例%")), 4),
        }

    result: Dict[str, Dict[str, Any]] = {}
    for code, item in securities.items():
        levels = item["levels"]
        total = levels.get(17, {"accounts": 0, "shares": 0, "ratio": 0.0})
        breakdown = []
        for label, group_levels in HOLDER_GROUPS:
            selected = [levels[level] for level in group_levels if level in levels]
            breakdown.append({
                "label": label,
                "accounts": sum(row["accounts"] for row in selected),
                "shares": sum(row["shares"] for row in selected),
                "ratio": round(sum(row["ratio"] for row in selected), 2),
            })
        large = breakdown[-1]
        small = breakdown[0]["ratio"] + breakdown[1]["ratio"]
        result[code] = {
            "ticker": code,
            "data_date": item["data_date"],
            "large_holder_threshold": "400 張以上（400,001 股以上）",
            "large_holder_ratio": large["ratio"],
            "large_holder_accounts": large["accounts"],
            "small_holder_ratio": round(small, 2),
            "total_accounts": total["accounts"],
            "total_shares": total["shares"],
            "breakdown": breakdown,
            "source": "臺灣集中保管結算所（TDCC）集保戶股權分散表",
        }
    return result


def aggregate_industry_performance(
    daily_rows: Iterable[Mapping[str, Any]],
    company_rows: Iterable[Mapping[str, Any]],
    *,
    limit: int = 10,
    minimum_companies: int = 3,
) -> List[Dict[str, Any]]:
    """Compute equal-weight industry returns from official listed-stock rows."""
    companies = {
        str(row.get("公司代號", "")).strip(): {
            "name": str(row.get("公司簡稱", "")).strip(),
            "industry_code": str(row.get("產業別", "")).strip().zfill(2),
        }
        for row in company_rows
        if str(row.get("公司代號", "")).strip()
    }
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in daily_rows:
        code = str(row.get("Code", "")).strip()
        profile = companies.get(code)
        if not profile:
            continue  # Excludes ETFs, warrants and non-common listed products.
        close = _number(row.get("ClosingPrice"), math.nan)
        change = _number(row.get("Change"), math.nan)
        previous = close - change
        if not math.isfinite(close) or not math.isfinite(change) or previous <= 0:
            continue
        pct = change / previous * 100
        if not math.isfinite(pct) or abs(pct) > 30:
            continue
        grouped[profile["industry_code"]].append({
            "ticker": code,
            "name": profile["name"],
            "pct_change": pct,
        })

    result = []
    for industry_code, stocks in grouped.items():
        if len(stocks) < minimum_companies:
            continue
        changes = [stock["pct_change"] for stock in stocks]
        leaders = sorted(stocks, key=lambda stock: stock["pct_change"], reverse=True)[:3]
        result.append({
            "industry_code": industry_code,
            "industry": INDUSTRY_NAMES.get(industry_code, f"產業 {industry_code}"),
            "average_change": round(statistics.fmean(changes), 2),
            "median_change": round(statistics.median(changes), 2),
            "advancers": sum(change > 0 for change in changes),
            "decliners": sum(change < 0 for change in changes),
            "company_count": len(stocks),
            "leaders": [
                {**stock, "pct_change": round(stock["pct_change"], 2)}
                for stock in leaders
            ],
        })
    result.sort(key=lambda row: (row["average_change"], row["median_change"]), reverse=True)
    return result[:limit]


def normalize_tpex_companies(rows: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Convert TPEx English field names to the MOPS/TWSE company schema."""
    return [
        {
            "公司代號": row.get("SecuritiesCompanyCode", ""),
            "公司簡稱": row.get("CompanyAbbreviation", ""),
            "公司名稱": row.get("CompanyName", ""),
            "產業別": row.get("SecuritiesIndustryCode", ""),
        }
        for row in rows
    ]


def rank_trending_stocks(
    news_items: Sequence[Mapping[str, Any]],
    company_rows: Iterable[Mapping[str, Any]],
    *,
    limit: int = 5,
    now_ts: float | None = None,
) -> List[Dict[str, Any]]:
    """Rank stocks by unique recent news mentions with recency/source boosts."""
    now_ts = now_ts or datetime.now(timezone.utc).timestamp()
    profiles = []
    for row in company_rows:
        code = str(row.get("公司代號", "")).strip()
        name = str(row.get("公司簡稱", "")).strip()
        if re.fullmatch(r"\d{4,6}", code) and len(name) >= 2:
            profiles.append((code, name))

    stats: Dict[str, Dict[str, Any]] = {}
    for article in news_items:
        title = str(article.get("title", "")).strip()
        summary = str(article.get("summary", "")).strip()
        text = f"{title} {summary}"
        if not text.strip():
            continue
        mentioned = []
        for code, name in profiles:
            code_match = re.search(rf"(?<!\d){re.escape(code)}(?!\d)", text)
            if code_match or (name not in AMBIGUOUS_STOCK_NAMES and name in text):
                mentioned.append((code, name))
        for code, name in set(mentioned):
            item = stats.setdefault(code, {
                "ticker": code,
                "name": name,
                "mention_count": 0,
                "weighted_score": 0.0,
                "sources": set(),
                "latest_headline": "",
                "latest_link": "",
                "latest_ts": 0.0,
            })
            published_ts = _number(article.get("published_ts"))
            age_hours = max(0.0, (now_ts - published_ts) / 3600) if published_ts else 72.0
            recency_boost = max(0.0, 1.0 - age_hours / 72.0)
            item["mention_count"] += 1
            item["weighted_score"] += 1.0 + recency_boost
            source = str(article.get("source", "")).strip()
            if source:
                item["sources"].add(source)
            if published_ts >= item["latest_ts"]:
                item["latest_ts"] = published_ts
                item["latest_headline"] = title
                item["latest_link"] = str(article.get("link", "")).strip()

    ranked = []
    for item in stats.values():
        source_count = len(item["sources"])
        item["weighted_score"] += max(0, source_count - 1) * 0.5
        ranked.append({
            "ticker": item["ticker"],
            "name": item["name"],
            "mention_count": item["mention_count"],
            "source_count": source_count,
            "sources": sorted(item["sources"]),
            "heat_score": round(item["weighted_score"], 2),
            "latest_headline": item["latest_headline"],
            "latest_link": item["latest_link"],
        })
    ranked.sort(
        key=lambda row: (row["heat_score"], row["mention_count"], row["source_count"]),
        reverse=True,
    )
    return ranked[:limit]


class MarketInsightsService:
    """Small TTL-cached facade around the three insight calculations."""

    def __init__(self) -> None:
        self._cache: Dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()
        self._session = requests.Session()
        self._session.headers.update(REQUEST_HEADERS)

    def _cached(self, key: str, ttl: int, loader):
        now = time.monotonic()
        with self._lock:
            cached = self._cache.get(key)
            if cached and now - cached[0] < ttl:
                return cached[1]
        value = loader()
        with self._lock:
            self._cache[key] = (time.monotonic(), value)
        return value

    def _json(self, url: str, timeout: int = 25) -> List[Dict[str, Any]]:
        response = self._session.get(url, timeout=timeout)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise ValueError(f"Unexpected response from {url}")
        return payload

    def _listed_companies(self) -> List[Dict[str, Any]]:
        return self._cached("listed_companies", 6 * 3600, lambda: self._json(TWSE_COMPANY_URL))

    def _all_companies(self) -> List[Dict[str, Any]]:
        def load():
            listed = self._json(TWSE_COMPANY_URL)
            try:
                return listed + normalize_tpex_companies(self._json(TPEX_COMPANY_URL))
            except (requests.RequestException, ValueError):
                return listed
        return self._cached("all_companies", 6 * 3600, load)

    def major_holders(self, ticker: str) -> Dict[str, Any]:
        code = str(ticker).upper().split(".")[0].strip()
        if not re.fullmatch(r"[0-9A-Z]{4,10}", code):
            raise ValueError("請輸入有效的台股代號，例如 2330")
        dataset = self._cached(
            "tdcc_holder_distribution",
            6 * 3600,
            lambda: aggregate_holder_rows(self._json(TDCC_DISTRIBUTION_URL, timeout=40)),
        )
        if code not in dataset:
            raise LookupError(f"集保資料中找不到 {code}，請確認代號或稍後再試")
        return dataset[code]

    def industry_performance(self, limit: int = 10) -> Dict[str, Any]:
        daily = self._cached("twse_daily", 10 * 60, lambda: self._json(TWSE_DAILY_URL))
        companies = self._listed_companies()
        tpex_included = False
        try:
            tpex_daily = self._cached("tpex_daily", 10 * 60, lambda: self._json(TPEX_DAILY_URL))
            tpex_companies = normalize_tpex_companies(
                self._cached("tpex_companies", 6 * 3600, lambda: self._json(TPEX_COMPANY_URL))
            )
            daily = daily + [
                {
                    "Date": row.get("Date"),
                    "Code": row.get("SecuritiesCompanyCode"),
                    "Name": row.get("CompanyName"),
                    "ClosingPrice": row.get("Close"),
                    "Change": row.get("Change"),
                }
                for row in tpex_daily
            ]
            companies = companies + tpex_companies
            tpex_included = True
        except (requests.RequestException, ValueError):
            # Keep the listed-market ranking available during a TPEx outage.
            pass
        rows = aggregate_industry_performance(daily, companies, limit=limit)
        date = _display_date(daily[0].get("Date")) if daily else ""
        return {
            "as_of": date,
            "market": "上市櫃普通股" if tpex_included else "上市普通股（櫃買資料暫缺）",
            "ranking_method": "依各產業成分股單日漲跌幅等權平均排序",
            "items": rows,
            "source": "臺灣證券交易所、證券櫃檯買賣中心 OpenAPI" if tpex_included else "臺灣證券交易所 OpenAPI",
        }

    def trending_stocks(self, limit: int = 5) -> Dict[str, Any]:
        news = self._cached(
            "recent_news",
            10 * 60,
            lambda: NewsCrawler.fetch_all(limit_per_source=30),
        )
        rows = rank_trending_stocks(news, self._all_companies(), limit=limit)
        return {
            "article_count": len(news),
            "ranking_method": "近期財經 RSS 的個股提及次數，並加入 72 小時時間與跨來源權重",
            "items": rows,
            "sources": sorted({str(item.get("source", "")) for item in news if item.get("source")}),
        }


market_insights = MarketInsightsService()

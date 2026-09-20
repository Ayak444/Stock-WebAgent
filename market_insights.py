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
from concurrent.futures import CancelledError, Future, ThreadPoolExecutor, wait
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Sequence

import requests

from news_crawler import NewsCrawler, RSS_SOURCES


TDCC_DISTRIBUTION_URL = "https://openapi.tdcc.com.tw/v1/opendata/1-5"
TWSE_DAILY_URL = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
TWSE_COMPANY_URL = "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"
TPEX_COMPANY_URL = "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O"
TPEX_DAILY_URL = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes"

REQUEST_HEADERS = {
    "Accept": "application/json",
    "User-Agent": "Stock-WebAgent/4.1 (+market-insights)",
}

SNAPSHOT_DEADLINE_SECONDS = 12.0
SOURCE_TIMEOUT_SECONDS = 7
RSS_TIMEOUT_SECONDS = 4
SNAPSHOT_EXECUTOR = ThreadPoolExecutor(
    max_workers=8,
    thread_name_prefix="market-insight",
)

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

SECTION_METADATA = {
    "identity": {
        "source": "臺灣證券交易所、證券櫃檯買賣中心公司基本資料與每日行情",
        "methodology": "依證券代號比對公司基本資料；無公司資料的商品以每日行情名稱補足",
    },
    "price": {
        "source": "臺灣證券交易所、證券櫃檯買賣中心每日行情",
        "methodology": "單日漲跌幅 = 漲跌價差 ÷（收盤價 − 漲跌價差）× 100%",
    },
    "industry_context": {
        "source": "臺灣證券交易所、證券櫃檯買賣中心 OpenAPI",
        "methodology": "普通股依官方產業別分組，以有效成分股單日漲跌幅等權計算",
    },
    "ownership": {
        "source": "臺灣集中保管結算所（TDCC）集保戶股權分散表",
        "methodology": "大戶採持股分級 12–15、小額持股採 1–3，分級 17 作總計",
    },
    "news_attention": {
        "source": "近期財經 RSS",
        "methodology": "統計最近 72 小時個股提及；每篇至多一次，並列出跨來源數",
    },
}


def normalize_taiwan_ticker(value: Any) -> tuple[str, str]:
    """Validate a Taiwan ticker and return its code plus optional suffix."""
    raw = str(value or "").strip().upper()
    match = re.fullmatch(r"([0-9A-Z]{4,10})(?:\.(TW|TWO))?", raw)
    if not match:
        raise ValueError("請輸入有效的台股代號，例如 2330、2330.TW 或 6488.TWO")
    return match.group(1), match.group(2) or ""


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
    companies = {}
    for row in company_rows:
        code = str(row.get("公司代號", "")).strip()
        industry_code = str(row.get("產業別", "")).strip()
        if code and industry_code:
            companies[code] = {
                "name": str(row.get("公司簡稱", "")).strip(),
                "industry_code": industry_code.zfill(2),
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
            "公司代號": row.get("公司代號") or row.get("SecuritiesCompanyCode", ""),
            "公司簡稱": row.get("公司簡稱") or row.get("CompanyAbbreviation", ""),
            "公司名稱": row.get("公司名稱") or row.get("CompanyName", ""),
            "產業別": row.get("產業別") or row.get("SecuritiesIndustryCode", ""),
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


def calculate_price_change(close_value: Any, change_value: Any) -> Dict[str, float] | None:
    """Return a validated close/change snapshot using the official change formula."""
    close = _number(close_value, math.nan)
    change = _number(change_value, math.nan)
    previous_close = close - change
    if (
        not math.isfinite(close)
        or not math.isfinite(change)
        or not math.isfinite(previous_close)
        or close < 0
        or previous_close <= 0
    ):
        return None
    percentage = change / previous_close * 100
    if not math.isfinite(percentage):
        return None
    return {
        "close": round(close, 4),
        "change": round(change, 4),
        "previous_close": round(previous_close, 4),
        "change_percent": round(percentage, 2),
    }


def analyze_stock_news_attention(
    news_items: Sequence[Mapping[str, Any]],
    ticker: str,
    name: str = "",
    *,
    now_ts: float | None = None,
) -> Dict[str, Any]:
    """Summarize one stock's unique article mentions from the last 72 hours."""
    now_ts = now_ts or datetime.now(timezone.utc).timestamp()
    articles = []
    for article in news_items:
        published_ts = _number(article.get("published_ts"), math.nan)
        if not math.isfinite(published_ts):
            continue
        age_hours = max(0.0, (now_ts - published_ts) / 3600)
        if age_hours > 72:
            continue
        title = str(article.get("title", "")).strip()
        summary = str(article.get("summary", "")).strip()
        text = f"{title} {summary}"
        ticker_match = bool(re.search(rf"(?<!\d){re.escape(ticker)}(?!\d)", text))
        name_match = bool(name and name not in AMBIGUOUS_STOCK_NAMES and name in text)
        if not ticker_match and not name_match:
            continue
        articles.append({
            "title": title,
            "link": str(article.get("link", "")).strip(),
            "source": str(article.get("source", "")).strip(),
            "published": str(article.get("published", "")).strip(),
            "published_ts": published_ts,
        })

    articles.sort(key=lambda item: item["published_ts"], reverse=True)
    sources = sorted({item["source"] for item in articles if item["source"]})
    return {
        "mention_count": len(articles),
        "source_count": len(sources),
        "cross_source": len(sources) > 1,
        "sources": sources,
        "articles": articles[:5],
    }


def _unavailable_section(section: str, code: str) -> Dict[str, Any]:
    metadata = SECTION_METADATA[section]
    return {
        "available": False,
        "as_of": "",
        "source": metadata["source"],
        "methodology": metadata["methodology"],
        "code": code,
    }


def _available_section(section: str, as_of: str, **values: Any) -> Dict[str, Any]:
    metadata = SECTION_METADATA[section]
    return {
        "available": True,
        "as_of": as_of,
        "source": metadata["source"],
        "methodology": metadata["methodology"],
        **values,
    }


class _CacheFlight:
    def __init__(self) -> None:
        self.event = threading.Event()
        self.error: BaseException | None = None


def _consume_future_exception(future: Future) -> None:
    """Prevent late bounded loader failures from becoming unobserved errors."""
    try:
        future.exception()
    except CancelledError:
        pass


class MarketInsightsService:
    """Small TTL-cached facade around the three insight calculations."""

    def __init__(self) -> None:
        self._cache: Dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()
        self._flights: Dict[str, _CacheFlight] = {}

    def _cached(self, key: str, ttl: int, loader):
        while True:
            now = time.monotonic()
            with self._lock:
                cached = self._cache.get(key)
                if cached and now - cached[0] < ttl:
                    return cached[1]
                flight = self._flights.get(key)
                if flight is None:
                    flight = _CacheFlight()
                    self._flights[key] = flight
                    is_loader = True
                else:
                    is_loader = False

            if is_loader:
                break
            flight.event.wait()
            if flight.error is not None:
                raise flight.error

        try:
            value = loader()
        except BaseException as exc:
            with self._lock:
                self._flights.pop(key, None)
                flight.error = exc
                flight.event.set()
            raise
        with self._lock:
            self._cache[key] = (time.monotonic(), value)
            self._flights.pop(key, None)
            flight.event.set()
        return value

    def _json(self, url: str, timeout: int = SOURCE_TIMEOUT_SECONDS) -> List[Dict[str, Any]]:
        with requests.Session() as session:
            session.headers.update(REQUEST_HEADERS)
            response = session.get(url, timeout=(3, timeout))
            response.raise_for_status()
            payload = response.json()
        if not isinstance(payload, list):
            raise ValueError(f"Unexpected response from {url}")
        return payload

    def _listed_companies(self) -> List[Dict[str, Any]]:
        return self._cached("listed_companies", 6 * 3600, lambda: self._json(TWSE_COMPANY_URL))

    def _tpex_companies(self) -> List[Dict[str, Any]]:
        rows = self._cached(
            "tpex_companies",
            6 * 3600,
            lambda: self._json(TPEX_COMPANY_URL),
        )
        return normalize_tpex_companies(rows)

    def _twse_daily(self) -> List[Dict[str, Any]]:
        return self._cached("twse_daily", 10 * 60, lambda: self._json(TWSE_DAILY_URL))

    def _tpex_daily(self) -> List[Dict[str, Any]]:
        rows = self._cached("tpex_daily", 10 * 60, lambda: self._json(TPEX_DAILY_URL))
        return [
            {
                "Date": row.get("Date"),
                "Code": row.get("Code") or row.get("SecuritiesCompanyCode"),
                "Name": row.get("Name") or row.get("CompanyName"),
                "ClosingPrice": row.get("ClosingPrice") or row.get("Close"),
                "Change": row.get("Change"),
            }
            for row in rows
        ]

    def _holder_distribution(self) -> Dict[str, Dict[str, Any]]:
        return self._cached(
            "tdcc_holder_distribution",
            6 * 3600,
            lambda: aggregate_holder_rows(self._json(TDCC_DISTRIBUTION_URL)),
        )

    def _recent_news(self) -> Dict[str, Any]:
        def load():
            items = []
            successful_sources = []
            unavailable_sources = []
            for key, source_info in RSS_SOURCES.items():
                source_name = str(source_info.get("name", key))
                try:
                    rows = NewsCrawler.fetch_rss(
                        key,
                        limit=30,
                        timeout=RSS_TIMEOUT_SECONDS,
                    )
                except Exception:
                    rows = []
                if rows:
                    items.extend(rows)
                    successful_sources.append(source_name)
                else:
                    unavailable_sources.append(source_name)
            items.sort(key=lambda item: _number(item.get("published_ts")), reverse=True)
            return {
                "items": items,
                "successful_sources": successful_sources,
                "unavailable_sources": unavailable_sources,
            }
        return self._cached("recent_news", 10 * 60, load)

    def _all_companies(self) -> List[Dict[str, Any]]:
        listed = self._listed_companies()
        try:
            return listed + self._tpex_companies()
        except (requests.RequestException, ValueError):
            return listed

    def major_holders(self, ticker: str) -> Dict[str, Any]:
        code, _ = normalize_taiwan_ticker(ticker)
        dataset = self._holder_distribution()
        if code not in dataset:
            raise LookupError(f"集保資料中找不到 {code}，請確認代號或稍後再試")
        return dataset[code]

    def industry_performance(self, limit: int = 10) -> Dict[str, Any]:
        daily = self._twse_daily()
        companies = self._listed_companies()
        tpex_included = False
        try:
            daily = daily + self._tpex_daily()
            companies = companies + self._tpex_companies()
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
        news_bundle = self._recent_news()
        news = news_bundle["items"]
        rows = rank_trending_stocks(news, self._all_companies(), limit=limit)
        return {
            "article_count": len(news),
            "ranking_method": "近期財經 RSS 的個股提及次數，並加入 72 小時時間與跨來源權重",
            "items": rows,
            "sources": news_bundle["successful_sources"],
            "unavailable_sources": news_bundle["unavailable_sources"],
        }

    def _snapshot_resources(
        self,
        deadline_seconds: float,
    ) -> Dict[str, tuple[bool, Any, bool]]:
        loaders = {
            "listed_companies": self._listed_companies,
            "tpex_companies": self._tpex_companies,
            "twse_daily": self._twse_daily,
            "tpex_daily": self._tpex_daily,
            "holders": self._holder_distribution,
            "news": self._recent_news,
        }
        futures = {
            key: SNAPSHOT_EXECUTOR.submit(loader)
            for key, loader in loaders.items()
        }
        wait(futures.values(), timeout=max(0.001, deadline_seconds))

        resources: Dict[str, tuple[bool, Any, bool]] = {}
        for key, future in futures.items():
            if not future.done():
                future.cancel()
                future.add_done_callback(_consume_future_exception)
                resources[key] = (False, None, True)
                continue
            try:
                resources[key] = (True, future.result(), False)
            except Exception:
                resources[key] = (False, None, False)
        return resources

    def stock_snapshot(
        self,
        ticker: str,
        *,
        deadline_seconds: float = SNAPSHOT_DEADLINE_SECONDS,
    ) -> Dict[str, Any]:
        """Build an explainable, partially available snapshot for one security."""
        code, suffix = normalize_taiwan_ticker(ticker)
        resources = self._snapshot_resources(deadline_seconds)

        def upstream_code(section: str, *resource_keys: str) -> str:
            suffix_name = (
                "upstream_timeout"
                if any(resources[key][2] for key in resource_keys)
                else "upstream_unavailable"
            )
            return f"{section}_{suffix_name}"

        listed_companies = resources["listed_companies"][1] or []
        tpex_companies = resources["tpex_companies"][1] or []
        twse_daily = resources["twse_daily"][1] or []
        tpex_daily = resources["tpex_daily"][1] or []

        listed_profile = next(
            (row for row in listed_companies if str(row.get("公司代號", "")).strip() == code),
            None,
        )
        tpex_profile = next(
            (row for row in tpex_companies if str(row.get("公司代號", "")).strip() == code),
            None,
        )
        listed_price = next(
            (row for row in twse_daily if str(row.get("Code", "")).strip() == code),
            None,
        )
        tpex_price = next(
            (row for row in tpex_daily if str(row.get("Code", "")).strip() == code),
            None,
        )

        if suffix == "TW":
            profile, price_row, market = listed_profile, listed_price, "上市"
            selected_company_keys = ("listed_companies",)
            selected_daily_keys = ("twse_daily",)
            selected_company_ok = resources["listed_companies"][0]
            selected_daily_ok = resources["twse_daily"][0]
        elif suffix == "TWO":
            profile, price_row, market = tpex_profile, tpex_price, "上櫃"
            selected_company_keys = ("tpex_companies",)
            selected_daily_keys = ("tpex_daily",)
            selected_company_ok = resources["tpex_companies"][0]
            selected_daily_ok = resources["tpex_daily"][0]
        elif listed_profile or listed_price:
            profile, price_row, market = listed_profile, listed_price, "上市"
            selected_company_keys = ("listed_companies",)
            selected_daily_keys = ("twse_daily",)
            selected_company_ok = resources["listed_companies"][0]
            selected_daily_ok = resources["twse_daily"][0]
        elif tpex_profile or tpex_price:
            profile, price_row, market = tpex_profile, tpex_price, "上櫃"
            selected_company_keys = ("tpex_companies",)
            selected_daily_keys = ("tpex_daily",)
            selected_company_ok = resources["tpex_companies"][0]
            selected_daily_ok = resources["tpex_daily"][0]
        else:
            profile, price_row, market = None, None, ""
            selected_company_keys = ("listed_companies", "tpex_companies")
            selected_daily_keys = ("twse_daily", "tpex_daily")
            selected_company_ok = (
                resources["listed_companies"][0] and resources["tpex_companies"][0]
            )
            selected_daily_ok = (
                resources["twse_daily"][0] and resources["tpex_daily"][0]
            )

        profile_name = ""
        if profile:
            profile_name = str(
                profile.get("公司簡稱") or profile.get("公司名稱") or ""
            ).strip()
        price_name = str((price_row or {}).get("Name", "")).strip()
        name = profile_name or price_name
        price_date = _display_date((price_row or {}).get("Date"))
        inferred_suffix = "TW" if market == "上市" else "TWO"

        if profile or price_row:
            identity = _available_section(
                "identity",
                price_date,
                ticker=code,
                symbol=f"{code}.{inferred_suffix}",
                name=name,
                market=market,
            )
        else:
            identity_source_complete = selected_company_ok and selected_daily_ok
            identity = _unavailable_section(
                "identity",
                "identity_not_found" if identity_source_complete else upstream_code(
                    "identity",
                    *selected_company_keys,
                    *selected_daily_keys,
                ),
            )

        calculated_price = calculate_price_change(
            (price_row or {}).get("ClosingPrice"),
            (price_row or {}).get("Change"),
        )
        if calculated_price:
            price = _available_section("price", price_date, **calculated_price)
            price["source"] = (
                "臺灣證券交易所每日行情" if market == "上市"
                else "證券櫃檯買賣中心每日行情"
            )
        else:
            price = _unavailable_section(
                "price",
                "price_not_found" if selected_daily_ok else upstream_code(
                    "price",
                    *selected_daily_keys,
                ),
            )

        industry_code = str((profile or {}).get("產業別", "")).strip()
        if industry_code:
            industry_code = industry_code.zfill(2)
        industry = None
        if not selected_company_ok or not selected_daily_ok:
            industry_context = _unavailable_section(
                "industry_context",
                upstream_code(
                    "industry",
                    *selected_company_keys,
                    *selected_daily_keys,
                ),
            )
        elif not industry_code:
            industry_context = _unavailable_section(
                "industry_context",
                "industry_not_applicable",
            )
        elif not calculated_price:
            industry_context = _unavailable_section(
                "industry_context",
                "industry_comparison_unavailable",
            )
        else:
            combined_daily = list(twse_daily) + list(tpex_daily)
            combined_companies = list(listed_companies) + list(tpex_companies)
            rankings = aggregate_industry_performance(
                combined_daily,
                combined_companies,
                limit=200,
            )
            industry = next(
                (row for row in rankings if row["industry_code"] == industry_code),
                None,
            )
            if industry:
                rank = rankings.index(industry) + 1
                industry_context = _available_section(
                    "industry_context",
                    price_date,
                    industry_code=industry_code,
                    industry=industry["industry"],
                    rank=rank,
                    total_industries=len(rankings),
                    mean_change=industry["average_change"],
                    median_change=industry["median_change"],
                    advancers=industry["advancers"],
                    company_count=industry["company_count"],
                    stock_minus_industry=round(
                        calculated_price["change_percent"] - industry["average_change"],
                        2,
                    ),
                )
                available_markets = []
                if resources["twse_daily"][0] and resources["listed_companies"][0]:
                    available_markets.append("臺灣證券交易所")
                if resources["tpex_daily"][0] and resources["tpex_companies"][0]:
                    available_markets.append("證券櫃檯買賣中心")
                industry_context["source"] = "、".join(available_markets) + " OpenAPI"
                industry_context["market_coverage"] = (
                    "上市櫃普通股" if len(available_markets) == 2
                    else "部分市場普通股"
                )
                industry_context["degraded"] = len(available_markets) < 2
            else:
                industry_context = _unavailable_section(
                    "industry_context",
                    "industry_insufficient_sample",
                )

        holders_ok, holder_dataset, _ = resources["holders"]
        holder = (holder_dataset or {}).get(code) if holders_ok else None
        if holder:
            ownership = _available_section(
                "ownership",
                holder.get("data_date", ""),
                **{key: value for key, value in holder.items() if key != "source"},
            )
        else:
            ownership = _unavailable_section(
                "ownership",
                "ownership_not_found" if holders_ok else upstream_code("ownership", "holders"),
            )

        news_ok, news_bundle, _ = resources["news"]
        news_bundle = news_bundle or {}
        successful_news_sources = list(news_bundle.get("successful_sources", []))
        unavailable_news_sources = list(news_bundle.get("unavailable_sources", []))
        if news_ok and successful_news_sources:
            news_items = list(news_bundle.get("items", []))
            attention = analyze_stock_news_attention(news_items, code, name)
            newest_ts = max(
                (_number(item.get("published_ts")) for item in news_items),
                default=0,
            )
            news_as_of = (
                datetime.fromtimestamp(newest_ts, timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
                if newest_ts else ""
            )
            news_attention = _available_section(
                "news_attention",
                news_as_of,
                **attention,
                article_count=len(news_items),
                available_sources=successful_news_sources,
                unavailable_sources=unavailable_news_sources,
                degraded=bool(unavailable_news_sources),
            )
            news_attention["source"] = "、".join(successful_news_sources)
        else:
            news_attention = _unavailable_section(
                "news_attention",
                upstream_code("news", "news"),
            )

        sections = {
            "identity": identity,
            "price": price,
            "industry_context": industry_context,
            "ownership": ownership,
            "news_attention": news_attention,
        }
        unavailable = [
            {"section": section, "code": payload["code"]}
            for section, payload in sections.items()
            if not payload["available"]
        ]
        warnings = []
        if industry_context.get("degraded"):
            warnings.append({
                "section": "industry_context",
                "code": "industry_market_partial",
            })
        if news_attention.get("degraded"):
            warnings.append({
                "section": "news_attention",
                "code": "news_sources_partial",
            })

        available_count = sum(payload["available"] for payload in sections.values())
        if not available_count:
            status = "unavailable"
        elif unavailable or warnings:
            status = "partial"
        else:
            status = "success"
        return {
            "status": status,
            "ticker": code,
            "data": sections,
            "unavailable": unavailable,
            "warnings": warnings,
        }


market_insights = MarketInsightsService()

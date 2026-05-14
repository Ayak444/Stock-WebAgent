import re
import time
from typing import Dict, List, Tuple
import requests
from data_provider import DataProvider

RELATION_DB: Dict[str, Dict] = {
    "2330.TW": {
        "name": "台積電",
        "group": "晶圓代工 / 半導體",
        "concepts": ["AI", "HPC", "先進製程", "CoWoS"],
        "supply_chain": {
            "upstream": ["2303.TW", "2327.TW", "2408.TW"],
            "midstream": ["2330.TW", "2454.TW"],
            "downstream": ["3711.TW", "3231.TW", "2382.TW"]
        },
        "related": ["2303.TW", "2454.TW", "3035.TW", "3711.TW", "3661.TW", "2379.TW", "2308.TW"]
    },
    "2317.TW": {
        "name": "鴻海",
        "group": "EMS / AI 伺服器",
        "concepts": ["AI 伺服器", "電動車", "蘋果供應鏈"],
        "supply_chain": {
            "upstream": ["1301.TW", "1303.TW", "2408.TW"],
            "midstream": ["2317.TW", "3231.TW", "2382.TW"],
            "downstream": ["2356.TW", "3017.TW", "6669.TW"]
        },
        "related": ["3231.TW", "2382.TW", "2356.TW", "3017.TW", "6669.TW", "2324.TW"]
    },
    "2454.TW": {
        "name": "聯發科",
        "group": "IC 設計",
        "concepts": ["邊緣 AI", "手機晶片", "網通"],
        "supply_chain": {
            "upstream": ["2330.TW", "5347.TWO"],
            "midstream": ["2454.TW", "2379.TW"],
            "downstream": ["2357.TW", "2382.TW", "2301.TW"]
        },
        "related": ["3034.TW", "2379.TW", "4966.TW", "6415.TW", "8299.TWO"]
    },
    "2308.TW": {
        "name": "台達電",
        "group": "電源供應 / 工業自動化",
        "concepts": ["電動車", "資料中心", "散熱電源"],
        "supply_chain": {
            "upstream": ["2303.TW", "3711.TW"],
            "midstream": ["2308.TW", "3017.TW"],
            "downstream": ["6669.TW", "4938.TW", "2356.TW"]
        },
        "related": ["3017.TW", "6669.TW", "2356.TW", "4938.TW", "3044.TW"]
    },
    "0050.TW": {
        "name": "元大台灣50",
        "group": "台灣大型權值 ETF",
        "concepts": ["大型權值股", "被動投資", "大盤連動"],
        "supply_chain": {
            "upstream": ["2330.TW", "2317.TW", "2454.TW"],
            "midstream": ["0050.TW"],
            "downstream": ["006208.TW", "00631L.TW"]
        },
        "related": ["2330.TW", "2317.TW", "2454.TW", "2308.TW", "2882.TW", "2412.TW"]
    }
}

TWSE_PROFILE_CACHE = {"ts": 0, "listed": [], "otc": []}
TWSE_PROFILE_TTL = 43200

FILTER_KEYS = {
    "近5日跌幅超過10%": "drop_5d_10",
    "近5日漲幅超過10%": "rise_5d_10",
    "外資或投信近期連續買超": "chip_buy",
    "預估殖利率大於5%": "dividend_5",
    "本益比低於同業平均": "pe_low",
    "營收連續三個月年月雙增": "revenue_3m",
    "站上20日均線": "above_ma20",
    "近5日平均量放大30%": "vol_up_30"
}

def _load_market_profiles():
    now = time.time()
    if TWSE_PROFILE_CACHE["listed"] and now - TWSE_PROFILE_CACHE["ts"] < TWSE_PROFILE_TTL:
        return TWSE_PROFILE_CACHE["listed"], TWSE_PROFILE_CACHE["otc"]

    listed, otc = [], []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json"
    }
    try:
        r1 = requests.get("https://openapi.twse.com.tw/v1/opendata/t187ap03_L", headers=headers, timeout=12)
        if r1.ok:
            listed = r1.json()
    except Exception:
        pass
    try:
        r2 = requests.get("https://openapi.twse.com.tw/v1/opendata/t187ap03_O", headers=headers, timeout=12)
        if r2.ok:
            otc = r2.json()
    except Exception:
        pass

    TWSE_PROFILE_CACHE["ts"] = now
    TWSE_PROFILE_CACHE["listed"] = listed if isinstance(listed, list) else []
    TWSE_PROFILE_CACHE["otc"] = otc if isinstance(otc, list) else []
    return TWSE_PROFILE_CACHE["listed"], TWSE_PROFILE_CACHE["otc"]

def _pick_field(row: dict, names: List[str]) -> str:
    for n in names:
        if n in row and row[n] not in (None, ""):
            return str(row[n]).strip()
    return ""

def _find_company_profile(ticker: str) -> Dict:
    code = ticker.split(".")[0]
    listed, otc = _load_market_profiles()

    for row in listed:
        c = _pick_field(row, ["公司代號", "代號", "Code"])
        if c == code:
            return {
                "ticker": f"{code}.TW",
                "name": _pick_field(row, ["公司簡稱", "公司名稱", "Name"]) or code,
                "industry": _pick_field(row, ["產業別", "Industry"]) or "未分類",
                "market": "listed"
            }
    for row in otc:
        c = _pick_field(row, ["公司代號", "代號", "Code"])
        if c == code:
            return {
                "ticker": f"{code}.TWO",
                "name": _pick_field(row, ["公司簡稱", "公司名稱", "Name"]) or code,
                "industry": _pick_field(row, ["產業別", "Industry"]) or "未分類",
                "market": "otc"
            }
    return {"ticker": ticker, "name": code, "industry": "未分類", "market": "unknown"}

def _industry_concepts(industry: str) -> List[str]:
    if "半導體" in industry:
        return ["半導體", "AI", "HPC", "先進製程"]
    if "電子零組件" in industry:
        return ["電子零組件", "AI 伺服器", "高速傳輸"]
    if "電腦及週邊" in industry:
        return ["伺服器", "筆電", "AI PC"]
    if "通信網路" in industry:
        return ["網通", "資料中心", "邊緣運算"]
    if "光電" in industry:
        return ["光電", "面板", "車用光學"]
    if "金融" in industry or "保險" in industry:
        return ["金融股", "高股息", "利率敏感"]
    return [industry or "未分類", "待補充"]

def _build_industry_peers(target_ticker: str, industry: str, limit: int = 9) -> List[str]:
    listed, otc = _load_market_profiles()
    peers = []
    target_code = target_ticker.split(".")[0]
    for row in listed:
        c = _pick_field(row, ["公司代號", "代號", "Code"])
        ind = _pick_field(row, ["產業別", "Industry"])
        if c and c != target_code and ind == industry:
            peers.append(f"{c}.TW")
            if len(peers) >= limit:
                return peers
    for row in otc:
        c = _pick_field(row, ["公司代號", "代號", "Code"])
        ind = _pick_field(row, ["產業別", "Industry"])
        if c and c != target_code and ind == industry:
            peers.append(f"{c}.TWO")
            if len(peers) >= limit:
                return peers
    return peers

def ensure_relation_profile(ticker: str, ai_enricher=None):
    if ticker in RELATION_DB:
        return
    code = ticker.split(".")[0]
    for k in RELATION_DB.keys():
        if k.split(".")[0] == code:
            return

    profile = _find_company_profile(ticker)
    p_ticker = profile["ticker"]
    name = profile["name"]
    industry = profile["industry"]
    peers = _build_industry_peers(p_ticker, industry, limit=9)

    relation = {
        "name": name,
        "group": industry or "未分類",
        "concepts": _industry_concepts(industry),
        "supply_chain": {
            "upstream": peers[:3],
            "midstream": [p_ticker],
            "downstream": peers[3:6]
        },
        "related": peers[:8]
    }

    if ai_enricher:
        try:
            ai_data = ai_enricher(p_ticker, name, industry)
            if isinstance(ai_data, dict):
                relation["name"] = ai_data.get("name") or relation["name"]
                relation["group"] = ai_data.get("group") or relation["group"]
                c = ai_data.get("concepts")
                if isinstance(c, list) and c:
                    relation["concepts"] = [str(x).strip() for x in c if str(x).strip()][:8]
                r = ai_data.get("related")
                if isinstance(r, list) and r:
                    relation["related"] = [str(x).strip().upper() for x in r if str(x).strip()][:12]
                sc = ai_data.get("supply_chain")
                if isinstance(sc, dict):
                    relation["supply_chain"] = {
                        "upstream": [str(x).strip().upper() for x in sc.get("upstream", []) if str(x).strip()][:6],
                        "midstream": [str(x).strip().upper() for x in sc.get("midstream", []) if str(x).strip()][:6] or [p_ticker],
                        "downstream": [str(x).strip().upper() for x in sc.get("downstream", []) if str(x).strip()][:6]
                    }
        except Exception:
            pass

    RELATION_DB[p_ticker] = relation

def _normalize_ticker(raw: str) -> str:
    txt = (raw or "").strip().upper()
    m = re.search(r"\d{4}", txt)
    if not m:
        return txt
    base = m.group(0)
    if ".TW" in txt or ".TWO" in txt:
        return f"{base}.TWO" if ".TWO" in txt else f"{base}.TW"
    return f"{base}.TW"

def _pick_relation(ticker: str) -> Dict:
    if ticker in RELATION_DB:
        return RELATION_DB[ticker]
    code = ticker.split(".")[0]
    for k, v in RELATION_DB.items():
        if code in k:
            return v
    return {
        "name": code,
        "group": "未分類",
        "concepts": ["待補充"],
        "supply_chain": {"upstream": [], "midstream": [ticker], "downstream": []},
        "related": []
    }

def _get_ticker_with_name(ticker: str) -> str:
    if ticker in RELATION_DB:
        name = RELATION_DB[ticker].get("name", ticker.split('.')[0])
    else:
        profile = _find_company_profile(ticker)
        name = profile.get("name", ticker.split('.')[0])
    return f"{ticker} {name}"

def _get_history_safely(ticker: str):
    df = DataProvider.get_stock_history(ticker, days=80)
    if df.empty and ticker.endswith(".TW"):
        df = DataProvider.get_stock_history(ticker.replace(".TW", ".TWO"), days=80)
    return df

def _calc_metrics(ticker: str) -> Dict:
    df = _get_history_safely(ticker)
    if df.empty or len(df) < 6:
        return {
            "ticker": ticker,
            "price": 0,
            "pct_5d": 0,
            "ma20": 0,
            "above_ma20": False,
            "vol_up_30": False,
            "has_data": False
        }

    close = df["Close"].astype(float)
    vol = df["Volume"].astype(float)
    last = float(close.iloc[-1])
    prev_5 = float(close.iloc[-6])
    pct_5d = ((last - prev_5) / prev_5 * 100) if prev_5 else 0
    ma20 = float(close.tail(20).mean()) if len(close) >= 20 else float(close.mean())
    recent_vol = float(vol.tail(5).mean())
    base_vol = float(vol.tail(25).head(20).mean()) if len(vol) >= 25 else float(vol.mean())
    vol_up_30 = base_vol > 0 and recent_vol >= base_vol * 1.3

    return {
        "ticker": ticker,
        "price": round(last, 2),
        "pct_5d": round(pct_5d, 2),
        "ma20": round(ma20, 2),
        "above_ma20": last >= ma20,
        "vol_up_30": vol_up_30,
        "close_series": close.tail(20).tolist(),
        "volume_series": vol.tail(20).tolist(),
        "has_data": True
    }

def _detect_main_force(metrics: Dict) -> Dict:
    if not metrics.get("has_data"):
        return {
            "score": 0,
            "bias": "無法判斷",
            "patterns": ["資料不足，無法辨識主力操作模式"],
            "summary": "缺少有效行情資料"
        }

    closes = metrics.get("close_series", [])
    vols = metrics.get("volume_series", [])
    if len(closes) < 10 or len(vols) < 10:
        return {
            "score": 0,
            "bias": "無法判斷",
            "patterns": ["樣本不足，無法辨識主力操作模式"],
            "summary": "近20日資料不足"
        }

    last_price = closes[-1]
    low_20 = min(closes)
    high_20 = max(closes)
    recent_5_avg = sum(vols[-5:]) / 5
    base_15_avg = sum(vols[:-5]) / max(1, len(vols[:-5]))
    vol_ratio = recent_5_avg / base_15_avg if base_15_avg > 0 else 1
    range_pos = (last_price - low_20) / (high_20 - low_20) if high_20 > low_20 else 0.5

    score = 50
    patterns = []

    if vol_ratio >= 1.5 and range_pos >= 0.7:
        score += 20
        patterns.append("放量突破偏多：主力偏向追價拉抬")
    elif vol_ratio >= 1.3 and 0.4 <= range_pos < 0.7:
        score += 10
        patterns.append("放量整理：主力可能在區間內換手吸籌")
    elif vol_ratio < 0.9 and range_pos >= 0.65:
        score += 5
        patterns.append("量縮守高：主力偏向鎖籌等待續攻")

    if range_pos <= 0.25 and vol_ratio >= 1.4:
        score -= 15
        patterns.append("低檔爆量：主力洗盤或調節，波動風險偏高")
    elif range_pos >= 0.85 and vol_ratio >= 1.6:
        score -= 10
        patterns.append("高檔爆量：主力可能邊拉邊出，留意反轉")

    if metrics.get("pct_5d", 0) >= 10 and vol_ratio >= 1.3:
        score += 8
        patterns.append("短線強攻：主力短期作價動能明顯")
    elif metrics.get("pct_5d", 0) <= -10 and vol_ratio >= 1.3:
        score -= 8
        patterns.append("急跌放量：主力可能測試支撐或轉弱出貨")

    score = max(0, min(100, int(round(score))))
    if score >= 70:
        bias = "主力買超"
    elif score >= 55:
        bias = "主力中性偏多"
    elif score >= 45:
        bias = "主力中性"
    elif score >= 30:
        bias = "主力中性偏空"
    else:
        bias = "主力賣超"

    if not patterns:
        patterns.append("區間整理：目前未見明顯主力表態")

    return {
        "score": score,
        "bias": bias,
        "patterns": patterns,
        "summary": f"近5日量比 {vol_ratio:.2f}x，20日區間位置 {range_pos * 100:.0f}%"
    }

def _evaluate_filter(filter_key: str, metrics: Dict) -> Tuple[bool, str]:
    if not metrics.get("has_data"):
        return False, ""

    pct_5d = metrics["pct_5d"]
    if filter_key == "drop_5d_10":
        return pct_5d <= -10, "跌逾10%(錯殺)"
    if filter_key == "rise_5d_10":
        return pct_5d >= 10, "漲逾10%(強勢)"
    if filter_key == "above_ma20":
        return metrics["above_ma20"], "站上月線"
    if filter_key == "vol_up_30":
        return metrics["vol_up_30"], "量能放大30%"
    
    if filter_key == "chip_buy":
        return False, "法人連買(待串接)"
    if filter_key == "dividend_5":
        return False, "高殖利率(待串接)"
    if filter_key == "pe_low":
        return False, "低本益比(待串接)"
    if filter_key == "revenue_3m":
        return False, "營收雙增(待串接)"

    return False, ""

def analyze_related_stocks(target_inputs: List[str], filters: List[str], ai_enricher=None):
    normalized_filters = [FILTER_KEYS[f] for f in filters if f in FILTER_KEYS]
    out = []

    for raw in target_inputs:
        ticker = _normalize_ticker(raw)
        ensure_relation_profile(ticker, ai_enricher=ai_enricher)
        relation = _pick_relation(ticker)

        related_universe = []
        related_universe.extend(relation.get("related", []))
        for lvl in ("upstream", "midstream", "downstream"):
            related_universe.extend(relation.get("supply_chain", {}).get(lvl, []))

        dedup_related = []
        seen = set()
        for r in related_universe:
            if r not in seen:
                seen.add(r)
                dedup_related.append(r)

        evaluated = []
        for r_ticker in dedup_related:
            metrics = _calc_metrics(r_ticker)
            main_force = _detect_main_force(metrics)
            
            tags = []
            for fk in normalized_filters:
                ok, tag_name = _evaluate_filter(fk, metrics)
                if ok:
                    tags.append(tag_name)

            if main_force["score"] >= 70:
                tags.append("主力買超")
            elif main_force["score"] <= 30:
                tags.append("主力賣超")

            if r_ticker in RELATION_DB:
                r_name = RELATION_DB[r_ticker].get("name", r_ticker.split('.')[0])
            else:
                r_name = _find_company_profile(r_ticker).get("name", r_ticker.split('.')[0])

            evaluated.append({
                "ticker": r_ticker,
                "name": r_name,
                "price": metrics["price"],
                "pct_5d": metrics["pct_5d"],
                "tags": tags,
                "main_force": main_force
            })

        supply_chain = relation.get("supply_chain", {})
        out_upstream = [_get_ticker_with_name(x) for x in supply_chain.get("upstream", [])]
        out_midstream = [_get_ticker_with_name(x) for x in supply_chain.get("midstream", [])]
        out_downstream = [_get_ticker_with_name(x) for x in supply_chain.get("downstream", [])]

        out.append({
            "target": {
                "ticker": ticker,
                "name": relation.get("name", ticker)
            },
            "group": relation.get("group", "未分類"),
            "concepts": relation.get("concepts", []),
            "supply_chain": {
                "upstream": out_upstream,
                "midstream": out_midstream,
                "downstream": out_downstream
            },
            "evaluated_stocks": evaluated
        })

    return out
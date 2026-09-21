"""Cash-only, next-open MA20/RSI backtest with explicit Taiwan-stock costs."""
from __future__ import annotations

import math
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

import pandas as pd

from analyzer import TechnicalAnalyzer
from data_provider import DataProvider


INITIAL_CAPITAL = Decimal("100000.00")
WARMUP_BARS = 30
SUPPORTED_BACKTEST_DAYS = (30, 90, 180, 365)
NTD = Decimal("1")
CENT = Decimal("0.01")
DEFAULT_COMMISSION_RATE = Decimal("0.001425")
DEFAULT_MIN_COMMISSION = Decimal("20")
DEFAULT_SELL_TAX_RATE = Decimal("0.003")
LIMITATIONS = [
    "僅使用未還原日線；不含股利、拆股與盤中流動性。",
    "訊號以當日收盤形成，僅在下一交易日開盤模擬成交；不保證實際成交價。",
    "成本是普通股示例，ETF、當沖與個別券商費率可能不同。",
    "歷史回測不代表未來績效，也不構成投資建議。",
]


def _money(value) -> Decimal:
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def _cost(gross: Decimal, rate: Decimal, minimum: Decimal = Decimal("0")) -> Decimal:
    return max(minimum.quantize(NTD, rounding=ROUND_HALF_UP),
               (gross * rate).quantize(NTD, rounding=ROUND_HALF_UP))


def _percent(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _date(index_value) -> date:
    return pd.Timestamp(index_value).date()


def _signal(previous, current) -> str:
    if any(pd.isna(value) for value in (
        previous["Close"], previous["MA20"], current["Close"], current["MA20"], current["RSI"]
    )):
        return "NEUTRAL"
    if previous["Close"] < previous["MA20"] and current["Close"] > current["MA20"] and current["RSI"] < 70:
        return "BUY"
    if (previous["Close"] > previous["MA20"] and current["Close"] < current["MA20"]) or current["RSI"] > 75:
        return "SELL"
    return "NEUTRAL"


def _max_affordable(cash: Decimal, price: Decimal, rate: Decimal, minimum: Decimal) -> int:
    low, high = 0, int(cash // price)
    while low < high:
        middle = (low + high + 1) // 2
        gross = price * middle
        if gross + _cost(gross, rate, minimum) <= cash:
            low = middle
        else:
            high = middle - 1
    return low


class Backtester:
    @staticmethod
    def run(
        ticker: str,
        days: int = 180,
        commission_rate=DEFAULT_COMMISSION_RATE,
        min_commission=DEFAULT_MIN_COMMISSION,
        sell_tax_rate=DEFAULT_SELL_TAX_RATE,
        *,
        frame: pd.DataFrame | None = None,
        now: date | None = None,
    ) -> dict:
        def error(code: str, message: str) -> dict:
            return {"status": "error", "code": code, "message": message}

        try:
            commission_rate = Decimal(str(commission_rate))
            min_commission = Decimal(str(min_commission))
            sell_tax_rate = Decimal(str(sell_tax_rate))
            if type(days) is not int or days not in SUPPORTED_BACKTEST_DAYS:
                return error("unsupported_window", "回測僅支援 30、90、180 或 365 個交易日")
            if any(not value.is_finite() or value < 0 for value in (
                commission_rate, min_commission, sell_tax_rate
            )) or commission_rate >= 1 or sell_tax_rate >= 1 or min_commission > INITIAL_CAPITAL:
                return error("invalid_cost", "交易成本設定無效")
        except (ArithmeticError, ValueError, TypeError):
            return error("invalid_cost", "交易成本設定無效")

        if frame is None:
            try:
                frame = DataProvider.get_backtest_history(ticker, days + WARMUP_BARS)
            except Exception:
                return error("source_unavailable", "歷史行情來源目前無法取得")
        if frame is None or frame.empty:
            return error("source_unavailable", "歷史行情來源目前無法取得")
        source = dict(frame.attrs.get("route") or {})
        if not source.get("source"):
            return error("source_unverified", "歷史行情缺少可驗證的來源資訊")
        if source.get("price_basis") != "unadjusted_daily":
            return error("price_basis_unverified", "歷史行情價格基礎無法確認")
        required = {"Open", "High", "Low", "Close", "Volume"}
        if not required.issubset(frame.columns):
            return error("invalid_data", "歷史行情欄位不完整")
        try:
            data = frame.copy().sort_index()
            if data.index.has_duplicates:
                return error("invalid_data", "歷史行情日期重複")
            values = data[list(required)].apply(pd.to_numeric, errors="coerce")
            if values.isna().any().any() or not values.map(math.isfinite).all().all():
                return error("invalid_data", "歷史行情包含無效數值")
            prices = values[["Open", "High", "Low", "Close"]]
            if (prices < 0.01).any().any() or (prices > 1_000_000_000).any().any() or (values["Volume"] < 0).any() or (values["Volume"] > 1_000_000_000_000_000).any():
                return error("invalid_data", "歷史行情價格或成交量無效")
            as_of = _date(data.index[-1])
            if source.get("asof") != as_of.isoformat():
                return error("source_date_mismatch", "歷史行情來源日期與資料不一致")
            today = now or datetime.now().date()
            if not 0 <= (today - as_of).days <= 7:
                return error("stale_data", "歷史行情日期過時或超前")
            if len(data) < days + WARMUP_BARS:
                return error("insufficient_data", "歷史行情不足回測窗口與 30 個交易日暖機期")
            data = data.iloc[-(days + WARMUP_BARS):].copy()
            data.attrs["route"] = source
            indicators = TechnicalAnalyzer.calculate_indicators(data)
            if indicators[["MA20", "RSI"]].iloc[WARMUP_BARS:].isna().any().any():
                return error("insufficient_data", "技術指標暖機資料不足")
        except (ValueError, TypeError, KeyError, OverflowError, InvalidOperation):
            return error("invalid_data", "歷史行情無法驗證")

        window = indicators.iloc[WARMUP_BARS:]
        first_open = _money(window.iloc[0]["Open"])
        last_close = _money(window.iloc[-1]["Close"])
        bh_shares = _max_affordable(INITIAL_CAPITAL, first_open, commission_rate, min_commission)
        bh_gross = first_open * bh_shares
        bh_fee = _cost(bh_gross, commission_rate, min_commission) if bh_shares else Decimal("0")
        bh_cash = INITIAL_CAPITAL - bh_gross - bh_fee
        bh_final = bh_cash + bh_shares * last_close

        cash, shares = INITIAL_CAPITAL, 0
        entry_cost = Decimal("0")
        trades: list[dict] = []
        closed_returns: list[Decimal] = []
        peak = INITIAL_CAPITAL
        max_drawdown = Decimal("0")
        latest_signal = "NEUTRAL"
        for index in range(WARMUP_BARS, len(indicators)):
            row = indicators.iloc[index]
            previous_signal = _signal(indicators.iloc[index - 2], indicators.iloc[index - 1])
            open_price = _money(row["Open"])
            trade_date = _date(row.name).isoformat()
            if previous_signal == "BUY" and shares == 0:
                quantity = _max_affordable(cash, open_price, commission_rate, min_commission)
                if quantity:
                    gross = open_price * quantity
                    fee = _cost(gross, commission_rate, min_commission)
                    entry_cost = gross + fee
                    cash -= entry_cost
                    shares = quantity
                    trades.append({
                        "date": trade_date, "action": "BUY", "price": float(open_price),
                        "shares": quantity, "gross": float(gross), "commission": float(fee),
                        "tax": 0.0, "net_cash_flow": float(-entry_cost),
                        "cash_after": float(_money(cash)), "return_pct": None,
                    })
            elif previous_signal == "SELL" and shares:
                gross = open_price * shares
                fee = _cost(gross, commission_rate, min_commission)
                tax = _cost(gross, sell_tax_rate)
                proceeds = gross - fee - tax
                if cash + proceeds < 0:
                    # A cash-only account cannot fund a sale whose fees exceed
                    # both its proceeds and the cash already on hand.
                    failure = error("sale_cost_unfunded", "賣出收入與現金不足以支付交易成本，回測已停止")
                    failure.update({
                        "trade_date": trade_date,
                        "available_cash": float(_money(cash)),
                        "sale_gross": float(_money(gross)),
                        "sale_commission": float(_money(fee)),
                        "sale_tax": float(_money(tax)),
                        "shortfall": float(_money(-(cash + proceeds))),
                    })
                    return failure
                cash += proceeds
                realized = proceeds - entry_cost
                ret = realized / entry_cost * 100
                closed_returns.append(ret)
                trades.append({
                    "date": trade_date, "action": "SELL", "price": float(open_price),
                    "shares": shares, "gross": float(gross), "commission": float(fee),
                    "tax": float(tax), "net_cash_flow": float(proceeds),
                    "cash_after": float(_money(cash)), "return_pct": _percent(ret),
                    "realized_pnl": float(_money(realized)),
                })
                shares = 0
                entry_cost = Decimal("0")

            equity = cash + shares * _money(row["Close"])
            peak = max(peak, equity)
            if peak:
                max_drawdown = max(max_drawdown, (peak - equity) / peak * 100)
            if index == len(indicators) - 1:
                latest_signal = _signal(indicators.iloc[index - 1], row)

        final_value = cash + shares * last_close
        strategy_return = (final_value / INITIAL_CAPITAL - 1) * 100
        bh_return = (bh_final / INITIAL_CAPITAL - 1) * 100
        win_rate = (
            _percent(Decimal(sum(value > 0 for value in closed_returns)) / len(closed_returns) * 100)
            if closed_returns else None
        )
        return {
            "status": "success", "ticker": ticker, "days": days,
            "currency": "TWD", "initial_capital": float(INITIAL_CAPITAL),
            "window_start": _date(window.index[0]).isoformat(),
            "window_end": _date(window.index[-1]).isoformat(),
            "source": source["source"], "as_of": as_of.isoformat(),
            "price_basis": source["price_basis"],
            "costs": {"commission_rate": float(commission_rate),
                      "min_commission": float(min_commission),
                      "sell_tax_rate": float(sell_tax_rate),
                      "rounding": "NT$1 ROUND_HALF_UP"},
            "strategy_return": _percent(strategy_return),
            "buy_hold_return": _percent(bh_return),
            "outperformance": _percent(strategy_return - bh_return),
            "trade_count": len(trades), "closed_trade_count": len(closed_returns),
            "final_value": float(_money(final_value)),
            "ending_cash": float(_money(cash)), "ending_shares": shares,
            "buy_hold_final_value": float(_money(bh_final)),
            "buy_hold_shares": bh_shares,
            "win_rate": win_rate, "max_drawdown": _percent(max_drawdown),
            "latest_signal": latest_signal, "trades": trades,
            "limitations": LIMITATIONS,
        }

"""After-close email alerts for simultaneous low-zone MACD and KD crossovers."""

import asyncio
import hashlib
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time
from email.errors import HeaderParseError
from email.headerregistry import Address
from zoneinfo import ZoneInfo

import aiohttp
import numpy as np
import pandas as pd

from analyzer import TechnicalAnalyzer


LOGGER = logging.getLogger(__name__)
TAIPEI = ZoneInfo("Asia/Taipei")
SCAN_TIME = time(20, 30)
HISTORY_DAYS = 180
RECENT_HISTORY_DAYS = 60
MINIMUM_BARS = 35
OVERSOLD_KD = 20
ETF_CODE = re.compile(r"00[0-9]{2,4}[A-Z]?(?:\.TW|\.TWO)?")
DOMAIN_LABEL = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?")
RESEND_ENDPOINT = "https://api.resend.com/emails"


def _is_mailbox(value: str) -> bool:
    if len(value) > 254 or not value.isascii():
        return False
    try:
        address = Address(addr_spec=value)
    except (ValueError, HeaderParseError, IndexError):
        return False
    labels = address.domain.split(".")
    return (
        address.addr_spec == value and 0 < len(address.username) <= 64
        and len(labels) > 1 and all(DOMAIN_LABEL.fullmatch(label) for label in labels)
    )


@dataclass(frozen=True)
class ETFAlertConfig:
    enabled: bool = False
    tickers: tuple[str, ...] = ()
    sender: str = field(default="", repr=False)
    recipient: str = field(default="", repr=False)
    api_key: str = field(default="", repr=False)
    errors: tuple[str, ...] = ()

    @property
    def ready(self) -> bool:
        return self.enabled and not self.errors

    @classmethod
    def from_env(cls, env=None):
        env = os.environ if env is None else env
        enabled = env.get("ETF_ALERT_ENABLED", "false").strip().lower()
        if enabled == "false":
            return cls()
        if enabled != "true":
            return cls(errors=("invalid_enabled",))

        codes = [code.strip().upper() for code in env.get("ETF_ALERT_TICKERS", "").split(",")]
        codes = [code for code in codes if code]
        tickers = tuple(dict.fromkeys(code if "." in code else f"{code}.TW" for code in codes))
        sender = env.get("ETF_ALERT_EMAIL_FROM", "").strip()
        recipient = env.get("ETF_ALERT_EMAIL_TO", "").strip()
        api_key = env.get("ETF_ALERT_RESEND_API_KEY", "").strip()
        errors = []
        if not codes or any(not ETF_CODE.fullmatch(code) for code in codes):
            errors.append("invalid_tickers")
        elif len(tickers) > 20:
            errors.append("too_many_tickers")
        if not _is_mailbox(sender):
            errors.append("invalid_sender")
        if not _is_mailbox(recipient):
            errors.append("invalid_recipient")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", api_key):
            errors.append("invalid_api_key")
        return cls(True, tickers, sender, recipient, api_key, tuple(errors))


def _taipei_time(now: datetime) -> datetime:
    if now.tzinfo is None:
        return now.replace(tzinfo=TAIPEI)
    return now.astimezone(TAIPEI)


def is_etf_alert_time(now: datetime | None = None) -> bool:
    local = _taipei_time(now or datetime.now(TAIPEI))
    return local.weekday() < 5 and local.time() >= SCAN_TIME


@dataclass(frozen=True)
class GoldenCross:
    market_date: date
    close: float
    macd: float
    signal: float
    k: float
    d: float

    @property
    def j(self) -> float:
        return 3 * self.k - 2 * self.d


def find_golden_cross(frame: pd.DataFrame, market_date: date) -> GoldenCross | None:
    """Evaluate only the completed session and the preceding available bar."""
    columns = ["Close", "Low", "High", "Volume"]
    if not isinstance(frame, pd.DataFrame) or len(frame) < MINIMUM_BARS:
        return None
    if not isinstance(frame.index, pd.DatetimeIndex) or not set(columns).issubset(frame.columns):
        return None
    if not frame.columns.is_unique or frame.index.hasnans or market_date.weekday() >= 5:
        return None

    index = frame.index
    if index.tz is not None:
        index = index.tz_convert(TAIPEI)
    index = index.normalize()
    if not index.is_unique or index.max().date() != market_date:
        return None

    bars = frame[columns].apply(pd.to_numeric, errors="coerce")
    bars.index = index
    bars = bars.sort_index()
    if not np.isfinite(bars.to_numpy(dtype=float, na_value=np.nan)).all():
        return None
    if ((bars["Low"] <= 0) | (bars["Close"] < bars["Low"]) |
            (bars["Close"] > bars["High"]) | (bars["Volume"] < 0)).any():
        return None
    if (bars["Volume"].tail(2) <= 0).any():
        return None
    kd_range = bars["High"].rolling(9).max() - bars["Low"].rolling(9).min()
    if (kd_range.tail(2) <= 0).any():
        return None

    indicators = TechnicalAnalyzer.calculate_indicators(bars)
    last_two = indicators[["MACD", "Signal", "K", "D"]].tail(2)
    if not np.isfinite(last_two.to_numpy()).all():
        return None
    previous, current = last_two.iloc[0], last_two.iloc[1]
    if not (previous.MACD <= previous.Signal and current.Signal < current.MACD < 0
            and previous.K <= previous.D < OVERSOLD_KD and current.K > current.D):
        return None
    return GoldenCross(
        market_date, float(bars["Close"].iloc[-1]),
        float(current.MACD), float(current.Signal), float(current.K), float(current.D),
    )


class ResendEmailSender:
    def __init__(self, config: ETFAlertConfig):
        self.config = config

    async def send(self, ticker: str, signal: GoldenCross) -> bool:
        event = f"{ticker}|{signal.market_date}|{self.config.recipient.casefold()}"
        key = hashlib.sha256(event.encode()).hexdigest()
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Idempotency-Key": f"etf-golden-cross/{key}",
        }
        payload = {
            "from": self.config.sender,
            "to": [self.config.recipient],
            "subject": f"ETF 黃金交叉通知｜{ticker}｜{signal.market_date}",
            "text": (
                f"{ticker} 在 {signal.market_date} 收盤時，MACD 與 KD 同時出現低檔黃金交叉。\n\n"
                f"收盤價：{signal.close:.2f}\n"
                f"MACD：{signal.macd:.4f}　訊號線：{signal.signal:.4f}\n"
                f"K：{signal.k:.2f}　D：{signal.d:.2f}　J：{signal.j:.2f}"
            ),
        }
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            status = await self._post(session, headers, payload)
            if status in (0, 408, 409, 429) or 500 <= status < 600:
                await asyncio.sleep(1)
                status = await self._post(session, headers, payload)
        if 200 <= status < 300:
            return True
        LOGGER.warning("etf_golden_cross delivery_failed status=%d", status)
        return False

    @staticmethod
    async def _post(session, headers, payload) -> int:
        try:
            async with session.post(
                RESEND_ENDPOINT, headers=headers, json=payload, allow_redirects=False,
            ) as response:
                return response.status
        except (aiohttp.ClientError, TimeoutError):
            return 0


async def load_etf_alert_history(ticker: str) -> pd.DataFrame:
    from async_data_provider import get_async_provider

    provider = await get_async_provider()
    history = await provider.get_stock_history(ticker, days=HISTORY_DAYS)
    if history.empty:
        history = await provider.get_stock_history(ticker, days=RECENT_HISTORY_DAYS)
    return history


class ETFGoldenCrossMonitor:
    def __init__(self, config: ETFAlertConfig, market_loader=load_etf_alert_history,
                 sender=None, clock=None):
        self.config = config
        self.market_loader = market_loader
        self.sender = sender if sender is not None else ResendEmailSender(config)
        self.clock = clock if clock is not None else lambda: datetime.now(TAIPEI)

    async def run(self) -> dict:
        now = _taipei_time(self.clock())
        results = {"checked": 0, "matched": 0, "sent": 0, "failed": 0}
        if not self.config.ready:
            return {"status": "invalid_config" if self.config.errors else "disabled", **results}
        if not is_etf_alert_time(now):
            return {"status": "outside_scan_window", **results}

        for ticker in self.config.tickers:
            if _taipei_time(self.clock()).date() != now.date():
                break
            results["checked"] += 1
            try:
                frame = await self.market_loader(ticker)
                if frame is None or frame.empty:
                    results["failed"] += 1
                    LOGGER.warning("etf_golden_cross history_unavailable ticker=%s", ticker)
                    continue
                signal = find_golden_cross(frame, now.date())
                if signal is None:
                    continue
                if _taipei_time(self.clock()).date() != now.date():
                    break
                results["matched"] += 1
                if await self.sender.send(ticker, signal):
                    results["sent"] += 1
                else:
                    results["failed"] += 1
            except Exception:
                results["failed"] += 1
                LOGGER.warning("etf_golden_cross ticker_failed ticker=%s", ticker)

        status = "partial" if results["failed"] else "success"
        LOGGER.info("etf_golden_cross date=%s status=%s counts=%s", now.date(), status, results)
        return {"status": status, **results}


async def _run_once() -> int:
    from async_data_provider import close_async_provider

    config = ETFAlertConfig.from_env()
    if config.errors:
        LOGGER.warning("etf_golden_cross configuration_invalid reasons=%s", config.errors)
        return 1
    try:
        result = await ETFGoldenCrossMonitor(config).run()
    finally:
        await close_async_provider()
    if result["status"] in ("disabled", "outside_scan_window"):
        LOGGER.info("etf_golden_cross status=%s", result["status"])
    return int(result["status"] == "partial")


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(asyncio.run(_run_once()))

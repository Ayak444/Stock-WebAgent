"""After-close Discord alerts for simultaneous low-zone MACD and KD crossovers."""

import asyncio
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time
from email.errors import HeaderParseError
from email.headerregistry import Address
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from account_alert_security import decrypt_webhook
from analyzer import TechnicalAnalyzer
from holder_volume_alerts import _invoke
from notifier import DiscordNotifier


LOGGER = logging.getLogger(__name__)
TAIPEI = ZoneInfo("Asia/Taipei")
SCAN_TIME = time(20, 30)
HISTORY_DAYS = 180
RECENT_HISTORY_DAYS = 60
MINIMUM_BARS = 35
OVERSOLD_KD = 20
ETF_CODE = re.compile(r"00[0-9]{2,4}[A-Z]?(?:\.TW|\.TWO)?")
DOMAIN_LABEL = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?")
EVENT_TICKER_PREFIX = "etf-golden-cross:"


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
    account_email: str = field(default="", repr=False)
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
        account_email = env.get("ETF_ALERT_DISCORD_ACCOUNT_EMAIL", "").strip().lower()
        if not account_email:
            account_email = env.get("ETF_ALERT_EMAIL_TO", "").strip().lower()
        errors = []
        if not codes or any(not ETF_CODE.fullmatch(code) for code in codes):
            errors.append("invalid_tickers")
        elif len(tickers) > 20:
            errors.append("too_many_tickers")
        if not _is_mailbox(account_email):
            errors.append("invalid_account_email")
        return cls(True, tickers, account_email, tuple(errors))


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


async def load_etf_alert_history(ticker: str) -> pd.DataFrame:
    from async_data_provider import get_async_provider

    provider = await get_async_provider()
    history = await provider.get_stock_history(ticker, days=HISTORY_DAYS)
    if history.empty:
        history = await provider.get_stock_history(ticker, days=RECENT_HISTORY_DAYS)
    return history


class ETFGoldenCrossMonitor:
    def __init__(self, config: ETFAlertConfig, store, market_loader=load_etf_alert_history,
                 notifier_factory=DiscordNotifier, *, clock=None):
        self.config = config
        self.store = store
        self.market_loader = market_loader
        self.notifier_factory = notifier_factory
        self.clock = clock if clock is not None else lambda: datetime.now(TAIPEI)

    def _configuration_status(self) -> str:
        if self.config.ready:
            return "ready"
        return "invalid_config" if self.config.errors else "disabled"

    async def _resolve_destination(self) -> tuple[str, tuple[str, str] | None]:
        try:
            user_id = await _invoke(self.store.get_account_user_id_by_email, self.config.account_email)
            if not user_id:
                return "account_unavailable", None
            settings = await _invoke(self.store.get_account_volume_settings, user_id)
        except Exception:
            return "store_unavailable", None
        try:
            webhook = decrypt_webhook(settings.get("webhook_ciphertext") or "")
        except Exception:
            return "webhook_unavailable", None
        return "ready", (user_id, webhook)

    def _log_destination_status(self, status: str) -> None:
        log = LOGGER.info if status in {"ready", "disabled"} else LOGGER.warning
        log("etf_golden_cross destination=%s", status)

    async def check_destination(self) -> dict:
        """Check server-side account configuration without sending any alert."""
        status = self._configuration_status()
        if status == "ready":
            status, _ = await self._resolve_destination()
        self._log_destination_status(status)
        return {"status": status}

    async def _deliver(self, user_id: str, webhook: str, ticker: str, signal: GoldenCross) -> str:
        now = _taipei_time(self.clock())
        if now.date() != signal.market_date:
            return "outside_scan_window"
        event_ticker = f"{EVENT_TICKER_PREFIX}{ticker}"
        market_date = signal.market_date.isoformat()
        try:
            claimed = await _invoke(
                self.store.claim_account_volume_event, user_id, event_ticker, market_date, now,
            )
        except Exception:
            LOGGER.warning("etf_golden_cross event_claim_failed ticker=%s", ticker)
            return "store_unavailable"
        if not claimed:
            return "suppressed"

        sent = False
        same_day = _taipei_time(self.clock()).date() == signal.market_date
        if same_day:
            message = "\n".join([
                f"標的：{ticker}",
                f"交易日：{market_date}",
                f"收盤價：{signal.close:.2f}",
                f"MACD：{signal.macd:.4f}　訊號線：{signal.signal:.4f}",
                f"K：{signal.k:.2f}　D：{signal.d:.2f}　J：{signal.j:.2f}",
            ])
            try:
                sent = bool(await _invoke(
                    self.notifier_factory(webhook).send_alert, "ETF 低檔黃金交叉通知", message, "success",
                ))
            except Exception:
                pass

        state = "sent" if sent else "failed"
        try:
            await _invoke(
                self.store.finish_account_volume_event, user_id, event_ticker, market_date,
                state, _taipei_time(self.clock()),
            )
        except Exception:
            LOGGER.warning("etf_golden_cross event_update_failed ticker=%s delivery=%s", ticker, state)
            return "store_unavailable"
        return state if same_day else "outside_scan_window"

    async def run(self) -> dict:
        now = _taipei_time(self.clock())
        results = {"checked": 0, "matched": 0, "sent": 0, "failed": 0, "suppressed": 0}
        status = self._configuration_status()
        if status != "ready":
            return {"status": status, **results}
        if not is_etf_alert_time(now):
            return {"status": "outside_scan_window", **results}

        destination_status, destination = await self._resolve_destination()
        self._log_destination_status(destination_status)
        if destination is None:
            return {"status": destination_status, **results}
        user_id, webhook = destination

        store_failed = False
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
            except Exception:
                results["failed"] += 1
                LOGGER.warning("etf_golden_cross ticker_failed ticker=%s", ticker)
                continue
            if signal is None:
                continue
            results["matched"] += 1
            delivery = await self._deliver(user_id, webhook, ticker, signal)
            if delivery == "outside_scan_window":
                break
            if delivery == "store_unavailable":
                results["failed"] += 1
                store_failed = True
                break
            results[delivery] += 1

        status = "store_unavailable" if store_failed else ("partial" if results["failed"] else "success")
        LOGGER.info("etf_golden_cross date=%s status=%s counts=%s", now.date(), status, results)
        return {"status": status, **results}


async def _run_once(*, check: bool = False) -> int:
    from async_data_provider import close_async_provider
    from database import Database

    config = ETFAlertConfig.from_env()
    if config.errors:
        LOGGER.warning("etf_golden_cross configuration_invalid reasons=%s", config.errors)
        return 1
    if not config.enabled:
        LOGGER.info("etf_golden_cross status=disabled")
        return 0
    try:
        store = Database()
    except Exception:
        LOGGER.warning("etf_golden_cross destination=store_unavailable")
        return 1
    monitor = ETFGoldenCrossMonitor(config, store)
    try:
        result = await (monitor.check_destination() if check else monitor.run())
    finally:
        await close_async_provider()
    if result["status"] in ("disabled", "outside_scan_window"):
        LOGGER.info("etf_golden_cross status=%s", result["status"])
    return int(result["status"] not in {"success", "ready", "outside_scan_window"})


if __name__ == "__main__":
    from argparse import ArgumentParser
    from dotenv import load_dotenv

    parser = ArgumentParser(description="Run the ETF Discord alert or check its stored destination.")
    parser.add_argument("--check", action="store_true", help="Verify the destination without sending.")
    args = parser.parse_args()
    load_dotenv()
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(asyncio.run(_run_once(check=args.check)))

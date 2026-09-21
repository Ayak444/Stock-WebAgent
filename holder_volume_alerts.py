"""大戶增持與量能放大監控；所有外部 I/O 皆由可注入介面提供。"""
from __future__ import annotations

import asyncio
import inspect
import math
import os
import re
import statistics
import threading
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any, Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo
from uuid import uuid4


TAIPEI = ZoneInfo("Asia/Taipei")
HOLDER_LEVELS = frozenset({12, 13, 14, 15})
HOLDER_INCREASE_THRESHOLD_PP = 0.50
VOLUME_MULTIPLE_THRESHOLD = 1.50
MIN_BASELINE_SESSIONS = 15
MAX_BASELINE_SESSIONS = 20
HOLDER_MAX_AGE_DAYS = 14
MARKET_HOLDER_MAX_GAP_DAYS = 7
EVENT_COOLDOWN_DAYS = 7
FAILED_RETRY_HOURS = 6
EVENT_VERSION = "v1"
TICKER_PATTERN = re.compile(r"^[0-9]{4,6}\.(?:TW|TWO)$")


async def _invoke(callable_obj: Any, *args: Any) -> Any:
    """Await async dependencies and move synchronous I/O off the event loop."""
    if inspect.iscoroutinefunction(callable_obj):
        return await callable_obj(*args)
    result = await asyncio.to_thread(callable_obj, *args)
    return await result if inspect.isawaitable(result) else result


def _bool_setting(value: Any, *, default: bool) -> bool:
    raw = str(value if value is not None else str(default)).strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    raise ValueError("invalid_boolean")


def parse_alert_tickers(value: Any) -> tuple[str, ...]:
    """Return ordered, deduplicated tickers or reject the entire setting."""
    raw_items = [item.strip().upper() for item in str(value or "").split(",")]
    items = [item for item in raw_items if item]
    if any(not TICKER_PATTERN.fullmatch(item) for item in items):
        raise ValueError("invalid_ticker")
    deduplicated = tuple(dict.fromkeys(items))
    if len(deduplicated) > 20:
        raise ValueError("too_many_tickers")
    return deduplicated


@dataclass(frozen=True)
class HolderAlertConfig:
    enabled: bool = False
    dry_run: bool = True
    tickers: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()

    @property
    def ready(self) -> bool:
        return self.enabled and bool(self.tickers) and not self.errors

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "HolderAlertConfig":
        values = os.environ if env is None else env
        errors: list[str] = []
        try:
            enabled = _bool_setting(values.get("HOLDER_ALERT_ENABLED"), default=False)
        except ValueError:
            enabled = False
            errors.append("invalid_enabled")
        try:
            dry_run = _bool_setting(values.get("HOLDER_ALERT_DRY_RUN"), default=True)
        except ValueError:
            dry_run = True
            errors.append("invalid_dry_run")
        try:
            tickers = parse_alert_tickers(values.get("HOLDER_ALERT_TICKERS", ""))
        except ValueError as exc:
            tickers = ()
            errors.append(str(exc))
        if enabled and not tickers:
            errors.append("tickers_required")
        return cls(enabled=enabled, dry_run=dry_run, tickers=tickers, errors=tuple(errors))


def _parse_date(value: Any) -> date | None:
    raw = str(value or "").strip()
    try:
        if re.fullmatch(r"\d{7}", raw):
            return date(int(raw[:3]) + 1911, int(raw[3:5]), int(raw[5:7]))
        if re.fullmatch(r"\d{8}", raw):
            return date(int(raw[:4]), int(raw[4:6]), int(raw[6:8]))
        return date.fromisoformat(raw[:10])
    except (TypeError, ValueError):
        return None


def _finite_number(value: Any) -> float | None:
    try:
        number = float(str(value).replace(",", "").strip())
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def aggregate_large_holder_history(
    rows: Iterable[Mapping[str, Any]], ticker: str
) -> list[dict[str, Any]]:
    """Aggregate levels 12–15 for each distinct TDCC date."""
    code = ticker.split(".", 1)[0]
    grouped: dict[date, dict[int, float]] = {}
    for raw in rows:
        row = {str(key).lstrip("\ufeff"): value for key, value in raw.items()}
        if str(row.get("證券代號", "")).strip() != code:
            continue
        try:
            level = int(str(row.get("持股分級", "")).strip())
        except ValueError:
            continue
        data_date = _parse_date(row.get("資料日期"))
        ratio = _finite_number(row.get("占集保庫存數比例%"))
        if level not in HOLDER_LEVELS or data_date is None or ratio is None or ratio < 0:
            continue
        grouped.setdefault(data_date, {})[level] = ratio
    history = [
        {"date": data_date.isoformat(), "ratio": round(sum(levels.values()), 4)}
        for data_date, levels in sorted(grouped.items())
        if levels
    ]
    return history


def merge_holder_history(
    current: Sequence[Mapping[str, Any]],
    stored: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Merge persisted weekly observations with the current TDCC response."""
    merged: dict[date, float] = {}
    for item in stored:
        data_date = _parse_date(item.get("holder_date") or item.get("date"))
        ratio = _finite_number(item.get("large_holder_ratio", item.get("ratio")))
        if data_date is not None and ratio is not None and ratio >= 0:
            merged[data_date] = ratio
    for item in current:  # Current official data wins for the same date.
        data_date = _parse_date(item.get("date"))
        ratio = _finite_number(item.get("ratio"))
        if data_date is not None and ratio is not None and ratio >= 0:
            merged[data_date] = ratio
    return [
        {"date": data_date.isoformat(), "ratio": round(ratio, 4)}
        for data_date, ratio in sorted(merged.items())
    ]


def _volume_measure(frame: Any) -> dict[str, Any]:
    if frame is None or getattr(frame, "empty", True) or "Volume" not in frame:
        return {"available": False, "reason": "market_data_unavailable"}
    ordered = frame.sort_index()
    latest_value = _finite_number(ordered["Volume"].iloc[-1])
    if latest_value is None or latest_value <= 0:
        return {"available": False, "reason": "latest_volume_not_positive"}
    previous = [
        number
        for value in ordered["Volume"].iloc[:-1].tolist()
        if (number := _finite_number(value)) is not None and number > 0
    ][-MAX_BASELINE_SESSIONS:]
    if len(previous) < MIN_BASELINE_SESSIONS:
        return {
            "available": False,
            "reason": "volume_history_insufficient",
            "baseline_sessions": len(previous),
        }
    baseline = statistics.median(previous)
    multiple = latest_value / baseline
    index_value = ordered.index[-1]
    market_date = getattr(index_value, "date", lambda: index_value)()
    parsed_market_date = _parse_date(market_date)
    route = dict(getattr(frame, "attrs", {}).get("route") or {})
    return {
        "available": True,
        "market_date": parsed_market_date.isoformat() if parsed_market_date else "",
        "latest_volume": int(latest_value),
        "baseline_median_volume": float(baseline),
        "baseline_sessions": len(previous),
        "volume_multiple": round(multiple, 4),
        "route": {
            "source": route.get("source"),
            "degraded": bool(route.get("degraded", False)),
            "asof": route.get("asof") or (parsed_market_date.isoformat() if parsed_market_date else None),
            "price_basis": route.get("price_basis"),
        },
    }


def evaluate_holder_volume_signal(
    ticker: str,
    tdcc_rows: Iterable[Mapping[str, Any]],
    market_frame: Any,
    *,
    now: datetime | None = None,
    stored_history: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Evaluate one ticker using stable, user-safe reason codes."""
    now = now or datetime.now(TAIPEI)
    if now.tzinfo is None:
        now = now.replace(tzinfo=TAIPEI)
    current_history = aggregate_large_holder_history(tdcc_rows, ticker)
    history = merge_holder_history(current_history, stored_history)
    volume = _volume_measure(market_frame)
    result: dict[str, Any] = {
        "ticker": ticker,
        "eligible": False,
        "reason": "holder_history_insufficient",
        "holder_periods": history[-3:],
        "volume": volume,
    }
    if len(history) < 3:
        return result
    periods = history[-3:]
    ratios = [float(item["ratio"]) for item in periods]
    holder_date = _parse_date(periods[-1]["date"])
    result["holder_date"] = periods[-1]["date"]
    result["holder_increase_pp"] = round(ratios[-1] - ratios[0], 4)
    if holder_date is None or not 0 <= (now.date() - holder_date).days <= HOLDER_MAX_AGE_DAYS:
        result["reason"] = "holder_data_stale"
        return result
    if not volume.get("available"):
        result["reason"] = str(volume.get("reason"))
        return result
    market_date = _parse_date(volume.get("market_date"))
    gap = (market_date - holder_date).days if market_date and holder_date else -1
    result["market_holder_gap_days"] = gap
    if not 0 <= gap <= MARKET_HOLDER_MAX_GAP_DAYS:
        result["reason"] = "market_holder_date_mismatch"
        return result
    if not ratios[0] < ratios[1] < ratios[2]:
        result["reason"] = "holder_ratio_not_strictly_increasing"
        return result
    if result["holder_increase_pp"] + 1e-9 < HOLDER_INCREASE_THRESHOLD_PP:
        result["reason"] = "holder_increase_below_threshold"
        return result
    if float(volume["volume_multiple"]) + 1e-9 < VOLUME_MULTIPLE_THRESHOLD:
        result["reason"] = "volume_multiple_below_threshold"
        return result
    result["eligible"] = True
    result["reason"] = "alert_candidate"
    return result


def event_key_for(ticker: str, holder_date: str) -> str:
    return f"{EVENT_VERSION}:{ticker}:{holder_date}"


def should_startup_catchup(now: datetime | None = None) -> bool:
    current = now or datetime.now(TAIPEI)
    if current.tzinfo is None:
        current = current.replace(tzinfo=TAIPEI)
    return current.astimezone(TAIPEI).time() >= time(20, 30)


class HolderVolumeAlertMonitor:
    """Coordinates DB idempotency, market evaluation, and safe notification."""

    def __init__(
        self,
        config: HolderAlertConfig,
        repository: Any,
        tdcc_loader: Any,
        market_loader: Any,
        notifier: Any,
        *,
        clock: Any = None,
    ) -> None:
        self.config = config
        self.repository = repository
        self.tdcc_loader = tdcc_loader
        self.market_loader = market_loader
        self.notifier = notifier
        self.clock = clock or (lambda: datetime.now(TAIPEI))
        self._run_lock = asyncio.Lock()
        self._owner = f"monitor-{uuid4()}"
        self._status_lock = threading.Lock()
        self._runtime = {
            "state": "disabled" if not config.enabled else "idle",
            "last_trigger": None,
            "last_started_at": None,
            "last_completed_at": None,
            "last_summary": None,
        }

    def status(self) -> dict[str, Any]:
        with self._status_lock:
            runtime = dict(self._runtime)
        return {
            "enabled": self.config.enabled,
            "dry_run": self.config.dry_run,
            "configured_ticker_count": len(self.config.tickers),
            "configuration": "ready" if self.config.ready else ("disabled" if not self.config.enabled else "invalid"),
            "configuration_errors": list(self.config.errors),
            **runtime,
        }

    def health_summary(self) -> dict[str, Any]:
        status = self.status()
        return {
            "enabled": status["enabled"],
            "dry_run": status["dry_run"],
            "configuration": status["configuration"],
            "state": status["state"],
            "last_completed_at": status["last_completed_at"],
        }

    def _set_runtime(self, **updates: Any) -> None:
        with self._status_lock:
            self._runtime.update(updates)

    async def needs_startup_catchup(self) -> bool:
        """Consult persisted state only during startup, never from status APIs."""
        now = self.clock().astimezone(TAIPEI)
        if not self.config.ready or not should_startup_catchup(now):
            return False
        try:
            state = await _invoke(self.repository.get_holder_alert_state, "last_run") or {}
        except Exception:
            return True  # The run itself will fail closed before external I/O.
        return (
            state.get("date") != now.date().isoformat()
            or state.get("status") != "success"
        )

    async def run(self, *, trigger: str = "scheduled") -> dict[str, Any]:
        if not self.config.enabled:
            return {"status": "disabled", "results": []}
        if not self.config.ready:
            self._set_runtime(state="configuration_error")
            return {"status": "configuration_error", "results": []}
        if self._run_lock.locked():
            return {"status": "already_running", "results": []}
        async with self._run_lock:
            now = self.clock().astimezone(TAIPEI)
            owner = self._owner
            started = now.isoformat()
            self._set_runtime(state="running", last_trigger=trigger, last_started_at=started)
            try:
                if not await _invoke(self.repository.acquire_holder_alert_lock, owner, now):
                    summary = {"status": "lock_unavailable", "results": []}
                    self._set_runtime(state="idle", last_summary={"status": summary["status"], "count": 0})
                    return summary
            except Exception:
                summary = {"status": "database_unavailable", "results": []}
                self._set_runtime(state="degraded", last_summary={"status": summary["status"], "count": 0})
                return summary

            try:
                try:
                    rows = await _invoke(self.tdcc_loader)
                except Exception:
                    rows = None

                semaphore = asyncio.Semaphore(4)

                async def process(ticker: str) -> dict[str, Any]:
                    try:
                        async with semaphore:
                            return await self._process_ticker(ticker, rows, now)
                    except Exception:
                        return {"ticker": ticker, "eligible": False, "reason": "ticker_processing_failed"}

                results = list(await asyncio.gather(*(process(ticker) for ticker in self.config.tickers)))
                degraded_reasons = {
                    "tdcc_upstream_unavailable",
                    "market_upstream_unavailable",
                    "ticker_processing_failed",
                    "database_unavailable",
                    "notification_failed",
                }
                counts = {
                    "evaluated": len(results),
                    "would_alert": sum(item.get("action") == "would_alert" for item in results),
                    "sent": sum(item.get("action") == "sent" for item in results),
                    "failed": sum(item.get("reason") in degraded_reasons for item in results),
                }
                summary_status = "success" if counts["failed"] == 0 else "partial"
                public_summary = {"status": summary_status, **counts}
                try:
                    await _invoke(
                        self.repository.set_holder_alert_state,
                        "last_run",
                        {"date": now.date().isoformat(), "trigger": trigger, **public_summary},
                        now,
                    )
                except Exception:
                    summary_status = "partial"
                    public_summary["status"] = summary_status
                    public_summary["state_write"] = "failed"
                completed = self.clock().astimezone(TAIPEI).isoformat()
                self._set_runtime(
                    state="idle" if summary_status == "success" else "degraded",
                    last_completed_at=completed,
                    last_summary=public_summary,
                )
                return {"status": summary_status, "results": results, "summary": public_summary}
            finally:
                try:
                    await _invoke(self.repository.release_holder_alert_lock, owner)
                except Exception:
                    self._set_runtime(state="degraded")

    async def _process_ticker(
        self, ticker: str, tdcc_rows: Sequence[Mapping[str, Any]] | None, now: datetime
    ) -> dict[str, Any]:
        if tdcc_rows is None:
            return {"ticker": ticker, "eligible": False, "reason": "tdcc_upstream_unavailable"}
        current_history = aggregate_large_holder_history(tdcc_rows, ticker)
        if not current_history:
            return {"ticker": ticker, "eligible": False, "reason": "holder_history_insufficient", "holder_periods": []}
        try:
            stored_history = await _invoke(
                self.repository.get_holder_alert_history, ticker, 3
            )
        except Exception:
            return {"ticker": ticker, "eligible": False, "reason": "database_unavailable"}
        try:
            frame = await _invoke(self.market_loader, ticker)
        except Exception:
            return {"ticker": ticker, "eligible": False, "reason": "market_upstream_unavailable"}
        result = evaluate_holder_volume_signal(
            ticker,
            tdcc_rows,
            frame,
            now=now,
            stored_history=stored_history,
        )
        periods = result.get("holder_periods") or []
        if not periods:
            return result
        holder_date = result.get("holder_date") or periods[-1]["date"]
        snapshot = {
            "ticker": ticker,
            "holder_date": holder_date,
            "market_date": result.get("volume", {}).get("market_date"),
            "holder_periods": periods,
            "large_holder_ratio": periods[-1]["ratio"],
            "holder_increase_pp": result.get("holder_increase_pp"),
            "latest_volume": result.get("volume", {}).get("latest_volume"),
            "baseline_median_volume": result.get("volume", {}).get("baseline_median_volume"),
            "baseline_sessions": result.get("volume", {}).get("baseline_sessions"),
            "volume_multiple": result.get("volume", {}).get("volume_multiple"),
            "market_route": result.get("volume", {}).get("route", {}),
            "eligible": result["eligible"],
            "reason": result["reason"],
            "evaluated_at": now.isoformat(),
        }
        try:
            await _invoke(self.repository.upsert_holder_alert_snapshot, snapshot)
        except Exception:
            return {**result, "eligible": False, "reason": "database_unavailable"}
        if not result["eligible"]:
            return result
        event_key = event_key_for(ticker, holder_date)
        result["event_key"] = event_key
        if self.config.dry_run:
            result["action"] = "would_alert"
            return result
        try:
            if await _invoke(
                self.repository.has_recent_sent_holder_alert,
                ticker,
                now - timedelta(days=EVENT_COOLDOWN_DAYS),
            ):
                return {**result, "action": "suppressed", "reason": "cooldown_active"}
            claimed = await _invoke(
                self.repository.claim_holder_alert_event,
                event_key,
                ticker,
                holder_date,
                now,
            )
        except Exception:
            return {**result, "eligible": False, "reason": "database_unavailable"}
        if not claimed:
            return {**result, "action": "suppressed", "reason": "duplicate_or_retry_deferred"}
        sent = False
        try:
            sent = bool(await _invoke(self.notifier.send_holder_volume_alert, result, event_key))
        except Exception:
            sent = False
        try:
            if sent:
                await _invoke(self.repository.mark_holder_alert_sent, event_key, now)
                return {**result, "action": "sent", "reason": "alert_sent"}
            await _invoke(
                self.repository.mark_holder_alert_failed,
                event_key,
                now,
                now + timedelta(hours=FAILED_RETRY_HOURS),
            )
        except Exception:
            return {**result, "eligible": False, "reason": "database_unavailable"}
        return {**result, "action": "failed", "reason": "notification_failed"}

"""Daily Taiwanese stock volume expansion alerts without a database dependency."""
from __future__ import annotations

import asyncio
import math
import os
from dataclasses import dataclass
from datetime import datetime, time
from typing import Any, Mapping

from holder_volume_alerts import TAIPEI, _bool_setting, _invoke, _volume_measure, parse_alert_tickers


@dataclass(frozen=True)
class VolumeAlertConfig:
    enabled: bool = False
    tickers: tuple[str, ...] = ()
    multiplier: float = 1.5
    errors: tuple[str, ...] = ()

    @property
    def ready(self) -> bool:
        return self.enabled and bool(self.tickers) and not self.errors

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "VolumeAlertConfig":
        values = os.environ if env is None else env
        errors: list[str] = []
        try:
            enabled = _bool_setting(values.get("VOLUME_ALERT_ENABLED"), default=False)
        except ValueError:
            enabled = False
            errors.append("invalid_enabled")
        try:
            tickers = parse_alert_tickers(values.get("VOLUME_ALERT_TICKERS", ""))
        except ValueError as exc:
            tickers = ()
            errors.append(str(exc))
        try:
            multiplier = float(values.get("VOLUME_ALERT_MULTIPLIER", "1.5"))
            if not math.isfinite(multiplier) or multiplier <= 1:
                raise ValueError
        except (TypeError, ValueError):
            multiplier = 1.5
            errors.append("invalid_multiplier")
        if enabled and not tickers:
            errors.append("tickers_required")
        if enabled and not str(values.get("DISCORD_WEBHOOK_URL", "")).strip():
            errors.append("discord_webhook_required")
        return cls(enabled, tickers, multiplier, tuple(errors))


def should_startup_catchup(now: datetime | None = None) -> bool:
    current = now or datetime.now(TAIPEI)
    if current.tzinfo is None:
        current = current.replace(tzinfo=TAIPEI)
    local_time = current.astimezone(TAIPEI).time()
    return time(20, 30) <= local_time < time(21, 30)


class VolumeAlertMonitor:
    def __init__(self, config: VolumeAlertConfig, market_loader: Any, notifier: Any, *, clock: Any = None) -> None:
        self.config = config
        self.market_loader = market_loader
        self.notifier = notifier
        self.clock = clock or (lambda: datetime.now(TAIPEI))
        self._run_lock = asyncio.Lock()
        self._sent: set[tuple[str, str]] = set()
        self._last_summary: dict[str, Any] | None = None
        self._last_completed_at: str | None = None

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.config.enabled,
            "configuration": "ready" if self.config.ready else ("invalid" if self.config.errors else "disabled"),
            "configuration_errors": list(self.config.errors),
            "configured_ticker_count": len(self.config.tickers),
            "multiplier": self.config.multiplier,
            "running": self._run_lock.locked(),
            "last_completed_at": self._last_completed_at,
            "last_summary": self._last_summary,
        }

    async def run(self, *, trigger: str = "scheduled") -> dict[str, Any]:
        if not self.config.ready:
            return {"status": "configuration_error" if self.config.enabled else "disabled", "results": []}
        if self._run_lock.locked():
            return {"status": "already_running", "results": []}
        async with self._run_lock:
            current = self.clock()
            if current.tzinfo is None:
                current = current.replace(tzinfo=TAIPEI)
            today = current.astimezone(TAIPEI).date().isoformat()
            results = []
            for ticker in self.config.tickers:
                try:
                    frame = await _invoke(self.market_loader, ticker)
                    volume = _volume_measure(frame)
                    if not volume.get("available"):
                        result = {"ticker": ticker, "reason": volume.get("reason", "market_data_unavailable")}
                    elif volume.get("market_date") != today:
                        result = {"ticker": ticker, "reason": "market_data_not_today"}
                    elif volume["latest_volume"] / volume["baseline_median_volume"] < self.config.multiplier:
                        result = {"ticker": ticker, "reason": "below_threshold"}
                    elif (ticker, today) in self._sent:
                        result = {"ticker": ticker, "reason": "already_sent"}
                    else:
                        sent = bool(await _invoke(self.notifier.send_volume_alert, ticker, volume))
                        if sent:
                            self._sent.add((ticker, today))
                        result = {"ticker": ticker, "reason": "sent" if sent else "notification_failed"}
                except Exception:
                    result = {"ticker": ticker, "reason": "ticker_processing_failed"}
                results.append(result)
            reasons: dict[str, int] = {}
            for item in results:
                reasons[item["reason"]] = reasons.get(item["reason"], 0) + 1
            summary = {
                "status": "success" if not any(item["reason"] in {"ticker_processing_failed", "notification_failed"} for item in results) else "partial",
                "trigger": trigger,
                "evaluated": len(results),
                "sent": sum(item["reason"] == "sent" for item in results),
                "reasons": reasons,
            }
            self._last_summary = summary
            completed = self.clock()
            if completed.tzinfo is None:
                completed = completed.replace(tzinfo=TAIPEI)
            self._last_completed_at = completed.astimezone(TAIPEI).isoformat()
            return {**summary, "results": results}

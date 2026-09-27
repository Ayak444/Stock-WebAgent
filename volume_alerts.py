"""Per-account Taiwanese stock volume expansion alerts."""
from __future__ import annotations

import asyncio
import math
import os
from dataclasses import dataclass
from datetime import datetime, time
from typing import Any, Mapping

from holder_volume_alerts import TAIPEI, _bool_setting, _invoke, _volume_measure, parse_alert_tickers
from account_alert_security import decrypt_webhook
from notifier import DiscordNotifier
from cryptography.fernet import Fernet


def should_startup_catchup(now: datetime | None = None) -> bool:
    current = now or datetime.now(TAIPEI)
    if current.tzinfo is None:
        current = current.replace(tzinfo=TAIPEI)
    local_time = current.astimezone(TAIPEI).time()
    return time(20, 30) <= local_time < time(21, 30)


@dataclass(frozen=True)
class AccountVolumeAlertConfig:
    enabled: bool = False
    multiplier: float = 1.5
    errors: tuple[str, ...] = ()

    @property
    def ready(self) -> bool:
        return self.enabled and not self.errors

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "AccountVolumeAlertConfig":
        values = os.environ if env is None else env
        errors: list[str] = []
        try:
            enabled = _bool_setting(values.get("VOLUME_ALERT_ENABLED"), default=False)
        except ValueError:
            enabled = False
            errors.append("invalid_enabled")
        try:
            multiplier = float(values.get("VOLUME_ALERT_MULTIPLIER", "1.5"))
            if not math.isfinite(multiplier) or multiplier <= 1:
                raise ValueError
        except (TypeError, ValueError):
            multiplier = 1.5
            errors.append("invalid_multiplier")
        if enabled:
            try:
                Fernet(str(values.get("ALERT_WEBHOOK_ENCRYPTION_KEY", "")).encode("ascii"))
            except (TypeError, ValueError, UnicodeError):
                errors.append("encryption_key_required")
        return cls(enabled, multiplier, tuple(errors))


class AccountVolumeAlertMonitor:
    """Shared market reads with isolated account delivery and database deduplication."""

    def __init__(self, config: AccountVolumeAlertConfig, store: Any, market_loader: Any,
                 notifier_factory: Any = DiscordNotifier, *, clock: Any = None) -> None:
        self.config = config
        self.store = store
        self.market_loader = market_loader
        self.notifier_factory = notifier_factory
        self.clock = clock or (lambda: datetime.now(TAIPEI))
        self._run_lock = asyncio.Lock()
        self._last_summary: dict[str, Any] | None = None
        self._last_completed_at: str | None = None

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.config.enabled,
            "configuration": "configured" if self.config.ready else ("invalid" if self.config.errors else "disabled"),
            "configuration_errors": list(self.config.errors),
            "multiplier": self.config.multiplier,
            "running": self._run_lock.locked(),
            "last_completed_at": self._last_completed_at,
            "last_summary": self._last_summary,
        }

    async def run(self, *, trigger: str = "scheduled") -> dict[str, Any]:
        if not self.config.ready:
            return {"status": "configuration_error" if self.config.enabled else "disabled"}
        if self._run_lock.locked():
            return {"status": "already_running"}
        async with self._run_lock:
            now = self.clock()
            if now.tzinfo is None:
                now = now.replace(tzinfo=TAIPEI)
            today = now.astimezone(TAIPEI).date().isoformat()
            try:
                accounts = await _invoke(self.store.list_account_volume_settings)
            except Exception:
                return {"status": "store_unavailable"}

            market: dict[str, dict[str, Any]] = {}
            counts: dict[str, int] = {}
            store_failed = False
            for account in accounts:
                if store_failed:
                    break
                try:
                    webhook = decrypt_webhook(account.get("webhook_ciphertext") or "")
                    user_id = account["user_id"]
                    tickers = parse_alert_tickers(",".join(account.get("tickers") or []))
                except Exception:
                    counts["invalid_account_settings"] = counts.get("invalid_account_settings", 0) + 1
                    continue
                for ticker in tickers:
                    try:
                        if ticker not in market:
                            frame = await _invoke(self.market_loader, ticker)
                            market[ticker] = _volume_measure(frame)
                        measure = market[ticker]
                        if not measure.get("available"):
                            reason = "market_data_unavailable"
                        elif measure.get("market_date") != today:
                            reason = "market_data_not_today"
                        elif measure["latest_volume"] / measure["baseline_median_volume"] < self.config.multiplier:
                            reason = "below_threshold"
                        elif not await _invoke(self.store.claim_account_volume_event, user_id, ticker, today, now):
                            reason = "already_claimed_or_sent"
                        else:
                            # A dedicated notifier is created from this account's decrypted URL.
                            sent = bool(await _invoke(
                                self.notifier_factory(webhook).send_volume_alert, ticker, measure
                            ))
                            await _invoke(self.store.finish_account_volume_event,
                                          user_id, ticker, today, "sent" if sent else "failed", self.clock())
                            reason = "sent" if sent else "notification_failed"
                    except RuntimeError as exc:
                        if str(exc) == "account_alert_store_unavailable":
                            store_failed = True
                            reason = "store_unavailable"
                        else:
                            reason = "ticker_processing_failed"
                    except Exception:
                        reason = "ticker_processing_failed"
                    counts[reason] = counts.get(reason, 0) + 1
                    if store_failed:
                        break
            summary = {
                "status": "store_unavailable" if store_failed else (
                    "partial" if counts.get("notification_failed") or counts.get("ticker_processing_failed") else "success"
                ),
                "trigger": trigger,
                "evaluated": sum(counts.values()),
                "sent": counts.get("sent", 0),
                "reasons": counts,
            }
            self._last_summary = summary
            self._last_completed_at = self.clock().astimezone(TAIPEI).isoformat()
            return summary

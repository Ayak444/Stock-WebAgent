"""Server-owned sessions and private Discord webhook validation/encryption."""
from __future__ import annotations

import os
from urllib.parse import urlsplit

from cryptography.fernet import Fernet, InvalidToken
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

SESSION_COOKIE = "stock_session"
SESSION_AGE_SECONDS = 7 * 24 * 60 * 60
DISCORD_HOSTS = frozenset({"discord.com", "discordapp.com"})


class WebhookEncryptionError(RuntimeError):
    def __init__(self, category):
        self.category = category
        super().__init__(category)


def _session_serializer() -> URLSafeTimedSerializer:
    secret = os.environ.get("AUTH_SESSION_SECRET", "")
    if len(secret) < 32:
        raise RuntimeError("auth_session_not_configured")
    return URLSafeTimedSerializer(secret, salt="stock-webagent-session-v1")


def issue_session(user_id: str) -> str:
    return _session_serializer().dumps({"uid": user_id})


def read_session(cookie: str | None) -> str | None:
    if not cookie:
        return None
    try:
        payload = _session_serializer().loads(cookie, max_age=SESSION_AGE_SECONDS)
        return payload.get("uid") if isinstance(payload, dict) else None
    except (BadSignature, SignatureExpired):
        return None


def validate_discord_webhook(url: str) -> str:
    if (not isinstance(url, str) or len(url) > 2048
            or any(ord(ch) <= 32 or ord(ch) == 127 for ch in url)):
        raise ValueError("invalid_discord_webhook")
    try:
        parsed = urlsplit(url)
        segments = parsed.path.split("/")
        valid = (parsed.scheme == "https" and parsed.hostname in DISCORD_HOSTS
                 and parsed.port is None and not parsed.username and not parsed.password
                 and not parsed.query and not parsed.fragment
                 and len(segments) == 5 and segments[:3] == ["", "api", "webhooks"]
                 and segments[3].isdigit() and bool(segments[4])
                 and all(ch.isalnum() or ch in "_-" for ch in segments[4]))
    except ValueError:
        valid = False
    if not valid:
        raise ValueError("invalid_discord_webhook")
    return url


def _fernet() -> Fernet:
    key = os.environ.get("ALERT_WEBHOOK_ENCRYPTION_KEY", "")
    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, TypeError, UnicodeError):
        raise WebhookEncryptionError("encryption_not_configured") from None


def encrypt_webhook(url: str) -> str:
    return _fernet().encrypt(validate_discord_webhook(url).encode("utf-8")).decode("ascii")


def decrypt_webhook(ciphertext: str) -> str:
    try:
        return validate_discord_webhook(_fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8"))
    except (InvalidToken, UnicodeError, ValueError) as exc:
        raise WebhookEncryptionError("encryption_unavailable") from None

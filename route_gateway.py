"""Process-local AI isolation and bounded, credential-free routing audit."""
import hashlib
import logging
import os
import threading
import time
from collections import Counter
import requests

logger = logging.getLogger('routing')
counts = Counter()
DEFAULT_GROQ_MODEL = 'openai/gpt-oss-120b'

_AI_ERROR_MESSAGES = {
    'ai_not_configured': 'AI 尚未設定，請聯絡管理員',
    'ai_busy': 'AI 忙碌，請稍後再試',
    'ai_circuit_open': 'AI 暫停呼叫，請稍後再試或聯絡管理員',
    'ai_auth_failed': 'AI 驗證失敗，請聯絡管理員',
    'ai_rate_limited': 'Groq 額度或速率受限，請稍後重試',
    'ai_request_rejected': 'AI 請求未被接受，請聯絡管理員',
    'ai_timeout': 'AI 回應逾時，請稍後再試',
    'ai_network_error': 'AI 連線失敗，請稍後再試',
    'ai_provider_error': 'AI 供應商服務暫時異常，請稍後再試',
    'ai_malformed_response': 'AI 回傳格式異常，請稍後再試',
    'ai_unavailable': 'AI 服務暫時無法使用，請稍後再試',
}

def audit(task, source, outcome):
    counts[(task, source, outcome)] += 1
    logger.info('route task=%s source=%s outcome=%s', task, source, outcome)

class AIUnavailable(RuntimeError):
    """An allowlisted error code and static, credential-free public message."""

    def __init__(self, code='ai_unavailable'):
        self.code = code if code in _AI_ERROR_MESSAGES else 'ai_unavailable'
        self.message = _AI_ERROR_MESSAGES[self.code]
        super().__init__(self.message)

class AIGateway:
    def __init__(self):
        self.lock = threading.Lock()
        self.fingerprint = None
        self.blocked_until = 0
        self.failures = 0

    def _failed(self, code):
        self.failures += 1
        if self.failures >= 3:
            self.blocked_until = time.monotonic() + 60
        audit('ai', 'groq', 'failed')
        raise AIUnavailable(code) from None

    def complete(self, payload):
        key = os.getenv('GROQ_API_KEY') or os.getenv('MAIAGENT_API_KEY', '')
        model = os.getenv('GROQ_MODEL', DEFAULT_GROQ_MODEL).strip() or DEFAULT_GROQ_MODEL
        if not key:
            raise AIUnavailable('ai_not_configured')
        fingerprint = hashlib.sha256(key.encode()).digest()
        # Serialize calls so concurrent requests cannot bypass an authentication failure.
        if not self.lock.acquire(timeout=2):
            raise AIUnavailable('ai_busy')
        try:
            if fingerprint != self.fingerprint:
                self.fingerprint, self.blocked_until, self.failures = fingerprint, 0, 0
            if time.monotonic() < self.blocked_until:
                audit('ai', 'groq', 'circuit_open')
                raise AIUnavailable('ai_circuit_open')
            try:
                response = requests.post(
                    'https://api.groq.com/openai/v1/chat/completions',
                    headers={'Authorization': f'Bearer {key}'},
                    json={**payload, 'model': model, 'max_tokens': 1500}, timeout=(5, 30))
                if response.status_code in (401, 403):
                    self.blocked_until = float('inf')
                    raise AIUnavailable('ai_auth_failed')
                if response.status_code == 429:
                    try:
                        delay = min(300, max(30, float(response.headers.get('Retry-After', 60))))
                    except (TypeError, ValueError):
                        delay = 60
                    self.blocked_until = time.monotonic() + delay
                    raise AIUnavailable('ai_rate_limited')
                if response.status_code in (400, 404, 422):
                    audit('ai', 'groq', f'rejected_{response.status_code}')
                    raise AIUnavailable('ai_request_rejected')
                response.raise_for_status()
                content = response.json()['choices'][0]['message']['content']
                if not isinstance(content, str) or not content.strip():
                    raise ValueError('empty content')
                self.failures = 0
                audit('ai', 'groq', 'success')
                return content
            except AIUnavailable:
                audit('ai', 'groq', 'unavailable')
                raise
            except requests.Timeout:
                self._failed('ai_timeout')
            except requests.HTTPError as exc:
                status = getattr(exc.response, 'status_code', None)
                self._failed('ai_provider_error' if isinstance(status, int) and
                             500 <= status <= 599 else 'ai_request_rejected')
            except (ValueError, KeyError, IndexError, TypeError):
                self._failed('ai_malformed_response')
            except requests.RequestException:
                self._failed('ai_network_error')
        finally:
            self.lock.release()

ai_gateway = AIGateway()

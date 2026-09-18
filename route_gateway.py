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

def audit(task, source, outcome):
    counts[(task, source, outcome)] += 1
    logger.info('route task=%s source=%s outcome=%s', task, source, outcome)

class AIUnavailable(RuntimeError):
    pass

class AIGateway:
    def __init__(self):
        self.lock = threading.Lock()
        self.fingerprint = None
        self.blocked_until = 0
        self.failures = 0

    def complete(self, payload):
        key = os.getenv('GROQ_API_KEY') or os.getenv('MAIAGENT_API_KEY', '')
        if not key:
            raise AIUnavailable('尚未設定 GROQ_API_KEY')
        fingerprint = hashlib.sha256(key.encode()).digest()
        # Serialize calls so concurrent requests cannot bypass an authentication failure.
        if not self.lock.acquire(timeout=2):
            raise AIUnavailable('AI 忙碌，請稍後再試')
        try:
            if fingerprint != self.fingerprint:
                self.fingerprint, self.blocked_until, self.failures = fingerprint, 0, 0
            if time.monotonic() < self.blocked_until:
                audit('ai', 'groq', 'circuit_open')
                raise AIUnavailable('AI 暫停呼叫，請確認 API Key／額度或稍後再試')
            try:
                response = requests.post(
                    'https://api.groq.com/openai/v1/chat/completions',
                    headers={'Authorization': f'Bearer {key}'},
                    json={**payload, 'max_tokens': 1500}, timeout=(5, 30))
                if response.status_code in (401, 403):
                    self.blocked_until = float('inf')
                    raise AIUnavailable('Groq 驗證失敗，請更新部署環境的 GROQ_API_KEY')
                if response.status_code == 429:
                    try:
                        delay = min(300, max(30, float(response.headers.get('Retry-After', 60))))
                    except (TypeError, ValueError):
                        delay = 60
                    self.blocked_until = time.monotonic() + delay
                    raise AIUnavailable('Groq 額度或速率限制，稍後重試')
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
            except (requests.RequestException, ValueError, KeyError, IndexError, TypeError):
                self.failures += 1
                if self.failures >= 3:
                    self.blocked_until = time.monotonic() + 60
                audit('ai', 'groq', 'failed')
                raise AIUnavailable('AI 連線或回傳格式異常，請稍後再試') from None
        finally:
            self.lock.release()

ai_gateway = AIGateway()

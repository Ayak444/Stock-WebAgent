import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

import main
from account_alert_security import decrypt_webhook, encrypt_webhook
from holder_volume_alerts import TAIPEI
from volume_alerts import AccountVolumeAlertConfig, AccountVolumeAlertMonitor, should_startup_catchup

NOW = datetime(2026, 9, 21, 20, 30, tzinfo=TAIPEI)
WEBHOOK_A = "https://discord.com/api/webhooks/123456/AccountA_token"
WEBHOOK_B = "https://discord.com/api/webhooks/789012/AccountB_token"
A = {"id": "00000000-0000-0000-0000-000000000001", "name": "A"}
B = {"id": "00000000-0000-0000-0000-000000000002", "name": "B"}


def frame(date="2026-09-21", latest=150, previous=None):
    previous = [100] * 20 if previous is None else previous
    data = pd.DataFrame({"Volume": previous + [latest]},
                        index=pd.bdate_range(end=date, periods=len(previous) + 1))
    data.attrs["route"] = {"source": "yahoo"}
    return data


class Store:
    def __init__(self):
        self.users = {A["id"]: A, B["id"]: B}
        self.settings = {}
        self.events = {}
        self.offline = False

    def check(self):
        if self.offline:
            raise RuntimeError("account_alert_store_unavailable")

    def verify_user(self, email, password):
        self.check()
        return A if email == "a@example.test" else B if email == "b@example.test" else None

    def get_public_user(self, user_id):
        self.check()
        return self.users.get(user_id)

    def get_account_volume_settings(self, user_id):
        self.check()
        return self.settings.get(user_id, {"tickers": [], "webhook_ciphertext": None})

    def save_account_volume_settings(self, user_id, settings):
        self.check()
        self.settings[user_id] = dict(settings)

    def list_account_volume_settings(self):
        self.check()
        return [{"user_id": uid, **s} for uid, s in self.settings.items()
                if s.get("webhook_ciphertext")]

    def claim_account_volume_event(self, uid, ticker, date, now):
        self.check()
        key = (uid, ticker, date)
        if self.events.get(key) in {"claimed", "sent"}:
            return False
        self.events[key] = "claimed"
        return True

    def finish_account_volume_event(self, uid, ticker, date, status, now):
        self.check()
        self.events[(uid, ticker, date)] = status


class ConfigTests(unittest.TestCase):
    def test_global_tickers_and_webhook_are_ignored(self):
        config = AccountVolumeAlertConfig.from_env({
            "VOLUME_ALERT_ENABLED": "true",
            "ALERT_WEBHOOK_ENCRYPTION_KEY": Fernet.generate_key().decode(),
            "VOLUME_ALERT_TICKERS": "invalid",
            "DISCORD_WEBHOOK_URL": "invalid",
        })
        self.assertTrue(config.ready)
        self.assertEqual(config.multiplier, 1.5)
        self.assertFalse(AccountVolumeAlertConfig.from_env({}).ready)
        self.assertTrue(should_startup_catchup(NOW))
        self.assertFalse(should_startup_catchup(NOW.replace(hour=20, minute=29)))


class EndpointTests(unittest.TestCase):
    def setUp(self):
        self.store = Store()
        self.secrets = patch.dict("os.environ", {
            "AUTH_SESSION_SECRET": "test-session-secret-" * 3,
            "ALERT_WEBHOOK_ENCRYPTION_KEY": Fernet.generate_key().decode(),
        })
        self.secrets.start()
        self.db_patch = patch.object(main, "db", self.store)
        self.db_patch.start()
        self.addCleanup(self.db_patch.stop)
        self.addCleanup(self.secrets.stop)
        self.a = TestClient(main.app, base_url="https://testserver")
        self.b = TestClient(main.app, base_url="https://testserver")

    def login(self, client, email):
        response = client.post("/auth/login",
                               json={"email": email, "password": "test"},
                               headers={"Origin": "https://testserver"})
        self.assertEqual(response.status_code, 200)
        for flag in ("httponly", "secure", "samesite=lax"):
            self.assertIn(flag, response.headers["set-cookie"].lower())

    def put(self, client, payload, origin="https://testserver"):
        return client.put("/api/account/volume-alerts", json=payload,
                          headers={"Origin": origin})

    def test_anonymous_session_origin_and_logout(self):
        self.assertEqual(self.a.get("/auth/me").status_code, 401)
        self.assertEqual(self.a.get("/api/account/volume-alerts").status_code, 401)
        self.assertEqual(self.put(self.a, {"tickers": []}).status_code, 401)
        self.login(self.a, "a@example.test")
        self.assertEqual(self.a.get("/auth/me").json()["user"]["id"], A["id"])
        self.assertEqual(self.put(self.a, {"tickers": []}, "https://evil.invalid").status_code, 403)
        self.assertEqual(self.a.post("/auth/logout",
                                     headers={"Origin": "https://testserver"}).status_code, 200)
        self.assertEqual(self.a.get("/auth/me").status_code, 401)

    def test_isolation_normalization_persistence_and_redaction(self):
        self.login(self.a, "a@example.test")
        self.login(self.b, "b@example.test")
        response = self.put(self.a, {"tickers": ["2330.tw", "6488.TWO", "2330.TW"],
                                     "webhook": WEBHOOK_A})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"tickers": ["2330.TW", "6488.TWO"],
                                           "webhook_configured": True})
        self.assertNotIn(WEBHOOK_A, response.text)
        self.assertNotIn(WEBHOOK_A, self.a.get("/api/account/volume-alerts").text)
        self.assertEqual(self.b.get("/api/account/volume-alerts").json(),
                         {"tickers": [], "webhook_configured": False})
        ciphertext = self.store.settings[A["id"]]["webhook_ciphertext"]
        self.assertNotEqual(ciphertext, WEBHOOK_A)
        self.assertEqual(decrypt_webhook(ciphertext), WEBHOOK_A)
        fresh = TestClient(main.app, base_url="https://testserver")
        fresh.cookies.update(self.a.cookies)
        self.assertEqual(fresh.get("/api/account/volume-alerts").json()["tickers"],
                         ["2330.TW", "6488.TWO"])
        self.assertEqual(self.put(self.a, {"tickers": ["2330.TW"],
                                           "remove_webhook": True}).json()["webhook_configured"], False)

    def test_invalid_webhook_and_unavailable_db(self):
        self.login(self.a, "a@example.test")
        for webhook in ("http://discord.com/api/webhooks/123/secret",
                        "https://evil.invalid/api/webhooks/123/secret",
                        "https://discord.com/api/webhooks/123/secret?x=1"):
            response = self.put(self.a, {"tickers": [], "webhook": webhook})
            self.assertEqual(response.status_code, 422)
            self.assertNotIn(webhook, response.text)
        self.store.offline = True
        self.assertEqual(self.a.get("/api/account/volume-alerts").status_code, 503)
        self.assertEqual(self.put(self.a, {"tickers": []}).status_code, 503)
        self.assertEqual(self.a.get("/auth/me").status_code, 503)


class MonitorTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        key = Fernet.generate_key().decode()
        self.secrets = patch.dict("os.environ", {"ALERT_WEBHOOK_ENCRYPTION_KEY": key})
        self.secrets.start()
        self.addCleanup(self.secrets.stop)
        self.store = Store()
        for user, webhook in ((A, WEBHOOK_A), (B, WEBHOOK_B)):
            self.store.settings[user["id"]] = {
                "tickers": ["2330.TW"], "webhook_ciphertext": encrypt_webhook(webhook),
            }
        self.sent = []
        self.market_reads = []

    def notifier(self, fail_url=None):
        def make(url):
            sender = Mock()
            sender.send_volume_alert.side_effect = lambda ticker, data: (
                self.sent.append((url, ticker)) or url != fail_url)
            return sender
        return make

    def market(self, ticker):
        self.market_reads.append(ticker)
        return frame()

    async def test_per_account_destination_shared_market_durable_dedupe(self):
        config = AccountVolumeAlertConfig(enabled=True)
        first = await AccountVolumeAlertMonitor(config, self.store, self.market,
                                                self.notifier(), clock=lambda: NOW).run()
        second = await AccountVolumeAlertMonitor(config, self.store, self.market,
                                                 self.notifier(), clock=lambda: NOW).run()
        self.assertEqual(first["sent"], 2)
        self.assertEqual(second["reasons"], {"already_claimed_or_sent": 2})
        self.assertEqual(self.market_reads, ["2330.TW", "2330.TW"])
        self.assertEqual({url for url, _ in self.sent}, {WEBHOOK_A, WEBHOOK_B})
        self.assertNotIn(WEBHOOK_A, str(first))

    async def test_failed_send_retries_only_failed_account(self):
        config = AccountVolumeAlertConfig(enabled=True)
        first = await AccountVolumeAlertMonitor(config, self.store, self.market,
                                                self.notifier(WEBHOOK_A), clock=lambda: NOW).run()
        second = await AccountVolumeAlertMonitor(config, self.store, self.market,
                                                 self.notifier(), clock=lambda: NOW).run()
        self.assertEqual((first["sent"], second["sent"]), (1, 1))
        self.assertEqual(second["reasons"].get("already_claimed_or_sent"), 1)
        self.assertEqual([url for url, _ in self.sent], [WEBHOOK_A, WEBHOOK_B, WEBHOOK_A])

    async def test_stale_short_low_volume_and_store_failure(self):
        for data in (frame(date="2026-09-18"), frame(previous=[100] * 14),
                     frame(latest=149)):
            monitor = AccountVolumeAlertMonitor(AccountVolumeAlertConfig(enabled=True),
                                                self.store, lambda _: data,
                                                self.notifier(), clock=lambda: NOW)
            self.assertEqual((await monitor.run())["sent"], 0)
        self.assertEqual(self.sent, [])
        self.store.offline = True
        result = await AccountVolumeAlertMonitor(AccountVolumeAlertConfig(enabled=True),
                                                 self.store, self.market,
                                                 self.notifier(), clock=lambda: NOW).run()
        self.assertEqual(result["status"], "store_unavailable")


class BrowserAndMigrationTests(unittest.TestCase):
    def test_browser_uses_server_session_and_handles_logout_failure(self):
        html = Path("static/index.html").read_text(encoding="utf-8")
        self.assertIn("apiCall('/auth/me')", html)
        self.assertNotIn("localStorage.setItem('trade_user'", html)
        self.assertNotIn("localStorage.setItem('volume-webhook'", html)
        logout = html.split("async function logout()", 1)[1].split("\n}", 1)[0]
        self.assertRegex(logout, r"const\s+\w+\s*=\s*await apiCall\('/auth/logout', 'POST'\)")
        self.assertLess(logout.index("status !== 'success'"), logout.index("currentUser = null"))

    def test_migration_has_account_event_key_and_failed_retry(self):
        sql = Path("migrations/003_account_volume_alerts.sql").read_text(encoding="utf-8")
        self.assertIn("PRIMARY KEY (user_id, ticker, market_date)", sql)
        self.assertIn("account_volume_alert_events.status = 'failed'", sql)


if __name__ == "__main__":
    unittest.main()

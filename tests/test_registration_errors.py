"""Offline signup regression tests using a small in-memory Supabase stand-in."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

import main
from database import Database, _verify_password


class ProviderError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class AccountQuery:
    def __init__(self, store):
        self.store = store
        self.action = None
        self.payload = None
        self.email = None

    def insert(self, payload):
        self.action = "insert"
        self.payload = payload
        return self

    def select(self, *_args):
        self.action = "select"
        return self

    def eq(self, field, value):
        if field == "email":
            self.email = value
        return self

    def limit(self, _count):
        return self

    def execute(self):
        if self.action == "insert":
            if self.store.failure:
                raise self.store.failure
            if self.payload["email"] in self.store.users:
                raise ProviderError("23505", "duplicate email / provider detail")
            user = {"id": "user-1", **self.payload}
            self.store.users[user["email"]] = user
            return SimpleNamespace(data=[user])
        return SimpleNamespace(data=[self.store.users[self.email]]
                               if self.email in self.store.users else [])


class AccountStore:
    def __init__(self):
        self.users = {}
        self.failure = None

    def table(self, name):
        assert name == "users"
        return AccountQuery(self)


class RegistrationErrorTests(unittest.TestCase):
    def setUp(self):
        self.store = AccountStore()
        self.database = Database.__new__(Database)
        self.database.supabase = self.store
        self.db_patch = patch.object(main, "db", self.database)
        self.db_patch.start()
        self.addCleanup(self.db_patch.stop)
        self.env_patch = patch.dict("os.environ", {
            "AUTH_SESSION_SECRET": "test-only-session-secret-" * 3,
        })
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)
        self.client = TestClient(main.app, base_url="https://testserver")

    def signup(self, password="valid-password", name="Person"):
        return self.client.post("/auth/signup", json={
            "email": " Person@Example.test ",
            "password": password,
            "name": name,
        })

    def test_signup_hashes_password_can_login_and_rejects_duplicate(self):
        signup = self.signup()
        self.assertEqual(signup.status_code, 200)
        self.assertEqual(signup.json()["user"]["email"], "person@example.test")
        self.assertNotIn("password_hash", signup.json()["user"])
        stored = self.store.users["person@example.test"]
        self.assertNotEqual(stored["password_hash"], "valid-password")
        self.assertEqual(_verify_password("valid-password", stored["password_hash"]),
                         (True, False))

        login = self.client.post("/auth/login", json={
            "email": "Person@Example.test", "password": "valid-password",
        }, headers={"Origin": "https://testserver"})
        self.assertEqual(login.status_code, 200)
        self.assertNotIn("password_hash", login.json()["user"])
        self.assertEqual(self.signup().status_code, 409)
        self.assertEqual(len(self.store.users), 1)

    def test_short_password_and_missing_database_are_actionable(self):
        invalid = self.signup(password="short")
        self.assertEqual(invalid.status_code, 400)
        self.assertIn("8", invalid.json()["detail"])
        self.database.supabase = None
        unavailable = self.signup()
        self.assertEqual(unavailable.status_code, 503)
        self.assertNotIn("not_configured", unavailable.text)

    def test_name_is_required_before_write_and_valid_name_is_trimmed(self):
        for payload in (
            {"email": "person@example.test", "password": "valid-password"},
            {"email": "person@example.test", "password": "valid-password",
             "name": "   "},
        ):
            with self.subTest(payload=payload):
                response = self.client.post("/auth/signup", json=payload)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(self.store.users, {})
        response = self.signup(name="  Person  ")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.store.users["person@example.test"]["name"], "Person")

    def test_provider_failure_redacts_response_and_logs(self):
        marker = "private-provider-detail-test-only"
        self.store.failure = ProviderError("42P01", marker)
        with self.assertLogs("database", level="ERROR") as database_logs, \
             self.assertLogs("main", level="ERROR") as main_logs:
            response = self.signup()
        self.assertEqual(response.status_code, 503)
        self.assertNotIn(marker, response.text)
        self.assertNotIn(marker, " ".join(database_logs.output + main_logs.output))
        self.assertIn("42P01", " ".join(database_logs.output))


if __name__ == "__main__":
    unittest.main()

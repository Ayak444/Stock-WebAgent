"""Offline notification-store and AI error-contract regressions."""

import ast
import asyncio
import logging
import os
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import requests
from fastapi import HTTPException

from database import Database
from route_gateway import AIGateway, AIUnavailable, DEFAULT_GROQ_MODEL


MARKER = "private-provider-and-settings-test-only-marker"
REQUIRED_COLUMNS = {"user_id", "tickers", "webhook_ciphertext", "updated_at"}


def main_definitions(names, environment):
    """Compile selected real handlers without main's import-time side effects."""
    tree = ast.parse(Path("main.py").read_text(encoding="utf-8"))
    nodes = [node for node in tree.body if getattr(node, "name", None) in names]
    for node in nodes:
        node.decorator_list = []
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            node.args.defaults = [ast.Constant(None) for _ in node.args.defaults]
    module = ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[]))
    exec(compile(module, "main.py", "exec"), environment)
    return environment


class StoreQuery:
    def __init__(self, columns=REQUIRED_COLUMNS, failure=None, data=None):
        self.columns = columns
        self.failure = failure
        self.data = data or []
        self.projection = None
        self.limit_count = None
        self.filters = []
        self.payload = None

    def table(self, name):
        if name != "account_volume_alert_settings":
            raise AssertionError("unexpected table")
        return self

    def select(self, projection):
        self.projection = projection
        if set(projection.split(",")) - self.columns:
            error = type("APIError", (Exception,), {})(MARKER)
            error.code = "42703"
            raise error
        return self

    def limit(self, count):
        self.limit_count = count
        return self

    def eq(self, field, value):
        self.filters.append((field, value))
        return self

    def upsert(self, payload, on_conflict):
        self.payload = payload
        self.on_conflict = on_conflict
        return self

    def execute(self):
        if self.failure:
            raise self.failure
        return SimpleNamespace(data=[] if self.limit_count == 0 else self.data)


def database_for(query):
    database = Database.__new__(Database)
    database.supabase = query
    return database


class NotificationStoreDiagnosticsTests(unittest.TestCase):
    def test_probe_requires_all_columns_without_fetching_rows(self):
        for stored_data in ([], [{"webhook_ciphertext": MARKER}]):
            with self.subTest(empty=not stored_data):
                query = StoreQuery(data=stored_data)
                self.assertTrue(database_for(query).check_account_volume_store())
                self.assertEqual(set(query.projection.split(",")), REQUIRED_COLUMNS)
                self.assertEqual(query.limit_count, 0)

    def test_missing_columns_or_inaccessible_store_never_reports_ready(self):
        for missing in REQUIRED_COLUMNS:
            with self.subTest(missing=missing), self.assertLogs("database", "ERROR"):
                database = database_for(StoreQuery(columns=REQUIRED_COLUMNS - {missing}))
                environment = main_definitions({"volume_alert_status"}, {
                    "db": database,
                    "volume_alert_monitor": SimpleNamespace(status=lambda: {
                        "configuration": "configured", "enabled": True}),
                })
                status = environment["volume_alert_status"]()
                self.assertEqual(status["store"], "unavailable")
                self.assertEqual(status["configuration"], "store_unavailable")
        with self.assertLogs("database", "ERROR"):
            self.assertFalse(database_for(None).check_account_volume_store())

    def test_probe_get_save_diagnostics_allowlist_metadata_and_redact_payloads(self):
        cases = (
            ("APIError", "42P01", "missing_schema"),
            ("APIError", "42501", "permission_auth"),
            ("ConnectTimeout", None, "connectivity"),
            (MARKER, MARKER, "unknown"),
        )
        for exception_type, code, category in cases:
            for operation in ("probe", "get", "save"):
                with self.subTest(exception_type=exception_type, operation=operation):
                    error = type(exception_type, (Exception,), {})(MARKER)
                    error.code = code
                    database = database_for(StoreQuery(failure=error))
                    with self.assertLogs("database", "ERROR") as captured:
                        if operation == "probe":
                            self.assertFalse(database.check_account_volume_store())
                        else:
                            with self.assertRaises(RuntimeError) as raised:
                                if operation == "get":
                                    database.get_account_volume_settings(MARKER)
                                else:
                                    database.save_account_volume_settings(MARKER, {
                                        "tickers": [MARKER], "webhook_ciphertext": MARKER})
                            self.assertEqual(str(raised.exception), "account_alert_store_unavailable")
                            self.assertTrue(raised.exception.__suppress_context__)
                    output = " ".join(captured.output)
                    self.assertIn("operation=" + operation, output)
                    self.assertIn("category=" + category, output)
                    self.assertNotIn(MARKER, output)
                    self.assertNotIn("Traceback", output)
                    safe_code = code if code in {"42P01", "42501"} else "unknown"
                    self.assertIn("code=" + safe_code, output)

    def test_http_auth_status_is_classified_without_body_or_unknown_code(self):
        error = requests.HTTPError(MARKER, response=SimpleNamespace(status_code=403))
        error.code = MARKER
        with self.assertLogs("database", "ERROR") as captured:
            self.assertFalse(database_for(StoreQuery(failure=error)).check_account_volume_store())
        self.assertIn("code=403 category=permission_auth", " ".join(captured.output))
        self.assertNotIn(MARKER, " ".join(captured.output))

    def test_empty_settings_success_preserves_shapes_and_user_scope(self):
        query = StoreQuery()
        database = database_for(query)
        self.assertEqual(database.get_account_volume_settings("test-user"), {
            "tickers": [], "webhook_ciphertext": None})
        self.assertEqual(query.filters, [("user_id", "test-user")])
        settings = {"tickers": ["2330.TW"], "webhook_ciphertext": "test-only-encrypted"}
        database.save_account_volume_settings("test-user", settings)
        self.assertEqual(query.payload, {"user_id": "test-user", **settings})
        self.assertEqual(query.on_conflict, "user_id")

    def test_settings_endpoints_return_concise_sanitized_503(self):
        database = Mock()
        environment = main_definitions({"get_account_volume_alerts", "put_account_volume_alerts"}, {
            "db": database, "HTTPException": HTTPException,
            "AccountVolumeSettingsRequest": object, "Request": object,
            "_require_same_origin": Mock(), "parse_alert_tickers": lambda text: ("2330.TW",),
            "datetime": datetime, "timezone": timezone,
        })
        database.get_account_volume_settings.side_effect = RuntimeError(MARKER)
        for invoke in (
            lambda: environment["get_account_volume_alerts"]({"id": "test-user"}),
            lambda: environment["put_account_volume_alerts"](
                SimpleNamespace(tickers=["2330.TW"], remove_webhook=False, webhook=None),
                object(), {"id": "test-user"}),
        ):
            with self.assertRaises(HTTPException) as raised:
                invoke()
            self.assertEqual(raised.exception.status_code, 503)
            self.assertEqual(raised.exception.detail, "通知設定暫時無法使用，請聯絡管理員")
            self.assertNotIn(MARKER, raised.exception.detail)
        database.get_account_volume_settings.side_effect = None
        database.get_account_volume_settings.return_value = {"webhook_ciphertext": None}
        database.save_account_volume_settings.side_effect = RuntimeError(MARKER)
        with self.assertRaises(HTTPException) as raised:
            environment["put_account_volume_alerts"](
                SimpleNamespace(tickers=["2330.TW"], remove_webhook=False, webhook=None),
                object(), {"id": "test-user"})
        self.assertEqual(raised.exception.status_code, 503)
        self.assertEqual(raised.exception.detail, "通知設定暫時無法使用，請聯絡管理員")


class AIGatewayDiagnosticsTests(unittest.TestCase):
    def gateway_error(self, expected_code, response=None, exception=None):
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-only-key"}, clear=True), \
             patch("route_gateway.requests.post", return_value=response, side_effect=exception):
            with self.assertLogs("routing", "INFO") as captured:
                with self.assertRaises(AIUnavailable) as raised:
                    AIGateway().complete({})
        self.assertEqual(raised.exception.code, expected_code)
        self.assertNotIn(MARKER, str(raised.exception))
        self.assertNotIn(MARKER, " ".join(captured.output))

    def test_timeout_and_network_have_distinct_static_codes(self):
        self.gateway_error("ai_timeout", exception=requests.Timeout(MARKER))
        self.gateway_error("ai_network_error", exception=requests.ConnectionError(MARKER))

    def test_provider_and_rejected_requests_have_distinct_codes(self):
        for status in (500, 502, 503):
            with self.subTest(status=status):
                response = Mock(status_code=status)
                response.raise_for_status.side_effect = requests.HTTPError(MARKER, response=response)
                self.gateway_error("ai_provider_error", response=response)
        for status in (400, 404, 422):
            with self.subTest(status=status):
                self.gateway_error("ai_request_rejected", response=Mock(status_code=status))

    def test_malformed_json_and_content_return_static_code(self):
        malformed = (None, {}, {"choices": []}, {"choices": [{"message": {"content": ""}}]},
                     {"choices": [{"message": {"content": [MARKER]}}]})
        for payload in malformed:
            with self.subTest(payload=payload):
                response = Mock(status_code=200)
                response.json.return_value = payload
                self.gateway_error("ai_malformed_response", response=response)
        response = Mock(status_code=200)
        response.json.side_effect = ValueError(MARKER)
        self.gateway_error("ai_malformed_response", response=response)

    def test_missing_and_unknown_codes_do_not_echo_private_input(self):
        with patch.dict(os.environ, {}, clear=True), patch("route_gateway.requests.post") as post:
            with self.assertRaises(AIUnavailable) as raised:
                AIGateway().complete({})
            self.assertEqual(raised.exception.code, "ai_not_configured")
            self.assertIn("管理員", raised.exception.message)
            self.assertNotIn("GROQ_API_KEY", raised.exception.message)
            post.assert_not_called()
        error = AIUnavailable(MARKER)
        self.assertEqual(error.code, "ai_unavailable")
        self.assertNotIn(MARKER, error.message)

    def test_auth_rate_limit_and_failure_circuits_preserve_no_call_behavior(self):
        cases = ((401, "ai_auth_failed"), (403, "ai_auth_failed"), (429, "ai_rate_limited"))
        for status, code in cases:
            with self.subTest(status=status), \
                 patch.dict(os.environ, {"GROQ_API_KEY": "test-only-key"}, clear=True), \
                 patch("route_gateway.time.monotonic", return_value=100), \
                 patch("route_gateway.requests.post", return_value=Mock(
                     status_code=status, headers={"Retry-After": "60"})) as post:
                gateway = AIGateway()
                with self.assertRaises(AIUnavailable) as first:
                    gateway.complete({})
                with self.assertRaises(AIUnavailable) as second:
                    gateway.complete({})
                self.assertEqual(first.exception.code, code)
                self.assertEqual(second.exception.code, "ai_circuit_open")
                self.assertEqual(post.call_count, 1)
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-only-key"}, clear=True), \
             patch("route_gateway.time.monotonic", return_value=100), \
             patch("route_gateway.requests.post", side_effect=requests.Timeout(MARKER)) as post:
            gateway = AIGateway()
            for _ in range(3):
                with self.assertRaises(AIUnavailable) as raised:
                    gateway.complete({})
                self.assertEqual(raised.exception.code, "ai_timeout")
            with self.assertRaises(AIUnavailable) as raised:
                gateway.complete({})
            self.assertEqual(raised.exception.code, "ai_circuit_open")
            self.assertEqual(post.call_count, 3)

    def test_success_keeps_model_tokens_timeout_and_resets_failures(self):
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-only-key"}, clear=True), \
             patch("route_gateway.requests.post", return_value=Mock(status_code=200)) as post:
            post.return_value.json.return_value = {"choices": [{"message": {"content": "OK"}}]}
            gateway = AIGateway()
            gateway.complete({})
            gateway.failures = 2
            self.assertEqual(gateway.complete({"model": "retired", "max_tokens": 9999}), "OK")
            self.assertEqual(gateway.failures, 0)
            self.assertEqual(post.call_args.kwargs["timeout"], (5, 30))
            self.assertEqual(post.call_args.kwargs["json"]["model"], DEFAULT_GROQ_MODEL)
            self.assertEqual(post.call_args.kwargs["json"]["max_tokens"], 1500)


class AIClientAndSummaryDiagnosticsTests(unittest.IsolatedAsyncioTestCase):
    def environment(self):
        gateway = SimpleNamespace(complete=Mock(return_value="safe summary"))
        environment = main_definitions({"MaiAgentClient", "chat", "auto_news"}, {
            "asyncio": asyncio, "http_requests": requests, "AIUnavailable": AIUnavailable,
            "DEFAULT_GROQ_MODEL": DEFAULT_GROQ_MODEL, "ai_gateway": gateway,
            "ChatRequest": object, "_extract_screener_prompt_payload": lambda _: None,
            "NewsCrawler": SimpleNamespace(fetch_all=Mock(return_value=[{
                "title": "test news", "source": "test source"}])),
            "logger": logging.getLogger("test-ai-summary"),
        })
        environment["mai_client"] = environment["MaiAgentClient"]("test-only-key", "", "")
        return environment, gateway

    async def test_client_chat_and_summary_forward_all_static_gateway_codes(self):
        codes = ("ai_timeout", "ai_network_error", "ai_provider_error", "ai_malformed_response",
                 "ai_auth_failed", "ai_rate_limited", "ai_request_rejected", "ai_busy", "ai_circuit_open")
        for code in codes:
            with self.subTest(code=code):
                environment, gateway = self.environment()
                error = AIUnavailable(code)
                gateway.complete.side_effect = error
                request = SimpleNamespace(message="hello", conversation_id=None)
                for result in (await environment["chat"](request), await environment["auto_news"]()):
                    self.assertEqual(result, {"status": "error", "code": code, "message": error.message})
                    self.assertNotIn(MARKER, str(result))

    async def test_disabled_summary_does_not_crawl_and_frontend_uses_textcontent(self):
        environment, _ = self.environment()
        environment["mai_client"].enabled = False
        result = await environment["auto_news"]()
        self.assertEqual(result["code"], "ai_not_configured")
        self.assertIn("管理員", result["message"])
        for internal in ("GROQ_API_KEY", "MaiAgent", "Render", "migrations/"):
            self.assertNotIn(internal, result["message"])
        environment["NewsCrawler"].fetch_all.assert_not_called()
        frontend = Path("static/index.html").read_text(encoding="utf-8")
        self.assertIn("error.textContent = aiRes.message", frontend)
        self.assertNotIn("innerHTML = aiRes.message", frontend)

    async def test_unexpected_client_and_summary_failures_are_static_and_redacted(self):
        environment, gateway = self.environment()
        gateway.complete.side_effect = RuntimeError(MARKER)
        result = environment["mai_client"].chat("hello")
        self.assertEqual(result["code"], "ai_unavailable")
        self.assertNotIn(MARKER, str(result))
        environment["NewsCrawler"].fetch_all.side_effect = RuntimeError(MARKER)
        with self.assertLogs("test-ai-summary", "WARNING") as captured:
            result = await environment["auto_news"]()
        self.assertEqual(result["code"], "ai_unavailable")
        self.assertNotIn(MARKER, str(result) + " ".join(captured.output))
        self.assertNotIn("Traceback", " ".join(captured.output))

    async def test_client_and_summary_preserve_success_shapes(self):
        environment, _ = self.environment()
        self.assertEqual(environment["mai_client"].chat("hello"), {
            "status": "success", "reply": "safe summary", "conversation_id": "groq-session"})
        self.assertEqual(await environment["auto_news"](), {
            "status": "success", "summary": "safe summary", "news_count": 1,
            "sources_used": ["test source"]})


if __name__ == "__main__":
    unittest.main()

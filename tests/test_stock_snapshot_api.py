import ast
import asyncio
import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from fastapi.responses import JSONResponse


def load_snapshot_endpoint(service):
    tree = ast.parse(Path("main.py").read_text(encoding="utf-8"))
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "get_stock_snapshot"
    )
    function.decorator_list = []
    namespace = {
        "asyncio": asyncio,
        "JSONResponse": JSONResponse,
        "logger": SimpleNamespace(exception=lambda *_args, **_kwargs: None),
        "market_insights": service,
    }
    exec(
        compile(ast.Module(body=[function], type_ignores=[]), "main.py", "exec"),
        namespace,
    )
    return namespace["get_stock_snapshot"]


class StockSnapshotEndpointTests(unittest.TestCase):
    def test_success_and_partial_payloads_remain_200(self):
        for status in ("success", "partial"):
            service = SimpleNamespace(
                stock_snapshot=lambda _ticker, value=status: {
                    "status": value,
                    "ticker": "2330",
                    "data": {},
                    "unavailable": [],
                    "warnings": [],
                }
            )
            endpoint = load_snapshot_endpoint(service)
            result = asyncio.run(endpoint("2330.TW"))
            self.assertEqual(result["status"], status)

    def test_invalid_ticker_is_sanitized_400(self):
        def invalid(_ticker):
            raise ValueError("internal validation detail")

        endpoint = load_snapshot_endpoint(SimpleNamespace(stock_snapshot=invalid))
        response = asyncio.run(endpoint("bad.ticker"))
        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(payload["code"], "invalid_ticker")
        self.assertNotIn("internal validation detail", str(payload))

    def test_all_sections_unavailable_is_503(self):
        payload = {
            "status": "unavailable",
            "ticker": "2330",
            "data": {},
            "unavailable": [
                {"section": "price", "code": "price_upstream_unavailable"}
            ],
            "warnings": [],
        }
        service = SimpleNamespace(stock_snapshot=lambda _ticker: payload)
        endpoint = load_snapshot_endpoint(service)
        response = asyncio.run(endpoint("2330"))
        self.assertEqual(response.status_code, 503)
        self.assertEqual(json.loads(response.body), payload)

    def test_unexpected_failure_is_sanitized_503(self):
        def failed(_ticker):
            raise RuntimeError("secret upstream response")

        endpoint = load_snapshot_endpoint(SimpleNamespace(stock_snapshot=failed))
        response = asyncio.run(endpoint("2330"))
        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(payload["code"], "snapshot_unavailable")
        self.assertNotIn("secret upstream response", str(payload))


if __name__ == "__main__":
    unittest.main()

"""Execute the production valuation model and endpoints without importing main."""
import ast
import asyncio
import copy
import unittest
import warnings
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from pydantic import BaseModel

from valuation_service import calculate_valuation


def api_snapshot():
    return {"status": "partial", "ticker": "2330.TW", "model_version": "offline-fixture",
            "data": {
                "identity": {"code": "2330", "ticker": "2330.TW", "ordinary": True},
                "quote": {"value": 100, "freshness": "fresh", "as_of": "2026-10-23", "kind": "close"},
                "eps_ttm": {"value": 5, "status": "available", "published_at": None},
                "official_pe": {"value": 22, "as_of": "2026-10-23"},
                "peer_reference": {"status": "unavailable"},
                "valuation_as_of": "2026-10-26", "horizon_end": "2027-10-26",
                "eps_period_start": "2026-10-26", "eps_period_end": "2027-10-25",
            }}


def load_api(snapshot):
    tree = ast.parse(Path("main.py").read_text(encoding="utf-8"))
    names = {"ValuationAssumptionsRequest", "get_valuation", "post_valuation_assumptions"}
    nodes = [node for node in tree.body if isinstance(node, (ast.ClassDef, ast.AsyncFunctionDef)) and node.name in names]
    if len(nodes) != 3:
        raise AssertionError("Production valuation model/endpoints missing")
    for node in nodes:
        node.decorator_list = []
    namespace = {"__name__": __name__, "BaseModel": BaseModel, "asyncio": asyncio,
                 "JSONResponse": JSONResponse, "HTTPException": HTTPException, "uuid4": uuid4,
                 "valuation_service": SimpleNamespace(snapshot=snapshot),
                 "calculate_valuation": calculate_valuation}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "main.py", "exec"), namespace)
    app = FastAPI()
    app.add_api_route("/api/valuation/{ticker}", namespace["get_valuation"], methods=["GET"])
    app.add_api_route("/api/valuation/{ticker}/assumptions", namespace["post_valuation_assumptions"], methods=["POST"])
    return TestClient(app)


class ValuationApiTests(unittest.TestCase):
    def setUp(self):
        self.payload = api_snapshot()
        self.client = load_api(lambda _ticker: copy.deepcopy(self.payload))
        self.addCleanup(self.client.close)

    def test_get_preserves_source_dates_and_gives_unique_request_ids(self):
        first = self.client.get("/api/valuation/2330.TW")
        second = self.client.get("/api/valuation/2330.TW")
        self.assertEqual(first.status_code, 200)
        data = first.json()
        UUID(data["request_id"])
        self.assertNotEqual(data["request_id"], second.json()["request_id"])
        self.assertEqual(data["data"]["quote"]["as_of"], "2026-10-23")
        self.assertIsNone(data["data"]["eps_ttm"]["published_at"])
        self.assertEqual(data["data"]["official_pe"]["value"], 22)

    def test_get_retains_calendar_version_expected_day_and_per_market_source_evidence(self):
        evidence = {"expected_completed_trading_day": "2026-10-22", "exception_version": "offline-closure-v1",
                    "used_exceptions": [{"date": "2026-10-23", "market_scope": ["TW"],
                                         "announced_at": "2026-10-22", "verified_at": "2026-10-26",
                                         "sources": [{"market_scope": ["TW"], "source_url": "https://www.twse.com.tw/fixture/notice.pdf"}]}]}
        self.payload["data"]["quote"].update(as_of="2026-10-22", calendar_evidence=evidence)
        response = self.client.get("/api/valuation/2330")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["quote"]["calendar_evidence"], evidence)

    def test_no_source_data_uses_503_and_keeps_unavailable_sections(self):
        self.payload["status"] = "unavailable"
        self.payload["unavailable_sections"] = ["quote", "eps_ttm"]
        response = self.client.get("/api/valuation/2330")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["unavailable_sections"], ["quote", "eps_ttm"])

    def test_invalid_ticker_errors_are_400_get_and_422_post(self):
        def invalid(_ticker):
            raise ValueError("有效台股代號 required")
        client = load_api(invalid)
        self.addCleanup(client.close)
        self.assertEqual(client.get("/api/valuation/bad").status_code, 400)
        self.assertEqual(client.post("/api/valuation/bad/assumptions", json={}).status_code, 422)

    def test_empty_assumptions_do_not_manufacture_multiples_or_future_eps(self):
        response = self.client.post("/api/valuation/2330/assumptions", json={})
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["current_model"]["reason_code"], "pe_assumptions_required")
        self.assertEqual(data["scenarios"], [])
        self.assertIsNone(data["forward_pe"])

    def test_manual_current_range_is_independent_of_official_pe(self):
        response = self.client.post("/api/valuation/2330/assumptions", json={"current_pe": {"low": 16, "mid": 20, "high": 24}})
        data = response.json()["data"]
        self.assertEqual(response.status_code, 200)
        self.assertEqual([data["current_model"][k] for k in ("low", "mid", "high")], [80, 100, 120])
        self.assertEqual(data["current_model"]["classification"], "within")
        self.assertEqual(data["official_pe"]["value"], 22)

    def test_scenarios_can_be_manual_without_verified_historical_ttm(self):
        self.payload["data"]["eps_ttm"] = {"value": None, "status": "unavailable"}
        rows = [{"eps": 4, "pe": 15}, {"eps": 5.5, "pe": 20}, {"eps": 7, "pe": 25}]
        response = self.client.post("/api/valuation/2330/assumptions", json={"scenarios": rows})
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual([r["price"] for r in data["scenarios"]], [60, 110, 175])
        self.assertAlmostEqual(data["forward_pe"], 100 / 5.5)
        self.assertEqual(data["horizon_end"], "2027-10-26")
        self.assertEqual(data["eps_period_start"], "2026-10-26")

    def test_bad_input_shapes_and_nonfinite_values_return_422_not_500(self):
        cases = [
            {"current_pe": {"low": 30, "mid": 20, "high": 10}},
            {"current_pe": {"low": 0, "mid": 20, "high": 30}},
            {"current_pe": {"low": "NaN", "mid": 20, "high": 30}},
            {"current_pe": {"low": "Infinity", "mid": 20, "high": 30}},
            {"current_pe": []}, {"scenarios": [42]},
            {"scenarios": [{"eps": 1, "pe": 20}]},
            {"scenarios": [{"eps": -1, "pe": 20}] * 3},
        ]
        for body in cases:
            with self.subTest(body=body):
                self.assertEqual(self.client.post("/api/valuation/2330/assumptions", json=body).status_code, 422)

    def test_unsupported_products_reject_manual_scenario_instead_of_showing_prices(self):
        self.payload["data"]["identity"]["ordinary"] = False
        response = self.client.post("/api/valuation/2330/assumptions", json={"scenarios": [{"eps": 5, "pe": 20}] * 3})
        self.assertEqual(response.status_code, 422)
        self.assertIn("不適用", response.json()["detail"])

    def test_overflowing_result_and_tiny_price_are_json_safe(self):
        self.payload["data"]["eps_ttm"]["value"] = 1e308
        response = self.client.post("/api/valuation/2330/assumptions", json={"current_pe": {"low": 16, "mid": 20, "high": 24}})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["current_model"]["reason_code"], "nonfinite_calculation")
        self.payload["data"]["quote"]["value"] = 1e-308
        response = self.client.post("/api/valuation/2330/assumptions", json={"scenarios": [{"eps": 1e6, "pe": 1e4}] * 3})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(all(r["price_change_pct"] is None for r in response.json()["data"]["scenarios"]))


if __name__ == "__main__":
    unittest.main()

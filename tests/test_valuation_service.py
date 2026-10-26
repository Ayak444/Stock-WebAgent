"""Deterministic financial, source-shape and failure fixtures; never live vendors."""
import copy
import json
import math
import threading
import time
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from valuation_service import (
    OFFICIAL, TAIPEI, TWSE_HOLIDAY_URL, ValuationService, calculate_valuation,
    iso_date, number, ordinary_company, peer_reference, percentile,
    quarterly_ttm, quote_freshness, quote_calendar_evidence,
    load_calendar_exceptions, validated_calendar_exceptions,
    valuation_service as production_service,
)


NOW = datetime(2026, 10, 26, 18, tzinfo=TAIPEI)
HOLIDAYS = [
    {"Date": "20260102", "Name": "開始交易"},
    {"Date": "20261026", "Name": "國定假日休市"},
    {"Date": "20261231", "Name": "最後交易"},
]


def quarters():
    return {
        "currency": "TWD", "quote_currency": "TWD", "vendor_ttm": 99,
        "source_url": "https://example.invalid/quarter-fixture",
        "actions_verified": False, "split_dates": [],
        "quarters": [
            {"period_end": day, "period_type": "standalone_quarter",
             "diluted_eps": value, "basic_eps": value + .25,
             "diluted_shares": 100, "basic_shares": 100}
            for day, value in zip(
                ("2026-06-30", "2026-03-31", "2025-12-31", "2025-09-30"),
                (6, 5, 4, 3),
            )
        ],
    }


def profile(code="2330", industry="24", name="離線普通股公司"):
    return {"公司代號": code, "公司名稱": name, "公司簡稱": name,
            "產業別": industry, "PreferredStock": "1000"}


def simple_snapshot(price=100, eps=5, freshness="fresh"):
    return {"identity": {"ordinary": True},
            "quote": {"value": price, "freshness": freshness, "as_of": "2026-10-23"},
            "eps_ttm": {"value": eps, "status": "available"},
            "peer_reference": {"status": "unavailable"}}


def exception_fixture(scopes=None):
    scopes = scopes or ["TW", "TWO"]
    hosts = {"TW": "www.twse.com.tw", "TWO": "www.tpex.org.tw"}
    return {"schemaVersion": 1, "version": "offline-closure-v1", "records": [{
        "date": "2026-10-23", "announced_at": "2026-10-22", "verified_at": "2026-10-26",
        "kind": "full_day_closure", "reason": "離線臨時休市 fixture", "market_scope": scopes,
        "sources": [{"market_scope": [market], "source_url": f"https://{hosts[market]}/fixture/closure-notice.pdf"} for market in scopes],
    }]}


def peer_fixture(market="TW"):
    codes = [str(2301 + i) for i in range(6)]
    profiles = [profile()] + [profile(code) for code in codes]
    field = "PEratio" if market == "TW" else "PriceEarningRatio"
    rows = [{"Code": code, "Date": "1151023", field: value}
            for code, value in zip(codes, (10, 12, 16, 20, 30, 40))]
    rows.append({"Code": "2330", "Date": "1151023", field: 999})
    return profiles, rows


def datasets(market="TW", code="2330"):
    profiles, peers = peer_fixture(market)
    profiles = [profile(code)] + [p for p in profiles if p["公司代號"] != "2330"]
    field = "PEratio" if market == "TW" else "PriceEarningRatio"
    pe = [r for r in peers if r["Code"] != "2330"]
    pe.append({"Code": code, "Date": "1151023", field: "22"})
    eps = {"公司代號": code, "季別": "2"}
    if market == "TW":
        eps.update({"年度": "115", "基本每股盈餘（元）": "49.33", "出表日期": "1151026"})
    else:
        eps.update({"Year": "115", "基本每股盈餘": "11.87", "Date": "1151026"})
    result = {url: [] for sources in OFFICIAL.values() for url in sources.values()}
    result.update({
        OFFICIAL[market]["companies"]: profiles,
        OFFICIAL[market]["quote"]: [{"Code": code, "Date": "1151023", "ClosingPrice": "100"}],
        OFFICIAL[market]["pe"]: pe,
        OFFICIAL[market]["eps"]: [eps],
        TWSE_HOLIDAY_URL: HOLIDAYS,
    })
    return result


class QuarterlyEpsTests(unittest.TestCase):
    def test_four_standalone_quarters_are_explicit_approximation_not_filed_ttm(self):
        result = quarterly_ttm(quarters(), NOW)
        self.assertEqual(result["value"], 18)
        self.assertEqual(result["basis"], "diluted")
        self.assertEqual((result["period_start"], result["period_end"]), ("2025-07-01", "2026-06-30"))
        self.assertIsNone(result["published_at"])
        self.assertIn("quarter_sum_approximation", result["warnings"])
        self.assertIn("corporate_actions_unknown_approximation", result["warnings"])
        self.assertIn("非會計規則", result["methodology"])

    def test_negative_individual_quarter_is_valid_when_total_positive(self):
        payload = quarters()
        payload["quarters"][-1]["diluted_eps"] = -1
        self.assertEqual(quarterly_ttm(payload, NOW)["value"], 14)

    def test_basic_fallback_uses_all_four_basic_values_not_mixed_basis(self):
        payload = quarters()
        payload["quarters"][0]["diluted_eps"] = None
        result = quarterly_ttm(payload, NOW)
        self.assertEqual((result["basis"], result["value"]), ("basic", 19))
        payload["quarters"][1]["basic_eps"] = None
        self.assertIsNone(quarterly_ttm(payload, NOW)["value"])

    def test_missing_nan_duplicate_gapped_cumulative_future_and_stale_rows_rejected(self):
        changes = {
            "missing": lambda p: p["quarters"].pop(),
            "nan": lambda p: p["quarters"][0].update(diluted_eps=float("nan"), basic_eps=None),
            "duplicate": lambda p: p["quarters"][0].update(period_end="2026-03-31"),
            "gap": lambda p: p["quarters"][-1].update(period_end="2025-06-30"),
            "not_quarter_end": lambda p: p["quarters"][0].update(period_end="2026-06-29"),
            "cumulative": lambda p: p["quarters"][0].update(period_type="cumulative_ytd"),
            "future": lambda p: p["quarters"][0].update(period_end="2026-12-31"),
            "currency": lambda p: p.update(currency="USD"),
        }
        for label, change in changes.items():
            with self.subTest(label=label):
                payload = quarters()
                change(payload)
                self.assertIsNone(quarterly_ttm(payload, NOW)["value"])
        self.assertIsNone(quarterly_ttm(quarters(), NOW + timedelta(days=400))["value"])

    def test_unknown_action_guard_includes_exact_one_percent_and_rejects_above(self):
        payload = quarters()
        payload["quarters"][0]["diluted_shares"] = 101
        accepted = quarterly_ttm(payload, NOW)
        self.assertEqual(accepted["value"], 18)
        self.assertIn("small_weighted_share_variation_approximation", accepted["warnings"])
        payload["quarters"][0]["diluted_shares"] = 101.00001
        self.assertEqual(quarterly_ttm(payload, NOW)["reason_code"], "material_share_change")

    def test_unknown_action_missing_nonpositive_nonfinite_counts_rejected(self):
        for value in (None, 0, -1, float("nan"), float("inf")):
            with self.subTest(value=value):
                payload = quarters()
                payload["quarters"][0]["diluted_shares"] = value
                self.assertEqual(quarterly_ttm(payload, NOW)["reason_code"], "share_basis_unverified")

    def test_known_split_rejects_even_stable_weighted_shares(self):
        payload = quarters()
        payload.update(actions_verified=True, split_dates=["2026-03-01"])
        self.assertEqual(quarterly_ttm(payload, NOW)["reason_code"], "corporate_action_in_period")

    def test_eps_sum_overflow_cannot_escape_as_nonfinite_json(self):
        payload = quarters()
        for row in payload["quarters"]:
            row["diluted_eps"] = 1e308
        result = quarterly_ttm(payload, NOW)
        self.assertEqual(result["reason_code"], "invalid_eps_total")
        json.dumps(result, allow_nan=False)


class PeerAndCalendarTests(unittest.TestCase):
    def test_exact_type_classification_excludes_dr_etf_pref_and_unknown_profiles(self):
        common_only = profile()
        common_only.pop("PreferredStock")
        self.assertTrue(ordinary_company("2330", common_only))
        # Issuers may have preferred shares alongside their ordinary listing.
        self.assertTrue(ordinary_company("2330", profile()))
        for code, item in (("9105", profile("9105", "91")), ("9110", profile("9110", "91")),
                           ("2330", profile(industry="91")), ("0050", None),
                           ("2882A", profile("2882A")), ("2330", None),
                           ("2330", profile(name="測試存託憑證")), ("2330", profile(industry=""))):
            with self.subTest(code=code, item=item):
                self.assertFalse(ordinary_company(code, item))

    def test_peer_percentiles_use_linear_interpolation_and_exclude_target(self):
        profiles, rows = peer_fixture()
        result = peer_reference("2330", profile(), profiles, rows, "2026-10-23", "2026-10-23", "TW", "fresh")
        self.assertEqual(result["count"], 6)
        self.assertEqual([result[k] for k in ("pe_low", "pe_mid", "pe_high")], [13, 18, 27.5])
        self.assertNotIn("2330.TW", [p["ticker"] for p in result["peers"]])
        self.assertTrue(result["source_url"].startswith("https://"))
        self.assertEqual(percentile([10, 12, 16, 20, 30, 40], .75), 27.5)

    def test_peer_dates_industry_profiles_and_positive_finite_values_are_required(self):
        profiles, rows = peer_fixture()
        rows[0]["Date"] = "1151022"
        rows[1]["PEratio"] = float("nan")
        profiles[3]["產業別"] = "91"
        result = peer_reference("2330", profile(), profiles, rows, "2026-10-23", "2026-10-23", "TW", "fresh")
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["count"], 3)
        self.assertEqual(result["reason_code"], "insufficient_peers")
        for freshness, pe_date in (("stale", "2026-10-23"), ("unknown", "2026-10-23"), ("fresh", "2026-10-22")):
            with self.subTest(freshness=freshness, pe_date=pe_date):
                self.assertEqual(peer_reference("2330", profile(), profiles, rows, "2026-10-23", pe_date, "TW", freshness)["status"], "unavailable")

    def test_peer_rows_are_deduplicated_and_otc_field_shape_supported(self):
        profiles, rows = peer_fixture("TWO")
        rows.append(copy.deepcopy(rows[0]))
        result = peer_reference("2330", profile(), profiles, rows, "2026-10-23", "2026-10-23", "TWO", "fresh")
        self.assertEqual(result["count"], 6)
        self.assertEqual(result["pe_mid"], 18)
        self.assertTrue(all(p["ticker"].endswith(".TWO") for p in result["peers"]))

    def test_calendar_holiday_weekend_and_start_last_trading_records(self):
        self.assertEqual(quote_freshness("2026-10-23", HOLIDAYS, NOW), "fresh")
        self.assertEqual(quote_freshness("2026-10-22", HOLIDAYS, NOW), "stale")
        self.assertEqual(quote_freshness("2026-10-23", None, NOW), "unknown")
        self.assertEqual(quote_freshness("2026-01-02", HOLIDAYS, datetime(2026, 1, 2, 18, tzinfo=TAIPEI)), "fresh")
        self.assertEqual(quote_freshness("2026-12-31", HOLIDAYS, datetime(2026, 12, 31, 18, tzinfo=TAIPEI)), "fresh")
        self.assertEqual(quote_freshness("2026-10-22", HOLIDAYS, datetime(2026, 10, 23, 10, tzinfo=TAIPEI)), "fresh")
        self.assertEqual(quote_freshness("2026-10-23", HOLIDAYS, datetime(2026, 10, 25, 18, tzinfo=TAIPEI)), "fresh")


class ExceptionalCalendarTests(unittest.TestCase):
    def test_verified_full_day_closure_changes_latest_completed_day_for_each_market(self):
        for market in ("TW", "TWO"):
            with self.subTest(market=market):
                evidence = quote_calendar_evidence("2026-10-22", HOLIDAYS, NOW, market, exception_fixture())
                self.assertEqual(evidence["freshness"], "fresh")
                self.assertEqual(evidence["expected_completed_trading_day"], "2026-10-22")
                self.assertEqual(evidence["exception_version"], "offline-closure-v1")
                self.assertEqual(evidence["annual_calendar_source_url"], TWSE_HOLIDAY_URL)
                self.assertEqual(evidence["used_exceptions"][0]["date"], "2026-10-23")
                self.assertTrue(evidence["used_exceptions"][0]["sources"])
                self.assertEqual(quote_freshness("2026-10-23", HOLIDAYS, NOW, market, exception_fixture()), "stale")

    def test_exception_evidence_cannot_replace_failed_annual_schedule(self):
        result = quote_calendar_evidence("2026-10-22", None, NOW, "TW", exception_fixture())
        self.assertEqual(result["freshness"], "unknown")
        self.assertEqual(result["reason_code"], "annual_calendar_unavailable")
        self.assertIsNone(result["expected_completed_trading_day"])
        self.assertEqual(result["used_exceptions"], [])

    def test_wrong_market_and_missing_scope_evidence_cannot_close_otc(self):
        tw_only = exception_fixture(["TW"])
        self.assertEqual(validated_calendar_exceptions(tw_only, "TWO", NOW.date()), [])
        result = quote_calendar_evidence("2026-10-23", HOLIDAYS, NOW, "TWO", tw_only)
        self.assertEqual(result["freshness"], "fresh")
        self.assertEqual(result["used_exceptions"], [])
        missing_otc_proof = exception_fixture()
        missing_otc_proof["records"][0]["sources"] = missing_otc_proof["records"][0]["sources"][:1]
        self.assertEqual(validated_calendar_exceptions(missing_otc_proof, "TW", NOW.date()), [])

    def test_invalid_future_untrusted_or_unsupported_records_are_ignored(self):
        changes = {
            "future_verification": lambda r: r.update(verified_at="2026-10-27"),
            "future_announcement": lambda r: r.update(announced_at="2026-10-27"),
            "verification_before_announcement": lambda r: r.update(verified_at="2026-10-21"),
            "bad_date": lambda r: r.update(date="not-a-date"),
            "wrong_kind": lambda r: r.update(kind="partial_day_closure"),
            "bad_scope": lambda r: r.update(market_scope=["NYSE"]),
            "untrusted_host": lambda r: r["sources"][0].update(source_url="https://www.twse.com.tw.attacker.invalid/notice"),
            "plain_http": lambda r: r["sources"][0].update(source_url="http://www.twse.com.tw/notice"),
            "unexpected_port": lambda r: r["sources"][0].update(source_url="https://www.twse.com.tw:8443/notice"),
        }
        for label, change in changes.items():
            with self.subTest(label=label):
                payload = exception_fixture()
                change(payload["records"][0])
                self.assertEqual(validated_calendar_exceptions(payload, "TW", NOW.date()), [])
                self.assertEqual(quote_freshness("2026-10-23", HOLIDAYS, NOW, "TW", payload), "fresh")
        for payload in ({}, {"schemaVersion": 2, "version": "v1", "records": []},
                        {"schemaVersion": 1, "version": "bad version", "records": []}):
            self.assertEqual(validated_calendar_exceptions(payload, "TW", NOW.date()), [])

    def test_future_closure_does_not_change_an_earlier_completed_day(self):
        payload = exception_fixture()
        payload["records"][0]["date"] = "2026-10-30"
        result = quote_calendar_evidence("2026-10-23", HOLIDAYS, NOW, "TW", payload)
        self.assertEqual(result["expected_completed_trading_day"], "2026-10-23")
        self.assertEqual(result["used_exceptions"], [])

    def test_production_loader_is_explicit_and_keeps_its_reviewed_provenance(self):
        self.assertIs(production_service.exception_calendar, load_calendar_exceptions)
        payload = load_calendar_exceptions()
        for market in ("TW", "TWO"):
            evidence = quote_calendar_evidence("2026-10-22", HOLIDAYS, NOW, market, payload)
            self.assertEqual(evidence["expected_completed_trading_day"], "2026-10-22")
            self.assertEqual(evidence["exception_version"], payload["version"])
            record = evidence["used_exceptions"][0]
            self.assertEqual(record["announced_at"], "2026-10-22")
            self.assertEqual(record["verified_at"], "2026-10-26")
            self.assertTrue(all(source["source_url"].startswith("https://") for source in record["sources"]))
        with patch("valuation_service.Path.read_text", side_effect=OSError("offline fixture")):
            self.assertEqual(load_calendar_exceptions(), {})


class CalculationTests(unittest.TestCase):
    def test_empty_assumptions_and_scenarios_are_never_prefilled(self):
        result = calculate_valuation(simple_snapshot())
        self.assertEqual(result["current_model"]["reason_code"], "pe_assumptions_required")
        self.assertEqual(result["scenarios"], [])
        self.assertIsNone(result["forward_pe"])

    def test_closed_interval_boundaries_and_manual_origin(self):
        for price, classification in ((79.99, "below"), (80, "within"), (100, "within"), (120, "within"), (120.01, "above")):
            with self.subTest(price=price):
                model = calculate_valuation(simple_snapshot(price), {"low": 16, "mid": 20, "high": 24})["current_model"]
                self.assertEqual(model["classification"], classification)
                self.assertEqual(model["origin"], "user_assumption")

    def test_manual_inputs_reject_empty_nonfinite_nonpositive_and_unsorted(self):
        for values in ({}, {"low": 30, "mid": 20, "high": 10}, *({"low": x, "mid": 20, "high": 24} for x in (None, "", True, 0, -1, float("nan"), float("inf"), 10001))):
            with self.subTest(values=values), self.assertRaises(ValueError):
                calculate_valuation(simple_snapshot(), values)

    def test_stale_unknown_nonpositive_or_unsupported_data_blocks_even_manual_classification(self):
        items = [simple_snapshot(freshness="stale"), simple_snapshot(freshness="unknown"),
                 simple_snapshot(eps=0), simple_snapshot(eps=-5), simple_snapshot(price=None)]
        unsupported = simple_snapshot()
        unsupported["identity"]["ordinary"] = False
        items.append(unsupported)
        for data in items:
            with self.subTest(data=data):
                self.assertEqual(calculate_valuation(data, {"low": 16, "mid": 20, "high": 24})["current_model"]["status"], "unavailable")

    def test_data_ineligibility_reason_takes_priority_over_missing_pe_assumptions(self):
        # A PE-input invitation is misleading when entering PE cannot enable valuation.
        for data in (simple_snapshot(freshness="stale"), simple_snapshot(freshness="unknown"), simple_snapshot(eps=None)):
            with self.subTest(data=data):
                model = calculate_valuation(data)["current_model"]
                self.assertEqual(model["status"], "unavailable")
                self.assertNotEqual(model["reason_code"], "pe_assumptions_required")

    def test_three_scenarios_and_forward_pe_are_separate_from_exit_multiple(self):
        result = calculate_valuation(simple_snapshot(), scenarios=[{"eps": 4, "pe": 15}, {"eps": 5.5, "pe": 20}, {"eps": 7, "pe": 25}])
        self.assertEqual([r["price"] for r in result["scenarios"]], [60, 110, 175])
        for row, expected in zip(result["scenarios"], (-40, 10, 75)):
            self.assertAlmostEqual(row["price_change_pct"], expected)
            self.assertEqual(row["origin"], "user_assumption")
        self.assertAlmostEqual(result["forward_pe"], 100 / 5.5)
        self.assertNotEqual(result["forward_pe"], 20)

    def test_scenario_length_invalid_values_and_inverted_prices_rejected(self):
        cases = [[], [{"eps": 1, "pe": 10}], [{"eps": e, "pe": 10} for e in (3, 2, 1)]]
        for value in (None, "", False, 0, -1, float("nan"), float("inf"), 1e7):
            cases.append([{"eps": value, "pe": 10}] * 3)
        for rows in cases:
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                calculate_valuation(simple_snapshot(), scenarios=rows)

    def test_finite_inputs_overflow_results_still_produce_valid_json(self):
        result = calculate_valuation(simple_snapshot(eps=1e308), {"low": 100, "mid": 200, "high": 300})
        self.assertEqual(result["current_model"]["reason_code"], "nonfinite_calculation")
        rows = [{"eps": 1e6, "pe": 10000}] * 3
        tiny = calculate_valuation(simple_snapshot(price=1e-308), scenarios=rows)
        self.assertTrue(all(row["price_change_pct"] is None for row in tiny["scenarios"]))
        large = calculate_valuation(simple_snapshot(price=1e308), scenarios=[{"eps": 1e-308, "pe": 1}] * 3)
        self.assertIsNone(large["forward_pe"])
        json.dumps([result, tiny, large], allow_nan=False)


class ProviderFixtureTests(unittest.TestCase):
    def service(self, data=None, yahoo=None, now=None, loader=None, exception_calendar=None):
        source = datasets() if data is None else data
        svc = ValuationService(json_loader=loader or (lambda url: copy.deepcopy(source[url])),
                               yahoo_loader=yahoo or (lambda _symbol: quarters()), now=now or (lambda: NOW),
                               exception_calendar=exception_calendar)
        self.addCleanup(svc._executor.shutdown, wait=True)
        return svc

    def test_listed_snapshot_keeps_source_dates_ytd_and_official_pe_independent(self):
        result = self.service().snapshot("2330")
        data = result["data"]
        self.assertEqual(data["identity"]["ticker"], "2330.TW")
        self.assertTrue(data["identity"]["ordinary"])
        self.assertEqual(data["quote"]["kind"], "close")
        self.assertEqual(data["quote"]["as_of"], "2026-10-23")
        self.assertEqual(data["quote"]["freshness"], "fresh")
        self.assertEqual(data["official_pe"]["value"], 22)
        self.assertAlmostEqual(data["calculated_pe"], 100 / 18)
        self.assertEqual(data["official_ytd_eps"]["value"], 49.33)
        self.assertEqual(data["official_ytd_eps"]["period_end"], "2026-06-30")
        self.assertEqual(data["official_ytd_eps"]["exported_at"], "2026-10-26")
        self.assertIsNone(data["official_ytd_eps"]["published_at"])
        self.assertNotEqual(data["eps_ttm"]["value"], 49.33)
        self.assertIn("vendor_trailing_eps_differs", data["eps_ttm"]["warnings"])
        self.assertEqual(data["scenarios"], [])
        self.assertEqual(data["horizon_end"], "2027-10-26")
        self.assertEqual(data["eps_period_end"], "2027-10-25")
        json.dumps(result, allow_nan=False)

    def test_otc_year_alias_ytd_shape_and_profile_resolution(self):
        data = datasets("TWO", "6488")
        result = self.service(data).snapshot("6488.TW")["data"]
        self.assertEqual(result["identity"]["ticker"], "6488.TWO")
        self.assertEqual(result["official_ytd_eps"]["value"], 11.87)
        self.assertEqual(result["official_ytd_eps"]["period_start"], "2026-01-01")
        self.assertEqual(result["official_ytd_eps"]["period_end"], "2026-06-30")
        self.assertIsNone(result["official_ytd_eps"]["published_at"])

    def test_snapshot_exposes_exception_calendar_proof_for_listed_and_otc(self):
        for market, code in (("TW", "2330"), ("TWO", "6488")):
            fixtures = datasets(market, code)
            fixtures[OFFICIAL[market]["quote"]][0]["Date"] = "1151022"
            for row in fixtures[OFFICIAL[market]["pe"]]:
                row["Date"] = "1151022"
            data = self.service(fixtures, exception_calendar=load_calendar_exceptions).snapshot(code)["data"]
            self.assertEqual(data["quote"]["freshness"], "fresh")
            self.assertEqual(data["quote"]["calendar_evidence"]["expected_completed_trading_day"], "2026-10-22")
            self.assertEqual(data["quote"]["calendar_evidence"]["exception_version"], load_calendar_exceptions()["version"])
            self.assertEqual(data["current_model"]["status"], "available")

    def test_missing_quarters_preserves_ytd_and_vendor_reference_but_not_estimation(self):
        payload = quarters()
        payload["quarters"] = []
        data = self.service(yahoo=lambda _symbol: payload).snapshot("2330")["data"]
        self.assertIsNone(data["eps_ttm"]["value"])
        self.assertEqual(data["vendor_ttm_eps"]["value"], 99)
        self.assertEqual(data["official_ytd_eps"]["value"], 49.33)
        self.assertIsNone(data["calculated_pe"])
        self.assertEqual(data["current_model"]["status"], "unavailable")

    def test_stale_and_unknown_price_dates_disable_automatic_and_manual_current_models(self):
        for mode in ("stale", "unknown"):
            fixtures = datasets()
            if mode == "stale":
                fixtures[OFFICIAL["TW"]["quote"]][0]["Date"] = "1151022"
            else:
                fixtures[TWSE_HOLIDAY_URL] = []
            data = self.service(fixtures).snapshot("2330")["data"]
            self.assertEqual(data["quote"]["freshness"], mode)
            self.assertEqual(data["current_model"]["status"], "unavailable")
            self.assertEqual(calculate_valuation(data, {"low": 10, "mid": 20, "high": 30})["current_model"]["status"], "unavailable")

    def test_unsupported_security_never_fetches_yahoo_or_classifies(self):
        for code, company in (("0050", None), ("9105", profile("9105", "91")), ("2882A", profile("2882A"))):
            fixtures = datasets(code=code)
            fixtures[OFFICIAL["TW"]["companies"]] = [] if company is None else [company]
            calls = []
            svc = self.service(fixtures, yahoo=lambda symbol: calls.append(symbol))
            data = svc.snapshot(code)["data"]
            self.assertFalse(data["identity"]["ordinary"])
            self.assertEqual(calls, [])
            self.assertEqual(data["current_model"]["status"], "unavailable")

    def test_quote_currency_must_be_independently_confirmed(self):
        payload = quarters()
        payload["quote_currency"] = "USD"
        data = self.service(yahoo=lambda _symbol: payload).snapshot("2330")["data"]
        self.assertEqual(data["eps_ttm"]["reason_code"], "quote_currency_unverified")

    def test_failing_one_source_is_partial_and_all_fail_is_unavailable(self):
        fixtures = datasets()
        def one_failure(url):
            if url == OFFICIAL["TW"]["eps"]:
                raise RuntimeError("private upstream fixture")
            return copy.deepcopy(fixtures[url])
        partial = self.service(loader=one_failure).snapshot("2330")
        self.assertEqual(partial["status"], "partial")
        self.assertEqual(partial["data"]["quote"]["value"], 100)
        self.assertIsNone(partial["data"]["official_ytd_eps"]["value"])
        def failure(_url):
            raise RuntimeError("private upstream fixture")
        failed = self.service(loader=failure).snapshot("2330")
        self.assertEqual(failed["status"], "unavailable")
        self.assertNotIn("private upstream fixture", json.dumps(failed))

    def test_cache_refresh_does_not_turn_source_date_into_fetch_date(self):
        fixtures, calls, clock = datasets(), [], [NOW]
        def loader(url):
            calls.append(url)
            return copy.deepcopy(fixtures[url])
        svc = self.service(loader=loader, now=lambda: clock[0])
        first = svc.snapshot("2330")
        clock[0] += timedelta(minutes=1)
        second = svc.snapshot("2330")
        self.assertEqual(len(calls), 9)
        self.assertEqual(first["data"]["quote"]["fetched_at"], second["data"]["quote"]["fetched_at"])
        self.assertEqual(second["data"]["quote"]["as_of"], "2026-10-23")

    def test_single_flight_ttl_and_caller_deadline_are_bounded(self):
        svc = self.service()
        started, release = threading.Event(), threading.Event()
        calls = []
        def slow():
            calls.append(1)
            started.set()
            release.wait(1)
            return {"as_of": "2026-10-23"}
        with patch("valuation_service.time.monotonic", return_value=100) as clock:
            first, _ = svc._start("isolated-fixture", 10, slow)
            self.assertTrue(started.wait(.5))
            second, _ = svc._start("isolated-fixture", 10, slow)
            self.assertIs(first, second)
            release.set()
            first.result(timeout=1)
            _, cached = svc._start("isolated-fixture", 10, slow)
            self.assertIsNotNone(cached)
            clock.return_value = 111
            refreshed, _ = svc._start("isolated-fixture", 10, slow)
            refreshed.result(timeout=1)
        self.assertEqual(len(calls), 2)
        slow_service = self.service(loader=lambda _url: (time.sleep(.15) or []))
        start = time.monotonic()
        result = slow_service.snapshot("2330", deadline_seconds=.02)
        self.assertLess(time.monotonic() - start, .12)
        self.assertEqual(result["status"], "unavailable")

    def test_public_fetch_transport_has_an_explicit_timeout_and_validates_shape(self):
        response = unittest.mock.Mock()
        response.json.return_value = {"not": "rows"}
        with patch("valuation_service.requests.get", return_value=response) as get:
            with self.assertRaises(ValueError):
                ValuationService._json("https://example.invalid/public-fixture")
            self.assertEqual(get.call_args.kwargs["timeout"], (2, 5))


if __name__ == "__main__":
    unittest.main()

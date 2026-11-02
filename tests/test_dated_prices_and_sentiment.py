"""Offline integration contracts for dated prices and weighted market mood."""
import ast
import asyncio
import copy
import json
import math
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from sentiment_service import (normalize_vix, parse_vix, select_news,
    validate_news_scores, compose, unavailable, SentimentService, VIX_URL)
from valuation_service import dated_twse_rows, ValuationService, OFFICIAL, TAIPEI, TWSE_HOLIDAY_URL
from test_valuation_service import datasets, quarters, HOLIDAYS

NOW = datetime(2026, 10, 31, 3, tzinfo=timezone.utc)
PRICE_NOW = datetime(2026, 10, 30, 2, tzinfo=TAIPEI)
CSV = "DATE,OPEN,HIGH,LOW,CLOSE\n10/29/2026,17,20,16,17.2\n10/30/2026,18,24,18,19.42\n"

def news_row(title="Market", age=1, link="https://example.invalid/a"):
    return dict(title=title, summary="summary", source="fixture", link=link,
                published_ts=(NOW-timedelta(hours=age)).timestamp())

def dated_report():
    fields = ["\u8b49\u5238\u4ee3\u865f", "\u8b49\u5238\u540d\u7a31", "\u6536\u76e4\u50f9", "\u672c\u76ca\u6bd4"]
    return dict(stat="OK", date="20261029", tables=[
        dict(fields=["index"], data=[["unrelated"]]),
        dict(title="115\u5e7410\u670829\u65e5 \u6bcf\u65e5\u6536\u76e4\u884c\u60c5", fields=fields,
             data=[["2330", "fixture", "2,415.00", "27.99"]] +
             [[str(2301+i), "peer", "100", str(10+5*i)] for i in range(6)])])

class DatedSourceTests(unittest.TestCase):
    def test_headers_and_tables_can_be_reordered_without_positional_assumptions(self):
        report = dated_report()
        table = report["tables"][1]
        table["fields"].reverse()
        table["data"] = [list(reversed(row)) for row in table["data"]]
        report["tables"].reverse()
        row = dated_twse_rows(report, "2026-10-29")[0]
        self.assertEqual((row["ClosingPrice"], row["PEratio"], row["Date"]), (2415, 27.99, "2026-10-29"))

    def test_dated_report_crosses_month_without_reusing_october_rows(self):
        report = dated_report()
        report["date"] = "20261102"
        report["tables"][1]["title"] = "115\u5e7411\u67082\u65e5 \u6bcf\u65e5\u6536\u76e4\u884c\u60c5"
        rows = dated_twse_rows(report, "2026-11-02")
        self.assertTrue(all(row["Date"] == "2026-11-02" for row in rows))
        with self.assertRaises(ValueError):
            dated_twse_rows(report, "2026-10-29")

    def test_echoed_response_date_cannot_override_actual_title_date(self):
        for kind in ("title", "date", "stat", "duplicate_table", "duplicate_code", "bad_width", "empty", "duplicate_header"):
            report = dated_report()
            table = report["tables"][1]
            if kind == "title": table["title"] = "115\u5e7410\u670828\u65e5 \u6bcf\u65e5\u6536\u76e4\u884c\u60c5"
            elif kind == "date": report["date"] = "20261028"
            elif kind == "stat": report["stat"] = "no data"
            elif kind == "duplicate_table": report["tables"].append(copy.deepcopy(table))
            elif kind == "duplicate_code": table["data"].append(table["data"][0][:])
            elif kind == "bad_width": table["data"][0].pop()
            elif kind == "empty": table["data"] = []
            else: table["fields"].append(table["fields"][0])
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                dated_twse_rows(report, "2026-10-29")

    def service(self, dated=None, data=None, clock=PRICE_NOW):
        data = copy.deepcopy(data or datasets())
        svc = ValuationService(json_loader=lambda url: copy.deepcopy(data[url]),
            yahoo_loader=lambda symbol: quarters(), now=lambda: clock,
            dated_loader=dated or (lambda url: dated_report()))
        self.addCleanup(svc._executor.shutdown, wait=True)
        return svc

    def test_stale_bulk_recovers_whole_same_date_market_and_real_provenance(self):
        calls = []
        svc = self.service(dated=lambda url: calls.append(url) or dated_report())
        result = svc.snapshot("2330")["data"]
        self.assertEqual(result["quote"]["value"], 2415)
        self.assertEqual(result["quote"]["freshness"], "fresh")
        self.assertEqual(result["official_pe"]["value"], 27.99)
        self.assertEqual(result["peer_reference"]["count"], 6)
        self.assertEqual(result["current_model"]["status"], "available")
        for section in ("quote", "official_pe", "peer_reference"):
            self.assertEqual(result[section]["as_of"], "2026-10-29")
            self.assertIn("MI_INDEX?", result[section]["source_url"])
            self.assertIsNotNone(result[section]["fetched_at"])
        svc.snapshot("2301")
        self.assertEqual(len(calls), 1, "dated market download must be shared across stocks")

    def test_failed_absent_or_nonpositive_target_preserves_stale_quote(self):
        for kind in ("raise", "absent", "zero", "future"):
            report = dated_report()
            if kind == "absent": report["tables"][1]["data"].pop(0)
            elif kind == "zero": report["tables"][1]["data"][0][2] = "0"
            elif kind == "future": report["date"] = "20261030"
            def loader(url):
                if kind == "raise": raise RuntimeError("fixture offline")
                return report
            with self.subTest(kind=kind):
                r = self.service(dated=loader).snapshot("2330")["data"]
                self.assertEqual(r["quote"]["value"], 100)
                self.assertEqual(r["quote"]["freshness"], "stale")
                self.assertEqual(r["current_model"]["reason_code"], "quote_stale")

    def test_missing_pe_does_not_discard_valid_latest_quote_or_fabricate_pe(self):
        report = dated_report()
        report["tables"][1]["data"][0][3] = "--"
        r = self.service(dated=lambda url: report).snapshot("2330")["data"]
        self.assertEqual(r["quote"]["value"], 2415)
        self.assertIsNone(r["official_pe"]["value"])
        self.assertEqual(r["peer_reference"]["status"], "available")

    def test_unknown_calendar_fresh_primary_and_otc_never_download_fallback(self):
        for mode in ("unknown", "fresh", "otc"):
            data = datasets("TWO", "6488") if mode == "otc" else datasets()
            if mode == "unknown": data[TWSE_HOLIDAY_URL] = []
            if mode == "fresh": data[OFFICIAL["TW"]["quote"]][0]["Date"] = "1151029"
            calls = []
            self.service(dated=lambda url: calls.append(url) or dated_report(), data=data).snapshot("6488" if mode == "otc" else "2330")
            self.assertEqual(calls, [], mode)

    def test_slow_dated_source_respects_caller_deadline(self):
        release = threading.Event()
        svc = self.service(dated=lambda url: release.wait(2) or dated_report())
        start = time.monotonic()
        try:
            result = svc.snapshot("2330", deadline_seconds=.05)
            self.assertLess(time.monotonic()-start, .5)
            self.assertIn(result["data"]["quote"]["freshness"], ("stale", "unknown"))
        finally: release.set()

class SentimentMathTests(unittest.TestCase):
    def test_mapping_interpolation_clamp_direction_and_reject_invalid(self):
        for raw, expected in ((1,100),(10,100),(12.5,87.5),(15,75),(19.42,52.9),(20,50),(25,37.5),(30,25),(40,0),(100,0)):
            self.assertAlmostEqual(normalize_vix(raw), expected)
        points = [normalize_vix(i) for i in range(1, 101)]
        self.assertEqual(points, sorted(points, reverse=True))
        for bad in (0,-1,None,True,float("nan"),float("inf"),"bad"):
            with self.subTest(bad=bad), self.assertRaises(ValueError): normalize_vix(bad)

    def test_fixed_weights_half_up_and_label_do_not_reuse_news_advice(self):
        r = compose(dict(status="available",score=50.625), dict(status="available",score=50), NOW)
        self.assertEqual(r["score"], 51)
        self.assertEqual(r["weights"], dict(vix=.8,news=.2))
        self.assertEqual(r["contributions"], dict(vix=40.5,news=10))
        self.assertEqual(r["recommendations"], [])
        self.assertEqual(compose(dict(status="available",score=100),dict(status="available",score=0),NOW)["score"],80)
        self.assertEqual(compose(dict(status="available",score=0),dict(status="available",score=100),NOW)["score"],20)

    def test_missing_component_is_null_not_neutral_or_reweighted(self):
        for v,n in ((unavailable("x"),dict(status="available",score=90)),(dict(status="available",score=90),unavailable("x"))):
            r = compose(v,n,NOW)
            self.assertIsNone(r["score"])
            self.assertEqual(r["label"], "\u8cc7\u6599\u4e0d\u8db3")
            self.assertEqual(r["contributions"],dict(vix=None,news=None))
            json.dumps(r, allow_nan=False)
        for bad in (True,101,-1,float("nan"),"50"):
            with self.assertRaises(ValueError): compose(dict(status="available",score=bad),dict(status="available",score=50),NOW)

class VixSourceTests(unittest.TestCase):
    def test_latest_completed_ny_date_and_daily_provenance(self):
        r = parse_vix(CSV,NOW)
        self.assertEqual((r["raw_value"],r["as_of"],r["kind"]),(19.42,"2026-10-30","daily_close"))
        self.assertEqual(r["source_url"],VIX_URL)
        before = datetime(2026,10,30,19, tzinfo=timezone.utc)
        self.assertEqual(parse_vix(CSV,before)["as_of"],"2026-10-29")
        boundary = datetime(2026,10,30,20,15,tzinfo=timezone.utc)
        self.assertEqual(parse_vix(CSV,boundary)["as_of"],"2026-10-30")

    def test_stale_future_conflicting_dates_and_payload_bounds(self):
        header = CSV.splitlines()[0] + "\n"
        cases = [header, header+"11/04/2026,1,1,1,20\n",
                 header+"10/20/2026,1,1,1,20\n",
                 CSV+"10/30/2026,1,1,1,21\n", "DATE,CLOSE\n10/30/2026,20\n", "x"*(2*1024*1024+1)]
        for text in cases:
            with self.subTest(prefix=text[:60]), self.assertRaises(ValueError): parse_vix(text,NOW)
        self.assertEqual(parse_vix(CSV,datetime(2026,11,3,22,tzinfo=timezone.utc))["as_of"],"2026-10-30")
        with self.assertRaises(ValueError): parse_vix(CSV,datetime(2026,11,4,22,tzinfo=timezone.utc))

    def test_stream_is_bounded_and_has_transport_timeout(self):
        response = SimpleNamespace(raise_for_status=lambda:None,iter_content=lambda size:iter([b"x"*(2*1024*1024+1)]))
        class Context:
            def __enter__(self): return response
            def __exit__(self,*args): pass
        with patch("sentiment_service.requests.get", return_value=Context()) as get:
            with self.assertRaises(ValueError): SentimentService._vix()
            self.assertTrue(get.call_args.kwargs["stream"])
            self.assertEqual(get.call_args.kwargs["timeout"],(2,5))

class NewsTests(unittest.TestCase):
    def test_window_actual_dates_dedup_order_and_bound(self):
        rows = [news_row("same",2),news_row("SAME",1,"https://example.invalid/b"),news_row("duplicate link",3),
                news_row("old",73,"o"),news_row("future",-1,"f"),dict(title="no date",fetched_at=NOW.isoformat())]
        selected = select_news(rows,NOW)
        self.assertEqual([r["title"] for r in selected],["SAME","duplicate link"])
        self.assertEqual([r["id"] for r in selected],[0,1])
        self.assertTrue(all(r["published_at"].endswith("+00:00") for r in selected))
        self.assertEqual(len(select_news([news_row(str(i),i,"url"+str(i)) for i in range(10)],NOW)),5)
        self.assertEqual(len(select_news([news_row(age=72)],NOW)),1)
        with self.assertRaises(ValueError): select_news([{}]*501,NOW)

    def test_all_scored_ids_required_exactly_once_and_numbers_strict(self):
        articles = select_news([news_row("a",1,"a"),news_row("b",2,"b")],NOW)
        score, analyses = validate_news_scores({"articles":[{"id":1,"score":80},{"id":0,"score":20}]},articles)
        self.assertEqual(score,50)
        self.assertEqual([r["id"] for r in analyses],[0,1])
        for payload in ({},{"articles":[]},{"articles":[{"id":0,"score":50}]*2},
                        {"articles":[{"id":0,"score":50},{"id":2,"score":50}]}):
            with self.assertRaises(ValueError): validate_news_scores(payload,articles)
        for bad in ("50",True,None,float("nan"),float("inf"),-1,101):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                validate_news_scores({"articles":[{"id":0,"score":bad},{"id":1,"score":50}]},articles)

class SentimentIntegrationTests(unittest.TestCase):
    def service(self, **kwargs):
        svc = SentimentService(vix_loader=kwargs.get("vix",lambda:CSV),
            news_loader=kwargs.get("news",lambda:[news_row()]),
            news_scorer=kwargs.get("scorer",lambda rows:{"articles":[dict(id=r["id"],score=70) for r in rows]}),
            now=lambda:NOW)
        self.addCleanup(svc._pool.shutdown,wait=True)
        return svc

    def test_snapshot_one_batch_cache_deepcopy_and_fixed_aggregate(self):
        calls = []
        svc = self.service(scorer=lambda rows:calls.append(rows) or {"articles":[dict(id=r["id"],score=70) for r in rows]})
        result = svc.snapshot()
        self.assertEqual(result["score"],56)
        self.assertEqual(len(calls),1)
        result["components"]["vix"]["score"] = -999
        self.assertAlmostEqual(svc.snapshot()["components"]["vix"]["score"],52.9)
        self.assertEqual(len(calls),1)

    def test_no_news_and_ai_error_or_malformed_scores_never_make_fake_aggregate(self):
        for mode in ("none","fail","bad"):
            def scorer(rows):
                if mode=="fail": raise RuntimeError("offline AI failure")
                return {"articles":[]}
            svc = self.service(news=(lambda:[]) if mode=="none" else (lambda:[news_row()]),scorer=scorer)
            r = svc.snapshot()
            self.assertIsNone(r["score"])
            self.assertEqual(r["components"]["vix"]["status"],"available")
            self.assertIsNone(r["components"]["news"]["score"])
            self.assertEqual(r["components"]["news"]["scored_count"],0)

    def test_concurrent_timeout_then_completion_shares_one_flight(self):
        release = threading.Event()
        calls = []
        def slow(): calls.append(1); release.wait(2); return CSV
        svc = self.service(vix=slow)
        try:
            a = svc.snapshot(.02); b = svc.snapshot(.02)
            self.assertIsNone(a["score"]); self.assertIsNone(b["score"])
            self.assertEqual(calls,[1])
        finally: release.set()
        for _ in range(100):
            if svc._future is None: break
            time.sleep(.005)
        self.assertEqual(svc.snapshot()["status"],"available")
        self.assertEqual(calls,[1])

    def test_response_model_and_actual_endpoint_keep_components_and_null(self):
        from models import SentimentResponse
        tree = ast.parse(Path("main.py").read_text(encoding="utf-8"))
        node = next(n for n in tree.body if isinstance(n,ast.AsyncFunctionDef) and n.name=="get_sentiment")
        node.decorator_list = []
        payload = compose(dict(status="available",score=52.9,raw_value=19.42,as_of="2026-10-30"),unavailable("news_missing"),NOW)
        ns = dict(asyncio=asyncio,sentiment_service=SimpleNamespace(snapshot=lambda:payload))
        exec(compile(ast.Module(body=[node],type_ignores=[]),"main.py","exec"),ns)
        result = asyncio.run(ns["get_sentiment"]())
        dumped = SentimentResponse.model_validate(result).model_dump()
        self.assertIsNone(dumped["score"])
        self.assertEqual(dumped["weights"],{"vix":.8,"news":.2})
        self.assertEqual(dumped["components"]["vix"]["raw_value"],19.42)
        self.assertEqual(dumped["components"]["news"]["reason_code"],"news_missing")

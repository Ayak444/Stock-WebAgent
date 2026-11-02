# Agent Handoff: Dated TWSE fallback and 80/20 VIX radar

## Work definition
- Objective: finish interrupted TWSE freshness recovery and replace news-only radar with VIX 80% plus news 20%.
- Baseline: 2ab06c67e4ca0e6d2762302d219def1bb0a0ad21 on codex/price-inspector-release.
- Scope: valuation_service.py dated fallback; focused sentiment service, route/model, existing radar UI; offline tests.
- Excluded: original dirty checkout, notification changes, YouTube/Podcast collection, new Render resources, dependencies, production env/database changes.
- Model: score 0 fear/negative, 100 calm/optimistic. VIX project anchors (10,100),(15,75),(20,50),(30,25),(40,0); linear interpolation and endpoint clamp; aggregate half-up round(0.8*VIXscore+0.2*newsScore).
- Sources: bounded official CBOE daily VIX history CSV (2MB maximum), latest valid dated close, not realtime. Four calendar-day application age limit; reject future dates. Existing financial RSS with 72-hour dated window, dedup and bounded count; at most one AI batch call.
- VIX anchors and availability age are project modelling rules, not official Cboe sentiment or verification of the latest US session. Low VIX does not predict rising Taiwan equities.

## Acceptance criteria
- [x] AC-F01: TWSE fallback only on stale/missing/invalid primary plus verified expected completed date; TPEx unchanged.
- [x] AC-F02: Validate stat, response date, selected daily table actual title date; unique header-based selection.
- [x] AC-F03: Reject malformed/ambiguous/duplicate/missing target/date and invalid prices; missing/nonpositive PE unavailable.
- [x] AC-F04: Whole dated table supplies quote and PE; existing ordinary/industry/count/same-day peer eligibility retained.
- [x] AC-F05: Actual fallback URL/trading date/fetch time appear in quote, official PE and peer provenance.
- [x] AC-F06: Failed fallback retains original stale/unavailable result; no relaxed calendar/EPS/action/product/finite guards.
- [x] AC-F07: Shared deadline, executor, TTL and single-flight; no serial timeouts or per-stock market download repetition.
- [x] AC-F08: Offline success/reorder/date/title/malformed/duplicates/failure/peers/provenance/deadline/cache/TPEx tests.
- [x] AC-S01: Anchor/interpolation/clamp/round/monotonic/finite tests prove documented 80/20 formula.
- [x] AC-S02: Bounded single VIX source/cache; raw value, source date/fetch time and daily/delayed label exposed.
- [x] AC-S03: Four-calendar-day availability policy explicit; future/stale invalid; no US latest-session claim.
- [x] AC-S04: News uses 72h window, dated dedup bounded count, links/timestamps/eligible/scored counts; invalid dates excluded.
- [x] AC-S05: Explicit news direction, at most one AI batch, structured unavailable for AI failure/invalid/fallback.
- [x] AC-S06: Both valid components required; otherwise null aggregate plus reason/available details, never fake50/reweight.
- [x] AC-S07: Response serialization retains weights, normalized scores, contributions, version/method/provenance/null.
- [x] AC-S08: Aggregate labels/explanation derived from score; no conflicting old AI label or buy/sell recommendations.
- [x] AC-S09: UI shows breakdown/formula/dates/reasons, null unavailable, resets old results on loading/failure, safe external text.
- [x] AC-S10: Preserve unrelated sentiment-helper callers; service/API/UI failure/date/dedup/bounds/escaping regressions.
- [x] AC-S11: Full offline quality gate and independent exact-revision review with zero blockers.
- [x] AC-S12: Final committed-version gates precede scoped publication; original checkout/env/db preserved.

## Stage ownership
| Stage | Owner | Status |
| --- | --- | --- |
| Product | /root/combined_supervisor/product | Complete, numbered criteria approved |
| Developer | /root/finish_supervisor/developer | Complete, production frozen |
| Tester | /root/finish_supervisor/tester | Candidate passed; final committed gate next |
| Reviewer | /root/finish_supervisor/reviewer | Candidate passed, zero blockers; final binding next |

## Revision identity
- Baseline/HEAD: 2ab06c67e4ca0e6d2762302d219def1bb0a0ad21.
- Recovered interrupted state: only valuation_service.py modified, no tests/handoff from prior interrupted attempt.
- Source identity: HEAD plus SHA256 staged binary patch, unstaged binary patch and stable all-untracked manifest. Ignore nested submodule dirt only, retain gitlinks.
- Exact candidate/final component hashes and manifests: pending immutable stage messages. A timestamp is not identity.
- Final protocol: finish this handoff, freeze, create scoped local commit; Tester reruns full gate with before/after identity; Reviewer independently binds that same committed HEAD. No edits or new commit afterward.

## Developer handoff
Changed files, syntax commands and limitations pending. Only Developer may write production; only Tester may write tests; Supervisor owns this handoff. One writer at a time.

## Test evidence
Acceptance-to-test matrix and full gate pending. Use dependency-complete TEMP interpreter and sanitized offline runner, never production bootstrap or dotenv.

## Review evidence
Blocking count pending; any blocking finding requires Developer fix -> full Tester regression -> Reviewer re-review on the new identity.

## Manual operations and risks
- Lead owns branch publication, Linux CI, expected-baseline main fast-forward and actual original Render URL verification.
- No production env/database/resource changes or new dependencies required.
- Public feeds may be unavailable or delayed; retain explicit partial states and actual dates.
- Official CBOE daily CSV: https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv . VIX measures S&P500 expected thirty-day volatility; this is an application proxy, not an official Taiwan market sentiment index.
- Original dirty source checkout remains read-only.

## Gate status
- [x] Acceptance gate: approved criteria mapped to passing candidate evidence below
- [x] Test gate: candidate complete offline suite passed; committed rerun required
- [x] Review gate: independent tested candidate review zero blockers; committed binding required
- [x] Manual operations and limitations recorded

## Recovery implementation evidence
- Recovery Supervisor: /root/finish_supervisor. Remote main still baseline2ab06c67 confirmed before work.
- Developer production frozen: main.py, models.py, static/index.html, valuation_service.py and new sentiment_service.py; no test/handoff/original checkout edits.
- Developer checks: four Python AST syntax checks, all inline JavaScript Node syntax, injected offline score fixture (VIX20 ->50; news100 -> aggregate60), Pydantic component preservation and git diff whitespace all pass. These are sanity checks, not the test gate.
- Only Tester may now write test files. Independent full regression and review pending.

## Completed candidate evidence and final freeze
- Production paths: main.py, models.py, static/index.html, valuation_service.py, sentiment_service.py. No other production changes.
- Tester-only additions: tests/test_dated_prices_and_sentiment.py, tests/test_sentiment_ui.py, tests/sentiment_ui_checks.cjs.
- Candidate full gate: 50 Python files compiled, 229 total tests (208 existing plus 21 new), zero failures, one existing Windows sendmsg skip, exit 0; test runtime 9.397 seconds.
- Tester before/after identity and independent Reviewer identity both e21038b872461b87a204f7f336a26537f8487c7f6be827739d27129d2c2fa3ae. Full component hashes/manifests/log/result: C:/Users/Ayak4-PC/AppData/Local/Temp/stock-dated-sentiment-final-candidate-tests/.
- Independent candidate review: correctness, source dates and provenance, finite/shape validation, bounded requests/executors/cache, schema and frontend escaping/reset/races checked; blocking count 0; no nonblocking findings reported.

| Criteria | Passing test evidence |
| --- | --- |
| F01,F04,F05 | Stale bulk recovers whole same-date market and real provenance; same-day peers; fresh primary, TPEx and unknown-calendar controls |
| F02,F03 | Reordered headers/tables, response-date echo versus actual title, malformed/duplicate/target/finite guards, missing PE |
| F06 | Failed, absent or nonpositive target preserves original stale source |
| F07 | Cross-stock date-cache reuse and slow dated source respects caller deadline |
| F08 | All fallback cases plus cross-month fixture and complete existing regression |
| S01 | Anchors/interpolation/clamp/finite/monotonic and fixed 80/20 half-up arithmetic |
| S02,S03 | Bounded CSV transport, latest completed New York close date, four-day application age, future/conflicting-date guards |
| S04 | Actual 72-hour dates, deduplication/order/count bounds; crawler undated published_ts is zero and excluded |
| S05 | Exact selected scoring IDs, one AI batch, no news and AI error/invalid data states |
| S06 | Missing either component yields null aggregate and no silent 50 or weight redistribution |
| S07 | Actual endpoint and response-model serialization preserve components, weights, sources and null |
| S08 | Aggregate-derived labels and empty recommendations; consistent news direction |
| S09,S10 | Actual frontend function VM: weights/contributions/dates, HTML and link escaping, loading/failure/null/zero and late response races |
| S11 | Full quality gate and independent exact-state review, zero blockers |
| S12 | Scoped packaging and immutable committed-version test/review protocol below; publication remains Lead operation |

## Final committed-version protocol
This handoff is now frozen before packaging. Developer may stage and commit only the five production paths, three test paths and this handoff, without altering their content. Tester must run full quality_gate.py on the resulting committed HEAD with independent before/after identity; Reviewer must independently recompute and bind the same final identity. Only their immutable final messages complete the committed-version gate and AC-S12; these checkboxes do not permit publication or completion before that evidence. Do not amend this document after packaging; a new commit invalidates later-stage evidence.

## Operational limits
- VIX uses the most recent accepted official daily close, not a realtime quote or certified latest US session. Four calendar days is an application availability threshold. Project anchors are not an official Cboe fear/greed index.
- News must have actual publication dates within 72 hours and a validated one-batch AI result. Missing either source produces a null aggregate, with available components and reasons visible.
- Dated TWSE backup validates the actual table title date, source response date and verified calendar expected day. Failed backup retains the stale primary state. TPEx provider unchanged.
- No new dependency, production environment variable, database migration or Render resource is required. No credentials, dotenv or production bootstrap were used in tests. Original dirty source remains read-only.
- Lead publishes this exact commit to the release branch, waits for Linux CI, advances main only with expected baseline lease, then verifies the actual original Render URL, health, valuation dates and radar response/UI. No role agent has pushed or deployed.

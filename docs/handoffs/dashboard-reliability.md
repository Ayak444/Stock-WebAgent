# Agent Handoff: dashboard reliability

## Work definition

- Objective: Fix the five reported dashboard availability and input usability problems.
- In scope: Reported calendar, private notification reads, industry/news coverage, technical/backtest latency and cost input usability; primary-host documentation.
- Out of scope: Live database schema/ACL changes, secret changes, exhaustive market calendar or ETF tax inference, broad strategy development.
- Assumptions: Primary service is ayak4-trading-strategy-bot-l4oa.onrender.com. Existing project has the private notification tables; the effective deployed credentials still require user-side confirmation.
- Dependencies: Official TWSE/TPEx/TDCC and available RSS feeds; backend Supabase credentials and corresponding Render service deployment.

## Acceptance criteria

- [x] AC-01: Official upcoming ex-dividend and market holiday calendar, Taipei date filtering, source links, honest unavailable state.
- [x] AC-02: Account-owned encrypted alert settings retain privacy; bounded transient read recovery and safe actionable diagnostics; no blanket migration rerun.
- [x] AC-03: Healthy official industry rows generate ranking without silently mixing trading dates; explicit coverage; ETF comparison is neutral not-applicable.
- [x] AC-04: Working RSS fallback and unique published recent 72-hour news; exclude stale/future/unverified timestamps; honest partial/empty coverage.
- [x] AC-05: Same-origin analysis/backtest reads support bounded cold-start timeout and retryable UI; no cross-host or mutation retries; quick technical analysis survives AI failure.
- [x] AC-06: Explicit percent fee/tax inputs converted once, defaults 0.1425%/0.3%/20 TWD, reset button and specific finite/range validation. UI percent rates 0..10 inclusive; minimum 0..100000. This guard is not a statutory rate limit; backend fractional-rate contract is unchanged.
- [x] AC-07: Offline regression and targeted criteria pass quality_gate; exact identity review has zero blockers; manual steps documented.

## Stage ownership

| Stage | Owner | Status | Started | Completed | Notes |
| --- | --- | --- | --- | --- | --- |
| Product | /root/dashboard_fix_supervisor/product | Complete |  |  |  |
| Developer | /root/dashboard_fix_supervisor/developer; /root authorized fixes | Complete |  |  | Lead fixed bounded retry propagation, synchronous SDK options, partial RSS, safe DOM writes, cost validation and news independent of price availability. |
| Tester | /root (explicit user override) | Pass: 133 tests, one platform skip |  |  | Full offline gate plus real browser helpers in Node with fake DOM/network. |
| Reviewer | /root (explicit user override) | Pass: zero blocking issues |  |  | Same Lead performs both stages under the explicit task-specific exception; not an independent review. |

## Explicit user workflow override

The user explicitly authorized this task only: 這次由主管理 Agent 完成測試與審查後發佈（建議，最快）. New Tester and completed Product/Reviewer follow-up dispatches were rejected by the tool with agent thread limit reached. Lead /root therefore owns both test and review stages for this exception, independently of the Developer production implementation. Lead may make necessary fixes if the Developer cannot be resumed, and must rerun the relevant gate after fixes. This is an explicit human authorization, not a silent Supervisor self-approval.

## Immutable final evidence protocol

This record contains the final implementation evidence. After committing it, Lead reruns the full gate and recomputes committed HEAD plus staged/unstaged/untracked SHA-256 identities externally. Final tested and reviewed identities must match and be clean before publication. Exact commit and empty-patch hashes are reported in the task tool transcript to avoid a self-referential document hash. The user-authorized Lead performs testing and review; independent-agent review is unavailable for this task.

## Revision identity

- Baseline commit: 43f735a
- Developer HEAD commit: 43f735aec3a7effdcba728d39d7d4577f6ca9985 (before Lead commit)
- Staged patch SHA-256: Final clean-state value recorded in tool transcript.
- Unstaged patch SHA-256: Final clean-state value recorded in tool transcript.
- Untracked files and content SHA-256 manifest: Final empty manifest recorded in tool transcript.
- Tested source-state ID (HEAD plus all three hashes): Final committed identity recorded in tool transcript.
- Reviewed source-state ID (HEAD plus all three hashes): Same committed identity; recomputed after final gate in tool transcript.
- Shared-workspace writer: Developer owns production files and this handoff until freeze. Lead owns the user-authorized test/review exception and will supply exact final revision evidence. Hash evidence is supplied outside this document to avoid a self-referential manifest.

The staged hash covers `git diff --cached --binary`, and the unstaged hash covers `git diff --binary`. The untracked manifest lists every untracked path and its content hash in stable path order, then records the manifest hash. Empty patches still receive the SHA-256 of empty content. Do not use a timestamp as source identity. Tester and Reviewer must independently recompute the source-state ID; both IDs must match the Developer handoff state.

## Developer handoff

### Changed files

| File | Purpose |
| --- | --- |
| market_insights.py | Official Taipei calendar, single-date coverage, recent valid unique news, bounded overview resource fan-out and cache wait. |
| news_crawler.py | Google Taiwan news aggregation fallback, parallel bounded fetch-all, recent unique timestamp filtering and Taipei publication display. |
| database.py | Eight-second Data API timeout, safe categorized errors/key-type labels and one transient settings read retry; no write retries. |
| main.py | Calendar/overview APIs, safe alert diagnostics, bounded analysis/backtest waits and best-effort background history persistence. |
| market_routing.py | Three concurrent official monthly technical history requests and bounded Yahoo/TWSE source attempts. |
| static/index.html | Official calendar rendering, coverage explanations, neutral ETF comparison, percent fee/tax input with reset and precise validation, loading/manual retry states. |
| README.md / MANUAL_SETUP.md | Primary host links and conditional safe credential/schema/network troubleshooting, limits and manual operations. |
| tests/test_dashboard_reliability.py / tests/dashboard_browser_checks.js | Ten focused regressions for reported dashboard contracts, actual browser syntax/retries/fee conversion and SDK construction without networking. |
| tests/test_market_insights.py / tests/test_notification_ai_diagnostics.py | Valid publication timestamps and inclusion of new safe diagnostic helper in existing test harness. |

### Commands and results

| Command | Exit code | Result |
| --- | ---: | --- |
| RTK file reads, searches and apply_patch | 0 | Source edits applied; no .env/production credentials read. |
| Temporary Python syntax command | 1 | Existing temp venv could not start its Python312 base executable. Tester/Lead must resolve runtime before quality gate. |
| Same syntax command with approved elevated runtime access | 0 | AST parsing passed for all five edited Python modules. Default sandbox could not access base runtime; no runtime installation required. |
| git diff --check | 0 | Preserved existing mixed line endings; no newly introduced whitespace defects. |
| python scripts/quality_gate.py | 0 | 38 Python files compile; 133 tests pass, one Windows sendmsg capability skip. Node browser check runs without network. Final committed revision is rechecked before push. |

### Known limitations

- Upstream feeds and official sources remain subject to outages. Calendar contains listed ex-dividend announcements and market holidays only, not all investor events.
- Equal-weight industry ranking excludes a market when its trading date differs; ETF comparison is not applicable.
- Background analysis history saving is best effort; computation response does not wait for the database. Free Render cold starts can still require explicit repeat execution after bounded waiting.
- No user data, webhook delivery or production writes were used for tests. Live notification functionality remains conditional on effective primary Render credentials; offline passing evidence is not a live delivery guarantee.

## Test evidence

| Acceptance criterion | Test case or check | Result | Evidence |
| --- | --- | --- | --- |
| AC-01 | test_calendar_uses_taipei_day_and_excludes_trading_markers; calendar implementation review | Pass | ROC dates, UTC-to-Taipei boundary, invalid/past exclusion, official URLs; partial loaders and future-only cache reviewed. |
| AC-02 | test_read_retries_once_but_write_and_permission_failure_do_not; test_sync_supabase_options_construct_without_network; existing notification/volume tests | Pass | Transient read twice, writes once, SQLSTATE precedence, synchronous SDK creation; ownership, encryption, safe errors and private migration regression. |
| AC-03 | test_market_dates_are_not_mixed; existing industry/snapshot tests; neutral ETF UI review | Pass | Excludes older market date, equal-weight output validated, not-applicable content escapes external fields. |
| AC-04 | test_news_excludes_stale_future_undated_and_duplicates; test_slow_feed_does_not_discard_healthy_feed; test_price_outage_does_not_remove_company_names_from_news; existing RSS tests | Pass | Healthy feed survives slow feed; valid recent unique articles; profiles usable independently of prices; timezone stable. |
| AC-05 | test_analysis_timeout_returns_retryable_504; test_analysis_response_survives_history_save_failure; test_actual_browser_helpers_without_network; existing routing/backtest tests | Pass | Server 55-second deadline, best-effort save failure, public GET one retry, private/auth/POST none, quick/deep AI failure fallback. |
| AC-06 | test_actual_browser_helpers_without_network; existing cost backtests; reset/default review | Pass | Real JS single percent conversion; 59.76, blank, negative, nonfinite rejection; configured fractional backend inputs unchanged. |
| AC-07 | full quality_gate; exact committed identity and final diff review | Pass | Final gate and clean tested/reviewed source IDs recorded externally before push; manual operations below. |

### Full regression

- Command: `python scripts/quality_gate.py`
- Exit code: 0
- Summary: 133 tests, one Windows sendmsg skip, 38 compiled files. Initial regressions and discovered SDK/retry issues were fixed and the full gate rerun. Final committed revision is validated again in the task transcript.

## Review evidence

- Correctness: Same-date industry coverage, Taipei calendar, partial resources, bounded retry counter and single cost conversion checked.
- Security: Account ownership, encrypted settings, filtered diagnostics, text/escaped DOM and safe URLs preserved; no production secrets inspected.
- Performance: Shared bounded RSS workers; one transient settings retry; analysis 55-second wait and best-effort saving; official monthly requests limited to three concurrent calls.
- Maintainability: Existing service/API architecture retained; synchronous SDK options use public export; manual operations differentiated from code fixes.
- Blocking-issue count: 0 for this change; final committed identity confirmed externally.
- Non-blocking findings and disposition:

| Severity | File and line | Reason | Blocking | Disposition |
| --- | --- | --- | --- | --- |
| P2 existing deployment | Supabase public.users ACL (live schema, no source line) | Public role SELECT with RLS disabled was observed in read-only schema inspection. | No, pre-existing and outside this change | Remediate separately after correct backend credentials and login are verified; no live ACL change made. |
| P2 operational | MANUAL_SETUP.md:48 | Free Render sleep can miss scheduled checks; upstream outages remain possible. | No | Documented constant-running service/external scheduler requirement and explicit retry limits. |

## Manual operations

- Deploy GitHub latest revision to the Render service serving https://ayak4-trading-strategy-bot-l4oa.onrender.com/ . Save and redeploy environment changes on this exact service.
- For account alerts, use safe `account_volume_store` log category and `credential_kind` to check same-project URL, effective backend credentials, Data API availability and private permissions. Do not blindly rerun migrations or grant public access.
- Only if a schema is confirmed missing should migration be applied after backup. Existing notification tables reportedly exist with service_role grants; no new migration is required by these source edits.
- Separate users-table public-access remediation is documented as a follow-up after backend authentication is verified; no live ACL change made here.

## Risks

- Requests timeouts and best-effort executor cancellations cannot forcibly terminate an already-running Python thread; underlying HTTP calls have finite timeouts. Manual retry does not guarantee upstream availability.
- Secret-key type detection is an allowlisted label, not credential validity or project verification. Raw provider details and key material are not returned.

## Gate status

- [x] Acceptance gate: all implementation criteria pass; live alert delivery still requires configuration verification.
- [x] Test gate: feature tests and full regression pass.
- [x] Review gate: blocking-issue count is zero under the explicit Lead exception.
- [x] Manual deployment, database, and environment steps are documented.

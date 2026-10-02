# Agent Handoff: remaining production safeguards

## Work definition

- Objective: Resolve seven remaining production correctness, privacy and data provenance issues.
- In scope: All AC-01 through AC-08 safeguards in root FastAPI, additive staged SQL, frontend provenance/error states and deployment documentation.
- Out of scope: Live database writes, key changes, real brokerage execution, historical virtual inventory reconstruction, cache-table ACL expansion.
- Assumptions: Existing legacy users/watch portfolios/trades/stress and account-alert tables exist in the intended project. Only trusted backend session owns personal requests.
- Dependencies: Backend service_role permissions; migration stage one RPCs; official TWSE/TPEx data and Yahoo daily macro chart availability.

## Acceptance criteria

- [ ] AC-01: Private portfolio, stress, trade and portfolio screener APIs derive ownership from verified session; missing session401, cross-origin writes403; frontend cookies.
- [ ] AC-02: Additive idempotent private account SQL preserves rows, enables RLS, revokes public table access and grants minimal server access; login/signup remain backend-only.
- [ ] AC-03: Virtual trades atomic NUMERIC transaction with validated action/ticker/amount/price, user-position locks, balance/holdings/history rollback, no overspend/overdraw.
- [ ] AC-04: Private saves return503 on storage failure, validate before writes and retain prior holdings on failure; manually editable watch portfolios cannot mint trade inventory.
- [ ] AC-05: Discord safe static categories distinguish encryption, schema, permission and transient connection with actionable Chinese UI; no webhook/env/user leakage.
- [ ] AC-06: Invalid or missing macro prices/changes are unavailable null with source/asof; frontend dash/reason; singlebar price can exist without change.
- [ ] AC-07: Official dated institutional net buys and provenance in async analysis and chips API; shares internally and lots display; no fake zero/trends.
- [ ] AC-08: AI summary actual timezone-aware generated_at, source news publish range and recent input, dated prompt; server generation time distinct from news dates.
- [ ] AC-09: Targeted regressions and full quality gate pass; zero review blockers exact tested revision; safe manual deployment/SQL/env steps.

## Stage ownership

| Stage | Owner | Status | Started | Completed | Notes |
| --- | --- | --- | --- | --- | --- |
| Product | /root/dashboard_fix_supervisor/product | Complete |   |  |  |
| Developer | /root/dashboard_fix_supervisor/developer | Implementation frozen; gates pending |  |  | Sole production/documentation writer. |
| Tester | /root/dashboard_fix_supervisor/safeguards_tester | Targeted validation passed; formal committed full gate pending |  |  | Tests only after production freeze. |
| Reviewer |  | Not started |  |  |  |

## Immutable final evidence protocol

This handoff is a precommit implementation and targeted-validation snapshot. Final full quality-gate status and Reviewer findings are pending at this capture point and will be delivered as immutable external reports against the same clean committed HEAD. Lead commits this file with source/tests, then Tester recomputes identity and runs full quality_gate; Reviewer independently reviews that exact passing revision. No later handoff edit is needed or permitted merely to insert its own commit hash. Any source change invalidates downstream gate evidence.

## Revision identity

- Baseline commit: 3ee9838e914bbba20aa230797596f60594db87be
- Developer HEAD commit: 3ee9838e914bbba20aa230797596f60594db87be (precommit baseline)
- Staged patch SHA-256:
- Unstaged patch SHA-256:
- Untracked files and content SHA-256 manifest:
- Tested source-state ID (HEAD plus all three hashes):
- Reviewed source-state ID (HEAD plus all three hashes):
- Shared-workspace writer: Developer through this freeze; Tester owns tests next. Lead will commit source, test additions and this immutable handoff before formal full quality gate and review. Final exact identity is recorded outside this document to avoid self-hash recursion.

The staged hash covers `git diff --cached --binary`, and the unstaged hash covers `git diff --binary`. The untracked manifest lists every untracked path and its content hash in stable path order, then records the manifest hash. Empty patches still receive the SHA-256 of empty content. Do not use a timestamp as source identity. Tester and Reviewer must independently recompute the source-state ID; both IDs must match the Developer handoff state.

## Developer handoff

### Changed files

| File | Purpose |
| --- | --- |
| models.py / main.py / database.py | Session-owned personal endpoints, finite Decimal/schema validation, atomic RPC calls, storage failures surfaced, safe private capability probe and notification diagnostics. |
| account_alert_security.py | Static encryption categories, including invalid/non-ASCII keys and undecipherable stored webhook. |
| supabase/migrations/20261002125008_account_atomic_operations.sql | Separate trusted virtual inventory, atomic watchlist replacement and virtual trade; read-only private capability RPC. CLI-generated, not applied. |
| supabase/migrations/20261002125014_account_access_hardening.sql | Separate second-phase legacy private table RLS/ACL, least privilege grants and fixed existing claim function search path. CLI-generated, not applied. |
| market_provenance.py / data_provider.py / async_data_provider.py / strategy.py | Shared finite macro null/source/date semantics and official institution flow parsing/fetching, source/date/unit metadata and same-date scoring. |
| static/index.html / MANUAL_SETUP.md | Session-cookie clients without UUID authority, save-failure visibility, quote dashes/provenance, share-to-lot conversion, AI generation/news-date display and staged manual deployment. |

### Commands and results

| Command | Exit code | Result |
| --- | ---: | --- |
| Supabase CLI migration new --help (npx pinned2.119.0) | 0 | Discovered scaffolding API. |
| migration new account_atomic_operations / account_access_hardening | 0 | Created the two canonical timestamped files; no database applied. |
| Python AST parse eight edited modules using existing temp runtime, elevated runtime access | 0 | Source syntax passed without imports, credentials or network. |

### Known limitations

- Macro uses Yahoo dated daily chart; missing/invalid/stale source values remain null. Single-bar price has no fabricated daily change.
- Institutional coverage uses ordinary stock/equity ETF code formats; source outage and differing market trading dates are explicit. Only same-day stock history evidence affects scoring. Eight candidate TWSE dates are bounded by an eight-second parallel collector; source transport calls have finite timeouts.
- Virtual trade price is user-specified for simulated bookkeeping. It is not a broker order and does not include transaction costs. Existing ledger/balances are preserved but are not automatically converted into trusted new inventory.
- Lost encryption key requires administrator diagnosis and webhook re-entry; no raw stored URL is returned.
- Targeted Python cases passed (12 new plus 16 existing diagnostics); exact isolated SQL passed 55 assertions. Formal regression remains pending against final committed HEAD. Isolated PGlite can execute SQL but does not prove real multi-connection concurrent contention; SQL locking order is additionally reviewed.

### RPC contracts for downstream validation

- `replace_watch_portfolio(p_user_id UUID, p_items JSONB) RETURNS BOOLEAN`: items code/type/cost/shares, max100, finite nonnegative6-decimal values. Returns true; invalid JSON/account/storage errors roll back all rows.
- `execute_virtual_trade(p_user_id UUID, p_action TEXT, p_ticker TEXT, p_amount NUMERIC, p_price NUMERIC) RETURNS JSONB`: locks user before position. Returns `ok=true`, exact numeric balance/quantity/trade fields; expected rejections `invalid_trade`, `account_missing`, `insufficient_balance`, `insufficient_position` before writes. Unexpected SQL errors roll back.
- `private_account_capability() RETURNS BOOLEAN`: service_role plus individually checked private table privileges and both write RPC EXECUTE rights; read-only, no rows returned.
- New personal APIs require verified session; client user_id is optional legacy input and ignored. GET/POST portfolio, stress save/history, trade/history, portfolio-source screener are isolated. Writes additionally require same origin.

## Test evidence

| Acceptance criterion | Test case or check | Result | Evidence |
| --- | --- | --- | --- |
| AC-01 | PrivateEndpointTests missing_invalid_and_expired_sessions; forged_user_identity; cross_origin_writes_validation_and_storage_failures | Pass | tests/test_production_safeguards.py |
| AC-02 | SQL migrations twice, preserved rows, RLS/private ACL and minimal server capability; private_capability_probe_has_static_labels_and_no_payload | Pass | tests/account_database_checks.cjs plus Python |
| AC-03 | SQL fractional buy/sell, invalid/overspend/oversell no mutation, forced_ledger_failure rollback; rpc_adapter_preserves_decimals | Pass | 55 actual Postgres assertions total; independent-connection concurrency not exercised |
| AC-04 | SQL duplicate/NaN/precision watch rejection, forced_watch_failure rollback, watch inventory isolation; storage503 validation | Pass | SQL plus PrivateEndpointTests |
| AC-05 | alert_categories_are_actionable; real_encryption_errors_are_static; private_capability_probe | Pass | Python private markers absent |
| AC-06 | ProvenanceTests.test_macro_missing_invalid_stale_and_single_bar | Pass | Missing prices and unavailable changes null |
| AC-07 | official_chip_parsing_units_dates_and_warrant_exclusion; twse_monday_and_holiday_fallback; async_analysis_provenance_misdated_score | Pass | ProvenanceTests |
| AC-08 | ai_summary_filters_old_future_undated_and_reports_generation_time; existing AIClientAndSummaryDiagnosticsTests | Pass | New and updated dated fixtures |
| AC-09 | Exact committed quality_gate and formal Reviewer report | Pending at snapshot | External immutable final reports required before release |

### Full regression

- Command: `python scripts/quality_gate.py`
- Exit code:
- Summary: Pending final committed full gate; targeted new Python12/12, existing diagnostic16/16 and isolated SQL55 assertions passed.

## Review evidence

- Correctness:
- Security:
- Performance:
- Maintainability:
- Blocking-issue count: Pending formal tested-revision review; final count supplied externally.
- Non-blocking findings and disposition:

| Severity | File and line | Reason | Blocking | Disposition |
| --- | --- | --- | --- | --- |
| Blocking test defect (fixed) | supabase/migrations/20261002125008_account_atomic_operations.sql:47 | PL/pgSQL item ambiguity prevented valid watch replacement | Resolved | Developer qualified rows.item; exact SQL re-run passed55 assertions. |

## Manual operations

- Backup intended Supabase project. Apply additive account_atomic_operations first without revoking legacy ACL; deploy new main-service code; verify `/health/private` HTTP200 ready and login/portfolio/notification reads; only then apply account_access_hardening and verify again.
- If private probe is not ready, correct effective backend key/project/Data API settings for primary Render service before legacy public permissions are revoked. Never relax private notification ACL/RLS.
- No official credentials or database rows were read/printed by Developer and no live SQL was applied.

## Risks

- Backend privilege mismatch may still block private operations pending manual environment repair; this is not solved by exposing tables publicly.
- Underlying transport threads cannot be forcefully terminated by a collector timeout; requests have finite network timeouts. Upstream availability remains external.
- No production trade smoke writes; review/test gates and phased manual operations must pass before rollout completion is claimed.

## Gate status

- [ ] Acceptance gate: all criteria pass.
- [ ] Test gate: feature tests and full regression pass.
- [ ] Review gate: blocking-issue count is zero.
- [x] Manual deployment, database, and environment steps are documented.

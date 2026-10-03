# Agent Handoff: institutional source reliability

## Work definition

- Objective: Reduce verified official institutional payload and expose safe bounded source-failure categories.
- In scope: market_provenance institutional transport, safe coverage and cache timing; necessary targeted tests.
- Out of scope: SQL, credentials, account logic, TLS bypass, DNS workarounds, unverified fallback or new features.
- Assumptions: Official exchange endpoints may fail independently. Source availability is separate from Supabase configuration.
- Dependencies: Public TWSE T86 and TPEx institutional endpoints; existing requests transport and bounded executors.

## Acceptance criteria

- [ ] AC-01: Official ALLBUT0999 preserves supported stock/ETF normalization, recent seven-day lookup, newest single trading date, shares and bounded parallel reads.
- [ ] AC-02: Independent market coverage has fixed dns/connect/read/deadline/schema/no_data categories without provider text, query, credentials or personal payload; success retains dated provenance.
- [ ] AC-03: Success TTL remains300s; empty/failure TTL15–30s; partial failures can retry without losing valid successful dated data.
- [ ] AC-04: Real available sources produce actual rows; external failures remain honest unavailable with safe reasons, no claims of fixing external DNS.
- [ ] AC-05: Minimal targeted regressions plus fullquality_gate and zero blocking review on exact new identity; no reuse old revision gate.

## Stage ownership

| Stage | Owner | Status | Started | Completed | Notes |
| --- | --- | --- | --- | --- | --- |
| Product | /root/dashboard_fix_supervisor/product | Complete |  |  |  |
| Developer | /root/dashboard_fix_supervisor/developer | Complete; frozen pending downstream gates |  |  | Sole production writer; no tests changed. |
| Tester | /root/dashboard_fix_supervisor/safeguards_tester | Targeted PASS; final committed full gate pending |  |  | Must independently verify identity and new cases before full gate. |
| Reviewer | /root/dashboard_fix_supervisor/product (Reviewer role) | Pending final tested revision |  |  | Must review the exact newly tested revision. |

## Immutable final evidence protocol

This is a precommit implementation and targeted-validation snapshot. Final formal test/review results remain pending at this capture point and are supplied externally against one clean committed HEAD. Lead commits source/tests/handoff; Tester independently verifies that HEAD and runs required full gate plus existing SQL55 checks; Reviewer verifies and reviews that same passing identity. No file is subsequently edited just to insert its own commit hash. Any new source change invalidates downstream evidence.

## Revision identity

- Baseline commit: 03c0a13194ca671364de7cc907f8ea824be42279
- Developer HEAD commit: 03c0a13194ca671364de7cc907f8ea824be42279
- Staged patch SHA-256:
- Unstaged patch SHA-256:
- Untracked files and content SHA-256 manifest:
- Tested source-state ID (HEAD plus all three hashes):
- Reviewed source-state ID (HEAD plus all three hashes):
- Shared-workspace writer: Developer until source freeze; Tester may then write tests only.

Freeze hashes are reported in the coordination message after this file is saved, avoiding a self-referential document hash. Lead will commit the final implementation and targeted tests before formal gates.

The staged hash covers `git diff --cached --binary`, and the unstaged hash covers `git diff --binary`. The untracked manifest lists every untracked path and its content hash in stable path order, then records the manifest hash. Empty patches still receive the SHA-256 of empty content. Do not use a timestamp as source identity. Tester and Reviewer must independently recompute the source-state ID; both IDs must match the Developer handoff state.

## Developer handoff

### Changed files

| File | Purpose |
| --- | --- |
| market_provenance.py | Smaller official TWSE selection; safe per-market failures and independent success/failure expiry. |
| docs/handoffs/institutional-source-reliability.md | Implementation contract, limitations and pending gate evidence. |

### Commands and results

| Command | Exit code | Result |
| --- | ---: | --- |
| Python AST parse of market_provenance.py | 0 | Syntax passes; no imports, credentials or network required. |
| git diff --check | 0 | No whitespace errors. |

Interface for targeted tests: `institutional_failure_reason(exception)` returns only `dns`, `connect`, `read`, `deadline`, `schema` or `no_data`. `_twse_result()` / `_tpex_result()` return `(rows, reason)` with `None` on success; `_twse()` retains its rows-only result. `get()` retains the existing ticker-to-row map and `_coverage` map. Successful rows preserve original source URL, date, market and shares. Each market has its own expiry: success 300 seconds; failure 20 seconds. Failed-market retries leave unexpired successful-market rows intact. DNS diagnosis follows exception types/causes only; exception text is never returned or logged.

Controls preserved: three TWSE workers, offsets 0 through 7, eight-second TWSE collection budget, twelve-second overall collection budget, requests connect/read timeout `(2, 4)`, normal HTTPS verification, existing supported-security normalization, newest available TWSE trading date. A partial lookup may use the newest completed response within its budget.

### Known limitations

- DNS/network availability is external; this change does not claim to repair TPEx DNS or guarantee availability from Render.
- Running worker calls cannot be forcefully terminated; requests timeouts remain finite, and queued pending calls are cancelled as before.
- HTTP refusals and generic connection failures use the fixed `connect` category; invalid payloads use `schema`. No raw status/provider text is exposed.
- The final offline regression, reviewer evidence and live post-deployment availability check are still pending; earlier revision gates do not apply.

## Test evidence

| Acceptance criterion | Test case or check | Result | Evidence |
| --- | --- | --- | --- |
| AC-01 | InstitutionalReliabilityTests.test_reduced_selector_preserves_supported_rows_and_latest_recent_date | Targeted PASS | Eight ALLBUT0999 queries; newest date; stock/ETF/filter/shares; seven-day acceptance. |
| AC-02 | test_real_exception_chains_and_schema_failures_have_static_private_reasons; test_deadline_failure_is_independent_of_healthy_market_and_redacted | Targeted PASS | Known nested real exception types and private marker exclusion; healthy market retained. |
| AC-03 | test_per_market_failure_retries_early_and_preserves_success_until_300_seconds | Targeted PASS | Fake clocks success300/failure20, failed-only retry, empty-cache retry. |
| AC-04 | Reduced-selector and healthy-market independence fixture cases | Targeted PASS; external live check pending | Actual supported fixture rows and truthful failed coverage; no DNS repair claim. |
| AC-05 | Exact new committed revision full gate and zero blocking review | Pending | Lead commit, Tester gate, then Reviewer. |

### Full regression

- Command: `python scripts/quality_gate.py`
- Exit code:
- Summary: Pending exact committed formal gate. Targeted four new plus fourteen existing safeguard tests passed under offline sanitized environment.

## Review evidence

- Correctness:
- Security:
- Performance:
- Maintainability:
- Blocking-issue count: Pending exact tested-revision Reviewer report; final count supplied externally.
- Non-blocking findings and disposition:

| Severity | File and line | Reason | Blocking | Disposition |
| --- | --- | --- | --- | --- |
|  |  |  |  |  |

## Manual operations

- After new gates pass, deploy the committed revision to the primary Render service and inspect `/api/chips` coverage. No database migration or new environment variable is required for this slice.
- If TPEx still reports `dns`, investigate service DNS/upstream reachability; never disable TLS or pin an unverified address.
- Existing backend-key remediation is separate and remains with the user/Lead; this slice does not change credentials or private database access.

## Risks

- Official sources can still time out or publish no recent trading data. UI receives truthful per-market coverage and fixed reasons rather than synthetic values.

## Gate status

- [ ] Acceptance gate: all criteria pass.
- [ ] Test gate: feature tests and full regression pass.
- [ ] Review gate: blocking-issue count is zero.
- [x] Manual deployment, database, and environment steps are documented.

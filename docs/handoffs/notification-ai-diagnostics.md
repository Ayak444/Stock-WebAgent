# Agent Handoff: Notification store and daily AI diagnostics

## Work definition

- Objective: Diagnose the account notification HTTP 503 and daily AI-summary error without exposing credentials or account settings.
- In scope: Required-column notification-store probe without retrieving stored rows, sanitized probe/get/save logs, concise public HTTP 503 messages, operator guidance in this handoff, and stable AI error codes/static messages in the shared gateway and daily-summary client.
- Out of scope: Automatic schema repair, new routing/features, live private account operations, webhook delivery, reading credentials, changing provider/model/token/timeouts, or destructive SQL.
- Assumptions: The exact private account-settings failure remains unproven. A previous public ready probe validated only user_id. The live daily summary previously reported a missing AI configuration.
- Dependencies: Operator access to Supabase SQL Editor and Render environment/logs; backend Supabase secret/service-role credentials; valid existing webhook encryption key and Groq API key.

## Acceptance criteria

- [ ] AC-01: The settings-store probe selects user_id,tickers,webhook_ciphertext,updated_at with limit(0), including an empty table, without fetching account/ciphertext values; missing/inaccessible columns return unavailable and status is not ready.
- [ ] AC-02: Probe/get/save logs contain static operation labels and allowlisted exception type/code/category only; classify missing schema, permission/auth, connectivity and unknown where available. Preserve HTTP 503 with concise public contact-admin wording; actionable operator checks belong in this handoff and sanitized logs. Never log raw exceptions, tracebacks, identifiers or settings data.
- [ ] AC-03: Disabled daily-summary AI returns a stable error code and Chinese contact-admin guidance. GROQ_API_KEY instructions belong in admin documentation only. Existing frontend uses textContent safely.
- [ ] AC-04: AIUnavailable carries stable codes/static messages for timeout, network, provider server and malformed responses, preserving auth/rate-limit behavior. MaiAgentClient.chat forwards sanitized classifications only; /auto_news outer catch never returns str(exc).
- [ ] AC-05: Preserve successful response shapes, per-account isolation, encryption, routing/model/max tokens/timeouts and notifications. No automatic or destructive database changes.

Lead decision after initial Product handoff: ordinary UI must not expose migration paths, environment names or Render implementation details; admin guidance stays in documentation. Readiness validation uses limit(0) rather than retrieving a stored row. These instructions supersede the original AC-02/AC-03 public operator wording and AC-01 limit(1) implementation choice.

## Stage ownership

| Stage | Owner | Status | Started | Completed | Notes |
| --- | --- | --- | --- | --- | --- |
| Product | Supervisor's Product Agent | Criteria approved | Before implementation | Before implementation | Numbered criteria handed to Developer |
| Developer | notification_ai_supervisor/developer | Implemented, ready for Tester | This task | This task | Sole production writer; no tests changed |
| Tester | notification_ai_supervisor/tester | Initial gate passed | After Developer handoff | Before initial review | 123 tests, one existing Windows skip; final committed-HEAD gate follows documentation publication |
| Reviewer | notification_ai_supervisor/reviewer | Initial review passed | After Tester pass | Before evidence publication | Exact tested identity matched; zero blocking or actionable non-blocking issues; final committed-HEAD review follows |

## Revision identity

- Baseline commit: 842f7086160b6a6693318620e0773904dcd2b64f
- Developer HEAD commit: 842f7086160b6a6693318620e0773904dcd2b64f
- Staged patch SHA-256: Published separately to Supervisor after this handoff is static.
- Unstaged patch SHA-256: Published separately to Supervisor after this handoff is static.
- Untracked files and content SHA-256 manifest: Published separately to Supervisor after this handoff is static.
- Initial tested and reviewed source-state ID: HEAD `842f7086160b6a6693318620e0773904dcd2b64f`; staged patch `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`; unstaged patch `1c946c9e2a5d97e99a47aaed4ac4f9916082c89d6952199e34ffe598999fbd19`; untracked manifest `4621660e4f8544eacaa0d4d5635c9d222beb622a4c2187b5ebb1e28a5db83b07`. Tester and Reviewer independently recomputed this identity.
- Final tested and reviewed committed source identity: Published in immutable Tester, Reviewer and Supervisor evidence after the Lead commits this documentation and the full gate/review repeat; no subsequent handoff content changes are permitted.
- Shared-workspace writer: Developer only during implementation; Tester may subsequently write tests only.

The staged hash covers git diff --cached --binary, and the unstaged hash covers git diff --binary. The untracked manifest covers every unignored untracked path and its content SHA-256, ordered by path. The manifest is a UTF-8 JSON array serialized with ensure_ascii=True and separators=(',', ':'); its SHA-256 is recorded separately. Empty patches receive the SHA-256 of empty content. Evidence is published to Supervisor separately to avoid hashing a document containing its own hash. This handoff is included in the untracked manifest and remains static until downstream evidence changes the source identity. Tester and Reviewer must independently recompute source identity.

## Developer handoff

### Changed files

| File | Purpose |
| --- | --- |
| database.py | Required-column store probe with limit(0), no row retrieval; allowlisted probe/get/save diagnostics; suppress original exception chain for settings get/save |
| route_gateway.py | AIUnavailable static code/message map and precise timeout/network/provider/malformed classification; existing circuit and request settings preserved |
| main.py | Sanitized client/daily-summary errors and concise static contact-admin settings 503 messages |
| docs/handoffs/notification-ai-diagnostics.md | Criteria, ownership, evidence protocol and manual operations |
| tests/test_notification_ai_diagnostics.py | Tester-owned focused fake tests for schema, safe metadata, UI messages and AI classifications |

### Commands and results

All shell commands are prefixed with rtk. Source inspection excluded .env and credentials.

| Command | Exit code | Result |
| --- | ---: | --- |
| rtk git status --short (baseline) | 0 | Clean baseline |
| rtk git rev-parse HEAD | 0 | Baseline commit above |
| rtk python -c compile(...), for database.py/main.py/route_gateway.py | 0 | All edited Python files compile in memory; no imports, environment loading or network |
| rtk git diff --stat and targeted diff | 0 | Production changes restricted to the three files listed |
| rtk proxy git diff --check | 0 | No whitespace errors after preserving unchanged main.py line endings; only Git LF/CRLF conversion warnings |

### Known limitations

- No private Render/Supabase access and no production credentials were used. Live recovery cannot be claimed from offline tests.
- A ready probe validates settings SELECT and required columns, not every write permission, RLS rule, row-specific condition or event RPC.
- Unknown/wrapped SDK failures without a recognized code/type remain category=unknown rather than leaking raw details.
- AI restoration requires the operator to supply the Groq key and redeploy.
- Existing migrations/003_account_volume_alerts.sql uses CREATE TABLE IF NOT EXISTS; it does not repair an incompatible preexisting table.

### Public AI error-code contract

ai_not_configured, ai_busy, ai_circuit_open, ai_auth_failed, ai_rate_limited, ai_request_rejected, ai_timeout, ai_network_error, ai_provider_error, ai_malformed_response, ai_unavailable.

Each AI error returned by the client/disabled-summary/outer-summary failure is status=error with code and static Chinese message. Successful responses remain unchanged.

## Test evidence

| Acceptance criterion | Test case or check | Result | Evidence |
| --- | --- | --- | --- |
| AC-01 | Required-column LIMIT0 projection, empty/stored rows, each missing column and unavailable status | Pass | Focused fake database/status tests |
| AC-02 | Probe/get/save schema/auth/connectivity/unknown metadata allowlists; secret/type/code/traceback non-disclosure; GET and SAVE concise 503 | Pass | Table-driven fake failures and extracted endpoint tests |
| AC-03 | Disabled /auto_news ai_not_configured contact-administrator message; no crawler call; frontend textContent; admin configuration docs | Pass | Extracted endpoint and frontend checks |
| AC-04 | Timeout/network/5xx/malformed/auth/rate-limit codes; exact forwarding; static unexpected-error catch | Pass | Fake gateway and extracted client/endpoint tests |
| AC-05 | Valid settings/AI success shapes, model, 1500-token and (5,30) timeout bounds, cooldown, existing isolation/encryption/notification regressions | Pass | Focused tests and complete offline regression |

### Full regression

- Command: `rtk proxy py -3.11 scripts/quality_gate.py`.
- Exit code: 0 on final production/test revision before documentation publication.
- Summary: 37 Python files compiled in memory; 123 tests passed with one existing Windows sendmsg skip. The focused module adds 17 tests. The final committed-HEAD gate repeats after evidence publication and is reported separately without mutating this document.

## Review evidence

- Correctness: Required-column readiness, settings errors, error classifications and successful shapes reviewed.
- Security: LIMIT0 retrieves no account values; diagnostics use metadata allowlists; customer messages are static; no credential access or provider payload disclosure introduced.
- Performance: Existing model, token/timeouts, serialization and circuit behavior preserved; readiness remains one bounded read-only query.
- Maintainability: Changes remain restricted to diagnostics and error handling with focused fake coverage and documented operator checks.
- Blocking-issue count: 0 against the initial tested identity above.
- Non-blocking findings and disposition: 0 actionable findings. Exact final committed-HEAD review follows publication, with its source identity and result reported separately.

| Severity | File and line | Reason | Blocking | Disposition |
| --- | --- | --- | --- | --- |
| None | Three production files and focused tests | No actionable findings | No | Initial tested identity independently matched; final committed-HEAD review required |

## Manual operations

1. Deploy the tested/reviewed code after the Lead authorizes completion.
2. In Supabase SQL Editor, validate required columns without reading stored rows:

   SELECT user_id,tickers,webhook_ciphertext,updated_at
   FROM public.account_volume_alert_settings LIMIT 0;

3. If the check fails, inspect column metadata before any repair:

   SELECT column_name,data_type,is_nullable
   FROM information_schema.columns
   WHERE table_schema='public' AND table_name='account_volume_alert_settings'
   ORDER BY ordinal_position;

4. Check service-role grants using metadata, without exposing user rows:

   SELECT has_table_privilege('service_role','public.account_volume_alert_settings','SELECT') AS can_select,
          has_table_privilege('service_role','public.account_volume_alert_settings','INSERT') AS can_insert,
          has_table_privilege('service_role','public.account_volume_alert_settings','UPDATE') AS can_update;

5. Inspect Render logs for account_volume_store operation=probe/get/save, exception_type, code and category. Share only these sanitized fields if more diagnosis is needed. Missing-schema codes require comparison with migrations/003_account_volume_alerts.sql; permission/auth requires same-project backend secret/service_role key and grants; connectivity requires service/network availability. Unknown needs further operator diagnosis. Do not execute DROP TABLE or overwrite existing incompatible columns based on a screenshot.
6. If tables are absent, apply migrations/003_account_volume_alerts.sql in the correct Supabase project. If tables already exist but are incompatible, obtain metadata and review a preserving migration before repair; rerunning CREATE TABLE IF NOT EXISTS is not a fix.
7. Render configuration: SUPABASE_URL and backend SUPABASE_KEY must refer to the same project; AUTH_SESSION_SECRET must meet the existing minimum; preserve valid ALERT_WEBHOOK_ENCRYPTION_KEY, VOLUME_ALERT_ENABLED=true and TZ=Asia/Taipei. Never send their contents to agents. Changing encryption key breaks existing saved webhook decryption.
8. For ai_not_configured, privately set GROQ_API_KEY in Render and Save, rebuild, and deploy. Keep existing GROQ_MODEL or the default. For other stable codes follow static guidance. Do not provide API response bodies or credentials.
9. After deployment, operator checks the public volume-alert status and authenticated settings page. Reauthenticate if the session secret changed. Each account maintains its own tickers/webhook through the existing UI. No notification messages were sent during this task.

## Risks

- Public ready cannot prove all authenticated settings operations work; private incident remains unresolved until operator checks the actual schema/permissions/logs.
- Logging is intentionally conservative; SDK errors without recognized safe codes remain unknown.
- This patch improves diagnosis and truthful status, not credentials or automatic schema provisioning.

## Gate status

- [x] Acceptance gate: all criteria pass on the initial tested production/test revision.
- [x] Test gate: focused tests and full regression pass; final committed-HEAD run required after evidence publication.
- [x] Review gate: initial tested identity has zero blocking issues; final committed-HEAD re-review required after evidence publication.
- [x] Manual deployment, database, and environment steps are documented.

# Agent Handoff: Registration error handling

## Work definition

- Objective: Make signup failures distinguishable and actionable without exposing credentials or database details.
- In scope: Signup error classification, safe diagnostics, and deployment guidance.
- Out of scope: Changing the authentication provider or creating a live account.
- Assumptions: The existing `public.users` table remains the account store.
- Dependencies: Render must use the same Supabase project's backend secret/service-role key and applicable `migrations/001_auth_store.sql` schema.

## Acceptance criteria

- AC-01: Duplicate email returns 409, handler-level invalid inputs return 400, and operational failures return safe 503. FastAPI request-model errors retain its standard 422.
- AC-02: New signup hashes the password and returns a public user without `password_hash`.
- AC-03: An existing email cannot create a duplicate account.
- AC-04: Backend insert failures do not expose provider details or secrets to clients or logs.
- AC-05: A newly registered account can log in using the existing flow.
- AC-06: Manual deployment guidance identifies the backend key and account schema requirements.

## Stage ownership

| Stage | Owner | Status |
| --- | --- | --- |
| Product | registration_product | Complete |
| Developer | registration_developer | Complete |
| Tester | registration_tester | Complete after rework |
| Reviewer | registration_reviewer | Complete after re-review |

## Revision identity

- Baseline commit: `57a7c04c5331af3fc4f5544a3dd8f1ab5537c168`
- Developer HEAD commit: `57a7c04c5331af3fc4f5544a3dd8f1ab5537c168` (uncommitted changes)
- Tested/reviewed code-state ID: HEAD `57a7c04c5331af3fc4f5544a3dd8f1ab5537c168`; staged binary patch SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`; unstaged binary patch SHA-256 `1c982a22ab13017f7e18226db299aac320b551035368033465e03cc789f24414`; pre-record untracked manifest SHA-256 `f77859eb530fe9ff78d4e9285605548f72161c687424405577f96785847b4035` using sorted `path<TAB>content_sha256<LF>` lines. Tester and Reviewer independently matched these values before this handoff record was finalized.
- Shared-workspace writer: Developer for production files; Tester for tests; Supervisor for this handoff.

## Developer handoff

Changed files: `database.py`, `main.py`, `.env.example`; Tester added `tests/test_registration_errors.py`.

Commands: in-memory AST parse passed; `git -c core.whitespace=cr-at-eol diff --check` passed.

Known limitation: The actual Render signup failure cannot be inferred from the screenshot alone.

## Test evidence

| Acceptance criterion | Test case or check | Result |
| --- | --- | --- |
| AC-01 | Short password, missing/blank name, duplicate email, and store failure | Pass: 400/409/503 as appropriate |
| AC-02 | Successful signup storage and public response | Pass: PBKDF2 hash stored; hash omitted from response |
| AC-03 | Duplicate insert check | Pass: no second row |
| AC-04 | Provider failure with private detail | Pass: detail absent from response/logs |
| AC-05 | Signup followed by login | Pass |
| AC-06 | `.env.example` and manual setup review | Pass |

Full regression: `py -3.11 scripts/quality_gate.py` passed, 107 tests with 1 existing Windows skip; in-memory compile passed 36 files. The default local Python 3.12 lacks project dependencies, so the repository's Python 3.11 interpreter was used.

## Review evidence

Reviewer inspected the same code/test revision as Tester for correctness, security, performance, and maintainability. The initial review found missing-name validation on a `users.name NOT NULL` schema; Developer fixed it, Tester reran the full gate, and Reviewer re-reviewed. Final blocking-issue count: **0**. Non-blocking: FastAPI returns its normal 422 for request-model validation; AC-01 now clarifies that distinction.

## Manual operations

- Confirm Render `SUPABASE_URL` and backend secret/service-role `SUPABASE_KEY` belong to the same project. Never reveal the key.
- Confirm `public.users` schema and apply `migrations/001_auth_store.sql` only after checking existing data; do not rerun destructive initial SQL.
- Deploy the change; if signup still returns 503, inspect the redacted Render log error category/SQLSTATE at the attempt time.

## Gate status

- Acceptance: passed for all AC-01 through AC-06.
- Test: passed on the final production/test code revision.
- Review: passed with 0 blocking issues on the tested code revision.

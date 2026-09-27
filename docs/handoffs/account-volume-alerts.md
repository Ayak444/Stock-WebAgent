# Agent Handoff: Per-account volume alerts

## Work definition

- Objective: Let each signed-in account manage its own volume-alert tickers and Discord webhook, then receive only its own matching alerts.
- In scope: authenticated account settings UI/API, storage migration, scheduled per-account scanning and durable deduplication.
- Out of scope: per-account threshold and intraday alerts.
- Assumptions: existing 20:30 Asia/Taipei schedule and 1.5x volume algorithm remain; at most 20 tickers per account.
- Dependencies: working Supabase auth store, migration, Render secrets.

## Acceptance criteria

- [ ] AC-01: Login issues a server-verifiable HttpOnly Secure SameSite cookie; `/auth/me` and logout work. Settings identity derives only from that session; anonymous requests return 401; writes reject cross-site requests. Browser localStorage is not an authorization source.
- [ ] AC-02: Each account can add/remove up to 20 validated and normalized `4-6 digits.TW/.TWO` symbols. The list survives reload and relogin, and users cannot access other accounts' settings.
- [ ] AC-03: Each account can save/replace/remove an official HTTPS Discord webhook. Backend encrypts it using a mature library such as `cryptography.Fernet` and `ALERT_WEBHOOK_ENCRYPTION_KEY`; reads reveal only whether it exists; URL never enters localStorage, logs, or responses. Missing webhook does not prevent saving tickers.
- [ ] AC-04: Daily scheduled scan uses the existing volume rule for each account, delivering only to its own webhook; stale/insufficient data and missed thresholds do not alert. Failure of one account/ticker does not stop others. Market data for duplicate tickers can be shared. No fallback to global webhook for personal volume alerts.
- [ ] AC-05: A DB unique key on user/ticker/market date prevents repeating successful notifications after restart or on multiple instances, while failed sends can retry. Status/error responses omit secrets and other users' data. When DB is unavailable, settings API returns an explicit 503 and scheduled monitoring fails closed.
- [ ] AC-06: Signed-in UI exposes volume alert settings and visible save state; signed-out state directs user to login. Browser restores identity via `/auth/me`. Global `VOLUME_ALERT_TICKERS` is documented as legacy/unused for personal alerts.
- [ ] AC-07: Small targeted tests cover account isolation, anonymous access, webhook validation/redaction, correct destination, dedupe, and failed-send retry. `python scripts/quality_gate.py` passes; Reviewer reports zero blockers.

## Stage ownership

| Stage | Owner | Status | Notes |
| --- | --- | --- | --- |
| Product | Product Agent | Complete | AC-01 through AC-07 above. |
| Developer | Developer Agent | Complete | Implemented API, UI, per-account monitor, migration, security, and documentation; stopped writing before Tester. |
| Tester | Tester Agent | Complete | Changed only `tests/test_volume_alerts.py`; final quality gate passed after one Developer rework. |
| Reviewer | Reviewer Agent | Pending | Exact tested revision. |

## Revision identity

- Baseline commit: `b93ce1fc0b9b26174db9fbe5b4b1cf29209ac7df`
- Developer HEAD commit: `b93ce1fc0b9b26174db9fbe5b4b1cf29209ac7df` plus the patches below; Lead commit pending.
- Staged patch SHA-256: pending
- Unstaged patch SHA-256: pending
- Untracked manifest SHA-256: pending
- Tested source-state ID: pending
- Reviewed source-state ID: pending
- Shared-workspace writer: Supervisor for handoff, Developer for production, Tester for tests; no concurrent writes.

## Developer handoff

- Changed files: `account_alert_security.py`, `database.py`, `volume_alerts.py`, `main.py`, `static/index.html`, `migrations/003_account_volume_alerts.sql`, `requirements.txt`, `render.yaml`, `.env.example`, `MANUAL_SETUP.md`; Tester changed `tests/test_volume_alerts.py`.
- Developer checks: Python 3.11 imports for cryptography/itsdangerous, Python compilation, inline JavaScript syntax, diff whitespace, fake-key Fernet roundtrip passed.
- Known limitations: live Supabase remains unconfigured. Render Free sleeping may miss the scheduled run. If Discord accepts a send but the database sent marker fails, retry may repeat it.

## Test evidence

| Acceptance criterion | Test case or check | Result | Evidence |
| --- | --- | --- | --- |
| AC-01 | Anonymous/session/origin/logout and browser session checks | Pass | `tests/test_volume_alerts.py`; cookie flags, 401/403, `/auth/me`, logout guard. |
| AC-02 | Isolation/normalization/persistence check | Pass | `tests/test_volume_alerts.py`; two fake accounts and session reload. |
| AC-03 | Webhook validation, encrypted storage, redaction and removal | Pass | `tests/test_volume_alerts.py`; invalid URL rejected, response omits URL. |
| AC-04 | Account-specific destination, shared market read, stale/low-volume/store failures | Pass | `tests/test_volume_alerts.py`; fake market and Discord sender. |
| AC-05 | Durable dedupe and failed-send retry | Pass | `tests/test_volume_alerts.py` and migration unique-key check; fake DB. |
| AC-06 | Account settings UI/browser session/logout checks | Pass | `tests/test_volume_alerts.py`; static/browser-oriented checks. |
| AC-07 | Focused tests and full offline regression | Pass | 102 tests OK, one existing Windows-only skip. |

- Full regression: `py -3.11 scripts/quality_gate.py` exit 0; 35 Python files compiled, 102 tests OK, one existing Windows-only skip. Exact committed HEAD recheck pending.

## Review evidence

- Correctness, security, performance, maintainability: pending.
- Blocking-issue count: pending.
- Non-blocking findings and disposition: pending.

## Manual operations

- Repair Render `SUPABASE_URL` and backend `SUPABASE_KEY` so `/health/auth` reports ready.
- Execute the new non-destructive Supabase migration in SQL Editor.
- Set independent random `AUTH_SESSION_SECRET` and `ALERT_WEBHOOK_ENCRYPTION_KEY` in Render and redeploy; each account enters its own symbols and Discord webhook in the UI.
- Render Free may sleep through the 20:30 schedule; use an always-awake plan or an external scheduler if exact timing is required.

## Risks

- Existing global Discord webhook remains for unrelated holder/daily jobs; personal volume alerts must never use it.

## Gate status

- [x] Acceptance gate: AC-01 through AC-07 passed against fake stores and static migration checks.
- [x] Test gate: focused tests and full offline gate passed before commit; committed HEAD recheck pending.
- [ ] Review gate: zero blockers.
- [ ] Manual steps documented in final user instructions.

# Agent Handoff: Daily Volume Discord Alerts

## Work definition

- Objective: Alert Discord when a selected Taiwanese stock's current trading-day volume expands materially.
- In scope: independent volume monitor, daily schedule, startup catch-up, in-process deduplication, Render settings and manual setup.
- Out of scope: intraday streaming, TDCC ownership condition, new database dependency, durable cross-restart deduplication.
- Assumptions: “today” means a completed daily market bar dated today in Asia/Taipei; default threshold is 1.5 times the prior trading sessions' median.
- Dependencies: existing market-history route and Discord notifier.

## Acceptance criteria

- [ ] AC-01: `VOLUME_ALERT_ENABLED` defaults false; `VOLUME_ALERT_TICKERS` accepts deduplicated comma-separated 4–6 digit `.TW`/`.TWO` symbols, maximum 20; `VOLUME_ALERT_MULTIPLIER` defaults 1.5 and must be finite and greater than 1. Invalid configuration does not schedule or send.
- [ ] AC-02: Enabled monitoring runs at 20:30 Asia/Taipei and has a startup catch-up only from 20:30 through 21:30. A ticker error does not stop other tickers.
- [ ] AC-03: Alert only when the newest market-bar date equals today's Asia/Taipei date, newest volume is positive, and 15–20 prior positive trading-day volumes support a median. Send when newest volume divided by that median meets the configured threshold; stale, weekend, holiday or insufficient data does not alert.
- [ ] AC-04: Discord message contains ticker, market date, newest volume, baseline median, volume multiple, source, and a non-investment-advice line. Disable mentions; preserve notifier timeouts; do not expose webhook URLs on failure.
- [ ] AC-05: Each ticker and market date sends at most once during one running process. Monitoring requires neither Supabase nor TDCC. State explicitly that a process restart can repeat a message.
- [ ] AC-06: `.env.example`, `render.yaml`, and `MANUAL_SETUP.md` document Webhook URL, stock list, enable switch, optional multiplier and deployment check. Explain that sleeping Render Free instances cannot reliably execute an in-process 20:30 job.
- [ ] AC-07: Add a few focused feature checks and pass the repository quality gate without broad new testing.

## Stage ownership

| Stage | Owner | Status | Started | Completed | Notes |
| --- | --- | --- | --- | --- | --- |
| Product | volume_product | Complete | 2026-09-27 | 2026-09-27 | Seven criteria and launch assumptions delivered. |
| Developer | volume_developer | Complete | 2026-09-27 | 2026-09-27 | Implemented independent volume-only monitoring and deployment settings. |
| Tester | volume_tester | Preliminary pass | 2026-09-27 |  | Five focused checks and 98-test gate passed before final commit; rerun required on final HEAD. |
| Reviewer | volume_reviewer | Not started |  |  | Review tested source state. |

## Revision identity

- Baseline commit: `049230476a9c09f1430ee50fba097e140b25ae26`
- Developer HEAD commit: Pending
- Staged patch SHA-256: Pending
- Unstaged patch SHA-256: Pending
- Untracked files and content SHA-256 manifest: Pending
- Tested source-state ID (HEAD plus all three hashes): Pending
- Reviewed source-state ID (HEAD plus all three hashes): Pending
- Shared-workspace writer: Supervisor for this handoff until Developer begins; Developer for production changes; Tester for tests only.

## Developer handoff

### Changed files

| File | Purpose |
| --- | --- |
| volume_alerts.py | Independent volume monitor, configuration, same-day checks and in-process deduplication. |
| main.py | 20:30 Asia/Taipei schedule, bounded startup catch-up and status endpoint. |
| notifier.py | Volume-specific Discord message via existing safe sender. |
| .env.example, render.yaml | New deployment configuration names and defaults. |
| MANUAL_SETUP.md | Manual setup and operational limitations. |
| tests/test_volume_alerts.py | Five focused behavior checks. |

### Commands and results

| Command | Exit code | Result |
| --- | ---: | --- |
| py -3.11 -m py_compile volume_alerts.py notifier.py main.py | 0 | Syntax passed; Developer confirmed. |
| py -3.11 -m scripts.offline_unittest discover -s tests -p test_volume_alerts.py -v | 0 | Five focused tests passed. |
| py -3.11 scripts/quality_gate.py | 0 | Preliminary: 34 files compiled, 98 tests passed, one existing Windows skip. Final HEAD rerun pending. |

### Known limitations

- Process restart may repeat a Discord alert for the same trading day.
- Render Free can sleep through the scheduled execution time.

## Test evidence

| Acceptance criterion | Test case or check | Result | Evidence |
| --- | --- | --- | --- |
| AC-01–AC-07 | Five focused volume tests plus existing quality gate | Preliminary pass | tests/test_volume_alerts.py; final HEAD check pending. |

### Full regression

- Command: `py -3.11 scripts/quality_gate.py`
- Exit code: 0 (preliminary; final HEAD rerun pending)
- Summary: 34 files compiled, 98 tests passed, one existing Windows skip.

## Review evidence

- Correctness: Pending
- Security: Pending
- Performance: Pending
- Maintainability: Pending
- Blocking-issue count: Pending
- Non-blocking findings and disposition: Pending

## Manual operations

- Set `DISCORD_WEBHOOK_URL` only in Render or another secret manager.
- Configure `VOLUME_ALERT_TICKERS` and `VOLUME_ALERT_ENABLED=true`; optionally adjust `VOLUME_ALERT_MULTIPLIER`.
- Keep the service awake or supply an external wake-up approach if fixed-time delivery is required.

## Risks

- No durable deduplication without a working persistent store.
- Market sources may publish the completed daily bar after the configured schedule; no alert is sent until the next run if the date is stale.

## Gate status

- [ ] Acceptance gate: all criteria pass.
- [ ] Test gate: focused feature checks and full quality gate pass.
- [ ] Review gate: blocking-issue count is zero.
- [ ] Manual deployment and environment steps are documented.



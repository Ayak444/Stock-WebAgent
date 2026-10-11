# Agent Handoff: Integrated editorial research UI

## Work definition

- Objective: Integrate the approved dark navy, warm white and orange editorial direction across the existing static application, preserve its tools, and carry one stock context through research and notification drafts.
- In scope: `static/index.html`, small frontend resources `static/workspace.css` and `static/workspace.js`, this feature handoff, and subsequent Tester-owned tests.
- Out of scope: React, backend/API contracts, database, environment files, deployment, new delivery-history/favorites APIs, GSAP skill submodule, and automatic paid AI analysis.
- Assumptions: Public visitors can read market data. Existing endpoint responses remain authoritative. Notification progress describes saved configuration rather than service activation or delivery. Explicit `.TW` / `.TWO` suffixes remain unchanged.
- Dependencies: Existing ECharts and GSAP CDN assets; existing static-file server and cookie-based APIs. GSAP absence and reduced motion do not gate the default application or About navigation.
- Reference: Approved `stock-ux-directions.html` external design artifact. UI/UX Pro Max guidance and GSAP core/performance skills were read; generic light finance colors were deliberately not applied because the approved visual direction takes precedence.

## Acceptance criteria

- [ ] AC-01: First entry displays the public `.app` market overview directly without login. About retains the original brand/functions page and returns to the market; absent GSAP/CDN or reduced motion does not prevent operation.
- [ ] AC-02: Four groups (market overview, individual research, strategy/risk, personal notifications) expose all ten original pages. Active state, titles and original keyboard shortcuts remain; technical analysis/news graph are labeled as market-wide.
- [ ] AC-03: All ten pages, authentication/history dialogs, chat and About use consistent navy/warm-white/orange typography, forms, buttons, headings, tables and states. Editorial separators and spacing avoid main-content gradients/heavy shadows/card stacking. Price rises/falls retain red/green plus signs or text.
- [ ] AC-04: Home reads market indicators, industry/news focus, manually requested AI, then news/calendar. Taiwan weighted index remains primary. Dates, sources, limitations, partial states and retry remain; focus/search enter the stock context. AI retains three content blocks and complete original disclosure.
- [ ] AC-05: Insights/K-line/backtest/screener share a validated ticker header and tool navigation. Explicit TW/TWO suffixes are preserved. Switching stock clears obsolete output; empty/invalid input or late responses cannot label old results as a new stock.
- [ ] AC-06: Overview uses the existing stock snapshot; K-line uses the existing chart; ownership and individual news filter the snapshot's ownership/news articles; backtest uses the existing tool. Dates/source/method/absence/not-applicable/ETF restrictions and market rankings/trending remain.
- [ ] AC-07: Switching context/tools synchronizes inputs without automatically starting analysis, backtest, screener or paid AI. K-line's manual button explicitly names chart loading and existing analysis. Screener receives only a candidate input; list mutation/import/run remain manual.
- [ ] AC-08: Preserve technical modes/sorting; K-line 30/90/180/365 periods, volume/MACD/KD/RSI, subchart/signals/fundamentals/chips; all backtest costs/reset/trades/performance/limits; stress positions/sync/analyze/history; news/sentiment/screener functions.
- [ ] AC-09: Notifications support in-place login, loading/failure/retry/empty/configured/recovery states. Progress/saved counts derive only from GET tickers/configured/readable/recovery fields. Drafts and saved state are distinct; 20-stock limits are explicit. Do not imply monitor activation, channel verification or message delivery.
- [ ] AC-10: Empty Webhook retains it; replacement/removal/unreadable recovery remain. Missing encryption configuration explains administrator restoration and removal; unavailable encryption permits replacement/removal. Never return an original URL. Save re-GETs configuration before updating progress. Research transfers one ticker as a labeled draft without replacing the list, exceeding 20 or autosaving.
- [ ] AC-11: Existing login/register/logout/session/account notifications/portfolio APIs, cookies and errors remain. Logout/account change clears the prior account's settings/Webhook draft. GET retries/POST no-retry, safe text/links/chat, WebSocket and wrapper remain. No new favorites/device history/delivery-query API.
- [ ] AC-12: 1440/390/320 layouts remain readable and operable without page-level horizontal overflow; wide tables scroll internally; headers/tabs/forms wrap and charts resize on navigation/window changes. Keyboard/focus/labels/states remain accessible. Tester supplies AC mapping, offline/full quality gate and desktop/mobile visual evidence; Reviewer reports zero blocking issues against the exact tested revision.

## Stage ownership

| Stage | Owner | Status | Started | Completed | Notes |
| --- | --- | --- | --- | --- | --- |
| Product | integrated_ui_supervisor/product | Complete; Lead approved AC-01–12 | 2026-10-10 | 2026-10-10 | Requirements relayed verbatim by Supervisor to Developer. |
| Developer | integrated_ui_supervisor/developer; integrated_ui_finish_supervisor/developer | Production frozen; follow-on handoff update then freeze | 2026-10-10 | 2026-10-11 | Original owner implemented production code; follow-on Developer changed only this handoff. |
| Tester | integrated_ui_finish_supervisor/tester | Precommit checks passed; final committed-source retest pending | 2026-10-11 | | Sole test writer; both test files frozen before this document update. |
| Reviewer | Assigned by integrated_ui_finish_supervisor after final Tester | Pending final-commit independent review | | | Must review the exact source that final Tester passed. |

## Revision identity

- Baseline commit: `4dc59f7646e66fe0a2c03b3d28236917cb1eae2a`.
- Developer HEAD commit: Baseline until Lead commits the final feature.
- Staged patch SHA-256: External final identity artifact; never self-hash this document into itself.
- Unstaged patch SHA-256: External final identity artifact.
- Untracked files and content SHA-256 manifest: External final identity artifact includes this document and every untracked frontend resource.
- Developer identity artifact: `C:/Users/Ayak4-PC/.codex/visualizations/2026/09/13/01a099ee-c132-7790-bae7-1702ec9ba186/integrated-ui-developer-identity.json`.
- Identity algorithm: Existing external `home-source-identity.cjs`; raw Git binary patches with `--ignore-submodules=dirty`, SHA-256, sorted JSON manifest of untracked paths/content hashes. Gitlink changes remain detectable.
- Tested source-state ID (HEAD plus all three hashes): Pending independent Tester computation.
- Reviewed source-state ID (HEAD plus all three hashes): Pending independent Reviewer computation.
- Shared-workspace writer: Original Developer froze production; Tester added only test files, froze them, and explicitly released the writer slot. Follow-on Developer then updated only this document and froze it. Lead owns the final commit; no Developer commit/push.
- Precommit Tester report: `C:/Users/Ayak4-PC/.codex/visualizations/2026/09/13/01a099ee-c132-7790-bae7-1702ec9ba186/integrated-ui-tester-precommit.md`.
- Final freeze identity: `C:/Users/Ayak4-PC/.codex/visualizations/2026/09/13/01a099ee-c132-7790-bae7-1702ec9ba186/integrated-ui-final-freeze-identity.json`, computed after this document update. Updating this handoff intentionally invalidates the previous untracked-manifest identity; the precommit report does not substitute for the final checks.
- Immutable final-evidence protocol: After Lead commits the frozen files, Tester independently recomputes source identity and reruns the feature suite and full offline gate. Reviewer independently recomputes that identity and reviews the same final commit. Final Tester and Reviewer reports remain outside the repository to avoid a handoff self-hash cycle. Supervisor supplies their exact report paths, reviewed HEAD, acceptance results and blocking count to Lead. No claim of completion follows merely from the precommit results recorded here.

## Developer handoff

### Changed files

| File | Purpose |
| --- | --- |
| `static/index.html` | Direct public entry, four navigation groups, editorial content, notification UI, original tools with request identity guards, auth reset and keyboard/modal accessibility. |
| `static/workspace.css` | Shared editorial surfaces/tokens, mobile wrapping, wide-table containment, single-section snapshot layouts and reduced motion. |
| `static/workspace.js` | Shared ticker/header/tool navigation, original field movement, request version/epoch checks, saved notification progress/draft transfer, About routing, chart resize and modal focus trap. |
| `docs/agent-handoff-integrated-ui.md` | Definition, criteria, owners, source identity protocol, checks, manual work and risks. |
| `tests/integrated_ui_checks.cjs` | Tester-owned offline DOM/API harness executing production helpers, context/async races, notification draft/recovery/account isolation and focus. |
| `tests/test_integrated_ui.py` | Tester-owned regression integration invoking the frontend harness through the offline quality gate. |

### Commands and results

| Command | Exit code | Result |
| --- | ---: | --- |
| `rtk proxy node --check static/workspace.js` | 0 | New shared frontend resource parses. |
| `rtk proxy node tests/home_overview_checks.cjs` | 0 | Existing homepage hierarchy/limits/dates/partial/failure/manual AI/safe rendering and GSAP fallback checks pass. |
| `rtk proxy node tests/dashboard_browser_checks.js` | 0 | Existing inline browser syntax/retry/cost/calendar/link-safety checks pass. |
| `rtk git diff --check --ignore-submodules=dirty` | 0 | No whitespace errors. |
| Lead external browser preview, fake fixtures only | Passed preliminary visual QA | 1440 desktop and 390/320 mobile: four navigation groups, ten routes, explicit `.TWO` stock transfer/manual snapshot, single-section views, saved/draft notification states, encryption recovery, retry and no page overflow. Formal Tester evidence remains required. |
| `rtk proxy node tests/integrated_ui_checks.cjs` | 0 | Independent precommit Tester: actual production helpers pass against offline DOM/API fixtures. |
| `rtk proxy C:/Users/Ayak4-PC/AppData/Local/Temp/stock-webagent-polish-quality-venv/Scripts/python.exe scripts/quality_gate.py` | 0 | Independent precommit Tester: 43 Python files compile; 159 tests run, 158 pass and one Windows `sendmsg unavailable` skip. Final committed-source retest remains required. |

### Known limitations

- ECharts is an existing remote chart dependency; a missing asset produces an explicit retry/reload message. No fabricated chart values are added.
- Individual ownership/news tools filter an already requested snapshot; if no snapshot has been requested, they display the manual read action. Market-wide industry/trending context remains available below.
- Research inputs preserve explicit suffixes; an unsuffixed valid Taiwan ticker defaults to `.TW`, consistent with the existing normalized input convention.
- Notification progress is configuration evidence only. The current APIs provide no channel-verification or delivery-history evidence.

## Test evidence

| Acceptance criterion | Test case or check | Result | Evidence |
| --- | --- | --- | --- |
| AC-01 | Actual entry/About helpers isolate app, restore market/focus and keep drafts without GSAP/API; homepage motion fallback tests | Precommit pass | `integrated_ui_checks.cjs`, existing homepage tests; external precommit report. |
| AC-02 | Four sections/ten routes, execute route active states/titles and preserved shortcut wiring | Precommit pass | `integrated_ui_checks.cjs`; Lead's actual browser route checks. |
| AC-03 | Original controls/dialogs/chat retained, shared CSS and signed colors; editorial visual inspection | Precommit pass with Lead visual evidence | Tester harness plus Lead's actual 1440/390/320 browser QA. Tester browser inventory was unavailable; no independent Tester screenshots are claimed. |
| AC-04 | Market order/limits/provenance/dates/partial/error/retry/manual three-block AI and full disclosure | Precommit pass | Existing `test_home_overview` and `home_overview_checks.cjs` in the full gate. |
| AC-05 | Ticker validation/suffixes/input sync; epoch and same-stock version races across snapshot/chart/analysis/fundamentals/chips/backtest | Precommit pass | Production helper execution with deferred offline API responses in `integrated_ui_checks.cjs`. |
| AC-06 | Snapshot source/date/method/ETF/partial/escaped articles, filtered ownership/news and chart/backtest paths | Precommit pass | Actual render/filter helpers in `integrated_ui_checks.cjs`; Lead visual filtered-view checks. |
| AC-07 | Six tool switches make no analysis calls, preserve screener list; manual K-line invokes chart and existing analysis once | Precommit pass | API-call observations and original list assertions in `integrated_ui_checks.cjs`. |
| AC-08 | Original periods/indicators, real subchart helpers, fundamentals/chips success/failure, backtest payload/costs/trades/limits and original tools | Precommit pass | Integrated harness plus full original technical/news/sentiment/stress/screener/backtest regression. |
| AC-09 | Real login/retry buttons; saved progress versus draft; append/dedup/20-limit; empty/error/recovery and no delivery claim | Precommit pass | Actual notification helpers and offline GET fixtures in `integrated_ui_checks.cjs`; Lead mobile state checks. |
| AC-10 | Blank Webhook null/preserve flag, replacement/removal/recovery, fresh GET confirmation before progress and no original URL display | Precommit pass | Actual PUT/GET helpers and deferred confirmation in `integrated_ui_checks.cjs`. |
| AC-11 | Account GET/PUT races/reset/logout success/failure; original cookie/session/CSRF/retry/safety/API regressions | Precommit pass | Integrated helper assertions plus existing full offline regression. |
| AC-12 | Forward/reverse focus trap; responsive/reduced-motion/table CSS; actual 1440/390/320 all-ten-page no-overflow/form/About checks; full gate | Precommit tests pass; exact final retest/review pending | Tester helper suite and full gate; actual visual evidence is Lead's browser QA. Final Tester/Reviewer reports must independently identify the committed source. |

### Full regression

- Lead's supplemental actual-browser evidence for the tested production files: `C:/Users/Ayak4-PC/.codex/visualizations/2026/09/13/01a099ee-c132-7790-bae7-1702ec9ba186/integrated-ui-tested-desktop.png`, `integrated-ui-tested-mobile.png`, and `integrated-ui-lead-responsive.json` in the same external directory. At 1440 and 390 widths the document fits the viewport; each of ten actual route clicks fits at 320. About hides the app, moves focus to its return action and restores the active market heading; selecting `6488.TWO` enters insights without automatically loading a snapshot.
- Precommit command: `rtk proxy C:/Users/Ayak4-PC/AppData/Local/Temp/stock-webagent-polish-quality-venv/Scripts/python.exe scripts/quality_gate.py`.
- Precommit exit code: 0; 43 Python files compiled; 159 tests in 10.661 seconds, 158 passed and one platform-specific `sendmsg unavailable` skip. Host execution was required for Windows event-loop behavior; the offline runner still excluded credentials and blocked network.
- Feature command: `rtk proxy node tests/integrated_ui_checks.cjs`, exit 0.
- Exact final committed-source full regression: Pending independent Tester; external final report is authoritative. The document update changes only the handoff but still requires recomputed identity and the mandatory final retest.

## Review evidence

- Correctness: Pending Reviewer.
- Security: Pending Reviewer.
- Performance: Pending Reviewer.
- Maintainability: Pending Reviewer.
- Blocking-issue count: Not assessed; no completion declaration before formal review.
- Non-blocking findings and disposition: Pending Reviewer.

| Severity | File and line | Reason | Blocking | Disposition |
| --- | --- | --- | --- | --- |
| Visual QA | `static/workspace.js`, `static/workspace.css`, `static/index.html` | Single snapshot section left half empty; repeated ticker fields; repetitive home subtitle. | Addressed before freeze | Single-column filtered views, move original ticker fields into shared header, concise subtitle. |
| Visual QA | `static/index.html`, `static/workspace.js`, `static/workspace.css` | Failed fundamentals left fields loading; notification completion state named already satisfied prerequisites; mobile workspace spacing was excessive. | Addressed before freeze | All failed fundamental fields show source unavailable, completion lists only missing saved prerequisites and distinguishes signed-in failure, mobile spacing reduced. |
| Blocking visual QA | `static/workspace.js`, `static/index.html` | About removed `.app.active` but the base `.app` remained displayed and exposed background navigation/forms to accessibility and keyboard focus. | Fixed; requires fresh Tester/Reviewer evidence | About now sets the app hidden, inert and inline display none, closes the mobile overlay and chat panel; returning restores the app and focuses the market heading. The inline entry fallback also restores hidden/inert/display state. Research context, notification drafts and chat messages remain in memory. |

## Manual operations

- Deploy the changed static assets through the existing application deployment flow and refresh the browser cache. No database migration, new environment setting or backend change is required.
- Discord encryption recovery continues to require an administrator restoring the existing encryption setting when the server reports `encryption_not_configured`; users may remove the unusable Webhook through the existing form.
- Lead commits the final source after Developer freeze; Supervisor obtains formal Tester and Reviewer evidence against the exact source.

## Risks

- Frontend resources must be served together with `index.html`; mixed cached versions can break the shared ticker controls. Existing API contracts are unchanged.
- Existing API/CDN availability remains a runtime dependency. Data and configuration states are explicitly distinguished from unavailable sources, AI conclusions and delivered alerts.

## Gate status

- [ ] Acceptance gate: all criteria pass.
- [ ] Test gate: feature tests and full regression pass.
- [ ] Review gate: blocking-issue count is zero.
- [x] Manual deployment, database, and environment steps are documented.

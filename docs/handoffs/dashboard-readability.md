# Agent Handoff: readable calendar and dashboard layout

## Work definition

- Objective: Open readable official calendar pages and improve summary typography and consistent responsive dark dashboard layouts.
- In scope: Frontend static/index.html styling and known official-link mapping; preserve API provenance/data logic.
- Out of scope: New news export, backend parsing, database, credentials, external branding/assets.
- Assumptions: User wants readable official source pages, not a news export. Known API provenance remains unchanged in API response data.
- Dependencies: Lead verified both official HTML pages with HTTP 200 and readable content; existing safe external-link binding and dashboard IDs/handlers.

## Acceptance criteria

- [ ] AC-01: Known calendar TWSE API source links map only to verified readable official event/holiday pages with safe target/rel; original source/date retained and unknown URLs handled safely.
- [ ] AC-02: Summary/opinion/news main prose >=16px, desktop18px/mobile17px for primary prose and lineheight approximately1.9 (Lead-approved direction supersedes initial1.7–1.85); readable width/wrapping, metadata>=12px and date/source/escaping preserved.
- [ ] AC-03: Consistent dark headings/cards/section/control spacing across dashboard pages; preserve nav IDs/handlers/chart containers/data logic.
- [ ] AC-04: Desktop1440/mobile375 responsive grids, operable forms, no page overflow, table-only scroll, visible keyboard focus/labels/reduced motion; no copied branding/assets.
- [ ] AC-05: Targeted safe link/readability checks, necessary visual/function smoke, fullquality_gate and zero blocking same identity review; only deploy/refresh manual steps.

## Stage ownership

| Stage | Owner | Status | Started | Completed | Notes |
| --- | --- | --- | --- | --- | --- |
| Product | /root/dashboard_fix_supervisor/product | Complete |  |  |  |
| Developer | /root/dashboard_fix_supervisor/developer | Complete; frozen pending downstream gates |  |  | Sole source/handoff writer; no test files changed. |
| Tester | /root/dashboard_fix_supervisor/safeguards_tester | Targeted PASS; committed full gate pending |  |  | Concurrency/agent availability may require recorded Lead role exception; Developer does not test its own change. |
| Reviewer | /root/dashboard_fix_supervisor/product (Reviewer role) | Pending exact tested revision |  |  | Exact new tested revision required. |

## Role exception for bounded mobile correction

Developer and alternate top-level Developer resume were both rejected by agent thread limit after the frozen-source visual check found a mobile date column wrapping ISO dates. Lead explicitly became temporary Developer owner only for two CSS declarations: mobile calendar column88px and time white-space:nowrap. Test writer paused during that production change. Lead froze the fix with diff-check success; independent Tester resumes after this record and independent Product-as-Reviewer is preferred. Supervisor did not implement or self-review production code. The existing user-authorized management fallback is used only if independent review also cannot resume.

## Immutable final evidence protocol

This file is a precommit implementation and targeted-validation snapshot. Final formal full quality-gate and review evidence are pending at capture and will be supplied as immutable external reports against the same clean committed HEAD. Lead commits frontend, test harness and handoff, then Tester recomputes identity and runs the full offline gate plus current browser harness; Reviewer independently verifies and reviews that exact passing revision. No handoff edit is needed merely to insert its own commit hash. Any later source change invalidates downstream evidence.

## Revision identity

- Baseline commit: 7fdccf4e9bf2b70b237d826ab778ce996e052954
- Developer HEAD commit: 7fdccf4e9bf2b70b237d826ab778ce996e052954
- Staged patch SHA-256:
- Unstaged patch SHA-256:
- Untracked files and content SHA-256 manifest:
- Tested source-state ID (HEAD plus all three hashes):
- Reviewed source-state ID (HEAD plus all three hashes):
- Shared-workspace writer: Developer until freeze; downstream test-only writer after independent identity verification.

Freeze hashes are supplied in the coordination message after saving this handoff; they are not embedded recursively in the hashed document. Lead commits implementation plus targeted tests before the formal full gate and review.

The staged hash covers `git diff --cached --binary`, and the unstaged hash covers `git diff --binary`. The untracked manifest lists every untracked path and its content hash in stable path order, then records the manifest hash. Empty patches still receive the SHA-256 of empty content. Do not use a timestamp as source identity. Tester and Reviewer must independently recompute the source-state ID; both IDs must match the Developer handoff state.

## Developer handoff

### Changed files

| File | Purpose |
| --- | --- |
| static/index.html | Verified calendar HTML link mapping, date timeline and six-entry disclosure; AI summary above news/calendar; shared dark card/layout style and targeted readable prose; mobile controls, table scrolling, focus and accessible control names. |
| docs/handoffs/dashboard-readability.md | Approved revised typography, implementation contract and pending validation/deployment evidence. |

### Commands and results

| Command | Exit code | Result |
| --- | ---: | --- |
| Node --check on all extracted inline scripts via UTF-8 stdin | 0 | 93,328 characters checked after final source edits; syntax passes. |
| git diff --check | 0 | No whitespace errors. |

An initial syntax attempt failed due to the Windows console's cp950 encoding; the corrected explicit UTF-8 command above checked the actual complete script successfully. These are syntax/format checks only; targeted behavior and visual smoke subsequently passed as recorded below; formal committed full regression and independent review remain pending.

Targeted helper contract: `calendarReadableSourceUrl(value)` maps only the known HTTPS `openapi.twse.com.tw` origin and exact endpoint path to `https://www.twse.com.tw/zh/announcement/ex-right/twt48u.html` or `https://www.twse.com.tw/zh/trading/holiday.html`. Query strings do not prevent the known mapping. Unknown valid HTTP(S) URLs retain their safe URL; malformed, non-HTTP(S), or credential-bearing URLs return empty. Existing `bindSafeExternalLinks` applies `_blank` and `noopener noreferrer` and converts unsafe links to plain text. API event objects, dates, titles and source values are never rewritten.

Calendar contract: first six real events are visible; all additional events remain in a native keyboard-operable details/summary disclosure with separate expanded/collapsed text. Date/title/kind/source are escaped. No nested fixed-height scrolling is used. AI update action and AI summary precede the news/calendar grid. Main summary body uses18px desktop,17px mobile,lineheight1.9 and74ch readable width; news tiles use16px prose. Source/time metadata is separate12px text. IDs, handlers, chart containers, API calls and data escaping are preserved.

### Known limitations

- External official pages can change independently; only the two verified known endpoints are mapped. Unknown sources remain safe external links rather than invented destinations.
- CSS respects reduced-motion for existing CSS animations/transitions; this slice adds no animations and does not rewrite pre-existing landing GSAP logic.
- Native details disclosure supplies the browser's expanded/collapsed accessibility state; no static aria-expanded value is introduced that could become inconsistent.
- Viewport/function smoke passed on the frozen frontend; formal committed regression and review are pending; earlier revision gates are invalid for this new source state.

## Test evidence

| Acceptance criterion | Test case or check | Result | Evidence |
| --- | --- | --- | --- |
| AC-01 | Actual tests/dashboard_browser_checks.js helper/render/binder behavior | Targeted PASS | Exact TWSE mappings and queries, safe unknown/path/lookalike preservation, unsafe or credential rejection, escaped values and protected new-tab links. |
| AC-02 | Lead frozen-source representative long-content viewport smoke | PASS | Summary18px desktop/17px mobile, line-height1.9, metadata12px; source/date preserved and renderer escaping verified by Node harness. |
| AC-03 | Lead all ten navigation pages at1440px and375px | PASS | No document overflow or clipped inputs/selects/buttons/cards; charts/handlers retained; summary precedes news/calendar. |
| AC-04 | Actual render disclosure plus Lead desktop/mobile/keyboard smoke | PASS | First six plus every remainder once; Enter expands/collapse hides;375 document width375,date88px nowrap; all nine fixture source anchors readable with target/rel. |
| AC-05 | Focused checks, full quality gate and zero blocking exact-HEAD review | Pending | Commit and downstream stages required. |

### Full regression

- Command: `python scripts/quality_gate.py`
- Exit code:
- Summary: Pending exact committed full gate; actual Node behavior harness and inline syntax passed, offline DashboardReliabilityTests11/11 passed. Lead viewport smoke passed on frozen production source.

## Review evidence

- Correctness:
- Security:
- Performance:
- Maintainability:
- Blocking-issue count: Pending exact tested-revision formal review; final count supplied externally.
- Non-blocking findings and disposition:

| Severity | File and line | Reason | Blocking | Disposition |
| --- | --- | --- | --- | --- |
|  |  |  |  |  |

## Manual operations

- Deploy the tested/reviewed committed frontend to the primary Render service, then refresh the browser (force reload if old assets remain cached).
- No new environment variables, database migrations, exports or manual data edits are required.

## Risks

- Dynamic responses and long titles can alter card heights; downstream viewport smoke must include real or representative long content on every navigation page.

## Gate status

- [ ] Acceptance gate: all criteria pass.
- [ ] Test gate: feature tests and full regression pass.
- [ ] Review gate: blocking-issue count is zero.
- [x] Manual deployment, database, and environment steps are documented.

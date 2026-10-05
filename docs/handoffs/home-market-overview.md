# Agent Handoff: home market overview

## Work definition

- Objective: Implement selected homepage market overview plus compact AI, retaining navy/orange readable layout and existing data/features.
- In scope: Existing homepage frontend macro hierarchy, single overview industries/trending, independently loaded latest news, safe collapsed AI and Taipei metadata.
- Out of scope: Landing redesign, new data/API, heatmaps/volume ranking, additional LLM summaries, database/env changes.
- Assumptions: Homepage is selected; landing and other pages remain unchanged. Dates come from the source response, not the browser refresh clock. News-interest ranking is not volume ranking.
- Dependencies: Existing /macro, /api/market-insights, /news, /auto_news and calendar APIs and safe URL helpers; no new backend endpoint or LLM call.

## Acceptance criteria

- [ ] AC-01: Market indicators replace misnamed hotspots; main TWSE plus SOX/SP500/VIX, other four native disclosure; no fake zeros/realtime claims.
- [ ] AC-02: One existing overview request per load/refresh, maxfive industries and news-interest stocks, true dates/coverage and independent missing states, no per-stock calls.
- [ ] AC-03: News initial independent fetch, valid publishdate sort max10, honest missing dates, refresh only news, safe source/title/prose disclosure.
- [ ] AC-04: AI button only, original firstthree contentblocks visible and keyboard full-content disclosure, no new rewriting call, all original content retained.
- [ ] AC-05: Limited safe Markdown headings/paragraphs/lists using escaped fixed markup or text nodes; no arbitrary HTML/events/unsafe links; distinct Taipei generation/market/news times.
- [ ] AC-06: Ticker/Enter existing analyze preserved; optionalname onlyexisting data; existing calendar/events/officialHTMLsource, landing/auth/nav behaviors preserved.
- [ ] AC-07: Each region independent loading/error/empty,1440/375 no clipped controls/documentoverflow, labels/focus/native disclosures.
- [ ] AC-08: Meaningful offline fake behavior/XSS/call separation/limits/completeness plus fullquality gate and exact-revisionzero blocking independentreview; no liveAI/notifications/DBtests.

## Stage ownership

| Stage | Owner | Status | Started | Completed | Notes |
| --- | --- | --- | --- | --- | --- |
| Product | /root/dashboard_fix_supervisor/product | Complete |  |  |  |
| Developer | /root/dashboard_fix_supervisor/developer | Complete; frozen pending gates |  |  | Sole frontend/handoff writer; no tests changed or run. |
| Tester | /root (explicit user-authorized fallback) | Targeted/visual and precommit full gate PASS; formal committed gate pending |  |  | New behavior/XSS cases and exact new revision full gate. |
| Reviewer | /root/dashboard_fix_supervisor/product (Reviewer role) | Pending exact passing committed revision |  |  | Review newly tested committed revision. |

## Explicit test-stage role exception

Existing Tester follow-up was rejected by agent thread limit both during independent planning and after Developer freeze. Under the existing explicit user authorization, Lead /root assumed Tester ownership, wrote only test files and executed offline fake-data behavior and browser checks. Developer remained the only production writer and stopped before that stage. Supervisor only coordinates and records this handoff; independent Product-as-Reviewer is required/preferred for the final passing revision.

## Immutable final evidence protocol

This is a precommit implementation and tested acceptance snapshot. Lead commits frontend, tests and this handoff together; final full quality-gate output and Reviewer findings are then supplied as immutable external reports against the same clean committed HEAD. Identity includes HEAD, both binary-patch hashes and sorted untracked manifest hash. No later handoff edit inserts its own commit hash. Any source change invalidates downstream formal evidence. Earlier revision evidence is never substituted for the new final gate.

## Revision identity

- Baseline commit: 58e7f56f28c115d516f2850c7337fb3419482a80
- Developer HEAD commit: 58e7f56f28c115d516f2850c7337fb3419482a80
- Staged patch SHA-256:
- Unstaged patch SHA-256:
- Untracked files and content SHA-256 manifest:
- Tested source-state ID (HEAD plus all three hashes):
- Reviewed source-state ID (HEAD plus all three hashes):
- Shared-workspace writer: Developer until freeze; then test-only writer after identity verification.

Freeze hashes are supplied in the coordination message after saving this file to avoid self-referential hashes. Lead commits implementation and targeted tests before the formal full gate and review. Earlier revision evidence is not reused.

The staged hash covers `git diff --cached --binary`, and the unstaged hash covers `git diff --binary`. The untracked manifest lists every untracked path and its content hash in stable path order, then records the manifest hash. Empty patches still receive the SHA-256 of empty content. Do not use a timestamp as source identity. Tester and Reviewer must independently recompute the source-state ID; both IDs must match the Developer handoff state.

## Developer handoff

### Changed files

| File | Purpose |
| --- | --- |
| static/index.html | Home-only indicator hierarchy/top-five overview, independent news and manual compact-AI loading, source-date display and safe original-text disclosures. |
| docs/handoffs/home-market-overview.md | Implementation contracts, validation seams, limitations and pending downstream evidence. |

### Commands and results

| Command | Exit code | Result |
| --- | ---: | --- |
| Node --check on all inline JavaScript via explicit UTF-8 stdin | 0 | Syntax passes on the final complete script. |
| git diff --check | 0 | No whitespace errors. |

Loader contract: init launches existing macro, one home overview, news and calendar loads independently. It never calls AI. `fetchHomeOverview()` performs only one `/api/market-insights` request and has an in-flight guard; max five numeric-ranked industry entries and five upstream-ranked news-interest stocks. `fetchHomeNews()` performs only `/news?limit=10`, with independent guard/loading/error/empty states. `fetchWarData()` performs only `/auto_news` after the button is activated. Removed the redundant macro fetch on landing-animation completion; landing animation, entry and auth/navigation behavior are preserved. Other analysis pages and existing calendar behavior are not rewritten.

Helper seams for targeted tests: `homeFinite`, `homeTimestamp`, `homeDateLabel`, `homeNewsItems`, `homeAIBlocks`, `homeAIPreviewBlocks`, `appendHomeAIText`, `renderHomeAI`, `homeIndicatorHtml`, and the three independent loaders. Timestamp formatting uses explicit Asia/Taipei. Missing, malformed, future or timezone-ambiguous news timestamps remain unknown; valid dates sort newest first, undated rows follow in original order and at most ten are rendered. No refresh-time fallback is used. Market dates, news publish dates and AI generation dates are separate; no realtime or fixed pre/post-market claim is added.

AI contract: first three original paragraph/list content blocks retain their adjacent headings; headings do not consume the three-content-block limit. Fixed h3/h4/h5, p, ul/ol, li and strong elements contain only text nodes or textContent. Whole-line bold headings and paired inline bold are rendered through fixed elements, without raw HTML or Markdown links. No arbitrary HTML, inline event handler, unsafe link or extra rewriting request is accepted. Every original character remains available in the native full-original disclosure, including Markdown syntax. No summarization/truncation discards the original source text. Full disclosure is keyboard operable.

Homepage stock entries are native buttons with escaped ticker attributes and registered click listeners. Only manual activation fills the existing quick-search field and enters its existing chart/analysis flow; loading or refreshing the overview never requests per-stock analysis.

Macro contract: Taiwan weighted index is primary; SOX, S&P500 and VIX are compact companions. Remaining supplied indicators stay in native details. Missing/nonfinite/blank/invalid price or change values display a dash, not synthetic zero. Existing source/as-of data remains visible and the UI states these are latest available daily observations, not realtime quotes.

### Known limitations

- Overview trending data does not supply a single publish/update timestamp; homepage explicitly says this rather than substituting browser time.
- Existing /news summaries can be shortened by the backend RSS reader; this frontend preserves the supplied summary and original source link, without claiming the RSS excerpt is the complete article.
- Targeted behavior, viewport/function smoke and precommit full regression passed. Final committed full gate, independent review and deployment remain pending.

## Test evidence

| Acceptance criterion | Test case or check | Result | Evidence |
| --- | --- | --- | --- |
| AC-01 | Actual tests/home_overview_checks.cjs macro helper plus Lead viewport smoke | PASS | Four main indicators plus native remaining four; null/nonfinite values dash, source-derived dates. |
| AC-02 | Actual overview fakeDOM/request cases and browser fixture | PASS | Initial overview exactly1; Top5 industries/Top5 news interest; no per-stock automatic calls; partial failure independent. |
| AC-03 | Actual news loader/date/limit/safe-link cases and browser counters | PASS | Initialnews1/AI0; refreshnews2/overviewunchanged; latest10 sorted; real safe source links and independent errors. |
| AC-04 | Actual block renderer/fold cases and native browser disclosure | PASS | Three content blocks with adjacent headings; exact full original retained; AI only manual1; complete native disclosure. |
| AC-05 | Malicious fake AI text and source-date tests plus browser DOM | PASS | No img/script nodes0, text-node bold/list/heading safe; Taipei dates explicit and not refresh time. |
| AC-06 | Enter2330 and all ten navigation pages; calendar keyboard smoke | PASS | 2330.TW enters existing Kline; calendar6+2 all8events Enteropens, officialHTMLsources; mobile sidebar closes. |
| AC-07 | 1440/375 mock-only browser and partial news503/empty industry fixture | PASS | All ten pages overflowfalse; visible homepage controls inbounds; prose17px/h3 20px; macro/trending/calendar remain usable. |
| AC-08 | Offline Node behavior plus required precommit quality_gate | Precommit PASS; formal review pending | 42Pythoncompiled;156tests155pass1existingWindows skip. Final same-clean-HEAD gate/review external reports required. |

### Full regression

- Command: `python scripts/quality_gate.py`
- Exit code: Precommit0; final committed gate supplied externally.
- Summary: Precommit42 Python files compiled;156 tests ran,155 passed and1 existing Windows skip. Initial legacy string-assert failure was fixed by updating test assertions while retaining safety checks, then full gate rerun passed. No production modification by Tester.

## Review evidence

- Correctness:
- Security:
- Performance:
- Maintainability:
- Blocking-issue count: Pending independent exact-tested-commit formal review; final count external.
- Non-blocking findings and disposition:

| Severity | File and line | Reason | Blocking | Disposition |
| --- | --- | --- | --- | --- |
|  |  |  |  |  |

## Manual operations

- After new gates pass, deploy the tested/reviewed frontend revision and refresh the browser; no new environment variables, SQL migration or user data entry is needed for this slice.

## Risks

- External data/AI sources may fail independently; each homepage region reports its own unavailable state and does not block the others.

## Gate status

- [ ] Acceptance gate: all criteria pass.
- [ ] Test gate: feature tests and full regression pass.
- [ ] Review gate: blocking-issue count is zero.
- [x] Manual deployment, database, and environment steps are documented.

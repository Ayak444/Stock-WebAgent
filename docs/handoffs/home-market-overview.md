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

- [ ] AC-09: Numeric point/date/money/quantity contexts and publisher names do not become stock mentions; explicit ticker/ETF/TW suffix/real company positives and mixed valid-invalid matches retained;72h/dedup/score/order/compiled-pattern performance preserved.

AC-04/05 postdeployment regression: only the heading-match line copy is trimmed; trailing-space/CRLF bold and hash headings remain headings, not three content-block quota. Exact full original text including whitespace/newlines is retained. Generated-time investigation is separate and not part of this bounded correction.

## Stage ownership

| Stage | Owner | Status | Started | Completed | Notes |
| --- | --- | --- | --- | --- | --- |
| Product | /root/dashboard_fix_supervisor/product | Complete |  |  |  |
| Developer | /root/polish_completion_supervisor/developer_fix | Bounded review fix complete; frozen for Tester |  |  | Sole production/handoff writer; no test files changed or formal tests run. |
| Tester | Fresh Tester appointed by /root/polish_completion_supervisor | Pending necessary regressions and full gate |  |  | Must add compound positives and quantity negative, then independently verify the new identity. |
| Reviewer | Fresh independent Reviewer appointed by /root/polish_completion_supervisor | Mandatory re-review pending fixed committed Tester PASS |  |  | Must review exact clean tested commit; earlier pass evidence cannot certify this fix. |

## Confirmed review rework: financial stock compounds

This section supersedes all earlier gate status for the current revision. Reviewer found one blocking P2 at `market_insights.py:83` on clean commit `47a0e9cd8575ecfe74531a3df3a6d85edc6d3d1d`: bare 股 in the quantity pattern rejected legitimate ticker mentions before 股價, 股票 and 股利 (including whitespace). AC-09/V-09 therefore failed despite the prior passing suite. Independent report: `C:/Users/Ayak4-PC/.codex/visualizations/2026/09/13/01a099ee-c132-7790-bae7-1702ec9ba186/polish-reviewer-final-report.md` and `.json`. Blocking count: 1; no additional findings.

Lead authorized the minimal correction and clarified that 股息, 股東, 股權 and 股本 are the same class. Developer changed only the compiled 股 alternative to `股(?![價票利息東權本])` and added an explanatory comment. Genuine `成交2330股` still reaches the quantity rejection; whitespace remains handled by the existing prefix. Other point/date/money/quantity alternatives, suffix/company/ETF/separator behavior, 72-hour window, deduplication, scoring, order and pattern compilation are unchanged. `static/index.html` remains byte-identical to the review baseline.

Current rework changed files: `market_insights.py`, `docs/handoffs/home-market-overview.md`, `docs/handoffs/home-visual-polish.md`. Developer basic validation: in-memory AST parse (no imports/network/environment access) exit 0; `git diff --check --ignore-submodules=dirty` exit 0. No formal tests executed or test files modified. Known limitation: regression and review gates remain pending; this implementation is not a completion declaration. Required manual operation after passing gates: deploy the tested/reviewed revision and refresh the browser; no environment, database, migration or data-entry steps.

Freeze protocol: Developer saves both handoffs, freezes all repository writes and supplies raw staged/unstaged binary-patch SHA-256 hashes plus compact sorted untracked manifest/manifest hash externally. Tester adds only necessary meaningful regressions (seven compounds with/without whitespace and genuine share-quantity negatives), independently captures the new identity and runs the full offline quality gate. Lead commits approved task files; final Tester reruns the full gate and Reviewer independently reviews that same clean fixed commit. Immutable evidence stays external; no post-gate handoff changes or self-hash recursion. HEAD/index gitlink remains `160000 aed9cfd3277740755f6bfc1155c7aa645403b760`; no submodule writes.

| Acceptance criterion | Required case/check | Current result |
| --- | --- | --- |
| AC-09 / V-09 | 股價/股票/股利/股息/股東/股權/股本 with and without ticker whitespace; genuine `成交2330股` negative; prior ranking regressions | Developer fix applied; fresh Tester evidence pending |
| AC-08 / V-10 | Full offline regression on fixed revision, then same-commit zero-blocking independent review | Pending; previous evidence invalidated for changed revision |

## Historical test-stage role exception

Existing Tester follow-up was rejected by agent thread limit both during independent planning and after Developer freeze. Under the existing explicit user authorization, Lead /root assumed Tester ownership, wrote only test files and executed offline fake-data behavior and browser checks. Developer remained the only production writer and stopped before that stage. Supervisor only coordinates and records this handoff; independent Product-as-Reviewer is required/preferred for the final passing revision.

## Immutable final evidence protocol

This is a precommit implementation and tested acceptance snapshot. Lead commits frontend, tests and this handoff together; final full quality-gate output and Reviewer findings are then supplied as immutable external reports against the same clean committed HEAD. Identity includes HEAD, both binary-patch hashes and sorted untracked manifest hash. No later handoff edit inserts its own commit hash. Any source change invalidates downstream formal evidence. Earlier revision evidence is never substituted for the new final gate.

## Postdeployment bounded rework

Current ownership supersedes the historical fallback below: fresh Supervisor-appointed Tester passed this candidate; a fresh independent Reviewer follows the final clean-commit gate. Lead remains responsible for commit/publication.

Published497f926 homepage/CI/source equality passed, but real news reproduced1236 index-points and 工商時報 publisher false mentions; real AI also used trailing-space bold headings. This rework adds AC-09 and existing AC-04/05 regression only. Previous gates do not serve as final gates for any changed revision. Product read-only criteria completed; Developer is sole source writer, Root is test-only owner, independent Product-as-Reviewer follows exact committed full gate. No API/source/LLM/database expansion.

Correction baseline:497f9262d272adf0aaa5636c0e433eee643c82ba. Changed files: `market_insights.py`, `static/index.html`, and this handoff. The ranker scans all occurrences of the existing compiled ticker pattern, rejects point/date/currency/quantity contexts, and accepts explicit .TW/.TWO suffixes. Publisher-only 時報 requires an explicit ticker or adjacent company context (文化/出版/公司/董事/營收/獲利/股價/股票); 工商時報 alone does not match. Original 72-hour filtering, article deduplication, once-per-stock scoring, weights, ordering, limit and API shape remain unchanged. Patterns stay compiled outside article/profile loops. Other stock-attention APIs are outside this bounded correction.

AI heading recognition uses a trimmed line copy only. Paragraph/list source lines and the original string used in the full disclosure retain their existing whitespace/newlines. Preview headings still do not consume the first-three-content-block quota. No rendering safety or request behavior changes.

Developer validation for this correction: in-memory Python AST parse, Node inline-JavaScript syntax check and `git diff --check` pass. New AC-09 and AC-04/05 regression results, full quality gate and independent review are pending on the newly committed revision. Source hashes are supplied externally at freeze; do not reuse preceding homepage gates. Deployment after new gates requires only the tested code rollout; no environment, SQL or manual data changes.

## Revision identity

- Baseline commit:497f9262d272adf0aaa5636c0e433eee643c82ba
- Developer HEAD commit:47a0e9cd8575ecfe74531a3df3a6d85edc6d3d1d (current review-rework baseline)
- Staged patch SHA-256:
- Unstaged patch SHA-256:
- Untracked files and content SHA-256 manifest:
- Tested source-state ID (HEAD plus all three hashes):
- Reviewed source-state ID (HEAD plus all three hashes):
- Shared-workspace writer: /root/polish_completion_supervisor/developer_fix frozen after the production fix and both handoffs; Tester becomes sole test-file writer next, then Lead commits and fresh committed gates follow.

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
- Fresh targeted behavior and Lead browser checks pass;42compiles/157tests/one existing skip pass. Final clean committed gate, independent review and deployment remain pending.

## Test evidence

Fresh Tester /root/polish_completion_supervisor/tester retained the existing test-only changes and independently verified this complete candidate. Prior results below are superseded by these fresh checks; final clean-commit gate and independent review are still required.

| Acceptance criterion | Test case or check | Result | Evidence |
| --- | --- | --- | --- |
| AC-01 | Actual Node macro helper plus Lead five-width browser | PASS | Four main indicators/remaining native disclosure; invalid values dash; source-derived dates and price semantics. |
| AC-02 | Actual overview fakeDOM/request tests and Lead browser | PASS | Initial overview1; topfive industries/stocks; no automatic per-stock calls; independent missing states. |
| AC-03 | Actual news loader/date/limit/safe-link tests and Lead browser | PASS | Initial news1/AI0; news-only refresh; newest valid timestamps first/max10; safe links; long prose intact. |
| AC-04 | Actual block/heading/whitespace/full-original cases and browser Enter | PASS | Three content blocks and adjacent headings; trailing-space/CRLF heading copy recognized; exact full original retained; AI manual only. |
| AC-05 | Actual malicious-text renderer and Taipei date tests | PASS | Fixed safe elements/text nodes; no arbitrary HTML or unsafe links; browser img/script nodes0; separate source dates. |
| AC-06 | Lead Enter2330, ten-page navigation and calendar keyboard smoke | PASS | Existing2330.TW analysis entry; all8calendar events/official HTML sources; mobile sidebar closes. |
| AC-07 | Fake region failures plus Lead five-width/long/native disclosure checks | PASS | News503/empty industry independent; all controls in bounds/no document overflow; focus/Enter retained. |
| AC-08 | Actual offline Node plus complete gate and independent identity | Precommit PASS; final committed gate/review pending |42Python compiles/157tests/one existing skip; no source writes during fresh Tester stage. |
| AC-09 |25 offline market tests and compiled-pattern inspection | PASS | Reject numeric points/dates/money/quantity and publisher-only工商時報; preserve valid bare/.TW/.TWO/ETF/company/list separators;72h boundary/dedup/order unchanged; patterns compile before article loops. |

### Full regression

- Command: python scripts/quality_gate.py through the repository offline wrapper using the prepared test-only Python runtime.
- Precommit exit code:0; final clean-commit rerun is required.
- Runtime: C:/Users/Ayak4-PC/AppData/Local/Temp/stock-webagent-polish-quality-venv/Scripts/python.exe (Python3.12.10), isolated test-only environment. Sandbox asyncio initialization was an execution-environment limitation, not a reproduced production defect.
- Summary:42 Python files compile;157tests run in9.919s; OK(skipped=1). Actual Node homepage/motion harness and25 targeted market tests also pass. The skip is the existing Windows subprocess restriction case.
- External acceptance matrix: C:/Users/Ayak4-PC/.codex/visualizations/2026/09/13/01a099ee-c132-7790-bae7-1702ec9ba186/polish-tester-precommit-acceptance.md. Raw logs use polish-tester-precommit-host-{node,market-targeted,quality-gate}.log in the same directory.157tests means156passed and1skipped; Tester reported zero blocking defects.
- Sandbox invocation stalled at the AST-only asynchronous endpoint test; the identical offline gate completed normally on the host. Credential allowlisting, dotenv disablement and socket/DNS blocking remain active; no production credential or network is used.

Fresh precommit source identity independently recomputed before and after checks and matched to Lead: HEAD497f9262d272adf0aaa5636c0e433eee643c82ba; staged patch SHA-256e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855; unstaged patch SHA-256f69a8022fb7454699c834ec49d493637d4ff9419205bec20e392cc9de950540b; sorted untracked manifest SHA-2567111c68e4cd05e563d862668658e50be4b8a4eea0ed0bd4caf690d727076d4a1. The only untracked entry is docs/handoffs/home-visual-polish.md with SHA-256b825233838c66689883f808ea162d2fb030296a006932e70858ac1a1a054dc83. Canonical manifest is compact UTF-8 JSON with sorted paths, each object inserts path then sha256, and no final newline. Raw binary patches use --ignore-submodules=dirty, which includes any changed gitlink revision. Existing GSAP gitlink remains160000 aed9cfd3277740755f6bfc1155c7aa645403b760 in HEAD and index.

These hashes identify the candidate before this evidence-only handoff update. Lead commits exactly the six task files; final Tester reruns the complete gate and Reviewer reviews that same clean commit. Immutable final reports remain external to avoid self-hash recursion or later source edits. Precommit external report: C:/Users/Ayak4-PC/.codex/visualizations/2026/09/13/01a099ee-c132-7790-bae7-1702ec9ba186/polish-tester-precommit-host-report.json.

## Review evidence

- Correctness:
- Security:
- Performance:
- Maintainability:
- Blocking-issue count: 1 confirmed P2 on 47a0e9c; Developer fix applied, mandatory fresh independent re-review pending. Final fixed-commit count is external.
- Non-blocking findings and disposition:

| Severity | File and line | Reason | Blocking | Disposition |
| --- | --- | --- | --- | --- |
| P2 | market_insights.py:83 (reviewed 47a0e9c) | Bare 股 quantity alternative rejected legitimate financial compounds after tickers. | Yes | Fixed by bounded negative lookahead; fresh regression and re-review pending. |

## Manual operations

- After new gates pass, deploy the tested/reviewed frontend revision and refresh the browser; no new environment variables, SQL migration or user data entry is needed for this slice.

## Risks

- External data/AI sources may fail independently; each homepage region reports its own unavailable state and does not block the others.

## Gate status

- [ ] Acceptance gate: all criteria pass.
- [ ] Test gate: feature tests and full regression pass.
- [ ] Review gate: blocking-issue count is zero.
- [x] Manual deployment, database, and environment steps are documented.

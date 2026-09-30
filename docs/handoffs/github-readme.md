# Agent Handoff: GitHub project README

## Work definition

- Objective: Add a root README that explains the deployed Stock-WebAgent to GitHub visitors and links to the working site.
- In scope: Traditional Chinese documentation of implemented features, live/source links, setup, configuration, and limitations.
- Out of scope: Production code, database/schema changes, deployment actions, the Vite template README, and unsupported feature claims.
- Assumptions: Root `main.py` and `static/index.html` are the deployed application; `render.yaml` defines the web service. Live links were confirmed HTTP 200 by Lead before this stage; Render cold starts may delay later requests.
- Dependencies: `.env.example`, `render.yaml`, `MANUAL_SETUP.md`, migration files, and source code for feature evidence.

## Acceptance criteria

- [x] AC-01: A root `README.md` in Traditional Chinese introduces the production app and only code-evidenced implemented features.
- [x] AC-02: Prominent links lead to `https://taiwan-stock-bot-urn9.onrender.com/` and `https://github.com/Ayak444/Stock-WebAgent`.
- [x] AC-03: Local/Render setup is concise and points to placeholder configuration, deployment and migrations without including credentials; account Discord alerts are presented as conditional.
- [x] AC-04: Caveats disclose delayed daily data, Groq dependency, disabled-by-default alerts, incomplete backtest factors and Render Free scheduling limitations.
- [x] AC-05: Markdown relative links target existing files and the README avoids stale runtime readiness claims.

## Stage ownership

| Stage | Owner | Status | Started | Completed | Notes |
| --- | --- | --- | --- | --- | --- |
| Product | Supervisor's Product Agent | Complete | Before Developer | Before Developer | Numbered criteria handed to Developer. |
| Developer | readme_supervisor/readme_developer | Complete; handoff amendment after review | This task | This task | Sole documentation writer; corrected README wording, then updated stale handoff evidence. |
| Tester | readme_supervisor/readme_tester | Completed on committed `87734a3`; post-amendment repeat required | After Developer | Before post-commit review | Mapped AC-01–05 and passed the full offline gate; will recompute amended source identity. |
| Reviewer | readme_supervisor/readme_reviewer | Completed review of committed `87734a3`; post-amendment re-review required | After Tester | After Tester | Pre-commit README re-review had zero blockers; post-commit review found one blocking stale-handoff issue, addressed by this amendment. |

## Revision identity

- Baseline commit: `2abeb91` (`Improve volume settings and AI failure diagnostics`).
- Local README and initial handoff commit: `87734a325b8b323126f8e7a9969c5b3690af6a56`.
- Developer HEAD for this amendment: `87734a325b8b323126f8e7a9969c5b3690af6a56`.
- Staged patch SHA-256: Published separately to Supervisor after this handoff is static.
- Unstaged patch SHA-256: Published separately to Supervisor after this handoff is static.
- Untracked files and content SHA-256 manifest: Published separately to Supervisor after this handoff is static.
- Prior committed tested and reviewed source identity: Clean HEAD `87734a325b8b323126f8e7a9969c5b3690af6a56`; Reviewer reported one blocking handoff issue.
- Post-amendment tested source-state ID: Tester publishes the exact HEAD/patch/manifest identity separately to Supervisor.
- Post-amendment reviewed source-state ID: Reviewer independently publishes the same identity and verdict separately to Supervisor.
- Shared-workspace writer: Developer only during documentation implementation.

The identity is HEAD plus SHA-256 of staged binary patch, unstaged binary patch, and a stable path/content-hash manifest of all untracked files. Tester and Reviewer recompute independently. To avoid a self-referential hash, this file stays unchanged after the Developer amendment; exact post-amendment gate identities and final committed-HEAD evidence are recorded in separate Supervisor messages, not by changing this already tested file.

## Developer handoff

### Changed files

| File | Purpose |
| --- | --- |
| `README.md` | GitHub-facing project description, links, setup and limitations. |
| `docs/handoffs/github-readme.md` | Governance handoff and gate record. |

### Commands and results

| Command | Exit code | Result |
| --- | ---: | --- |
| `rtk git status --short --branch` | 0 | Clean baseline at `main` before edits. |
| `rtk rg --files` and focused `rtk rg -n` queries | 0 | Verified paths, UI features, source behavior and backtest caveats. |
| `rtk read README.md` | 0 | Confirmed new Markdown content. |
| `rtk git rev-parse HEAD` | 0 | Confirmed committed README/handoff baseline `87734a3` before this amendment. |

### Known limitations

- Documentation only; no production behavior or live account state changed.
- Online links may be delayed by Render Free cold start.

## Test evidence

| Acceptance criterion | Test case or check | Result | Evidence |
| --- | --- | --- | --- |
| AC-01 | Check claims against root app/UI and feature modules | Pass on `87734a3` | Source and UI inspection; README wording corrected from historical-change claim to current holding-ratio snapshot. |
| AC-02 | Verify required URLs in root README | Pass on `87734a3` | Live demo and GitHub links present; Lead confirmed HTTP 200 before publication. |
| AC-03 | Verify local paths and no credentials | Pass on `87734a3` | Relative paths resolve; `.env.example` placeholders and conditional alert setup; no secret values. |
| AC-04 | Check limitations against implementation | Pass on `87734a3` | Backtest, routing and alert caveats match source, including optional global versus personal Discord alerts. |
| AC-05 | Check relative links resolve and no runtime-ready assertion | Pass on `87734a3` | Repository link inspection; no assertion that private live configuration is healthy. |

### Full regression

- Command: `python scripts/quality_gate.py` under isolated temporary Python 3.12.10.
- Exit code: 0 on committed `87734a3`.
- Summary: 37 Python files compiled in memory; 123 tests passed, one existing Windows skip. Tester independently verified source identity. The post-amendment full gate and final committed-HEAD repeat are reported separately by Supervisor.

## Review evidence

- Correctness: README feature claims and links reviewed; earlier claim of historical large-holder change was corrected to current holding-ratio snapshot before commit. The committed handoff had stale status fields, which this amendment updates.
- Security: Documentation contains no credential values and directs backend-only secret handling.
- Performance: Documentation-only change; no runtime performance effect.
- Maintainability: Root README separates personal and global alert configuration; handoff records stages and external evidence protocol.
- Blocking-issue count: 1 in the Reviewer report on committed `87734a3` (stale handoff evidence). Post-amendment count awaits re-review and is not claimed here.
- Non-blocking findings and disposition: No additional actionable findings reported in the cited review.

| Severity | File and line | Reason | Blocking | Disposition |
| --- | --- | --- | --- | --- |
| P2 | `docs/handoffs/github-readme.md`:23–27, 35–40, 65–90, 100–105 in `87734a3` | Stages, test matrix and gates still marked pending after completed work. | Yes | Developer amended this handoff; Tester must rerun full gate and Reviewer must re-review exact amended state. |

## Manual operations

- The README was committed locally as `87734a3`. After the amendment passes the full gate and re-review, commit and push the final reviewed state to the repository's default branch. No database or Render environment change is required for documentation itself.
- The README's instructions describe optional operations needed for corresponding live features; users must configure their own secret values privately.

## Risks

- Public app availability and specific feature readiness depend on Render and private service configuration; README intentionally does not assert every feature is currently healthy.

## Gate status

- [x] Acceptance gate: AC-01–05 passed on committed `87734a3`; the amendment changes only historical handoff evidence.
- [x] Test gate: full offline regression passed on committed `87734a3`; amendment/final-commit repetitions are reported separately and required before Lead completion.
- [ ] Review gate: committed `87734a3` had one blocking handoff finding; post-amendment zero-blocker re-review is required and reported separately.
- [x] Manual deployment, database, and environment steps are documented for readers.

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
| Developer | readme_supervisor/readme_developer | Complete; awaiting Tester | This task | This task | Sole writer for README and this handoff. |
| Tester | readme_supervisor/readme_tester | Pending |  |  | Must independently calculate source identity and run full gate. |
| Reviewer | readme_supervisor/readme_reviewer | Pending |  |  | Must review the exact state Tester passed. |

## Revision identity

- Baseline commit: `2abeb91` (`Improve volume settings and AI failure diagnostics`).
- Developer HEAD commit: `2abeb91`.
- Staged patch SHA-256: Published separately to Supervisor after this handoff is static.
- Unstaged patch SHA-256: Published separately to Supervisor after this handoff is static.
- Untracked files and content SHA-256 manifest: Published separately to Supervisor after this handoff is static.
- Tested source-state ID: Pending Tester calculation.
- Reviewed source-state ID: Pending Reviewer calculation.
- Shared-workspace writer: Developer only during documentation implementation.

The identity is HEAD plus SHA-256 of staged binary patch, unstaged binary patch, and a stable path/content-hash manifest of all untracked files. Tester and Reviewer recompute independently. This file stays unchanged after the Developer handoff so later checks apply to the same source state.

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

### Known limitations

- Documentation only; no production behavior or live account state changed.
- Online links may be delayed by Render Free cold start.

## Test evidence

| Acceptance criterion | Test case or check | Result | Evidence |
| --- | --- | --- | --- |
| AC-01 | Check claims against root app/UI and feature modules | Pending Tester | Source review. |
| AC-02 | Verify required URLs in root README | Pending Tester | Markdown inspection. |
| AC-03 | Verify local paths and no credentials | Pending Tester | File/link inspection. |
| AC-04 | Check limitations against implementation | Pending Tester | Backtest, routing, alerts. |
| AC-05 | Check relative links resolve and no runtime-ready assertion | Pending Tester | Repository files. |

### Full regression

- Command: `python scripts/quality_gate.py`
- Exit code: Pending Tester.
- Summary: Pending Tester.

## Review evidence

- Correctness: Pending Reviewer.
- Security: Pending Reviewer.
- Performance: Pending Reviewer.
- Maintainability: Pending Reviewer.
- Blocking-issue count: Pending Reviewer.
- Non-blocking findings and disposition: Pending Reviewer.

## Manual operations

- To publish this README on GitHub, commit and push the reviewed files to the repository's default branch. No database or Render environment change is required for documentation itself.
- The README's instructions describe optional operations needed for corresponding live features; users must configure their own secret values privately.

## Risks

- Public app availability and specific feature readiness depend on Render and private service configuration; README intentionally does not assert every feature is currently healthy.

## Gate status

- [ ] Acceptance gate: awaiting Tester evidence for every criterion.
- [ ] Test gate: awaiting full offline regression.
- [ ] Review gate: awaiting zero blocking findings.
- [x] Manual deployment, database, and environment steps are documented for readers.

# Agent Handoff: <feature name>

## Work definition

- Objective:
- In scope:
- Out of scope:
- Assumptions:
- Dependencies:

## Acceptance criteria

- [ ] AC-01:
- [ ] AC-02:

## Stage ownership

| Stage | Owner | Status | Started | Completed | Notes |
| --- | --- | --- | --- | --- | --- |
| Product |  | Not started |  |  |  |
| Developer |  | Not started |  |  |  |
| Tester |  | Not started |  |  |  |
| Reviewer |  | Not started |  |  |  |

## Revision identity

- Baseline commit:
- Developer HEAD commit:
- Staged patch SHA-256:
- Unstaged patch SHA-256:
- Untracked files and content SHA-256 manifest:
- Tested source-state ID (HEAD plus all three hashes):
- Reviewed source-state ID (HEAD plus all three hashes):
- Shared-workspace writer:

The staged hash covers `git diff --cached --binary`, and the unstaged hash covers `git diff --binary`. The untracked manifest lists every untracked path and its content hash in stable path order, then records the manifest hash. Empty patches still receive the SHA-256 of empty content. Do not use a timestamp as source identity. Tester and Reviewer must independently recompute the source-state ID; both IDs must match the Developer handoff state.

## Developer handoff

### Changed files

| File | Purpose |
| --- | --- |
|  |  |

### Commands and results

| Command | Exit code | Result |
| --- | ---: | --- |
|  |  |  |

### Known limitations

- None recorded.

## Test evidence

| Acceptance criterion | Test case or check | Result | Evidence |
| --- | --- | --- | --- |
| AC-01 |  | Pending |  |

### Full regression

- Command: `python scripts/quality_gate.py`
- Exit code:
- Summary:

## Review evidence

- Correctness:
- Security:
- Performance:
- Maintainability:
- Blocking-issue count:
- Non-blocking findings and disposition:

| Severity | File and line | Reason | Blocking | Disposition |
| --- | --- | --- | --- | --- |
|  |  |  |  |  |

## Manual operations

- None recorded.

## Risks

- None recorded.

## Gate status

- [ ] Acceptance gate: all criteria pass.
- [ ] Test gate: feature tests and full regression pass.
- [ ] Review gate: blocking-issue count is zero.
- [ ] Manual deployment, database, and environment steps are documented.

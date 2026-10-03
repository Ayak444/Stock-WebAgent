# Agent Handoff: AI completion compatibility

## Work definition

- Objective: Correct bounded compatible AI completion request settings for the existing malformed empty response failure.
- In scope: Existing gateway payload compatibility for two verified GPT-OSS models, strict final response validation and fixed incomplete-response error.
- Out of scope: UI layout rewrite, database, credentials, raw provider bodies, chain-of-thought exposure, indiscriminate token increases or automatic retry sends.
- Assumptions: A reasoning/completion budget interaction is a plausible cause of the live empty content; it is not established as the root cause.
- Dependencies: Lead verified Groq reasoning documentation and API reference: GPT-OSS low/medium/high reasoning effort, include_reasoning false, max_completion_tokens includes reasoning; no reasoning_format for these models.

## Acceptance criteria

- [ ] AC-01: Only verified GPT-OSS20b/120b gets low reasoning_effort/include_reasoning=false and bounded max_completion_tokens4096 cap; other models retain1500 and no exclusive params; model env precedence/JSON/messages preserved; caller cannot override budget.
- [ ] AC-02: Accept only nonempty final content; no reasoning-field fallback/exposure/log; reject malformed/empty/reasoning-only and finish_reason length with fixed safe incomplete code.
- [ ] AC-03: Preserve single provider attempt, lock/timeout/circuit/auth/rate-limit/JSON validation; no raw prompt/key/body leakage or auto resend; news dates unchanged.
- [ ] AC-04: Minimal gateway/doc changes; external fail honest and inference not confirmed; new revision targeted compatibility/privacy plus fullqualitygate+zero review blockers; Lead live validation required before claiming live repair.

## Stage ownership

| Stage | Owner | Status | Started | Completed | Notes |
| --- | --- | --- | --- | --- | --- |
| Product | /root/dashboard_fix_supervisor/product | Complete |  |  |  |
| Developer | /root/dashboard_fix_supervisor/developer | Complete; frozen pending gates |  |  | Only gateway and this handoff changed; no tests run or edited. |
| Tester | /root/dashboard_fix_supervisor/safeguards_tester | Targeted PASS; committed full gate pending |  |  | Targeted request/privacy/response cases and exact new revision full gate. |
| Reviewer | /root/dashboard_fix_supervisor/product (Reviewer role) | Pending exact tested revision |  |  | Review newly tested revision; earlier gates invalid. |

## Immutable final evidence protocol

This is a precommit implementation and targeted-validation snapshot. Formal full-gate and Reviewer evidence are pending at capture and will be supplied as immutable external reports against the same clean committed HEAD. Lead explicitly commits only gateway, approved diagnostics test and handoff; Tester recomputes identity and runs full offline quality_gate, then Reviewer independently verifies and reviews that exact passing revision. No later handoff edit inserts its own commit hash. Any source change invalidates downstream evidence. Live post-deployment result is separate from offline acceptance, and the original provider cause remains an inference.

## Revision identity

- Baseline commit: 8a981dc96785475d00ca97c87011e4d0a006fb4e
- Developer HEAD commit: 8a981dc96785475d00ca97c87011e4d0a006fb4e
- Staged patch SHA-256:
- Unstaged patch SHA-256:
- Untracked files and content SHA-256 manifest:
- Tested source-state ID (HEAD plus all three hashes):
- Reviewed source-state ID (HEAD plus all three hashes):
- Shared-workspace writer: Developer until freeze; then test-only writer after identity verification.

Source hashes are supplied in the coordination message after saving this handoff, avoiding recursive document hashes. Lead excluded the unrelated temporary .tmp.driveupload directory using local Git metadata only; Developer did not read, copy, delete, move or stage its contents. Final identity covers all unignored untracked task files.

The staged hash covers `git diff --cached --binary`, and the unstaged hash covers `git diff --binary`. The untracked manifest lists every untracked path and its content hash in stable path order, then records the manifest hash. Empty patches still receive the SHA-256 of empty content. Do not use a timestamp as source identity. Tester and Reviewer must independently recompute the source-state ID; both IDs must match the Developer handoff state.

## Developer handoff

### Changed files

| File | Purpose |
| --- | --- |
| route_gateway.py | Exact model-specific bounded settings; strip caller budget/reasoning parameters; reject length-truncated results using static error. |
| docs/handoffs/ai-completion-compatibility.md | Approved request/response contract, evidence limits and deployment steps. |

### Commands and results

| Command | Exit code | Result |
| --- | ---: | --- |
| Python AST parse of route_gateway.py | 0 | Syntax passes without imports, network or production credentials. |
| git diff --check | 0 | No whitespace errors. |

Payload contract: only exact `openai/gpt-oss-20b` and `openai/gpt-oss-120b` receive `reasoning_effort=low`, `include_reasoning=false`, `max_completion_tokens=4096`. Other models receive `max_tokens=1500`; no GPT-OSS-specific parameters are sent. Caller `max_tokens`, `max_completion_tokens`, `reasoning_effort`, `include_reasoning`, and `reasoning_format` are removed before server parameters are set. Existing environment model priority, messages and JSON response_format are retained. No new environment variable exists.

Response contract: only nonempty string `choices[0].message.content` is accepted. `finish_reason=length` is rejected even with nonempty content as `ai_incomplete_response` and the fixed Chinese message “AI 回覆尚未完成，請稍後再試”. Reasoning fields are never used, returned or logged. Malformed choice objects still become the static malformed-response error. There is one HTTP request per attempt, unchanged lock acquisition and `(5,30)` timeouts, no automatic resend, and unchanged circuit/auth/rate handling. Incomplete responses increment the existing failure counter and do not reset it as success.

### Known limitations

- Hiding reasoning output does not disable internal reasoning; the 4096-token budget includes both reasoning and final completion.
- This parameter change may improve completion but does not prove the previous live error's cause or guarantee success. Lead must check live auto_news after tested/reviewed deployment before claiming resolution.
- No prompt, provider body, API key, reasoning field or environment contents were read for implementation or syntax validation.

## Test evidence

| Acceptance criterion | Test case or check | Result | Evidence |
| --- | --- | --- | --- |
| AC-01 | test_completion_policy_uses_exact_server_model_and_preserves_request | Targeted PASS | Five model cases, exact caps/reasoning flags, stripped caller knobs, unchanged messages/JSON and input payload. |
| AC-02 | test_reasoning_only_empty_and_truncated_replies_fail_once_without_leaks plus malformed/success fixtures | Targeted PASS | Null/whitespace/reasoning-only/truncated rejection, fixed error, final content only, one call and private markers absent. |
| AC-03 | Busy lock, success/timeout/auth/rate/circuit cases and real client/summary error forwarding | Targeted PASS | Incomplete responses participate in three-failure circuit; original once-post and timeout behavior preserved. |
| AC-04 | Targeted cases/full quality gate/zero exact-revision blockers plus live auto_news validation | Pending | Lead commits final source/tests before formal gate and reviewer. |

### Full regression

- Command: `python scripts/quality_gate.py`
- Exit code:
- Summary: Pending exact committed full gate. Targeted diagnostics19 plus routing9 passed28/28 under offline test-only configuration.

## Review evidence

- Correctness:
- Security:
- Performance:
- Maintainability:
- Blocking-issue count: Pending exact tested-revision Reviewer report; final count supplied externally.
- Non-blocking findings and disposition:

| Severity | File and line | Reason | Blocking | Disposition |
| --- | --- | --- | --- | --- |
|  |  |  |  |  |

## Manual operations

- After new test/review gates pass, deploy the committed revision to the primary Render service and refresh/retry the AI summary once; Lead records the safe live result.
- No new environment variable, database migration or user-operated key entry is required for this gateway slice.

## Risks

- The GPT-OSS cap is bounded at4096 rather than1500; token usage can increase. Low reasoning effort and hidden reasoning output do not guarantee shorter latency or lower cost.
- Upstream service/configuration failures remain honestly reported; no reasoning fallback or partial result is presented as a completed summary.

## Gate status

- [ ] Acceptance gate: all criteria pass.
- [ ] Test gate: feature tests and full regression pass.
- [ ] Review gate: blocking-issue count is zero.
- [x] Manual deployment, database, and environment steps are documented.

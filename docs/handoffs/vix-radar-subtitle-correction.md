# Agent Handoff: VIX radar subtitle correction

## Work definition
- Objective: finish release copy consistency with the approved VIX 80% plus news 20% formula.
- Baseline commit: 5edd218df77171258451a0aebcfd7227e8b16f79.
- Scope: static/index.html:979 replaces the multiplication sign with a plus sign.
- Assumptions: original acceptance criteria and candidate evidence remain in dated-prices-and-vix-radar.md. Actual computation is already additive.
- Excluded: formula changes, refactors, dependencies, environment/database/resources, original checkout edits.

## Acceptance criteria
- AC-C01: Subtitle reads exactly VIX 80%＋財經新聞／消息 20%, consistent with the implemented weighted sum.
- AC-C02: Full offline quality gate passes on the final committed revision.
- AC-C03: Independent Reviewer binds the same tested committed revision and reports zero blocking issues.

## Stage ownership
| Stage | Owner | Status |
| --- | --- | --- |
| Product | Existing approved feature criteria; Lead confirmed copy scope | Complete |
| Developer | /root/final_release_supervisor/copy_developer | Copy edit frozen; scoped commit next |
| Tester | Independent role appointed after commit | Final committed full regression required |
| Reviewer | Independent role appointed after Tester passes | Exact tested committed review required |
| Supervisor | /root/final_release_supervisor | Owns only this addendum; coordinates gates |

## Developer handoff
- Production: static/index.html, one subtitle line only.
- Documentation: this Supervisor-owned addendum; original frozen handoff preserved.
- Developer verified clean baseline, exact replacement and one-insertion/one-deletion production diff.
- One writer at a time: Developer froze production before Supervisor created this addendum. Developer may commit these two paths unchanged after Supervisor releases ownership.
- No tests, dependencies or application bootstrap changes required.

## Revision and evidence protocol
- This addendum freezes before the scoped commit. Developer records final SHA and clean status in its immutable final message.
- Tester independently records before/after HEAD, staged binary patch SHA-256, unstaged binary patch SHA-256, stable all-untracked path/content manifest and combined identity.
- Reviewer independently recomputes those values and binds the same final committed revision.
- Immutable final role messages complete this record without modifying the tested commit. Changed HEAD invalidates downstream evidence.

## Acceptance-to-test matrix
| Criterion | Required evidence | Completion record |
| --- | --- | --- |
| AC-C01 | Exact subtitle assertion and scoped diff | Tester and Reviewer final messages |
| AC-C02 | Full python scripts/quality_gate.py, sanitized offline runner | Tester final message: exit, count, identities |
| AC-C03 | Exact-revision independent review | Reviewer final message: explicit blocking count |

## Gate status
- Acceptance gate: pending final role messages.
- Test gate: pending committed-version full regression.
- Review gate: pending independent exact-revision review.
- Prior revision results cannot substitute for final evidence.

## Manual operations, risks and limitations
- Lead alone publishes the release branch, waits for Linux CI, advances main with expected baseline lease, and verifies existing Render deployment.
- Existing feature limitations remain in dated-prices-and-vix-radar.md; this change corrects explanatory copy only.
- No new dependencies, environment variables, database operations, Render resources or production bootstrap required.
- Original dirty Documents checkout remains read-only. No role may read secrets or push/deploy.

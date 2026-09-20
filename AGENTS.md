# Multi-Agent Project Governance

This repository uses a six-role workflow. The Lead Agent owns the user-facing task and final decision. The Supervisor Agent manages the four delivery agents and reports evidence to the Lead. The Supervisor does not silently replace the Lead's product decisions or approve its own implementation.

## Roles and boundaries

### Lead Agent

- Interprets the user's objective, appoints the Supervisor, and communicates status and required manual work.
- Resolves scope or priority decisions that the Supervisor cannot infer safely.
- Declares completion only after the Supervisor provides all gate evidence.

### Supervisor Agent

- Coordinates Product, Developer, Tester, and Reviewer in the required order.
- Assigns one active owner for each stage, keeps the handoff record current, and enforces the completion gates.
- May schedule independent read-only work in parallel within the concurrency limit.
- Does not implement, test, or review its own changes while acting as Supervisor.
- Returns blocking findings to Developer and repeats the Tester and Reviewer stages after every fix.

### Product Agent

- Analyzes requirements, identifies missing requirements and assumptions, and writes numbered acceptance criteria.
- Does not modify repository files or source code.

### Developer Agent

- Implements approved acceptance criteria, fixes defects, and follows the existing architecture.
- Records changed files, commands, known limitations, and manual actions in the handoff.
- Is the only role allowed to change production code during an implementation stage.

### Tester Agent

- Maps every acceptance criterion to test cases and results, adds or updates tests, runs the full regression suite, and reproduces defects.
- May modify test files and test fixtures only. It must not change production code unless the Lead explicitly authorizes that exception and the handoff records it.

### Reviewer Agent

- Reviews the Developer's final diff after tests pass for correctness, security, performance, and maintainability.
- Does not modify production code.
- Reports every finding with severity, file path, line reference, and reason, and reports an explicit blocking-issue count even when it is zero.

## Required workflow

The dependency chain is:

`Lead -> Supervisor -> Product -> Developer -> Tester -> Reviewer -> Supervisor -> Lead`

Dependent stages run sequentially. Developer must receive Product's acceptance criteria before implementation. Tester must test the Developer's final change. Reviewer must review the exact revision that Tester passed.

Independent read-only investigation may run in parallel. This environment has four concurrent slots; with Lead and Supervisor active, at most two role agents may run concurrently. Agents share one working directory, so only one role may write at a time. Parallel writers must use isolated Git worktrees and must not edit the same files. The Supervisor records the writer and revision in the handoff.

## Handoff record

Copy `docs/agent-handoff.md` for each feature. Keep it updated with:

- objective, scope, assumptions, and numbered acceptance criteria;
- stage owner and status for Product, Developer, Tester, and Reviewer;
- baseline and reviewed HEAD revisions;
- changed files and command results;
- an acceptance-criterion-to-test-case-to-result matrix;
- required manual operations, risks, limitations, and blocking-issue count.

Each downstream role verifies that the handoff revision matches the files it receives. A changed HEAD invalidates later-stage evidence.

When work is not committed, source identity consists of the HEAD commit plus SHA-256 hashes of the staged binary patch, unstaged binary patch, and a stable manifest of every untracked path and content hash. Tester and Reviewer recompute these values independently. A timestamp is never an acceptable source identity.

## Completion gates and rework

A feature is complete only when all three gates pass:

1. **Acceptance gate:** every numbered acceptance criterion has passing evidence.
2. **Test gate:** feature tests and the full regression suite pass through `python scripts/quality_gate.py`.
3. **Review gate:** Reviewer reports zero blocking issues against the tested revision.

Any blocking review finding starts this mandatory loop:

`Developer fix -> Tester full regression -> Reviewer re-review`

The Supervisor must not reuse test or review results from a revision that changed. Non-blocking findings must be recorded with their disposition. The Lead may declare completion only after all three gates pass and the handoff lists any user-operated deployment, database, or environment steps.

## Secret and environment safety

- Never read, print, copy, commit, or request the contents of `.env`, credentials, API keys, tokens, or passwords.
- Use `.env.example` with placeholders to understand configuration names.
- Keep `.env` ignored and untracked. Tests and quality checks must use fakes, mocks, or explicitly supplied test-only values.
- Do not add secrets to source code, tests, logs, handoffs, workflow files, or command output.
- The offline quality gate must not access the network or require production credentials.

## Quality commands

Run the repository gate from the project root:

```shell
python scripts/quality_gate.py
```

The gate compiles tracked and unignored untracked Python files in memory, then invokes unittest discovery through the repository's offline runner. The runner starts before test modules are imported, passes only an explicit environment allowlist, disables dotenv, and blocks socket and DNS access.

```shell
python -m scripts.offline_unittest discover -s tests -v
```

Any syntax or test failure returns a non-zero exit code. GitHub Actions runs the same gate on every push and pull request with Python 3.11 and no repository secrets.

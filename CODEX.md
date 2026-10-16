# HiLabs Codex Playbook

Use this file for every task in this repository. This is a local-first hackathon starter; problem statement (PS) decides final domain stages.

## Non-negotiables

- Read `README.md` and `docs/PS_CHECKLIST.md` before PS-specific changes.
- Keep raw inputs immutable. Every transformed record needs source ID, reason codes, decision, review flag, and export path.
- Implement deterministic rules before model calls. Make model output optional, typed, logged, and reviewable.
- Never invent benchmark, accuracy, data source, or integration result.
- Keep secrets in local `.env`; never commit them. Treat uploaded data as sensitive.
- Test hard constraints before UI polish.
- Make one logical change set per task. After verified work: commit and push `main`.
- Do not stage unrelated working-tree changes.

## Skill router

Use smallest applicable set. Read each selected skill's `SKILL.md` before acting.

| Need | Skills | Output |
| --- | --- | --- |
| Understand PS, rules, judging, or source files | `compound-engineering:ce-doc-review`, `superpowers:brainstorming` | Constraint sheet, risks, success metric, demo journey |
| Research domain, prior winners, papers, APIs, or datasets | `academic-researcher`; use `firecrawl-deep-research` or `firecrawl-search` for current web evidence | Cited research memo; only verified claims |
| Turn PS into executable plan | `superpowers:writing-plans`, `compound-engineering:ce-plan` | Ordered milestones, owners, tests, demo checkpoints |
| Create project-specific reusable skill | `skill-creator`, `superpowers:writing-skills` | Validated `SKILL.md`; keep it concise and task-triggered |
| Choose architecture or interfaces | `c4-architecture`, `backend-to-frontend-handoff-docs` | Component/API contract, state and failure paths |
| Design relational schema, review queue, audit log | `database-schema-designer` | Schema, indexes, migration/retention rules |
| Build feature or pipeline stage | `caveman:lean-build`, `superpowers:test-driven-development` | Small tested diff; deterministic core first |
| Make small fix | `caveman:surgical-patch` | Narrow regression-tested patch |
| Debug failing behavior | `caveman:investigate-first`, `superpowers:systematic-debugging` | Reproduction, root cause, minimal fix |
| Refactor without behavior change | `caveman:safe-refactor` | Tests before/after, no feature creep |
| Review implementation | `caveman:caveman-review`, `compound-engineering:ce-code-review` | Findings ranked by impact, fixes where authorized |
| Validate complete task | `caveman:verify-and-stop`, `superpowers:verification-before-completion` | Exact commands, outputs, known gaps |
| Prepare README, API guide, or handoff | `crafting-effective-readmes`, `backend-to-frontend-handoff-docs`, `session-handoff` | Runbook and demo path |
| Create pitch deck or final presentation | `presentations:Presentations`, `visualize:visualize` | Evidence-led deck; no fabricated metrics |
| Commit and publish finished unit | `commit-work` | Conventional commit, push to `origin/main` |

## PS-day procedure

1. Capture PS verbatim in `docs/ps/` with input format, outputs, rules, scoring, constraints, and deadline.
2. Run PS analysis skills. Produce one-page `docs/PS_DECISIONS.md`:
   - user and operator
   - one measurable outcome
   - input/output schemas
   - deterministic rules
   - ML/LLM role, or explicit reason not used
   - privacy/security limits
   - evaluation split and leakage risks
   - demo happy path and failure path
3. Write acceptance tests for schema, hard constraints, error handling, audit records, and export.
4. Build vertical slice: input -> validation -> decision -> review/evidence -> export -> UI.
5. Add domain stages only after vertical slice works.
6. Run clean-start verification. Record commands and results in README or handoff.
7. Commit and push.

## Default implementation shape

```text
web UI
  -> FastAPI endpoint
  -> parser/validator
  -> pure deterministic pipeline
  -> optional ML/LLM adapter
  -> decision + audit record
  -> review queue/export
```

Keep business logic in `api/app/`, pure functions where possible. Keep HTTP handlers thin. Preserve `raw` and `normalized` fields separately. Return structured error codes, not untraceable strings.

## Model-use policy

- Prefer rules, reference lookup, and reproducible scoring for hard decisions.
- Use ML only when labels/data support it. Baseline first.
- Use LLM only for bounded tasks: extraction, classification, explanation, or query assistance.
- Require JSON schema/typed output; validate it; retain prompt/model/version and confidence where allowed.
- Route low confidence or policy-sensitive cases to review.
- Never send protected/sensitive data to external model APIs without explicit PS permission.

## Quality gates

Before each commit:

1. Run targeted tests plus full test suite.
2. Run formatter/type checks when configured.
3. Test success, invalid input, empty input, duplicate/conflict, and review-required paths.
4. Test exported audit data against displayed decision.
5. Run `git diff --check`.
6. Inspect staged diff for secrets, generated files, mocks, and unrelated edits.
7. Commit conventional message. Push `origin/main`.

Before final demo:

1. Start from clean clone or clean containers.
2. Run seeded fixture through full workflow.
3. Confirm UI numbers equal API/export numbers.
4. Record known limits honestly.
5. Prepare 90-second script: problem -> workflow -> evidence -> outcome -> limitation -> next step.

## Repository commands

```bash
make test
docker compose up --build
git diff --check
git status --short
git add <intended-files>
git commit -m "type: summary"
git push origin main
```

`docker` and third-party dependencies may not exist on local machine. Report missing runtime/tooling; do not claim smoke test passed without it.

## Files to add after PS release

```text
docs/ps/PROBLEM_STATEMENT.md
docs/PS_DECISIONS.md
docs/DEMO_SCRIPT.md
api/tests/test_<domain>.py
data/fixtures/<safe-synthetic-input>.csv
```

Never commit real user, health, credential, or proprietary data.

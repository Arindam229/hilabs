# HiLabs Codex Playbook

Use this file for every task in this repository. This is a local-first hackathon starter; problem statement (PS) decides final domain stages.

## Team context

### Mission

- Event: AI Quest HiLabs Hackathon, IIT Roorkee.
- Team repo: `github.com:sivk-kex/hilabs`, branch `main`.
- Status: PS not released when this scaffold was built.
- Objective: turn released PS into working, evidence-backed product fast; optimize judging impact, reliability, demo clarity, and honest claims.

### Prior-winner pattern

Reference repo reviewed: `github.com/beingamanforever/hilabs`.

Pattern worth copying:

```text
messy source data
  -> deterministic cleaning/normalization
  -> matching, deduplication, and validation
  -> explainable decision/review queue
  -> dashboard/export
  -> optional AI assistant over prepared data
```

Winning lesson: build complete operator workflow, not isolated model. Show input, decision, evidence, exception handling, and measurable output. Keep deterministic data work visible; AI augments product, not fake magic.

### Current implementation

Commit `c20ec2b` added generic vertical slice:

```text
CSV upload
  -> UTF-8/header validation
  -> pure normalization pipeline
  -> raw + normalized audit record
  -> review routing for missing source ID
  -> API result and audit CSV export
  -> Next.js evidence dashboard
```

Important files:

| Path | Purpose |
| --- | --- |
| `api/app/main.py` | FastAPI routes: health, metrics, CSV process, run lookup, export |
| `api/app/ingestion.py` | CSV parsing and basic input validation |
| `api/app/pipeline.py` | Pure generic normalization; safe place for PS-specific deterministic stages |
| `api/app/store.py` | Process-local run storage and flattened audit export |
| `api/tests/` | Four core behavior tests; extend before domain code |
| `web/app/page.tsx` | Upload, live run metrics, evidence queue, export link |
| `docs/PS_CHECKLIST.md` | Required PS intake checklist |
| `docker-compose.yml` | API + web local stack |

Current pipeline only knows generic fields `full_name`, `practice_phone`, and `practice_zip`. It preserves unknown columns. It is scaffold code, not final HiLabs-domain solution.

### Stack decision

- API: Python 3.11 + FastAPI. Small typed HTTP layer; core business logic stays pure Python.
- UI: Next.js + TypeScript. Fast judge-facing workflow/dashboard.
- Storage now: process memory. Replace only if PS requires persistence, concurrent users, or durable review state.
- Packaging: Docker Compose for repeatable demo.
- Data tools later: Pandas/OpenPyXL for files, RapidFuzz for entity matching, DuckDB for local analytic joins. Add only when PS proves need.
- AI later: structured, validated adapter after deterministic baseline. No model dependency in current core path.

### Known limits

- No PS-specific schema, rules, model, data source, or success metric exists yet.
- No database or user authentication exists.
- Run store resets when API restarts.
- Only CSV input path exists today.
- Docker/FastAPI/Next runtime smoke test needs dependencies and Docker available on machine. Core Python pipeline tests passed during scaffold creation.
- Do not present generic normalizers as clinical/provider-data validation unless PS supplies required reference data and rules.

### Team lanes after PS release

| Lane | First deliverable | Do not do |
| --- | --- | --- |
| Product/research | `docs/PS_DECISIONS.md`: rubric, users, workflow, baseline, citations | Choose model before defining metric |
| Data/backend | Fixture, schema tests, deterministic pipeline, audit export | Mutate/remove raw input |
| ML/AI | Baseline comparison, bounded structured output, confidence/review rules | Make opaque decisions or leak evaluation labels |
| Frontend/demo | One operator journey, live evidence, error/review path | Display mock metrics as real |
| QA/integration | Clean-start runbook, edge-case tests, measured demo result | Merge unverified changes |

### Definition of ready

Before claiming solution ready, team can demonstrate:

1. Real or sanctioned synthetic input enters product.
2. Every output has traceable source and decision reason.
3. Invalid and uncertain cases route safely.
4. Export/API/UI report same counts.
5. Success metric is computed from reproducible data or clearly labelled mock/synthetic data.
6. Demo works from documented startup steps.

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

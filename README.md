# HiLabs

Local-first skeleton for data-quality hackathon problem statements.

## Default workflow

```text
CSV upload -> validate -> normalize -> audit/review queue -> export
```

PS-specific matching, reference validation, ranking, and AI assistance attach after this working path. Raw rows remain preserved; every normalization carries reason codes and review status.

## Stack

- API: Python 3.11, FastAPI, Pydantic
- Data: Pandas, RapidFuzz, DuckDB, OpenPyXL — added only when PS needs them
- UI: Next.js, TypeScript, CSS
- Packaging: Docker Compose
- Tests: stdlib `unittest` now; add `pytest` when dependencies install

## Run

```bash
make test
docker compose up --build
```

- UI: `http://localhost:3000`
- API docs: `http://localhost:8000/docs`
- API health: `http://localhost:8000/health`

## Structure

```text
api/app/       API, parser, pure pipeline, export store
api/tests/     core behavior tests
web/app/       upload and evidence-queue dashboard
data/          local fixtures/reference files, never committed if sensitive
docs/          PS intake and decisions
```

## PS release sequence

1. Read `docs/PS_CHECKLIST.md`.
2. Freeze schema and hard constraints in tests.
3. Add deterministic PS stages under `api/app/`.
4. Connect live metrics to UI. No mock metric fallback.
5. Run clean Docker smoke test, export, and demo.

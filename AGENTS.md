# AGENTS.md — Provider Rates PTD pipeline

Codex loads this file automatically. Read it fully, then read before any task:

1. `docs/ps/PROBLEM_STATEMENT.md` — the problem, verbatim. Source of truth.
2. `docs/ps/DATA_FINDINGS.md` — verified facts about the real files + open hypotheses.
3. `docs/PLAN.md` — task cards. Work on exactly ONE card per session.
4. `docs/DECISIONS.md` — decision log. Append to it; never silently change a rule.
5. `CODEX.md` — team playbook (general rules, skill router, quality gates). This file wins on conflict.

## What we are building

A re-runnable CLI pipeline that streams Centene's Transparency-in-Coverage files and produces:
PPO network map (C1–C2) → file quality grades (C3) → PPO rates (C4) → NPI/TIN→address links (C5)
→ provider rate file (C6) → optional cost-effectiveness (C7). Judges score **logic + metrics**
(every decision explained) and **scalability + coverage** (streaming, parallel, % NPIs linked to a verified address).

The existing `api/` + `web/` scaffold is the later UI (brownie point 7a). Do not touch it until C6 is done.

## Layout

```text
pipeline/                 # python package, all PS logic lives here
  cli.py                  # `python -m pipeline <stage>` and `python -m pipeline all`
  config.py               # reads config.yaml + env; the ONLY place paths come from
  stages/c1_index.py ...  # one module per card; pure functions + a thin run(cfg) entrypoint
  io/                     # streaming readers (http/gzip/json), parquet writers, manifests
tests/fixtures/           # tiny hand-written TiC/NPPES samples (committed, synthetic or public)
tests/test_c1_index.py    # one test file per stage
config.yaml               # sources (URLs), scope (payer/state/market/network), thresholds
data/                     # runtime output, git-ignored: data/raw (cache), data/stage/<cN>/, data/out/
docs/                     # PS, findings, plan, decisions, generated deliverables
```

## Hard rules

- **Stream, never load.** Rate files are 0.7 GB+ uncompressed JSON. Disk on dev box has ~5 GB free.
  Use `ijson` (yajl2_c backend) over a streamed HTTP/gzip body; write Parquet in bounded batches
  (pyarrow). Memory must stay flat as file size grows. Joins/aggregates go through DuckDB over Parquet.
  A test must prove a stage works on a fixture without reading the whole file into a Python object.
- **No hardcoded paths or URLs in code.** Everything from `config.yaml` / env (`PTD_DATA_DIR`). Deliverable 6
  is "re-runs from README" — a clean clone + `make setup && make pipeline` must work.
- **Every stage writes `data/stage/<cN>/_manifest.json`**: inputs (URL/path, size, last-modified, sha256 when local),
  row counts in/out/dropped-by-reason, runtime, config hash, git sha. The Summary deliverable is generated
  from manifests — never type a number into a doc by hand.
- **Every rule has an ID** (`R-C2-03`) used in code comments, in `docs/DECISIONS.md`, and in any output
  column that records why a row was kept/dropped (`reason_code`). Judges read the logic; make it traceable.
- **Raw is immutable.** Keep source fields as-is next to normalized ones. Never overwrite a source column.
- **Idempotent + resumable.** Re-running a stage with same inputs + config produces identical outputs;
  `--from cN` skips finished upstream stages whose manifest config hash matches.
- **Parallelism is explicit.** Independent files go through `concurrent.futures.ProcessPoolExecutor`
  with `--workers` (default `os.cpu_count()-1`). One file = one sequential streaming pass.
- **Claims need evidence.** Never state a count, match rate or "verified" without the query that produced it.
  If a hypothesis in DATA_FINDINGS is unconfirmed, say so.
- **No PHI exists here**, but NPPES/PTD are large public files: never commit them. Only small fixtures.
- External calls (NPPES, CMS, payer directory, geocoder): cached under `data/raw/`, rate-limited, retried
  with backoff, and runnable offline from the cache.

## Stack

Python 3.11+, `uv` for env. Deps: `ijson`, `pyarrow`, `duckdb`, `httpx`, `pyyaml`, `rapidfuzz`, `usaddress`,
`openpyxl` (Excel deliverable), `pytest`, `ruff`. Add anything else only with a one-line reason in DECISIONS.md.

## Workflow per card

1. Read the card in `docs/PLAN.md`. Restate goal + acceptance in 3 lines.
2. Write/extend fixture + failing test for the acceptance criteria.
3. Implement the minimum that passes; run it on real data for the in-scope slice.
4. Record every judgment call in `docs/DECISIONS.md` (rule ID, rule, why, evidence query/result, alternatives rejected).
5. Update `docs/ps/DATA_FINDINGS.md` if you learned a fact about the data (mark verified vs hypothesis).
6. Gates: `uv run ruff check . && uv run pytest -q` green; `git diff --check`; manifest written.
7. One commit per card: `feat(c2): ...`. Do not push unless the human says so.
8. End with: what was done, numbers from the manifest, open questions, next card.

## Commands

```bash
make setup                       # uv sync
make test                        # ruff + pytest
make pipeline                    # python -m pipeline all
uv run python -m pipeline c3 --workers 8
```

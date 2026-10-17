# C1–C2 Network Classification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build repeatable C1 index parsing and C2 California commercial-group PPO classification with evidence and rate-file queue outputs.

**Architecture:** Add isolated `pipeline` package. Pure classification functions transform plan rows; CLI reads configured index files, writes stage artifacts and manifests. A separate incremental TiC evidence pass aggregates network signals only; it does not extract rates.

**Tech Stack:** Python 3.11+, `uv`, `ijson`, `pyarrow`, `pyyaml`, stdlib `unittest`.

**Spec:** `docs/ps/PROBLEM_STATEMENT.md`, `docs/PLAN.md`, `docs/ps/DATA_FINDINGS.md`, `AGENTS.md`.

## Global Constraints

- Stream source JSON. Never load rate files into memory.
- Paths and URLs come from `config.yaml` or `PTD_DATA_DIR`; no absolute paths.
- Raw source stays immutable and untracked under `data/raw/`.
- Every rule has a matching `R-C1-*` or `R-C2-*` reason code and decision-log entry.
- Every stage writes a manifest with source metadata, counts, config hash, runtime, and Git SHA.
- C2 never claims plan-name classification proves PPO rate membership; in-file evidence remains explicit.

## Review Focus

- A plan containing both PPO and EPO/HMO/POS/EOA tokens must classify as restrictive network, not PPO.
- Concatenated `CUSPPO` must classify as PPO when no restrictive token exists.
- Unknown plans must remain `UNRESOLVED`; never silently assign PPO.
- Duplicate plan/file pairs must not duplicate the C1 plan table or C2 rate queue.
- Missing or malformed source JSON must fail with a clear error and no partial stage output.

---

### Task 1: Pipeline foundation and C1 parser

**Files:**
- Create: `pyproject.toml`, `config.yaml`, `pipeline/__init__.py`, `pipeline/__main__.py`, `pipeline/config.py`, `pipeline/io/manifest.py`, `pipeline/stages/c1_index.py`
- Create: `tests/fixtures/healthnet_index.json`, `tests/test_c1_index.py`
- Modify: `Makefile`, `.gitignore`, `README.md`, `docs/DECISIONS.md`

**Interfaces:**
- Produces: `parse_index_paths(paths: list[Path]) -> list[dict[str, str]]`
- Produces: `run_c1(cfg: Config) -> StageResult`
- Writes: `data/stage/c1/plans.parquet`, `data/stage/c1/rate_files.parquet`, `data/stage/c1/_manifest.json`

- [ ] Write failing tests for flattening `reporting_structure`, exact plan/file pair dedupe, and unique rate-file counts.
- [ ] Run `uv run pytest tests/test_c1_index.py -q`; confirm expected import failure.
- [ ] Implement config, stage writer, manifest writer, and parser with `ijson.items(..., "reporting_structure.item")`.
- [ ] Run focused test, then full `uv run pytest -q` and `uv run ruff check .`.
- [ ] Commit `feat(c1): parse and deduplicate Centene indexes`.

### Task 2: C2 plan classification and PPO queue

**Files:**
- Create: `pipeline/stages/c2_network.py`, `tests/test_c2_network.py`
- Modify: `pipeline/__main__.py`, `docs/DECISIONS.md`

**Interfaces:**
- Consumes: C1 `plans.parquet` rows.
- Produces: `classify_plan(row: Mapping[str, str]) -> PlanClassification`
- Produces: `run_c2(cfg: Config) -> StageResult`
- Writes: `data/stage/c2/plan_network.parquet`, `data/stage/c2/rate_files.parquet`, `data/stage/c2/_manifest.json`

- [ ] Write failing tests for explicit PPO, CUSPPO, conflicting PPO+EPO, HMO/EOA/POS, non-group, non-CA, and unresolved cases.
- [ ] Run focused test; confirm failure because classifier is missing.
- [ ] Implement ordered restrictive-token precedence, positive PPO detection, `UNRESOLVED` fallback, reason code, and confidence fields.
- [ ] Build one PPO rate-file queue row per unique URL with associated plan count and sample plan name.
- [ ] Run focused tests, full test suite, and ruff.
- [ ] Commit `feat(c2): classify PPO plans with rule evidence`.

### Task 3: C2 in-file evidence aggregation

**Files:**
- Create: `pipeline/stages/c2_evidence.py`, `tests/fixtures/tic_network_sample.json`, `tests/test_c2_evidence.py`
- Modify: `pipeline/__main__.py`, `pipeline/stages/c2_network.py`, `docs/DECISIONS.md`

**Interfaces:**
- Consumes: configured local TiC rate-file paths or URLs and C2 queue.
- Produces: `aggregate_network_evidence(source: BinaryIO) -> dict[str, object]`
- Writes: `data/stage/c2/network_evidence.parquet`, `data/stage/c2/network_keys.parquet`, updated C2 manifest.

- [ ] Write failing fixture test proving aggregate counts include provider-group business-name labels, `additional_information` values, billing classes, and referenced group IDs.
- [ ] Run focused test; confirm failure because evidence aggregator is missing.
- [ ] Implement sequential `ijson` passes over local or HTTP-streamed TiC JSON. Record no rate rows; only network-disambiguation aggregates.
- [ ] Emit candidate keys only when observed evidence supports a rule; otherwise write `UNRESOLVED` decision with evidence counts.
- [ ] Run focused tests, full suite, ruff, and a configured sample run.
- [ ] Commit `feat(c2): aggregate rate-file network evidence`.

### Task 4: Operational handoff

**Files:**
- Modify: `README.md`, `docs/DECISIONS.md`, `docs/ps/DATA_FINDINGS.md`

- [ ] Document `make setup`, `make c1`, `make c2`, `PTD_DATA_DIR`, data placement, generated artifacts, and expected unavailable-data failure.
- [ ] Add `R-C1-*` and `R-C2-*` rule entries with commands/evidence placeholders; do not invent run counts.
- [ ] Verify clean clone setup plus tests; commit `docs: document C1 C2 runbook`.

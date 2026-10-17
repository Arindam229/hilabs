# HiLabs Provider Rates

Local-first Centene Price Transparency Data pipeline. Raw data stays outside Git.

## Generate C1, then C2

`make c2` always rebuilds C1 from raw source archive before classifying C2.

1. Put `hilabs_dataset_2026-10-17.zip` in the `data/` folder. By default the
   pipeline looks in `data/` for the archive, so no `PTD_DATA_DIR` is needed.
   Archive may store Centene index JSON files under a top-level directory.
2. Run:

```bash
cd /home/redacted/Desktop/projects/hilabs
make setup
make c2
```

`PTD_DATA_DIR` can still override the directory containing the archive. It points
to the directory containing the archive, not the archive path. Change
`sources.archive` in `config.yaml` if the source archive has another name.

Pipeline stages:

```text
raw ZIP -> C1 plans + deduplicated rate files -> C2 PPO classification -> Excel
```

Outputs:

```text
data/stage/c1/plans.parquet           C1: plan-to-rate-file mapping
data/stage/c1/rate_files.parquet      C1: unique physical rate-file queue
data/stage/c1/_manifest.json          C1: source/count evidence
data/stage/c2/plan_network.parquet    C2: every plan classification
data/stage/c2/rate_files.parquet      C2: deduplicated PPO candidate files
data/out/c2_ppo_network.xlsx          C2 deliverable workbook
```

`c2_ppo_network.xlsx` has two sheets:

- `Plan classification`: every parsed plan, rule ID, confidence.
- `PPO rate files`: unique rate URLs for downstream streaming.

PPO is plan-level classification only. Shared rate file can serve multiple plan
types; provider membership needs later rate-file evidence.

Run C1 only:

```bash
make c1
```

Use `PTD_DATA_DIR="/absolute/path/to/archive-directory" make c1` to read the
archive from another directory.

Run checks:

```bash
make test
```

## Repository layout

```text
pipeline/stages/c1_index.py      C1 streaming index parser
pipeline/stages/c2_network.py    C2 PPO classification + Excel export
tests/                           C1/C2/command behavior tests
data/                            local sources and ignored run artifacts
docs/                            PS scope and rule decisions
```

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

## C3: grade queued PPO rate files

```bash
make c3
```

C3 streams every C2-queued MRF from archive, without extracting it. It keeps
only counters, bounded cohort reservoirs and a temporary SQLite duplicate index.
Outputs:

```text
data/stage/c3/file_metrics.parquet    file-level quality metrics
data/stage/c3/row_flags/*.parquet     capped exception examples per MRF
docs/deliverables/file_quality_metrics.md
```

Useful resource controls:

```bash
# Grade separate queued files concurrently. Default: 1 worker.
PTD_C3_WORKERS=2 make c3

# Diagnostic sampling only: retain one 1,000-service block in every 10 blocks.
# C4 rejects sampled C3 output; rerun normal C3 before final extraction.
PTD_C3_SAMPLE_EVERY=10 PTD_C3_BLOCK_SIZE=1000 make c3

# Keep first 25,000 row-level exception examples while retaining exact counts.
PTD_C3_ROW_FLAG_LIMIT=25000 make c3
```

## C4: extract PPO rates

C4 streams the selected Health Net CA in-network TiC JSON and explodes it into
one row per resolved NPI, TIN and negotiated price. It uses `ijson` over the
streamed file and a temporary SQLite index; it never loads the whole document.

Inputs: a local TiC in-network JSON (plain or gzip). It must contain top-level
`provider_references` and `in_network` sections. By default the Makefile streams the
file directly from `data/hilabs_dataset_2026-10-17.zip`
(`hilabs_dataset_2026-10-17/centene/in_network/2026-09-30_..._healthnet-ca_in-network.json`),
so no extraction is required. Set `PTD_RATE_FILE` to an extracted JSON or another
zip member as needed.

Run:

```bash
make c4 PTD_RATE_FILE=/path/to/healthnet-ca_in-network.json
```

Override the output directory if needed:

```bash
make c4 PTD_RATE_FILE=/path/to/healthnet-ca_in-network.json PTD_C4_OUTPUT_DIR=/tmp/c4out
```

Outputs in the stage directory (default `data/stage/c4/`):

- `raw_rates.csv`: every extracted source record, including exact duplicates, invalid,
  zero and negative rates. This is the C3 source-duplication input.
- `c4result.csv`: curated one row per `(npi, tin, billing_code)` selection key after
  exact-duplicate removal and rate selection. Includes `selection_rule`,
  `candidate_count` and `distinct_candidate_count`.
- `c4_selection_audit.csv`: non-selected alternative candidate rates with the reason they
  were not selected and the selected rate for comparison.
- `c4_summary.json`: all counts.
- `_manifest.json`: reproducibility metadata.

Provider-group references are resolved by exact `provider_group_id`, not by array
position or numeric order. Unresolved references are counted and never joined to
invented NPIs or TINs. NPI and TIN values are kept as strings.

Rate values are preserved as published, including `$0`, negative, missing and
non-numeric rates; those are counted separately rather than silently dropped.
Expiration dates of `9999-12-31` are not treated as proof of staleness.

### Rate selection rules (C4)

1. Exact duplicates are detected on the full pricing/provider key (provider identifiers,
   billing code and type, negotiated amount, rate type, billing class, setting,
   modifiers and other pricing attributes such as service code and additional
   information). Confirmed exact duplicates are removed from `c4result.csv`; their
   count is retained in `c4_summary.json` and the manifest for C3.
2. When several distinct rates remain for the same `(npi, tin, billing_code)` selection
   key, one is selected in this order:
   - `R-C4-SEL-02`: prefer `negotiated` over `fee schedule` and other rate types.
   - `R-C4-SEL-03`: prefer rows with fewer billing-code modifiers.
   - `R-C4-SEL-04`: prefer `professional` over `institutional` billing class.
   - `R-C4-SEL-05`: prefer the most common rate value among candidates.
   - `R-C4-SEL-06`: break remaining ties by the highest negotiated rate.
   - `R-C4-SEL-07`: final deterministic first row if all else is equal.
3. Single-candidate keys use `R-C4-SEL-01`.
4. Alternative rates are never discarded silently: every non-selected candidate is
   written to `c4_selection_audit.csv` with the selection rule and selected rate.
5. Meaningful differences in billing class, setting, modifiers, rate type and other
   pricing context are preserved in `raw_rates.csv`; collapsing happens only in the
   curated `c4result.csv` and is fully audited.

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

## C5/C6: address mapping and final workbook

```bash
make c5
make c6
```

C5 streams NPPES, CMS DAC and NUCC from the outer dataset ZIP, maps practice
addresses to C4 providers, enriches specialties, and writes `c5result.csv`,
`c5_address_audit.csv`, and `c5_summary.json`. C6 selects one canonical address
per `(NPI, TIN, Billing Code)` and writes `data/out/final_provider_rates.xlsx`.

## Repository layout

```text
pipeline/stages/c1_index.py      C1 streaming index parser
pipeline/stages/c2_network.py    C2 PPO classification + Excel export
tests/                           C1/C2/command behavior tests
data/                            local sources and ignored run artifacts
docs/                            PS scope and rule decisions
```

## C4 extraction, duplicate and selection criteria

### Criteria used during rate extraction

| Criterion | What we check | Why |
| --- | --- | --- |
| Provider-group reference | Match each `provider_references` ID to the corresponding `provider_group_id` | Prevents assigning a rate to the wrong provider |
| NPI | Extract the associated NPI or NPIs | Identifies the healthcare provider |
| TIN | Extract the associated TIN | Identifies the billing entity |
| Billing code | Extract the parent service's `billing_code` | Identifies the medical service |
| Negotiated rate | Extract `negotiated_rate` | Gives the price |
| Negotiated type | Inspect `negotiated_type` | Distinguishes direct negotiated rates from other pricing arrangements |
| Billing class | Preserve professional versus institutional classification | Different billing contexts may have different rates |
| Setting | Preserve available setting information | A rate may vary by care setting |
| Service code and modifiers | Preserve these pricing attributes where available | Helps distinguish potentially different rate contexts |
| Expiration date | Preserve the rate's expiration metadata | Helps interpret the rate's validity |

Optional fields are retained when available rather than assumed to exist in every record.

### Criteria used to identify duplicates

- The same billing code alone does not mean two records are duplicates.
- The same price alone does not mean two records are duplicates.
- Different NPIs or TINs must not be merged.
- Records with different billing classes, settings, service codes or modifiers may represent legitimate alternatives.
- Records matching across all relevant provider, billing-code and pricing attributes can be treated as exact duplicates.

Source records are preserved in `raw_rates.csv` so duplicate counts remain available for C3.

### Criteria used to select one final rate

1. Group records correctly using `NPI + TIN + billing_code` as the selection key. Do not combine different providers or billing entities.
2. Remove confirmed exact duplicates so repeated identical records do not influence selection multiple times.
3. Compare pricing contexts: negotiated type, billing class, setting, service code, modifiers and other relevant attributes.
4. Apply a documented selection rule: prefer an appropriate directly negotiated dollar rate when the output requires a dollar amount, while respecting the intended service and billing context.
5. Resolve or flag remaining alternatives: use a deterministic tie-breaker when justified; if information is insufficient, flag the case for review rather than arbitrarily choosing the cheapest or highest rate.

Selection key and hierarchy are implementation decisions, not a complete algorithm prescribed by the problem statement. Preferring professional over institutional is not universally correct; it depends on the intended analysis.

### Missing or invalid values

| Case | C4 treatment |
| --- | --- |
| NPI is `0` | Treat as invalid, not as an actual NPI |
| NPI or TIN is missing | Preserve the source record, flag it, and exclude it from confirmed provider-level selection |
| Rate is zero | Preserve and count it for quality analysis; do not automatically delete it |
| Rate is negative or nonnumeric | Flag it for validation |
| Provider reference cannot be resolved | Record the unresolved reference rather than inventing an NPI or TIN |
| Multiple legitimate rate alternatives remain | Preserve them in the audit output and document the selection decision |

### C4 outputs

- `raw_rates.csv` — extracted source records, including duplicates.
- `selected_rates.csv` — one selected rate per valid NPI + TIN + billing-code key.
- `rate_selection_audit.csv` — alternatives, duplicates, selected rates and reasons.
- `c4_summary.json` — counts of extracted records, selected rates, invalid identifiers, duplicates and unresolved cases.

## Logic: PPO network identification (C1–C2)

- C1 parses Centene index files and deduplicates plan-to-rate-file mappings.
- C2 classifies plans as PPO using explicit plan-name tokens (`PPO`, `CUSPPO`,
  `Preferred Provider`) only for California commercial-group plans.
- Restrictive tokens (`HMO`, `EPO`, `POS`, `WholeCare`, `SmartCare`,
  `CommunityCare`, `Salud`) override PPO tokens.
- Non-group and non-CA plans are `OUT_OF_SCOPE`; ambiguous plans (e.g. `EOA`)
  remain `UNRESOLVED` rather than guessed.
- Health Net CA and OR share separate files; CA commercial group uses one shared
  in-network file, so plan names alone cannot prove rate-level membership.

## Logic: TIN to NPI to address mapping (C5)

Sources used:
- NPPES (primary + secondary practice locations, taxonomy codes)
- CMS Doctors & Clinicians national file (practice address, specialty)
- NUCC taxonomy (taxonomy code -> specialty)
- HiLabs Spec-Proc weights (billing code -> specialty fallback)
- Centene provider directory API (unavailable/blocked in this environment)

Rules:
- NPI is the primary join key; TIN and org name are supplementary only.
- Practice addresses are preferred over mailing addresses.
- Multiple addresses per NPI are preserved as distinct candidates.
- TIN-address links are never assumed; all are marked `UNVERIFIED`.
- Address statuses: `CORROBORATED`, `SINGLE_SOURCE`, `CONFLICTING`, `UNRESOLVED`,
  `INVALID_NPI`.
- Address normalization trims, removes punctuation, standardizes ZIP and street
  suffixes; fuzzy matching (>=97%) merges only near-identical addresses.
- Materially different addresses are never merged on city/ZIP/org alone.

Conflicts:
- When NPPES and CMS disagree, both addresses are retained as `CONFLICTING`
  candidates rather than one being silently dropped.
- C6 selects one canonical address per `(NPI, TIN, Billing Code)` using an
  evidence tier (corroboration > single source > conflicting), source count,
  record freshness, and a deterministic lexicographic tie-breaker.
- Ambiguous selections are marked `AMBIGUOUS_SINGLE_ADDRESS_SELECTED` and all
  alternatives are preserved in the audit.
- No address is invented; unresolved rows keep a blank `Address`.

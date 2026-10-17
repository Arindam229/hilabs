# Plan — task cards

One card per Codex session. Order matters: each card consumes the previous card's Parquet + manifest.
Every card's "Done when" is checked by tests + a manifest, not by prose.

Points map (judges use one track): Logic 40 / Metrics 35 / Structure 25 — or — Scalability 40 / Coverage 35 / Correctness 25.
Cards are designed to score on both.

---

## C0 — Skeleton (do first, small)

- Create `pipeline/` package, `config.yaml`, `cli.py` (`python -m pipeline <c1..c7|all> [--from cN] [--workers N]`),
  `config.py` (data dir from `PTD_DATA_DIR`, default `./data`), `io/manifest.py`, `io/stream.py`
  (httpx streamed GET → optional gzip → `ijson` items; same reader for local paths), `io/parquet.py` (batched writer).
- `pyproject.toml` (uv), Makefile targets `setup test pipeline`, `.gitignore` for `data/*` except `.gitkeep`.
- Test: stream a fixture TiC file and yield provider_references + in_network items; manifest written.
- **Done when:** `make setup && make test` green on clean clone; `python -m pipeline --help` works.

## C1 — Parse index files → plan table  *(Core 1)*

- Input: all index URLs from `config.yaml` (scrape the Centene page for current URLs; keep a pinned list as fallback).
  Follow sub-indexes (QualChoice employer indexes).
- Output `stage/c1/plans.parquet`: brand, index_url, plan_name, plan_id, plan_id_type, plan_market_type,
  issuer_name, plan_sponsor_name, structure_id, rate_file_url. `stage/c1/rate_files.parquet`: one row per unique
  rate_file_url with n_plans, brands, market types, state guess (from URL/plan names), HTTP size + last-modified (HEAD).
- Dedupe: many plans → one file. Report plans parsed, structures, unique files.
- **Done when:** counts in manifest; test covers a fixture index with shared files + sub-index; dedupe rule logged.

## C2 — Find the PPO network  *(Core 1, Logic heavy)*

Two levels — explain both:
1. **File level:** which rate files can contain CA commercial-group PPO? Rule out by brand/market/state with counts
   (H3). Expect: Health Net CA in-network file only — prove it.
2. **Inside the file:** CA PPO/HMO/EOA/POS plans share ONE file, so identify PPO rates/providers inside it.
   Test H1 (`additional_information` codes) and H2 (`PPO: <County>` groups) with streamed aggregates:
   code × billing_class counts, code co-occurrence with PPO-labelled groups, providers per code.
- Plan classification: rules on plan name tokens (PPO/HMO/EPO/POS/EOA/HSA/"CUS"), each a rule ID; unknowns
  listed explicitly, never guessed. Show how HMO/EPO/POS were ruled out.
- Output `stage/c2/plan_network.parquet` (plan → network + reason_code + confidence),
  `stage/c2/network_keys.parquet` (whatever in-file key defines PPO: codes and/or provider_group_ids).
- **Done when:** every in-scope plan has a network label or an explicit `UNRESOLVED` reason; decision entries
  R-C2-* with evidence queries; a "how we ruled out HMO/EPO/POS" section exists in DECISIONS.md.

## C3 — Grade PTD files  *(Core 2, Metrics 35 pts)*

- One streaming pass per file (parallel across files) computing metrics into `stage/c3/file_metrics.parquet`:
  - Schema validity (TiC version, required fields present), parse errors.
  - Code coverage: distinct billing codes vs. the HiLabs specialty→code list and vs. CMS shoppable-service set.
  - Provider coverage: distinct NPIs/TINs; % NPIs valid (Luhn check) and found in NPPES; Type1/Type2 mix.
  - Rate sanity: % $0, % negative, outliers (per code, robust z on log rate / IQR), % percentage-type vs dollar.
  - Rate types: negotiated_type & billing_class mix; arrangement (ffs/bundle/capitation).
  - Duplicates: identical (npi,tin,code,modifier,class,setting,rate) rows; same key with conflicting rates.
  - Staleness: `last_updated_on` age; expiration 9999 share (finding: 100% in sample → note it, don't score on it);
    NPIs deactivated in NPPES.
  - Referential integrity: provider_references referenced but missing / defined but unused.
- Composite grade (A–F) = weighted sum; weights justified in DECISIONS.md (R-C3-*). Show sensitivity: grade
  ranking under 2 alternative weightings.
- Output also `docs/deliverables/file_quality_metrics.md` generated from the parquet (metric, formula, why, value).
- **Done when:** every in-scope file scored; each metric has formula + rationale + test on a fixture with known
  defects (planted $0, dupes, bad NPI).

## C4 — Extract PPO rates  *(supporting)*

- Stream the PPO file(s); keep only PPO keys from C2; join provider_reference ids → (npi, tin).
- Explode to `stage/c4/rates.parquet`: npi, tin, billing_code, code_type, modifier, billing_class, setting,
  negotiated_type, rate, service_codes, additional_information, provider_group_id, source_file, reason_code.
- Multiple rates per (npi,tin,code): write the rule (e.g. professional > institutional for Type 1, no-modifier
  base rate, ffs `negotiated` over `derived`/`fee schedule`, then most common, then max/median with flag).
  Keep all candidates in a side table; final table one row per key with `selection_rule`.
- **Done when:** memory stays flat (log peak RSS in manifest); sample of 50 rows hand-checkable against raw JSON
  via a `pipeline trace <npi> <code>` command.

## C5 — NPI/TIN → practicing address  *(Core 3, Coverage 35 pts)*

Do NOT trust NPPES alone (~80% stale). Build candidate addresses from several sources, then score:
- Sources (each cached under `data/raw/`, each a rule-ID'd adapter):
  - NPPES CA extract: primary practice location + `pl_pfile` secondary locations; last-update date; deactivations.
  - CMS Doctors & Clinicians national file: NPI → practice address + group (org PAC) — recency signal from Medicare.
  - Health Net provider directory (FHIR Plan-Net, H4) — network-specific locations; best "verified" source if reachable.
  - TIN business_name ↔ NPPES Type 2 org name (rapidfuzz) to link TIN → org NPI → org address.
  - Address standardization: `usaddress` + USPS-style normalization; Census batch geocoder for lat/long + validity.
- Model the graph: TIN → {NPI} (from PTD) and NPI → {address} (from sources); address belongs to TIN if it is
  the org address or shared by ≥k NPIs of that TIN.
- Score each (npi, tin, address) candidate: source agreement count, source recency, directory confirmation,
  geocode validity, TIN co-location. Define **verified** = (directory-confirmed) OR (≥2 independent sources agree
  after normalization). Everything else = `unverified` with reason.
- Output `stage/c5/npi_tin_address.parquet` + coverage stats: % NPIs / % TINs with ≥1 verified address.
- **Done when:** coverage numbers in manifest; DECISIONS explains scoring + conflicts; baseline (NPPES-only)
  coverage reported next to ours to show lift.

## C6 — Provider rate file  *(Deliverable 1)*

- Join c4 rates × c5 addresses × specialty (NPPES taxonomy → NUCC → specialty; cross-check with HiLabs
  specialty→code mapping to flag implausible specialty/code pairs).
- Output `data/out/provider_rates.xlsx` (+ parquet/csv): NPI, TIN, Address, Billing Code, Specialty, Rate,
  plus traceability columns (address_status, selection_rule, source_file). Excel row limit 1,048,576 → split
  sheets or ship CSV alongside; note it.
- Generate `docs/deliverables/summary.md` from all manifests (Deliverable 4) and `logic.md` from DECISIONS.md (Deliverable 2).
- **Done when:** clean-clone `make pipeline` regenerates everything; numbers in summary == parquet counts (test).

## C7 — Cost effectiveness  *(brownie, optional)*

- "Similar" = same specialty × same billing code × same geography (county/CBSA) × same billing_class.
- Metrics: provider rate / peer median per code; volume-weighted index across a specialty's common codes;
  percentile rank; Medicare PFS ratio as an external anchor. Defend each in DECISIONS.md.

## UI (brownie 7a, last)

Reuse `web/` + `api/`: exec view (network, file grades, coverage) and analyst view (search NPI/TIN/code →
rates + address evidence + rule trail). Read only from `data/out/`. No mock numbers.

---

## Running Codex on a card

```bash
cd ~/Desktop/projects/hilabs
codex "Do card C1 from docs/PLAN.md. Follow AGENTS.md exactly."        # interactive, review each step
# unattended: writes limited to repo; network on (cards download Centene/NPPES/CMS files)
codex exec -s workspace-write -c sandbox_workspace_write.network_access=true \
  "Do card C3 from docs/PLAN.md. Follow AGENTS.md."
```

After each card: review the diff (`/review` in Codex, or a second model), check the manifest numbers, then commit.

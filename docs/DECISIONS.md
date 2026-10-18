# Decision log

Feeds deliverables 2 (Logic file) and 3 (File quality metrics). One entry per rule. Newest at bottom.
Code, output `reason_code` columns, and this log all use the same rule ID.

Template:

```markdown
### R-C2-01 — <short name>
- **Rule:** exact condition, as implemented.
- **Why:** reasoning in domain terms.
- **Evidence:** query/command + result (counts). Link manifest.
- **Alternatives rejected:** what else was considered and why not.
- **Confidence / risk:** what would make this wrong; how we'd detect it.
```

## Entries

### R-C0-01 — Stream every source file
- **Rule:** No stage loads a whole source file into memory; parsing is incremental (`ijson`) with batched Parquet writes.
- **Why:** HN CA rate file alone is 701 MB uncompressed; national scope is TBs. Scalability is 40 points.
- **Evidence:** `DATA_FINDINGS.md` size check (HTTP content-length 701,615,514).
- **Alternatives rejected:** `json.load` (memory ∝ file size); pandas `read_json` (same).
- **Confidence / risk:** High.

### R-C1-01 — Preserve plan-to-file mapping, queue unique physical files
- **Rule:** C1 keeps one row per distinct plan/file pair and emits a separate unique rate-file table.
- **Why:** C2 needs plan-level evidence; later stages must not stream one physical file repeatedly.
- **Evidence:** Written by C1 manifest at execution time.
- **Alternatives rejected:** URL-only C1 table loses required plan ID and plan name.
- **Confidence / risk:** High; source index structure is explicit.

### R-C2-01 — Exclude non-group plans
- **Rule:** A plan whose `market_type` is not `group` is `OUT_OF_SCOPE`.
- **Why:** Problem scope is California commercial group coverage; individual exchange products are different markets.
- **Evidence:** C2 classification test covers an individual PPO plan.
- **Alternatives rejected:** Including every PPO-named plan regardless of market.
- **Confidence / risk:** High; source market type is explicit.

### R-C2-02 — Exclude non-California plans
- **Rule:** A group plan is `OUT_OF_SCOPE` unless plan ID, plan name, or file URL identifies California.
- **Why:** Problem scope is California.
- **Evidence:** C2 classification test covers Oregon plan ID `67138OR001`.
- **Alternatives rejected:** Assuming every Health Net group plan is California.
- **Confidence / risk:** High for explicit CA identifiers; ambiguous names remain unresolved.

### R-C2-03 — Restrictive network tokens override PPO tokens
- **Rule:** Scan entire plan name, including suffixes and punctuation-separated words. A California commercial-group plan containing `POS`, `EPO`, `HMO`, `WholeCare`, `SmartCare`, `CommunityCare`, or `Salud` is classified as that restrictive network even when `PPO` also appears. Thus `EPO$15` and `FWP-EPO$10` are EPO, not PPO.
- **Why:** Employer/account labels can contain PPO while final benefit design is EPO, HMO, or POS. Restrictive benefit tokens are stronger evidence than a broad account token.
- **Evidence:** Fixture cases `CA L CUS PPO SACRAMENTO CITY USD EPO`, `... EPO$15`, and `... FWP-EPO$10`; `pytest tests/test_c2_network.py -q`.
- **Alternatives rejected:** First-match PPO token; it misclassifies conflicting names.
- **Confidence / risk:** High for explicit tokens. It does not prove rate-level membership in shared files.

### R-C2-04 — PPO token creates a candidate plan
- **Rule:** A California commercial-group plan containing `PPO`, `CUSPPO`, or `Preferred Provider`, with no restrictive token, is classified as PPO with medium confidence.
- **Why:** This is explicit plan-level evidence, but shared Health Net rate files prevent a rate-level claim.
- **Evidence:** `pytest tests/test_c2_network.py -q` covers spaced and concatenated PPO tokens.
- **Alternatives rejected:** Treating plan-name token as proof of every rate in its shared file.
- **Confidence / risk:** Medium; validate with in-file evidence before C4 extraction.

### R-C2-05 — Keep unverified network labels unresolved
- **Rule:** `EOA` and plan names without a confirmed token stay `UNRESOLVED`.
- **Why:** Health Net California PPO, HMO, and other plans share a physical rate file. Plan names alone cannot prove individual rate membership.
- **Evidence:** `docs/ps/DATA_FINDINGS.md` verified shared CA rate file; C2 Excel records confidence and rule ID.
- **Alternatives rejected:** Inferring EOA means EPO or treating a shared file as all-PPO without in-file evidence.
- **Confidence / risk:** Deliberately conservative; C2 evidence pass must validate provider-group or schedule keys.

### R-C2-06 — Do not infer missing network type
- **Rule:** An in-scope plan without a supported token is `UNRESOLVED`.
- **Why:** Absence of a token is not positive PPO evidence.
- **Evidence:** C2 classification test covers `CA Open Access`.
- **Alternatives rejected:** Defaulting every unknown commercial-group plan to PPO.
- **Confidence / risk:** High for conservative handling; candidate coverage may increase after in-file evidence.

### R-C2-07 — Queue each PPO candidate file once
- **Rule:** C2 Excel shows PPO plans only; one queue row represents each distinct URL shared by accepted PPO plans. Full classifications remain in `data/stage/c2/plan_network.parquet` for audit.
- **Why:** C2 output is a PPO-network candidate list, while exclusion reasoning must remain available without mixing other policies into the result sheet.
- **Evidence:** `pytest tests/test_c2_network.py -q` verifies PPO-only Excel output and URL deduplication.
- **Alternatives rejected:** Re-streaming the same physical rate file for each PPO plan, or showing HMO/EPO/POS records in PPO export.
- **Confidence / risk:** High for plan-level workbook scope; in-file evidence still controls rate extraction.

### R-C4-01 — Stream provider references and in_network separately
- **Rule:** C4 builds the `provider_group_id` lookup from one streaming pass over
  `provider_references`, then streams `in_network` in a second pass. The full TiC
  document is never loaded into a Python object.
- **Why:** The Health Net CA file is ~670 MB; memory must stay flat.
- **Evidence:** Real run processed 1,717 service entries and 1,511,720 output rows.
- **Alternatives rejected:** `json.load()` / pandas `read_json`.
- **Confidence / risk:** High.

### R-C4-02 — Resolve provider groups by exact ID
- **Rule:** `provider_group_id` values are dictionary keys; array position and numeric
  order are never used. Missing IDs are counted as unresolved and produce no rows.
- **Why:** Provider group IDs are identifiers, not offsets.
- **Evidence:** Synthetic test uses IDs 5 and 2 out of order.
- **Alternatives rejected:** Index-based lookup.
- **Confidence / risk:** High.

### R-C4-03 — Preserve NPI and TIN as strings
- **Rule:** NPI and TIN values are converted to strings in every output.
- **Why:** Leading zeros and formatting must survive CSV round-trips.
- **Evidence:** Synthetic test checks `12-345` and `111`.
- **Alternatives rejected:** Numeric identifiers.
- **Confidence / risk:** High.

### R-C4-04 — Preserve all negotiated prices
- **Rule:** Every `negotiated_prices` entry is emitted; no cheapest/highest/median
  selection occurs in `raw_rates.csv`.
- **Why:** C3 and later stages need the full pricing distribution.
- **Evidence:** Real run emitted 1,511,720 rows from 1,500,288 prices.
- **Alternatives rejected:** Early rate selection in extraction.
- **Confidence / risk:** High.

### R-C4-05 — Count invalid, zero and negative rates without dropping them
- **Rule:** Missing/non-numeric rates are counted in `missing_invalid_nonnumeric_rates`;
  zero and negative rates are counted separately. Rows are still written to
  `raw_rates.csv` with the original rate text.
- **Why:** C3 grades file quality on these signals.
- **Evidence:** Real run had 0 invalid, 0 zero and 0 negative rates.
- **Alternatives rejected:** Silently excluding defective rows.
- **Confidence / risk:** High.

### R-C4-06 — Track unresolved references
- **Rule:** A `provider_references` ID absent from the lookup increments
  `unresolved_provider_references` and `records_rejected`; no NPI/TIN is invented.
- **Why:** Referential integrity must be visible.
- **Evidence:** Synthetic test has one unresolved reference (ID 999).
- **Alternatives rejected:** Emitting placeholder providers.
- **Confidence / risk:** High.

### R-C4-07 — `9999-12-31` is not staleness proof
- **Rule:** Expiration dates are preserved but never interpreted as staleness.
- **Why:** Every Health Net CA price expires on `9999-12-31`.
- **Evidence:** `DATA_FINDINGS.md`.
- **Alternatives rejected:** Filtering on expiration date.
- **Confidence / risk:** High.

### R-C4-08 — Exact-duplicate detection key
- **Rule:** Exact duplicates require equality across provider identifiers, billing code
  and type, negotiated amount, rate type, billing class, setting, modifiers and other
  pricing attributes (service code, additional information, expiration date, etc.).
- **Why:** C3 measures source duplication precisely.
- **Evidence:** Real run found 12,732 exact duplicate rows.
- **Alternatives rejected:** Keying only on NPI/TIN/code/rate.
- **Confidence / risk:** High.

### R-C4-09 — Curated selection key and rules
- **Rule:** `c4result.csv` keeps one row per `(npi, tin, billing_code, billing_code_type,
  billing_code_type_version)` after exact-duplicate removal. Selection order:
  negotiated type, fewer modifiers, professional billing class, most common rate,
  highest rate, then deterministic first row. Every non-selected candidate is written
  to `c4_selection_audit.csv`.
- **Why:** PS requires stating which rate is kept and why.
- **Evidence:** Real run curated 21,858 rows from 1,511,720 extracted rows.
- **Alternatives rejected:** Cheapest/median/highest-only selection without justification.
- **Confidence / risk:** Medium; selection policy is documented and auditable.

### R-C4-10 — Exclude non-10-digit NPIs from curated output only
- **Rule:** `raw_rates.csv` preserves every source row, including NPI `0` or other
  invalid NPI values. `c4result.csv` includes only rows whose NPI is exactly 10 digits;
  excluded rows are counted under `records_rejected` as `invalid_npi_not_10_digits`.
- **Why:** NPIs must be 10-digit identifiers; invalid values are data-quality issues for
  C3/C5 rather than silently corrected values.
- **Evidence:** Real run excluded 5 rows with NPI `0`; curated rows fell from 21,858 to 21,853.
- **Alternatives rejected:** Dropping invalid NPIs from raw data or replacing them with null.
- **Confidence / risk:** High.

### R-C3-01 — Grade every C2 candidate file before C4 extraction
- **Rule:** C3 reads `stage/c2/rate_files.parquet`, resolves every URL to one member in supplied source archive, and writes one file-metric row per candidate. C4 implicitly consumes only C2's sole queued file and requires its C3 metric row.
- **Why:** C1/C2 owns scope; C3 must grade exactly files C4 will extract, never a hand-picked file.
- **Evidence:** `pytest tests/test_c2_c3_c4_connection.py -q` creates C1/C2 source archive, grades queued file, then extracts same source.
- **Alternatives rejected:** Hardcoded Health Net member in C4; it bypasses C2 and can silently extract out-of-scope data.
- **Confidence / risk:** High for one-file California Health Net scope. Multiple candidate files require explicit C4 input until per-file fan-out is added.

### R-C5-01 — Resolve addresses at `(NPI, TIN)` grain
- **Rule:** C5 first creates one candidate-address bridge row per `(NPI, TIN, address)` from C4's provider relationships. Billing codes and rates attach after address candidates are resolved.
- **Why:** A billing code does not determine a practice location. Resolving candidates per billing code repeats identical work and inflates quality counts.
- **Evidence:** Real C4 output has 21,853 rate rows but only 3,775 distinct `(NPI, TIN)` keys; C5 writes `c5_address_candidates.csv` with 5,917 address candidates over those keys.
- **Alternatives rejected:** Resolving candidates at `(NPI, TIN, billing_code)` grain or joining source address data directly on TIN, which NPPES and CMS DAC do not expose.
- **Confidence / risk:** High for pipeline grain. TIN-to-address remains `UNVERIFIED` until group or directory evidence is added; PTD proves only NPI-to-TIN.

### R-C5-02 — Score practice-address evidence before C6 selection
- **Rule:** C5 scores candidate addresses: CMS DAC `+50`, payer PTD physical address `+40` when present, NPPES secondary location `+30`, NPPES primary location `+10`, independent-source corroboration `+20`, and P.O. Box `-60`. Scores ≥60 are `VERIFIED`, 30–59 `PROBABLE`, lower scores `LOW`. C6 selects highest score for each `(NPI, TIN, billing code)` only after C5 candidate generation.
- **Why:** NPPES primary location alone is stale-prone; source corroboration should beat source ordering or lexicographic fallback.
- **Evidence:** `tests/test_c5_candidate_keys.py` proves corroborated address (`80`) beats NPPES secondary-only address (`30`) and that P.O. Boxes are penalized.
- **Alternatives rejected:** Selecting by billing code, which carries price/specialty information but no address evidence; claiming a score proves TIN ownership of address.
- **Confidence / risk:** Medium. CMS DAC supports active provider-location evidence; C4 supports NPI-to-TIN. Neither source alone proves exact TIN-to-street ownership.

### R-C5-03 — CMS National Provider Directory is opt-in, cached location evidence
- **Rule:** When `PTD_NPD_API=1`, C5 queries CMS FHIR `Practitioner` by NPI, then active `PractitionerRole` records with included `Location` resources. California physical locations score `+60`. Raw responses cache per NPI; later runs request only uncached NPIs. `PTD_NPD_MAX_NPIS` defaults to `100`; `0` requests all remaining NPIs. `PTD_NPD_WORKERS` defaults to `4`.
- **Why:** Current directory locations can strengthen stale NPPES/DAC evidence, but thousands of public API calls must be resumable and deliberate.
- **Evidence:** `tests/test_c5_candidate_keys.py` parses CMS FHIR Location address data. One live API check returned a valid FHIR response and location references.
- **Alternatives rejected:** Calling public API once per C4 rate row; treating NPD provider data as proof of TIN-to-street ownership.
- **Confidence / risk:** Medium. NPD coverage depends on directory participation; absent response means `no directory listing`, not `no practice`.

### R-C3-02 — Full streaming grade by default; bounded sampled diagnosis only when explicit
- **Rule:** C3 scans every `in_network` item by default. `PTD_C3_SAMPLE_EVERY=N` retains one deterministic block of `PTD_C3_BLOCK_SIZE` items for every `N` blocks only when requested. C4 rejects sampled C3 output. C3 writes at most `PTD_C3_ROW_FLAG_LIMIT` exception examples while retaining exact exception counts.
- **Why:** Sampling lowers diagnostic cost on extreme files but must never silently drive final rate selection or reported file quality.
- **Evidence:** `tests/test_c3_resource_optimizations.py` verifies deterministic block selection and compact exception flags; `tests/test_c2_c3_c4_connection.py` verifies C4 rejects sampled grades.
- **Alternatives rejected:** Always sampling C3, which weakens C3's required file-level quality claim; loading complete MRFs into memory for exact metrics.
- **Confidence / risk:** High for memory safety. Cohort-outlier rate is reservoir-sampled and must remain labelled as an estimate; row-flag Parquet is an auditable capped sample when exceptions exceed its limit.

### R-C5-04 — Bridge CMS reassignment to DAC by exact NPI and Group PAC ID
- **Rule:** Stream `revalidation_group_reassignment_pa_xref.csv` directly from its ZIP using CP1252. Keep only C4 NPIs. Join each record to CMS Doctors and Clinicians on exact `(Individual NPI, Group PAC ID = org_pac_id)`. Add 15 address-evidence points for an exact bridge and 10 more when normalized PTD TIN business name exactly matches CMS group/facility name. Label the TIN/address link `SUPPORTED` or `STRONGLY_SUPPORTED`; never `DIRECTLY_VERIFIED`.
- **Why:** Reassignment proves that a clinician bills through a Medicare group, while DAC locates that same clinician/group pair. Exact organization-name agreement further supports the PTD TIN entity. Dataset still omits numeric TIN-to-address mapping.
- **Evidence:** Real 2026-10 file streamed 3,634,486 rows; matched 314 rows, 207 C4 NPIs and 250 Group PAC IDs. C5 summary reports 6 strongly supported `(NPI,TIN)` keys. Candidate output contains 130 exact-PAC and 7 exact-PAC-plus-name address candidates after address normalization.
- **Alternatives rejected:** NPI-only reassignment join, fuzzy organization-name matching, and treating Group PAC ID as TIN. Each can falsely attach an address to wrong billing organization.
- **Confidence / risk:** High for exact reassignment/DAC pair; medium for TIN association because business-name record linkage is not numeric TIN proof. Coverage is Medicare-limited.

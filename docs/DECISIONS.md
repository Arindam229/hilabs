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
- **Rule:** A California commercial-group plan containing `POS`, `EPO`, `HMO`, `WholeCare`, `SmartCare`, `CommunityCare`, or `Salud` is classified as that restrictive network even when `PPO` also appears.
- **Why:** Employer/account labels can contain PPO while final benefit design is EPO, HMO, or POS. Restrictive benefit tokens are stronger evidence than a broad account token.
- **Evidence:** Fixture case `CA L CUS PPO SACRAMENTO CITY USD EPO`; `pytest tests/test_c2_network.py -q`.
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

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

### R-C2-01 — Restrictive network tokens override PPO tokens
- **Rule:** A California commercial-group plan containing `POS`, `EPO`, `HMO`, `WholeCare`, `SmartCare`, `CommunityCare`, or `Salud` is classified as that restrictive network even when `PPO` also appears.
- **Why:** Employer/account labels can contain PPO while final benefit design is EPO, HMO, or POS. Restrictive benefit tokens are stronger evidence than a broad account token.
- **Evidence:** Fixture case `CA L CUS PPO SACRAMENTO CITY USD EPO`; `pytest tests/test_c2_network.py -q`.
- **Alternatives rejected:** First-match PPO token; it misclassifies conflicting names.
- **Confidence / risk:** High for explicit tokens. It does not prove rate-level membership in shared files.

### R-C2-02 — Keep unverified network labels unresolved
- **Rule:** `EOA` and plan names without a confirmed token stay `UNRESOLVED`; explicit PPO plan names become candidate files only.
- **Why:** Health Net California PPO, HMO, and other plans share a physical rate file. Plan names alone cannot prove individual rate membership.
- **Evidence:** `docs/ps/DATA_FINDINGS.md` verified shared CA rate file; C2 Excel records confidence and rule ID.
- **Alternatives rejected:** Inferring EOA means EPO or treating a shared file as all-PPO without in-file evidence.
- **Confidence / risk:** Deliberately conservative; C2 evidence pass must validate provider-group or schedule keys.

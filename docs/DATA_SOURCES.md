# Data sources

**One archive holds every input:** `data/hilabs_dataset_2026-10-17.zip` (git-ignored, 2.39 GB, 133 members).
The pipeline finds members by path suffix (`pipeline/io/archive.py`), so the archive's root folder name
does not matter. Sizes + sha256: `MANIFEST.txt`, `MANIFEST_referenced_files.txt`,
`MANIFEST_additions_2026-10-18.txt` inside it. `COMPLETENESS.txt` checks the 66 files the Centene indexes
reference (65 match the server, 1 is a 404 on Centene's side); `NOT_OBTAINED.txt` lists what is missing.

| Member (under the archive root) | Source | As of | Used by |
|---|---|---|---|
| `centene/index/`, `centene/in_network/`, `centene/allowed_amounts/` | centene.com/price-transparency-files.html | 2026-09 | C1–C4 |
| `nppes/` (monthly V2, weekly, deactivations) | download.cms.gov/nppes/NPI_Files.html | 2026-10 | C5, c5hn |
| `cms_dac/DAC_NationalDownloadableFile.csv` | data.cms.gov Doctors and Clinicians | 2026-10 | C5 |
| `nucc/`, `hilabs/` Excel, `cms_pfs/`, `census/` | nucc.org, PS link, cms.gov PFS, census.gov | 2026 | C3, C5 |
| `cms/Revalidation Reassignment List.zip` | data.cms.gov | 2026-10 | C5 (R-C5-04) |
| `cms/Medicare Physician & Other Practitioners - by Provider.zip` | data.cms.gov | **data year 2024** | C5 (R-C5-12) |
| `cms/Medicare Fee-For-Service Public Provider Enrollment.zip` (PECOS Q1+Q3) | data.cms.gov | 2026-07 | C5 flag (R-C5-12) |
| `healthnet/healthnet_pces_responses_2026-10-18.zip` | Health Net Find-a-Provider API, PPO networks 8201/8203 | 2026-10-18 | c5hn (offline replay) |

The `cms/` files were downloaded manually: data.cms.gov returns 403 to scripted access from this network.
A standalone copy can override a member: `PTD_REVALIDATION_ZIP`, `PTD_MEDICARE_PROVIDER_ZIP`, `PTD_PECOS_ENROLLMENT_ZIP`.
The Health Net web bundle holding the API key is not in the archive; only `--offline` replay needs no key.

Run order: `c1 → c2 → c3 → c4 → c5hn → c5 → c6` (`make pipeline`).

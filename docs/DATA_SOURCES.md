# Data sources

Everything is in `data/hilabs_dataset_2026-10-17.zip` (git-ignored): 128 entries, CRC-verified (incl. VALIDATION.md). `COMPLETENESS.txt` inside it checks all 66 files the Centene indexes reference (65 match the server, 1 is a 404 on Centene's side). `NOT_OBTAINED.txt` lists what could not be downloaded and why.

**Read inputs from the zip.** On 2026-10-17 the large working copies in `data/raw/` (all in-network rate files and the NPPES zips) were deleted to free disk; each was first confirmed identical (size + CRC) to its entry in the archive. `data/raw/` now holds only the small files: Centene index files, NUCC CSVs, the HiLabs Excel, the PFS RVU26D zip and the Census ZCTA-county file.

Sources: centene.com/price-transparency-files.html · download.cms.gov/nppes/NPI_Files.html · nucc.org CSV page (all 35 versions) · cms.gov PFS RVU26D (includes GPCI2026 and 26LOCCO) · census.gov ZCTA-county 2020 · data.cms.gov Doctors and Clinicians (in zip only) · HiLabs Excel (PS link).

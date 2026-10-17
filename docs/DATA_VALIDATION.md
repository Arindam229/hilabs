# Dataset validation — 2026-10-17

Every file in hilabs_dataset_2026-10-17.zip was read in full: JSON stream-parsed end to end (TiC required keys checked), every CSV row checked against its header column count, every Excel workbook and nested zip opened (nested zips CRC-tested). Files are kept exactly as published; data-quality issues are measured here and handled by the pipeline (C3/C4), never edited in the raw files.

Result: 147 OK, 1 flagged.

Flagged: nucc/nucc_taxonomy_90.csv (NUCC v9.0, 2009) — line 2 is an AMA copyright notice with 2 fields, not data; file is cp1252-encoded. Source-side, not corruption; the notice requires the file to stay unchanged. Skip that row when reading.

## Mandatory files (PS section 4)

| PS dataset | File(s) | Check |
|---|---|---|
| Centene index files (Ambetter, Health Net, QualChoice, Fidelis) | centene/index/ — 11 files, every link on the Centene page | all parse; HN index 1,693 plans |
| In-scope rate file (Health Net CA, commercial group) | centene/in_network/2026-09-30_..._healthnet-ca_in-network.json | parses; 2,825 provider groups, 1,717 billing items, 1,500,288 prices |
| NPPES extract (CA NPIs, type, taxonomy, primary + secondary addresses) | nppes/NPPES_Data_Dissemination_October_2026_V2.zip | npidata 9,852,180 rows x 330 cols (type 1: 7,512,094; type 2: 1,982,161; no type/deactivated: 357,925; CA practice rows: 1,196,152); pl_pfile 1,274,332 secondary locations; 0 ragged rows |
| NUCC taxonomy | nucc/nucc_taxonomy_261.csv (current) + 34 older versions | 883 codes, clean |
| Specialty to Billing Code Mapping (HiLabs Excel) | hilabs/Rate Benchmarking Individual Weights_Hackathon.xlsx | 3 sheets: Taxonomy-Spec Xwalk 213 rows, Specialty Weights 48, Spec-Proc Weights 946 |

## Data-quality signals already measurable (glossary terms)

- $0 rates: 0 of 7,650,002 prices across all 32 in-network files.
- Stale contracts (expiration_date before 2026-10-17): 0 — every price in HN CA expires 9999-12-31, so expiry cannot reveal staleness; use last_updated_on and NPPES deactivations instead.
- Duplicates, outliers, ghost rates: need the C3/C4 joins; not measurable by a parse.
- Deactivated NPIs: 357,928 in the deactivation report vs 357,925 NPPES rows with no entity type (3-row difference, to examine in REF).

## Every check

| Status | File | Detail |
|---|---|---|
| OK | centene/in_network/2026-09-28_centene-management-company-llc_ambetter-ca_in-network.json | {'provider_groups': 3141, 'items': 4360, 'prices': 247890, 'zero_rates': 0, 'expired_prices': 0, 'version': '2.0.0', 'last_updated': '2026-09-28'} |
| OK | centene/in_network/2026-09-30_centene-management-company-llc_healthnet-ca_in-network.json | {'provider_groups': 2825, 'items': 1717, 'prices': 1500288, 'zero_rates': 0, 'expired_prices': 0, 'version': '2.0.0', 'last_updated': '2026-10-06'} |
| OK | centene/in_network/2026-09-30_centene-management-company-llc_healthnet-or_in-network.json | {'provider_groups': 218, 'items': 337, 'prices': 18468, 'zero_rates': 0, 'expired_prices': 0, 'version': '2.0.0', 'last_updated': '2026-10-06'} |
| OK | centene/index/2026-09-28_ambetter_index.json | {'structures': 28, 'plans': 1120, 'version': '2.0.0', 'last_updated': '2026-09-28'} |
| OK | centene/index/2026-09-28_fidelis_index.json | {'structures': 2, 'plans': 94, 'version': '2.0.0', 'last_updated': '2026-09-28'} |
| OK | centene/index/2026-09-28_qualchoice_alf_plan_index.json | {'structures': 1, 'plans': 32, 'version': '2.0.0', 'last_updated': '2026-09-28'} |
| OK | centene/index/2026-09-28_qualchoice_arnold_and_blevins_index.json | {'structures': 1, 'plans': 1, 'version': '2.0.0', 'last_updated': '2026-09-28'} |
| OK | centene/index/2026-09-28_qualchoice_big_four_index.json | {'structures': 1, 'plans': 4, 'version': '2.0.0', 'last_updated': '2026-09-28'} |
| OK | centene/index/2026-09-28_qualchoice_city_of_fort_smith_index.json | {'structures': 1, 'plans': 4, 'version': '2.0.0', 'last_updated': '2026-09-28'} |
| OK | centene/index/2026-09-28_qualchoice_city_of_hot_springs_index.json | {'structures': 1, 'plans': 2, 'version': '2.0.0', 'last_updated': '2026-09-28'} |
| OK | centene/index/2026-09-28_qualchoice_dillards_index.json | {'structures': 1, 'plans': 12, 'version': '2.0.0', 'last_updated': '2026-09-28'} |
| OK | centene/index/2026-09-28_qualchoice_index.json | {'structures': 1, 'plans': 308, 'version': '2.0.0', 'last_updated': '2026-09-28'} |
| OK | centene/index/2026-09-28_qualchoice_jv_manufacturing_index.json | {'structures': 1, 'plans': 5, 'version': '2.0.0', 'last_updated': '2026-09-28'} |
| OK | centene/index/2026-09-30_healthnet_index.json | {'structures': 2, 'plans': 1693, 'version': '2.0.0', 'last_updated': '2026-09-30'} |
| OK | centene/index/_urls.txt | 1064 bytes |
| OK | hilabs/Rate Benchmarking Individual Weights_Hackathon.xlsx | {'Taxonomy-Spec Xwalk': 214, 'Specialty Weights': 49, 'Spec-Proc Weights': 947} |
| OK | nppes/NPPES_Data_Dissemination_October_2026_V2.zip | nested zip CRC OK, 10 entries |
| OK | nppes/NPPES_Data_Dissemination_October_2026_V2.zip::othername_pfile_20050523-20261011.csv | cols 4 rows 864775 ragged 0 |
| OK | nppes/NPPES_Data_Dissemination_October_2026_V2.zip::endpoint_pfile_20050523-20261011.csv | cols 19 rows 608236 ragged 0 |
| OK | nppes/NPPES_Data_Dissemination_October_2026_V2.zip::npidata_pfile_20050523-20261011.csv | cols 330 rows 9852180 ragged 0 / type1 7512094 type2 1982161 no-type(deactivated) 357925 / CA practice rows 1196152 |
| OK | nppes/NPPES_Data_Dissemination_October_2026_V2.zip::pl_pfile_20050523-20261011.csv | cols 10 rows 1274332 ragged 0 |
| OK | nppes/NPPES_Deactivated_NPI_Report_101226_V2.zip | nested zip CRC OK, 1 entries |
| OK | nppes/NPPES_Deactivated_NPI_Report_101226_V2.zip::NPPES Deactivated NPI Report 20261012.xlsx | {'DeactivatedNPIs': 357928} |
| OK | nucc/nucc_taxonomy_261.csv | cols 8 rows 883 ragged 0 enc utf-8-sig |
| OK | docs/PROBLEM_STATEMENT.md | 7283 bytes |
| OK | cms_dac/DAC_NationalDownloadableFile.csv | cols 31 rows 3630233 ragged 0 enc utf-8-sig |
| OK | MANIFEST.txt | 1327 bytes |
| OK | centene/allowed_amounts/2026-09-28_centene-management-company-llc_ambetter-al_allowed-amounts.json | {'oon_items': 136, 'version': '2.0.0', 'last_updated': '2026-09-28'} |
| OK | centene/in_network/2026-09-28_centene-management-company-llc_ambetter-al_in-network.json | {'provider_groups': 876, 'items': 3483, 'prices': 29744, 'zero_rates': 0, 'expired_prices': 0, 'version': '2.0.0', 'last_updated': '2026-09-28'} |
| OK | centene/allowed_amounts/2026-09-28_centene-management-company-llc_ambetter-ar_allowed-amounts.json | {'oon_items': 343, 'version': '2.0.0', 'last_updated': '2026-09-28'} |
| OK | centene/in_network/2026-09-28_centene-management-company-llc_ambetter-ar_in-network.json | {'provider_groups': 1173, 'items': 5334, 'prices': 287202, 'zero_rates': 0, 'expired_prices': 0, 'version': '2.0.0', 'last_updated': '2026-09-28'} |
| OK | centene/allowed_amounts/2026-09-28_centene-management-company-llc_ambetter-az_allowed-amounts.json | {'oon_items': 195, 'version': '2.0.0', 'last_updated': '2026-09-28'} |
| OK | centene/in_network/2026-09-28_centene-management-company-llc_ambetter-az_in-network.json | {'provider_groups': 1053, 'items': 3896, 'prices': 217504, 'zero_rates': 0, 'expired_prices': 0, 'version': '2.0.0', 'last_updated': '2026-09-28'} |
| OK | centene/allowed_amounts/2026-09-28_centene-management-company-llc_ambetter-ca_allowed-amounts.json | {'oon_items': 174, 'version': '2.0.0', 'last_updated': '2026-09-28'} |
| OK | centene/allowed_amounts/2026-09-28_centene-management-company-llc_ambetter-de_allowed-amounts.json | {'oon_items': 25, 'version': '2.0.0', 'last_updated': '2026-09-28'} |
| OK | centene/in_network/2026-09-28_centene-management-company-llc_ambetter-de_in-network.json | {'provider_groups': 289, 'items': 1101, 'prices': 4308, 'zero_rates': 0, 'expired_prices': 0, 'version': '2.0.0', 'last_updated': '2026-09-28'} |
| OK | centene/allowed_amounts/2026-09-28_centene-management-company-llc_ambetter-fl_allowed-amounts.json | {'oon_items': 601, 'version': '2.0.0', 'last_updated': '2026-09-28'} |
| OK | centene/in_network/2026-09-28_centene-management-company-llc_ambetter-fl_in-network.json | {'provider_groups': 6780, 'items': 7937, 'prices': 1546619, 'zero_rates': 0, 'expired_prices': 0, 'version': '2.0.0', 'last_updated': '2026-09-28'} |
| OK | centene/allowed_amounts/2026-09-28_centene-management-company-llc_ambetter-ga_allowed-amounts.json | {'oon_items': 276, 'version': '2.0.0', 'last_updated': '2026-09-28'} |
| OK | centene/in_network/2026-09-28_centene-management-company-llc_ambetter-ga_in-network.json | {'provider_groups': 3378, 'items': 6723, 'prices': 906310, 'zero_rates': 0, 'expired_prices': 0, 'version': '2.0.0', 'last_updated': '2026-09-28'} |
| OK | centene/allowed_amounts/2026-09-28_centene-management-company-llc_ambetter-ia_allowed-amounts.json | {'oon_items': 35, 'version': '2.0.0', 'last_updated': '2026-09-28'} |
| OK | centene/in_network/2026-09-28_centene-management-company-llc_ambetter-ia_in-network.json | {'provider_groups': 384, 'items': 1155, 'prices': 5419, 'zero_rates': 0, 'expired_prices': 0, 'version': '2.0.0', 'last_updated': '2026-09-28'} |
| OK | centene/allowed_amounts/2026-09-28_centene-management-company-llc_ambetter-il_allowed-amounts.json | {'oon_items': 71, 'version': '2.0.0', 'last_updated': '2026-09-28'} |
| OK | centene/in_network/2026-09-28_centene-management-company-llc_ambetter-il_in-network.json | {'provider_groups': 1481, 'items': 3055, 'prices': 29128, 'zero_rates': 0, 'expired_prices': 0, 'version': '2.0.0', 'last_updated': '2026-09-28'} |
| OK | centene/allowed_amounts/2026-09-28_centene-management-company-llc_ambetter-in_allowed-amounts.json | {'oon_items': 116, 'version': '2.0.0', 'last_updated': '2026-09-28'} |
| OK | centene/in_network/2026-09-28_centene-management-company-llc_ambetter-in_in-network.json | {'provider_groups': 2467, 'items': 5024, 'prices': 378369, 'zero_rates': 0, 'expired_prices': 0, 'version': '2.0.0', 'last_updated': '2026-09-28'} |
| OK | centene/allowed_amounts/2026-09-28_centene-management-company-llc_ambetter-ks_allowed-amounts.json | {'oon_items': 100, 'version': '2.0.0', 'last_updated': '2026-09-28'} |
| OK | centene/in_network/2026-09-28_centene-management-company-llc_ambetter-ks_in-network.json | {'provider_groups': 147, 'items': 506, 'prices': 977, 'zero_rates': 0, 'expired_prices': 0, 'version': '2.0.0', 'last_updated': '2026-09-28'} |
| OK | centene/allowed_amounts/2026-09-28_centene-management-company-llc_ambetter-ky_allowed-amounts.json | {'oon_items': 213, 'version': '2.0.0', 'last_updated': '2026-09-28'} |
| OK | centene/in_network/2026-09-28_centene-management-company-llc_ambetter-ky_in-network.json | {'provider_groups': 1091, 'items': 3246, 'prices': 30348, 'zero_rates': 0, 'expired_prices': 0, 'version': '2.0.0', 'last_updated': '2026-09-28'} |
| OK | centene/allowed_amounts/2026-09-28_centene-management-company-llc_ambetter-la_allowed-amounts.json | {'oon_items': 152, 'version': '2.0.0', 'last_updated': '2026-09-28'} |
| OK | centene/in_network/2026-09-28_centene-management-company-llc_ambetter-la_in-network.json | {'provider_groups': 719, 'items': 2860, 'prices': 26294, 'zero_rates': 0, 'expired_prices': 0, 'version': '2.0.0', 'last_updated': '2026-09-28'} |
| OK | centene/allowed_amounts/2026-09-28_centene-management-company-llc_ambetter-mi_allowed-amounts.json | {'oon_items': 45, 'version': '2.0.0', 'last_updated': '2026-09-28'} |
| OK | centene/in_network/2026-09-28_centene-management-company-llc_ambetter-mi_in-network.json | {'provider_groups': 758, 'items': 2420, 'prices': 16217, 'zero_rates': 0, 'expired_prices': 0, 'version': '2.0.0', 'last_updated': '2026-09-28'} |
| OK | centene/allowed_amounts/2026-09-28_centene-management-company-llc_ambetter-mo_allowed-amounts.json | {'oon_items': 275, 'version': '2.0.0', 'last_updated': '2026-09-28'} |
| OK | centene/in_network/2026-09-28_centene-management-company-llc_ambetter-mo_in-network.json | {'provider_groups': 3317, 'items': 5307, 'prices': 189010, 'zero_rates': 0, 'expired_prices': 0, 'version': '2.0.0', 'last_updated': '2026-09-30'} |
| OK | centene/allowed_amounts/2026-09-28_centene-management-company-llc_ambetter-ms_allowed-amounts.json | {'oon_items': 217, 'version': '2.0.0', 'last_updated': '2026-09-28'} |
| OK | centene/in_network/2026-09-28_centene-management-company-llc_ambetter-ms_in-network.json | {'provider_groups': 2624, 'items': 5139, 'prices': 233807, 'zero_rates': 0, 'expired_prices': 0, 'version': '2.0.0', 'last_updated': '2026-09-28'} |
| OK | centene/allowed_amounts/2026-09-28_centene-management-company-llc_ambetter-nc_allowed-amounts.json | {'oon_items': 222, 'version': '2.0.0', 'last_updated': '2026-09-28'} |
| OK | centene/in_network/2026-09-28_centene-management-company-llc_ambetter-nc_in-network.json | {'provider_groups': 1256, 'items': 5145, 'prices': 185809, 'zero_rates': 0, 'expired_prices': 0, 'version': '2.0.0', 'last_updated': '2026-09-28'} |
| OK | centene/allowed_amounts/2026-09-28_centene-management-company-llc_ambetter-ne_allowed-amounts.json | {'oon_items': 74, 'version': '2.0.0', 'last_updated': '2026-09-28'} |
| OK | centene/in_network/2026-09-28_centene-management-company-llc_ambetter-ne_in-network.json | {'provider_groups': 1215, 'items': 3752, 'prices': 58449, 'zero_rates': 0, 'expired_prices': 0, 'version': '2.0.0', 'last_updated': '2026-09-28'} |
| OK | centene/allowed_amounts/2026-09-28_centene-management-company-llc_ambetter-nh_allowed-amounts.json | {'oon_items': 16, 'version': '2.0.0', 'last_updated': '2026-09-30'} |
| OK | centene/in_network/2026-09-28_centene-management-company-llc_ambetter-nh_in-network.json | {'provider_groups': 507, 'items': 2175, 'prices': 11095, 'zero_rates': 0, 'expired_prices': 0, 'version': '2.0.0', 'last_updated': '2026-09-28'} |
| OK | centene/allowed_amounts/2026-09-28_centene-management-company-llc_ambetter-nj_allowed-amounts.json | {'oon_items': 7, 'version': '2.0.0', 'last_updated': '2026-09-30'} |
| OK | centene/in_network/2026-09-28_centene-management-company-llc_ambetter-nj_in-network.json | {'provider_groups': 396, 'items': 993, 'prices': 3625, 'zero_rates': 0, 'expired_prices': 0, 'version': '2.0.0', 'last_updated': '2026-09-28'} |
| OK | centene/allowed_amounts/2026-09-28_centene-management-company-llc_ambetter-nv_allowed-amounts.json | {'oon_items': 40, 'version': '2.0.0', 'last_updated': '2026-09-28'} |
| OK | centene/in_network/2026-09-28_centene-management-company-llc_ambetter-nv_in-network.json | {'provider_groups': 675, 'items': 2681, 'prices': 26079, 'zero_rates': 0, 'expired_prices': 0, 'version': '2.0.0', 'last_updated': '2026-09-28'} |
| OK | centene/allowed_amounts/2026-09-28_centene-management-company-llc_ambetter-oh_allowed-amounts.json | {'oon_items': 154, 'version': '2.0.0', 'last_updated': '2026-09-28'} |
| OK | centene/in_network/2026-09-28_centene-management-company-llc_ambetter-oh_in-network.json | {'provider_groups': 2185, 'items': 4196, 'prices': 86459, 'zero_rates': 0, 'expired_prices': 0, 'version': '1.0.0', 'last_updated': '2026-09-28'} |
| OK | centene/allowed_amounts/2026-09-28_centene-management-company-llc_ambetter-ok_allowed-amounts.json | {'oon_items': 219, 'version': '2.0.0', 'last_updated': '2026-09-28'} |
| OK | centene/in_network/2026-09-28_centene-management-company-llc_ambetter-ok_in-network.json | {'provider_groups': 1539, 'items': 3470, 'prices': 25525, 'zero_rates': 0, 'expired_prices': 0, 'version': '2.0.0', 'last_updated': '2026-09-28'} |
| OK | centene/allowed_amounts/2026-09-28_centene-management-company-llc_ambetter-pa_allowed-amounts.json | {'oon_items': 35, 'version': '2.0.0', 'last_updated': '2026-09-28'} |
| OK | centene/in_network/2026-09-28_centene-management-company-llc_ambetter-pa_in-network.json | {'provider_groups': 1276, 'items': 2696, 'prices': 31150, 'zero_rates': 0, 'expired_prices': 0, 'version': '2.0.0', 'last_updated': '2026-09-28'} |
| OK | centene/allowed_amounts/2026-09-28_centene-management-company-llc_ambetter-sc_allowed-amounts.json | {'oon_items': 265, 'version': '2.0.0', 'last_updated': '2026-09-28'} |
| OK | centene/in_network/2026-09-28_centene-management-company-llc_ambetter-sc_in-network.json | {'provider_groups': 2086, 'items': 4663, 'prices': 91421, 'zero_rates': 0, 'expired_prices': 0, 'version': '2.0.0', 'last_updated': '2026-09-28'} |
| OK | centene/allowed_amounts/2026-09-28_centene-management-company-llc_ambetter-tn_allowed-amounts.json | {'oon_items': 248, 'version': '2.0.0', 'last_updated': '2026-09-28'} |
| OK | centene/in_network/2026-09-28_centene-management-company-llc_ambetter-tn_in-network.json | {'provider_groups': 3101, 'items': 4959, 'prices': 169444, 'zero_rates': 0, 'expired_prices': 0, 'version': '2.0.0', 'last_updated': '2026-09-28'} |
| OK | centene/allowed_amounts/2026-09-28_centene-management-company-llc_ambetter-tx_allowed-amounts.json | {'oon_items': 758, 'version': '2.0.0', 'last_updated': '2026-09-28'} |
| OK | centene/in_network/2026-09-28_centene-management-company-llc_ambetter-tx_in-network.json | {'provider_groups': 5612, 'items': 7308, 'prices': 665753, 'zero_rates': 0, 'expired_prices': 0, 'version': '2.0.0', 'last_updated': '2026-09-28'} |
| OK | centene/allowed_amounts/2026-09-28_centene-management-company-llc_ambetter-wa_allowed-amounts.json | {'oon_items': 76, 'version': '2.0.0', 'last_updated': '2026-09-28'} |
| OK | centene/in_network/2026-09-28_centene-management-company-llc_ambetter-wa_in-network.json | {'provider_groups': 1853, 'items': 4151, 'prices': 53898, 'zero_rates': 0, 'expired_prices': 0, 'version': '2.0.0', 'last_updated': '2026-09-28'} |
| OK | centene/allowed_amounts/2026-09-28_centene-management-company-llc_fidelis-es_allowed-amounts.json | {'oon_items': 156, 'version': '2.0.0', 'last_updated': '2026-09-28'} |
| OK | centene/in_network/2026-09-28_centene-management-company-llc_fidelis-es_in-network.json | {'provider_groups': 1841, 'items': 2480, 'prices': 379958, 'zero_rates': 0, 'expired_prices': 0, 'version': '2.0.0', 'last_updated': '2026-10-06'} |
| OK | centene/allowed_amounts/2026-09-28_centene-management-company-llc_fidelis-ex_allowed-amounts.json | {'oon_items': 49, 'version': '2.0.0', 'last_updated': '2026-09-28'} |
| OK | centene/in_network/2026-09-28_centene-management-company-llc_fidelis-ex_in-network.json | {'provider_groups': 1380, 'items': 1554, 'prices': 193435, 'zero_rates': 0, 'expired_prices': 0, 'version': '2.0.0', 'last_updated': '2026-10-06'} |
| OK | centene/allowed_amounts/2026-09-28_centene-management-company-llc_qualchoice_allowed-amounts.json | {'oon_items': 32, 'version': '2.0.0', 'last_updated': '2026-09-28'} |
| OK | centene/allowed_amounts/2026-09-30_centene-management-company-llc_healthnet-ca_allowed-amounts.json | {'oon_items': 336, 'version': '2.0.0', 'last_updated': '2026-09-30'} |
| OK | centene/allowed_amounts/2026-09-30_centene-management-company-llc_healthnet-or_allowed-amounts.json | {'oon_items': 28, 'version': '2.0.0', 'last_updated': '2026-09-30'} |
| OK | MANIFEST_referenced_files.txt | 952 bytes |
| OK | COMPLETENESS.txt | 17609 bytes |
| OK | nppes/NPPES_Data_Dissemination_100526_101126_Weekly_V2.zip | nested zip CRC OK, 10 entries |
| OK | nppes/NPPES_Data_Dissemination_100526_101126_Weekly_V2.zip::endpoint_pfile_20261005-20261011.csv | cols 19 rows 2679 ragged 0 |
| OK | nppes/NPPES_Data_Dissemination_100526_101126_Weekly_V2.zip::othername_pfile_20261005-20261011.csv | cols 4 rows 2548 ragged 0 |
| OK | nppes/NPPES_Data_Dissemination_100526_101126_Weekly_V2.zip::pl_pfile_20261005-20261011.csv | cols 10 rows 11790 ragged 0 |
| OK | nppes/NPPES_Data_Dissemination_100526_101126_Weekly_V2.zip::npidata_pfile_20261005-20261011.csv | cols 330 rows 32641 ragged 0 / type1 25495 type2 6459 no-type(deactivated) 687 / CA practice rows 3885 |
| OK | nppes/NPI-What-You-Need-To-Know.pdf | pdf header |
| OK | nucc/nucc_characteristics5.pdf | pdf header |
| OK | nucc/nucc_taxonomy_100.csv | cols 6 rows 815 ragged 0 enc cp1252 |
| OK | nucc/nucc_taxonomy_101.csv | cols 6 rows 818 ragged 0 enc cp1252 |
| OK | nucc/nucc_taxonomy_110.csv | cols 6 rows 821 ragged 0 enc cp1252 |
| OK | nucc/nucc_taxonomy_111.csv | cols 6 rows 824 ragged 0 enc cp1252 |
| OK | nucc/nucc_taxonomy_120.csv | cols 6 rows 827 ragged 0 enc cp1252 |
| OK | nucc/nucc_taxonomy_121.csv | cols 6 rows 829 ragged 0 enc cp1252 |
| OK | nucc/nucc_taxonomy_130.csv | cols 6 rows 830 ragged 0 enc cp1252 |
| OK | nucc/nucc_taxonomy_131.csv | cols 6 rows 830 ragged 0 enc cp1252 |
| OK | nucc/nucc_taxonomy_140.csv | cols 6 rows 831 ragged 0 enc cp1252 |
| OK | nucc/nucc_taxonomy_141.csv | cols 6 rows 833 ragged 0 enc cp1252 |
| OK | nucc/nucc_taxonomy_150.csv | cols 6 rows 834 ragged 0 enc cp1252 |
| OK | nucc/nucc_taxonomy_151.csv | cols 6 rows 838 ragged 0 enc utf-8-sig |
| OK | nucc/nucc_taxonomy_160.csv | cols 6 rows 845 ragged 0 enc cp1252 |
| OK | nucc/nucc_taxonomy_161.csv | cols 6 rows 848 ragged 0 enc cp1252 |
| OK | nucc/nucc_taxonomy_170.csv | cols 6 rows 851 ragged 0 enc cp1252 |
| OK | nucc/nucc_taxonomy_171.csv | cols 6 rows 853 ragged 0 enc utf-8-sig |
| OK | nucc/nucc_taxonomy_180.csv | cols 6 rows 854 ragged 0 enc utf-8-sig |
| OK | nucc/nucc_taxonomy_181.csv | cols 6 rows 855 ragged 0 enc utf-8-sig |
| OK | nucc/nucc_taxonomy_190.csv | cols 6 rows 856 ragged 0 enc utf-8-sig |
| OK | nucc/nucc_taxonomy_191.csv | cols 6 rows 862 ragged 0 enc utf-8-sig |
| OK | nucc/nucc_taxonomy_200.csv | cols 6 rows 862 ragged 0 enc utf-8-sig |
| OK | nucc/nucc_taxonomy_201.csv | cols 6 rows 862 ragged 0 enc utf-8-sig |
| OK | nucc/nucc_taxonomy_210.csv | cols 7 rows 865 ragged 0 enc utf-8-sig |
| OK | nucc/nucc_taxonomy_211.csv | cols 8 rows 866 ragged 0 enc utf-8-sig |
| OK | nucc/nucc_taxonomy_220.csv | cols 8 rows 868 ragged 0 enc utf-8-sig |
| OK | nucc/nucc_taxonomy_221.csv | cols 11 rows 868 ragged 0 enc utf-8-sig |
| OK | nucc/nucc_taxonomy_230.csv | cols 8 rows 873 ragged 0 enc cp1252 |
| OK | nucc/nucc_taxonomy_231.csv | cols 8 rows 874 ragged 0 enc cp1252 |
| OK | nucc/nucc_taxonomy_240.csv | cols 8 rows 874 ragged 0 enc utf-8-sig |
| OK | nucc/nucc_taxonomy_241.csv | cols 8 rows 874 ragged 0 enc utf-8-sig |
| OK | nucc/nucc_taxonomy_250.csv | cols 8 rows 879 ragged 0 enc utf-8-sig |
| OK | nucc/nucc_taxonomy_251.csv | cols 8 rows 883 ragged 0 enc utf-8-sig |
| FAIL | nucc/nucc_taxonomy_90.csv | cols 6 rows 810 ragged 1 enc cp1252 |
| OK | nucc/nucc_taxonomy_91.csv | cols 6 rows 814 ragged 0 enc cp1252 |
| OK | cms_pfs/rvu26d-updated-08-26-2026.zip | nested zip CRC OK, 19 entries |
| OK | cms_pfs/rvu26d-updated-08-26-2026.zip::GPCI2026.csv | cols 7 rows 120 ragged 0 enc utf-8-sig |
| OK | cms_pfs/rvu26d-updated-08-26-2026.zip::GPCI2026.xlsx | {'Addendum E. GPCIs': 122} |
| OK | cms_pfs/rvu26d-updated-08-26-2026.zip::OPPSCAP_Oct.csv | cols 7 rows 16101 ragged 0 enc utf-8-sig |
| OK | cms_pfs/rvu26d-updated-08-26-2026.zip::OPPSCAP_Oct.xlsx | {'OPPSCAP_Oct': 16102} |
| OK | cms_pfs/rvu26d-updated-08-26-2026.zip::PPRRVU2026_Oct_nonQPP.csv | cols 32 rows 19462 ragged 0 enc utf-8-sig |
| OK | cms_pfs/rvu26d-updated-08-26-2026.zip::PPRRVU2026_Oct_nonQPP.xlsx | {'PPRRVU2026_Oct_nonQPP': 19463} |
| OK | cms_pfs/rvu26d-updated-08-26-2026.zip::PPRRVU2026_Oct_QPP.csv | cols 32 rows 11987 ragged 0 enc utf-8-sig |
| OK | cms_pfs/rvu26d-updated-08-26-2026.zip::PPRRVU2026_Oct_QPP.xlsx | {'PPRRVU2026_Oct_QPP': 11988} |
| OK | cms_pfs/rvu26d-updated-08-26-2026.zip::26LOCCO.csv | cols 6 rows 170 ragged 0 enc utf-8-sig |
| OK | cms_pfs/rvu26d-updated-08-26-2026.zip::26LOCCO.xlsx | {'26LOCCO': 171} |
| OK | cms_pfs/rvu26d-updated-08-26-2026.zip::ANES2026.csv | cols 5 rows 112 ragged 0 enc utf-8-sig |
| OK | cms_pfs/rvu26d-updated-08-26-2026.zip::ANES2026.xlsx | {'Locality Adjusted CFs': 113, 'Anesthesia Shares': 4} |
| OK | census/tab20_zcta520_county20_natl.txt | cols 18 rows 47863 ragged 0 enc utf-8-sig |
| OK | NOT_OBTAINED.txt | 1009 bytes |
| OK | docs/DATA_SOURCES.md | 5094 bytes |

Not in the archive (see NOT_OBTAINED.txt): QualChoice in-network file (HTTP 404 at Centene); CMS Revalidation Reassignment List (data.cms.gov blocks this machine, VPN needed).

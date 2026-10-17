# Data findings

Facts about the real files. Mark each **verified** (with how) or **hypothesis**. Update as you learn.

## Verified (2026-10-17, by direct download/inspection)

- Centene index page lists 11 index files: Ambetter, Fidelis, QualChoice (main + 7 employer sub-indexes),
  Health Net. Dated `2026-09-28` / `2026-09-30`; page says monthly refresh, so URLs change monthly — read
  them from the page or `config.yaml`, never hardcode in code.
- MHN has no index of its own: page says it is folded into Ambetter CA (marketplace) and Health Net (commercial).
- **Health Net index** (`2026-09-30_healthnet_index.json`, 576 KB): 2 `reporting_structure` entries,
  1,693 plans, all `plan_market_type = group`, `plan_id_type` = ein (1,692) / hios (1).
  - Structure 1 → **one** in-network file `..._healthnet-ca_in-network.json` (701,615,514 bytes,
    uncompressed JSON) shared by 1,312 CA plans. By plan name: contains "HMO" 719, "PPO" 456, "POS" 6, none of these 131 (mostly "EOA …", some union/trust plans).
  - Structure 2 → `..._healthnet-or_in-network.json` (Oregon, out of scope), 381 plans mostly employer names.
  - ⇒ Index alone cannot separate PPO from HMO in CA: **network must be resolved inside the rate file.**
- **Health Net CA rate file** (first 3 MB sampled): TiC schema `version 2.0.0`, entity type
  "Third Party Administrator", `last_updated_on 2026-10-06`.
  - `provider_references` come first (inline), then `in_network`. Each group: `npi[]` + `tin{type,value,business_name}`.
  - `network_name` field exists on every provider reference but was empty in all 2,825 sampled.
  - Some `tin.business_name` values are network labels, not businesses: `"PPO: Los Angeles County"` (41),
    `"PPO: San Bernardino County"` (11), … 12 CA counties seen in sample.
  - `negotiated_prices[].additional_information` carries short codes like `1EB11`, `3HB21`, `3CA11`.
  - In sample: `negotiated_type` all `negotiated`; `billing_class` 2,590 institutional / 14 professional;
    `expiration_date` all `9999-12-31` (so expiration is useless for staleness — use `last_updated_on`,
    contract signals, and cross-file comparison instead).

## Hypotheses (unconfirmed — test before relying on them)

- H1: `additional_information` codes identify network/product (e.g. PPO vs HMO fee schedule). Test: co-occurrence
  of codes with `PPO: <County>` provider groups; code distribution per billing class.
- H2: `PPO: <County>` business_name groups mark PPO-network providers (or county-based PPO fee schedules).
- H3: Ambetter (marketplace) + Fidelis (NY) + QualChoice (AR) contain no CA commercial-group PPO → ruled out
  by market type / state. Must be shown with counts, not asserted.
- H4: Health Net publishes a CMS-mandated FHIR Provider Directory API (Da Vinci PDex Plan-Net) with
  network-tagged practitioner locations — strongest candidate for verified addresses + PPO membership.
- H5: "EOA" plans are a Health Net product line (Elect/Open Access?) — classify only with evidence.

## Size / environment constraints

- Dev box: ~5 GB free disk, 12 cores, 15 GB RAM. NPPES full zip ≈ 1 GB → ~10 GB CSV unzipped:
  stream-filter to CA straight from the zip; do not unzip to disk.

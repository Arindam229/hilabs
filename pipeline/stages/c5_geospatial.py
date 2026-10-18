"""Post-process C5 candidates with cached geocoding and TIN geography."""

from __future__ import annotations

import csv
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from pipeline.stages.c5_address import (
    _geo_support,
    _geocode_address,
    _haversine_km,
    _normalize_address,
)


def enrich_c5_directory(stage_dir: Path) -> dict[str, int]:
    """Enrich existing C5 CSVs; preserve source files until enriched files finish."""
    candidates_path = stage_dir / "c5_address_candidates.csv"
    result_path = stage_dir / "c5result.csv"
    cache_path = stage_dir / "census_geocode_cache.json"
    if not candidates_path.is_file() or not result_path.is_file():
        raise FileNotFoundError("C5 candidate/result CSVs are required")

    with candidates_path.open(newline="", encoding="utf-8") as f:
        candidates = list(csv.DictReader(f))
    with result_path.open(newline="", encoding="utf-8") as f:
        result = list(csv.DictReader(f))
    cache = json.loads(cache_path.read_text()) if cache_path.is_file() else {}
    addresses = {}
    address_rows = result if os.environ.get("PTD_GEO_CANONICAL_ONLY") == "1" else candidates
    for row in address_rows:
        norm = row.get("Normalized_Address", "") or _normalize_address(row.get("Address", ""), "", "", "", "")
        address = row.get("Address", "")
        if norm and address:
            addresses.setdefault(norm, address)

    os.environ["PTD_GEOCODE"] = "1"
    workers = max(1, min(16, int(os.environ.get("PTD_GEOCODE_WORKERS", "8"))))
    pending = {norm: address for norm, address in addresses.items() if norm not in cache}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_geocode_address, address, cache): norm for norm, address in pending.items()}
        for index, future in enumerate(as_completed(futures), start=1):
            norm = futures[future]
            try:
                cache[norm] = future.result()
            except (OSError, ValueError, KeyError, TimeoutError):
                cache[norm] = {"status": "error", "latitude": None, "longitude": None}
            if index % 100 == 0:
                cache_path.write_text(json.dumps(cache, sort_keys=True) + "\n")
                print(f"C5 geo: {index}/{len(pending)} addresses", flush=True)
    cache_path.write_text(json.dumps(cache, sort_keys=True) + "\n")

    # Weak TIN support from geocoded physical addresses. This is clustering evidence,
    # not proof that TIN legally owns site.
    trusted = {}
    zip_counts = {}
    address_npis = {}
    tin_npis = {}
    for row in candidates:
        if row.get("Address_Role") == "mailing/po_box" or row.get("Geocode_Status") != "matched":
            continue
        tin = row.get("TIN", "")
        npi = row.get("NPI", "")
        tin_npis.setdefault(tin, set()).add(npi)
        norm = row.get("Normalized_Address", "")
        zip3 = norm.split()[-1][:3] if norm.split() and norm.split()[-1].isdigit() else ""
        if zip3:
            zip_counts.setdefault(tin, {}).setdefault(zip3, set()).add(npi)
        address_npis.setdefault((tin, norm), set()).add(npi)
        geo = cache.get(norm, {})
        if geo.get("latitude") is not None and geo.get("longitude") is not None:
            trusted.setdefault(tin, []).append((npi, float(geo["latitude"]), float(geo["longitude"])))
    modal = {
        tin: max(counts, key=lambda z: (len(counts[z]), z))
        for tin, counts in zip_counts.items()
        if counts
    }

    enriched = []
    matched = 0
    anomalies = 0
    geo_measured = 0
    for row in candidates:
        norm = row.get("Normalized_Address", "")
        geo = cache.get(norm, {})
        lat, lon = geo.get("latitude"), geo.get("longitude")
        distances = []
        if lat is not None and lon is not None:
            for peer_npi, plat, plon in trusted.get(row.get("TIN", ""), []):
                if peer_npi != row.get("NPI", ""):
                    distances.append(_haversine_km(float(lat), float(lon), plat, plon))
        distance = min(distances) if distances else None
        geo_score, geo_flag = _geo_support(distance)
        tin = row.get("TIN", "")
        npi_count = len(address_npis.get((tin, norm), set()))
        zip3 = norm.split()[-1][:3] if norm.split() and norm.split()[-1].isdigit() else ""
        tin_score = (10 if len(tin_npis.get(tin, set())) >= 2 and zip3 and zip3 == modal.get(tin, "") else 0) + (15 if npi_count >= 2 else 0)
        tin_score = min(20, tin_score)
        row.update({
            "Geocode_Status": geo.get("status", "no_match"),
            "Latitude": lat if lat is not None else "",
            "Longitude": lon if lon is not None else "",
            "Nearest_TIN_Site_Distance_Km": round(distance, 3) if distance is not None else "",
            "Geo_Score": geo_score,
            "Geo_Anomaly_Flag": geo_flag,
            "TIN_Modal_ZIP3": modal.get(tin, ""),
            "TIN_Support_Score": tin_score,
            "TIN_Address_Link_Status": "SUPPORTED" if tin_score else "UNVERIFIED",
        })
        if geo.get("status") == "matched":
            matched += 1
        if distance is not None:
            geo_measured += 1
        if geo_flag == "distant_tin_site":
            anomalies += 1
        enriched.append(row)

    def write_rows(path: Path, rows: list[dict[str, str]]) -> None:
        tmp = path.with_suffix(path.suffix + ".geo.tmp")
        fields = list(rows[0]) if rows else []
        with tmp.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        tmp.replace(path)

    write_rows(candidates_path, enriched)
    by_key = {(r.get("NPI", ""), r.get("TIN", ""), _normalize_address(r.get("Address", ""), "", "", "", "")): r for r in enriched}
    for row in result:
        key = (row.get("NPI", ""), row.get("TIN", ""), _normalize_address(row.get("Address", ""), "", "", "", ""))
        source = by_key.get(key)
        if source:
            for field in ("Geocode_Status", "Latitude", "Longitude", "Nearest_TIN_Site_Distance_Km", "Geo_Score", "Geo_Anomaly_Flag", "TIN_Modal_ZIP3", "TIN_Support_Score", "TIN_Address_Link_Status"):
                row[field] = source.get(field, "")
    write_rows(result_path, result)
    return {
        "candidate_rows": len(enriched),
        "result_rows": len(result),
        "unique_addresses": len(addresses),
        "geocoded_matched": matched,
        "geocode_cache_entries": len(cache),
        "haversine_measured": geo_measured,
        "distant_tin_site_flags": anomalies,
        "supported_tin_links": sum(1 for r in enriched if r.get("TIN_Address_Link_Status") == "SUPPORTED"),
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("stage_dir", type=Path)
    args = parser.parse_args()
    print(json.dumps(enrich_c5_directory(args.stage_dir), indent=2))

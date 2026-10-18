"""C5: map C4 provider rates to practice addresses and NUCC specialties."""

from __future__ import annotations

import csv
import io
import json
import math
import os
import re
import time
import urllib.parse
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from difflib import SequenceMatcher

try:
    import openpyxl
except (OSError, KeyError, ValueError, TypeError, ImportError):
    openpyxl = None
try:
    import usaddress
except ImportError:
    usaddress = None
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pipeline.config import Config
from pipeline.io.manifest import write_manifest

C5_COLUMNS = [
    "NPI", "TIN", "Address", "Billing_Code", "Specialty", "Rate",
    "Address_Status", "Address_Confidence", "Address_Source", "Address_Source_Count",
    "Address_Score", "Address_Verification_Status",
    "Address_Record_Updated_At", "Address_Role", "Address_Evidence_Tier",
    "Geocode_Status", "Latitude", "Longitude", "Nearest_TIN_Site_Distance_Km", "Geo_Score", "Geo_Anomaly_Flag",
    "TIN_Modal_ZIP3", "TIN_Support_Score",
    "Match_Method", "TIN_Address_Link_Status", "Taxonomy_Code",
    "Specialty_Source", "Specialty_Status", "Negotiated_Type", "Billing_Class",
    "Setting", "Service_Code", "Modifiers", "Source_File", "Selection_Rule",
]

CANDIDATE_COLUMNS = [
    "NPI", "TIN", "TIN_Business_Name", "Address", "Normalized_Address",
    "Address_Status", "Address_Confidence", "Address_Source", "Address_Source_Count",
    "Address_Score", "Address_Verification_Status",
    "Address_Record_Updated_At", "Address_Role", "Address_Evidence_Tier",
    "Match_Method", "TIN_Address_Link_Status", "Taxonomy_Code", "CMS_Specialty",
    "Alternative_Addresses", "Geocode_Status", "Latitude", "Longitude",
    "Nearest_TIN_Site_Distance_Km", "Geo_Score", "Geo_Anomaly_Flag", "TIN_Modal_ZIP3", "TIN_Support_Score",
]

AUDIT_COLUMNS = [
    "C4_Row_Id", "NPI", "TIN", "Billing_Code", "Original_Address",
    "Normalized_Address", "Source", "Source_Record_Id", "Source_Updated_At",
    "Match_Method", "Address_Status", "Included_In_C5", "Reason",
    "TIN_Address_Link_Status", "Taxonomy_Code", "NUCC_Specialty",
    "CMS_Specialty", "Specialty_Source", "Specialty_Status", "NUCC_vs_HiLabs_Discrepancy",
    "Conflicting_Address", "Alternative_Addresses",
]


@dataclass(frozen=True)
class StageResult:
    stage: str
    counts: dict[str, int]
    outputs: tuple[Path, ...]


def _text(v: Any) -> str:
    if v is None:
        return ""
    return str(v).strip()


def _normalize_address(line1, line2, city, state, zipcode) -> str:
    parts = [line1, line2, city, state, zipcode]
    s = " ".join(_text(p) for p in parts if _text(p))
    s = s.upper()
    # remove punctuation except spaces and hyphens
    s = re.sub(r"[,.;:#]", " ", s)
    # normalize zip to 5 digits when possible
    zm = re.search(r"\b(\d{5})(?:-?\d{4})?\b", s)
    if zm:
        s = s.replace(zm.group(0), zm.group(1))
    # street suffix normalization
    s = re.sub(r"\bSTREET\b", "ST", s)
    s = re.sub(r"\bAVENUE\b", "AVE", s)
    s = re.sub(r"\bROAD\b", "RD", s)
    s = re.sub(r"\bBOULEVARD\b", "BLVD", s)
    s = re.sub(r"\bDRIVE\b", "DR", s)
    s = re.sub(r"\bSUITE\b", "STE", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _orig_address(line1, line2, city, state, zipcode) -> str:
    parts = []
    if _text(line1):
        parts.append(_text(line1))
    if _text(line2):
        parts.append(_text(line2))
    city_state_zip = ", ".join(x for x in [_text(city), _text(state)] if x)
    if _text(zipcode):
        city_state_zip = (city_state_zip + " " + _text(zipcode)).strip()
    if city_state_zip:
        parts.append(city_state_zip)
    return ", ".join(parts)


def _compact(s: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


def _fuzzy_addr_equal(a: str, b: str) -> bool:
    if not a or not b:
        return False
    if a == b:
        return True
    ca, cb = _compact(a), _compact(b)
    if ca == cb:
        return True
    if not ca or not cb:
        return False
    ratio = SequenceMatcher(None, ca, cb).ratio()
    return ratio >= 0.97


def _is_street_address(addr: str) -> bool:
    if not addr or _address_role(addr) == "mailing/po_box":
        return False
    if usaddress is None:
        return bool(re.search(r"\b\d+\b", addr))
    try:
        parsed, _ = usaddress.tag(addr)
    except (usaddress.RepeatedLabelError, ValueError):
        return bool(re.search(r"\b\d+\b", addr))
    return bool(parsed.get("AddressNumber") and parsed.get("StreetName"))


def _census_query_params(addr: str) -> dict[str, str]:
    if usaddress is not None:
        try:
            parsed, _ = usaddress.tag(addr)
            street_labels = (
                "AddressNumber", "StreetNamePreDirectional", "StreetName",
                "StreetNamePostType", "StreetNamePostDirectional", "OccupancyType",
                "OccupancyIdentifier",
            )
            street = " ".join(parsed.get(label, "") for label in street_labels if parsed.get(label, "")).strip()
            if street and parsed.get("PlaceName") and parsed.get("StateName"):
                return {
                    "street": street,
                    "city": parsed["PlaceName"],
                    "state": parsed["StateName"],
                    "zip": parsed.get("ZipCode", ""),
                    "benchmark": "Public_AR_Current",
                    "format": "json",
                }
        except (usaddress.RepeatedLabelError, ValueError):
            pass
    parts = [part.strip() for part in addr.split(",")]
    last = parts[-1].split() if parts else []
    return {
        "street": parts[0] if parts else "",
        "city": parts[-2] if len(parts) >= 2 else "",
        "state": last[0] if last else "",
        "zip": last[1] if len(last) > 1 else "",
        "benchmark": "Public_AR_Current",
        "format": "json",
    }


def _geocode_address(addr: str, cache: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Census geocode one physical address; cache avoids repeated HTTP calls."""
    key = _normalize_address(addr, "", "", "", "")
    if os.environ.get("PTD_GEOCODE") != "1":
        return {"status": "disabled", "latitude": None, "longitude": None}
    if not _is_street_address(addr):
        return {"status": "not_physical", "latitude": None, "longitude": None}
    if key in cache:
        return cache[key]
    try:
        params = urllib.parse.urlencode(_census_query_params(addr))
        url = "https://geocoding.geo.census.gov/geocoder/locations/address?" + params
        timeout = float(os.environ.get("PTD_GEOCODE_TIMEOUT", "5"))
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        matches = data.get("result", {}).get("addressMatches", [])
        if not matches:
            result = {"status": "no_match", "latitude": None, "longitude": None}
        else:
            point = matches[0].get("coordinates", {})
            result = {
                "status": "matched",
                "latitude": float(point["y"]),
                "longitude": float(point["x"]),
            }
        cache[key] = result
        return result
    except (OSError, ValueError, KeyError, TimeoutError):
        return {"status": "error", "latitude": None, "longitude": None}


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    earth_radius_km = 6371.0088
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (math.sin(d_lat / 2) ** 2 + math.cos(math.radians(lat1))
         * math.cos(math.radians(lat2)) * math.sin(d_lon / 2) ** 2)
    return 2 * earth_radius_km * math.asin(math.sqrt(a))


def _geo_support(distance_km: float | None) -> tuple[int, str]:
    if distance_km is None:
        return 0, "not_measured"
    if distance_km <= 10:
        return 10, "near_tin_site"
    if distance_km <= 50:
        return 5, "regional_tin_site"
    if distance_km <= 160:
        return 0, "separate_possible_site"
    return -10, "distant_tin_site"


def _valid_npi(npi: str) -> bool:
    return len(npi) == 10 and npi.isdigit()


def c4_candidate_keys(c4_rows: list[dict[str, str]]) -> dict[tuple[str, str], str]:
    """Return one C5 address-candidate key per C4 NPI/TIN relationship."""
    keys: dict[tuple[str, str], str] = {}
    for row in c4_rows:
        npi = _text(row.get("npi") or row.get("NPI"))
        tin = _text(row.get("tin") or row.get("TIN"))
        if npi and tin:
            keys.setdefault((npi, tin), _text(row.get("business_name") or row.get("TIN_Business_Name")))
    return keys


def _resolve_address_candidates(
    npi: str,
    nppes_addrs: list[dict[str, Any]],
    cms_addrs: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], str]:
    """Resolve source records to candidate addresses for one NPI/TIN key."""
    addr_groups: dict[str, dict[str, Any]] = {}
    for rec in nppes_addrs + cms_addrs:
        norm = rec["norm"]
        if not norm:
            continue
        matched_key = next((existing for existing in addr_groups if _fuzzy_addr_equal(norm, existing)), None)
        if matched_key is None:
            addr_groups[norm] = {
                "orig": rec["orig"], "sources": set(), "families": set(),
                "taxonomy": rec.get("taxonomy", ""),
                "cms_specialty": rec.get("cms_specialty", ""), "updated": rec.get("updated", ""),
            }
            matched_key = norm
        elif not addr_groups[matched_key]["orig"]:
            addr_groups[matched_key]["orig"] = rec["orig"]
        addr_groups[matched_key]["sources"].add(rec["source"])
        addr_groups[matched_key]["families"].add("NPPES" if rec["source"].startswith("NPPES") else rec["source"])
        if rec.get("taxonomy") and not addr_groups[matched_key]["taxonomy"]:
            addr_groups[matched_key]["taxonomy"] = rec["taxonomy"]
        if rec.get("cms_specialty") and not addr_groups[matched_key]["cms_specialty"]:
            addr_groups[matched_key]["cms_specialty"] = rec["cms_specialty"]

    if not _valid_npi(npi):
        return addr_groups, "INVALID_NPI"
    if not addr_groups:
        return addr_groups, "UNRESOLVED"
    if len(addr_groups) == 1 and len(next(iter(addr_groups.values()))["sources"]) >= 2:
        return addr_groups, "CORROBORATED"
    if len(addr_groups) == 1:
        return addr_groups, "SINGLE_SOURCE"
    return addr_groups, "CONFLICTING"


def _address_role(addr: str) -> str:
    u = (addr or "").upper()
    if "PO BOX" in u or "P.O. BOX" in u or "P O BOX" in u:
        return "mailing/po_box"
    return "practice"


def score_address_candidate(candidate: dict[str, Any], geo_score: int = 0) -> tuple[int, str]:
    """Score physical-practice evidence; not proof that a TIN owns address."""
    sources = candidate.get("sources", set())
    families = candidate.get("families", set())
    score = 0
    if "CMS_NPD_LOCATION" in sources:
        score += 60
    if "CMS_DAC" in sources:
        score += 50
    if "PTD_ADDRESS" in sources:
        score += 40
    if "NPPES_PL" in sources:
        score += 30
    if "NPPES" in sources:
        score += 10
    if len(families) >= 2:
        score += 20
    if _address_role(_text(candidate.get("orig"))) == "mailing/po_box":
        score -= 60
    base_score = max(0, min(score, 100))
    score = max(0, min(base_score + geo_score, 100))
    verification = "VERIFIED" if base_score >= 60 else "PROBABLE" if base_score >= 30 else "LOW"
    return score, verification


def _zip3(address: str) -> str:
    match = re.search(r"\b(\d{5})\b", address or "")
    return match.group(1)[:3] if match else ""


def _build_tin_profiles(
    pair_candidates: dict[tuple[str, str], tuple[dict[str, dict[str, Any]], str]],
) -> dict[str, dict[str, Any]]:
    """Build weak TIN geography from independently strong NPI address evidence."""
    profiles: dict[str, dict[str, Any]] = {}
    for (npi, tin), (groups, _) in pair_candidates.items():
        profile = profiles.setdefault(tin, {"zip3_npis": {}, "address_npis": {}})
        for norm, group in groups.items():
            base_score, _ = score_address_candidate(group)
            if base_score < 60:
                continue
            zip3 = _zip3(norm or group.get("orig", ""))
            if zip3:
                profile["zip3_npis"].setdefault(zip3, set()).add(npi)
            if norm:
                profile["address_npis"].setdefault(norm, set()).add(npi)
    for profile in profiles.values():
        profile["modal_zip3"] = max(
            profile["zip3_npis"],
            key=lambda value: (len(profile["zip3_npis"][value]), value),
            default="",
        )
    return profiles


def _tin_geographic_support(profile: dict[str, Any], npi: str, norm: str) -> tuple[int, str, str, int]:
    zip3 = _zip3(norm)
    zip_score = 10 if zip3 and zip3 == profile.get("modal_zip3") else 0
    address_count = len(profile.get("address_npis", {}).get(norm, set()))
    reuse_score = 15 if address_count >= 2 else 0
    support = min(20, zip_score + reuse_score)
    return support, "SUPPORTED" if support else "UNVERIFIED", profile.get("modal_zip3", ""), address_count


def _apply_geospatial_support(
    pair_candidates: dict[tuple[str, str], tuple[dict[str, dict[str, Any]], str]],
    cache_path: Path,
) -> dict[str, int | bool]:
    """Add weak same-TIN geographic support after base evidence is established."""
    enabled = os.environ.get("PTD_GEOCODE") == "1"
    try:
        cache = json.loads(cache_path.read_text()) if cache_path.is_file() else {}
    except (OSError, ValueError):
        cache = {}
    cache_before = len(cache)
    profiles = _build_tin_profiles(pair_candidates)
    trusted_by_tin: dict[str, list[tuple[str, float, float]]] = {}
    candidates = []
    address_lookup: dict[str, str] = {}
    for groups, _ in pair_candidates.values():
        for norm, group in groups.items():
            if norm:
                address_lookup.setdefault(norm, _text(group.get("orig")))
    geocodes: dict[str, dict[str, Any]] = {}
    if enabled:
        try:
            workers = max(1, min(16, int(os.environ.get("PTD_GEOCODE_WORKERS", "8"))))
        except ValueError:
            workers = 8
        pending = {
            norm: address for norm, address in address_lookup.items()
            if _normalize_address(address, "", "", "", "") not in cache
        }
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_geocode_address, address, cache): norm for norm, address in pending.items()}
            for future, norm in ((future, norm) for future, norm in futures.items()):
                try:
                    geocodes[norm] = future.result()
                except (OSError, ValueError, KeyError, TimeoutError):
                    geocodes[norm] = {"status": "error", "latitude": None, "longitude": None}

    for (npi, tin), (groups, _) in pair_candidates.items():
        for norm, group in groups.items():
            geo = geocodes.get(norm)
            if geo is None:
                geo = _geocode_address(_text(group.get("orig")), cache)
            group["geo"] = geo
            group["geo_score"] = 0
            group["geo_flag"] = "not_measured"
            tin_support, tin_status, modal_zip3, address_count = _tin_geographic_support(
                profiles.get(tin, {}), npi, norm
            )
            group["tin_support_score"] = tin_support
            group["tin_link_status"] = tin_status
            group["tin_modal_zip3"] = modal_zip3
            group["tin_address_npi_count"] = address_count
            candidates.append((npi, tin, norm, group))
            base_score, _ = score_address_candidate(group)
            if base_score >= 60 and geo["latitude"] is not None:
                trusted_by_tin.setdefault(tin, []).append((npi, geo["latitude"], geo["longitude"]))

    for npi, tin, _, group in candidates:
        geo = group["geo"]
        group["support_score"] = int(group.get("tin_support_score", 0))
        if geo["latitude"] is None:
            continue
        distances = [
            _haversine_km(geo["latitude"], geo["longitude"], lat, lon)
            for peer_npi, lat, lon in trusted_by_tin.get(tin, [])
            if peer_npi != npi
        ]
        distance = min(distances) if distances else None
        geo_score, geo_flag = _geo_support(distance)
        group["nearest_tin_site_distance_km"] = distance
        group["geo_score"] = geo_score
        group["geo_flag"] = geo_flag
        group["support_score"] += geo_score

    if enabled:
        cache_path.write_text(json.dumps(cache, sort_keys=True) + "\n")
    matches = sum(1 for _, _, _, group in candidates if group["geo"]["status"] == "matched")
    return {
        "enabled": enabled,
        "candidates": len(candidates),
        "matched": matches,
        "profiles": len(profiles),
        "supported_candidates": sum(1 for *_, group in candidates if group.get("tin_link_status") == "SUPPORTED"),
        "cache_entries_before": cache_before,
        "cached_addresses": len(cache),
    }


def _is_complete_address(addr: str) -> bool:
    # basic completeness: has digits, city/state/zip
    if not addr:
        return False
    if not any(ch.isdigit() for ch in addr):
        return False
    return "," in addr


def _load_nucc(outer_zip_path: Path) -> dict[str, dict[str, str]]:
    mapping = {}
    with zipfile.ZipFile(outer_zip_path) as z:
        member = "hilabs_dataset_2026-10-17/nucc/nucc_taxonomy_261.csv"
        with z.open(member) as f:
            reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig", newline=""))
            for row in reader:
                code = _text(row.get("Code"))
                if code:
                    mapping[code] = {
                        "grouping": _text(row.get("Grouping")),
                        "classification": _text(row.get("Classification")),
                        "specialization": _text(row.get("Specialization")),
                        "display": _text(row.get("Display Name")),
                    }
    return mapping


def _load_specproc(outer_zip_path: Path) -> dict[str, str]:
    """Map billing code -> best specialty description using Spec-Proc Weights."""
    result: dict[str, str] = {}
    best: dict[str, tuple[int, float]] = {}
    try:
        import io as _io
        with zipfile.ZipFile(outer_zip_path) as z:
            member = "hilabs_dataset_2026-10-17/hilabs/Rate Benchmarking Individual Weights_Hackathon.xlsx"
            data = z.read(member)
        if openpyxl is None:
            return result
        wb = openpyxl.load_workbook(_io.BytesIO(data), read_only=True)
        ws = wb["Spec-Proc Weights"]
        rows = list(ws.iter_rows(values_only=True))
        header = rows[0]
        idx = {name: i for i, name in enumerate(header)}
        for r in rows[1:]:
            spec_desc = _text(r[idx["SPEC_DESCRIPTION"]])
            proc = _text(r[idx["PROC_CD"]])
            rank = r[idx["SPEC_PROC_RANK"]]
            weight = r[idx["SPEC_PROC_WEIGHT"]]
            try:
                rank_i = int(rank)
            except (TypeError, ValueError):
                rank_i = 9999
            try:
                weight_f = float(weight)
            except (TypeError, ValueError):
                weight_f = 0.0
            if not proc or not spec_desc:
                continue
            if proc not in best or (rank_i, -weight_f) < (best[proc][0], -best[proc][1]):
                best[proc] = (rank_i, weight_f)
                result[proc] = spec_desc
    except (OSError, KeyError, ValueError, TypeError, ImportError):
        return result
    return result


def _primary_taxonomy(row: dict[str, str]) -> str:
    for i in range(1, 16):
        code = _text(row.get(f"Healthcare Provider Taxonomy Code_{i}"))
        switch = _text(row.get(f"Healthcare Provider Primary Taxonomy Switch_{i}"))
        if code and switch.upper() == "Y":
            return code
    # fallback first non-empty
    for i in range(1, 16):
        code = _text(row.get(f"Healthcare Provider Taxonomy Code_{i}"))
        if code:
            return code
    return ""


def _build_nppes(outer_zip_path: Path, npi_set: set[str]) -> tuple[dict[str, list[dict[str, Any]]], dict[str, str]]:
    """Return dict npi -> list of address dicts {source, orig, norm, taxonomy, updated}."""
    result: dict[str, list[dict[str, Any]]] = {n: [] for n in npi_set}
    primary_tax: dict[str, str] = {n: "" for n in npi_set}
    with zipfile.ZipFile(outer_zip_path) as z:
        inner = "hilabs_dataset_2026-10-17/nppes/NPPES_Data_Dissemination_October_2026_V2.zip"
        nz = zipfile.ZipFile(io.BytesIO(z.read(inner)))
        # npidata
        member = next(m for m in nz.namelist() if m.endswith("npidata_pfile_20050523-20261011.csv"))
        with nz.open(member) as f:
            reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8", newline=""))
            _n = 0
            for row in reader:
                _n += 1
                if _n % 1000000 == 0:
                    print(f"C5: scanned {_n} NPPES rows...")
                npi = _text(row.get("NPI"))
                if npi not in npi_set:
                    continue
                addr = _orig_address(
                    row.get("Provider First Line Business Practice Location Address"),
                    row.get("Provider Second Line Business Practice Location Address"),
                    row.get("Provider Business Practice Location Address City Name"),
                    row.get("Provider Business Practice Location Address State Name"),
                    row.get("Provider Business Practice Location Address Postal Code"),
                )
                norm = _normalize_address(
                    row.get("Provider First Line Business Practice Location Address"),
                    row.get("Provider Second Line Business Practice Location Address"),
                    row.get("Provider Business Practice Location Address City Name"),
                    row.get("Provider Business Practice Location Address State Name"),
                    row.get("Provider Business Practice Location Address Postal Code"),
                )
                tax = _primary_taxonomy(row)
                if tax and not primary_tax.get(npi):
                    primary_tax[npi] = tax
                rec = {"source": "NPPES", "orig": addr, "norm": norm, "taxonomy": tax or primary_tax.get(npi, ""),
                       "updated": "NPPES_Oct2026", "cms_specialty": ""}
                # dedup by norm
                if not any(r["norm"] == norm and r["source"] == "NPPES" for r in result[npi]):
                    result[npi].append(rec)
        # pl_pfile secondary
        member2 = next(m for m in nz.namelist() if m.endswith("pl_pfile_20050523-20261011.csv"))
        with nz.open(member2) as f:
            reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8", newline=""))
            _n = 0
            for row in reader:
                _n += 1
                if _n % 1000000 == 0:
                    print(f"C5: scanned {_n} NPPES rows...")
                npi = _text(row.get("NPI"))
                if npi not in npi_set:
                    continue
                addr = _orig_address(
                    row.get("Provider Secondary Practice Location Address- Address Line 1"),
                    row.get("Provider Secondary Practice Location Address-  Address Line 2"),
                    row.get("Provider Secondary Practice Location Address - City Name"),
                    row.get("Provider Secondary Practice Location Address - State Name"),
                    row.get("Provider Secondary Practice Location Address - Postal Code"),
                )
                norm = _normalize_address(
                    row.get("Provider Secondary Practice Location Address- Address Line 1"),
                    row.get("Provider Secondary Practice Location Address-  Address Line 2"),
                    row.get("Provider Secondary Practice Location Address - City Name"),
                    row.get("Provider Secondary Practice Location Address - State Name"),
                    row.get("Provider Secondary Practice Location Address - Postal Code"),
                )
                rec = {"source": "NPPES_PL", "orig": addr, "norm": norm, "taxonomy": primary_tax.get(npi, ""),
                       "updated": "NPPES_Oct2026", "cms_specialty": ""}
                if norm and not any(r["norm"] == norm for r in result[npi]):
                    result[npi].append(rec)
    return result, primary_tax


def _build_cms(outer_zip_path: Path, npi_set: set[str], primary_tax: dict[str, str] | None = None) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {n: [] for n in npi_set}
    primary_tax: dict[str, str] = {n: "" for n in npi_set}
    with zipfile.ZipFile(outer_zip_path) as z:
        member = "hilabs_dataset_2026-10-17/cms_dac/DAC_NationalDownloadableFile.csv"
        with z.open(member) as f:
            reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8", newline=""))
            _n = 0
            for row in reader:
                _n += 1
                if _n % 1000000 == 0:
                    print(f"C5: scanned {_n} NPPES rows...")
                npi = _text(row.get("NPI"))
                if npi not in npi_set:
                    continue
                addr = _orig_address(row.get("adr_ln_1"), row.get("adr_ln_2"),
                                     row.get("City/Town"), row.get("State"), row.get("ZIP Code"))
                norm = _normalize_address(row.get("adr_ln_1"), row.get("adr_ln_2"),
                                         row.get("City/Town"), row.get("State"), row.get("ZIP Code"))
                spec = _text(row.get("pri_spec"))
                rec = {"source": "CMS_DAC", "orig": addr, "norm": norm, "taxonomy": (primary_tax or {}).get(npi, ""),
                       "updated": "CMS_DAC", "cms_specialty": spec}
                if norm and not any(r["norm"] == norm and r["source"] == "CMS_DAC" for r in result[npi]):
                    result[npi].append(rec)
    return result


def _npd_location_records(bundle: dict[str, Any]) -> list[dict[str, str]]:
    """Extract California active-location records from a CMS NPD FHIR bundle."""
    records = []
    for entry in bundle.get("entry", []):
        resource = entry.get("resource", {})
        if resource.get("resourceType") != "Location" or resource.get("status") == "inactive":
            continue
        address = resource.get("address", {})
        if _text(address.get("state")).upper() != "CA":
            continue
        lines = address.get("line", [])
        if not isinstance(lines, list):
            lines = [lines]
        line1, line2 = (lines + ["", ""])[:2]
        orig = _orig_address(line1, line2, address.get("city"), address.get("state"), address.get("postalCode"))
        norm = _normalize_address(line1, line2, address.get("city"), address.get("state"), address.get("postalCode"))
        if norm:
            records.append({
                "source": "CMS_NPD_LOCATION", "orig": orig, "norm": norm,
                "taxonomy": "", "updated": _text(resource.get("meta", {}).get("lastUpdated")),
                "cms_specialty": "",
            })
    return records


def _npd_get(path: str, params: dict[str, str]) -> dict[str, Any]:
    base = os.environ.get("PTD_NPD_BASE_URL", "https://directory.cms.gov/fhir").rstrip("/")
    url = f"{base}/{path.lstrip('/')}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"Accept": "application/fhir+json"})
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def _npd_npis_to_fetch(npi_set: set[str], cache_dir: Path, max_npis: int) -> list[str]:
    npis = [npi for npi in sorted(npi_set) if not (cache_dir / f"{npi}.json").is_file()]
    return npis if max_npis == 0 else npis[:max_npis]


def _fetch_npd_payload(npi: str) -> dict[str, Any]:
    practitioner = _npd_get("Practitioner", {
        "identifier": f"http://hl7.org/fhir/sid/us-npi|{npi}", "_count": "1",
    })
    entries = practitioner.get("entry", [])
    practitioner_id = _text(entries[0].get("resource", {}).get("id")) if entries else ""
    roles = _npd_get("PractitionerRole", {
        "practitioner": f"Practitioner/{practitioner_id}", "active": "true",
        "_include": "PractitionerRole:location", "_count": "100",
    }) if practitioner_id else {}
    return {"practitioner": practitioner, "roles": roles}


def _build_cms_npd(npi_set: set[str], cache_dir: Path, max_npis: int, workers: int = 4) -> tuple[dict[str, list[dict[str, str]]], dict[str, int]]:
    """Fetch current CMS NPD locations once per NPI, with resumable raw-response cache."""
    result: dict[str, list[dict[str, str]]] = {npi: [] for npi in npi_set}
    cache_dir.mkdir(parents=True, exist_ok=True)
    stats = {"requested": 0, "cache_hits": 0, "api_success": 0, "api_errors": 0, "location_records": 0}
    uncached_npis = _npd_npis_to_fetch(npi_set, cache_dir, max_npis)
    cached_npis = sorted(npi for npi in npi_set if (cache_dir / f"{npi}.json").is_file())
    stats["cache_hits"] = len(cached_npis)
    stats["requested"] = len(uncached_npis)

    def fetch_one(npi: str) -> tuple[str, dict[str, Any] | None]:
        try:
            payload = _fetch_npd_payload(npi)
            (cache_dir / f"{npi}.json").write_text(json.dumps(payload), encoding="utf-8")
            time.sleep(0.1)
            return npi, payload
        except (OSError, ValueError, TimeoutError):
            return npi, None

    fetched: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = [executor.submit(fetch_one, npi) for npi in uncached_npis]
        for future in as_completed(futures):
            npi, payload = future.result()
            if payload is None:
                stats["api_errors"] += 1
            else:
                fetched[npi] = payload
                stats["api_success"] += 1

    for npi in cached_npis + uncached_npis:
        cache_path = cache_dir / f"{npi}.json"
        payload = fetched.get(npi, {})
        if not payload and cache_path.is_file():
            try:
                payload = json.loads(cache_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                payload = {}
        records = _npd_location_records(payload.get("roles", {}))
        result[npi] = records
        stats["location_records"] += len(records)
    return result, stats


def _nucc_specialty(code: str, nucc: dict[str, dict[str, str]]) -> str:
    if not code:
        return ""
    info = nucc.get(code)
    if not info:
        return ""
    # prefer classification + specialization
    parts = [info.get("classification", ""), info.get("specialization", "")]
    return " - ".join(p for p in parts if p).strip(" -")


def run_c5(cfg: Config, c4_path: Path | None = None, output_dir: Path | None = None, **kwargs: Any) -> StageResult:
    started_at = time.monotonic()
    # resolve c4 input
    if c4_path is None:
        c4_path = cfg.stage_dir("c4") / "selected_rates.csv"
        if not c4_path.is_file():
            c4_path = cfg.stage_dir("c4") / "c4result.csv"
    if output_dir is None:
        out_dir = cfg.stage_dir("c5")
    else:
        out_dir = Path(output_dir)
        if not out_dir.is_absolute():
            out_dir = cfg.root / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    # read c4 rows
    with c4_path.open(newline="", encoding="utf-8") as f:
        c4_rows = list(csv.DictReader(f))

    candidate_keys = c4_candidate_keys(c4_rows)
    npi_set = {npi for npi, _ in candidate_keys if _valid_npi(npi)}

    outer_zip = cfg.archive if str(cfg.archive).endswith(".zip") else None
    if outer_zip is None:
        outer_zip = Path(cfg.data_dir) / "hilabs_dataset_2026-10-17.zip"
    nucc = _load_nucc(outer_zip)
    specproc = _load_specproc(outer_zip)
    # outer zip path
    nppes_map, primary_tax = _build_nppes(outer_zip, npi_set)
    cms_map = _build_cms(outer_zip, npi_set, primary_tax)
    npd_map: dict[str, list[dict[str, str]]] = {npi: [] for npi in npi_set}
    npd_stats: dict[str, Any] = {"enabled": False}
    if os.environ.get("PTD_NPD_API") == "1":
        try:
            max_npis = int(os.environ.get("PTD_NPD_MAX_NPIS", "100"))
        except ValueError:
            max_npis = 100
        try:
            npd_workers = int(os.environ.get("PTD_NPD_WORKERS", "4"))
        except ValueError:
            npd_workers = 4
        npd_map, npd_stats = _build_cms_npd(npi_set, out_dir / "cms_npd_cache", max_npis, npd_workers)
        npd_stats["enabled"] = True

    # outputs
    c5_path = out_dir / "c5result.csv"
    candidate_path = out_dir / "c5_address_candidates.csv"
    audit_path = out_dir / "c5_address_audit.csv"
    summary_path = out_dir / "c5_summary.json"
    manifest_path = out_dir / "_manifest.json"

    cf = c5_path.open("w", newline="", encoding="utf-8")
    pf = candidate_path.open("w", newline="", encoding="utf-8")
    af = audit_path.open("w", newline="", encoding="utf-8")
    cwriter = csv.DictWriter(cf, fieldnames=C5_COLUMNS, extrasaction="ignore")
    pwriter = csv.DictWriter(pf, fieldnames=CANDIDATE_COLUMNS, extrasaction="ignore")
    awriter = csv.DictWriter(af, fieldnames=AUDIT_COLUMNS, extrasaction="ignore")
    cwriter.writeheader()
    pwriter.writeheader()
    awriter.writeheader()

    row_count = 0
    distinct_npi = set()
    distinct_tin = set()
    addr_matched = 0
    corroborated = 0
    single = 0
    conflicting = 0
    unresolved = 0
    invalid_npi_count = 0
    unverified_tin = 0
    four_key_set = set()
    four_key_dup = 0
    specialty_mapped = 0
    specialty_unmapped = 0
    audit_rows = 0

    # C5 resolves addresses once at NPI/TIN grain. Billing codes belong to C4
    # rate rows and are attached only after this candidate bridge is built.
    pair_candidates: dict[tuple[str, str], tuple[dict[str, dict[str, Any]], str]] = {}
    for (npi, tin), business_name in candidate_keys.items():
        nppes_addrs = nppes_map.get(npi, []) if _valid_npi(npi) else []
        cms_addrs = (cms_map.get(npi, []) + npd_map.get(npi, [])) if _valid_npi(npi) else []
        addr_groups, status = _resolve_address_candidates(npi, nppes_addrs, cms_addrs)
        pair_candidates[(npi, tin)] = (addr_groups, status)
        if status == "CORROBORATED":
            corroborated += 1
        elif status == "SINGLE_SOURCE":
            single += 1
        elif status == "CONFLICTING":
            conflicting += 1
        elif status == "UNRESOLVED":
            unresolved += 1

    geocode_stats = _apply_geospatial_support(pair_candidates, out_dir / "census_geocode_cache.json")
    supported_tin = sum(
        any(group.get("tin_link_status") == "SUPPORTED" for group in groups.values())
        for groups, _ in pair_candidates.values()
    )
    unverified_tin = len(candidate_keys) - supported_tin

    for (npi, tin), business_name in candidate_keys.items():
        addr_groups, status = pair_candidates[(npi, tin)]
        candidate_norms = list(addr_groups)
        for norm in candidate_norms or [""]:
            group = addr_groups.get(norm, {})
            sources = group.get("sources", set())
            families = group.get("families", set())
            orig_addr = group.get("orig", "")
            geo = group.get("geo", {"status": "not_attempted", "latitude": None, "longitude": None})
            score, verification = score_address_candidate(group, int(group.get("support_score", 0)))
            tier = "Tier 4" if not norm else "Tier 2" if len(families) >= 2 else "Tier 3" if _is_complete_address(orig_addr) else "Tier 4"
            pwriter.writerow({
                "NPI": npi, "TIN": tin, "TIN_Business_Name": business_name,
                "Address": orig_addr, "Normalized_Address": norm, "Address_Status": status,
                "Address_Confidence": "HIGH" if tier == "Tier 2" else "MEDIUM" if tier == "Tier 3" else "NONE" if not norm else "LOW",
                "Address_Source": ";".join(sorted(sources)) if sources else "NONE",
                "Address_Source_Count": len(sources), "Address_Score": score,
                "Address_Verification_Status": verification, "Address_Record_Updated_At": group.get("updated", ""),
                "Address_Role": _address_role(orig_addr) if norm else "unknown", "Address_Evidence_Tier": tier,
                "Match_Method": "exact_npi_tin" if _valid_npi(npi) else "invalid_npi",
                "TIN_Address_Link_Status": group.get("tin_link_status", "UNVERIFIED"), "Taxonomy_Code": group.get("taxonomy", ""),
                "CMS_Specialty": group.get("cms_specialty", ""),
                "Alternative_Addresses": "; ".join(other for other in candidate_norms if other != norm),
                "Geocode_Status": geo["status"], "Latitude": geo["latitude"], "Longitude": geo["longitude"],
                "Nearest_TIN_Site_Distance_Km": group.get("nearest_tin_site_distance_km"),
                "Geo_Score": group.get("geo_score", 0), "Geo_Anomaly_Flag": group.get("geo_flag", "not_measured"),
                "TIN_Modal_ZIP3": group.get("tin_modal_zip3", ""),
                "TIN_Support_Score": group.get("tin_support_score", 0),
            })

    for idx, c4r in enumerate(c4_rows):
        npi = _text(c4r.get("npi") or c4r.get("NPI"))
        tin = _text(c4r.get("tin") or c4r.get("TIN"))
        billing_code = _text(c4r.get("billing_code") or c4r.get("Billing_Code") or c4r.get("billing_code"))
        rate = _text(c4r.get("negotiated_rate") or c4r.get("Rate") or c4r.get("rate"))
        negotiated_type = _text(c4r.get("negotiated_type") or c4r.get("Negotiated_Type"))
        billing_class = _text(c4r.get("billing_class") or c4r.get("Billing_Class"))
        setting = _text(c4r.get("setting") or c4r.get("Setting"))
        service_code = _text(c4r.get("service_code") or c4r.get("Service_Code"))
        modifiers = _text(c4r.get("modifiers") or c4r.get("Modifiers"))
        source_file = _text(c4r.get("source_file") or c4r.get("Source_File"))
        selection_rule = _text(c4r.get("selection_rule") or c4r.get("Selection_Rule"))

        distinct_tin.add(tin)
        if _valid_npi(npi):
            distinct_npi.add(npi)
        else:
            invalid_npi_count += 1

        addr_groups, status = pair_candidates.get((npi, tin), ({}, "INVALID_NPI"))
        distinct_norms = list(addr_groups)

        has_conflict = len(distinct_norms) > 1

        # If unresolved/invalid: emit one row with blank address
        if status in ("UNRESOLVED", "INVALID_NPI"):
            addr_list = [""]
        else:
            addr_list = distinct_norms

        for norm in addr_list:
            if norm == "":
                orig_addr = ""
                sources = set()
                tax_code = ""
                cms_spec = ""
                updated = ""
                tier = "Tier 4"
                confidence = "NONE"
                role = "unknown"
                source_count = 0
                score = 0
                verification = "NONE"
                geo = {"status": "not_attempted", "latitude": None, "longitude": None}
                geo_score = 0
                geo_flag = "not_measured"
                nearest_tin_site_distance_km = None
                tin_support_score = 0
                tin_modal_zip3 = ""
                tin_link = "UNVERIFIED"
            else:
                g = addr_groups[norm]
                orig_addr = g["orig"]
                sources = g["sources"]
                tax_code = g["taxonomy"]
                cms_spec = g["cms_specialty"]
                updated = g["updated"]
                fams = g.get("families", set())
                if len(fams) >= 2:
                    tier = "Tier 2"
                elif _is_complete_address(orig_addr):
                    tier = "Tier 3"
                else:
                    tier = "Tier 4"
                confidence = "HIGH" if tier == "Tier 2" else "MEDIUM" if tier == "Tier 3" else "LOW"
                role = _address_role(orig_addr)
                source_count = len(sources)
                geo = g.get("geo", {"status": "not_attempted", "latitude": None, "longitude": None})
                geo_score = int(g.get("geo_score", 0))
                geo_flag = g.get("geo_flag", "not_measured")
                nearest_tin_site_distance_km = g.get("nearest_tin_site_distance_km")
                tin_support_score = int(g.get("tin_support_score", 0))
                tin_modal_zip3 = g.get("tin_modal_zip3", "")
                tin_link = g.get("tin_link_status", "UNVERIFIED")
                score, verification = score_address_candidate(g, int(g.get("support_score", geo_score)))

            # specialty
            nucc_spec = _nucc_specialty(tax_code, nucc)
            specproc_spec = specproc.get(billing_code, "")
            nucc_hilabs_discrepancy = "yes" if (nucc_spec and specproc_spec and nucc_spec != specproc_spec) else "no"
            if nucc_spec:
                specialty = nucc_spec
                spec_source = "NPPES_NUCC"
                spec_status = "MAPPED"
                specialty_mapped += 1
            elif tax_code:
                if cms_spec:
                    specialty = cms_spec
                    spec_source = "CMS"
                    spec_status = "CMS_ONLY"
                elif specproc.get(billing_code):
                    specialty = specproc[billing_code]
                    spec_source = "HILABS_SPEC_PROC"
                    spec_status = "MAPPED"
                    specialty_mapped += 1
                else:
                    specialty = ""
                    spec_source = "NONE"
                    spec_status = "UNMAPPED"
                if not (cms_spec or specproc.get(billing_code)):
                    specialty_unmapped += 1
            else:
                if cms_spec:
                    specialty = cms_spec
                    spec_source = "CMS"
                    spec_status = "CMS_ONLY"
                    specialty_mapped += 1
                elif specproc.get(billing_code):
                    specialty = specproc[billing_code]
                    spec_source = "HILABS_SPEC_PROC"
                    spec_status = "MAPPED"
                    specialty_mapped += 1
                else:
                    specialty = ""
                    spec_source = "NONE"
                    spec_status = "MISSING"
                    specialty_unmapped += 1

            if tax_code and not nucc.get(tax_code):
                # unmapped count
                pass

            addr_status = status
            # if multiple distinct addresses, per-address could be conflicting; keep status
            source_str = ";".join(sorted(sources)) if sources else ""
            if status == "CONFLICTING":
                addr_status = "CONFLICTING"

            out_row = {
                "NPI": npi,
                "TIN": tin,
                "Address": orig_addr,
                "Billing_Code": billing_code,
                "Specialty": specialty,
                "Rate": rate,
                "Address_Status": addr_status,
                "Address_Confidence": confidence,
                "Address_Source": source_str if source_str else ("NONE" if status in ("UNRESOLVED", "INVALID_NPI") else ""),
                "Address_Source_Count": source_count,
                "Address_Score": score,
                "Address_Verification_Status": verification,
                "Address_Record_Updated_At": updated,
                "Address_Role": role,
                "Address_Evidence_Tier": tier,
                "Geocode_Status": geo["status"],
                "Latitude": geo["latitude"],
                "Longitude": geo["longitude"],
                "Nearest_TIN_Site_Distance_Km": nearest_tin_site_distance_km,
                "Geo_Score": geo_score,
                "Geo_Anomaly_Flag": geo_flag,
                "Match_Method": "exact_npi" if _valid_npi(npi) else "invalid_npi",
                "Confidence_or_Evidence_Level": "HIGH" if addr_status == "CORROBORATED" else "MEDIUM" if addr_status == "SINGLE_SOURCE" else "LOW" if addr_status == "CONFLICTING" else "NONE",
                "TIN_Address_Link_Status": tin_link,
                "TIN_Modal_ZIP3": tin_modal_zip3,
                "TIN_Support_Score": tin_support_score,
                "Taxonomy_Code": tax_code,
                "Specialty_Source": spec_source,
                "Specialty_Status": spec_status,
                "Negotiated_Type": negotiated_type,
                "Billing_Class": billing_class,
                "Setting": setting,
                "Service_Code": service_code,
                "Modifiers": modifiers,
                "Source_File": source_file,
                "Selection_Rule": selection_rule,
            }
            cwriter.writerow(out_row)
            row_count += 1
            if status not in ("UNRESOLVED", "INVALID_NPI"):
                addr_matched += 1
            # audit row
            audit_row = {
                "C4_Row_Id": idx,
                "NPI": npi,
                "TIN": tin,
                "Billing_Code": billing_code,
                "Original_Address": orig_addr,
                "Normalized_Address": norm if norm else "",
                "Source": source_str,
                "Source_Record_Id": "",
                "Source_Updated_At": updated,
                "Match_Method": "exact_npi",
                "Address_Status": addr_status,
                "Included_In_C5": "yes",
                "Reason": status,
                "TIN_Address_Link_Status": tin_link,
                "Taxonomy_Code": tax_code,
                "NUCC_Specialty": nucc_spec,
                "CMS_Specialty": cms_spec,
                "Specialty_Source": spec_source,
                "Specialty_Status": spec_status,
                "NUCC_vs_HiLabs_Discrepancy": nucc_hilabs_discrepancy,
                "Conflicting_Address": "yes" if has_conflict else "no",
                "Alternative_Addresses": "; ".join(a for a in distinct_norms if a != norm),
            }
            awriter.writerow(audit_row)
            audit_rows += 1

            # four-key uniqueness
            four_key = (npi, tin, billing_code, orig_addr)
            if four_key in four_key_set:
                four_key_dup += 1
            else:
                four_key_set.add(four_key)

    # unresolved/invalid rows already emitted as blank address rows above? For INVALID_NPI/UNRESOLVED we emitted one blank row.
    # Count unresolved
    # (already counted in loop)

    cf.close()
    pf.close()
    af.close()

    # summary
    summary = {
        "stage": "c5",
        "input_c4_rows": len(c4_rows),
        "candidate_keys_npi_tin": len(candidate_keys),
        "distinct_valid_npis": len(distinct_npi),
        "distinct_tins": len(distinct_tin),
        "output_rows": row_count,
        "address_matched_rows": addr_matched,
        "corroborated": corroborated,
        "single_source": single,
        "conflicting": conflicting,
        "unresolved": unresolved,
        "invalid_npi_count": invalid_npi_count,
        "unverified_tin_address_links": unverified_tin,
        "supported_tin_address_links": supported_tin,
        "duplicate_four_key_rows": four_key_dup,
        "specialty_mapped": specialty_mapped,
        "specialty_unmapped": specialty_unmapped,
        "nppes_zip": "NPPES_Data_Dissemination_October_2026_V2.zip",
        "cms_file": "DAC_NationalDownloadableFile.csv",
        "nucc_file": "nucc_taxonomy_261.csv",
        "nucc_mapped_codes": len(nucc),
        "api_status": npd_stats,
        "geocoding": geocode_stats,
        "sources": ["NPPES", "NPPES_PL", "CMS_DAC", "CMS_NPD_LOCATION"],
    }
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")

    write_manifest(
        manifest_path,
        stage="c5",
        config_path=cfg.root / "config.yaml",
        sources=[{"path": str(c4_path)}, {"path": str(outer_zip)}],
        counts={
            "input_c4_rows": len(c4_rows),
            "candidate_keys_npi_tin": len(candidate_keys),
            "output_rows": row_count,
            "distinct_valid_npis": len(distinct_npi),
            "address_matched_rows": addr_matched,
            "unresolved": unresolved,
            "invalid_npi_count": invalid_npi_count,
        },
        started_at=started_at,
    )

    print(f"C5: input_rows={len(c4_rows)} candidate_keys={len(candidate_keys)} output_rows={row_count} npis={len(distinct_npi)}")
    print(f"C5: corroborated={corroborated} single={single} conflicting={conflicting} unresolved={unresolved}")
    print(f"C5: outputs={candidate_path}, {c5_path}, {audit_path}, {summary_path}")

    return StageResult("c5", summary, (candidate_path, c5_path, audit_path, summary_path, manifest_path))

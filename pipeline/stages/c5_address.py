"""C5: map C4 provider rates to practice addresses and NUCC specialties."""

from __future__ import annotations

import csv
import io
import json
import re
import time
import zipfile
from difflib import SequenceMatcher

try:
    import openpyxl
except (OSError, KeyError, ValueError, TypeError, ImportError):
    openpyxl = None
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pipeline.config import Config
from pipeline.io.manifest import write_manifest

C5_COLUMNS = [
    "NPI", "TIN", "Address", "Billing_Code", "Specialty", "Rate",
    "Address_Status", "Address_Confidence", "Address_Source", "Address_Source_Count",
    "Address_Record_Updated_At", "Address_Role", "Address_Evidence_Tier",
    "Match_Method", "TIN_Address_Link_Status", "Taxonomy_Code",
    "Specialty_Source", "Specialty_Status", "Negotiated_Type", "Billing_Class",
    "Setting", "Service_Code", "Modifiers", "Source_File", "Selection_Rule",
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


def _valid_npi(npi: str) -> bool:
    return len(npi) == 10 and npi.isdigit()


def _address_role(addr: str) -> str:
    u = (addr or "").upper()
    if "PO BOX" in u or "P.O. BOX" in u or "P O BOX" in u:
        return "mailing/po_box"
    return "practice"


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

    npi_set = set()
    for r in c4_rows:
        npi = _text(r.get("npi"))
        if _valid_npi(npi):
            npi_set.add(npi)

    outer_zip = cfg.archive if str(cfg.archive).endswith(".zip") else None
    if outer_zip is None:
        outer_zip = Path(cfg.data_dir) / "hilabs_dataset_2026-10-17.zip"
    nucc = _load_nucc(outer_zip)
    specproc = _load_specproc(outer_zip)
    # outer zip path
    nppes_map, primary_tax = _build_nppes(outer_zip, npi_set)
    cms_map = _build_cms(outer_zip, npi_set, primary_tax)

    # outputs
    c5_path = out_dir / "c5result.csv"
    audit_path = out_dir / "c5_address_audit.csv"
    summary_path = out_dir / "c5_summary.json"
    manifest_path = out_dir / "_manifest.json"

    cf = c5_path.open("w", newline="", encoding="utf-8")
    af = audit_path.open("w", newline="", encoding="utf-8")
    cwriter = csv.DictWriter(cf, fieldnames=C5_COLUMNS, extrasaction="ignore")
    awriter = csv.DictWriter(af, fieldnames=AUDIT_COLUMNS, extrasaction="ignore")
    cwriter.writeheader()
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

        # gather addresses
        nppes_addrs = nppes_map.get(npi, []) if _valid_npi(npi) else []
        cms_addrs = cms_map.get(npi, []) if _valid_npi(npi) else []

        # build candidate address list with source tracking
        # group by normalized address
        addr_groups: dict[str, dict[str, Any]] = {}
        for rec in nppes_addrs + cms_addrs:
            norm = rec["norm"]
            if not norm:
                continue
            matched_key = None
            for existing in addr_groups:
                if _fuzzy_addr_equal(norm, existing):
                    matched_key = existing
                    break
            if matched_key is None:
                addr_groups[norm] = {"orig": rec["orig"], "sources": set(), "families": set(),
                                     "taxonomy": rec.get("taxonomy", ""),
                                     "cms_specialty": rec.get("cms_specialty", ""), "updated": rec.get("updated", "")}
                target = norm
            else:
                target = matched_key
                if not addr_groups[target]["orig"]:
                    addr_groups[target]["orig"] = rec["orig"]
            addr_groups[target]["sources"].add(rec["source"])
            if rec["source"].startswith("NPPES"):
                addr_groups[target]["families"].add("NPPES")
            else:
                addr_groups[target]["families"].add(rec["source"])
            if rec.get("taxonomy") and not addr_groups[target]["taxonomy"]:
                addr_groups[target]["taxonomy"] = rec["taxonomy"]
            if rec.get("cms_specialty") and not addr_groups[target]["cms_specialty"]:
                addr_groups[target]["cms_specialty"] = rec["cms_specialty"]

        # Determine distinct normalized addresses
        distinct_norms = list(addr_groups.keys())

        # status
        if not _valid_npi(npi):
            status = "INVALID_NPI"
        elif not distinct_norms:
            status = "UNRESOLVED"
            unresolved += 1
        elif len(distinct_norms) == 1 and len(addr_groups[distinct_norms[0]]["sources"]) >= 2:
            status = "CORROBORATED"
            corroborated += 1
        elif len(distinct_norms) == 1:
            status = "SINGLE_SOURCE"
            single += 1
        else:
            status = "CONFLICTING"
            conflicting += 1

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

            tin_link = "UNVERIFIED"

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
                "Address_Record_Updated_At": updated,
                "Address_Role": role,
                "Address_Evidence_Tier": tier,
                "Match_Method": "exact_npi" if _valid_npi(npi) else "invalid_npi",
                "Confidence_or_Evidence_Level": "HIGH" if addr_status == "CORROBORATED" else "MEDIUM" if addr_status == "SINGLE_SOURCE" else "LOW" if addr_status == "CONFLICTING" else "NONE",
                "TIN_Address_Link_Status": tin_link,
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
            if addr_status == "CORROBORATED":
                corroborated += 1
            elif addr_status == "SINGLE_SOURCE":
                single += 1
            elif addr_status == "CONFLICTING":
                conflicting += 1
            else:
                if addr_status == "UNRESOLVED":
                    unresolved += 1
                if addr_status == "INVALID_NPI":
                    pass
            unverified_tin += 1

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
    af.close()

    # summary
    summary = {
        "stage": "c5",
        "input_c4_rows": len(c4_rows),
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
        "duplicate_four_key_rows": four_key_dup,
        "specialty_mapped": specialty_mapped,
        "specialty_unmapped": specialty_unmapped,
        "nppes_zip": "NPPES_Data_Dissemination_October_2026_V2.zip",
        "cms_file": "DAC_NationalDownloadableFile.csv",
        "nucc_file": "nucc_taxonomy_261.csv",
        "nucc_mapped_codes": len(nucc),
        "api_status": "unavailable (network blocked / no NPI search param)",
        "sources": ["NPPES", "NPPES_PL", "CMS_DAC"],
    }
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")

    write_manifest(
        manifest_path,
        stage="c5",
        config_path=cfg.root / "config.yaml",
        sources=[{"path": str(c4_path)}, {"path": str(outer_zip)}],
        counts={
            "input_c4_rows": len(c4_rows),
            "output_rows": row_count,
            "distinct_valid_npis": len(distinct_npi),
            "address_matched_rows": addr_matched,
            "unresolved": unresolved,
            "invalid_npi_count": invalid_npi_count,
        },
        started_at=started_at,
    )

    print(f"C5: input_rows={len(c4_rows)} output_rows={row_count} npis={len(distinct_npi)}")
    print(f"C5: corroborated={corroborated} single={single} conflicting={conflicting} unresolved={unresolved}")
    print(f"C5: outputs={c5_path}, {audit_path}, {summary_path}")

    return StageResult("c5", summary, (c5_path, audit_path, summary_path, manifest_path))

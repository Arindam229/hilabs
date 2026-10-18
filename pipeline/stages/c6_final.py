"""C6: final curated provider rate workbook from C5 results."""

from __future__ import annotations

import csv
import json
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import openpyxl
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

from pipeline.config import Config
from pipeline.io.manifest import write_manifest
from pipeline.stages.c5_address import _address_state, _normalize_address, _text


@dataclass(frozen=True)
class StageResult:
    stage: str
    counts: dict[str, int]
    outputs: tuple[Path, ...]


TIER_RANK = {"Tier 1": 0, "Tier 2": 1, "Tier 3": 2, "Tier 4": 3}
STATUS_RANK = {"CORROBORATED": 0, "SINGLE_SOURCE": 1, "CONFLICTING": 2, "UNRESOLVED": 3, "INVALID_NPI": 4}


def _source_count(src: str) -> int:
    return len([x for x in (src or "").split(";") if x.strip()])


def _c5_summary_path(c5_path: Path) -> Path:
    return c5_path.parent / "c5_summary.json"


def _select_canonical(group_rows: list[dict[str, str]]) -> tuple[dict[str, str], str, str, list[str]]:
    """Return (selected_row, status, reason, alternatives)."""
    # dedup by normalized address
    by_norm: dict[str, dict[str, str]] = {}
    for r in group_rows:
        norm = _normalize_address(r.get("Address", ""), "", "", "", "")
        if norm not in by_norm:
            by_norm[norm] = r
    distinct = list(by_norm.values())
    [r.get("Address", "") for r in distinct]

    if len(distinct) == 1:
        return distinct[0], "SINGLE_ADDRESS", "only one distinct address", []

    # rank
    def rank_key(r):
        try:
            score = float(r.get("Address_Score", "0") or 0)
        except ValueError:
            score = 0.0
        tier = r.get("Address_Evidence_Tier", "")
        tr = TIER_RANK.get(tier, 9)
        st = r.get("Address_Status", "")
        sr = STATUS_RANK.get(st, 9)
        sc = _source_count(r.get("Address_Source", ""))
        upd = r.get("Address_Record_Updated_At", "") or r.get("Source_Updated_At", "") or ""
        norm = _normalize_address(r.get("Address", ""), "", "", "", "")
        return (-score, tr, sr, -sc, 0 if upd else 1, norm)

    sorted_cands = sorted(distinct, key=rank_key)
    top = sorted_cands[0]
    # check tie
    top_key = rank_key(top)
    tied = [r for r in sorted_cands if rank_key(r) == top_key]
    st = top.get("Address_Status", "")
    if len(distinct) > 1 and st in ("CONFLICTING", "UNRESOLVED") and len(tied) > 1:
        status = "AMBIGUOUS_SINGLE_ADDRESS_SELECTED"
        reason = "conflicting/ambiguous addresses; selected best available (lexicographically smallest) fallback"
    elif len(tied) > 1:
        status = "AMBIGUOUS_SINGLE_ADDRESS_SELECTED"
        reason = "tie among top candidates; selected lexicographically smallest address"
    else:
        status = "CANONICAL_SELECTED"
        if st == "SINGLE_SOURCE":
            reason = "only available source"
        else:
            reason = "highest address evidence score"
    alt_list = [r.get("Address", "") for r in sorted_cands[1:]]
    return top, status, reason, alt_list


def run_c6(cfg: Config, c5_path: Path | None = None, output_path: Path | None = None, **kwargs) -> StageResult:
    started_at = time.monotonic()
    if c5_path is None:
        c5_path = cfg.stage_dir("c5") / "c5result.csv"
    if output_path is None:
        out_path = cfg.data_dir / "out" / "final_provider_rates.xlsx"
    else:
        out_path = Path(output_path)
        if not out_path.is_absolute():
            out_path = cfg.root / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with c5_path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    # Group by (NPI, TIN, Billing_Code)
    groups: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    for r in rows:
        key = (r.get("NPI", ""), r.get("TIN", ""), r.get("Billing_Code", ""))
        groups[key].append(r)

    selected_rows = []
    audit_rows = []
    seen_keys = set()
    dup_keys = 0
    ambiguous_count = 0
    for key, grp in groups.items():
        # Defense in depth: C6 never exports an out-of-market or unknown-state address,
        # even when supplied an older C5 artifact produced before CA-only filtering.
        grp = [row for row in grp if _address_state(row.get("Address", "")) == "CA"]
        if not grp:
            continue
        sel, status, reason, alts = _select_canonical(grp)
        if status == "AMBIGUOUS_SINGLE_ADDRESS_SELECTED":
            ambiguous_count += 1
        # filter billing code length 5
        if len(_text(sel.get("Billing_Code", ""))) != 5:
            continue
        out_row = dict(sel)
        out_row["Address_Candidate_Count"] = len({_normalize_address(r.get("Address", ""), "", "", "", "") for r in grp})
        out_row["Address_Selection_Status"] = status
        out_row["Address_Selection_Reason"] = reason
        out_row["Alternative_Addresses"] = "; ".join(alts)
        selected_rows.append(out_row)

        audit_rows.append({
            "NPI": key[0],
            "TIN": key[1],
            "Billing_Code": key[2],
            "Selected_Address": sel.get("Address", ""),
            "Candidate_Count": out_row["Address_Candidate_Count"],
            "Address_Evidence_Tier": sel.get("Address_Status", ""),
            "Selection_Reason": reason,
            "Selection_Status": status,
            "Alternative_Addresses": "; ".join(alts),
            "TIN_Address_Link_Status": sel.get("TIN_Address_Link_Status", ""),
        })

        k2 = (key[0], key[1], key[2])
        if k2 in seen_keys:
            dup_keys += 1
        else:
            seen_keys.add(k2)

    # Final curation: keep only rows with complete required fields and 5-char billing codes.
    selected_rows = [r for r in selected_rows
                     if len(_text(r.get("Billing_Code", ""))) == 5
                     and _text(r.get("NPI", ""))
                     and _text(r.get("TIN", ""))
                     and _text(r.get("Address", ""))
                     and _address_state(r.get("Address", "")) == "CA"
                     and _text(r.get("Specialty", ""))
                     and _text(r.get("Rate", ""))]

    # write audit csv
    audit_path = cfg.stage_dir("c6") / "c6_address_audit.csv"
    cfg.stage_dir("c6").mkdir(parents=True, exist_ok=True)
    with audit_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(audit_rows[0].keys()) if audit_rows else ["NPI"])
        w.writeheader()
        for r in audit_rows:
            w.writerow(r)

    # summary
    summary_path = _c5_summary_path(c5_path)
    summary = {}
    if summary_path.is_file():
        summary = json.loads(summary_path.read_text())

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Curated Rates"
    headers = ["NPI", "TIN", "Address", "Billing Code", "Specialty", "Rate",
               "Address_Status", "Address_Source", "Address_Confidence",
               "Address_Source_Count", "Address_Score", "Address_Verification_Status",
               "Address_Evidence_Tier", "Taxonomy_Code", "Specialty_Source",
               "Negotiated_Type", "Billing_Class", "Address_Candidate_Count",
               "Address_Selection_Status", "Address_Selection_Reason", "Specialty_Status",
               "Geocode_Status", "Latitude", "Longitude", "Nearest_TIN_Site_Distance_Km",
               "Geo_Score", "Geo_Anomaly_Flag", "TIN_Modal_ZIP3", "TIN_Support_Score",
               "TIN_Address_Link_Status", "Reassignment_Status", "Group_PAC_ID",
               "Reassignment_Group_Name", "Reassignment_Name_Match",
               "HN_Hidden_Reason", "PECOS_Enrollment"]
    ws.append(headers)
    for r in selected_rows:
        rate = r.get("Rate", "")
        try:
            rate = float(rate)
        except (TypeError, ValueError):
            pass
        address_source_count = r.get("Address_Source_Count", "")
        address_score = r.get("Address_Score", "")
        try:
            address_source_count = int(address_source_count)
        except (TypeError, ValueError):
            pass
        try:
            address_score = float(address_score)
            if address_score.is_integer():
                address_score = int(address_score)
        except (TypeError, ValueError):
            pass
        ws.append([
            r.get("NPI", ""), r.get("TIN", ""), r.get("Address", ""),
            r.get("Billing_Code", ""), r.get("Specialty", ""), rate,
            r.get("Address_Status", ""), r.get("Address_Source", ""),
            r.get("Address_Confidence", ""), address_source_count, address_score,
            r.get("Address_Verification_Status", ""), r.get("Address_Evidence_Tier", ""),
            r.get("Taxonomy_Code", ""), r.get("Specialty_Source", ""),
            r.get("Negotiated_Type", ""), r.get("Billing_Class", ""),
            r.get("Address_Candidate_Count", ""),
            r.get("Address_Selection_Status", ""),
            r.get("Address_Selection_Reason", ""),
            r.get("Specialty_Status", ""), r.get("Geocode_Status", ""),
            r.get("Latitude", ""), r.get("Longitude", ""),
            r.get("Nearest_TIN_Site_Distance_Km", ""), r.get("Geo_Score", ""),
            r.get("Geo_Anomaly_Flag", ""), r.get("TIN_Modal_ZIP3", ""),
            r.get("TIN_Support_Score", ""), r.get("TIN_Address_Link_Status", ""),
            r.get("Reassignment_Status", ""), r.get("Group_PAC_ID", ""),
            r.get("Reassignment_Group_Name", ""), r.get("Reassignment_Name_Match", ""),
            r.get("HN_Hidden_Reason", ""), r.get("PECOS_Enrollment", ""),
        ])
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{ws.max_row}"
    for c in ws[1]:
        c.font = Font(bold=True)

    dq = wb.create_sheet("Data Quality")
    dq.append(["Metric", "Value"])
    dq.append(["C5 input rows", len(rows)])
    dq.append(["C6 curated rows", len(selected_rows)])
    dq.append(["Distinct (NPI,TIN,Billing Code) groups", len(groups)])
    dq.append(["Ambiguous selections", ambiguous_count])
    dq.append(["Duplicate (NPI,TIN,Billing Code) keys", dup_keys])
    for k, v in summary.items():
        if isinstance(v, (int, float, str)) and not isinstance(v, bool):
            dq.append([f"c5:{k}", v])
    for c in dq[1]:
        c.font = Font(bold=True)

    audit = wb.create_sheet("Audit and Sources")
    audit.append(["Item", "Detail"])
    audit.append(["C5 input", str(c5_path)])
    audit.append(["C6 address audit", str(audit_path)])
    audit.append(["Candidate key", "(NPI, TIN, Address)"])
    audit.append(["Rate join", "C4 rates attach to C5 candidates on (NPI, TIN)"])
    audit.append(["Selection", "one canonical address per (NPI, TIN, Billing Code)"])
    audit.append(["API", json.dumps(summary.get("api_status", "not used"), sort_keys=True)])
    for c in audit[1]:
        c.font = Font(bold=True)

    wb.save(out_path)
    out_csv_path = out_path.with_suffix(".csv")
    with open(out_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for r in selected_rows:
            writer.writerow([r.get(h, "") for h in headers])

    manifest_path = cfg.stage_dir("c6") / "_manifest.json"
    cfg.stage_dir("c6").mkdir(parents=True, exist_ok=True)
    write_manifest(
        manifest_path,
        stage="c6",
        config_path=cfg.root / "config.yaml",
        sources=[{"path": str(c5_path)}],
        counts={"c5_rows": len(rows), "c6_rows": len(selected_rows),
                "groups": len(groups), "ambiguous": ambiguous_count, "duplicate_keys": dup_keys},
        started_at=started_at,
    )

    print(f"C6: groups={len(groups)} selected={len(selected_rows)} ambiguous={ambiguous_count} dup_keys={dup_keys}")
    print(f"C6: output={out_path} audit={audit_path}")
    return StageResult("c6", {"c6_rows": len(selected_rows), "ambiguous": ambiguous_count}, (out_path, audit_path, manifest_path))

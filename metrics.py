#!/usr/bin/env python3
"""C3: grade a Centene PTD in-network file for quality and completeness.

One streaming pass (ijson) over the file computes every metric -- real
files run up to ~700MB, so json.load() isn't an option (and the PS
explicitly scores streaming vs. whole-file loads).

Usage:
    python metrics.py path/to/in-network.json
    python metrics.py path/to/in-network.json --out scorecard.json
    python metrics.py path/to/in-network.json --benchmark other.xlsx --pfs-zip other.zip
    python metrics.py path/to/in-network.json --no-benchmark --no-pfs   # skip either reference dataset

Reference data (both optional, both default to the HiLabs-supplied paths
under data/hilabs_dataset_2026-10-17/ if present):
  --benchmark  HiLabs' Specialty/Procedure weighting Excel -> code coverage (M1, M2)
  --pfs-zip    CMS Physician Fee Schedule RVUs -> E/M ladder ordering (M5) and
               the Medicare-rate benchmark (M11)
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
import zipfile
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterator

import ijson
import pandas as pd

HERE = Path(__file__).resolve().parent
_DATASET = HERE / "data" / "hilabs_dataset_2026-10-17"
DEFAULT_BENCHMARK_XLSX = (
    _DATASET / "hilabs" / "Rate Benchmarking Individual Weights_Hackathon.xlsx"
    if (_DATASET / "hilabs" / "Rate Benchmarking Individual Weights_Hackathon.xlsx").exists()
    else HERE / "Rate Benchmarking Individual Weights_Hackathon.xlsx"
)
DEFAULT_PFS_ZIP = _DATASET / "cms_pfs" / "rvu26d-updated-08-26-2026.zip"

OUTLIER_MIN_SAMPLES = 5  # below this, a per-code IQR/z-score is just noise
OUTLIER_Z_THRESHOLD = 3.0  # robust (median/MAD) z-score on log(rate)

# CPT established/new-patient office-visit families. Which codes are
# "more complex than which" is NOT assumed here -- see em_ladders_by_rvu().
EM_LADDER_CODES = {
    "established_patient": ["99211", "99212", "99213", "99214", "99215"],
    "new_patient": ["99202", "99203", "99204", "99205"],
}


# --------------------------------------------------------------------------
# Reference data: HiLabs benchmark Excel + CMS Physician Fee Schedule
# --------------------------------------------------------------------------


def load_benchmark(xlsx_path: Path) -> dict[str, Any]:
    """HiLabs' own Specialty/Procedure weighting: the authoritative code
    universe + importance weights M1/M2 score coverage against."""
    df_proc = pd.read_excel(xlsx_path, sheet_name="Spec-Proc Weights")
    df_spec = pd.read_excel(xlsx_path, sheet_name="Specialty Weights")
    proc_weights = (
        df_proc.drop_duplicates(subset=["PROC_CD"])
        .set_index("PROC_CD")["SPEC_PROC_WEIGHT"]
        .to_dict()
    )
    top_specs = (
        df_spec.sort_values("Specialty Weight", ascending=False).head(10)["Spec Code"].tolist()
    )
    top_spec_codes = (
        df_proc[df_proc["SPEC_CD"].isin(top_specs) & (df_proc["SPEC_PROC_RANK"] <= 5)]
        .groupby("SPEC_CD")["PROC_CD"]
        .apply(set)
        .to_dict()
    )
    return {"proc_weights": proc_weights, "top_spec_codes": top_spec_codes}


_PFS_PAYABLE_STATUS = {"A", "R", "T"}

# What we need, by the CMS file's own column text -- not by position.
# The real PFS CSV splits each column name across two header rows (e.g.
# row "WORK" + row "RVU" = "WORK RVU"); reading by position breaks
# silently (wrong number read as a different field) if CMS ever reorders
# columns between releases. Reading by name instead either finds the
# right column wherever it moved to, or raises a clear error -- it never
# silently returns wrong data.
_PFS_REQUIRED_COLUMNS = {
    "code": "HCPCS",
    "status": "STATUS CODE",
    "work_rvu": "WORK RVU",
    "pe_rvu_nonfac": "NON-FAC PE RVU",
    "pe_rvu_fac": "FACILITY PE RVU",
    "mp_rvu": "MP RVU",
    "conversion_factor": "CONV FACTOR",
}


def _find_pfs_columns(rows: list[list[str]]) -> tuple[int, dict[str, int]]:
    """Locate the header row by content (the preamble/copyright-notice
    row count isn't fixed release to release), then map each two-row
    combined column name -> index."""
    for i, row in enumerate(rows):
        if any(cell.strip() == "HCPCS" for cell in row):
            sub_header = rows[i - 1] if i > 0 else [""] * len(row)
            combined = [f"{a} {b}".strip() for a, b in zip(sub_header, row)]
            return i, {text: idx for idx, text in enumerate(combined) if text}
    raise ValueError(
        "Could not find the CMS PFS header row (no 'HCPCS' column) -- "
        "this file's layout doesn't match what load_pfs_table expects."
    )


def load_pfs_table(zip_path: Path) -> dict[str, dict[str, float]]:
    """CMS Physician Fee Schedule RVUs: a government-published, objective
    complexity/cost ranking -- used for both the E/M ladder order (M5) and
    the Medicare-rate benchmark. Columns are located by name (see above),
    not by hardcoded position."""
    with zipfile.ZipFile(zip_path) as z, z.open("PPRRVU2026_Oct_nonQPP.csv") as f:
        rows = list(csv.reader(io.TextIOWrapper(f, encoding="utf-8-sig")))

    header_row, columns = _find_pfs_columns(rows)
    missing = [text for text in _PFS_REQUIRED_COLUMNS.values() if text not in columns]
    if missing:
        raise ValueError(f"CMS PFS file is missing expected column(s): {missing}")
    col = {name: columns[text] for name, text in _PFS_REQUIRED_COLUMNS.items()}
    last_needed = max(col.values())

    table: dict[str, dict[str, float]] = {}
    for row in rows[header_row + 1 :]:
        if len(row) <= last_needed or row[col["status"]] not in _PFS_PAYABLE_STATUS:
            continue
        try:
            table[row[col["code"]]] = {
                "work_rvu": float(row[col["work_rvu"]]),
                "pe_rvu_nonfac": float(row[col["pe_rvu_nonfac"]]),
                "pe_rvu_fac": float(row[col["pe_rvu_fac"]]),
                "mp_rvu": float(row[col["mp_rvu"]]),
                "conversion_factor": float(row[col["conversion_factor"]]),
            }
        except ValueError:
            continue  # blank/non-numeric fragment row
    return table


def em_ladders_by_rvu(pfs_table: dict[str, dict[str, float]]) -> dict[str, list[str]]:
    """Each E/M family ordered by total RVU ascending -- the expected
    "costs more" order comes from CMS's own valuation, not an assumption
    that higher CPT numbers mean higher complexity."""
    ladders = {}
    for name, codes in EM_LADDER_CODES.items():
        present = [c for c in codes if c in pfs_table]
        present.sort(key=lambda c: sum(pfs_table[c].values()))
        if len(present) >= 2:
            ladders[name] = present
    return ladders


def california_blended_gpci(zip_path: Path) -> dict[str, float]:
    """Mean work/PE/MP GPCI across all CA localities -- a stated, bounded
    approximation (real GPCI needs per-provider locality, which is C5's
    job), good enough to tell "roughly Medicare-aligned" from "not"."""
    with zipfile.ZipFile(zip_path) as z, z.open("GPCI2026.csv") as f:
        rows = list(csv.reader(io.TextIOWrapper(f, encoding="utf-8-sig")))
    ca_rows = [r for r in rows if len(r) > 1 and r[1] == "CA"]
    return {
        "work": sum(float(r[4]) for r in ca_rows) / len(ca_rows),
        "pe": sum(float(r[5]) for r in ca_rows) / len(ca_rows),
        "mp": sum(float(r[6]) for r in ca_rows) / len(ca_rows),
    }


def medicare_lookup(pfs_table: dict[str, dict[str, float]], gpci: dict[str, float]) -> dict[str, dict[str, float]]:
    """code -> {nonfac, fac} CA-blended Medicare allowed amount."""
    lookup: dict[str, dict[str, float]] = {}
    for code, rvu in pfs_table.items():
        nonfac = (rvu["work_rvu"] * gpci["work"] + rvu["pe_rvu_nonfac"] * gpci["pe"] + rvu["mp_rvu"] * gpci["mp"]) * rvu["conversion_factor"]
        fac = (rvu["work_rvu"] * gpci["work"] + rvu["pe_rvu_fac"] * gpci["pe"] + rvu["mp_rvu"] * gpci["mp"]) * rvu["conversion_factor"]
        if nonfac > 0 or fac > 0:
            lookup[code] = {"nonfac": nonfac, "fac": fac}
    return lookup


# --------------------------------------------------------------------------
# Streaming over the in-network file (single pass)
# --------------------------------------------------------------------------


def read_header_and_declared_groups(path: Path) -> tuple[dict[str, Any], set[int]]:
    """Cheap preamble-only pass: stops the instant in_network starts, so
    this never touches the multi-hundred-MB part of the file."""
    header: dict[str, Any] = {}
    declared: set[int] = set()
    wanted = {"reporting_entity_name", "reporting_entity_type", "version", "last_updated_on"}
    with path.open("rb") as f:
        for prefix, event, value in ijson.parse(f):
            if prefix in wanted and event == "string":
                header[prefix] = value
            if prefix == "provider_references.item.provider_group_id" and event == "number":
                declared.add(int(value))
            if prefix == "in_network" and event == "start_array":
                break
    return header, declared


def iter_price_rows(path: Path) -> Iterator[dict[str, Any]]:
    with path.open("rb") as f:
        for item in ijson.items(f, "in_network.item"):
            code = item.get("billing_code")
            for nr in item.get("negotiated_rates", []):
                provider_refs = tuple(nr.get("provider_references", []))
                for price in nr.get("negotiated_prices", []):
                    rate = price.get("negotiated_rate")
                    yield {
                        "billing_code": code,
                        "negotiated_type": price.get("negotiated_type"),
                        "negotiated_rate": float(rate) if rate is not None else None,
                        "billing_class": price.get("billing_class"),
                        "setting": price.get("setting"),
                        "service_code": tuple(price.get("service_code") or []),
                        "billing_code_modifier": tuple(price.get("billing_code_modifier") or []),
                        "additional_information": price.get("additional_information"),
                        "provider_group_ids": provider_refs,
                    }


# --------------------------------------------------------------------------
# Metrics
# --------------------------------------------------------------------------


def _outlier_count(rates_by_code: dict[str, list[float]]) -> int:
    """Per billing code, not globally -- rate scale varies hugely by
    procedure (an MRI's normal range would swamp an office visit's in one
    shared distribution)."""
    count = 0
    for rates in rates_by_code.values():
        if len(rates) < OUTLIER_MIN_SAMPLES:
            continue
        logs = sorted(math.log(r) for r in rates)
        median = logs[len(logs) // 2]
        mad = sorted(abs(x - median) for x in logs)[len(logs) // 2] or 1e-9
        count += sum(1 for x in logs if abs(0.6745 * (x - median) / mad) > OUTLIER_Z_THRESHOLD)
    return count


def _em_monotonicity(
    em_group_rates: dict[tuple[str, tuple], dict[str, float]],
    ladders: dict[str, list[str]],
) -> dict[str, Any]:
    """For every E/M ladder pair present in the SAME (billing_class,
    setting, service_code, modifier, provider) context, the higher-RVU
    code's rate must not be lower than the lower-RVU code's. A violation
    with everything else held constant can only be explained by the
    complexity tier itself -- it isn't confounded by a different setting,
    modifier, or service_code.

    Denominator is groups that actually HAVE >=2 comparable codes, not
    every group that merely has one E/M code (which can never violate
    anything and would just dilute the rate).
    """
    comparable_groups = 0
    violating_groups = 0
    comparable_pairs = 0
    violating_pairs = 0

    for (ladder_name, _group_key), rates in em_group_rates.items():
        ladder = ladders.get(ladder_name, [])
        present = [c for c in ladder if c in rates]
        if len(present) < 2:
            continue
        comparable_groups += 1
        group_violated = False
        for i in range(len(present)):
            for j in range(i + 1, len(present)):
                lo, hi = present[i], present[j]  # hi has >= RVU of lo by construction
                comparable_pairs += 1
                if rates[hi] < rates[lo]:
                    violating_pairs += 1
                    group_violated = True
        if group_violated:
            violating_groups += 1

    # This metric only has something to say where E/M office-visit codes
    # are actually billed -- an institutional/facility-heavy file may
    # legitimately bill none. That's a real, expected limit of this one
    # metric, not a bug: say so explicitly rather than returning a bare
    # null that looks the same as "something went wrong."
    applicable = comparable_groups > 0
    return {
        "applicable": applicable,
        "reason": None if applicable else "no provider/context in this file bills 2+ codes from the same E/M ladder",
        "comparable_groups": comparable_groups,
        "violating_groups": violating_groups,
        "violation_rate_pct": (
            round(100 * violating_groups / comparable_groups, 2) if applicable else None
        ),
        "comparable_pairs": comparable_pairs,
        "violating_pairs": violating_pairs,
    }


def compute_metrics(
    rows: Iterator[dict[str, Any]],
    *,
    header: dict[str, Any],
    declared_groups: set[int],
    benchmark: dict[str, Any] | None = None,
    em_ladders: dict[str, list[str]] | None = None,
    medicare: dict[str, dict[str, float]] | None = None,
    as_of: date | None = None,
) -> dict[str, Any]:
    as_of = as_of or date.today()
    em_ladders = em_ladders or {}

    file_codes: set[str] = set()
    referenced_groups: set[int] = set()
    negotiated_type_counts: Counter[str] = Counter()
    rates_by_code: defaultdict[str, list[float]] = defaultdict(list)
    pair_rates: defaultdict[tuple, set[float]] = defaultdict(set)
    full_tuple_counts: Counter[tuple] = Counter()
    em_group_rates: defaultdict[tuple, dict[str, float]] = defaultdict(dict)
    medicare_ratios: list[float] = []
    total = 0
    zero_or_negative = 0

    em_codes = {c for codes in EM_LADDER_CODES.values() for c in codes}

    for row in rows:
        total += 1
        code = row["billing_code"]
        rate = row["negotiated_rate"]
        file_codes.add(code)
        referenced_groups.update(row["provider_group_ids"])
        negotiated_type_counts[row["negotiated_type"]] += 1

        if rate is None:
            continue
        if rate <= 0:
            zero_or_negative += 1
            continue

        rates_by_code[code].append(rate)
        pair_rates[(code, row["provider_group_ids"])].add(rate)
        full_tuple_counts[
            (
                code,
                row["provider_group_ids"],
                rate,
                row["billing_class"],
                row["setting"],
                row["service_code"],
                row["billing_code_modifier"],
                row["additional_information"],
            )
        ] += 1

        if code in em_codes:
            ladder_name = next((n for n, cs in EM_LADDER_CODES.items() if code in cs), None)
            group_key = (
                ladder_name,
                (
                    row["billing_class"],
                    row["setting"],
                    row["service_code"],
                    row["billing_code_modifier"],
                    row["provider_group_ids"],
                ),
            )
            em_group_rates[group_key][code] = rate

        if medicare and code in medicare:
            lookup = medicare[code]["fac" if row["billing_class"] == "institutional" else "nonfac"]
            if lookup:
                medicare_ratios.append(rate / lookup)

    if total == 0:
        return {"price_count": 0, "note": "empty or unreadable file"}

    staleness_days = None
    if header.get("last_updated_on"):
        staleness_days = (as_of - datetime.strptime(header["last_updated_on"], "%Y-%m-%d").date()).days

    multi_rate_pairs = sum(1 for s in pair_rates.values() if len(s) > 1)
    duplicate_entries = sum(c - 1 for c in full_tuple_counts.values() if c > 1)

    code_coverage = None
    top_spec_breadth = None
    if benchmark:
        proc_weights = benchmark["proc_weights"]
        matched = file_codes & proc_weights.keys()
        total_weight = sum(proc_weights.values())
        code_coverage = {
            "matched_codes": len(matched),
            "weighted_coverage_pct": (
                round(100 * sum(proc_weights[c] for c in matched) / total_weight, 2) if total_weight else None
            ),
        }
        top_spec_codes = benchmark["top_spec_codes"]
        if top_spec_codes:
            covered = sum(1 for codes in top_spec_codes.values() if file_codes & codes)
            top_spec_breadth = round(100 * covered / len(top_spec_codes), 2)

    medicare_metrics = None
    if medicare is not None:
        # "applicable" distinguishes "wasn't asked to run" (key is just
        # absent/None, see below) from "ran, and this file has ~zero
        # CPT/HCPCS-coded professional prices to compare" -- expected on
        # an institutional-heavy file, not an error.
        applicable = len(medicare_ratios) > 0
        medicare_ratios.sort()
        n = len(medicare_ratios)
        medicare_metrics = {
            "applicable": applicable,
            "reason": None if applicable else "no prices in this file matched a CPT/HCPCS code priced by the PFS",
            "coverage_pct": round(100 * n / total, 4) if applicable else 0.0,
            "median_pct_of_medicare": round(100 * medicare_ratios[n // 2], 1) if applicable else None,
            "below_50pct_of_medicare_pct": (
                round(100 * sum(1 for r in medicare_ratios if r < 0.5) / n, 2) if applicable else None
            ),
            "above_400pct_of_medicare_pct": (
                round(100 * sum(1 for r in medicare_ratios if r > 4.0) / n, 2) if applicable else None
            ),
        }

    orphan_refs = referenced_groups - declared_groups
    ghost_groups = declared_groups - referenced_groups

    return {
        "file_metadata": {
            "schema_version": header.get("version"),
            "last_updated_on": header.get("last_updated_on"),
            "staleness_days": staleness_days,
        },
        "volume": {
            "price_count": total,
            "distinct_codes": len(file_codes),
            "declared_provider_groups": len(declared_groups),
            "referenced_provider_groups": len(referenced_groups),
        },
        "code_coverage": code_coverage,
        "top_specialty_breadth_pct": top_spec_breadth,
        "zero_or_negative_rate_pct": round(100 * zero_or_negative / total, 4),
        "outlier_rate_pct": round(100 * _outlier_count(rates_by_code) / total, 2),
        "em_monotonicity": _em_monotonicity(em_group_rates, em_ladders),
        "rate_ambiguity_density_pct": (
            round(100 * multi_rate_pairs / len(pair_rates), 2) if pair_rates else None
        ),
        "duplicate_entry_pct": round(100 * duplicate_entries / total, 2),
        "rate_type_certainty_pct": round(
            100 * negotiated_type_counts.get("negotiated", 0) / total, 2
        ),
        "pointer_hygiene": {
            "orphan_references": len(orphan_refs),
            "ghost_groups": len(ghost_groups),
            "integrity_pct": round(
                100 * (1 - (len(orphan_refs) + len(ghost_groups)) / max(1, len(declared_groups))), 2
            ),
        },
        "medicare_benchmark": medicare_metrics,
    }


def grade_file(
    path: Path,
    *,
    benchmark_xlsx: Path | None = DEFAULT_BENCHMARK_XLSX,
    pfs_zip: Path | None = DEFAULT_PFS_ZIP,
) -> dict[str, Any]:
    header, declared_groups = read_header_and_declared_groups(path)

    benchmark = None
    if benchmark_xlsx and Path(benchmark_xlsx).exists():
        benchmark = load_benchmark(Path(benchmark_xlsx))

    em_ladders: dict[str, list[str]] = {}
    medicare = None
    if pfs_zip and Path(pfs_zip).exists():
        pfs_table = load_pfs_table(Path(pfs_zip))
        em_ladders = em_ladders_by_rvu(pfs_table)
        gpci = california_blended_gpci(Path(pfs_zip))
        medicare = medicare_lookup(pfs_table, gpci)

    metrics = compute_metrics(
        iter_price_rows(path),
        header=header,
        declared_groups=declared_groups,
        benchmark=benchmark,
        em_ladders=em_ladders,
        medicare=medicare,
    )
    metrics["file"] = path.name
    return metrics


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("in_network_file", type=Path, help="Path to a Centene *_in-network.json file")
    parser.add_argument("--benchmark", type=Path, default=DEFAULT_BENCHMARK_XLSX)
    parser.add_argument("--pfs-zip", type=Path, default=DEFAULT_PFS_ZIP)
    parser.add_argument("--no-benchmark", action="store_true", help="skip the HiLabs weighting Excel")
    parser.add_argument("--no-pfs", action="store_true", help="skip the CMS PFS reference data")
    parser.add_argument("--out", type=Path, default=None, help="write JSON here instead of stdout")
    args = parser.parse_args()

    result = grade_file(
        args.in_network_file,
        benchmark_xlsx=None if args.no_benchmark else args.benchmark,
        pfs_zip=None if args.no_pfs else args.pfs_zip,
    )
    text = json.dumps(result, indent=2, default=str)
    if args.out:
        args.out.write_text(text)
        print(f"Wrote {args.out}")
    else:
        print(text)


if __name__ == "__main__":
    main()

"""C7 (brownie point): rate cost-effectiveness vs. similar providers.

"Similar" = same billing code, with specialty-matched peers preferred over
cross-specialty ones (proven *not* interchangeable -- see the credibility
blend below). Every number is anchored in the CMS Physician Fee Schedule,
resolved to each provider's own practice locality (not a statewide
average), so geography is corrected for before any peer comparison happens.

Three real properties of this dataset drive every design choice here, all
verified against data/out/final_provider_rates.xlsx, not assumed:
  - 1,550 of 3,146 providers (49%) bill exactly ONE code. A naive
    per-provider average is a single noisy data point for half the book.
  - Of 3,761 (Specialty, Code) cohorts, the MEDIAN size is 1 provider.
    Requiring exact specialty+code peer match is unusable most of the time.
  - Only 64.8% of priced rows (by row count) match a CMS PFS code at all --
    the rest (preventive-visit, drug J-codes, DME, lab codes) are priced
    under *different* Medicare fee schedules entirely. This is structural,
    not a data quality bug, and is tracked explicitly rather than ignored.

Math, in one pass per provider (no per-row quadratic cohort scans -- see
_leave_one_out_median for the O(1)-after-sort trick that makes this cheap
even for the largest cohort, ~980 rows):

  medicare_ratio(p, c)   = Rate(p, c) / medicare_allowed(c, locality(p))
  peer_specialty(p, c)   = leave-one-out median of medicare_ratio over the
                            same (Specialty, Code) cohort
  peer_code_only(p, c)   = leave-one-out median of medicare_ratio over the
                            same Code, any specialty (weaker signal --
                            proven not to control for specialty mix: the
                            coefficient of variation for code 99214 is
                            identical, 0.967, whether measured in raw
                            dollars or medicare_ratio)

  z_A = n_specialty_code / (n_specialty_code + K_A), K_A = 5
  z_B = n_code_only       / (n_code_only + K_B),       K_B = 10 (double K_A:
        cross-specialty data needs ~2x the sample to earn equal trust)

  reference_ratio(p, c) = z_A * peer_specialty
                         + (1 - z_A) * (z_B * peer_code_only
                                        + (1 - z_B) * medicare_ratio(p, c))

  PPI_raw(p)      = weighted average of reference_ratio(p, c) over p's
                     priceable basket, weights = HiLabs SPEC_PROC_WEIGHT
                     (median HiLabs weight for a PFS-matched code HiLabs did not weight)
  Z_p             = W_p / (W_p + K_provider), K_provider = median basket
                     weight across ALL providers in this dataset (not
                     per-specialty -- most specialties are themselves too
                     thin to give a stable per-specialty median)
  PPI_credible(p) = Z_p * PPI_raw(p) + (1 - Z_p) * 1.00

Codes with neither a PFS match nor any peer data contribute nothing (not
silently defaulted to 1.00, which would manufacture false evidence) and
are tracked in effective_basket_pct so a thin, well-supported score is
never indistinguishable from a thin, unsupported one.
"""

from __future__ import annotations

import csv
import difflib
import io
import re
import sys as _sys
import time
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Any

import openpyxl
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

from pipeline.config import Config
from pipeline.io.archive import require_member
from pipeline.io.manifest import write_manifest

_sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from metrics import load_benchmark, load_pfs_table


@dataclass(frozen=True)
class StageResult:
    stage: str
    counts: dict[str, int]
    outputs: tuple[Path, ...]


K_A = 5.0  # half-credibility sample size, specialty+code cohort
K_B = 10.0  # half-credibility sample size, code-only cohort (2x K_A: noisier per-observation)
DEFAULT_CODE_WEIGHT = 1.0  # a PFS-priced code HiLabs didn't separately weight
REST_OF_CALIFORNIA_LOCALITY = "75"
CA_FIPS_PREFIX = "06"
# Stress-tested pairwise against all 58 real CA county names (see
# load_county_to_locality docstring): zero false-positive collisions at
# this threshold, while still catching CMS's real "ORAGNGE"/"ORANGE" typo.
FUZZY_COUNTY_CUTOFF = 0.85

_ZIP_RE = re.compile(r"(\d{5})(?:-?\d{4})?\s*$")


# --------------------------------------------------------------------------
# Geography: ZIP -> county -> CMS locality -> GPCI
# --------------------------------------------------------------------------


def extract_zip5(address: str) -> str | None:
    m = _ZIP_RE.search((address or "").strip())
    return m.group(1) if m else None


def _dataset_member(archive_path: Path, relative: str) -> str:
    """Member path inside the outer archive, found by path suffix (pipeline/io/archive.py), so the
    archive's root folder name does not have to match its file name."""
    with zipfile.ZipFile(archive_path) as z:
        return require_member(z, relative)


def _open_nested_zip(archive_path: Path, member: str) -> zipfile.ZipFile:
    """A .zip file stored as a member of the outer archive (same pattern
    c5_address.py uses for the NPPES nested zip) -- read its bytes once and
    open them in memory, no temp file on disk."""
    with zipfile.ZipFile(archive_path) as outer:
        return zipfile.ZipFile(io.BytesIO(outer.read(member)))


def _strip_county_suffix(name: str) -> str:
    name = name.upper().strip()
    for suffix in (" COUNTY", " CNTY", " PARISH"):
        name = name.removesuffix(suffix)
    return name.strip()


def load_zip_to_county(archive_path: Path) -> dict[str, str]:
    """ZIP5 -> CA county name (as spelled in the Census file -- the
    authoritative source we fuzzy-match 26LOCCO.csv's county tokens
    against, rather than hand-listing expected typos), picking the county
    with the largest land-area overlap when a ZIP spans more than one
    (verified against the real file: ZCTA 89019 spans Inyo and San
    Bernardino)."""
    member = _dataset_member(archive_path, "census/tab20_zcta520_county20_natl.txt")
    best_area: dict[str, int] = {}
    result: dict[str, str] = {}
    with zipfile.ZipFile(archive_path) as z, z.open(member) as raw:
        f = io.TextIOWrapper(raw, encoding="utf-8-sig")
        cols = f.readline().strip().split("|")
        zip_i = cols.index("GEOID_ZCTA5_20")
        fips_i = cols.index("GEOID_COUNTY_20")
        name_i = cols.index("NAMELSAD_COUNTY_20")
        area_i = cols.index("AREALAND_PART")
        for line in f:
            parts = line.rstrip("\n").split("|")
            if len(parts) <= area_i:
                continue
            zip5 = parts[zip_i]
            fips = parts[fips_i]
            if not zip5 or not fips or not fips.startswith(CA_FIPS_PREFIX):
                continue
            try:
                area = int(parts[area_i] or 0)
            except ValueError:
                area = 0
            if area >= best_area.get(zip5, -1):
                best_area[zip5] = area
                result[zip5] = _strip_county_suffix(parts[name_i])
    return result


def load_county_to_locality(
    archive_path: Path, known_counties: set[str]
) -> tuple[dict[str, str], dict[str, str]]:
    """CA county name -> CMS locality number, from 26LOCCO.csv (a nested
    zip member inside cms_pfs/rvu26d-....zip, itself a member of the outer
    archive). Returns (mapping, fuzzy_corrections).

    The file lists a state name only on the first row of that state's
    block (blank on subsequent rows), and a locality's Counties column can
    use "," or "/" as a separator (both appear in the real file). Any CA
    county not explicitly listed falls back to locality 75 ("REST OF
    CALIFORNIA" / "REST OF STATE*") -- the file's own documented catch-all.

    County tokens that don't exactly match `known_counties` (the real,
    data-derived CA county list from the Census file, not a hand-maintained
    list) are fuzzy-matched via stdlib difflib instead of silently
    discarded -- CMS's own file has at least one real typo ("ORAGNGE" for
    "ORANGE" on the LA-area locality row) and there is no reason to assume
    it's the only one. The 0.85 cutoff was stress-tested against all 58
    real CA county names pairwise: zero false-positive collisions at that
    threshold, while still catching the known typo (similarity 0.92).
    Every fuzzy correction made is returned, not applied silently.
    """
    member = _dataset_member(archive_path, "cms_pfs/rvu26d-updated-08-26-2026.zip")
    with _open_nested_zip(archive_path, member) as z, z.open("26LOCCO.csv") as f:
        rows = list(csv.reader(io.TextIOWrapper(f, encoding="utf-8-sig")))

    mapping: dict[str, str] = {}
    fuzzy_corrections: dict[str, str] = {}
    current_state = ""
    for row in rows:
        if len(row) < 5:
            continue
        state_cell = row[2].strip().upper()
        if state_cell:
            current_state = state_cell
        if current_state != "CALIFORNIA":
            continue
        locality = row[1].strip()
        if not locality:
            continue
        for token in re.split(r"[,/]", row[4]):
            raw = _strip_county_suffix(token)
            if not raw or raw in ("ALL COUNTIES", "ALL OTHER COUNTIES"):
                continue
            if raw in known_counties:
                mapping[raw] = locality
                continue
            match = difflib.get_close_matches(raw, known_counties, n=1, cutoff=FUZZY_COUNTY_CUTOFF)
            if match:
                mapping[match[0]] = locality
                fuzzy_corrections[raw] = match[0]
            # else: genuinely unresolvable token -- left unmapped, falls
            # back to REST OF CALIFORNIA at the ZIP-resolution stage, the
            # same safety net as any other unlisted county.
    return mapping, fuzzy_corrections


def load_ca_gpci_by_locality(archive_path: Path) -> dict[str, dict[str, float]]:
    """CMS locality number -> {work, pe, mp} GPCI (per locality, not
    blended -- verified 29 distinct CA localities in the real file)."""
    member = _dataset_member(archive_path, "cms_pfs/rvu26d-updated-08-26-2026.zip")
    with _open_nested_zip(archive_path, member) as z, z.open("GPCI2026.csv") as f:
        rows = list(csv.reader(io.TextIOWrapper(f, encoding="utf-8-sig")))
    gpci: dict[str, dict[str, float]] = {}
    for row in rows:
        if len(row) > 6 and row[1].strip() == "CA":
            gpci[row[2].strip()] = {
                "work": float(row[4]),
                "pe": float(row[5]),
                "mp": float(row[6]),
            }
    return gpci


def resolve_locality(
    zip5: str | None, zip_to_county: dict[str, str], county_to_locality: dict[str, str]
) -> tuple[str, bool]:
    """Returns (locality, used_fallback). Falls back to the statewide
    "REST OF CALIFORNIA" locality when the ZIP or its county isn't found,
    rather than guessing -- tracked via the bool so fallback usage is
    visible in the output, not silently absorbed."""
    county = zip_to_county.get(zip5 or "")
    if county:
        locality = county_to_locality.get(county)
        if locality:
            return locality, False
    return REST_OF_CALIFORNIA_LOCALITY, True


def medicare_allowed(rvu: dict[str, float], gpci: dict[str, float], facility: bool) -> float:
    pe = rvu["pe_rvu_fac"] if facility else rvu["pe_rvu_nonfac"]
    return (rvu["work_rvu"] * gpci["work"] + pe * gpci["pe"] + rvu["mp_rvu"] * gpci["mp"]) * rvu[
        "conversion_factor"
    ]


# --------------------------------------------------------------------------
# Leave-one-out cohort median (O(n log n) sort once, O(1) per member)
# --------------------------------------------------------------------------


def _leave_one_out_medians(values: list[float]) -> list[float | None]:
    """For each position i in `values`, the median of every OTHER value in
    the list, in the same input order. A naive re-median-per-element is
    O(n^2 log n) for a cohort; this sorts once and looks up in O(1) per
    element, so grading the largest real cohort here (~980 providers on
    code 99214) costs one sort, not ~980 sorts.

    Why leave-one-out at all: including a provider's own rate in their own
    "peer" median biases small cohorts toward 1.0 (perfect agreement with
    yourself) -- exactly the cohorts where that bias matters most.
    """
    n = len(values)
    if n < 2:
        return [None] * n
    order = sorted(range(n), key=lambda i: values[i])
    sorted_vals = [values[i] for i in order]
    rank = [0] * n
    for pos, i in enumerate(order):
        rank[i] = pos

    remaining = n - 1
    mid = remaining // 2
    out: list[float | None] = [None] * n
    for i in range(n):
        r = rank[i]
        if remaining % 2 == 1:
            k = mid
            idx = k if k < r else k + 1
            out[i] = sorted_vals[idx]
        else:
            k1, k2 = mid - 1, mid
            idx1 = k1 if k1 < r else k1 + 1
            idx2 = k2 if k2 < r else k2 + 1
            out[i] = (sorted_vals[idx1] + sorted_vals[idx2]) / 2.0
    return out


# --------------------------------------------------------------------------
# Row-level reference ratio
# --------------------------------------------------------------------------


def compute_reference_ratios(rows: list[dict[str, Any]]) -> None:
    """Mutates each row in place, adding 'reference_ratio', 'n_specialty',
    'n_code_only', 'tier'. Rows without a 'medicare_ratio' (no PFS match)
    are left untouched -- they have no signal to blend and are excluded
    from the provider-level basket entirely, not defaulted to 1.0."""
    priceable = [r for r in rows if r.get("medicare_ratio") is not None]

    by_code: defaultdict[str, list[dict]] = defaultdict(list)
    by_spec_code: defaultdict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in priceable:
        by_code[r["billing_code"]].append(r)
        by_spec_code[(r["specialty"], r["billing_code"])].append(r)

    for group in by_code.values():
        loo = _leave_one_out_medians([r["medicare_ratio"] for r in group])
        for r, v in zip(group, loo):
            r["_peer_code_only"] = v
            r["n_code_only"] = len(group) - 1

    for group in by_spec_code.values():
        loo = _leave_one_out_medians([r["medicare_ratio"] for r in group])
        for r, v in zip(group, loo):
            r["_peer_specialty"] = v
            r["n_specialty"] = len(group) - 1

    for r in priceable:
        n_a = r.get("n_specialty", 0)
        n_b = r.get("n_code_only", 0)
        peer_a = r.get("_peer_specialty")
        peer_b = r.get("_peer_code_only")
        mr = r["medicare_ratio"]

        z_a = n_a / (n_a + K_A) if n_a else 0.0
        z_b = n_b / (n_b + K_B) if n_b else 0.0

        inner = (z_b * peer_b + (1 - z_b) * mr) if peer_b is not None else mr
        ref = (z_a * peer_a + (1 - z_a) * inner) if peer_a is not None else inner

        r["reference_ratio"] = ref
        if n_a >= K_A:
            r["tier"] = "A_specialty_code"
        elif n_b >= K_B:
            r["tier"] = "B_code_only"
        else:
            r["tier"] = "C_medicare_only"


# --------------------------------------------------------------------------
# Row loading + per-row Medicare ratio
# --------------------------------------------------------------------------


def _read_c6_rows(c6_path: Path) -> list[dict[str, Any]]:
    wb = openpyxl.load_workbook(c6_path, read_only=True)
    ws = wb["Curated Rates"]
    rows_iter = ws.iter_rows(values_only=True)
    header = [str(h) for h in next(rows_iter)]
    out = []
    for values in rows_iter:
        row = dict(zip(header, values))
        try:
            rate = float(row.get("Rate") or 0)
        except (TypeError, ValueError):
            continue
        out.append(
            {
                "npi": str(row.get("NPI") or ""),
                "tin": str(row.get("TIN") or ""),
                "address": str(row.get("Address") or ""),
                "billing_code": str(row.get("Billing Code") or ""),
                "specialty": str(row.get("Specialty") or ""),
                "rate": rate,
                "billing_class": str(row.get("Billing_Class") or ""),
            }
        )
    return out


def attach_medicare_ratios(
    rows: list[dict[str, Any]],
    pfs_table: dict[str, dict[str, float]],
    zip_to_county: dict[str, str],
    county_to_locality: dict[str, str],
    gpci_by_locality: dict[str, dict[str, float]],
) -> dict[str, int]:
    """Mutates rows in place: adds 'medicare_ratio' (or leaves it unset when
    the code isn't PFS-priced) and 'locality_fallback'. Caches
    medicare_allowed per (code, locality, facility) -- bounded by
    #codes x #localities (~217 x 29 here), not by row count, so repeating
    the same code/locality combination across many rows costs one lookup."""
    cache: dict[tuple[str, str, bool], float] = {}
    counts = {"rows": 0, "pfs_matched": 0, "locality_fallback": 0}

    for r in rows:
        counts["rows"] += 1
        zip5 = extract_zip5(r["address"])
        locality, used_fallback = resolve_locality(zip5, zip_to_county, county_to_locality)
        r["locality"] = locality
        r["locality_fallback"] = used_fallback
        if used_fallback:
            counts["locality_fallback"] += 1

        code = r["billing_code"]
        rvu = pfs_table.get(code)
        if rvu is None:
            r["medicare_ratio"] = None
            continue
        facility = r["billing_class"] == "institutional"
        key = (code, locality, facility)
        if key not in cache:
            gpci = gpci_by_locality.get(locality) or gpci_by_locality.get(REST_OF_CALIFORNIA_LOCALITY)
            cache[key] = medicare_allowed(rvu, gpci, facility)
        allowed = cache[key]
        r["medicare_ratio"] = (r["rate"] / allowed) if allowed > 0 else None
        if r["medicare_ratio"] is not None:
            counts["pfs_matched"] += 1
    return counts


# --------------------------------------------------------------------------
# Provider-level aggregation
# --------------------------------------------------------------------------


def aggregate_providers(
    rows: list[dict[str, Any]], proc_weights: dict[str, float]
) -> tuple[list[dict[str, Any]], float]:
    """Returns (provider_rows, k_provider) -- k_provider is surfaced so the
    Methodology sheet can report the actual shrinkage constant used, not
    just that shrinkage happened."""
    by_npi: defaultdict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_npi[r["npi"]].append(r)

    # HiLabs weights are raw volumes (median ~5.6M, max ~529M). A code HiLabs did not weight gets the
    # median weight, not 1.0: on the raw scale 1.0 is ~0, which zeroed credibility and pinned 109
    # providers (raw ratios 0.71x-31x) to exactly 1.00.
    positive = [w for w in proc_weights.values() if w and w > 0]
    default_weight = median(positive) if positive else DEFAULT_CODE_WEIGHT

    all_weights: list[float] = []
    provider_rows: list[dict[str, Any]] = []
    for npi, npi_rows in by_npi.items():
        priced = [r for r in npi_rows if r.get("reference_ratio") is not None]
        weight_sum = 0.0
        weighted_sum = 0.0
        tier_weight: defaultdict[str, float] = defaultdict(float)
        for r in priced:
            w = proc_weights.get(r["billing_code"]) or default_weight
            weight_sum += w
            weighted_sum += w * r["reference_ratio"]
            tier_weight[r["tier"]] += w
        ppi_raw = (weighted_sum / weight_sum) if weight_sum > 0 else None
        if weight_sum > 0:
            all_weights.append(weight_sum)

        specialties = [r["specialty"] for r in npi_rows if r["specialty"]]
        specialty = max(set(specialties), key=specialties.count) if specialties else ""
        distinct_codes_billed = {r["billing_code"] for r in npi_rows}

        provider_rows.append(
            {
                "npi": npi,
                "tins": ";".join(sorted({r["tin"] for r in npi_rows if r["tin"]})),
                "specialty": specialty,
                "codes_billed": len(distinct_codes_billed),
                "codes_priced": len(priced),
                "effective_basket_pct": round(100 * len(priced) / len(npi_rows), 1) if npi_rows else 0.0,
                "basket_weight": round(weight_sum, 2),
                "ppi_raw": round(ppi_raw, 4) if ppi_raw is not None else None,
                "tier_A_weight_pct": round(100 * tier_weight["A_specialty_code"] / weight_sum, 1) if weight_sum else 0.0,
                "tier_B_weight_pct": round(100 * tier_weight["B_code_only"] / weight_sum, 1) if weight_sum else 0.0,
                "tier_C_weight_pct": round(100 * tier_weight["C_medicare_only"] / weight_sum, 1) if weight_sum else 0.0,
                "_distinct_codes": distinct_codes_billed,
            }
        )

    k_provider = median(all_weights) if all_weights else 1.0
    for p in provider_rows:
        w = p["basket_weight"]
        if p["ppi_raw"] is None or w <= 0:
            p["z_credibility"] = 0.0
            p["ppi_credible"] = None  # no priced code = no evidence; never scored as average
        else:
            z = w / (w + k_provider)
            p["z_credibility"] = round(z, 3)
            p["ppi_credible"] = round(z * p["ppi_raw"] + (1 - z) * 1.0, 4)

    # Breadth: self-contained -- codes this provider prices / codes ANY
    # provider sharing their (modal) specialty prices in this dataset. No
    # cross-taxonomy join to HiLabs' SPEC_CD is attempted here: the C6
    # "Specialty" field comes from NUCC/CMS DAC, a different taxonomy than
    # HiLabs' Spec-Proc Weights sheet, and no verified crosswalk between
    # them exists in this dataset -- inventing one would be exactly the
    # kind of unverified mapping this build was told not to introduce.
    codes_by_specialty: defaultdict[str, set[str]] = defaultdict(set)
    for p in provider_rows:
        codes_by_specialty[p["specialty"]] |= p["_distinct_codes"]
    for p in provider_rows:
        universe = codes_by_specialty.get(p["specialty"]) or set()
        p["breadth_pct"] = round(100 * len(p["_distinct_codes"]) / len(universe), 1) if universe else 0.0
        del p["_distinct_codes"]

    scored = [p for p in provider_rows if p["ppi_credible"] is not None]
    ppi_values = sorted(p["ppi_credible"] for p in scored)
    breadth_values = sorted(p["breadth_pct"] for p in scored)
    ppi_median = ppi_values[len(ppi_values) // 2] if ppi_values else 1.0
    breadth_median = breadth_values[len(breadth_values) // 2] if breadth_values else 0.0

    for p in provider_rows:
        if p["ppi_credible"] is None:
            p["quadrant"] = "Insufficient data"
            continue
        low_price = p["ppi_credible"] <= ppi_median
        high_breadth = p["breadth_pct"] >= breadth_median
        if low_price and high_breadth:
            p["quadrant"] = "Broad Network Value"
        elif low_price and not high_breadth:
            p["quadrant"] = "Preferred Niche"
        elif not low_price and high_breadth:
            p["quadrant"] = "High-Cost Broad Scope"
        else:
            p["quadrant"] = "Niche Watchlist"

    provider_rows.sort(key=lambda p: (p["ppi_credible"] is None, p["ppi_credible"] or 0.0))
    return provider_rows, k_provider


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------


def run_c7(cfg: Config, c6_path: Path | None = None, output_path: Path | None = None) -> StageResult:
    started_at = time.monotonic()
    if c6_path is None:
        c6_path = cfg.data_dir / "out" / "final_provider_rates.xlsx"
    if output_path is None:
        out_path = cfg.data_dir / "out" / "c7_cost_effectiveness.xlsx"
    else:
        out_path = Path(output_path)
        if not out_path.is_absolute():
            out_path = cfg.root / out_path

    # Everything below reads from INSIDE cfg.archive (the one zip the README
    # asks the user to drop in data/) -- same convention c1-c6 use, not a
    # separately-extracted directory on disk. See _dataset_member /
    # _open_nested_zip.
    pfs_member = _dataset_member(cfg.archive, "cms_pfs/rvu26d-updated-08-26-2026.zip")
    benchmark_member = _dataset_member(
        cfg.archive, "hilabs/Rate Benchmarking Individual Weights_Hackathon.xlsx"
    )
    with zipfile.ZipFile(cfg.archive) as outer:
        pfs_bytes = outer.read(pfs_member)
        benchmark_bytes = outer.read(benchmark_member)

    pfs_table = load_pfs_table(io.BytesIO(pfs_bytes))
    benchmark = load_benchmark(io.BytesIO(benchmark_bytes))
    proc_weights = benchmark["proc_weights"]
    zip_to_county = load_zip_to_county(cfg.archive)
    county_to_locality, fuzzy_corrections = load_county_to_locality(
        cfg.archive, known_counties=set(zip_to_county.values())
    )
    gpci_by_locality = load_ca_gpci_by_locality(cfg.archive)

    rows = _read_c6_rows(c6_path)
    row_counts = attach_medicare_ratios(rows, pfs_table, zip_to_county, county_to_locality, gpci_by_locality)
    compute_reference_ratios(rows)
    providers, k_provider = aggregate_providers(rows, proc_weights)

    cfg.stage_dir("c7").mkdir(parents=True, exist_ok=True)
    detail_path = cfg.stage_dir("c7") / "c7_code_detail.csv"
    with detail_path.open("w", newline="", encoding="utf-8") as f:
        fields = ["npi", "tin", "billing_code", "specialty", "rate", "locality", "locality_fallback",
                   "medicare_ratio", "n_specialty", "n_code_only", "tier", "reference_ratio"]
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({**r, "medicare_ratio": r.get("medicare_ratio"), "reference_ratio": r.get("reference_ratio")})

    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Provider Scores"
    headers = ["npi", "tins", "specialty", "codes_billed", "codes_priced", "effective_basket_pct",
               "basket_weight", "ppi_raw", "z_credibility", "ppi_credible",
               "tier_A_weight_pct", "tier_B_weight_pct", "tier_C_weight_pct", "breadth_pct", "quadrant"]
    ws.append(headers)
    for p in providers:
        ws.append([p.get(h) for h in headers])
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{ws.max_row}"
    for c in ws[1]:
        c.font = Font(bold=True)

    dq = wb.create_sheet("Methodology")
    dq.append(["Metric", "Value"])
    dq.append(["C6 input rows", row_counts["rows"]])
    dq.append(["Rows matched to CMS PFS", row_counts["pfs_matched"]])
    dq.append(["Rows resolved to REST_OF_CALIFORNIA locality (fallback)", row_counts["locality_fallback"]])
    dq.append(["Distinct providers (NPI)", len(providers)])
    dq.append(["K_A (specialty+code half-credibility)", K_A])
    dq.append(["K_B (code-only half-credibility)", K_B])
    dq.append(["K_provider (median basket weight, provider-level shrinkage)", round(k_provider, 2)])
    dq.append(["County names fuzzy-matched in 26LOCCO.csv (not exact)", len(fuzzy_corrections)])
    for raw, matched in sorted(fuzzy_corrections.items()):
        dq.append([f"  fuzzy match: {raw!r}", f"-> {matched!r}"])
    quadrant_counts = Counter(p["quadrant"] for p in providers)
    for q, c in quadrant_counts.items():
        dq.append([f"quadrant: {q}", c])
    for c in dq[1]:
        c.font = Font(bold=True)
    wb.save(out_path)

    manifest_path = cfg.stage_dir("c7") / "_manifest.json"
    write_manifest(
        manifest_path,
        stage="c7",
        config_path=cfg.root / "config.yaml",
        sources=[{"path": str(c6_path)}, {"path": str(cfg.archive)}],
        counts={"providers": len(providers), "fuzzy_county_matches": len(fuzzy_corrections), **row_counts},
        started_at=started_at,
    )

    print(f"C7: rows={row_counts['rows']} pfs_matched={row_counts['pfs_matched']} "
          f"locality_fallback={row_counts['locality_fallback']} providers={len(providers)}")
    print(f"C7: outputs={out_path}, {detail_path}")
    return StageResult("c7", {"providers": len(providers), **row_counts}, (out_path, detail_path, manifest_path))

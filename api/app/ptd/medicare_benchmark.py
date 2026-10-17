"""Original C3 metric: negotiated rate as a % of the CMS Medicare allowable.

Internal outlier detection (grading.py) can only ever ask "is this rate
unusual compared to other rates in this same file?" -- it has no way to
tell if the *whole file* is priced oddly high or low, because it has no
outside reference point. The CMS Physician Fee Schedule (already provided
in data/.../cms_pfs/, unused until now) gives one: Medicare's allowed
amount per code is a government-published, payer-independent anchor, and
"% of Medicare" is the actual unit contracting teams negotiate and compare
rates in -- not a metric invented for this pipeline.

Limitation, stated plainly: this only covers CPT/HCPCS professional codes
(institutional claims mostly use revenue/DRG codes, which the PFS doesn't
price), and uses one blended California GPCI rather than resolving each
provider's exact locality (that needs an NPI -> address -> locality join,
which is C5's job, not C3's). The metric reports its own coverage % so
this limitation is visible, not hidden.
"""

from __future__ import annotations

import csv
import io
import zipfile
from pathlib import Path

# 2026 PFS file: header text rows precede the real header; this is the
# header row index, verified against the actual file layout.
_HEADER_ROW = 9
_COL_CODE = 0
_COL_STATUS = 3
_COL_WORK_RVU = 5
_COL_PE_RVU_NONFAC = 6
_COL_PE_RVU_FAC = 8
_COL_MP_RVU = 10
_COL_CONVERSION_FACTOR = 25

# Status codes CMS marks as actively priced/payable under the PFS.
_PAYABLE_STATUS = {"A", "R", "T"}


def load_pfs_table(zip_path: Path) -> dict[str, dict[str, float]]:
    """code -> {work_rvu, pe_rvu_nonfac, pe_rvu_fac, mp_rvu, conversion_factor}."""
    table: dict[str, dict[str, float]] = {}
    with zipfile.ZipFile(zip_path) as z:
        with z.open("PPRRVU2026_Oct_nonQPP.csv") as f:
            rows = list(csv.reader(io.TextIOWrapper(f, encoding="utf-8-sig")))

    for row in rows[_HEADER_ROW + 1 :]:
        if len(row) <= _COL_CONVERSION_FACTOR:
            continue
        if row[_COL_STATUS] not in _PAYABLE_STATUS:
            continue
        try:
            table[row[_COL_CODE]] = {
                "work_rvu": float(row[_COL_WORK_RVU]),
                "pe_rvu_nonfac": float(row[_COL_PE_RVU_NONFAC]),
                "pe_rvu_fac": float(row[_COL_PE_RVU_FAC]),
                "mp_rvu": float(row[_COL_MP_RVU]),
                "conversion_factor": float(row[_COL_CONVERSION_FACTOR]),
            }
        except ValueError:
            continue  # blank/non-numeric row (header fragments, etc.)
    return table


def california_blended_gpci(zip_path: Path) -> dict[str, float]:
    """Simple mean of work/PE/MP GPCI across all California localities.

    A real per-provider calculation would resolve each NPI's practice
    locality (26LOCCO.csv + the provider's ZIP) -- out of scope for a
    file-level quality score. A statewide blend is a stated, bounded
    approximation: good enough to tell "roughly in line with Medicare"
    from "wildly off," not precise enough for an actual reimbursement
    calculation.
    """
    with zipfile.ZipFile(zip_path) as z:
        with z.open("GPCI2026.csv") as f:
            rows = list(csv.reader(io.TextIOWrapper(f, encoding="utf-8-sig")))

    ca_rows = [r for r in rows if len(r) > 1 and r[1] == "CA"]
    work = [float(r[4]) for r in ca_rows]
    pe = [float(r[5]) for r in ca_rows]
    mp = [float(r[6]) for r in ca_rows]
    return {
        "work": sum(work) / len(work),
        "pe": sum(pe) / len(pe),
        "mp": sum(mp) / len(mp),
    }


def build_medicare_lookup(
    pfs_table: dict[str, dict[str, float]],
    gpci: dict[str, float],
    *,
    facility: bool = False,
) -> dict[str, float]:
    """code -> CA-blended Medicare allowed amount, precomputed once."""
    pe_key = "pe_rvu_fac" if facility else "pe_rvu_nonfac"
    lookup = {}
    for code, rvu in pfs_table.items():
        allowed = (
            rvu["work_rvu"] * gpci["work"]
            + rvu[pe_key] * gpci["pe"]
            + rvu["mp_rvu"] * gpci["mp"]
        ) * rvu["conversion_factor"]
        if allowed > 0:
            lookup[code] = allowed
    return lookup

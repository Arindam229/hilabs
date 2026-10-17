"""C3 entry point: grade every rate file C2 identified as in-scope.

Reads the "PPO rate files" sheet C2 produces (one row per unique rate
file), not the plan-level sheet -- grading is per-file, not per-plan.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import openpyxl

from .grading import grade_file
from .medicare_benchmark import build_medicare_lookup, california_blended_gpci, load_pfs_table


def unique_rate_files_from_c2(c2_xlsx: Path, sheet: str = "PPO rate files") -> list[str]:
    wb = openpyxl.load_workbook(c2_xlsx, read_only=True)
    ws = wb[sheet]
    rows = list(ws.iter_rows(values_only=True))
    header = [str(h) for h in rows[0]]
    url_col = header.index("Rate file URL")
    return [row[url_col] for row in rows[1:] if row[url_col]]


def local_in_network_path(rate_file_url: str, in_network_dir: Path) -> Path:
    return in_network_dir / rate_file_url.rsplit("/", 1)[-1]


def grade_c2_rate_files(
    c2_xlsx: Path,
    in_network_dir: Path,
    *,
    pfs_zip: Path | None = None,
) -> list[dict[str, Any]]:
    """Grade every file C2 says is in scope. Missing local files are
    reported, not skipped silently -- a file we were supposed to grade
    and can't find is itself a completeness problem worth surfacing."""
    medicare_lookup_nonfac = medicare_lookup_fac = None
    if pfs_zip is not None:
        pfs_table = load_pfs_table(pfs_zip)
        gpci = california_blended_gpci(pfs_zip)
        medicare_lookup_nonfac = build_medicare_lookup(pfs_table, gpci, facility=False)
        medicare_lookup_fac = build_medicare_lookup(pfs_table, gpci, facility=True)

    results = []
    for url in unique_rate_files_from_c2(c2_xlsx):
        path = local_in_network_path(url, in_network_dir)
        if not path.exists():
            results.append({"file": path.name, "rate_file_url": url, "error": "file not found locally"})
            continue
        metrics = grade_file(
            path,
            medicare_lookup_nonfac=medicare_lookup_nonfac,
            medicare_lookup_fac=medicare_lookup_fac,
        )
        metrics["rate_file_url"] = url
        results.append(metrics)
    return results

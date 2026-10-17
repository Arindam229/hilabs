"""C1: parse Centene index files into one plan -> rate-file table.

Pure functions. One row per (plan, rate file); exact-duplicate rows collapsed.
Network-type (PPO/HMO/...) classification is C2's job, not this module's.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_CA_RATE_FILE_RE = re.compile(r"-ca_in-network\.json$", re.IGNORECASE)

_BRAND_TOKENS = {
    "ambetter": "Ambetter",
    "fidelis": "Fidelis",
    "qualchoice": "QualChoice",
    "healthnet": "Health Net",
}

TABLE_COLUMNS = (
    "brand",
    "plan_name",
    "plan_id",
    "plan_id_type",
    "market_type",
    "issuer_name",
    "rate_file_url",
    "source_index_file",
)


def brand_from_filename(filename: str) -> str:
    lowered = filename.lower()
    for token, brand in _BRAND_TOKENS.items():
        if token in lowered:
            return brand
    return "Unknown"


def parse_index_file(path: Path) -> list[dict[str, Any]]:
    """One row per (plan, in-network rate file) found in a single index file."""
    data = json.loads(path.read_text(encoding="utf-8"))
    brand = brand_from_filename(path.name)
    rows: list[dict[str, Any]] = []

    for structure in data.get("reporting_structure", []):
        rate_file_urls = [
            f["location"] for f in structure.get("in_network_files", []) if f.get("location")
        ]
        for plan in structure.get("reporting_plans", []):
            for url in rate_file_urls:
                rows.append(
                    {
                        "brand": brand,
                        "plan_name": plan.get("plan_name", ""),
                        "plan_id": plan.get("plan_id", ""),
                        "plan_id_type": plan.get("plan_id_type", ""),
                        "market_type": plan.get("plan_market_type", ""),
                        "issuer_name": plan.get("issuer_name", ""),
                        "rate_file_url": url,
                        "source_index_file": path.name,
                    }
                )
    return rows


def build_c1_table(paths: list[Path]) -> list[dict[str, Any]]:
    """Parse every index file and drop exact-duplicate rows.

    "Duplicate" means every column matches (the same plan listed twice,
    e.g. once per redundant file reference). Many *different* plans sharing
    one rate_file_url is expected, not a duplicate, and is kept.
    """
    seen: set[tuple[Any, ...]] = set()
    table: list[dict[str, Any]] = []
    for path in paths:
        for row in parse_index_file(path):
            key = tuple(row[c] for c in TABLE_COLUMNS)
            if key in seen:
                continue
            seen.add(key)
            table.append(row)
    return table


def is_california_rate_file(rate_file_url: str) -> bool:
    """True for a California in-network file (PS scope, section 3).

    Centene encodes state in the rate-file filename for brands that are
    split per state (Ambetter: ambetter-<state>, Health Net: healthnet-ca /
    healthnet-or). Brands with one undifferentiated file (Fidelis, QualChoice)
    never match this and are correctly excluded: verified against this
    dataset, their HIOS plan IDs are entirely NY and AR respectively.
    """
    return bool(_CA_RATE_FILE_RE.search(rate_file_url))


def filter_group_market(table: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """PS scope (section 3) is commercial *group* market only, not individual."""
    return [row for row in table if row["market_type"] == "group"]


def filter_california(table: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in table if is_california_rate_file(row["rate_file_url"])]

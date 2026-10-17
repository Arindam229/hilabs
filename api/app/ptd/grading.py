"""C3: grade a PTD in-network file for quality and completeness.

Core metric logic (compute_metrics) is pure and takes an already-streamed
iterable of price rows -- testable without touching a file. grade_file()
is the only part that knows about ijson/disk, and does ONE streaming pass:
grading and extraction (C4) can later share this same pass instead of
reading a 700MB file twice.

Each metric maps to one trust question a contracting team actually has
about a rate (see the "quality dimension" table in the PR discussion):
completeness (code/provider coverage), validity ($0/outliers), usability
(rate types), consistency (duplicates), freshness (staleness).
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Iterator

import ijson

# CMS expects TiC files refreshed monthly; 60d = one missed cycle (warn),
# 180d = roughly half a year stale (critical). Thresholds, not laws of
# nature -- tune if the team has a different tolerance.
STALE_WARN_DAYS = 60
STALE_CRITICAL_DAYS = 180

# Per-code outlier detection needs enough samples to mean anything.
OUTLIER_MIN_SAMPLES = 5
OUTLIER_Z_THRESHOLD = 3.0  # robust (median/MAD) z-score on log(rate)


def read_header(path: Path) -> dict[str, Any]:
    """Top-level fields only (stops before the huge in_network array)."""
    header: dict[str, Any] = {}
    wanted = {"reporting_entity_name", "reporting_entity_type", "version", "last_updated_on"}
    with path.open("rb") as f:
        for prefix, event, value in ijson.parse(f):
            if prefix in wanted and event == "string":
                header[prefix] = value
            if prefix == "in_network" and event == "start_array":
                break
    return header


def iter_price_rows(path: Path) -> Iterator[dict[str, Any]]:
    """Stream one row per negotiated_prices entry across the whole file."""
    with path.open("rb") as f:
        for item in ijson.items(f, "in_network.item"):
            code = item.get("billing_code")
            code_type = item.get("billing_code_type")
            description = item.get("description")
            for negotiated_rate in item.get("negotiated_rates", []):
                provider_refs = tuple(negotiated_rate.get("provider_references", []))
                for price in negotiated_rate.get("negotiated_prices", []):
                    yield {
                        "billing_code": code,
                        "billing_code_type": code_type,
                        "description": description,
                        "negotiated_type": price.get("negotiated_type"),
                        # ijson yields Decimal for precision; float is plenty
                        # for a quality metric and avoids Decimal/float mixing.
                        "negotiated_rate": (
                            float(price["negotiated_rate"])
                            if price.get("negotiated_rate") is not None
                            else None
                        ),
                        "billing_class": price.get("billing_class"),
                        "service_code": tuple(price.get("service_code") or []),
                        "billing_code_modifier": tuple(price.get("billing_code_modifier") or []),
                        "setting": price.get("setting"),
                        # Institutional (e.g. DRG-severity) sub-classification -- two
                        # prices for the same code/provider with different
                        # additional_information are different billing scenarios,
                        # not a duplicate rate for the same thing.
                        "additional_information": price.get("additional_information"),
                        "provider_group_ids": provider_refs,
                    }


def _outlier_count(rates_by_code: dict[str, list[float]]) -> int:
    """Robust (median/MAD) z-score on log(rate), computed per billing code.

    Per-code because rate scale varies enormously by procedure -- a global
    threshold would flag normal MRI rates as outliers relative to office
    visits. MAD instead of std-dev so a handful of real outliers don't
    inflate the threshold and hide themselves.
    """
    count = 0
    for rates in rates_by_code.values():
        if len(rates) < OUTLIER_MIN_SAMPLES:
            continue
        logs = sorted(math.log(r) for r in rates)
        median = logs[len(logs) // 2]
        mad = sorted(abs(x - median) for x in logs)[len(logs) // 2] or 1e-9
        for x in logs:
            if abs(0.6745 * (x - median) / mad) > OUTLIER_Z_THRESHOLD:
                count += 1
    return count


def compute_metrics(
    rows: Iterable[dict[str, Any]],
    *,
    header: dict[str, Any] | None = None,
    expected_codes: set[str] | None = None,
    network_provider_group_count: int | None = None,
    medicare_lookup_nonfac: dict[str, float] | None = None,
    medicare_lookup_fac: dict[str, float] | None = None,
    as_of: date | None = None,
) -> dict[str, Any]:
    """Pure: no file I/O. `rows` is whatever iter_price_rows() yields.

    medicare_lookup_* are precomputed code -> CA Medicare-allowed-amount
    dicts (see medicare_benchmark.build_medicare_lookup) -- pass None to
    skip that metric entirely (e.g. in tests that don't need it).
    """
    header = header or {}
    as_of = as_of or date.today()

    seen_codes: set[str] = set()
    provider_group_ids: set[Any] = set()
    negotiated_type_counts: Counter[str] = Counter()
    billing_class_counts: Counter[str] = Counter()
    rates_by_code: defaultdict[str, list[float]] = defaultdict(list)
    dup_key_counts: Counter[tuple] = Counter()
    descriptions_by_code: defaultdict[str, set[str]] = defaultdict(set)
    medicare_ratios: list[float] = []
    total = 0
    zero_or_negative = 0

    for row in rows:
        total += 1
        code = row["billing_code"]
        rate = row["negotiated_rate"]
        seen_codes.add(code)
        provider_group_ids.update(row["provider_group_ids"])
        negotiated_type_counts[row["negotiated_type"]] += 1
        billing_class_counts[row["billing_class"]] += 1
        if row.get("description"):
            descriptions_by_code[code].add(row["description"])
        if rate is not None and rate <= 0:
            zero_or_negative += 1
        elif rate is not None:
            rates_by_code[code].append(rate)
            lookup = (
                medicare_lookup_fac
                if row["billing_class"] == "institutional"
                else medicare_lookup_nonfac
            )
            if lookup and code in lookup:
                medicare_ratios.append(rate / lookup[code])
        dup_key_counts[
            (
                code,
                row["provider_group_ids"],
                row["service_code"],
                row["billing_class"],
                row["billing_code_modifier"],
                row["setting"],
                row["additional_information"],
            )
        ] += 1

    if total == 0:
        return {"price_count": 0, "quality_score": 0.0, "note": "empty or unreadable file"}

    duplicate_groups = [c for c in dup_key_counts.values() if c > 1]
    staleness_days = None
    if header.get("last_updated_on"):
        staleness_days = (as_of - datetime.strptime(header["last_updated_on"], "%Y-%m-%d").date()).days

    inconsistent_codes = [c for c, descs in descriptions_by_code.items() if len(descs) > 1]
    medicare_ratios.sort()
    medicare_metrics = None
    if medicare_ratios:
        n = len(medicare_ratios)
        medicare_metrics = {
            "coverage_pct": n / total,
            "median_pct_of_medicare": round(100 * medicare_ratios[n // 2], 1),
            "below_50pct_of_medicare_pct": sum(1 for r in medicare_ratios if r < 0.5) / n,
            "above_400pct_of_medicare_pct": sum(1 for r in medicare_ratios if r > 4.0) / n,
        }

    metrics: dict[str, Any] = {
        "schema_version": header.get("version"),
        "last_updated_on": header.get("last_updated_on"),
        "staleness_days": staleness_days,
        "price_count": total,
        "distinct_codes": len(seen_codes),
        "distinct_provider_groups": len(provider_group_ids),
        "code_coverage": (
            len(seen_codes & expected_codes) / len(expected_codes) if expected_codes else None
        ),
        "provider_coverage": (
            len(provider_group_ids) / network_provider_group_count
            if network_provider_group_count
            else None
        ),
        "zero_or_negative_rate_pct": zero_or_negative / total,
        "outlier_rate_pct": _outlier_count(rates_by_code) / total,
        "negotiated_type_pct": {k: v / total for k, v in negotiated_type_counts.items()},
        "billing_class_pct": {k: v / total for k, v in billing_class_counts.items()},
        "duplicate_group_count": len(duplicate_groups),
        "duplicate_entry_pct": sum(c - 1 for c in duplicate_groups) / total,
        # Original metric 1: internal self-consistency. The same billing_code
        # should mean the same service everywhere in one file; if it maps to
        # more than one description, the file (or our join of it) is suspect.
        "inconsistent_code_description_count": len(inconsistent_codes),
        # Original metric 2: external grounding against CMS Medicare PFS --
        # see medicare_benchmark.py docstring for why this exists and its
        # stated limits (CPT/HCPCS only, CA-blended GPCI, not per-provider).
        "medicare_benchmark": medicare_metrics,
    }
    metrics["quality_score"] = _composite_score(metrics)
    return metrics


# Weights: duplicates/outliers/rate-type usability weigh more than raw
# coverage, because they threaten the *correctness* of a rate someone
# actually extracts (C4), not just the file's breadth. Stated explicitly
# so they're easy to challenge/retune -- the raw metrics above matter more
# than this single number.
_WEIGHTS = {
    "code_coverage": 0.20,
    "provider_coverage": 0.20,
    "cleanliness": 0.20,  # 1 - ($0/neg + outlier rate)
    "rate_type_usability": 0.15,  # share of prices that are negotiated_type == "negotiated"
    "duplicate_cleanliness": 0.15,  # 1 - duplicate_entry_pct
    "freshness": 0.10,
}


def _composite_score(m: dict[str, Any]) -> float:
    parts: dict[str, float] = {}
    if m["code_coverage"] is not None:
        parts["code_coverage"] = m["code_coverage"]
    if m["provider_coverage"] is not None:
        parts["provider_coverage"] = m["provider_coverage"]
    parts["cleanliness"] = max(0.0, 1 - m["zero_or_negative_rate_pct"] - m["outlier_rate_pct"])
    parts["rate_type_usability"] = m["negotiated_type_pct"].get("negotiated", 0.0)
    parts["duplicate_cleanliness"] = max(0.0, 1 - m["duplicate_entry_pct"])
    if m["staleness_days"] is None:
        parts["freshness"] = 0.5  # unknown, neither rewarded nor punished
    else:
        parts["freshness"] = max(
            0.0, 1 - min(1.0, m["staleness_days"] / STALE_CRITICAL_DAYS)
        )

    used_weight = sum(_WEIGHTS[k] for k in parts)
    if used_weight == 0:
        return 0.0
    score = sum(_WEIGHTS[k] * v for k, v in parts.items()) / used_weight
    return round(100 * score, 1)


def grade_file(
    path: Path,
    *,
    expected_codes: set[str] | None = None,
    network_provider_group_count: int | None = None,
    medicare_lookup_nonfac: dict[str, float] | None = None,
    medicare_lookup_fac: dict[str, float] | None = None,
) -> dict[str, Any]:
    header = read_header(path)
    metrics = compute_metrics(
        iter_price_rows(path),
        header=header,
        expected_codes=expected_codes,
        network_provider_group_count=network_provider_group_count,
        medicare_lookup_nonfac=medicare_lookup_nonfac,
        medicare_lookup_fac=medicare_lookup_fac,
    )
    metrics["file"] = path.name
    return metrics

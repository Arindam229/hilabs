"""Structural C3 diagnostics: item repetition, provider depth, description
consistency, pointer hygiene, unrecognized codes, weighted code coverage.
All computed in the same streaming pass grade_member already does -- no
second read."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from pipeline.stages.c3_quality import grade_member

MEMBER = "centene/in_network/test.json"


def _item(
    code: str,
    rate: object = 100,
    *,
    provider_refs=(7,),
    description: str | None = None,
    billing_code_type: str | None = None,
    expiration_date: str | None = "9999-12-31",
):
    price: dict = {
        "negotiated_type": "negotiated",
        "negotiated_rate": rate,
        "billing_class": "professional",
        "setting": "office",
    }
    if expiration_date is not None:
        price["expiration_date"] = expiration_date
    item: dict = {
        "billing_code": code,
        "negotiated_rates": [{"provider_references": list(provider_refs), "negotiated_prices": [price]}],
    }
    if description is not None:
        item["description"] = description
    if billing_code_type is not None:
        item["billing_code_type"] = billing_code_type
    return item


def _archive(path: Path, items: list[dict], declared_provider_groups: list[int] | None = None) -> str:
    # provider_references must precede in_network -- matches the real TiC
    # schema's actual key order (verified earlier against real files), and
    # _header()'s preamble scan relies on it, stopping the instant
    # in_network starts.
    payload: dict = {"version": "2.0.0", "last_updated_on": "2026-10-01"}
    if declared_provider_groups is not None:
        payload["provider_references"] = [
            {"provider_group_id": g, "provider_groups": []} for g in declared_provider_groups
        ]
    payload["in_network"] = items
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(MEMBER, json.dumps(payload))
    return MEMBER


# --------------------------------------------------------------------------
# #1 item repetition rate
# --------------------------------------------------------------------------


def test_item_repetition_rate_zero_when_every_code_is_unique(tmp_path: Path):
    archive = tmp_path / "source.zip"
    member = _archive(archive, [_item("A", provider_refs=(1,)), _item("B", provider_refs=(1,))],
                       declared_provider_groups=[1])
    result = grade_member(archive, member, "url", tmp_path / "db.sqlite")
    assert result["item_repetition_rate_pct"] == 0.0


def test_item_repetition_rate_and_worst_offender_tracked(tmp_path: Path):
    # code "A" appears as 3 separate items, "B" once -- 4 items, 2 distinct
    # codes -> (4-2)/4 = 50% repetition.
    archive = tmp_path / "source.zip"
    items = [_item("A", provider_refs=(1,)), _item("A", rate=200, provider_refs=(1,)),
             _item("A", rate=300, provider_refs=(1,)), _item("B", provider_refs=(1,))]
    member = _archive(archive, items, declared_provider_groups=[1])
    result = grade_member(archive, member, "url", tmp_path / "db.sqlite")
    assert result["item_repetition_rate_pct"] == 50.0
    assert result["most_repeated_code"] == "A"
    assert result["most_repeated_code_count"] == 3


# --------------------------------------------------------------------------
# #2 provider depth per code
# --------------------------------------------------------------------------


def test_avg_providers_per_code(tmp_path: Path):
    archive = tmp_path / "source.zip"
    items = [
        _item("A", provider_refs=(1, 2, 3)),  # 3 distinct providers for A
        _item("B", provider_refs=(1,)),  # 1 distinct provider for B
    ]
    member = _archive(archive, items, declared_provider_groups=[1, 2, 3])
    result = grade_member(archive, member, "url", tmp_path / "db.sqlite")
    # (3 + 1) / 2 codes = 2.0 average
    assert result["avg_providers_per_code"] == 2.0


# --------------------------------------------------------------------------
# #3 code-description consistency
# --------------------------------------------------------------------------


def test_consistent_description_not_flagged(tmp_path: Path):
    archive = tmp_path / "source.zip"
    items = [_item("A", provider_refs=(1,), description="Office visit"),
             _item("A", rate=150, provider_refs=(1,), description="Office visit")]
    member = _archive(archive, items, declared_provider_groups=[1])
    result = grade_member(archive, member, "url", tmp_path / "db.sqlite")
    assert result["inconsistent_description_codes"] == 0


def test_inconsistent_description_flagged(tmp_path: Path):
    archive = tmp_path / "source.zip"
    items = [_item("A", provider_refs=(1,), description="Office visit"),
             _item("A", rate=150, provider_refs=(1,), description="MRI scan")]
    member = _archive(archive, items, declared_provider_groups=[1])
    result = grade_member(archive, member, "url", tmp_path / "db.sqlite")
    assert result["inconsistent_description_codes"] == 1
    assert result["inconsistent_description_rate_pct"] == 100.0


# --------------------------------------------------------------------------
# #4 pointer hygiene / referential integrity
# --------------------------------------------------------------------------


def test_pointer_integrity_perfect_when_declared_matches_referenced(tmp_path: Path):
    archive = tmp_path / "source.zip"
    member = _archive(archive, [_item("A", provider_refs=(1, 2))], declared_provider_groups=[1, 2])
    result = grade_member(archive, member, "url", tmp_path / "db.sqlite")
    assert result["orphan_provider_refs"] == 0
    assert result["ghost_provider_groups"] == 0
    assert result["pointer_integrity_pct"] == 100.0


def test_pointer_integrity_detects_orphan_reference(tmp_path: Path):
    # price references provider group 99, but it's never declared
    archive = tmp_path / "source.zip"
    member = _archive(archive, [_item("A", provider_refs=(99,))], declared_provider_groups=[1])
    result = grade_member(archive, member, "url", tmp_path / "db.sqlite")
    assert result["orphan_provider_refs"] == 1
    assert result["ghost_provider_groups"] == 1  # group 1 declared but never used
    assert result["pointer_integrity_pct"] < 100.0


# --------------------------------------------------------------------------
# --------------------------------------------------------------------------
# PS-named "code coverage", weighted by HiLabs' claims-volume importance
# (SPEC_PROC_WEIGHT) -- not just a flat is-it-present count.
# --------------------------------------------------------------------------


def test_code_coverage_weighted_by_importance_not_flat_count(tmp_path: Path):
    # file has code "A" (heavy weight) but not "B" (light weight) --
    # coverage should reflect that A matters far more than B, not just
    # "1 of 2 codes present = 50%".
    archive = tmp_path / "source.zip"
    member = _archive(archive, [_item("A", provider_refs=(1,))], declared_provider_groups=[1])
    result = grade_member(
        archive, member, "url", tmp_path / "db.sqlite", hilabs_weights={"A": 90.0, "B": 10.0}
    )
    # matched weight 90 / total weight 100 = 90%, not a flat 50%
    assert result["code_coverage_weighted_pct"] == 90.0


def test_code_coverage_weighted_full_when_everything_present(tmp_path: Path):
    archive = tmp_path / "source.zip"
    items = [_item("A", provider_refs=(1,)), _item("B", provider_refs=(1,))]
    member = _archive(archive, items, declared_provider_groups=[1])
    result = grade_member(
        archive, member, "url", tmp_path / "db.sqlite", hilabs_weights={"A": 90.0, "B": 10.0}
    )
    assert result["code_coverage_weighted_pct"] == 100.0


def test_code_coverage_weighted_none_without_reference_sheet(tmp_path: Path):
    archive = tmp_path / "source.zip"
    member = _archive(archive, [_item("A", provider_refs=(1,))], declared_provider_groups=[1])
    result = grade_member(archive, member, "url", tmp_path / "db.sqlite", hilabs_weights=None)
    assert result["code_coverage_weighted_pct"] is None


# --------------------------------------------------------------------------
# Expiration transparency: does each price carry a real validity period,
# not just the 9999-12-31 sentinel (confirmed 100% sentinel on the real file)?
# --------------------------------------------------------------------------


def test_expiration_transparency_zero_when_all_sentinel(tmp_path: Path):
    archive = tmp_path / "source.zip"
    items = [_item("A", provider_refs=(1,)), _item("B", provider_refs=(1,))]  # default sentinel
    member = _archive(archive, items, declared_provider_groups=[1])
    result = grade_member(archive, member, "url", tmp_path / "db.sqlite")
    assert result["expiration_transparency_pct"] == 0.0


def test_expiration_transparency_full_when_real_dates_given(tmp_path: Path):
    archive = tmp_path / "source.zip"
    items = [_item("A", provider_refs=(1,), expiration_date="2027-06-30")]
    member = _archive(archive, items, declared_provider_groups=[1])
    result = grade_member(archive, member, "url", tmp_path / "db.sqlite")
    assert result["expiration_transparency_pct"] == 100.0


def test_expiration_transparency_treats_missing_as_no_real_expiration(tmp_path: Path):
    archive = tmp_path / "source.zip"
    items = [_item("A", provider_refs=(1,), expiration_date=None)]  # field absent entirely
    member = _archive(archive, items, declared_provider_groups=[1])
    result = grade_member(archive, member, "url", tmp_path / "db.sqlite")
    assert result["expiration_transparency_pct"] == 0.0


# --------------------------------------------------------------------------
# Code-type collision: same billing_code under >1 billing_code_type --
# validates C4's own assumption that billing_code alone isn't always safe.
# --------------------------------------------------------------------------


def test_code_type_collision_none_when_each_code_has_one_type(tmp_path: Path):
    archive = tmp_path / "source.zip"
    items = [_item("A", provider_refs=(1,), billing_code_type="CPT"),
             _item("A", rate=150, provider_refs=(1,), billing_code_type="CPT")]
    member = _archive(archive, items, declared_provider_groups=[1])
    result = grade_member(archive, member, "url", tmp_path / "db.sqlite")
    assert result["code_type_collisions"] == 0
    assert result["code_type_collision_rate_pct"] == 0.0


def test_code_type_collision_detected_when_same_code_different_types(tmp_path: Path):
    archive = tmp_path / "source.zip"
    items = [_item("A", provider_refs=(1,), billing_code_type="CPT"),
             _item("A", rate=150, provider_refs=(1,), billing_code_type="RC")]
    member = _archive(archive, items, declared_provider_groups=[1])
    result = grade_member(archive, member, "url", tmp_path / "db.sqlite")
    assert result["code_type_collisions"] == 1
    assert result["code_type_collision_rate_pct"] == 100.0


# --------------------------------------------------------------------------
# Scalability: outlier-reservoir cohort count is capped, not unbounded.
# --------------------------------------------------------------------------


def test_outlier_cohort_cap_not_reached_under_normal_use(tmp_path: Path):
    archive = tmp_path / "source.zip"
    items = [_item("A", rate=r, provider_refs=(1,)) for r in [100, 110, 120, 130, 140, 150]]
    member = _archive(archive, items, declared_provider_groups=[1])
    result = grade_member(archive, member, "url", tmp_path / "db.sqlite", max_outlier_cohorts=50_000)
    assert result["outlier_cohort_cap_reached"] is False
    assert result["outlier_cohort_cap_skipped_prices"] == 0


def test_outlier_cohort_cap_bounds_memory_and_is_honestly_reported(tmp_path: Path):
    # 5 distinct codes -> 5 distinct (code, class, type) cohorts, but cap
    # the cap at 2 to force skipping -- proves the cap actually bounds
    # growth instead of just being a reported-but-unused number.
    archive = tmp_path / "source.zip"
    items = [_item(f"CODE{i}", rate=100 + i, provider_refs=(1,)) for i in range(5)]
    member = _archive(archive, items, declared_provider_groups=[1])
    result = grade_member(archive, member, "url", tmp_path / "db.sqlite", max_outlier_cohorts=2)
    assert result["distinct_outlier_cohorts"] == 2
    assert result["outlier_cohort_cap_reached"] is True
    assert result["outlier_cohort_cap_skipped_prices"] == 3  # the other 3 codes' prices

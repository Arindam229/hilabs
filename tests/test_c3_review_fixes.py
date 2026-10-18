"""Fixes applied after an external code review of c3_quality.py, verified
against real pipeline data before being implemented (see conversation):
Medicare matching restricted to professional claims with place-of-service-
based facility selection (Fix 1), coverage metrics recovering the real
CPT/HCPCS identity RC-typed prices carry in additional_information (Fix 4),
dollar-rate detection broadened beyond just "negotiated" type, and an
as_of-parameterized expired-rate metric."""

from __future__ import annotations

import json
import zipfile
from datetime import date
from pathlib import Path

from pipeline.stages.c3_quality import grade_member

MEMBER = "centene/in_network/test.json"


def _price(
    rate: object = 100,
    *,
    negotiated_type: str = "negotiated",
    billing_class: str = "professional",
    service_code: list[str] | None = None,
    expiration_date: str | None = "9999-12-31",
) -> dict:
    price: dict = {
        "negotiated_type": negotiated_type,
        "negotiated_rate": rate,
        "billing_class": billing_class,
        "setting": "office",
    }
    if service_code is not None:
        price["service_code"] = service_code
    if expiration_date is not None:
        price["expiration_date"] = expiration_date
    return price


def _item(
    code: str,
    prices: list[dict],
    *,
    provider_refs=(7,),
    billing_code_type: str | None = None,
    additional_information: str | None = None,
) -> dict:
    if additional_information is not None:
        for price in prices:
            price["additional_information"] = additional_information
    item: dict = {
        "billing_code": code,
        "negotiated_rates": [{"provider_references": list(provider_refs), "negotiated_prices": prices}],
    }
    if billing_code_type is not None:
        item["billing_code_type"] = billing_code_type
    return item


def _archive(path: Path, items: list[dict], declared_provider_groups: list[int] | None = None) -> str:
    payload: dict = {"version": "2.0.0", "last_updated_on": "2026-10-01"}
    if declared_provider_groups is not None:
        payload["provider_references"] = [
            {"provider_group_id": g, "provider_groups": []} for g in declared_provider_groups
        ]
    payload["in_network"] = items
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(MEMBER, json.dumps(payload))
    return MEMBER


MEDICARE_RATES = {"99213": (35.0, 40.0)}  # (non_facility, facility)


# --------------------------------------------------------------------------
# Fix 1: Medicare matching is professional-only, and picks the facility or
# non-facility PFS benchmark based on the price's own place-of-service
# (service_code), not billing_class.
# --------------------------------------------------------------------------


def test_medicare_match_skips_institutional_claims(tmp_path: Path):
    # Institutional billing is priced under OPPS/IPPS, not the physician fee
    # schedule -- comparing it to any PFS number is a category error, so it
    # must never count as matched at all.
    archive = tmp_path / "source.zip"
    member = _archive(
        archive, [_item("99213", [_price(billing_class="institutional")])], declared_provider_groups=[7]
    )
    result = grade_member(archive, member, "url", tmp_path / "db.sqlite", medicare_rates=MEDICARE_RATES)
    assert result["medicare_matched_rate_pct"] == 0.0


def test_medicare_match_uses_facility_benchmark_for_facility_pos(tmp_path: Path):
    # service_code "21" (inpatient hospital) is a facility POS -> compare
    # against the facility PFS rate (40.0), not non-facility (35.0).
    archive = tmp_path / "source.zip"
    member = _archive(
        archive,
        [_item("99213", [_price(rate=40.0, service_code=["21"])])],
        declared_provider_groups=[7],
    )
    result = grade_member(archive, member, "url", tmp_path / "db.sqlite", medicare_rates=MEDICARE_RATES)
    assert result["medicare_matched_rate_pct"] == 100.0
    assert result["medicare_out_of_band_pct"] == 0.0


def test_medicare_match_flags_out_of_band_against_correct_benchmark(tmp_path: Path):
    # Billed at 40.0 (the facility rate) while priced as non-facility (POS
    # "11", office) -- benchmark is 35.0, so ratio 40/35 is in-band; but
    # billed at 400 it's wildly out of band against the right (35.0) number.
    archive = tmp_path / "source.zip"
    member = _archive(
        archive,
        [_item("99213", [_price(rate=400.0, service_code=["11"])])],
        declared_provider_groups=[7],
    )
    result = grade_member(archive, member, "url", tmp_path / "db.sqlite", medicare_rates=MEDICARE_RATES)
    assert result["medicare_matched_rate_pct"] == 100.0
    assert result["medicare_out_of_band_pct"] == 100.0


# --------------------------------------------------------------------------
# Fix 4: coverage metrics use coverage_codes, which recovers the real
# CPT/HCPCS identity an RC (revenue code) price carries in
# additional_information -- verified on 74.9% of all prices in the real file.
# --------------------------------------------------------------------------


def test_rc_code_recovers_real_identity_from_additional_information(tmp_path: Path):
    # billing_code is a revenue code ("0450"), but additional_information
    # carries the real CPT code "99213" -- coverage should credit 99213,
    # not the revenue code, matching how RC-typed real-file rows work.
    archive = tmp_path / "source.zip"
    member = _archive(
        archive,
        [_item("0450", [_price()], billing_code_type="RC", additional_information="99213")],
        declared_provider_groups=[7],
    )
    result = grade_member(
        archive, member, "url", tmp_path / "db.sqlite", hilabs_weights={"99213": 100.0}
    )
    assert result["code_coverage_weighted_pct"] == 100.0
    assert result["unrecognized_code_count"] == 0


def test_non_rc_code_is_not_rewritten_by_additional_information(tmp_path: Path):
    # Already a real CPT/HCPCS code -- additional_information (if present)
    # must not override it.
    archive = tmp_path / "source.zip"
    member = _archive(
        archive,
        [_item("99213", [_price()], additional_information="99999")],
        declared_provider_groups=[7],
    )
    result = grade_member(
        archive, member, "url", tmp_path / "db.sqlite", hilabs_weights={"99213": 100.0}
    )
    assert result["code_coverage_weighted_pct"] == 100.0
    assert result["unrecognized_code_count"] == 0


# --------------------------------------------------------------------------
# Dollar-rate detection broadened beyond just "negotiated" -- "fee schedule"
# and "derived" also resolve to a real dollar amount.
# --------------------------------------------------------------------------


def test_negotiated_dollar_rate_pct_counts_fee_schedule_and_derived(tmp_path: Path):
    archive = tmp_path / "source.zip"
    items = [
        _item("A", [_price(negotiated_type="negotiated")], provider_refs=(1,)),
        _item("B", [_price(negotiated_type="fee schedule")], provider_refs=(1,)),
        _item("C", [_price(negotiated_type="derived")], provider_refs=(1,)),
        _item("D", [_price(negotiated_type="percentage")], provider_refs=(1,)),
    ]
    member = _archive(archive, items, declared_provider_groups=[1])
    result = grade_member(archive, member, "url", tmp_path / "db.sqlite")
    assert result["negotiated_dollar_rate_pct"] == 75.0


# --------------------------------------------------------------------------
# expired_rate_pct: as_of-parameterized so a prior run's result is
# reproducible regardless of what day the pipeline happens to be rerun.
# --------------------------------------------------------------------------


def test_expired_rate_pct_uses_as_of_not_todays_date(tmp_path: Path):
    archive = tmp_path / "source.zip"
    items = [
        _item("A", [_price(expiration_date="2026-01-01")], provider_refs=(1,)),  # expired by 2026-06-01
        _item("B", [_price(expiration_date="2027-01-01")], provider_refs=(1,)),  # not expired
    ]
    member = _archive(archive, items, declared_provider_groups=[1])
    result = grade_member(
        archive, member, "url", tmp_path / "db.sqlite", as_of=date(2026, 6, 1)
    )
    assert result["expired_rate_pct"] == 50.0


def test_expired_rate_pct_zero_when_nothing_has_passed_as_of(tmp_path: Path):
    archive = tmp_path / "source.zip"
    items = [_item("A", [_price(expiration_date="2027-01-01")], provider_refs=(1,))]
    member = _archive(archive, items, declared_provider_groups=[1])
    result = grade_member(
        archive, member, "url", tmp_path / "db.sqlite", as_of=date(2026, 6, 1)
    )
    assert result["expired_rate_pct"] == 0.0

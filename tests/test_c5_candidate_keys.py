from pathlib import Path

import pytest

from pipeline.stages.c5_address import (
    _build_tin_profiles,
    _census_query_params,
    _haversine_km,
    _npd_location_records,
    _npd_npis_to_fetch,
    _resolve_address_candidates,
    _tin_geographic_support,
    c4_candidate_keys,
    score_address_candidate,
)
from pipeline.stages.c6_final import _c5_summary_path, _select_canonical


def test_c5_candidate_key_is_npi_and_tin_not_billing_code():
    keys = c4_candidate_keys([
        {"npi": "1234567890", "tin": "11-1111111", "business_name": "Group A", "billing_code": "99213"},
        {"npi": "1234567890", "tin": "11-1111111", "business_name": "Group A", "billing_code": "99214"},
        {"npi": "1234567890", "tin": "22-2222222", "business_name": "Group B", "billing_code": "99213"},
    ])

    assert keys == {
        ("1234567890", "11-1111111"): "Group A",
        ("1234567890", "22-2222222"): "Group B",
    }


def test_c5_corroborates_one_address_once_per_candidate_key():
    nppes = [{
        "source": "NPPES", "orig": "10 Main Street, Los Angeles, CA 90001",
        "norm": "10 MAIN ST LOS ANGELES CA 90001", "taxonomy": "207Q00000X",
        "updated": "NPPES", "cms_specialty": "",
    }]
    cms = [{
        "source": "CMS_DAC", "orig": "10 MAIN ST, LOS ANGELES, CA 90001",
        "norm": "10 MAIN ST LOS ANGELES CA 90001", "taxonomy": "",
        "updated": "CMS", "cms_specialty": "Family Medicine",
    }]

    candidates, status = _resolve_address_candidates("1234567890", nppes, cms)

    assert status == "CORROBORATED"
    assert len(candidates) == 1
    assert candidates["10 MAIN ST LOS ANGELES CA 90001"]["sources"] == {"NPPES", "CMS_DAC"}


def test_c5_scores_corroborated_practice_address_above_secondary_candidate():
    corroborated = {
        "orig": "10 Main Street, Los Angeles, CA 90001",
        "sources": {"NPPES", "CMS_DAC"},
        "families": {"NPPES", "CMS_DAC"},
    }
    secondary = {
        "orig": "20 Second Avenue, Los Angeles, CA 90002",
        "sources": {"NPPES_PL"},
        "families": {"NPPES"},
    }

    assert score_address_candidate(corroborated) == (80, "VERIFIED")
    assert score_address_candidate(secondary) == (30, "PROBABLE")


def test_c5_penalizes_po_box_even_when_cms_lists_it():
    po_box = {
        "orig": "P.O. Box 123, Los Angeles, CA 90001",
        "sources": {"CMS_DAC"},
        "families": {"CMS_DAC"},
    }

    assert score_address_candidate(po_box) == (0, "LOW")


def test_c5_treats_current_cms_directory_location_as_verified():
    directory_location = {
        "orig": "100 Main Street, Los Angeles, CA 90001",
        "sources": {"CMS_NPD_LOCATION"},
        "families": {"CMS_NPD_LOCATION"},
    }

    assert score_address_candidate(directory_location) == (60, "VERIFIED")


def test_c5_haversine_scores_near_verified_tin_site_as_support_not_proof():
    # Los Angeles City Hall to a nearby downtown point: hand-checked ~0.5 km.
    assert _haversine_km(34.0537, -118.2428, 34.0580, -118.2468) == pytest.approx(0.59, abs=0.05)

    candidate = {
        "orig": "100 Main Street, Los Angeles, CA 90001",
        "sources": {"NPPES"},
        "families": {"NPPES"},
    }
    assert score_address_candidate(candidate, geo_score=10) == (20, "LOW")


def test_c5_geography_cannot_upgrade_candidate_to_verified():
    candidate = {
        "orig": "100 Main Street, Los Angeles, CA 90001",
        "sources": {"CMS_DAC"},
        "families": {"CMS_DAC"},
    }

    assert score_address_candidate(candidate, geo_score=10) == (60, "PROBABLE")


def test_c5_tin_profile_supports_modal_zip_and_reused_site_without_proving_ownership():
    pairs = {
        ("1000000001", "11-1111111"): ({
            "10 MAIN ST LOS ANGELES CA 90001": {"orig": "10 MAIN ST, LOS ANGELES, CA 90001", "sources": {"CMS_DAC", "NPPES"}, "families": {"CMS_DAC", "NPPES"}},
        }, "SINGLE_SOURCE"),
        ("1000000002", "11-1111111"): ({
            "10 MAIN ST LOS ANGELES CA 90001": {"orig": "10 MAIN ST, LOS ANGELES, CA 90001", "sources": {"CMS_NPD_LOCATION"}, "families": {"CMS_NPD_LOCATION"}},
        }, "SINGLE_SOURCE"),
    }

    profiles = _build_tin_profiles(pairs)
    support = _tin_geographic_support(profiles["11-1111111"], "1000000001", "10 MAIN ST LOS ANGELES CA 90001")

    assert support == (20, "SUPPORTED", "900", 2)


def test_census_geocoder_receives_split_street_city_state_zip_fields():
    assert _census_query_params("1600 Pennsylvania Ave NW, Washington, DC 20500") == {
        "street": "1600 Pennsylvania Ave NW",
        "city": "Washington",
        "state": "DC",
        "zip": "20500",
        "benchmark": "Public_AR_Current",
        "format": "json",
    }


def test_c6_selects_highest_scored_address_before_source_tier():
    selected, status, _, alternatives = _select_canonical([
        {
            "Address": "20 Second Avenue, Los Angeles, CA 90002",
            "Address_Score": "30",
            "Address_Evidence_Tier": "Tier 2",
            "Address_Status": "CONFLICTING",
            "Address_Source": "NPPES_PL",
        },
        {
            "Address": "10 Main Street, Los Angeles, CA 90001",
            "Address_Score": "80",
            "Address_Evidence_Tier": "Tier 3",
            "Address_Status": "CONFLICTING",
            "Address_Source": "NPPES;CMS_DAC",
        },
    ])

    assert selected["Address"].startswith("10 Main")
    assert status == "CANONICAL_SELECTED"
    assert alternatives == ["20 Second Avenue, Los Angeles, CA 90002"]


def test_c5_extracts_active_cms_directory_location_address():
    bundle = {
        "entry": [{
            "resource": {
                "resourceType": "Location",
                "id": "active-clinic",
                "status": "active",
                "address": {
                    "line": ["100 Main Street", "Suite 4"],
                    "city": "Los Angeles",
                    "state": "CA",
                    "postalCode": "90001-1234",
                },
                "meta": {"lastUpdated": "2026-10-17T12:00:00Z"},
            }
        }]
    }

    assert _npd_location_records(bundle) == [{
        "source": "CMS_NPD_LOCATION",
        "orig": "100 Main Street, Suite 4, Los Angeles, CA 90001-1234",
        "norm": "100 MAIN ST STE 4 LOS ANGELES CA 90001",
        "taxonomy": "",
        "updated": "2026-10-17T12:00:00Z",
        "cms_specialty": "",
    }]


def test_c5_api_queue_skips_cached_npis(tmp_path):
    (tmp_path / "1000000001.json").write_text("{}")

    assert _npd_npis_to_fetch(
        {"1000000001", "1000000002", "1000000003"}, tmp_path, 2
    ) == ["1000000002", "1000000003"]


def test_c6_reads_summary_next_to_supplied_c5_result():
    assert _c5_summary_path(Path("data/stage/c5_npd_full_run/c5result.csv")) == Path(
        "data/stage/c5_npd_full_run/c5_summary.json"
    )

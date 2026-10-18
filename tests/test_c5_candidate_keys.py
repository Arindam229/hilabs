from pipeline.stages.c5_address import (
    _npd_location_records,
    _resolve_address_candidates,
    c4_candidate_keys,
    score_address_candidate,
)
from pipeline.stages.c6_final import _select_canonical


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

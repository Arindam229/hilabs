import csv
import io
import zipfile
from pathlib import Path

import openpyxl
import pytest

from pipeline.config import Config
from pipeline.stages.c5_address import (
    _build_cms,
    _build_tin_profiles,
    _census_query_params,
    _enrich_cms_with_reassignment,
    _haversine_km,
    _load_revalidation,
    _npd_location_records,
    _npd_npis_to_fetch,
    _reassignment_support,
    _resolve_address_candidates,
    _tin_geographic_support,
    c4_candidate_keys,
    score_address_candidate,
)
from pipeline.stages.c6_final import _c5_summary_path, _select_canonical, run_c6


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


def test_c5_streams_cp1252_reassignment_zip_for_target_npis_only(tmp_path):
    archive = tmp_path / "revalidation.zip"
    headers = [
        "Group PAC ID", "Group Enrollment ID", "Group Legal Business Name",
        "Group State Code", "Record Type", "Individual NPI",
    ]
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=headers)
    writer.writeheader()
    writer.writerow({
        "Group PAC ID": "1234567890",
        "Group Enrollment ID": "I20000000000001",
        "Group Legal Business Name": "Clinique\u00a0Medicale",
        "Group State Code": "CA",
        "Record Type": "Reassignment",
        "Individual NPI": "1111111111",
    })
    writer.writerow({
        "Group PAC ID": "9999999999",
        "Group Enrollment ID": "I20000000000002",
        "Group Legal Business Name": "Out of Scope Group",
        "Group State Code": "CA",
        "Record Type": "Reassignment",
        "Individual NPI": "2222222222",
    })
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("release/revalidation_group_reassignment_pa_xref.csv", buffer.getvalue().encode("cp1252"))

    records, stats = _load_revalidation(archive, {"1111111111"})

    assert records == {
        "1111111111": [{
            "group_pac_id": "1234567890",
            "group_enrollment_id": "I20000000000001",
            "group_name": "Clinique\u00a0Medicale",
            "group_state": "CA",
            "record_type": "Reassignment",
        }]
    }
    assert stats == {
        "available": True,
        "rows_scanned": 2,
        "matched_rows": 1,
        "matched_npis": 1,
        "matched_group_pac_ids": 1,
    }


def test_c5_reassignment_enriches_only_exact_npi_group_pac_address():
    cms = [
        {
            "source": "CMS_DAC", "orig": "10 Main St, Los Angeles, CA 90001",
            "norm": "10 MAIN ST LOS ANGELES CA 90001", "org_pac_id": "1234567890",
            "facility_name": "Digestive Care Consultants",
        },
        {
            "source": "CMS_DAC", "orig": "20 Other St, Los Angeles, CA 90002",
            "norm": "20 OTHER ST LOS ANGELES CA 90002", "org_pac_id": "5555555555",
            "facility_name": "Other Group",
        },
    ]
    reassignment = [{
        "group_pac_id": "1234567890",
        "group_enrollment_id": "I20000000000001",
        "group_name": "Digestive Care Consultants",
        "group_state": "CA",
        "record_type": "Reassignment",
    }]

    enriched = _enrich_cms_with_reassignment(
        "1174512172", "DIGESTIVE CARE CONSULTANTS", cms, reassignment
    )

    assert enriched[0]["reassignment_status"] == "EXACT_NPI_GROUP_PAC_NAME"
    assert enriched[0]["reassignment_name_match"] is True
    assert enriched[0]["reassignment_group_pac_id"] == "1234567890"
    assert enriched[1]["reassignment_status"] == "NONE"


def test_c5_keeps_same_dac_address_when_group_pac_differs(tmp_path):
    archive = tmp_path / "dataset.zip"
    headers = [
        "NPI", "org_pac_id", "Facility Name", "adr_ln_1", "adr_ln_2",
        "City/Town", "State", "ZIP Code", "pri_spec",
    ]
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=headers)
    writer.writeheader()
    for pac_id in ("1111111111", "2222222222"):
        writer.writerow({
            "NPI": "1174512172", "org_pac_id": pac_id,
            "Facility Name": "Digestive Care Consultants", "adr_ln_1": "10 Main St",
            "City/Town": "Los Angeles", "State": "CA", "ZIP Code": "90001",
            "pri_spec": "Gastroenterology",
        })
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "hilabs_dataset_2026-10-17/cms_dac/DAC_NationalDownloadableFile.csv",
            buffer.getvalue(),
        )

    records = _build_cms(archive, {"1174512172"})["1174512172"]

    assert {record["org_pac_id"] for record in records} == {"1111111111", "2222222222"}


def test_c5_reassignment_bridge_scores_address_without_claiming_direct_tin_proof():
    cms = [{
        "source": "CMS_DAC", "orig": "10 Main St, Los Angeles, CA 90001",
        "norm": "10 MAIN ST LOS ANGELES CA 90001", "taxonomy": "",
        "updated": "CMS_DAC", "cms_specialty": "Gastroenterology",
        "org_pac_id": "1234567890", "facility_name": "Digestive Care Consultants",
    }]
    reassignment = [{
        "group_pac_id": "1234567890", "group_enrollment_id": "I20000000000001",
        "group_name": "Digestive Care Consultants", "group_state": "CA",
        "record_type": "Reassignment",
    }]
    enriched = _enrich_cms_with_reassignment(
        "1174512172", "DIGESTIVE CARE CONSULTANTS", cms, reassignment
    )

    candidates, _ = _resolve_address_candidates("1174512172", [], enriched)
    candidate = candidates["10 MAIN ST LOS ANGELES CA 90001"]

    assert score_address_candidate(candidate) == (75, "VERIFIED")
    assert _reassignment_support(candidate) == (
        25,
        "STRONGLY_SUPPORTED",
        "1234567890",
        "Digestive Care Consultants",
        "EXACT_NPI_GROUP_PAC_NAME",
    )


def test_c5_keeps_strongest_reassignment_evidence_when_dac_rows_share_address():
    shared = {
        "source": "CMS_DAC", "orig": "10 Main St, Los Angeles, CA 90001",
        "norm": "10 MAIN ST LOS ANGELES CA 90001", "taxonomy": "",
        "updated": "CMS_DAC", "cms_specialty": "Gastroenterology",
    }
    strong = dict(shared, reassignment_status="EXACT_NPI_GROUP_PAC_NAME",
                  reassignment_name_match=True, reassignment_group_pac_id="111",
                  reassignment_group_name="Matching Group")
    weak = dict(shared, reassignment_status="EXACT_NPI_GROUP_PAC",
                reassignment_name_match=False, reassignment_group_pac_id="222",
                reassignment_group_name="Other Group")

    candidates, _ = _resolve_address_candidates("1174512172", [], [strong, weak])

    assert candidates[shared["norm"]]["reassignment_status"] == "EXACT_NPI_GROUP_PAC_NAME"
    assert candidates[shared["norm"]]["reassignment_group_pac_id"] == "111"


def test_c6_reads_summary_next_to_supplied_c5_result():
    assert _c5_summary_path(Path("data/stage/c5_npd_full_run/c5result.csv")) == Path(
        "data/stage/c5_npd_full_run/c5_summary.json"
    )


def test_c6_exports_reassignment_evidence_columns(tmp_path):
    c5_path = tmp_path / "c5result.csv"
    row = {
        "NPI": "1174512172", "TIN": "33-0308231",
        "Address": "23451 MADISON ST, TORRANCE, CA 90505",
        "Billing_Code": "99213", "Specialty": "Gastroenterology", "Rate": "120.00",
        "Address_Status": "CORROBORATED", "Address_Source": "CMS_DAC;NPPES",
        "Address_Score": "100", "Address_Evidence_Tier": "Tier 2",
        "Reassignment_Status": "EXACT_NPI_GROUP_PAC_NAME",
        "Group_PAC_ID": "1234567890",
        "Reassignment_Group_Name": "Digestive Care Consultants",
        "Reassignment_Name_Match": "yes",
        "TIN_Address_Link_Status": "STRONGLY_SUPPORTED",
    }
    with c5_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(row))
        writer.writeheader()
        writer.writerow(row)
    cfg = Config(
        root=tmp_path, data_dir=tmp_path, archive=tmp_path / "source.zip",
        index_members=(), c2_evidence_members=(),
    )
    (tmp_path / "config.yaml").write_text("sources: {}\n")
    output = tmp_path / "provider_rates.xlsx"

    run_c6(cfg, c5_path=c5_path, output_path=output)

    sheet = openpyxl.load_workbook(output, read_only=True)["Curated Rates"]
    values = list(sheet.iter_rows(values_only=True))
    headers = values[0]
    exported = dict(zip(headers, values[1]))
    assert exported["Reassignment_Status"] == "EXACT_NPI_GROUP_PAC_NAME"
    assert exported["Group_PAC_ID"] == "1234567890"
    assert exported["Reassignment_Group_Name"] == "Digestive Care Consultants"
    assert exported["Reassignment_Name_Match"] == "yes"

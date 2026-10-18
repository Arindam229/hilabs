from pipeline.stages.c5_address import _resolve_address_candidates, c4_candidate_keys


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

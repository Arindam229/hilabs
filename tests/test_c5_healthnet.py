from pipeline.stages.c5_healthnet import classify, extract_locations, person_from_org, query_name


def _resp(npis, network_id="8201", end="9999-12-31", exclude="N", state="CA"):
    return {"results": [{"source": {"carrierEntity": {
        "entityId": "3324568", "entityType": "prac",
        "nationalProviderIdentifiers": [{"number": n} for n in npis],
        "network": {"product": {"networkId": network_id, "name": "HealthNet Commercial PPO"},
                    "carrier": {"name": "CA PPO Large and Small"}},
        "locations": [{
            "name": "BAIK",
            "address": {"addressLine1": "266 S HARVARD BLVD", "addressLine2": "STE 110",
                        "city": "LOS ANGELES", "stateCode": state, "zipCode": "90004"},
            "networkLocationCycles": [{"startDate": "2020-01-01", "endDate": end, "excludeFromDirectory": exclude}],
            # the public site's own filter (R-C5-HN-02)
            "eligibleForDisplay": [{"eligibleIndicator": "N" if exclude == "Y" else "Y",
                                    "startDate": "2020-01-01", "endDate": end}],
        }],
    }}}]}


C5 = ["266 S HARVARD BLVD STE 110 LOS ANGELES CA 90004"]


def test_person_corp_names_strip_to_person_and_real_orgs_do_not():
    assert person_from_org("SANG H BAIK M.D., INC") == "SANG H BAIK"
    assert person_from_org("JOHN SMITH, A MEDICAL CORPORATION") == "JOHN SMITH"
    assert person_from_org("Carlsbad Surgery Center, LLC") == ""
    assert person_from_org("ACME") == ""
    assert query_name("SANG H BAIK M.D., INC") == "SANG H BAIK M D INC"


def test_active_target_ppo_location_matching_c5_address_is_payer_match():
    rows = extract_locations(_resp(["1285732370"]), "2026-10-18", ["8201"])
    assert rows[0]["HN_Target_Network"] == "yes" and rows[0]["HN_Active"] == "yes"
    assert classify(rows, C5)[0] == "PAYER_PPO_ADDRESS_MATCH"


def test_expired_or_other_network_locations_never_verify():
    for resp in (_resp(["1"], end="2025-12-31"), _resp(["1"], network_id="13181")):
        rows = extract_locations(resp, "2026-10-18", ["8201"])
        assert classify(rows, C5)[0] == "LISTED_NON_TARGET_OR_INACTIVE_ONLY"


def test_current_but_directory_hidden_ppo_location_is_hidden_match_not_verified():
    rows = extract_locations(_resp(["1"], end="4000-01-01", exclude="Y"), "2026-10-18", ["8201"])
    assert rows[0]["HN_Active"] == "no" and rows[0]["HN_Contract_Current"] == "yes"
    assert classify(rows, C5) == ("PAYER_PPO_HIDDEN_ADDRESS_MATCH", "R-C5-HN-06",
                                  "266 S HARVARD BLVD, STE 110, LOS ANGELES, CA, 90004")


def test_non_california_locations_dropped_and_absence_is_not_found():
    assert extract_locations(_resp(["1"], state="NV"), "2026-10-18", ["8201"]) == []
    assert classify([], C5)[0] == "NOT_FOUND_IN_PAYER_DIRECTORY"


def test_target_ppo_at_unknown_address_is_new_candidate():
    rows = extract_locations(_resp(["1"]), "2026-10-18", ["8201"])
    assert classify(rows, ["1 OTHER ST LOS ANGELES CA 90001"])[0] == "PAYER_PPO_ADDRESS_NEW"

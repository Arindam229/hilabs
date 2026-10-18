from pipeline.stages.c5_address import (
    _normalize_address,
    _resolve_address_candidates,
    score_address_candidate,
)
from pipeline.stages.c5_external import _display, pecos_flag

NPPES = {"source": "NPPES", "orig": "72757 FRED WARING DR STE 1, PALM DESERT, CA 922609404",
         "norm": _normalize_address("72757 FRED WARING DR STE 1", "", "PALM DESERT", "CA", "922609404"),
         "state": "CA", "taxonomy": "", "updated": "NPPES", "cms_specialty": ""}


def _ext(source, line1="72757 Fred Waring Dr", reason=""):
    norm = _normalize_address(line1, "", "Palm Desert", "CA", "92260")
    return {"source": source, "orig": f"{line1}, Palm Desert, CA, 92260", "norm": norm, "state": "CA",
            "taxonomy": "", "updated": "x", "cms_specialty": "", "building_match": True, "hn_hidden_reason": reason}


def test_zip_plus4_is_cut_even_when_street_number_has_five_digits():
    assert NPPES["norm"].endswith("CA 92260")
    assert _normalize_address("266 S HARVARD BLVD", "STE 110", "LOS ANGELES", "CA", "90004-4374").endswith("CA 90004")


def test_payer_record_without_suite_joins_the_nppes_candidate():
    groups, status = _resolve_address_candidates("1003849621", [NPPES], [_ext("HEALTHNET_PPO_SHOWN")])
    assert len(groups) == 1 and status == "CORROBORATED"
    assert next(iter(groups.values()))["sources"] == {"NPPES", "HEALTHNET_PPO_SHOWN"}


def test_shown_payer_or_claims_plus_nppes_verifies_but_hidden_does_not():
    for source, expected in (("HEALTHNET_PPO_SHOWN", "VERIFIED"), ("MEDICARE_CLAIMS_2024", "VERIFIED"),
                             ("HEALTHNET_PPO_HIDDEN", "PROBABLE")):
        groups, _ = _resolve_address_candidates("1003849621", [NPPES], [_ext(source, reason="Claims History")])
        assert score_address_candidate(next(iter(groups.values())))[1] == expected, source


def test_single_external_source_alone_is_never_verified():
    for source in ("HEALTHNET_PPO_SHOWN", "MEDICARE_CLAIMS_2024", "HEALTHNET_PPO_HIDDEN"):
        groups, _ = _resolve_address_candidates("1003849621", [], [_ext(source)])
        assert score_address_candidate(next(iter(groups.values())))[1] != "VERIFIED", source


def test_display_address_keeps_state_zip_readable_by_c6_and_pecos_flags():
    assert _display("266 S Harvard Blvd, Ste 110, Los Angeles, CA, 90004") == \
        "266 S Harvard Blvd, Ste 110, Los Angeles, CA 90004"
    assert (pecos_flag({"CA", "NV"}), pecos_flag({"OR"}), pecos_flag(None)) == ("CA", "OTHER_STATE_ONLY", "NOT_ENROLLED")


def test_sources_resolve_inside_one_archive_by_suffix_and_env_file_overrides(tmp_path):
    import io
    import zipfile

    from pipeline.io.archive import open_source_zip

    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w") as z:
        z.writestr("2024/MUP_PHY_X_Prov.csv", "Rndrng_NPI\n1\n")
    archive = tmp_path / "any_root_name.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("renamed_root/cms/Medicare by Provider.zip", inner.getvalue())
    with open_source_zip(archive, "cms/Medicare by Provider.zip") as (z, label):
        assert z.namelist() == ["2024/MUP_PHY_X_Prov.csv"] and label.endswith("renamed_root/cms/Medicare by Provider.zip")
    with open_source_zip(archive, "cms/absent.zip") as (z, label):
        assert z is None and "not in archive" in label
    standalone = tmp_path / "override.zip"
    standalone.write_bytes(inner.getvalue())
    with open_source_zip(archive, "cms/absent.zip", standalone) as (z, label):
        assert z is not None and label == str(standalone)

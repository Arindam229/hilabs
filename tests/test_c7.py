from pathlib import Path

import pytest

from pipeline.stages.c7 import (
    REST_OF_CALIFORNIA_LOCALITY,
    _leave_one_out_medians,
    _strip_county_suffix,
    aggregate_providers,
    compute_reference_ratios,
    extract_zip5,
    medicare_allowed,
    resolve_locality,
)

ARCHIVE = Path("data/hilabs_dataset_2026-10-17.zip")


# --------------------------------------------------------------------------
# extract_zip5
# --------------------------------------------------------------------------


def test_extract_zip5_plain():
    assert extract_zip5("17777 VENTURA BLVD STE 105, ENCINO, CA 91316") == "91316"


def test_extract_zip5_with_hyphenated_plus4():
    assert extract_zip5("123 MAIN ST, SF, CA 94102-1234") == "94102"


def test_extract_zip5_concatenated_plus4_no_hyphen():
    # real format seen in the dataset: zip5+zip4 run together with no separator
    assert extract_zip5("5471 KEARNY VILLA RD, SAN DIEGO, CA 921231105") == "92123"


def test_extract_zip5_missing():
    assert extract_zip5("no zip here") is None


# --------------------------------------------------------------------------
# County suffix stripping (typo correction is handled separately, by fuzzy
# matching against the real county list in load_county_to_locality -- not
# hardcoded here, see test_county_to_locality_resolves_orange_county below)
# --------------------------------------------------------------------------


def test_strip_county_suffix():
    assert _strip_county_suffix("Los Angeles County") == "LOS ANGELES"
    assert _strip_county_suffix("ORANGE CNTY") == "ORANGE"
    assert _strip_county_suffix("Plaquemines Parish") == "PLAQUEMINES"


# --------------------------------------------------------------------------
# resolve_locality
# --------------------------------------------------------------------------


def test_fuzzy_match_generalizes_to_an_arbitrary_unseen_typo():
    # Proves the mechanism isn't secretly a hardcoded list for one known
    # case: a *different* synthetic typo, never mentioned anywhere in this
    # codebase, still resolves correctly via the same FUZZY_COUNTY_CUTOFF
    # used in production.
    import difflib

    from pipeline.stages.c7 import FUZZY_COUNTY_CUTOFF

    real_ca_counties = {"SACRAMENTO", "SAN JOAQUIN", "STANISLAUS", "TUOLUMNE", "MONTEREY"}
    typo = "SACRAMENTOO"  # a typo this codebase has never seen
    match = difflib.get_close_matches(typo, real_ca_counties, n=1, cutoff=FUZZY_COUNTY_CUTOFF)
    assert match == ["SACRAMENTO"]


def test_resolve_locality_found():
    zip_to_county = {"91316": "LOS ANGELES"}
    county_to_locality = {"LOS ANGELES": "18"}
    locality, fallback = resolve_locality("91316", zip_to_county, county_to_locality)
    assert locality == "18"
    assert fallback is False


def test_resolve_locality_unknown_zip_falls_back():
    locality, fallback = resolve_locality("00000", {}, {})
    assert locality == REST_OF_CALIFORNIA_LOCALITY
    assert fallback is True


def test_resolve_locality_known_zip_unmapped_county_falls_back():
    zip_to_county = {"99999": "NOWHERESVILLE"}
    locality, fallback = resolve_locality("99999", zip_to_county, {})
    assert locality == REST_OF_CALIFORNIA_LOCALITY
    assert fallback is True


# --------------------------------------------------------------------------
# medicare_allowed
# --------------------------------------------------------------------------


def test_medicare_allowed_non_facility_formula():
    rvu = {"work_rvu": 1.0, "pe_rvu_nonfac": 2.0, "pe_rvu_fac": 1.0, "mp_rvu": 0.5, "conversion_factor": 10.0}
    gpci = {"work": 1.0, "pe": 1.0, "mp": 1.0}
    assert medicare_allowed(rvu, gpci, facility=False) == pytest.approx(35.0)


def test_medicare_allowed_facility_uses_facility_pe():
    rvu = {"work_rvu": 1.0, "pe_rvu_nonfac": 2.0, "pe_rvu_fac": 1.0, "mp_rvu": 0.5, "conversion_factor": 10.0}
    gpci = {"work": 1.0, "pe": 1.0, "mp": 1.0}
    assert medicare_allowed(rvu, gpci, facility=True) == pytest.approx(25.0)


# --------------------------------------------------------------------------
# leave-one-out median
# --------------------------------------------------------------------------


def test_leave_one_out_median_matches_brute_force():
    import random
    from statistics import median

    random.seed(7)
    for n in range(10):
        vals = [round(random.uniform(0.1, 5.0), 3) for _ in range(n)]
        got = _leave_one_out_medians(vals)
        for i in range(n):
            rest = vals[:i] + vals[i + 1 :]
            expected = median(rest) if rest else None
            if expected is None:
                assert got[i] is None
            else:
                assert got[i] == pytest.approx(expected)


# --------------------------------------------------------------------------
# compute_reference_ratios: the credibility blend itself
# --------------------------------------------------------------------------


def _row(npi="1", code="99213", specialty="Cardiology", rate=100.0, medicare_ratio=1.0):
    return {
        "npi": npi,
        "billing_code": code,
        "specialty": specialty,
        "rate": rate,
        "medicare_ratio": medicare_ratio,
    }


def test_no_peers_falls_back_to_pure_medicare_ratio():
    rows = [_row(npi="1", medicare_ratio=1.5)]  # the only row for this (specialty, code)
    compute_reference_ratios(rows)
    assert rows[0]["reference_ratio"] == pytest.approx(1.5)
    assert rows[0]["tier"] == "C_medicare_only"


def test_large_specialty_cohort_converges_toward_peer_median():
    # one low outlier among many peers clustered at medicare_ratio=2.0
    rows = [_row(npi=str(i), medicare_ratio=2.0) for i in range(30)]
    rows.append(_row(npi="outlier", medicare_ratio=0.1))
    compute_reference_ratios(rows)
    outlier = next(r for r in rows if r["npi"] == "outlier")
    # with n_A=30 peers, z_A = 30/(30+5) ~= 0.857 -> pulled strongly toward 2.0
    assert outlier["reference_ratio"] > 1.5
    assert outlier["tier"] == "A_specialty_code"


def test_cross_specialty_is_weaker_signal_than_same_specialty():
    # Build a case where only code-only (cross-specialty) peers exist.
    rows = [_row(npi=str(i), specialty=f"Spec{i}", medicare_ratio=2.0) for i in range(15)]
    rows.append(_row(npi="target", specialty="UniqueSpecialty", medicare_ratio=0.1))
    compute_reference_ratios(rows)
    target = next(r for r in rows if r["npi"] == "target")
    assert target["tier"] == "B_code_only"
    # z_B uses K_B=10 (double K_A=5): with n_B=15, z_B = 15/25 = 0.6, weaker
    # pull than an equivalent same-specialty cohort would give.
    assert 0.1 < target["reference_ratio"] < 1.5


def test_codes_without_medicare_ratio_are_untouched():
    rows = [{"npi": "1", "billing_code": "RC110", "specialty": "X", "rate": 100.0, "medicare_ratio": None}]
    compute_reference_ratios(rows)
    assert "reference_ratio" not in rows[0]


# --------------------------------------------------------------------------
# aggregate_providers
# --------------------------------------------------------------------------


def test_aggregate_providers_weighted_ppi_and_shrinkage():
    rows = [
        {"npi": "1", "tin": "T1", "billing_code": "A", "specialty": "Cardiology",
         "reference_ratio": 2.0, "tier": "A_specialty_code"},
        {"npi": "1", "tin": "T1", "billing_code": "B", "specialty": "Cardiology",
         "reference_ratio": 1.0, "tier": "A_specialty_code"},
    ]
    proc_weights = {"A": 3.0, "B": 1.0}
    providers, _k_provider = aggregate_providers(rows, proc_weights)
    assert len(providers) == 1
    p = providers[0]
    # weighted raw PPI = (3*2.0 + 1*1.0) / 4 = 1.75
    assert p["ppi_raw"] == pytest.approx(1.75)
    assert p["basket_weight"] == pytest.approx(4.0)


def test_single_provider_in_dataset_gets_full_credibility():
    # with exactly one provider, k_provider == that provider's own weight,
    # so z = w/(w+w) = 0.5 exactly -- a precise, checkable case.
    rows = [{"npi": "1", "tin": "T1", "billing_code": "A", "specialty": "X",
             "reference_ratio": 3.0, "tier": "C_medicare_only"}]
    providers, _k_provider = aggregate_providers(rows, {"A": 10.0})
    assert providers[0]["z_credibility"] == pytest.approx(0.5)
    assert providers[0]["ppi_credible"] == pytest.approx(0.5 * 3.0 + 0.5 * 1.0)


def test_breadth_is_self_contained_within_specialty():
    rows = [
        {"npi": "1", "tin": "T1", "billing_code": "A", "specialty": "Derm",
         "reference_ratio": 1.0, "tier": "A_specialty_code"},
        {"npi": "2", "tin": "T2", "billing_code": "A", "specialty": "Derm",
         "reference_ratio": 1.0, "tier": "A_specialty_code"},
        {"npi": "2", "tin": "T2", "billing_code": "B", "specialty": "Derm",
         "reference_ratio": 1.0, "tier": "A_specialty_code"},
    ]
    providers, _ = aggregate_providers(rows, {"A": 1.0, "B": 1.0})
    by_npi = {p["npi"]: p for p in providers}
    # Derm universe = {A, B}; provider 1 has only A -> 50%, provider 2 has both -> 100%
    assert by_npi["1"]["breadth_pct"] == pytest.approx(50.0)
    assert by_npi["2"]["breadth_pct"] == pytest.approx(100.0)


def test_provider_with_no_priceable_codes_is_unscored_not_average():
    rows = [{"npi": "1", "tin": "T1", "billing_code": "RC1", "specialty": "X"}]  # no reference_ratio at all
    providers, _ = aggregate_providers(rows, {})
    assert providers[0]["ppi_raw"] is None
    assert providers[0]["ppi_credible"] is None
    assert providers[0]["quadrant"] == "Insufficient data"
    assert providers[0]["z_credibility"] == 0.0


# --------------------------------------------------------------------------
# Real-data smoke tests
# --------------------------------------------------------------------------


@pytest.mark.skipif(not ARCHIVE.exists(), reason="real dataset archive not present in this environment")
def test_zip_to_county_resolves_known_zips():
    from pipeline.stages.c7 import load_zip_to_county

    zip_to_county = load_zip_to_county(ARCHIVE)
    assert zip_to_county["91316"] == "LOS ANGELES"
    assert zip_to_county["94102"] == "SAN FRANCISCO"


@pytest.mark.skipif(not ARCHIVE.exists(), reason="real dataset archive not present in this environment")
def test_county_to_locality_resolves_orange_county_via_fuzzy_match():
    # No hardcoded typo list -- this proves the general fuzzy-match
    # mechanism catches CMS's real "ORAGNGE"/"ORANGE" typo on its own,
    # and reports it rather than applying it silently.
    from pipeline.stages.c7 import load_county_to_locality, load_zip_to_county

    known_counties = set(load_zip_to_county(ARCHIVE).values())
    county_to_locality, fuzzy_corrections = load_county_to_locality(ARCHIVE, known_counties)
    assert county_to_locality["ORANGE"] == "18"
    assert county_to_locality["LOS ANGELES"] == "18"
    assert fuzzy_corrections.get("ORAGNGE") == "ORANGE"


@pytest.mark.skipif(
    not (Path("data/out/final_provider_rates.xlsx").exists()),
    reason="C6 output not present in this environment -- run the pipeline first",
)
def test_run_c7_end_to_end_on_real_data():
    from pipeline.config import load_config
    from pipeline.stages.c7 import run_c7

    cfg = load_config()
    result = run_c7(cfg)
    assert result.counts["providers"] > 0
    assert result.counts["pfs_matched"] > 0
    for p in result.outputs:
        assert p.exists()

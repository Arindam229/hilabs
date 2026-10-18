import io
import zipfile
from pathlib import Path
from typing import ClassVar

import pytest

from metrics import (
    DEFAULT_BENCHMARK_XLSX,
    DEFAULT_PFS_ZIP,
    compute_metrics,
    em_ladders_by_rvu,
    grade_file,
    load_pfs_table,
)

REAL_FILE = Path(
    "data/hilabs_dataset_2026-10-17/centene/in_network/"
    "2026-09-28_centene-management-company-llc_ambetter-ks_in-network.json"
)


def _row(
    code="99213",
    rate=100.0,
    bclass="professional",
    setting="outpatient",
    svc=(),
    modifier=(),
    group=(1,),
    ptype="negotiated",
    additional_info=None,
):
    return {
        "billing_code": code,
        "negotiated_type": ptype,
        "negotiated_rate": rate,
        "billing_class": bclass,
        "setting": setting,
        "service_code": svc,
        "billing_code_modifier": modifier,
        "additional_information": additional_info,
        "provider_group_ids": group,
    }


def _metrics(rows, **kw):
    return compute_metrics(rows, header={}, declared_groups=set(), **kw)


def test_zero_or_negative_rate():
    m = _metrics([_row(rate=100.0), _row(rate=0.0), _row(rate=-5.0)])
    assert m["zero_or_negative_rate_pct"] == pytest.approx(200 / 3, abs=0.01)


def test_outlier_is_per_code_not_global():
    rows = [_row(code="A", rate=r) for r in [100, 102, 98, 101, 99, 5000]]
    rows += [_row(code="B", rate=r) for r in [9000, 9100, 8900, 9050, 8950]]
    m = _metrics(rows)
    assert m["outlier_rate_pct"] == pytest.approx(100 / 11, abs=0.01)


def test_duplicate_entry_pct_uses_full_identity_including_modifier():
    rows = [
        _row(code="A", group=(1,), modifier=("AA",), rate=100.0),
        _row(code="A", group=(1,), modifier=("AA",), rate=100.0),  # true duplicate
        _row(code="A", group=(1,), modifier=("GT",), rate=100.0),  # different modifier, not a dup
    ]
    m = _metrics(rows)
    assert m["duplicate_entry_pct"] == pytest.approx(100 / 3, abs=0.01)


def test_rate_ambiguity_density_only_flags_conflicting_rates():
    rows = [
        _row(code="A", group=(1,), rate=100.0),
        _row(code="A", group=(1,), rate=150.0),  # same code+provider, different rate -> ambiguous
        _row(code="B", group=(1,), rate=100.0),
        _row(code="B", group=(1,), rate=100.0),  # same rate repeated -> not ambiguous
    ]
    m = _metrics(rows)
    assert m["rate_ambiguity_density_pct"] == 50.0


def test_pointer_hygiene_detects_orphans_and_ghosts():
    rows = [_row(group=(1, 2))]  # references groups 1 and 2
    m = compute_metrics(rows, header={}, declared_groups={1, 3})  # declares 1 and 3
    assert m["pointer_hygiene"]["orphan_references"] == 1  # group 2 referenced but undeclared
    assert m["pointer_hygiene"]["ghost_groups"] == 1  # group 3 declared but unused


class TestEmMonotonicity:
    LADDERS: ClassVar[dict[str, list[str]]] = {"established_patient": ["99213", "99214", "99215"]}

    def test_no_violation_when_rates_increase_with_complexity(self):
        rows = [_row(code="99213", rate=100), _row(code="99214", rate=150), _row(code="99215", rate=200)]
        m = _metrics(rows, em_ladders=self.LADDERS)
        assert m["em_monotonicity"] == {
            "applicable": True,
            "reason": None,
            "comparable_groups": 1,
            "violating_groups": 0,
            "violation_rate_pct": 0.0,
            "comparable_pairs": 3,
            "violating_pairs": 0,
        }

    def test_file_with_no_em_codes_at_all_is_not_applicable_not_an_error(self):
        # e.g. a purely institutional/facility file with zero office-visit
        # billing -- must degrade gracefully, never raise or divide by zero.
        rows = [_row(code="99381", rate=100)]  # a real CPT code, just not E/M
        m = _metrics(rows, em_ladders=self.LADDERS)
        assert m["em_monotonicity"]["applicable"] is False
        assert m["em_monotonicity"]["reason"] is not None
        assert m["em_monotonicity"]["violation_rate_pct"] is None

    def test_no_ladders_available_at_all_is_not_applicable_not_an_error(self):
        # e.g. --no-pfs, so there's no RVU-derived ladder to compare against.
        rows = [_row(code="99213", rate=100), _row(code="99214", rate=150)]
        m = _metrics(rows, em_ladders={})
        assert m["em_monotonicity"]["applicable"] is False

    def test_both_adjacent_violations_counted_not_just_the_first(self):
        # the original script used if/elif here, which silently dropped the
        # second violation whenever both occurred in the same group.
        rows = [_row(code="99213", rate=200), _row(code="99214", rate=100), _row(code="99215", rate=50)]
        m = _metrics(rows, em_ladders=self.LADDERS)
        assert m["em_monotonicity"]["violating_pairs"] == 3  # 213>214, 214>215, AND 213>215
        assert m["em_monotonicity"]["violating_groups"] == 1

    def test_non_adjacent_violation_caught_even_with_middle_code_missing(self):
        # 99214 absent entirely -- a 213-vs-215 inversion must still be caught.
        rows = [_row(code="99213", rate=200), _row(code="99215", rate=100)]
        m = _metrics(rows, em_ladders=self.LADDERS)
        assert m["em_monotonicity"]["violating_pairs"] == 1

    def test_groups_with_only_one_em_code_are_not_comparable(self):
        # original script's denominator counted these; they can never violate.
        rows = [_row(code="99213", rate=100)]
        m = _metrics(rows, em_ladders=self.LADDERS)
        assert m["em_monotonicity"]["comparable_groups"] == 0
        assert m["em_monotonicity"]["violation_rate_pct"] is None

    def test_different_setting_is_a_different_group_not_a_false_violation(self):
        # telehealth 99214 cheaper than in-person 99213 isn't a complexity
        # inversion -- it's a different billing context and must not be compared.
        rows = [
            _row(code="99213", rate=200, setting="outpatient"),
            _row(code="99214", rate=50, setting="telehealth"),
        ]
        m = _metrics(rows, em_ladders=self.LADDERS)
        assert m["em_monotonicity"]["comparable_groups"] == 0


def test_medicare_benchmark_is_none_when_not_requested():
    m = _metrics([_row()])  # no `medicare=` passed at all
    assert m["medicare_benchmark"] is None


def test_medicare_benchmark_not_applicable_when_no_codes_match_but_doesnt_crash():
    # requested, but this file's only code isn't in the (tiny, fake) PFS table
    rows = [_row(code="RC110", rate=100)]  # institutional revenue code, not CPT
    m = _metrics(rows, medicare={"99213": {"nonfac": 100.0, "fac": 90.0}})
    assert m["medicare_benchmark"]["applicable"] is False
    assert m["medicare_benchmark"]["reason"] is not None
    assert m["medicare_benchmark"]["median_pct_of_medicare"] is None


def test_medicare_benchmark_applicable_and_correct_when_matched():
    rows = [_row(code="99213", rate=150.0, bclass="professional")]
    m = _metrics(rows, medicare={"99213": {"nonfac": 100.0, "fac": 50.0}})
    assert m["medicare_benchmark"]["applicable"] is True
    assert m["medicare_benchmark"]["median_pct_of_medicare"] == 150.0




def test_load_pfs_table_finds_columns_by_name_not_fixed_position(tmp_path):
    # Columns in a completely different order than the real CMS file --
    # the only thing that should matter is the combined two-row header
    # TEXT, never a hardcoded index. If this test used the same column
    # order as the real file it would prove nothing about robustness.
    sub_header = ["CONV", "", "STATUS", "WORK", "MP", "NON-FAC", "FACILITY"]
    header = ["FACTOR", "HCPCS", "CODE", "RVU", "RVU", "PE RVU", "PE RVU"]
    buf = io.StringIO()
    import csv as _csv

    w = _csv.writer(buf)
    w.writerow(["preamble row, not real data"])
    w.writerow(sub_header)
    w.writerow(header)
    w.writerow(["33.4009", "99213", "A", "1.30", "0.09", "1.46", "0.33"])
    zip_path = tmp_path / "reordered_pfs.zip"
    with zipfile.ZipFile(zip_path, "w") as z:
        z.writestr("PPRRVU2026_Oct_nonQPP.csv", buf.getvalue())

    table = load_pfs_table(zip_path)
    assert table["99213"]["work_rvu"] == 1.30
    assert table["99213"]["pe_rvu_nonfac"] == 1.46
    assert table["99213"]["pe_rvu_fac"] == 0.33
    assert table["99213"]["mp_rvu"] == 0.09
    assert table["99213"]["conversion_factor"] == 33.4009


def test_load_pfs_table_raises_clear_error_on_missing_column(tmp_path):
    buf = io.StringIO()
    import csv as _csv

    w = _csv.writer(buf)
    w.writerow(["HCPCS", "STATUS CODE"])  # missing WORK RVU, PE RVU, MP RVU, CONV FACTOR
    w.writerow(["99213", "A"])
    zip_path = tmp_path / "broken_pfs.zip"
    with zipfile.ZipFile(zip_path, "w") as z:
        z.writestr("PPRRVU2026_Oct_nonQPP.csv", buf.getvalue())

    with pytest.raises(ValueError, match="missing expected column"):
        load_pfs_table(zip_path)


def test_em_ladders_by_rvu_orders_by_total_rvu_not_assumed():
    pfs_table = {
        "99213": {"work_rvu": 1.0, "pe_rvu_nonfac": 1.0, "mp_rvu": 0.1},
        "99214": {"work_rvu": 1.5, "pe_rvu_nonfac": 1.5, "mp_rvu": 0.1},
        "99215": {"work_rvu": 2.0, "pe_rvu_nonfac": 2.0, "mp_rvu": 0.1},
    }
    ladders = em_ladders_by_rvu(pfs_table)
    assert ladders["established_patient"] == ["99213", "99214", "99215"]


@pytest.mark.skipif(not REAL_FILE.exists(), reason="real dataset not present in this environment")
def test_grade_file_streams_a_real_file_end_to_end():
    m = grade_file(REAL_FILE, benchmark_xlsx=None, pfs_zip=None)
    assert m["volume"]["price_count"] == 977
    assert m["zero_or_negative_rate_pct"] == 0.0


@pytest.mark.skipif(
    not (DEFAULT_BENCHMARK_XLSX.exists() and DEFAULT_PFS_ZIP.exists() and REAL_FILE.exists()),
    reason="real reference datasets not present in this environment",
)
def test_grade_file_with_real_reference_data():
    m = grade_file(REAL_FILE)
    assert m["code_coverage"]["weighted_coverage_pct"] > 0
    assert m["medicare_benchmark"]["coverage_pct"] > 0

import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ptd.grading import compute_metrics, grade_file


def _row(
    code="A",
    rate=100.0,
    ptype="negotiated",
    bclass="professional",
    group=(1,),
    svc=(),
    modifier=(),
    setting="outpatient",
    additional_info=None,
    code_type="CPT",
    description="a service",
):
    return {
        "billing_code": code,
        "billing_code_type": code_type,
        "description": description,
        "negotiated_type": ptype,
        "negotiated_rate": rate,
        "billing_class": bclass,
        "service_code": svc,
        "billing_code_modifier": modifier,
        "setting": setting,
        "additional_information": additional_info,
        "provider_group_ids": group,
    }


class GradingMetricsTests(unittest.TestCase):
    def test_empty_file_scores_zero(self):
        self.assertEqual(compute_metrics([])["price_count"], 0)

    def test_zero_or_negative_rate_detected(self):
        rows = [_row(rate=100.0), _row(rate=0.0), _row(rate=-5.0)]
        m = compute_metrics(rows)
        self.assertAlmostEqual(m["zero_or_negative_rate_pct"], 2 / 3)

    def test_outlier_flagged_per_code_not_globally(self):
        # code A: tight cluster + one extreme outlier (needs >= 5 samples)
        rows = [_row(code="A", rate=r) for r in [100, 102, 98, 101, 99, 5000]]
        # code B: a single rate that's "normal" for B's own scale but would
        # look like an outlier if compared against A's cluster -- must not
        # be flagged, since each code is judged against its own distribution.
        rows += [_row(code="B", rate=r) for r in [9000, 9100, 8900, 9050, 8950]]
        m = compute_metrics(rows)
        # exactly 1 of 11 prices (the 5000 under code A) should be flagged
        self.assertAlmostEqual(m["outlier_rate_pct"], 1 / 11)

    def test_duplicates_detected_by_full_key(self):
        rows = [
            _row(code="A", group=(1,), rate=100.0),
            _row(code="A", group=(1,), rate=110.0),  # same key, different rate -> dup
            _row(code="A", group=(2,), rate=100.0),  # different provider -> not a dup
        ]
        m = compute_metrics(rows)
        self.assertEqual(m["duplicate_group_count"], 1)
        self.assertAlmostEqual(m["duplicate_entry_pct"], 1 / 3)

    def test_different_additional_information_is_not_a_duplicate(self):
        # Institutional (DRG-severity) sub-classification: same code/provider,
        # different additional_information -> different billing scenario, not
        # a conflicting duplicate rate for the identical thing.
        rows = [
            _row(code="A", group=(1,), rate=100.0, additional_info="1EA11"),
            _row(code="A", group=(1,), rate=200.0, additional_info="2EA11"),
        ]
        m = compute_metrics(rows)
        self.assertEqual(m["duplicate_group_count"], 0)

    def test_rate_type_and_billing_class_distribution(self):
        rows = [_row(ptype="negotiated")] * 3 + [_row(ptype="percentage of billed charges")]
        m = compute_metrics(rows)
        self.assertAlmostEqual(m["negotiated_type_pct"]["negotiated"], 0.75)
        self.assertAlmostEqual(m["negotiated_type_pct"]["percentage of billed charges"], 0.25)

    def test_code_and_provider_coverage(self):
        rows = [_row(code="A", group=(1,)), _row(code="B", group=(2,))]
        m = compute_metrics(rows, expected_codes={"A", "B", "C"}, network_provider_group_count=4)
        self.assertAlmostEqual(m["code_coverage"], 2 / 3)
        self.assertAlmostEqual(m["provider_coverage"], 2 / 4)

    def test_coverage_is_none_without_a_denominator(self):
        m = compute_metrics([_row()])
        self.assertIsNone(m["code_coverage"])
        self.assertIsNone(m["provider_coverage"])

    def test_staleness_computed_from_last_updated_on(self):
        m = compute_metrics(
            [_row()], header={"last_updated_on": "2026-01-01"}, as_of=date(2026, 4, 1)
        )
        self.assertEqual(m["staleness_days"], 90)

    def test_quality_score_is_bounded_and_perfect_file_scores_high(self):
        clean_rows = [
            _row(code=f"C{i}", group=(i,), rate=100.0 + i) for i in range(10)
        ]
        m = compute_metrics(
            clean_rows,
            header={"last_updated_on": date.today().isoformat()},
            expected_codes={f"C{i}" for i in range(10)},
            network_provider_group_count=10,
        )
        self.assertGreaterEqual(m["quality_score"], 95.0)
        self.assertLessEqual(m["quality_score"], 100.0)

    def test_inconsistent_code_description_detected(self):
        rows = [
            _row(code="A", description="Office visit"),
            _row(code="A", description="Office visit"),  # consistent, same text
            _row(code="B", description="MRI brain"),
            _row(code="B", description="MRI brain with contrast"),  # inconsistent
        ]
        m = compute_metrics(rows)
        self.assertEqual(m["inconsistent_code_description_count"], 1)

    def test_medicare_benchmark_ratio_computed_when_lookup_provided(self):
        # Medicare allows $100 for code A (non-facility/professional).
        rows = [_row(code="A", rate=150.0, bclass="professional")]
        m = compute_metrics(rows, medicare_lookup_nonfac={"A": 100.0})
        self.assertAlmostEqual(m["medicare_benchmark"]["coverage_pct"], 1.0)
        self.assertAlmostEqual(m["medicare_benchmark"]["median_pct_of_medicare"], 150.0)

    def test_medicare_benchmark_uses_facility_lookup_for_institutional_rows(self):
        rows = [_row(code="A", rate=200.0, bclass="institutional")]
        m = compute_metrics(
            rows, medicare_lookup_nonfac={"A": 100.0}, medicare_lookup_fac={"A": 50.0}
        )
        # institutional -> facility lookup (50), not non-fac (100): 200/50 = 400%
        self.assertAlmostEqual(m["medicare_benchmark"]["median_pct_of_medicare"], 400.0)

    def test_medicare_benchmark_none_without_any_lookup(self):
        m = compute_metrics([_row()])
        self.assertIsNone(m["medicare_benchmark"])

    def test_grade_file_streams_a_real_small_in_network_file(self):
        path = Path(
            "data/hilabs_dataset_2026-10-17/centene/in_network/"
            "2026-09-28_centene-management-company-llc_ambetter-ks_in-network.json"
        )
        if not path.exists():
            self.skipTest("real dataset not present in this environment")
        m = grade_file(path)
        self.assertEqual(m["price_count"], 977)
        self.assertEqual(m["schema_version"], "2.0.0")
        self.assertEqual(m["zero_or_negative_rate_pct"], 0.0)


if __name__ == "__main__":
    unittest.main()

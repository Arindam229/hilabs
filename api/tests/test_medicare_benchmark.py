import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ptd.medicare_benchmark import (
    build_medicare_lookup,
    california_blended_gpci,
    load_pfs_table,
)

_PFS_ZIP = Path("data/hilabs_dataset_2026-10-17/cms_pfs/rvu26d-updated-08-26-2026.zip")


class MedicareLookupMathTests(unittest.TestCase):
    def test_build_medicare_lookup_non_facility_formula(self):
        pfs_table = {
            "99213": {
                "work_rvu": 1.0,
                "pe_rvu_nonfac": 2.0,
                "pe_rvu_fac": 1.0,
                "mp_rvu": 0.5,
                "conversion_factor": 10.0,
            }
        }
        gpci = {"work": 1.0, "pe": 1.0, "mp": 1.0}
        lookup = build_medicare_lookup(pfs_table, gpci, facility=False)
        # (1.0 + 2.0 + 0.5) * 10.0 = 35.0
        self.assertAlmostEqual(lookup["99213"], 35.0)

    def test_facility_flag_uses_facility_pe_rvu(self):
        pfs_table = {
            "99213": {
                "work_rvu": 1.0,
                "pe_rvu_nonfac": 2.0,
                "pe_rvu_fac": 1.0,
                "mp_rvu": 0.5,
                "conversion_factor": 10.0,
            }
        }
        gpci = {"work": 1.0, "pe": 1.0, "mp": 1.0}
        lookup = build_medicare_lookup(pfs_table, gpci, facility=True)
        # (1.0 + 1.0 + 0.5) * 10.0 = 25.0
        self.assertAlmostEqual(lookup["99213"], 25.0)

    def test_zero_allowed_amount_excluded(self):
        pfs_table = {"X": {"work_rvu": 0, "pe_rvu_nonfac": 0, "pe_rvu_fac": 0,
                            "mp_rvu": 0, "conversion_factor": 10.0}}
        lookup = build_medicare_lookup(pfs_table, {"work": 1, "pe": 1, "mp": 1})
        self.assertNotIn("X", lookup)


class RealPfsFileTests(unittest.TestCase):
    def setUp(self):
        if not _PFS_ZIP.exists():
            self.skipTest("real CMS PFS zip not present in this environment")

    def test_known_code_matches_published_rvus(self):
        table = load_pfs_table(_PFS_ZIP)
        # Office visit, established patient, low complexity -- verified by hand
        # against the raw CSV: work=1.30, pe_nonfac=1.46, pe_fac=0.33, mp=0.09, cf=33.4009
        row = table["99213"]
        self.assertAlmostEqual(row["work_rvu"], 1.30)
        self.assertAlmostEqual(row["pe_rvu_nonfac"], 1.46)
        self.assertAlmostEqual(row["pe_rvu_fac"], 0.33)
        self.assertAlmostEqual(row["mp_rvu"], 0.09)
        self.assertAlmostEqual(row["conversion_factor"], 33.4009)

    def test_california_gpci_is_averaged_across_all_ca_localities(self):
        gpci = california_blended_gpci(_PFS_ZIP)
        # every CA GPCI component is > 1.0 in the published table (CA has no
        # locality below the national floor), so the blend must be too.
        self.assertGreater(gpci["work"], 1.0)
        self.assertGreater(gpci["pe"], 1.0)
        self.assertGreater(gpci["mp"], 0.0)

    def test_end_to_end_lookup_for_99213_non_facility(self):
        table = load_pfs_table(_PFS_ZIP)
        gpci = california_blended_gpci(_PFS_ZIP)
        lookup = build_medicare_lookup(table, gpci, facility=False)
        expected = (
            1.30 * gpci["work"] + 1.46 * gpci["pe"] + 0.09 * gpci["mp"]
        ) * 33.4009
        self.assertAlmostEqual(lookup["99213"], expected, places=2)


if __name__ == "__main__":
    unittest.main()

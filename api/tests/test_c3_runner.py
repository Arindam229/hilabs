import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ptd.c3_runner import grade_c2_rate_files, local_in_network_path, unique_rate_files_from_c2

_C2_XLSX = Path("data/derived/c2_ppo_network.xlsx")
_IN_NETWORK_DIR = Path("data/hilabs_dataset_2026-10-17/centene/in_network")


class C3RunnerTests(unittest.TestCase):
    def setUp(self):
        if not _C2_XLSX.exists():
            self.skipTest("real C2 output not present in this environment")

    def test_local_in_network_path_uses_filename_only(self):
        url = "https://www.centene.com/.../2026-09-30_x_healthnet-ca_in-network.json"
        self.assertEqual(
            local_in_network_path(url, Path("/data")),
            Path("/data/2026-09-30_x_healthnet-ca_in-network.json"),
        )

    def test_reads_exactly_the_one_in_scope_file(self):
        urls = unique_rate_files_from_c2(_C2_XLSX)
        self.assertEqual(len(urls), 1)
        self.assertTrue(urls[0].endswith("healthnet-ca_in-network.json"))

    def test_grade_c2_rate_files_end_to_end(self):
        if not _IN_NETWORK_DIR.exists():
            self.skipTest("real dataset not present in this environment")
        results = grade_c2_rate_files(_C2_XLSX, _IN_NETWORK_DIR)
        self.assertEqual(len(results), 1)
        self.assertNotIn("error", results[0])
        self.assertEqual(results[0]["price_count"], 1500288)


if __name__ == "__main__":
    unittest.main()

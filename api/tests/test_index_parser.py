import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ptd.index_parser import (
    brand_from_filename,
    build_c1_table,
    filter_california,
    filter_group_market,
    is_california_rate_file,
    parse_index_file,
)


def _write_index(path: Path, structures: list[dict]) -> None:
    path.write_text(json.dumps({"reporting_structure": structures}))


class IndexParserTests(unittest.TestCase):
    def test_brand_from_filename(self):
        self.assertEqual(brand_from_filename("2026-09-28_ambetter_index.json"), "Ambetter")
        self.assertEqual(brand_from_filename("2026-09-30_healthnet_index.json"), "Health Net")
        self.assertEqual(
            brand_from_filename("2026-09-28_qualchoice_dillards_index.json"), "QualChoice"
        )
        self.assertEqual(brand_from_filename("mystery_index.json"), "Unknown")

    def test_parse_index_file_emits_one_row_per_plan_per_file(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "2026-09-28_fidelis_index.json"
            _write_index(
                path,
                [
                    {
                        "in_network_files": [{"location": "https://example.com/rates.json"}],
                        "reporting_plans": [
                            {
                                "plan_name": "Plan A",
                                "plan_id": "1",
                                "plan_id_type": "hios",
                                "plan_market_type": "group",
                                "issuer_name": "Fidelis",
                            },
                            {
                                "plan_name": "Plan B",
                                "plan_id": "1",
                                "plan_id_type": "hios",
                                "plan_market_type": "group",
                                "issuer_name": "Fidelis",
                            },
                        ],
                    }
                ],
            )
            rows = parse_index_file(path)

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["brand"], "Fidelis")
        self.assertEqual(rows[0]["rate_file_url"], "https://example.com/rates.json")
        self.assertEqual({r["plan_name"] for r in rows}, {"Plan A", "Plan B"})

    def test_build_c1_table_drops_exact_duplicate_rows_but_keeps_distinct_plans(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "2026-09-28_ambetter_index.json"
            # Two reporting_structures pointing to the same file+plan (exact dup)
            # plus a second, distinct plan sharing that same rate file (not a dup).
            _write_index(
                path,
                [
                    {
                        "in_network_files": [{"location": "https://example.com/rates.json"}],
                        "reporting_plans": [
                            {
                                "plan_name": "Plan A",
                                "plan_id": "1",
                                "plan_id_type": "hios",
                                "plan_market_type": "group",
                                "issuer_name": "Ambetter",
                            }
                        ],
                    },
                    {
                        "in_network_files": [{"location": "https://example.com/rates.json"}],
                        "reporting_plans": [
                            {
                                "plan_name": "Plan A",
                                "plan_id": "1",
                                "plan_id_type": "hios",
                                "plan_market_type": "group",
                                "issuer_name": "Ambetter",
                            },
                            {
                                "plan_name": "Plan B",
                                "plan_id": "2",
                                "plan_id_type": "hios",
                                "plan_market_type": "group",
                                "issuer_name": "Ambetter",
                            },
                        ],
                    },
                ],
            )
            table = build_c1_table([path])

        self.assertEqual(len(table), 2)
        self.assertEqual({r["plan_name"] for r in table}, {"Plan A", "Plan B"})

    def test_is_california_rate_file(self):
        self.assertTrue(
            is_california_rate_file(
                "https://x.com/2026-09-28_centene-management-company-llc_ambetter-ca_in-network.json"
            )
        )
        self.assertTrue(
            is_california_rate_file(
                "https://x.com/2026-09-30_centene-management-company-llc_healthnet-ca_in-network.json"
            )
        )
        self.assertFalse(
            is_california_rate_file(
                "https://x.com/2026-09-28_centene-management-company-llc_ambetter-tx_in-network.json"
            )
        )
        self.assertFalse(
            is_california_rate_file(
                "https://x.com/2026-09-28_centene-management-company-llc_qualchoice_in-network.json"
            )
        )

    def test_filter_california_keeps_only_ca_rows(self):
        table = [
            {"rate_file_url": "https://x.com/ambetter-ca_in-network.json", "plan_name": "keep"},
            {"rate_file_url": "https://x.com/ambetter-tx_in-network.json", "plan_name": "drop"},
        ]
        self.assertEqual(filter_california(table), [table[0]])

    def test_filter_group_market_drops_individual(self):
        table = [
            {"market_type": "group", "plan_name": "keep"},
            {"market_type": "individual", "plan_name": "drop"},
        ]
        self.assertEqual(filter_group_market(table), [table[0]])


if __name__ == "__main__":
    unittest.main()

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ingestion import parse_csv
from app.store import RunStore, export_rows


class IngestionAndStoreTests(unittest.TestCase):
    def test_parse_csv_returns_rows_and_rejects_blank_header(self):
        rows = parse_csv(b"provider_id,full_name\nP-1,Jane Doe\n")
        self.assertEqual(rows, [{"provider_id": "P-1", "full_name": "Jane Doe"}])

        with self.assertRaisesRegex(ValueError, "header"):
            parse_csv(b"\nP-1,Jane Doe\n")

    def test_store_keeps_run_and_export_keeps_audit_columns(self):
        result = {
            "run_id": "run-001",
            "summary": {"input_count": 1, "output_count": 1, "review_count": 0},
            "records": [
                {
                    "source_id": "P-1",
                    "normalized": {"provider_id": "P-1", "full_name": "Jane Doe"},
                    "action": "normalized",
                    "reason_codes": ["NAME_NORMALIZED"],
                    "review_required": False,
                }
            ],
        }
        store = RunStore()
        store.save(result)

        self.assertEqual(store.get("run-001")["summary"]["output_count"], 1)
        self.assertEqual(
            export_rows(result),
            [
                {
                    "provider_id": "P-1",
                    "full_name": "Jane Doe",
                    "source_id": "P-1",
                    "action": "normalized",
                    "reason_codes": "NAME_NORMALIZED",
                    "review_required": False,
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()

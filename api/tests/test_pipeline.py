import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.pipeline import process_records


class ProcessRecordsTests(unittest.TestCase):
    def test_normalizes_known_fields_and_keeps_source_row(self):
        result = process_records(
            [
                {
                    "provider_id": "P-001",
                    "full_name": "  jANE   DOE, md ",
                    "practice_phone": "(212) 555-1212",
                    "practice_zip": "123",
                }
            ],
            run_id="run-001",
        )

        row = result["records"][0]
        self.assertEqual(row["source_id"], "P-001")
        self.assertEqual(row["normalized"]["full_name"], "Jane Doe, Md")
        self.assertEqual(row["normalized"]["practice_phone"], "2125551212")
        self.assertEqual(row["normalized"]["practice_zip"], "00123")
        self.assertEqual(row["action"], "normalized")
        self.assertFalse(row["review_required"])
        self.assertEqual(
            row["reason_codes"],
            ["NAME_NORMALIZED", "PHONE_NORMALIZED", "ZIP_NORMALIZED"],
        )

    def test_routes_missing_identifier_to_review_without_dropping_record(self):
        result = process_records(
            [{"full_name": "Alex Smith", "practice_phone": ""}],
            run_id="run-002",
        )

        row = result["records"][0]
        self.assertEqual(result["summary"]["input_count"], 1)
        self.assertEqual(result["summary"]["output_count"], 1)
        self.assertEqual(result["summary"]["review_count"], 1)
        self.assertEqual(row["action"], "review")
        self.assertTrue(row["review_required"])
        self.assertIn("MISSING_SOURCE_ID", row["reason_codes"])


if __name__ == "__main__":
    unittest.main()

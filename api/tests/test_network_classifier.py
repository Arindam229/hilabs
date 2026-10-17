import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ptd.network_classifier import classify_network_type, classify_table, filter_ppo


class NetworkClassifierTests(unittest.TestCase):
    def test_plain_ppo_and_hmo(self):
        self.assertEqual(classify_network_type("Gold 80 Ambetter PPO"), ("PPO", "token_match"))
        self.assertEqual(classify_network_type("Silver 70 Ambetter HMO"), ("HMO", "token_match"))

    def test_eoa_is_hmo_not_ppo(self):
        self.assertEqual(classify_network_type("CA L EOA 20/0/1500"), ("HMO(EOA)", "eoa_token"))

    def test_concatenated_token_suffix_match(self):
        self.assertEqual(
            classify_network_type("CA L CUSPPO 15/250/20% RAP"), ("PPO", "suffix_match")
        )

    def test_multiple_tokens_flagged_takes_first(self):
        self.assertEqual(
            classify_network_type("CA L CUS PPO CA IRONWORKERS FWP EPO$15"),
            ("PPO", "multi_token_flagged"),
        )

    def test_no_token_is_unknown(self):
        self.assertEqual(
            classify_network_type("CA L&T CUS SAL CEMENT MASONS CA H&W GF+"),
            ("UNKNOWN", "no_token"),
        )

    def test_filter_ppo_excludes_non_ppo_and_marks_review(self):
        table = [
            {"plan_name": "Gold 80 Ambetter PPO"},
            {"plan_name": "Silver 70 Ambetter HMO"},
            {"plan_name": "CA L CUSPPO 15/250/20% RAP"},
        ]
        ppo_rows = filter_ppo(table)
        self.assertEqual(len(ppo_rows), 2)
        self.assertEqual(ppo_rows[0]["review_required"], False)
        self.assertEqual(ppo_rows[1]["review_required"], True)

    def test_classify_table_preserves_other_columns(self):
        rows = classify_table([{"plan_name": "Gold 80 Ambetter PPO", "plan_id": "1"}])
        self.assertEqual(rows[0]["plan_id"], "1")
        self.assertEqual(rows[0]["network_type"], "PPO")


if __name__ == "__main__":
    unittest.main()

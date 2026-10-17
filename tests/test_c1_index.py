from pathlib import Path

from pipeline.stages.c1_index import parse_index_paths, unique_rate_files

FIXTURE = Path(__file__).parent / "fixtures" / "healthnet_index.json"


def test_parse_index_flattens_plan_file_pairs_and_deduplicates_exact_rows():
    rows = parse_index_paths([FIXTURE])

    assert len(rows) == 2
    assert rows[0] == {
        "brand": "Health Net",
        "source_index": "healthnet_index.json",
        "issuer_name": "Health Net",
        "plan_name": "CA Group PPO 250",
        "plan_id": "67138CA001",
        "plan_id_type": "hios",
        "market_type": "group",
        "rate_file_url": "https://example.test/healthnet-ca.json",
    }


def test_unique_rate_files_counts_many_plans_per_url():
    rows = parse_index_paths([FIXTURE])

    assert unique_rate_files(rows) == [
        {
            "rate_file_url": "https://example.test/healthnet-ca.json",
            "associated_plan_count": 1,
            "brands": "Health Net",
            "market_types": "group",
        },
        {
            "rate_file_url": "https://example.test/healthnet-or.json",
            "associated_plan_count": 1,
            "brands": "Health Net",
            "market_types": "group",
        },
    ]

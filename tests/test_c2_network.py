from pathlib import Path

from openpyxl import load_workbook

from pipeline.config import Config
from pipeline.stages.c1_index import PLAN_COLUMNS, _write_parquet
from pipeline.stages.c2_network import classify_plan, run_c2, unique_ppo_rate_files


def _plan(name: str, *, market: str = "group", plan_id: str = "67138CA001") -> dict[str, str]:
    return {
        "brand": "Health Net",
        "source_index": "healthnet_index.json",
        "issuer_name": "Health Net",
        "plan_name": name,
        "plan_id": plan_id,
        "plan_id_type": "hios",
        "market_type": market,
        "rate_file_url": "https://example.test/healthnet-ca.json",
    }


def test_c2_accepts_explicit_and_concatenated_ppo_tokens():
    assert classify_plan(_plan("CA Group PPO 250"))["network_type"] == "PPO"
    assert classify_plan(_plan("CA CUSPPO 15/250"))["reason_code"] == "R-C2-04-PPO_TOKEN"


def test_c2_restrictive_tokens_override_ppo_token():
    classified = classify_plan(_plan("CA L CUS PPO SACRAMENTO CITY USD EPO"))

    assert classified["network_type"] == "EPO"
    assert classified["reason_code"] == "R-C2-03-RESTRICTIVE_TOKEN"


def test_c2_keeps_non_group_non_ca_and_ambiguous_plans_out_of_ppo_queue():
    assert classify_plan(_plan("CA Individual PPO", market="individual"))["network_type"] == "OUT_OF_SCOPE"
    assert classify_plan(_plan("OR Group PPO", plan_id="67138OR001"))["network_type"] == "OUT_OF_SCOPE"
    assert classify_plan(_plan("CA Open Access", plan_id="67138CA010"))["network_type"] == "UNRESOLVED"


def test_unique_ppo_rate_files_deduplicates_queue_and_keeps_plan_evidence():
    rows = [
        classify_plan(_plan("CA Group PPO 250")),
        classify_plan(_plan("CA CUSPPO 15/250")),
        classify_plan(_plan("CA Group HMO 250")),
    ]

    assert unique_ppo_rate_files(rows) == [
        {
            "rate_file_url": "https://example.test/healthnet-ca.json",
            "associated_ppo_plan_count": 2,
            "sample_plan_name": "CA CUSPPO 15/250",
            "queue_reason_code": "R-C2-07-CANDIDATE_FILE",
        }
    ]


def test_run_c2_writes_excel_from_c1_plan_table(tmp_path: Path):
    data_dir = tmp_path / "data"
    c1_dir = data_dir / "stage" / "c1"
    c1_dir.mkdir(parents=True)
    _write_parquet(
        c1_dir / "plans.parquet",
        [_plan("CA Group PPO 250"), _plan("CA Group HMO 250")],
        PLAN_COLUMNS,
    )
    (tmp_path / "config.yaml").write_text("data_dir: data\n")
    cfg = Config(
        root=tmp_path,
        data_dir=data_dir,
        archive=data_dir / "unused.zip",
        index_members=(),
        c2_evidence_members=(),
    )

    result = run_c2(cfg)

    assert result.counts == {"plans_classified": 2, "ppo_plans": 1, "candidate_rate_files": 1}
    workbook = load_workbook(data_dir / "out" / "c2_ppo_network.xlsx", read_only=True)
    assert workbook.sheetnames == ["Plan classification", "PPO rate files"]
    rows = list(workbook["Plan classification"].values)
    assert len(rows) == 2
    assert rows[0] == (
        "Brand",
        "Plan name",
        "Plan ID",
        "Market type",
        "Rate file URL",
        "Network classification",
        "Rule ID",
        "Confidence",
    )
    assert rows[1][-3:] == ("PPO", "R-C2-04-PPO_TOKEN", "medium")

"""C2 candidate queue drives C3 grading and C4 extraction."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pyarrow.parquet as pq

from pipeline.config import Config
from pipeline.stages.c1_index import run_c1
from pipeline.stages.c2_network import run_c2
from pipeline.stages.c3_quality import run_c3
from pipeline.stages.c4_rates import run_c4

FIXTURES = Path(__file__).parent / "fixtures"


def _cfg_with_source_archive(tmp_path: Path) -> Config:
    archive = tmp_path / "data" / "source.zip"
    archive.parent.mkdir()
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.write(FIXTURES / "healthnet_index.json", "centene/index/healthnet_index.json")
        bundle.write(
            FIXTURES / "healthnet_tic_small.json",
            "centene/in_network/healthnet-ca.json",
        )
    (tmp_path / "config.yaml").write_text(
        "data_dir: data\n"
        "sources:\n"
        "  archive: source.zip\n"
        "  index_members:\n"
        "    - centene/index/*.json\n"
    )
    return Config(
        root=tmp_path,
        data_dir=tmp_path / "data",
        archive=archive,
        index_members=("centene/index/*.json",),
        c2_evidence_members=(),
    )


def test_c2_candidate_queue_drives_c3_then_c4_from_source_archive(tmp_path: Path):
    cfg = _cfg_with_source_archive(tmp_path)
    run_c1(cfg)
    run_c2(cfg)

    c3 = run_c3(cfg)
    c3_rows = pq.read_table(tmp_path / "data" / "stage" / "c3" / "file_metrics.parquet").to_pylist()
    assert c3.counts["files_scored"] == 1
    assert c3_rows[0]["rate_file_url"] == "https://example.test/healthnet-ca.json"
    assert c3_rows[0]["price_count"] == 7

    c4 = run_c4(cfg)
    summary = json.loads((tmp_path / "data" / "stage" / "c4" / "c4_summary.json").read_text())
    assert c4.counts["curated_records"] == 3
    assert summary["source_rate_file_url"] == "https://example.test/healthnet-ca.json"

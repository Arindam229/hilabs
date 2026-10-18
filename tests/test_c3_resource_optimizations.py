"""C3 must remain bounded-memory while preserving audit evidence."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pyarrow.parquet as pq

from pipeline.stages.c3_quality import _load_medicare_lookup, grade_member


def _archive_with_items(path: Path, items: list[dict]) -> str:
    member = "centene/in_network/test.json"
    payload = {
        "version": "2.0.0",
        "last_updated_on": "2026-10-01",
        "in_network": items,
    }
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(member, json.dumps(payload))
    return member


def _item(rate: object, *, code: str = "99213") -> dict:
    return {
        "billing_code": code,
        "negotiated_rates": [
            {
                "provider_references": [7],
                "negotiated_prices": [
                    {
                        "negotiated_type": "negotiated",
                        "negotiated_rate": rate,
                        "billing_class": "professional",
                        "setting": "office",
                    }
                ],
            }
        ],
    }


def test_grade_member_samples_deterministic_blocks(tmp_path: Path):
    archive = tmp_path / "source.zip"
    member = _archive_with_items(archive, [_item(100), _item(200), _item(300)])

    result = grade_member(
        archive,
        member,
        "https://example.test/test.json",
        tmp_path / "identities.sqlite",
        sample_every=2,
        block_size=1,
    )

    assert result["is_sampled"] is True
    assert result["price_count"] == 2
    assert result["sample_every"] == 2


def test_grade_member_writes_only_exception_rows_to_parquet(tmp_path: Path):
    archive = tmp_path / "source.zip"
    member = _archive_with_items(archive, [_item(100), _item(None), _item(0), _item(100)])
    flags_path = tmp_path / "row_flags.parquet"

    result = grade_member(
        archive,
        member,
        "https://example.test/test.json",
        tmp_path / "identities.sqlite",
        flags_path=flags_path,
    )

    rows = pq.read_table(flags_path).to_pylist()
    assert result["exception_row_count"] == 3
    assert len(rows) == 3
    assert {row["flag"] for row in rows} == {
        "INVALID_RATE",
        "ZERO_OR_NEGATIVE_RATE",
        "EXACT_DUPLICATE",
    }


def test_grade_member_caps_exception_flag_examples_without_losing_counts(tmp_path: Path):
    archive = tmp_path / "source.zip"
    member = _archive_with_items(archive, [_item(100), _item(None), _item(0), _item(100)])
    flags_path = tmp_path / "row_flags.parquet"

    result = grade_member(
        archive,
        member,
        "https://example.test/test.json",
        tmp_path / "identities.sqlite",
        flags_path=flags_path,
        flag_limit=2,
    )

    assert result["exception_row_count"] == 3
    assert result["row_flags_written"] == 2
    assert result["row_flags_truncated"] is True
    assert pq.read_table(flags_path).num_rows == 2


def test_medicare_lookup_reads_nested_pfs_without_extracting_to_disk(tmp_path: Path):
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w") as pfs:
        pfs.writestr("GPCI2026.csv", "x,CA,x,x,1,1,1\n")
        pfs.writestr(
            "PPRRVU2026_Oct_nonQPP.csv",
            ",,,WORK,NON-FAC,FACILITY,MP,CONV\n,HCPCS,STATUS CODE,RVU,PE RVU,PE RVU,RVU,FACTOR\n,99213,A,1,2,3,4,5\n",
        )
    archive = tmp_path / "source.zip"
    with zipfile.ZipFile(archive, "w") as outer:
        outer.writestr("cms_pfs/rvu26d-updated-08-26-2026.zip", inner.getvalue())

    assert _load_medicare_lookup(archive) == {"99213": (35.0, 40.0)}

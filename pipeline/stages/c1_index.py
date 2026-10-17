"""C1: flatten Centene index files into deduplicated plan/file artifacts."""

from __future__ import annotations

import fnmatch
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO

import ijson
import pyarrow as pa
import pyarrow.parquet as pq

from pipeline.config import Config
from pipeline.io.manifest import write_manifest

PLAN_COLUMNS = (
    "brand",
    "source_index",
    "issuer_name",
    "plan_name",
    "plan_id",
    "plan_id_type",
    "market_type",
    "rate_file_url",
)
RATE_FILE_COLUMNS = ("rate_file_url", "associated_plan_count", "brands", "market_types")


@dataclass(frozen=True)
class StageResult:
    stage: str
    counts: dict[str, int]
    outputs: tuple[Path, ...]


def _brand(source_name: str) -> str:
    name = source_name.lower()
    if "healthnet" in name or "health-net" in name:
        return "Health Net"
    if "ambetter" in name:
        return "Ambetter"
    if "fidelis" in name:
        return "Fidelis"
    if "qualchoice" in name:
        return "QualChoice"
    return Path(source_name).stem


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def parse_index_stream(stream: BinaryIO, source_name: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for structure in ijson.items(stream, "reporting_structure.item"):
        files = structure.get("in_network_files", [])
        for plan in structure.get("reporting_plans", []):
            for rate_file in files:
                location = _text(rate_file.get("location"))
                if not location:
                    continue
                rows.append(
                    {
                        "brand": _brand(source_name),
                        "source_index": source_name,
                        "issuer_name": _text(plan.get("issuer_name")),
                        "plan_name": _text(plan.get("plan_name")),
                        "plan_id": _text(plan.get("plan_id")),
                        "plan_id_type": _text(plan.get("plan_id_type")),
                        "market_type": _text(plan.get("plan_market_type")).lower(),
                        "rate_file_url": location,
                    }
                )
    return rows


def _dedupe(rows: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, ...]] = set()
    unique: list[dict[str, str]] = []
    for row in rows:
        key = tuple(row[column] for column in PLAN_COLUMNS)
        if key not in seen:
            seen.add(key)
            unique.append(row)
    return unique


def parse_index_paths(paths: list[Path]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in paths:
        with path.open("rb") as stream:
            rows.extend(parse_index_stream(stream, path.name))
    return _dedupe(rows)


def unique_rate_files(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        grouped.setdefault(row["rate_file_url"], []).append(row)
    return [
        {
            "rate_file_url": url,
            "associated_plan_count": len(group),
            "brands": ";".join(sorted({row["brand"] for row in group})),
            "market_types": ";".join(sorted({row["market_type"] for row in group})),
        }
        for url, group in sorted(grouped.items())
    ]


def _matching_members(archive: zipfile.ZipFile, patterns: tuple[str, ...]) -> list[str]:
    # Archive members may be stored under a top-level directory (e.g.
    # ``hilabs_dataset_.../centene/index/...``). Match the configured
    # relative pattern with or without that leading directory so the
    # default data layout keeps working.
    expanded: list[str] = []
    for pattern in patterns:
        expanded.append(pattern)
        if not pattern.startswith("*"):
            expanded.append("*" + pattern)
    return [
        name
        for name in archive.namelist()
        if any(fnmatch.fnmatch(name, pattern) for pattern in expanded)
    ]


def _write_parquet(path: Path, rows: list[dict[str, object]], columns: tuple[str, ...]) -> None:
    count_columns = {"associated_plan_count", "associated_ppo_plan_count"}
    fields = [
        pa.field(column, pa.int64()) if column in count_columns else pa.field(column, pa.string())
        for column in columns
    ]
    table = pa.Table.from_pylist(rows, schema=pa.schema(fields))
    pq.write_table(table, path, compression="zstd")


def run_c1(cfg: Config) -> StageResult:
    if not cfg.archive.is_file():
        raise FileNotFoundError(
            f"C1 archive not found: {cfg.archive}. Set PTD_DATA_DIR or copy Drive archive there."
        )
    stage_dir = cfg.stage_dir("c1")
    stage_dir.mkdir(parents=True, exist_ok=True)
    started_at = __import__("time").monotonic()
    rows: list[dict[str, str]] = []
    source_rows: list[dict[str, object]] = []
    with zipfile.ZipFile(cfg.archive) as archive:
        members = _matching_members(archive, cfg.index_members)
        if not members:
            raise ValueError(f"No index members matched {cfg.index_members} in {cfg.archive.name}")
        for member in members:
            with archive.open(member) as stream:
                parsed = parse_index_stream(stream, member)
            rows.extend(parsed)
            source_rows.append({"member": member, "size": archive.getinfo(member).file_size})
    rows = _dedupe(rows)
    rate_files = unique_rate_files(rows)
    plans_path = stage_dir / "plans.parquet"
    rate_files_path = stage_dir / "rate_files.parquet"
    manifest_path = stage_dir / "_manifest.json"
    _write_parquet(plans_path, rows, PLAN_COLUMNS)
    _write_parquet(rate_files_path, rate_files, RATE_FILE_COLUMNS)
    write_manifest(
        manifest_path,
        stage="c1",
        config_path=cfg.root / "config.yaml",
        sources=source_rows,
        counts={"plan_file_rows": len(rows), "unique_rate_files": len(rate_files)},
        started_at=started_at,
    )
    return StageResult("c1", {"plan_file_rows": len(rows), "unique_rate_files": len(rate_files)}, (plans_path, rate_files_path, manifest_path))

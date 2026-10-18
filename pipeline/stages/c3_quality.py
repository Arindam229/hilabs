"""C3: stream-grade every physical rate file C2 queued."""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import time
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Any

import ijson
import pyarrow as pa
import pyarrow.parquet as pq

from pipeline.config import Config
from pipeline.io.c2_queue import archive_member_for_url, c2_rate_files
from pipeline.io.manifest import write_manifest
from pipeline.stages.c1_index import StageResult


def _open_member(archive_path: Path, member: str):
    import zipfile

    archive = zipfile.ZipFile(archive_path)
    return archive, archive.open(member)


def _header(archive_path: Path, member: str) -> dict[str, str]:
    archive, stream = _open_member(archive_path, member)
    try:
        header: dict[str, str] = {}
        for prefix, event, value in ijson.parse(stream):
            if prefix in {"version", "last_updated_on"} and event == "string":
                header[prefix] = str(value)
            if prefix == "in_network" and event == "start_array":
                break
        return header
    finally:
        stream.close()
        archive.close()


def _freshness_score(last_updated_on: str) -> float | None:
    if not last_updated_on:
        return None
    try:
        age = max(0, (date.today() - datetime.strptime(last_updated_on, "%Y-%m-%d").date()).days)
    except ValueError:
        return None
    return max(0.0, 100.0 - max(0, age - 30) * 2.0)


def _identity(item: dict[str, Any], refs: object, price: dict[str, Any]) -> str:
    payload = {
        "billing_code": item.get("billing_code"),
        "provider_references": refs or [],
        "negotiated_rate": price.get("negotiated_rate"),
        "negotiated_type": price.get("negotiated_type"),
        "billing_class": price.get("billing_class"),
        "setting": price.get("setting"),
        "service_code": price.get("service_code") or [],
        "modifier": price.get("billing_code_modifier") or [],
        "additional_information": price.get("additional_information"),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def grade_member(archive_path: Path, member: str, rate_file_url: str, db_path: Path) -> dict[str, object]:
    """Compute bounded-memory C3 metrics with duplicate identities on disk."""
    header = _header(archive_path, member)
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE identities (key TEXT PRIMARY KEY)")
    total = duplicates = zero_or_negative = invalid_rate = 0
    codes: set[str] = set()
    provider_refs: set[str] = set()
    rate_types: Counter[str] = Counter()
    billing_classes: Counter[str] = Counter()
    archive, stream = _open_member(archive_path, member)
    try:
        for item in ijson.items(stream, "in_network.item", use_float=True):
            code = str(item.get("billing_code") or "").strip()
            if code:
                codes.add(code)
            for negotiated_rate in item.get("negotiated_rates") or []:
                refs = negotiated_rate.get("provider_references") or []
                provider_refs.update(str(ref) for ref in refs)
                for price in negotiated_rate.get("negotiated_prices") or []:
                    total += 1
                    rate_types[str(price.get("negotiated_type") or "missing").lower()] += 1
                    billing_classes[str(price.get("billing_class") or "missing").lower()] += 1
                    try:
                        value = float(price.get("negotiated_rate"))
                    except (TypeError, ValueError):
                        invalid_rate += 1
                    else:
                        if not math.isfinite(value) or value <= 0:
                            zero_or_negative += 1
                    try:
                        conn.execute("INSERT INTO identities VALUES (?)", (_identity(item, refs, price),))
                    except sqlite3.IntegrityError:
                        duplicates += 1
        conn.commit()
    finally:
        stream.close()
        archive.close()
        conn.close()

    validity = 100.0 * (1 - (zero_or_negative + invalid_rate) / total) if total else 0.0
    uniqueness = 100.0 * (1 - duplicates / total) if total else 0.0
    rate_type = 100.0 * rate_types["negotiated"] / total if total else 0.0
    freshness = _freshness_score(header.get("last_updated_on", ""))
    measured = [validity, uniqueness, rate_type] + ([] if freshness is None else [freshness])
    score = round(sum(measured) / len(measured), 1) if measured else 0.0
    return {
        "rate_file_url": rate_file_url,
        "archive_member": member,
        "schema_version": header.get("version", ""),
        "last_updated_on": header.get("last_updated_on", ""),
        "price_count": total,
        "distinct_billing_codes": len(codes),
        "distinct_provider_group_refs": len(provider_refs),
        "zero_or_negative_rate_pct": round(100 * zero_or_negative / total, 4) if total else 0.0,
        "invalid_rate_pct": round(100 * invalid_rate / total, 4) if total else 0.0,
        "exact_duplicate_rate_pct": round(100 * duplicates / total, 4) if total else 0.0,
        "negotiated_dollar_rate_pct": round(100 * rate_types["negotiated"] / total, 4) if total else 0.0,
        "professional_rate_pct": round(100 * billing_classes["professional"] / total, 4) if total else 0.0,
        "freshness_score": freshness,
        "quality_score": score,
        "quality_grade": "A" if score >= 85 else "B" if score >= 70 else "C" if score >= 55 else "D" if score >= 40 else "F",
    }


def run_c3(cfg: Config) -> StageResult:
    started_at = time.monotonic()
    if not cfg.archive.is_file():
        raise FileNotFoundError(f"C3 source archive not found: {cfg.archive}")
    stage_dir = cfg.stage_dir("c3")
    stage_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for index, candidate in enumerate(c2_rate_files(cfg)):
        url = str(candidate["rate_file_url"])
        member = archive_member_for_url(cfg, url)
        db_path = stage_dir / f".c3_identities_{index}.sqlite"
        if db_path.exists():
            db_path.unlink()
        try:
            rows.append(grade_member(cfg.archive, member, url, db_path))
        finally:
            db_path.unlink(missing_ok=True)
    metrics_path = stage_dir / "file_metrics.parquet"
    pq.write_table(pa.Table.from_pylist(rows), metrics_path, compression="zstd")
    report_path = cfg.root / "docs" / "deliverables" / "file_quality_metrics.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# C3 file quality metrics", "", "| File | Score | Grade | Prices | $0/negative % | Duplicates % |", "|---|---:|---|---:|---:|---:|"]
    lines.extend(
        f"| {row['archive_member']} | {row['quality_score']} | {row['quality_grade']} | {row['price_count']} | {row['zero_or_negative_rate_pct']} | {row['exact_duplicate_rate_pct']} |"
        for row in rows
    )
    report_path.write_text("\n".join(lines) + "\n")
    manifest_path = stage_dir / "_manifest.json"
    write_manifest(
        manifest_path,
        stage="c3",
        config_path=cfg.root / "config.yaml",
        sources=[{"path": row["rate_file_url"], "archive_member": row["archive_member"]} for row in rows],
        counts={"files_scored": len(rows), "price_rows_scored": sum(int(row["price_count"]) for row in rows)},
        started_at=started_at,
    )
    return StageResult("c3", {"files_scored": len(rows), "price_rows_scored": sum(int(row["price_count"]) for row in rows)}, (metrics_path, report_path, manifest_path))

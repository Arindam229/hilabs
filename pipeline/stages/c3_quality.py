"""C3: stream-grade every physical rate file C2 queued."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import random
import sqlite3
import time
import zipfile
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
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

IDENTITY_BATCH_SIZE = 500
OUTLIER_RESERVOIR_SIZE = 512
FLAG_SCHEMA = pa.schema(
    (
        pa.field("archive_member", pa.string()),
        pa.field("source_position", pa.string()),
        pa.field("billing_code", pa.string()),
        pa.field("negotiated_rate", pa.float64()),
        pa.field("flag", pa.string()),
    )
)


def _open_member(archive_path: Path, member: str):
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


def _positive_env(name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(name, default)))
    except ValueError:
        return default


def _keep_item(item_index: int, sample_every: int, block_size: int) -> bool:
    return sample_every == 1 or (item_index // block_size) % sample_every == 0


def _existing_keys(conn: sqlite3.Connection, keys: list[str]) -> set[str]:
    existing: set[str] = set()
    for start in range(0, len(keys), IDENTITY_BATCH_SIZE):
        chunk = keys[start : start + IDENTITY_BATCH_SIZE]
        placeholders = ",".join("?" for _ in chunk)
        existing.update(row[0] for row in conn.execute(f"SELECT key FROM identities WHERE key IN ({placeholders})", chunk))
    return existing


def _flush_flags(writer: pq.ParquetWriter, rows: list[dict[str, object]]) -> None:
    if rows:
        writer.write_table(pa.Table.from_pylist(rows, schema=FLAG_SCHEMA))
        rows.clear()


def _flush_identities(
    conn: sqlite3.Connection,
    batch: list[dict[str, object]],
    flags: list[dict[str, object]],
    *,
    flag_limit: int,
    flags_written: int,
) -> tuple[int, int, int]:
    if not batch:
        return 0, 0, flags_written
    keys = list(dict.fromkeys(str(row["identity"]) for row in batch))
    existing = _existing_keys(conn, keys)
    conn.executemany(
        "INSERT OR IGNORE INTO identities (key) VALUES (?)",
        ((key,) for key in keys if key not in existing),
    )
    seen: set[str] = set()
    duplicates = exception_count = 0

    def record(flag_base: dict[str, object], flag: str) -> None:
        nonlocal flags_written
        if flags_written < flag_limit:
            flags.append({**flag_base, "flag": flag})
            flags_written += 1

    for row in batch:
        key = str(row["identity"])
        if key in existing or key in seen:
            duplicates += 1
            record(row["flag_base"], "EXACT_DUPLICATE")
            exception_count += 1
        seen.add(key)
        for flag in row["base_flags"]:
            record(row["flag_base"], flag)
            exception_count += 1
    batch.clear()
    return duplicates, exception_count, flags_written


def _reservoir_add(
    reservoirs: dict[tuple[str, str, str], list[float]],
    observed: Counter[tuple[str, str, str]],
    cohort: tuple[str, str, str],
    rate: float,
    rng: random.Random,
) -> None:
    observed[cohort] += 1
    values = reservoirs[cohort]
    if len(values) < OUTLIER_RESERVOIR_SIZE:
        values.append(rate)
        return
    replacement = rng.randrange(observed[cohort])
    if replacement < OUTLIER_RESERVOIR_SIZE:
        values[replacement] = rate


def _cohort_outlier_estimate(
    reservoirs: dict[tuple[str, str, str], list[float]], observed: Counter[tuple[str, str, str]]
) -> tuple[float | None, int]:
    estimated_outliers = 0.0
    support = 0
    for cohort, values in reservoirs.items():
        if len(values) < 5:
            continue
        logs = sorted(math.log(rate) for rate in values if rate > 0)
        if len(logs) < 5:
            continue
        median = logs[len(logs) // 2]
        mad = sorted(abs(value - median) for value in logs)[len(logs) // 2]
        if mad == 0:
            support += observed[cohort]
            continue
        outliers = sum(abs(0.6745 * (value - median) / mad) > 3.0 for value in logs)
        estimated_outliers += outliers * observed[cohort] / len(logs)
        support += observed[cohort]
    return (100 * estimated_outliers / support if support else None), support


def _load_medicare_lookup(archive_path: Path) -> dict[str, tuple[float, float]] | None:
    """Read CMS PFS nested zip in memory; never extract reference files to disk."""
    try:
        with zipfile.ZipFile(archive_path) as archive:
            member = next(name for name in archive.namelist() if name.endswith("rvu26d-updated-08-26-2026.zip"))
            payload = archive.read(member)
        with zipfile.ZipFile(io.BytesIO(payload)) as pfs_zip:
            with pfs_zip.open("GPCI2026.csv") as stream:
                gpci_rows = csv.reader(io.TextIOWrapper(stream, encoding="utf-8-sig"))
                ca = [row for row in gpci_rows if len(row) > 6 and row[1] == "CA"]
            gpci = tuple(sum(float(row[index]) for row in ca) / len(ca) for index in (4, 5, 6))
            with pfs_zip.open("PPRRVU2026_Oct_nonQPP.csv") as stream:
                rows = csv.reader(io.TextIOWrapper(stream, encoding="utf-8-sig"))
                previous: list[str] = []
                columns: dict[str, int] | None = None
                lookup: dict[str, tuple[float, float]] = {}
                for row in rows:
                    if "HCPCS" in row:
                        names = [f"{left} {right}".strip() for left, right in zip(previous, row)]
                        columns = {name: index for index, name in enumerate(names)}
                        required = {"HCPCS", "STATUS CODE", "WORK RVU", "NON-FAC PE RVU", "FACILITY PE RVU", "MP RVU", "CONV FACTOR"}
                        if not required <= set(columns):
                            return None
                    elif columns and len(row) > max(columns.values()) and row[columns["STATUS CODE"]] in {"A", "R", "T"}:
                        try:
                            work = float(row[columns["WORK RVU"]])
                            nonfac_pe = float(row[columns["NON-FAC PE RVU"]])
                            fac_pe = float(row[columns["FACILITY PE RVU"]])
                            malpractice = float(row[columns["MP RVU"]])
                            conversion = float(row[columns["CONV FACTOR"]])
                        except ValueError:
                            previous = row
                            continue
                        lookup[row[columns["HCPCS"]]] = (
                            (work * gpci[0] + nonfac_pe * gpci[1] + malpractice * gpci[2]) * conversion,
                            (work * gpci[0] + fac_pe * gpci[1] + malpractice * gpci[2]) * conversion,
                        )
                    previous = row
        return lookup
    except (KeyError, StopIteration, ValueError, zipfile.BadZipFile):
        return None


def grade_member(
    archive_path: Path,
    member: str,
    rate_file_url: str,
    db_path: Path,
    *,
    flags_path: Path | None = None,
    sample_every: int = 1,
    block_size: int = 1000,
    flag_limit: int = 100_000,
    medicare_rates: dict[str, tuple[float, float]] | None = None,
) -> dict[str, object]:
    """Compute bounded-memory C3 metrics. Sampling is explicit; default scans every row."""
    header = _header(archive_path, member)
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE identities (key TEXT PRIMARY KEY)")
    if flags_path is None:
        flags_path = db_path.with_suffix(".flags.parquet")
    flags_path.parent.mkdir(parents=True, exist_ok=True)
    writer = pq.ParquetWriter(flags_path, FLAG_SCHEMA, compression="zstd")
    total = duplicates = zero_or_negative = invalid_rate = exception_rows = flags_written = 0
    scanned_items = sampled_items = medicare_matched = medicare_out_of_band = 0
    codes: set[str] = set()
    provider_refs: set[str] = set()
    rate_types: Counter[str] = Counter()
    billing_classes: Counter[str] = Counter()
    reservoirs: dict[tuple[str, str, str], list[float]] = defaultdict(list)
    observed: Counter[tuple[str, str, str]] = Counter()
    rng = random.Random(0)
    identity_batch: list[dict[str, object]] = []
    flag_batch: list[dict[str, object]] = []
    archive, stream = _open_member(archive_path, member)
    try:
        for item_index, item in enumerate(ijson.items(stream, "in_network.item", use_float=True)):
            scanned_items += 1
            if not _keep_item(item_index, sample_every, block_size):
                continue
            sampled_items += 1
            code = str(item.get("billing_code") or "").strip()
            if code:
                codes.add(code)
            for negotiated_index, negotiated_rate in enumerate(item.get("negotiated_rates") or []):
                refs = negotiated_rate.get("provider_references") or []
                provider_refs.update(str(ref) for ref in refs)
                for price_index, price in enumerate(negotiated_rate.get("negotiated_prices") or []):
                    total += 1
                    price_type = str(price.get("negotiated_type") or "missing").lower()
                    billing_class = str(price.get("billing_class") or "missing").lower()
                    rate_types[price_type] += 1
                    billing_classes[billing_class] += 1
                    position = f"{item_index}:{negotiated_index}:{price_index}"
                    base_flags: list[str] = []
                    try:
                        value = float(price.get("negotiated_rate"))
                    except (TypeError, ValueError):
                        invalid_rate += 1
                        value = None
                        base_flags.append("INVALID_RATE")
                    else:
                        if not math.isfinite(value) or value <= 0:
                            zero_or_negative += 1
                            base_flags.append("ZERO_OR_NEGATIVE_RATE")
                        else:
                            cohort = (code, billing_class, price_type)
                            _reservoir_add(reservoirs, observed, cohort, value, rng)
                            if medicare_rates and code in medicare_rates:
                                benchmark = medicare_rates[code][1 if billing_class == "institutional" else 0]
                                if benchmark > 0:
                                    medicare_matched += 1
                                    ratio = value / benchmark
                                    if ratio < 0.3 or ratio > 10:
                                        medicare_out_of_band += 1
                    identity_batch.append(
                        {
                            "identity": _identity(item, refs, price),
                            "flag_base": {
                                "archive_member": member,
                                "source_position": position,
                                "billing_code": code,
                                "negotiated_rate": value,
                            },
                            "base_flags": base_flags,
                        }
                    )
                    if len(identity_batch) >= IDENTITY_BATCH_SIZE:
                        added_duplicates, added_exceptions, flags_written = _flush_identities(
                            conn,
                            identity_batch,
                            flag_batch,
                            flag_limit=flag_limit,
                            flags_written=flags_written,
                        )
                        duplicates += added_duplicates
                        exception_rows += added_exceptions
                        _flush_flags(writer, flag_batch)
        added_duplicates, added_exceptions, flags_written = _flush_identities(
            conn,
            identity_batch,
            flag_batch,
            flag_limit=flag_limit,
            flags_written=flags_written,
        )
        duplicates += added_duplicates
        exception_rows += added_exceptions
        _flush_flags(writer, flag_batch)
        conn.commit()
    finally:
        writer.close()
        stream.close()
        archive.close()
        conn.close()

    validity = 100.0 * (1 - (zero_or_negative + invalid_rate) / total) if total else 0.0
    uniqueness = 100.0 * (1 - duplicates / total) if total else 0.0
    rate_type = 100.0 * rate_types["negotiated"] / total if total else 0.0
    freshness = _freshness_score(header.get("last_updated_on", ""))
    outlier_pct, outlier_support = _cohort_outlier_estimate(reservoirs, observed)
    outlier_sanity = None if outlier_pct is None else 100.0 - outlier_pct
    medicare_sanity = None
    if medicare_matched:
        medicare_sanity = 100.0 * (1 - medicare_out_of_band / medicare_matched)
    components = [validity, uniqueness, rate_type]
    components.extend(value for value in (freshness, outlier_sanity, medicare_sanity) if value is not None)
    score = round(sum(components) / len(components), 1) if components else 0.0
    return {
        "rate_file_url": rate_file_url,
        "archive_member": member,
        "schema_version": header.get("version", ""),
        "last_updated_on": header.get("last_updated_on", ""),
        "is_sampled": sample_every > 1,
        "sample_every": sample_every,
        "block_size": block_size,
        "in_network_items_scanned": scanned_items,
        "in_network_items_sampled": sampled_items,
        "price_count": total,
        "distinct_billing_codes": len(codes),
        "distinct_provider_group_refs": len(provider_refs),
        "zero_or_negative_rate_pct": round(100 * zero_or_negative / total, 4) if total else 0.0,
        "invalid_rate_pct": round(100 * invalid_rate / total, 4) if total else 0.0,
        "exact_duplicate_rate_pct": round(100 * duplicates / total, 4) if total else 0.0,
        "negotiated_dollar_rate_pct": round(100 * rate_types["negotiated"] / total, 4) if total else 0.0,
        "professional_rate_pct": round(100 * billing_classes["professional"] / total, 4) if total else 0.0,
        "cohort_outlier_rate_pct_estimate": None if outlier_pct is None else round(outlier_pct, 4),
        "cohort_outlier_support": outlier_support,
        "medicare_matched_rate_pct": round(100 * medicare_matched / total, 4) if total else 0.0,
        "medicare_out_of_band_pct": round(100 * medicare_out_of_band / medicare_matched, 4) if medicare_matched else None,
        "freshness_score": freshness,
        "exception_row_count": exception_rows,
        "row_flags_written": flags_written,
        "row_flags_truncated": exception_rows > flags_written,
        "quality_score": score,
        "quality_grade": "A" if score >= 85 else "B" if score >= 70 else "C" if score >= 55 else "D" if score >= 40 else "F",
    }


def _grade_candidate(
    archive_path: Path,
    stage_dir: Path,
    index: int,
    rate_file_url: str,
    member: str,
    sample_every: int,
    block_size: int,
    flag_limit: int,
    medicare_rates: dict[str, tuple[float, float]] | None,
) -> tuple[int, dict[str, object]]:
    db_path = stage_dir / f".c3_identities_{index}.sqlite"
    flags_path = stage_dir / "row_flags" / f"{index:04d}.parquet"
    if db_path.exists():
        db_path.unlink()
    try:
        return index, grade_member(
            archive_path,
            member,
            rate_file_url,
            db_path,
            flags_path=flags_path,
            sample_every=sample_every,
            block_size=block_size,
            flag_limit=flag_limit,
            medicare_rates=medicare_rates,
        )
    finally:
        db_path.unlink(missing_ok=True)


def run_c3(cfg: Config) -> StageResult:
    started_at = time.monotonic()
    if not cfg.archive.is_file():
        raise FileNotFoundError(f"C3 source archive not found: {cfg.archive}")
    stage_dir = cfg.stage_dir("c3")
    stage_dir.mkdir(parents=True, exist_ok=True)
    sample_every = _positive_env("PTD_C3_SAMPLE_EVERY", 1)
    block_size = _positive_env("PTD_C3_BLOCK_SIZE", 1000)
    flag_limit = _positive_env("PTD_C3_ROW_FLAG_LIMIT", 100_000)
    candidates = [
        (index, str(candidate["rate_file_url"]), archive_member_for_url(cfg, str(candidate["rate_file_url"])))
        for index, candidate in enumerate(c2_rate_files(cfg))
    ]
    medicare_rates = _load_medicare_lookup(cfg.archive)
    workers = min(_positive_env("PTD_C3_WORKERS", 1), max(1, len(candidates)))
    args = [
        (cfg.archive, stage_dir, index, url, member, sample_every, block_size, flag_limit, medicare_rates)
        for index, url, member in candidates
    ]
    if workers == 1:
        results = [_grade_candidate(*arg) for arg in args]
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            results = list(executor.map(lambda arg: _grade_candidate(*arg), args))
    rows = [row for _index, row in sorted(results)]
    metrics_path = stage_dir / "file_metrics.parquet"
    pq.write_table(pa.Table.from_pylist(rows), metrics_path, compression="zstd")
    report_path = cfg.root / "docs" / "deliverables" / "file_quality_metrics.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# C3 file quality metrics",
        "",
        "| File | Score | Grade | Prices | $0/negative % | Duplicates % | Outlier % | Medicare out-of-band % |",
        "|---|---:|---|---:|---:|---:|---:|---:|",
    ]
    lines.extend(
        f"| {row['archive_member']} | {row['quality_score']} | {row['quality_grade']} | {row['price_count']} | {row['zero_or_negative_rate_pct']} | {row['exact_duplicate_rate_pct']} | {row['cohort_outlier_rate_pct_estimate']} | {row['medicare_out_of_band_pct']} |"
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

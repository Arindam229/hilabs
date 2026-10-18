"""C4: stream a Centene in-network TiC JSON into flat provider rate rows."""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

import ijson
import pyarrow.parquet as pq

from pipeline.io.c2_queue import single_c2_rate_source
from pipeline.io.manifest import write_manifest

RAW_COLUMNS = (
    "source_file", "provider_group_id", "npi", "tin", "tin_type", "business_name",
    "billing_code", "billing_code_type", "billing_code_type_version", "billing_code_description",
    "negotiated_type", "negotiated_rate", "expiration_date", "service_code", "billing_class",
    "setting", "modifiers", "additional_information", "negotiation_arrangement",
)

CURATED_COLUMNS = tuple(c for c in RAW_COLUMNS if c != "expiration_date") + (
    "selection_rule",
    "candidate_count",
    "distinct_candidate_count",
)
AUDIT_COLUMNS = RAW_COLUMNS + ("selection_status", "selection_reason", "selected_negotiated_rate", "selected_negotiated_type")


@dataclass(frozen=True)
class StageResult:
    stage: str
    counts: dict[str, int]
    outputs: tuple[Path, ...]


def _text(value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return ";".join(_text(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True)
    return str(value).strip()


def _number(value):
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _service_code(value):
    if value is None:
        return ""
    if isinstance(value, list):
        return ";".join(str(item).strip() for item in value if item is not None)
    return str(value).strip()


def _modifiers(value):
    if value is None:
        return ""
    if isinstance(value, list):
        return ";".join(str(item).strip() for item in value if item is not None)
    return str(value).strip()


def _additional(value):
    if value is None:
        return ""
    if isinstance(value, list):
        return ";".join(_text(item) for item in value)
    return _text(value)


def _open_stream(path, member=None):
    if member:
        import zipfile
        zf = zipfile.ZipFile(path)
        return zf.open(member)
    if path.suffix.lower() == ".zip":
        # Allow PTD_RATE_MEMBER to be resolved by caller; default to the in-scope member.
        import zipfile
        zf = zipfile.ZipFile(path)
        members = [m for m in zf.namelist() if m.endswith("healthnet-ca_in-network.json")]
        if not members:
            raise FileNotFoundError(f"No healthnet-ca in-network member found in {path}")
        return zf.open(members[0])
    raw = path.open("rb")
    try:
        magic = raw.read(2)
        raw.seek(0)
    except Exception:
        raw.close()
        raise
    if magic == b"\x1f\x8b" or path.suffix.lower() in {".gz", ".gzip"}:
        raw.close()
        return gzip.open(path, "rb")
    return raw


def _top_level_keys(path, member=None):
    stream = _open_stream(path, member)
    try:
        keys = []
        for prefix, event, value in ijson.parse(stream):
            if prefix == "" and event == "map_key":
                keys.append(str(value))
        return keys
    finally:
        stream.close()


def _validate_input(path, member=None):
    if not path.is_file():
        raise FileNotFoundError(f"C4 input file not found: {path}. Pass --rate-file or set PTD_RATE_FILE.")
    try:
        keys = _top_level_keys(path, member)
    except Exception as exc:
        raise ValueError(f"C4 input is not valid JSON: {path}: {exc}") from exc
    missing = [key for key in ("provider_references", "in_network") if key not in keys]
    if missing:
        raise ValueError(f"C4 input is incompatible: missing top-level section(s) {missing} in {path}.")


def _build_provider_lookup(path, member=None):
    stream = _open_stream(path, member)
    try:
        lookup = {}
        for ref in ijson.items(stream, "provider_references.item", use_float=True):
            if not isinstance(ref, dict):
                continue
            pid = ref.get("provider_group_id")
            if pid is None:
                continue
            if pid not in lookup:
                lookup[pid] = list(ref.get("provider_groups") or [])
        return lookup
    finally:
        stream.close()


def _resolve_rate_file(cfg, rate_file):
    if rate_file is not None:
        path = Path(rate_file).expanduser()
        if not path.is_absolute():
            candidate = cfg.root / path
            path = candidate if candidate.exists() else path.resolve()
        return path
    if getattr(cfg, "rate_file", None):
        return Path(cfg.rate_file).expanduser()
    env = os.environ.get("PTD_RATE_FILE")
    if env:
        return Path(env).expanduser()
    raise ValueError("C4 needs --rate-file, sources.rate_file, PTD_RATE_FILE, or a C2 candidate queue.")


def _resolve_c4_source(cfg, rate_file, rate_member):
    """Use explicit input for debugging; otherwise consume C2's sole queue row."""
    if rate_file is not None or getattr(cfg, "rate_file", None) or os.environ.get("PTD_RATE_FILE"):
        return _resolve_rate_file(cfg, rate_file), rate_member or os.environ.get("PTD_RATE_MEMBER"), None
    rate_file_url, member = single_c2_rate_source(cfg)
    return cfg.archive, member, rate_file_url


def _c3_quality_score(cfg, rate_file_url):
    if rate_file_url is None:
        return None
    metrics_path = cfg.stage_dir("c3") / "file_metrics.parquet"
    if not metrics_path.is_file():
        raise FileNotFoundError(f"C4 needs C3 output: {metrics_path}. Run `python -m pipeline c3` first.")
    matches = [row for row in pq.read_table(metrics_path).to_pylist() if row["rate_file_url"] == rate_file_url]
    if len(matches) != 1:
        raise ValueError(f"C3 has no unique metric row for C2 rate file {rate_file_url!r}")
    return float(matches[0]["quality_score"])


def _resolve_output_dir(cfg, output_dir):
    if output_dir is not None:
        path = Path(output_dir).expanduser()
        if not path.is_absolute():
            path = cfg.root / path
        return path
    env = os.environ.get("PTD_C4_OUTPUT_DIR")
    if env:
        path = Path(env).expanduser()
        if not path.is_absolute():
            path = cfg.root / path
        return path
    return cfg.stage_dir("c4")


def _modifier_count(value):
    if not value:
        return 0
    return value.count(";") + 1


def _rank_key(candidate):
    nt = (candidate.get("negotiated_type") or "").strip().lower()
    nt_priority = 0 if nt == "negotiated" else 1 if nt == "fee schedule" else 2
    mods = candidate.get("modifiers") or ""
    mod_count = _modifier_count(mods)
    bc = (candidate.get("billing_class") or "").strip().lower()
    bc_priority = 0 if bc == "professional" else 1 if bc == "institutional" else 2
    freq = candidate.get("_freq", 1)
    rate = candidate.get("_rate_num")
    rate_key = -(rate if rate is not None else float("-inf"))
    return (nt_priority, mod_count, bc_priority, -freq, rate_key)


def _selection_rule(candidates, selected):
    if len(candidates) == 1:
        return "R-C4-SEL-01-SINGLE_CANDIDATE"
    nts = {(c.get("negotiated_type") or "").strip().lower() for c in candidates}
    if len(nts) > 1:
        min_priority = min(
            0 if (c.get("negotiated_type") or "").strip().lower() == "negotiated"
            else 1 if (c.get("negotiated_type") or "").strip().lower() == "fee schedule" else 2
            for c in candidates
        )
        selected_priority = (
            0 if (selected.get("negotiated_type") or "").strip().lower() == "negotiated"
            else 1 if (selected.get("negotiated_type") or "").strip().lower() == "fee schedule" else 2
        )
        if selected_priority == min_priority:
            return "R-C4-SEL-02-PREFERRED_NEGOTIATED_TYPE"
    mod_counts = {_modifier_count(c.get("modifiers") or "") for c in candidates}
    if len(mod_counts) > 1 and _modifier_count(selected.get("modifiers") or "") == min(mod_counts):
        return "R-C4-SEL-03-FEWER_MODIFIERS"
    bcs = {(c.get("billing_class") or "").strip().lower() for c in candidates}
    if len(bcs) > 1:
        selected_bc = (selected.get("billing_class") or "").strip().lower()
        selected_bc_priority = 0 if selected_bc == "professional" else 1 if selected_bc == "institutional" else 2
        min_bc_priority = min(
            0 if (c.get("billing_class") or "").strip().lower() == "professional"
            else 1 if (c.get("billing_class") or "").strip().lower() == "institutional" else 2
            for c in candidates
        )
        if selected_bc_priority == min_bc_priority:
            return "R-C4-SEL-04-PROFESSIONAL_CLASS"
    freqs = {c.get("_freq", 1) for c in candidates}
    if len(freqs) > 1 and selected.get("_freq", 1) == max(freqs):
        return "R-C4-SEL-05-MOST_COMMON_RATE"
    rates = {c.get("_rate_num") for c in candidates}
    if len(rates) > 1:
        selected_rate = selected.get("_rate_num")
        valid_rates = [r for r in rates if r is not None]
        if selected_rate is not None and valid_rates and selected_rate == max(valid_rates):
            return "R-C4-SEL-06-MAX_RATE_TIEBREAK"
    return "R-C4-SEL-07-FIRST_DETERMINISTIC"


def run_c4(cfg, rate_file=None, output_dir=None, rate_member=None, **kwargs):
    started_at = time.monotonic()
    input_path, member, source_rate_file_url = _resolve_c4_source(cfg, rate_file, rate_member)
    c3_quality_score = _c3_quality_score(cfg, source_rate_file_url)
    _validate_input(input_path, member)
    out_dir = _resolve_output_dir(cfg, output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"C4: input={input_path}")
    print(f"C4: output_dir={out_dir}")

    lookup = _build_provider_lookup(input_path, member)

    db_path = out_dir / ".c4_rates.sqlite"
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=OFF")
    conn.execute("PRAGMA synchronous=OFF")
    conn.execute(
        """CREATE TABLE rates (
            source_file TEXT, provider_group_id TEXT, npi TEXT, tin TEXT, tin_type TEXT,
            business_name TEXT, billing_code TEXT, billing_code_type TEXT,
            billing_code_type_version TEXT, billing_code_description TEXT,
            negotiated_type TEXT, negotiated_rate_raw TEXT, negotiated_rate_num REAL,
            expiration_date TEXT, service_code TEXT, billing_class TEXT, setting TEXT,
            modifiers TEXT, additional_information TEXT, negotiation_arrangement TEXT
        )"""
    )

    raw_path = out_dir / "raw_rates.csv"
    raw_file = raw_path.open("w", newline="", encoding="utf-8")
    raw_writer = csv.DictWriter(raw_file, fieldnames=RAW_COLUMNS, extrasaction="ignore")
    raw_writer.writeheader()

    source_name = Path(member).name if member else input_path.name
    service_count = 0
    negotiated_rate_count = 0
    raw_count = 0
    unresolved_count = 0
    distinct_unresolved = set()
    rejected_reasons = {}
    referenced_group_ids = set()
    db_batch = []

    def _flush_db_batch():
        nonlocal db_batch
        if db_batch:
            conn.executemany(
                """INSERT INTO rates (
                    source_file, provider_group_id, npi, tin, tin_type, business_name,
                    billing_code, billing_code_type, billing_code_type_version,
                    billing_code_description, negotiated_type, negotiated_rate_raw,
                    negotiated_rate_num, expiration_date, service_code, billing_class,
                    setting, modifiers, additional_information, negotiation_arrangement
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                db_batch,
            )
            conn.commit()
            db_batch = []

    try:
        stream = _open_stream(input_path, member)
        try:
            for item in ijson.items(stream, "in_network.item", use_float=True):
                if not isinstance(item, dict):
                    rejected_reasons["malformed_service_entry"] = rejected_reasons.get("malformed_service_entry", 0) + 1
                    continue
                service_count += 1
                if service_count % 100 == 0:
                    print(f"C4: processed {service_count} service entries...")
                billing_code = _text(item.get("billing_code"))
                billing_code_type = _text(item.get("billing_code_type"))
                billing_code_type_version = _text(item.get("billing_code_type_version"))
                description = _text(item.get("name")) or _text(item.get("description"))
                negotiation_arrangement = _text(item.get("negotiation_arrangement"))

                for negotiated_rate in item.get("negotiated_rates") or []:
                    if not isinstance(negotiated_rate, dict):
                        continue
                    negotiated_rate_count += 1
                    provider_refs = negotiated_rate.get("provider_references") or []
                    prices = negotiated_rate.get("negotiated_prices") or []

                    price_rows = []
                    for price in prices:
                        if not isinstance(price, dict):
                            continue
                        rate_raw_value = price.get("negotiated_rate", None)
                        rate_num = _number(rate_raw_value)
                        rate_raw = "" if rate_raw_value is None else str(rate_raw_value)
                        negotiated_type = _text(price.get("negotiated_type"))
                        expiration_date = _text(price.get("expiration_date"))
                        service_code = _service_code(price.get("service_code"))
                        billing_class = _text(price.get("billing_class"))
                        setting = _text(price.get("setting"))
                        modifiers = _modifiers(price.get("billing_code_modifier"))
                        additional_information = _additional(price.get("additional_information"))
                        price_rows.append({
                            "negotiated_type": negotiated_type,
                            "negotiated_rate_raw": rate_raw,
                            "negotiated_rate_num": rate_num,
                            "expiration_date": expiration_date,
                            "service_code": service_code,
                            "billing_class": billing_class,
                            "setting": setting,
                            "modifiers": modifiers,
                            "additional_information": additional_information,
                        })

                    for ref_id in provider_refs:
                        referenced_group_ids.add(_text(ref_id))
                        if ref_id not in lookup:
                            unresolved_count += 1
                            distinct_unresolved.add(ref_id)
                            rejected_reasons["unresolved_provider_reference"] = rejected_reasons.get("unresolved_provider_reference", 0) + 1
                            continue
                        groups = lookup.get(ref_id) or []
                        for group in groups:
                            if not isinstance(group, dict):
                                continue
                            npis = group.get("npi") or []
                            if not isinstance(npis, list):
                                npis = [npis]
                            tin_info = group.get("tin") or {}
                            if not isinstance(tin_info, dict):
                                tin_info = {}
                            tin_value = _text(tin_info.get("value"))
                            tin_type = _text(tin_info.get("type"))
                            business_name = _text(tin_info.get("business_name"))
                            for npi in npis:
                                npi_text = _text(npi)
                                if not npi_text:
                                    continue
                                for price in price_rows:
                                    row = {
                                        "source_file": source_name,
                                        "provider_group_id": _text(ref_id),
                                        "npi": npi_text,
                                        "tin": tin_value,
                                        "tin_type": tin_type,
                                        "business_name": business_name,
                                        "billing_code": billing_code,
                                        "billing_code_type": billing_code_type,
                                        "billing_code_type_version": billing_code_type_version,
                                        "billing_code_description": description,
                                        "negotiated_type": price["negotiated_type"],
                                        "negotiated_rate": price["negotiated_rate_raw"],
                                        "expiration_date": price["expiration_date"],
                                        "service_code": price["service_code"],
                                        "billing_class": price["billing_class"],
                                        "setting": price["setting"],
                                        "modifiers": price["modifiers"],
                                        "additional_information": price["additional_information"],
                                        "negotiation_arrangement": negotiation_arrangement,
                                    }
                                    raw_writer.writerow(row)
                                    raw_count += 1
                                    db_batch.append((
                                        source_name, _text(ref_id), npi_text, tin_value, tin_type,
                                        business_name, billing_code, billing_code_type,
                                        billing_code_type_version, description, price["negotiated_type"],
                                        price["negotiated_rate_raw"], price["negotiated_rate_num"],
                                        price["expiration_date"], price["service_code"], price["billing_class"],
                                        price["setting"], price["modifiers"], price["additional_information"],
                                        negotiation_arrangement,
                                    ))
                                    if len(db_batch) >= 1000:
                                        _flush_db_batch()
                raw_file.flush()
        finally:
            stream.close()
    finally:
        pass

    _flush_db_batch()
    invalid_count = int(conn.execute("SELECT COUNT(*) FROM rates WHERE negotiated_rate_num IS NULL").fetchone()[0] or 0)
    zero_count = int(conn.execute("SELECT COUNT(*) FROM rates WHERE negotiated_rate_num = 0").fetchone()[0] or 0)
    negative_count = int(conn.execute("SELECT COUNT(*) FROM rates WHERE negotiated_rate_num < 0").fetchone()[0] or 0)

    raw_file.close()

    dup_fields = (
        "source_file", "provider_group_id", "npi", "tin", "tin_type", "business_name",
        "billing_code", "billing_code_type", "billing_code_type_version",
        "billing_code_description", "negotiated_type", "negotiated_rate_raw",
        "expiration_date", "service_code", "billing_class", "setting", "modifiers",
        "additional_information", "negotiation_arrangement",
    )
    group_by = ", ".join(dup_fields)
    dup_sql = (f"SELECT COALESCE(SUM(c - 1), 0) FROM ("
               f"SELECT COUNT(*) AS c FROM rates GROUP BY {group_by} HAVING COUNT(*) > 1)")
    dup_count = int(conn.execute(dup_sql).fetchone()[0] or 0)

    distinct_npis = int(conn.execute("SELECT COUNT(DISTINCT npi) FROM rates").fetchone()[0] or 0)
    distinct_tins = int(conn.execute("SELECT COUNT(DISTINCT tin) FROM rates").fetchone()[0] or 0)

    curated_path = out_dir / "selected_rates.csv"
    audit_path = out_dir / "rate_selection_audit.csv"
    curated_file = curated_path.open("w", newline="", encoding="utf-8")
    audit_file = audit_path.open("w", newline="", encoding="utf-8")
    curated_writer = csv.DictWriter(curated_file, fieldnames=CURATED_COLUMNS, extrasaction="ignore")
    audit_writer = csv.DictWriter(audit_file, fieldnames=AUDIT_COLUMNS, extrasaction="ignore")
    curated_writer.writeheader()
    audit_writer.writeheader()

    curated_count = 0
    audit_count = 0
    curated_npis = set()
    curated_tins = set()

    select_cols = [
        "source_file", "provider_group_id", "npi", "tin", "tin_type", "business_name",
        "billing_code", "billing_code_type", "billing_code_type_version",
        "billing_code_description", "negotiated_type", "negotiated_rate_raw",
        "negotiated_rate_num", "expiration_date", "service_code", "billing_class",
        "setting", "modifiers", "additional_information", "negotiation_arrangement",
    ]
    col_sql = ", ".join(select_cols)
    order_sql = "npi, tin, billing_code, billing_code_type, billing_code_type_version, provider_group_id"
    query = f"SELECT {col_sql} FROM rates ORDER BY {order_sql}"

    current_key = None
    group_rows = []

    def _process_group(rows):
        nonlocal curated_count, audit_count
        if not rows:
            return
        candidate_map = {}
        for r in rows:
            sig = (
                r["source_file"], r["provider_group_id"], r["npi"], r["tin"], r["tin_type"],
                r["business_name"], r["billing_code"], r["billing_code_type"],
                r["billing_code_type_version"], r["billing_code_description"],
                r["negotiated_type"], r["negotiated_rate_raw"], r["expiration_date"],
                r["service_code"], r["billing_class"], r["setting"], r["modifiers"],
                r["additional_information"], r["negotiation_arrangement"],
            )
            if sig not in candidate_map:
                candidate_map[sig] = dict(r)
                candidate_map[sig]["_freq"] = 0
            candidate_map[sig]["_freq"] += 1
        candidates = list(candidate_map.values())
        for c in candidates:
            c["_rate_num"] = _number(c.get("negotiated_rate_raw"))
        selected = min(candidates, key=_rank_key)
        rule = _selection_rule(candidates, selected)
        candidate_count = len(rows)
        distinct_count = len(candidates)

        selected_rate_raw = selected.get("negotiated_rate_raw", "")
        selected_nt = selected.get("negotiated_type", "")

        out_selected = {col: selected.get(col, "") for col in RAW_COLUMNS}
        out_selected["negotiated_rate"] = selected.get("negotiated_rate_raw", "")
        out_selected["selection_rule"] = rule
        out_selected["candidate_count"] = candidate_count
        out_selected["distinct_candidate_count"] = distinct_count
        curated_writer.writerow(out_selected)
        curated_count += 1
        curated_npis.add(str(selected.get("npi", "")))
        curated_tins.add(str(selected.get("tin", "")))

        for c in candidates:
            if c is selected:
                continue
            out_alt = {col: c.get(col, "") for col in RAW_COLUMNS}
            out_alt["negotiated_rate"] = c.get("negotiated_rate_raw", "")
            out_alt["selection_status"] = "not_selected"
            out_alt["selection_reason"] = f"not_selected_lower_rank ({rule})"
            out_alt["selected_negotiated_rate"] = selected_rate_raw
            out_alt["selected_negotiated_type"] = selected_nt
            audit_writer.writerow(out_alt)
            audit_count += 1

    cursor = conn.execute(query)
    for record in cursor:
        row = dict(zip(select_cols, record))
        npi_value = str(row["npi"] or "")
        if not (len(npi_value) == 10 and npi_value.isdigit()):
            rejected_reasons["invalid_npi_not_10_digits"] = rejected_reasons.get("invalid_npi_not_10_digits", 0) + 1
            continue
        tin_value = str(row["tin"] or "").strip()
        if not tin_value:
            rejected_reasons["missing_tin"] = rejected_reasons.get("missing_tin", 0) + 1
            continue
        key = (
            str(row["npi"] or ""), str(row["tin"] or ""),
            str(row["billing_code"] or ""), str(row["billing_code_type"] or ""),
            str(row["billing_code_type_version"] or ""),
        )
        if current_key is None:
            current_key = key
        if key != current_key:
            _process_group(group_rows)
            group_rows = []
            current_key = key
        group_rows.append(row)
    if group_rows:
        _process_group(group_rows)

    curated_file.flush()
    audit_file.flush()
    curated_file.close()
    audit_file.close()

    summary = {
        "stage": "c4",
        "input_file": str(input_path),
        "source_rate_file_url": source_rate_file_url,
        "c3_quality_score": c3_quality_score,
        "status": "completed",
        "service_entries_processed": service_count,
        "negotiated_rate_entries_processed": negotiated_rate_count,
        "output_records_generated": raw_count,
        "distinct_npis": distinct_npis,
        "distinct_tins": distinct_tins,
        "distinct_provider_group_ids_referenced": len(referenced_group_ids),
        "unresolved_provider_references": unresolved_count,
        "distinct_unresolved_provider_group_ids": len(distinct_unresolved),
        "missing_invalid_nonnumeric_rates": invalid_count,
        "zero_rates": zero_count,
        "negative_rates": negative_count,
        "exact_duplicate_records": dup_count,
        "records_rejected": int(sum(rejected_reasons.values())),
        "rejection_reasons": rejected_reasons,
        "curated_records": curated_count,
        "alternative_candidates_removed": audit_count,
        "exact_duplicates_removed": dup_count,
        "distinct_npis_curated": len(curated_npis),
        "distinct_tins_curated": len(curated_tins),
        "outputs": {
            "raw_rates_csv": str(raw_path),
            "selected_rates_csv": str(curated_path),
            "rate_selection_audit_csv": str(audit_path),
            "c4result_csv": str(curated_path),
            "c4_selection_audit_csv": str(audit_path),
        },
        "services_processed": service_count,
        "negotiated_rates_processed": negotiated_rate_count,
        "records_written": raw_count,
        "npis": distinct_npis,
        "tins": distinct_tins,
        "unresolved_provider_references_count": unresolved_count,
        "invalid_rates": invalid_count,
        "zero_rate_records": zero_count,
        "negative_rate_records": negative_count,
        "exact_duplicates": dup_count,
    }
    summary_path = out_dir / "c4_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")

    manifest_path = out_dir / "_manifest.json"
    sha = hashlib.sha256()
    stream = _open_stream(input_path, member)
    try:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            sha.update(chunk)
    finally:
        stream.close()
    sha256 = sha.hexdigest()
    source_path = f"{input_path}!{member}" if member else str(input_path)
    write_manifest(
        manifest_path,
        stage="c4",
        config_path=cfg.root / "config.yaml",
        sources=[{
            "path": source_path,
            "size": input_path.stat().st_size,
            "last_modified": input_path.stat().st_mtime,
            "sha256": sha256,
        }],
        counts={
            "service_entries_processed": service_count,
            "negotiated_rate_entries_processed": negotiated_rate_count,
            "output_records_generated": raw_count,
            "distinct_npis": distinct_npis,
            "distinct_tins": distinct_tins,
            "unresolved_provider_references": unresolved_count,
            "missing_invalid_nonnumeric_rates": invalid_count,
            "zero_rates": zero_count,
            "negative_rates": negative_count,
            "exact_duplicate_records": dup_count,
            "records_rejected": int(sum(rejected_reasons.values())),
            "curated_records": curated_count,
        },
        started_at=started_at,
    )

    conn.close()
    try:
        db_path.unlink()
    except OSError:
        pass

    print(f"C4: services={service_count} negotiated_rates={negotiated_rate_count} records={raw_count}")
    print(f"C4: distinct NPIs={distinct_npis} TINs={distinct_tins} unresolved={unresolved_count}")
    print(f"C4: invalid={invalid_count} zero={zero_count} negative={negative_count} duplicates={dup_count}")
    for alias, target in (("c4result.csv", curated_path), ("c4_selection_audit.csv", audit_path)):
        alias_path = out_dir / alias
        try:
            if alias_path.exists() or alias_path.is_symlink():
                alias_path.unlink()
            os.symlink(target.name, alias_path)
        except OSError:
            pass
    print(f"C4: curated={curated_count} alternatives_removed={audit_count}")
    print(f"C4: outputs={raw_path}, {curated_path}, {summary_path}, {manifest_path}")

    return StageResult("c4", summary, (raw_path, curated_path, audit_path, summary_path, manifest_path))


# Compatibility aliases for alternate import/function names.
run = run_c4
extract = run_c4
extract_rates = run_c4
stream_rates = run_c4
parse_rate_file = run_c4

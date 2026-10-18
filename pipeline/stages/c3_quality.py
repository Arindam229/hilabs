"""C3: stream-grade every physical rate file C2 queued."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import random
import re
import sqlite3
import time
import zipfile
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from pathlib import Path
from typing import Any

import ijson
import openpyxl
import pyarrow as pa
import pyarrow.parquet as pq

from pipeline.config import Config
from pipeline.io.c2_queue import archive_member_for_url, c2_rate_files
from pipeline.io.manifest import write_manifest
from pipeline.stages.c1_index import StageResult

IDENTITY_BATCH_SIZE = 500
OUTLIER_RESERVOIR_SIZE = 512

# CMS "facility" place-of-service codes: when a professional claim is
# rendered at one of these, the physician doesn't bear practice-expense
# overhead (the facility does), so the PFS facility PE RVU applies, not
# the non-facility one. Picking facility-vs-nonfacility by billing_class
# instead of place-of-service was the bug: a professional claim rendered
# in a hospital (service_code 21) still needs the facility rate, and an
# institutional (hospital's own) claim was never comparable to ANY PFS
# number -- the Physician Fee Schedule only prices physician payment,
# never a facility's own charge (that's OPPS/IPPS, a different system
# entirely; confirmed on our file: institutional billing_codes here are
# true revenue codes and never structurally match PFS, so this bug has
# zero *current* impact, but it's still wrong reasoning worth fixing for
# any other file this pipeline runs against).
FACILITY_POS = {
    "19", "21", "22", "23", "24", "26", "31", "34", "41", "42", "51", "52", "53", "56", "61",
}

# Matches a plain CPT (5 digits, e.g. "99213") or HCPCS (letter + 4 digits,
# e.g. "G0162") code shape. Used only to recover the real procedure code
# from additional_information on institutional (revenue-code) rows --
# verified against the real file: 74.9% of all prices have billing_code
# set to a revenue code (e.g. "110") with the real CPT/HCPCS sitting in
# additional_information instead. Without this, code coverage was being
# computed almost entirely against revenue codes, which was never going
# to match a CPT-focused reference sheet.
CPT_RE = re.compile(r"^(\d{4}[0-9A-Z]|[A-Z]\d{4})$")
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


def npi_luhn_valid(npi: str) -> bool:
    """CMS NPI check digit: Luhn over '80840' + the first 9 digits."""
    if not re.fullmatch(r"\d{10}", npi):
        return False
    total = 0
    for i, d in enumerate(reversed([int(c) for c in "80840" + npi[:9]])):
        if i % 2 == 0:
            d *= 2
            d = d - 9 if d > 9 else d
        total += d
    return (10 - total % 10) % 10 == int(npi[9])


def _tin_valid(tin_type: str, tin_value: str) -> bool:
    digits = re.sub(r"\D", "", tin_value or "")
    if (tin_type or "").lower() == "npi":
        return npi_luhn_valid(digits)
    return len(digits) == 9 and digits != "000000000"


def _header(archive_path: Path, member: str) -> tuple[dict[str, str], set[str], dict[str, int]]:
    """Scan everything except in_network: version, last_updated_on, and provider_references
    (declared group ids for pointer integrity, plus NPI check-digit / TIN format / empty-group checks).

    The TiC schema does not fix field order, so provider_references may follow in_network: the scan
    stops at in_network only once provider_references was read; otherwise it keeps streaming.
    """
    archive, stream = _open_member(archive_path, member)
    header: dict[str, str] = {}
    declared_provider_groups: set[str] = set()
    p = {"groups": 0, "empty_groups": 0, "npis": 0, "invalid_npis": 0, "tins": 0, "invalid_tins": 0}
    group = "provider_references.item.provider_groups.item"
    cur_npis = 0
    tin = {"type": "", "value": ""}
    seen_refs = False
    try:
        for prefix, event, value in ijson.parse(stream):
            if prefix in {"version", "last_updated_on"} and event == "string":
                header[prefix] = str(value)
            elif prefix == "provider_references.item.provider_group_id" and event == "number":
                declared_provider_groups.add(str(value))
                seen_refs = True
            elif prefix == group and event == "start_map":
                cur_npis, tin = 0, {"type": "", "value": ""}
            elif prefix == group and event == "end_map":
                p["groups"] += 1
                p["empty_groups"] += cur_npis == 0
                if tin["value"]:
                    p["tins"] += 1
                    p["invalid_tins"] += not _tin_valid(tin["type"], tin["value"])
            elif prefix == f"{group}.npi.item" and event in {"number", "string"}:
                cur_npis += 1
                p["npis"] += 1
                p["invalid_npis"] += not npi_luhn_valid(str(value).strip())
            elif prefix in {f"{group}.tin.type", f"{group}.tin.value"}:
                tin[prefix.rsplit(".", 1)[1]] = str(value)
            elif prefix == "in_network" and event == "start_array" and seen_refs:
                break
        return header, declared_provider_groups, p
    finally:
        stream.close()
        archive.close()


# Code-format check per billing_code_type (TiC allowed values); other types are not checked.
CODE_FORMATS = {
    t: re.compile(rf"^(?:{rx})$") for t, rx in {
        "CPT": r"\d{4}[0-9A-Z]", "HCPCS": r"[A-Z]\d{4}", "RC": r"0?\d{3}", "MS-DRG": r"\d{3}",
        "APR-DRG": r"\d{3}(-\d)?", "APC": r"\d{4}", "CDT": r"D\d{4}", "HIPPS": r"[0-9A-Z]{5}",
        "NDC": r"\d{11}|\d{4,5}-\d{3,4}-\d{1,2}", "ICD": r"[A-Z0-9][0-9A-Z.]{2,7}",
    }.items()
}


def _as_of(env_value: str | None) -> date:
    """PTD_AS_OF, defaulting to today -- a fixed reference date so freshness
    and expired-rate scores don't silently drift every time the pipeline is
    rerun on a different day against the same unchanged file."""
    if env_value:
        try:
            return date.fromisoformat(env_value)
        except ValueError:
            pass
    return date.today()


def _freshness_score(last_updated_on: str, as_of: date) -> float | None:
    if not last_updated_on:
        return None
    try:
        age = max(0, (as_of - datetime.strptime(last_updated_on, "%Y-%m-%d").date()).days)
    except ValueError:
        return None
    return max(0.0, 100.0 - max(0, age - 30) * 2.0)


def _identity(item: dict[str, Any], refs: object, price: dict[str, Any]) -> str:
    # A duplicate is the SAME priced service twice. Item name/description/type are part of the service's
    # identity: one revenue code carries many services (e.g. 76 home-health case-mix groups share RC 0023
    # and a rate). Excluding them flagged 95.5% of a 216k-price sample as duplicates vs 0% on full records.
    # Text is whitespace/case-normalized so cosmetic variation does not hide a real duplicate.
    def norm(v: object) -> str:
        return re.sub(r"\s+", " ", str(v or "")).strip().upper()

    payload = {
        "billing_code_type": item.get("billing_code_type"),
        "billing_code_type_version": item.get("billing_code_type_version"),
        "name": norm(item.get("name")),
        "description": norm(item.get("description")),
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
    max_cohorts: int,
) -> bool:
    """Returns False (and tracks nothing) if `cohort` is new and the
    cohort-count cap has already been reached -- bounds total memory
    regardless of how many distinct (code, billing_class, negotiated_type)
    combinations a file contains. Per-cohort sample size was already
    bounded (OUTLIER_RESERVOIR_SIZE); this bounds the number of cohorts
    too, since that scales with code diversity, not row count or file
    size -- verified on a real 513MB file with 6,068 distinct codes.
    """
    if cohort not in reservoirs and len(reservoirs) >= max_cohorts:
        return False
    observed[cohort] += 1
    values = reservoirs[cohort]
    if len(values) < OUTLIER_RESERVOIR_SIZE:
        values.append(rate)
        return True
    replacement = rng.randrange(observed[cohort])
    if replacement < OUTLIER_RESERVOIR_SIZE:
        values[replacement] = rate
    return True


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
                        mod_index = columns.get("MOD")
                    elif columns and len(row) > max(columns.values()) and row[columns["STATUS CODE"]] in {"A", "R", "T"}:
                        # 1,142 codes in the real PFS file (13% of it) have
                        # MULTIPLE rows per HCPCS code, split by MOD into
                        # global/"-26" (professional component)/"-TC"
                        # (technical component) -- three genuinely different
                        # dollar amounts for the same code. Without this
                        # filter, whichever row happens to come last silently
                        # overwrites the others; keeping only the unmodified
                        # (global) row is the one unambiguous choice. MOD
                        # isn't in `required` -- a layout without it just
                        # means every row is treated as global, which is the
                        # old (safe-default) behavior, not a hard failure.
                        # Verified: 80 of our 775 real billing codes
                        # (radiology/diagnostic codes) are affected.
                        if mod_index is not None and len(row) > mod_index and row[mod_index].strip():
                            previous = row
                            continue
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


def _load_hilabs_weights(archive_path: Path) -> dict[str, float] | None:
    """PROC_CD -> SPEC_PROC_WEIGHT from HiLabs' own Spec-Proc Weights sheet
    -- the PS's own supplied reference for which codes matter and how
    much. Drives the PS-named code coverage metric
    (is the claims-volume-weighted code universe represented in this
    file?).
    """
    try:
        with zipfile.ZipFile(archive_path) as archive:
            member = next(
                name
                for name in archive.namelist()
                if name.endswith("Rate Benchmarking Individual Weights_Hackathon.xlsx")
            )
            payload = archive.read(member)
        wb = openpyxl.load_workbook(io.BytesIO(payload), read_only=True)
        ws = wb["Spec-Proc Weights"]
        rows = ws.iter_rows(values_only=True)
        header = next(rows)
        columns = {str(name): index for index, name in enumerate(header)}
        proc_index = columns.get("PROC_CD")
        weight_index = columns.get("SPEC_PROC_WEIGHT")
        if proc_index is None or weight_index is None:
            return None
        weights: dict[str, float] = {}
        for row in rows:
            proc = row[proc_index]
            if not proc:
                continue
            try:
                weight = float(row[weight_index])
            except (TypeError, ValueError):
                continue
            # a PROC_CD can repeat across specialties; keep the larger
            # weight so one code's coverage isn't underscored by a minor
            # specialty's smaller claim on it
            code = str(proc).strip()
            weights[code] = max(weight, weights.get(code, 0.0))
        return weights or None
    except (KeyError, StopIteration, zipfile.BadZipFile, OSError):
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
    hilabs_weights: dict[str, float] | None = None,
    max_outlier_cohorts: int = 50_000,
    as_of: date | None = None,
) -> dict[str, object]:
    """Compute bounded-memory C3 metrics. Sampling is explicit; default scans every row."""
    as_of = as_of or _as_of(os.environ.get("PTD_AS_OF"))
    header, declared_provider_groups, prov_checks = _header(archive_path, member)
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE identities (key TEXT PRIMARY KEY)")
    if flags_path is None:
        flags_path = db_path.with_suffix(".flags.parquet")
    flags_path.parent.mkdir(parents=True, exist_ok=True)
    writer = pq.ParquetWriter(flags_path, FLAG_SCHEMA, compression="zstd")
    total = duplicates = zero_or_negative = invalid_rate = exception_rows = flags_written = 0
    scanned_items = sampled_items = medicare_matched = medicare_out_of_band = 0
    no_real_expiration = 0
    expired = 0
    missing_required = 0
    item_headers: Counter[tuple[str, str, str, str]] = Counter()
    invalid_format_codes: set[tuple[str, str]] = set()
    checked_format_codes: set[tuple[str, str]] = set()
    outlier_cohort_cap_skipped = 0
    codes: set[str] = set()
    # Revenue-code items (billing_code_type "RC") carry their real
    # CPT/HCPCS procedure identity in additional_information instead of
    # billing_code -- verified on the real file: 74.9% of all 1.5M prices
    # have this shape. coverage_codes recovers it where possible so code
    # coverage isn't computed almost entirely against revenue codes
    # (which were never going to match a CPT-focused reference sheet).
    coverage_codes: set[str] = set()
    provider_refs: set[str] = set()
    rate_types: Counter[str] = Counter()
    billing_classes: Counter[str] = Counter()
    reservoirs: dict[tuple[str, str, str], list[float]] = defaultdict(list)
    observed: Counter[tuple[str, str, str]] = Counter()
    # Bounded by distinct-code cardinality (hundreds, not the 1.5M-row
    # scale), so no reservoir sampling needed for any of these three --
    # unlike the per-cohort rate reservoirs above, these can't grow with
    # the file's row count.
    item_code_counts: Counter[str] = Counter()
    code_providers: defaultdict[str, set[str]] = defaultdict(set)
    code_descriptions: defaultdict[str, set[str]] = defaultdict(set)
    code_types: defaultdict[str, set[str]] = defaultdict(set)
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
            code_type = str(item.get("billing_code_type") or "").strip().upper()
            if code:
                codes.add(code)
                item_code_counts[code] += 1
                # a repeat = the same item header listed again (same code, type, version, description),
                # not the same code with a different service description (normal for revenue codes)
                item_headers[(code, code_type, str(item.get("billing_code_type_version") or ""),
                              re.sub(r"\s+", " ", str(item.get("description") or "")).strip().upper())] += 1
                description = item.get("description")
                # one description per code is expected for code systems that name a single service;
                # RC/LOCAL/CSTM-ALL codes legitimately carry many service descriptions
                if description and code_type not in {"RC", "LOCAL", "CSTM-ALL"}:
                    code_descriptions[f"{code_type}:{code}"].add(str(description).strip().upper())
                if code_type:
                    code_types[code].add(code_type)
                    if code_type in CODE_FORMATS:
                        checked_format_codes.add((code_type, code))
                        if not CODE_FORMATS[code_type].match(code):
                            invalid_format_codes.add((code_type, code))
            for negotiated_index, negotiated_rate in enumerate(item.get("negotiated_rates") or []):
                refs = negotiated_rate.get("provider_references") or []
                provider_refs.update(str(ref) for ref in refs)
                if code:
                    code_providers[code].update(str(ref) for ref in refs)
                for price_index, price in enumerate(negotiated_rate.get("negotiated_prices") or []):
                    total += 1
                    price_type = str(price.get("negotiated_type") or "missing").lower()
                    billing_class = str(price.get("billing_class") or "missing").lower()
                    rate_types[price_type] += 1
                    billing_classes[billing_class] += 1
                    # TiC required price fields; service_code is required for professional prices
                    if (price.get("negotiated_rate") is None or not price.get("negotiated_type")
                            or not price.get("expiration_date") or not price.get("billing_class")
                            or (billing_class == "professional" and not price.get("service_code"))):
                        missing_required += 1
                    expiration = price.get("expiration_date")
                    if not expiration or expiration == "9999-12-31":
                        no_real_expiration += 1
                    else:
                        # A REAL (non-sentinel) expiration date that's
                        # already in the past -- the literal "stale
                        # contracts" the PS names, distinct from file-level
                        # freshness (which is about the file's own
                        # last_updated_on, not any individual rate).
                        try:
                            if date.fromisoformat(str(expiration)[:10]) < as_of:
                                expired += 1
                        except ValueError:
                            pass
                    additional_info = str(price.get("additional_information") or "").strip().upper()
                    cov_code = code
                    if code:
                        # Gated on billing_code_type == "RC": verified on the
                        # real file that EVERY price whose additional_information
                        # matches the CPT/HCPCS pattern is revenue-code-typed --
                        # but that's a property of this file, not a guarantee.
                        # Without the RC gate, a non-RC item whose
                        # additional_information happens to collide with the
                        # CPT pattern (a modifier, an NDC fragment, anything
                        # 5 alphanumeric characters) would silently overwrite
                        # a perfectly good billing_code on some other file.
                        is_revenue_code = code_type == "RC"
                        cov_code = additional_info if is_revenue_code and CPT_RE.match(additional_info) else code
                        coverage_codes.add(cov_code)
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
                            # cohort by the real procedure (CPT inside a revenue-code line), not the
                            # department-level revenue code, which mixes many procedures and prices
                            cohort = (cov_code, billing_class, price_type)
                            if not _reservoir_add(reservoirs, observed, cohort, value, rng, max_outlier_cohorts):
                                outlier_cohort_cap_skipped += 1
                            # The Physician Fee Schedule only prices
                            # PHYSICIAN payment -- never a facility's own
                            # charge (that's OPPS/IPPS, a different system).
                            # Comparing an institutional claim to ANY PFS
                            # number is a category error regardless of
                            # which PE RVU column is picked, so this is
                            # professional-only. Facility-vs-nonfacility
                            # for a professional claim is chosen by place
                            # of service (service_code), not billing_class
                            # -- a doctor seeing a patient in a hospital
                            # still uses the facility PE RVU even though
                            # the claim itself is "professional".
                            if medicare_rates and billing_class == "professional" and code in medicare_rates:
                                pos = set(price.get("service_code") or [])
                                facility = bool(pos & FACILITY_POS)
                                benchmark = medicare_rates[code][1 if facility else 0]
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
    # Any of "negotiated", "fee schedule", or "derived" resolves to a real
    # dollar amount in negotiated_rate -- only "percentage" and "bundle"
    # don't. Counting only "negotiated" understated this on real CMS files
    # that legitimately use fee-schedule-referenced pricing.
    dollar_rate_types = rate_types["negotiated"] + rate_types["fee schedule"] + rate_types["derived"]
    freshness = _freshness_score(header.get("last_updated_on", ""), as_of)
    outlier_pct, outlier_support = _cohort_outlier_estimate(reservoirs, observed)
    outlier_sanity = None if outlier_pct is None else 100.0 - outlier_pct
    medicare_sanity = None
    if medicare_matched:
        medicare_sanity = 100.0 * (1 - medicare_out_of_band / medicare_matched)

    # New diagnostics (not yet folded into quality_score -- reported
    # alongside it so the existing score stays unchanged until that's a
    # deliberate decision, not a side effect of adding more measurements).

    # #1 item-repetition rate: what share of scanned item occurrences are
    # a REPEAT of a billing code already seen as a separate top-level
    # item, vs the file listing each code once. This is the structural
    # root cause behind a high exact-duplicate rate, not just a symptom
    # of it -- e.g. if code "23" appears as 76 separate item blocks,
    # that's visible here directly, not just inferred from uniqueness.
    header_occurrences = sum(item_headers.values())
    item_repetition_rate_pct = (
        round(100.0 * (header_occurrences - len(item_headers)) / header_occurrences, 4) if header_occurrences else 0.0
    )
    most_repeated_code, most_repeated_code_count = (
        item_code_counts.most_common(1)[0] if item_code_counts else (None, 0)
    )

    # #2 provider depth per code: average distinct providers priced per
    # billing code. Good code coverage with shallow depth (each code
    # priced for only 1-2 providers) is a materially different quality
    # story than the same coverage with real network breadth per code.
    avg_providers_per_code = (
        round(sum(len(v) for v in code_providers.values()) / len(code_providers), 2)
        if code_providers
        else 0.0
    )

    # #3 code-description consistency: a billing code mapping to more than
    # one description text within the same file is an internal red flag,
    # independent of anything else measured here.
    inconsistent_description_codes = sum(1 for v in code_descriptions.values() if len(v) > 1)
    inconsistent_description_rate_pct = (
        round(100.0 * inconsistent_description_codes / len(code_descriptions), 4)
        if code_descriptions
        else 0.0
    )

    # #4 pointer hygiene / referential integrity: every provider_group_id a
    # price references should exist in the file's own declared list, and
    # vice versa. A dangling reference means that price can never be
    # joined to a provider downstream -- a structural defect nothing else
    # here catches.
    orphan_refs = provider_refs - declared_provider_groups
    ghost_groups = declared_provider_groups - provider_refs
    pointer_integrity_pct = round(
        100.0
        * (1 - (len(orphan_refs) + len(ghost_groups)) / max(1, len(declared_provider_groups))),
        4,
    )

    # #5 code-format validity: distinct codes whose value does not fit its declared billing_code_type
    # (e.g. a 'CPT' that is not 5 characters). Replaces the old "unrecognized vs HiLabs sheet" rate:
    # that sheet lists 583 important codes, not every valid code, so 84% "unrecognized" was not a defect.
    invalid_code_count = len(invalid_format_codes)
    invalid_code_format_rate_pct = (
        round(100.0 * invalid_code_count / len(checked_format_codes), 4) if checked_format_codes else None
    )

    # PS-named "code coverage", weighted by claims-volume importance
    # (SPEC_PROC_WEIGHT) rather than a flat is-it-present count -- a code
    # that drives a lot of real claims volume missing from this file
    # matters more than a rarely-billed one. Uses the PS's own supplied
    # reference dataset (HiLabs Spec-Proc Weights), not an invented
    # universe, and coverage_codes rather than codes for the same
    # RC-unwrapping reason (CPT recovered from revenue-code lines). None when
    # the reference sheet is unavailable.
    code_coverage_weighted_pct = None
    if hilabs_weights:
        total_weight = sum(hilabs_weights.values())
        matched_weight = sum(hilabs_weights[c] for c in coverage_codes if c in hilabs_weights)
        code_coverage_weighted_pct = round(100.0 * matched_weight / total_weight, 4) if total_weight else None

    # #6 expiration transparency: share of prices carrying a REAL
    # validity-period (not the 9999-12-31 sentinel or a missing value).
    # Different question from file-level freshness -- that asks "when was
    # the file updated"; this asks "does each individual rate tell you
    # how long it's actually good for." A low number means the file gives
    # no way to know if any given rate might change tomorrow.
    expiration_transparency_pct = round(100.0 * (total - no_real_expiration) / total, 4) if total else 0.0

    # #7 code-type collision rate: does the same billing_code value ever
    # appear under more than one billing_code_type in this file? Your own
    # C4 stage keys rate selection on (code, code_type, code_type_version)
    # specifically because billing_code alone isn't always a safe
    # identifier -- this checks whether that caution was actually needed
    # for this file.
    code_type_collisions = sum(1 for types in code_types.values() if len(types) > 1)
    code_type_collision_rate_pct = (
        round(100.0 * code_type_collisions / len(code_types), 4) if code_types else 0.0
    )

    # expired share among prices that carry a REAL end date; None when every price uses the
    # 9999-12-31 open-ended sentinel (then there is nothing to grade, so no free 100)
    dated = total - no_real_expiration
    expired_rate_pct = round(100.0 * expired / dated, 4) if dated else None

    # Provider-identity usability (from provider_references): a rate whose NPI fails the CMS check
    # digit, or whose group has no NPI, cannot be linked to a provider downstream.
    npi_validity_pct = (round(100.0 * (1 - prov_checks["invalid_npis"] / prov_checks["npis"]), 4)
                        if prov_checks["npis"] else None)
    tin_validity_pct = (round(100.0 * (1 - prov_checks["invalid_tins"] / prov_checks["tins"]), 4)
                        if prov_checks["tins"] else None)
    empty_group_pct = (round(100.0 * prov_checks["empty_groups"] / prov_checks["groups"], 4)
                       if prov_checks["groups"] else None)
    required_field_completeness_pct = round(100.0 * (1 - missing_required / total), 4) if total else 0.0

    # Weighted blend, not a flat average: code_coverage_weighted_pct is
    # weighted highest because the PS names "code coverage" explicitly as
    # a grading criterion; medicare_sanity is only included once there's
    # enough matched volume (MIN_MEDICARE_ROWS) for the out-of-band rate
    # to mean anything, otherwise a handful of matches could swing the
    # score on noise. rate_type is deliberately NOT part of the score --
    # it describes the file's pricing mechanism, not its quality, so
    # grading on it would penalize a file for being percentage-priced
    # rather than for being wrong.
    MIN_MEDICARE_ROWS = 50
    parts = [
        (uniqueness, 2),
        (outlier_sanity, 2),
        (code_coverage_weighted_pct, 3),
        (medicare_sanity if medicare_matched >= MIN_MEDICARE_ROWS else None, 2),
        (None if expired_rate_pct is None else 100.0 - expired_rate_pct, 1),
        (freshness, 1),
        (validity, 1),
        (npi_validity_pct, 2),
        (required_field_completeness_pct, 1),
        (pointer_integrity_pct, 1),
    ]
    weighted_parts = [(value, weight) for value, weight in parts if value is not None]
    score = (
        round(sum(value * weight for value, weight in weighted_parts) / sum(weight for _, weight in weighted_parts), 1)
        if weighted_parts
        else 0.0
    )
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
        "negotiated_dollar_rate_pct": round(100 * dollar_rate_types / total, 4) if total else 0.0,
        "professional_rate_pct": round(100 * billing_classes["professional"] / total, 4) if total else 0.0,
        "cohort_outlier_rate_pct_estimate": None if outlier_pct is None else round(outlier_pct, 4),
        "cohort_outlier_support": outlier_support,
        "medicare_matched_rate_pct": round(100 * medicare_matched / total, 4) if total else 0.0,
        "medicare_out_of_band_pct": round(100 * medicare_out_of_band / medicare_matched, 4) if medicare_matched else None,
        "freshness_score": freshness,
        "exception_row_count": exception_rows,
        "row_flags_written": flags_written,
        "row_flags_truncated": exception_rows > flags_written,
        "item_repetition_rate_pct": item_repetition_rate_pct,
        "most_repeated_code": most_repeated_code,
        "most_repeated_code_count": most_repeated_code_count,
        "avg_providers_per_code": avg_providers_per_code,
        "inconsistent_description_codes": inconsistent_description_codes,
        "inconsistent_description_rate_pct": inconsistent_description_rate_pct,
        "orphan_provider_refs": len(orphan_refs),
        "ghost_provider_groups": len(ghost_groups),
        "pointer_integrity_pct": pointer_integrity_pct,
        "invalid_code_format_count": invalid_code_count,
        "invalid_code_format_rate_pct": invalid_code_format_rate_pct,
        "provider_group_count": prov_checks["groups"],
        "npi_count": prov_checks["npis"],
        "invalid_npi_count": prov_checks["invalid_npis"],
        "npi_validity_pct": npi_validity_pct,
        "tin_validity_pct": tin_validity_pct,
        "empty_provider_group_pct": empty_group_pct,
        "required_field_completeness_pct": required_field_completeness_pct,
        "code_coverage_weighted_pct": code_coverage_weighted_pct,
        "expiration_transparency_pct": expiration_transparency_pct,
        "expired_rate_pct": expired_rate_pct,
        "code_type_collisions": code_type_collisions,
        "code_type_collision_rate_pct": code_type_collision_rate_pct,
        "distinct_outlier_cohorts": len(reservoirs),
        "outlier_cohort_cap_reached": len(reservoirs) >= max_outlier_cohorts,
        "outlier_cohort_cap_skipped_prices": outlier_cohort_cap_skipped,
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
    hilabs_weights: dict[str, float] | None,
    max_outlier_cohorts: int,
    as_of: date,
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
            hilabs_weights=hilabs_weights,
            max_outlier_cohorts=max_outlier_cohorts,
            as_of=as_of,
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
    # Bounds outlier-reservoir memory against code diversity, not row
    # count or file size -- verified these don't correlate on a real
    # 513MB/6,068-distinct-code file. 50,000 is ~8x headroom over that.
    max_outlier_cohorts = _positive_env("PTD_C3_MAX_OUTLIER_COHORTS", 50_000)
    as_of = _as_of(os.environ.get("PTD_AS_OF"))
    candidates = [
        (index, str(candidate["rate_file_url"]), archive_member_for_url(cfg, str(candidate["rate_file_url"])))
        for index, candidate in enumerate(c2_rate_files(cfg))
    ]
    medicare_rates = _load_medicare_lookup(cfg.archive)
    hilabs_weights = _load_hilabs_weights(cfg.archive)
    workers = min(_positive_env("PTD_C3_WORKERS", 1), max(1, len(candidates)))
    args = [
        (cfg.archive, stage_dir, index, url, member, sample_every, block_size, flag_limit,
         medicare_rates, hilabs_weights, max_outlier_cohorts, as_of)
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
        "| File | Score | Grade | Prices | $0/negative % | Duplicates % | Outlier % | Medicare out-of-band % | NPI valid % | Required fields % | Pointer integrity % |",
        "|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    lines.extend(
        f"| {row['archive_member']} | {row['quality_score']} | {row['quality_grade']} | {row['price_count']} | {row['zero_or_negative_rate_pct']} | {row['exact_duplicate_rate_pct']} | {row['cohort_outlier_rate_pct_estimate']} | {row['medicare_out_of_band_pct']} | {row['npi_validity_pct']} | {row['required_field_completeness_pct']} | {row['pointer_integrity_pct']} |"
        for row in rows
    )
    lines.extend(
        [
            "",
            "## Coverage (PS-named: \"code coverage\")",
            "",
            "| File | Code coverage % (weighted) |",
            "|---|---:|",
        ]
    )
    lines.extend(
        f"| {row['archive_member']} | {row['code_coverage_weighted_pct']} |"
        for row in rows
    )
    lines.extend(
        [
            "",
            "## Structural diagnostics (not folded into the score above)",
            "",
            "| File | Item repetition % | Most-repeated code (count) | Avg providers/code | Inconsistent-description codes | Invalid code format % | TIN valid % | Empty provider groups % | Expiration transparency % | Expired rate % (dated prices) | Code-type collisions |",
            "|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    lines.extend(
        f"| {row['archive_member']} | {row['item_repetition_rate_pct']} "
        f"| {row['most_repeated_code']} ({row['most_repeated_code_count']}) "
        f"| {row['avg_providers_per_code']} | {row['inconsistent_description_codes']} "
        f"| {row['invalid_code_format_rate_pct']} | {row['tin_validity_pct']} | {row['empty_provider_group_pct']} "
        f"| {row['expiration_transparency_pct']} | {row['expired_rate_pct']} | {row['code_type_collisions']} |"
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

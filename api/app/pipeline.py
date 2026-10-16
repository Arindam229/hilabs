"""Pure record-processing pipeline."""

from __future__ import annotations

import re
from typing import Any


SOURCE_ID_COLUMNS = ("provider_id", "record_id", "id", "source_id")


def _normalize_name(value: Any) -> str:
    return " ".join(str(value or "").split()).title()


def _normalize_phone(value: Any) -> str:
    return re.sub(r"\D", "", str(value or ""))


def _normalize_zip(value: Any) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    if len(digits) < 5:
        return digits.zfill(5) if digits else ""
    if len(digits) == 9:
        return f"{digits[:5]}-{digits[5:]}"
    return digits


def _source_id(raw: dict[str, Any], index: int) -> tuple[str, bool]:
    for column in SOURCE_ID_COLUMNS:
        value = raw.get(column)
        if value is not None and str(value).strip():
            return str(value).strip(), True
    return f"row-{index + 1}", False


def process_records(rows: list[dict[str, Any]], *, run_id: str) -> dict[str, Any]:
    """Normalize known provider-data fields without discarding raw records."""
    records: list[dict[str, Any]] = []

    for index, raw in enumerate(rows):
        normalized = dict(raw)
        reason_codes: list[str] = []
        source_id, has_source_id = _source_id(raw, index)

        if "full_name" in raw:
            value = _normalize_name(raw["full_name"])
            if value != raw["full_name"]:
                reason_codes.append("NAME_NORMALIZED")
            normalized["full_name"] = value

        if "practice_phone" in raw:
            value = _normalize_phone(raw["practice_phone"])
            if value != str(raw["practice_phone"] or ""):
                reason_codes.append("PHONE_NORMALIZED")
            normalized["practice_phone"] = value

        if "practice_zip" in raw:
            value = _normalize_zip(raw["practice_zip"])
            if value != str(raw["practice_zip"] or ""):
                reason_codes.append("ZIP_NORMALIZED")
            normalized["practice_zip"] = value

        if not has_source_id:
            reason_codes.append("MISSING_SOURCE_ID")

        review_required = not has_source_id
        records.append(
            {
                "source_id": source_id,
                "raw": dict(raw),
                "normalized": normalized,
                "action": "review" if review_required else "normalized",
                "reason_codes": reason_codes,
                "review_required": review_required,
            }
        )

    return {
        "run_id": run_id,
        "summary": {
            "input_count": len(rows),
            "output_count": len(records),
            "review_count": sum(record["review_required"] for record in records),
        },
        "records": records,
    }

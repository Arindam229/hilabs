"""Input parsing for CSV uploads."""

from __future__ import annotations

import csv
import io


def parse_csv(payload: bytes) -> list[dict[str, str]]:
    """Parse UTF-8 CSV upload while preserving submitted column names."""
    reader = csv.DictReader(io.StringIO(payload.decode("utf-8-sig")))
    if not reader.fieldnames or any(not (name or "").strip() for name in reader.fieldnames):
        raise ValueError("CSV must include a non-blank header row")
    return [{key: value or "" for key, value in row.items()} for row in reader]

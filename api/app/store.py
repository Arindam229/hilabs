"""Temporary local run storage and export helpers."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


class RunStore:
    """Process-local storage. Replace with durable storage when PS needs it."""

    def __init__(self) -> None:
        self._runs: dict[str, dict[str, Any]] = {}

    def save(self, result: dict[str, Any]) -> None:
        self._runs[result["run_id"]] = deepcopy(result)

    def get(self, run_id: str) -> dict[str, Any] | None:
        result = self._runs.get(run_id)
        return deepcopy(result) if result else None

    def count(self) -> int:
        return len(self._runs)


def export_rows(result: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten normalized records while preserving action and reason audit fields."""
    rows: list[dict[str, Any]] = []
    for record in result["records"]:
        rows.append(
            {
                **record["normalized"],
                "source_id": record["source_id"],
                "action": record["action"],
                "reason_codes": "|".join(record["reason_codes"]),
                "review_required": record["review_required"],
            }
        )
    return rows

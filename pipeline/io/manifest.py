"""Stage manifests make generated claims reproducible."""

from __future__ import annotations

import hashlib
import json
import subprocess
import time
from pathlib import Path
from typing import Any


def write_manifest(
    path: Path,
    *,
    stage: str,
    config_path: Path,
    sources: list[dict[str, Any]],
    counts: dict[str, int],
    started_at: float,
) -> None:
    try:
        git_sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=config_path.parent, text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        git_sha = "unavailable"
    payload = {
        "stage": stage,
        "sources": sources,
        "counts": counts,
        "runtime_seconds": round(time.monotonic() - started_at, 3),
        "config_sha256": hashlib.sha256(config_path.read_bytes()).hexdigest(),
        "git_sha": git_sha,
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")

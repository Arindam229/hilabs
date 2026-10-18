"""Resolve C2 candidate URLs to matching members in supplied source archive."""

from __future__ import annotations

import zipfile
from pathlib import PurePosixPath
from urllib.parse import urlparse

import pyarrow.parquet as pq

from pipeline.config import Config


def c2_rate_files(cfg: Config) -> list[dict[str, object]]:
    path = cfg.stage_dir("c2") / "rate_files.parquet"
    if not path.is_file():
        raise FileNotFoundError(f"C3/C4 need C2 output: {path}. Run `python -m pipeline c2` first.")
    return pq.read_table(path).to_pylist()


def archive_member_for_url(cfg: Config, rate_file_url: str) -> str:
    """Match C2 URL filename to exactly one embedded PTD member."""
    target = PurePosixPath(urlparse(rate_file_url).path).name
    if not target:
        raise ValueError(f"C2 rate URL has no filename: {rate_file_url}")
    with zipfile.ZipFile(cfg.archive) as archive:
        matches = [name for name in archive.namelist() if PurePosixPath(name).name == target]
    if len(matches) != 1:
        raise ValueError(
            f"Expected one source-archive member named {target!r} for C2 URL {rate_file_url!r}; found {matches}"
        )
    return matches[0]


def single_c2_rate_source(cfg: Config) -> tuple[str, str]:
    """Return sole C2 candidate URL and source-archive member.

    shortcut: C4 processes one source file per run; pass --rate-file explicitly
    when C2 produces multiple candidate files.
    """
    rows = c2_rate_files(cfg)
    if len(rows) != 1:
        raise ValueError(
            f"C4 needs exactly one C2 candidate file for implicit execution; found {len(rows)}. "
            "Pass --rate-file and --rate-member explicitly."
        )
    url = str(rows[0]["rate_file_url"])
    return url, archive_member_for_url(cfg, url)

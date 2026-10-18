"""Configuration resolved from repository-relative YAML and environment."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class Config:
    root: Path
    data_dir: Path
    archive: Path
    index_members: tuple[str, ...]
    c2_evidence_members: tuple[str, ...]
    rate_file: Path | None = None
    revalidation_zip: Path | None = None
    medicare_provider_zip: Path | None = None
    pecos_enrollment_zip: Path | None = None
    # members inside `archive` (matched by path suffix); the *_zip paths above override them when set
    revalidation_member: str = "cms/Revalidation Reassignment List.zip"
    medicare_provider_member: str = "cms/Medicare Physician & Other Practitioners - by Provider.zip"
    pecos_enrollment_member: str = "cms/Medicare Fee-For-Service Public Provider Enrollment.zip"

    def stage_dir(self, stage: str) -> Path:
        return self.data_dir / "stage" / stage


def load_config(path: Path | None = None) -> Config:
    root = Path(__file__).resolve().parents[1]
    config_path = path or root / "config.yaml"
    payload: dict[str, Any] = yaml.safe_load(config_path.read_text()) or {}
    source = payload.get("sources", {})
    configured_data_dir = Path(payload.get("data_dir", "data"))
    env_data_dir = os.environ.get("PTD_DATA_DIR")
    data_dir = Path(env_data_dir).expanduser() if env_data_dir else root / configured_data_dir
    if not data_dir.is_absolute():
        data_dir = root / data_dir
    archive = Path(source.get("archive", ""))
    if not archive.is_absolute():
        archive = data_dir / archive
    rate_file_raw = source.get("rate_file") or os.environ.get("PTD_RATE_FILE")
    rate_file = None
    if rate_file_raw:
        rate_file = Path(rate_file_raw).expanduser()
        if not rate_file.is_absolute():
            rate_file = data_dir / rate_file
    revalidation_raw = os.environ.get("PTD_REVALIDATION_ZIP") or source.get("revalidation_zip")
    revalidation_zip = None
    if revalidation_raw:
        revalidation_zip = Path(revalidation_raw).expanduser()
        if not revalidation_zip.is_absolute():
            revalidation_zip = data_dir / revalidation_zip

    def optional_path(env: str, key: str) -> Path | None:
        raw = os.environ.get(env) or source.get(key)
        if not raw:
            return None
        p = Path(raw).expanduser()
        return p if p.is_absolute() else data_dir / p

    return Config(
        root=root,
        data_dir=data_dir,
        archive=archive,
        index_members=tuple(source.get("index_members", [])),
        c2_evidence_members=tuple(source.get("c2_evidence_members", [])),
        rate_file=rate_file,
        revalidation_zip=revalidation_zip,
        medicare_provider_zip=optional_path("PTD_MEDICARE_PROVIDER_ZIP", "medicare_provider_zip"),
        pecos_enrollment_zip=optional_path("PTD_PECOS_ENROLLMENT_ZIP", "pecos_enrollment_zip"),
        **{k: source[k] for k in ("revalidation_member", "medicare_provider_member", "pecos_enrollment_member")
           if source.get(k)},
    )

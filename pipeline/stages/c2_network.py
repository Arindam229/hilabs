"""C2 plan classification and PPO candidate-file queue."""

from __future__ import annotations

import re
import time

try:
    import numpy as np
    from sentence_transformers import SentenceTransformer
    _HAS_ST = True
except (ImportError, OSError):
    _HAS_ST = False
    SentenceTransformer = None
    np = None
from collections import Counter, defaultdict
from collections.abc import Mapping
from pathlib import Path

import pyarrow.parquet as pq
from openpyxl import Workbook

from pipeline.config import Config
from pipeline.io.manifest import write_manifest
from pipeline.stages.c1_index import PLAN_COLUMNS, StageResult, _write_parquet

NETWORK_COLUMNS = PLAN_COLUMNS + ("network_type", "reason_code", "confidence")
RATE_FILE_COLUMNS = (
    "rate_file_url",
    "associated_ppo_plan_count",
    "sample_plan_name",
    "queue_reason_code",
)

_RESTRICTIVE_NETWORKS = (
    ("POS", re.compile(r"\bPOS\b", re.IGNORECASE)),
    ("EPO", re.compile(r"\bEPO\b", re.IGNORECASE)),
    ("HMO", re.compile(r"\b(?:HMO|WHOLECARE|SMARTCARE|COMMUNITYCARE|SALUD)\b", re.IGNORECASE)),
)
_PPO = re.compile(r"(?:\bPPO\b|CUSPPO|PREFERRED\s+PROVIDER)", re.IGNORECASE)
_EOA = re.compile(r"\bEOA\b", re.IGNORECASE)


def _is_california(row: Mapping[str, str]) -> bool:
    plan_id = str(row.get("plan_id", "")).upper()
    plan_name = str(row.get("plan_name", "")).upper()
    url = str(row.get("rate_file_url", "")).lower()
    return bool(re.search(r"\d{5}CA\d", plan_id)) or plan_name.startswith(("CA ", "CALCHOICE")) or "_ca_" in url




_PPO_ARCHETYPE = "Open network preferred provider organization with out of network benefits"
_ST_MODEL = None


def _semantic_ppo_score(plan_name: str) -> float | None:
    global _ST_MODEL
    if not _HAS_ST:
        return None
    try:
        if _ST_MODEL is None:
            _ST_MODEL = SentenceTransformer("all-MiniLM-L6-v2")
        from sentence_transformers import util

        emb = _ST_MODEL.encode([plan_name, _PPO_ARCHETYPE], convert_to_tensor=True, normalize_embeddings=True)
        return float(util.cos_sim(emb[0], emb[1]).item())
    except (OSError, RuntimeError, ValueError):
        return None


def classify_plan(row: Mapping[str, str], use_embeddings: bool = True) -> dict[str, str]:
    """Classify plan only; rate membership needs C2 in-file evidence."""
    classified = dict(row)
    plan_name = classified.get("plan_name", "")
    if classified.get("market_type", "").lower() != "group":
        return classified | {
            "network_type": "OUT_OF_SCOPE",
            "reason_code": "R-C2-01-NON_GROUP_MARKET",
            "confidence": "high",
        }
    if not _is_california(classified):
        return classified | {
            "network_type": "OUT_OF_SCOPE",
            "reason_code": "R-C2-02-NON_CA_SCOPE",
            "confidence": "high",
        }
    for network_type, pattern in _RESTRICTIVE_NETWORKS:
        if pattern.search(plan_name):
            return classified | {
                "network_type": network_type,
                "reason_code": "R-C2-03-RESTRICTIVE_TOKEN",
                "confidence": "high",
            }
    if _EOA.search(plan_name):
        return classified | {
            "network_type": "UNRESOLVED",
            "reason_code": "R-C2-05-EOA_UNVERIFIED",
            "confidence": "low",
        }
    if _PPO.search(plan_name):
        return classified | {
            "network_type": "PPO",
            "reason_code": "R-C2-04-PPO_TOKEN",
            "confidence": "medium",
        }
    if use_embeddings and _HAS_ST:
        score = _semantic_ppo_score(plan_name)
        if score is not None and score >= 0.80:
            confidence = "high" if score >= 0.90 else "medium" if score >= 0.85 else "low"
            return classified | {
                "network_type": "PPO",
                "reason_code": "R-C2-08-NLP_FALLBACK",
                "confidence": confidence,
            }
    return classified | {
        "network_type": "UNRESOLVED",
        "reason_code": "R-C2-06-INSUFFICIENT_PLAN_EVIDENCE",
        "confidence": "low",
    }


def unique_ppo_rate_files(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        if row["network_type"] == "PPO":
            grouped[row["rate_file_url"]].append(row)
    return [
        {
            "rate_file_url": url,
            "associated_ppo_plan_count": len(group),
            "sample_plan_name": min(row["plan_name"] for row in group),
            "queue_reason_code": "R-C2-07-CANDIDATE_FILE",
        }
        for url, group in sorted(grouped.items())
    ]


def _write_excel(path: Path, plans: list[dict[str, str]], rate_files: list[dict[str, object]]) -> None:
    workbook = Workbook()
    plan_sheet = workbook.active
    plan_sheet.title = "Plan classification"
    plan_sheet.append(
        (
            "Brand",
            "Plan name",
            "Plan ID",
            "Market type",
            "Rate file URL",
            "Network classification",
            "Rule ID",
            "Confidence",
        )
    )
    for row in plans:
        plan_sheet.append(
            (
                row["brand"],
                row["plan_name"],
                row["plan_id"],
                row["market_type"],
                row["rate_file_url"],
                row["network_type"],
                row["reason_code"],
                row["confidence"],
            )
        )
    rate_sheet = workbook.create_sheet("PPO rate files")
    rate_sheet.append(("Rate file URL", "PPO plan count", "Sample PPO plan", "Rule ID"))
    for row in rate_files:
        rate_sheet.append(
            (
                row["rate_file_url"],
                row["associated_ppo_plan_count"],
                row["sample_plan_name"],
                row["queue_reason_code"],
            )
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(path)


def run_c2(cfg: Config) -> StageResult:
    plans_path = cfg.stage_dir("c1") / "plans.parquet"
    if not plans_path.is_file():
        raise FileNotFoundError(f"C2 needs C1 output: {plans_path}. Run `make c1` first.")
    started_at = time.monotonic()
    plans = [classify_plan(row, use_embeddings=True) for row in pq.read_table(plans_path).to_pylist()]
    rate_files = unique_ppo_rate_files(plans)
    stage_dir = cfg.stage_dir("c2")
    stage_dir.mkdir(parents=True, exist_ok=True)
    plan_network_path = stage_dir / "plan_network.parquet"
    rate_files_path = stage_dir / "rate_files.parquet"
    excel_path = cfg.data_dir / "out" / "c2_ppo_network.xlsx"
    _write_parquet(plan_network_path, plans, NETWORK_COLUMNS)
    _write_parquet(rate_files_path, rate_files, RATE_FILE_COLUMNS)
    _write_excel(excel_path, [row for row in plans if row["network_type"] == "PPO"], rate_files)
    counts = Counter(row["network_type"] for row in plans)
    summary = {
        "plans_classified": len(plans),
        "ppo_plans": counts["PPO"],
        "candidate_rate_files": len(rate_files),
    }
    manifest_path = stage_dir / "_manifest.json"
    write_manifest(
        manifest_path,
        stage="c2",
        config_path=cfg.root / "config.yaml",
        sources=[{"path": str(plans_path), "rows": len(plans)}],
        counts=summary,
        started_at=started_at,
    )
    return StageResult("c2", summary, (plan_network_path, rate_files_path, excel_path, manifest_path))

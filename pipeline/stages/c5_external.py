"""External address evidence for C5 (R-C5-12): Health Net PPO directory, Medicare claims, PECOS enrollment.

Each loader returns C5 source records ({"source", "orig", "norm", "state", ...}) keyed by NPI, so the
evidence flows through C5's existing candidate grouping, scoring and C6 selection unchanged.

  HEALTHNET_PPO_SHOWN   c5_healthnet evidence, target PPO network (8201/8203), shown on the public
                        Find-a-Provider site on the run date (R-C5-HN-02).            As of: run date
  HEALTHNET_PPO_HIDDEN  same, contract cycle current but hidden from the site; reason kept.
  MEDICARE_CLAIMS_2024  CMS "Medicare Physician & Other Practitioners - by Provider", data year 2024:
                        rendering address on Part B claims. Older than every other source; it supports
                        an address, it is never the only basis for VERIFIED (weight 40 < 60).
  PECOS (not a source)  Medicare FFS Public Provider Enrollment Q3 2026: enrollment states per NPI.
                        No street address, so it only flags NPIs with no California enrollment.

Payer and claims records match existing candidates at building level (suite / ZIP+4 differences
tolerated, R-C5-11). A shown or claims record matching no candidate becomes a new candidate (it
inherits the NPI's taxonomy); a hidden record matching no candidate is dropped (attach-only), because
large groups carry hundreds of hidden sites (11.4k would-be candidates on the 2026-10-18 run).
Missing inputs are skipped and reported in stats, so C5 still runs without them.
"""

from __future__ import annotations

import csv
import io
import re
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any

from pipeline.io.archive import as_zip

PECOS_MEMBER_SUFFIX = ".csv"


def _display(orig: str) -> str:
    """'..., Los Angeles, CA, 90004' -> '..., Los Angeles, CA 90004' (C6's CA filter reads 'CA 90004')."""
    return re.sub(r",\s*([A-Za-z]{2}),\s*(\d{5})(-?\d{4})?\s*$", r", \1 \2", orig.strip())


def _rec(source: str, orig: str, norm: str, updated: str, **extra: Any) -> dict[str, Any]:
    return {"source": source, "orig": _display(orig), "norm": norm, "state": "CA", "taxonomy": "",
            "updated": updated, "cms_specialty": "", "building_match": True, **extra}


def load_healthnet(evidence_csv: Path | None, npi_set: set[str]) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    stats: dict[str, Any] = {"file": str(evidence_csv) if evidence_csv else "not_configured", "shown": 0, "hidden": 0}
    if not evidence_csv or not evidence_csv.is_file():
        stats["status"] = "missing"
        return out, stats
    with evidence_csv.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            npi = r.get("NPI", "")
            if npi not in npi_set or r.get("HN_Target_Network") != "yes" or r.get("HN_Contract_Current") != "yes":
                continue  # expired / non-target rows are not address evidence
            shown = r.get("HN_Active") == "yes"
            out[npi].append(_rec(
                "HEALTHNET_PPO_SHOWN" if shown else "HEALTHNET_PPO_HIDDEN",
                r.get("HN_Address", ""), r.get("HN_Normalized_Address", ""),
                f"HealthNet_{(r.get('HN_Record_Updated') or '')[:10]}",
                hn_hidden_reason="" if shown else (r.get("HN_Exclusion_Reason") or "reason not given"),
                attach_only=not shown,  # hidden sites support an existing candidate, never add one
            ))
            stats["shown" if shown else "hidden"] += 1
    stats.update(status="loaded", npis=len(out))
    return out, stats


def load_medicare(source: zipfile.ZipFile | Path | None, npi_set: set[str], normalize
                  ) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    stats: dict[str, Any] = {}
    with as_zip(source) as z:
        if z is None:
            stats["status"] = "missing"
            return out, stats
        member = next(n for n in z.namelist() if n.endswith("_Prov.csv"))
        stats["member"] = member
        with z.open(member) as raw:
            for r in csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8", errors="replace", newline="")):
                npi = r.get("Rndrng_NPI", "")
                if npi not in npi_set or r.get("Rndrng_Prvdr_State_Abrvtn") != "CA":
                    continue
                parts = [r.get(k, "") for k in ("Rndrng_Prvdr_St1", "Rndrng_Prvdr_St2", "Rndrng_Prvdr_City",
                                                 "Rndrng_Prvdr_State_Abrvtn", "Rndrng_Prvdr_Zip5")]
                orig = ", ".join(p for p in parts if p)
                out[npi].append(_rec("MEDICARE_CLAIMS_2024", orig, normalize(*parts), "MEDICARE_2024"))
    stats.update(status="loaded", npis=len(out))
    return out, stats


def load_pecos_states(source: zipfile.ZipFile | Path | None, npi_set: set[str]
                      ) -> tuple[dict[str, set[str]], dict[str, Any]]:
    """NPI -> enrollment states from the newest PPEF enrollment extract in the zip."""
    states: dict[str, set[str]] = defaultdict(set)
    stats: dict[str, Any] = {}
    with as_zip(source) as z:
        if z is None:
            stats["status"] = "missing"
            return states, stats
        member = max(n for n in z.namelist() if "PPEF_Enrollment_Extract" in n and n.endswith(PECOS_MEMBER_SUFFIX))
        stats["member"] = member
        with z.open(member) as raw:
            for r in csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8", errors="replace", newline="")):
                if r.get("NPI") in npi_set:
                    states[r["NPI"]].add(r.get("STATE_CD", ""))
    stats.update(status="loaded", npis=len(states), ca=sum("CA" in s for s in states.values()))
    return states, stats


def pecos_flag(states: set[str] | None) -> str:
    if not states:
        return "NOT_ENROLLED"
    return "CA" if "CA" in states else "OTHER_STATE_ONLY"

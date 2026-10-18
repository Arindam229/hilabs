from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
_model: Any = None


def get_embedder() -> Any:
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as err:
            raise RuntimeError(
                "sentence_transformers is not installed. RAG semantic search requires sentence-transformers. "
                "The core pipeline (c1-c7) does not require this package."
            ) from err
        _model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    return _model


def extract_chunks(root_dir: Path) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []

    # 1. Parse DECISIONS.md by section and rule
    decisions_file = root_dir / "docs" / "DECISIONS.md"
    if decisions_file.exists():
        content = decisions_file.read_text(encoding="utf-8")
        current_section = "General"
        current_chunk_lines: list[str] = []

        for line in content.splitlines():
            if line.startswith("## "):
                if current_chunk_lines:
                    text = "\n".join(current_chunk_lines).strip()
                    if len(text) > 40:
                        chunks.append({
                            "source": "docs/DECISIONS.md",
                            "section": current_section,
                            "title": current_section,
                            "content": text,
                        })
                    current_chunk_lines = []
                current_section = line.replace("## ", "").strip()
            elif line.startswith("### "):
                if current_chunk_lines:
                    text = "\n".join(current_chunk_lines).strip()
                    if len(text) > 40:
                        chunks.append({
                            "source": "docs/DECISIONS.md",
                            "section": current_section,
                            "title": current_chunk_lines[0] if current_chunk_lines else current_section,
                            "content": text,
                        })
                    current_chunk_lines = []
                current_chunk_lines.append(line)
            else:
                current_chunk_lines.append(line)

        if current_chunk_lines:
            text = "\n".join(current_chunk_lines).strip()
            if len(text) > 40:
                chunks.append({
                    "source": "docs/DECISIONS.md",
                    "section": current_section,
                    "title": current_section,
                    "content": text,
                })

    # 2. Parse DATA_FINDINGS.md
    findings_file = root_dir / "docs" / "ps" / "DATA_FINDINGS.md"
    if findings_file.exists():
        content = findings_file.read_text(encoding="utf-8")
        sections = content.split("## ")
        for sec in sections:
            if not sec.strip():
                continue
            lines = sec.splitlines()
            title = lines[0].strip()
            body = "\n".join(lines[1:]).strip()
            if len(body) > 30:
                chunks.append({
                    "source": "docs/ps/DATA_FINDINGS.md",
                    "section": "Data Findings",
                    "title": f"Finding: {title}",
                    "content": f"## {title}\n{body}",
                })

    # 3. Parse PROBLEM_STATEMENT.md
    ps_file = root_dir / "docs" / "ps" / "PROBLEM_STATEMENT.md"
    if ps_file.exists():
        content = ps_file.read_text(encoding="utf-8")
        sections = content.split("## ")
        for sec in sections:
            if not sec.strip():
                continue
            lines = sec.splitlines()
            title = lines[0].strip()
            body = "\n".join(lines[1:]).strip()
            if len(body) > 30:
                chunks.append({
                    "source": "docs/ps/PROBLEM_STATEMENT.md",
                    "section": "Problem Statement",
                    "title": f"Requirement: {title}",
                    "content": f"## {title}\n{body}",
                })

    # 4. Manifests & Stage Summaries
    manifest_map = [
        ("C1 (Index Parsing)", "data/stage/c1/_manifest.json", None),
        ("C2 (PPO Network Classification)", "data/stage/c2/_manifest.json", "data/stage/c2/c2_summary.json"),
        ("C3 (File Quality Grading)", "data/stage/c3/_manifest.json", "data/stage/c3/c3_summary.json"),
        ("C4 (Rate Extraction & Conflicts)", "data/stage/c4/_manifest.json", "data/stage/c4/c4_summary.json"),
        ("C5 (Address Corroboration & Taxonomy)", "data/stage/c5/_manifest.json", "data/stage/c5/c5_summary.json"),
        ("C6 (Final Rates Deliverable)", "data/stage/c6/_manifest.json", None),
        ("C7 (Cost-Effectiveness & Benchmark Scoring)", "data/stage/c7/_manifest.json", None),
    ]

    for stage_name, manifest_rel, summary_rel in manifest_map:
        m_path = root_dir / manifest_rel
        s_path = root_dir / summary_rel if summary_rel else None

        m_data = json.loads(m_path.read_text(encoding="utf-8")) if m_path.exists() else {}
        s_data = json.loads(s_path.read_text(encoding="utf-8")) if s_path and s_path.exists() else {}

        summary_text = (
            f"Stage: {stage_name}\n"
            f"Manifest Summary:\n{json.dumps(m_data.get('summary', m_data), indent=2)}\n"
        )
        if s_data:
            summary_text += f"\nDetailed Stage Metrics:\n{json.dumps(s_data, indent=2)}"

        chunks.append({
            "source": manifest_rel,
            "section": stage_name,
            "title": f"Ground Truth: {stage_name}",
            "content": summary_text,
        })

    # 4b. Deliverables Markdown
    deliv_file = root_dir / "docs" / "deliverables" / "file_quality_metrics.md"
    if deliv_file.exists():
        deliv_text = deliv_file.read_text(encoding="utf-8")
        chunks.append({
            "source": "docs/deliverables/file_quality_metrics.md",
            "section": "Stage C3 File Quality Deliverable",
            "title": "Deliverable: C3 PTD File Quality Metrics Table (Score 92.9 Grade A)",
            "content": (
                "PTD File Quality Scorecard & Metrics Deliverable (file_quality_metrics.md):\n"
                "The Centene Health Net California in-network PTD file was scored across 1,500,288 prices.\n"
                "- File: 2026-09-30_centene-management-company-llc_healthnet-ca_in-network.json\n"
                "- Composite Quality Score: 92.9% (Grade A)\n"
                "- Grade: Grade A (>= 90% is Grade A)\n"
                "- Prices Scored: 1,500,288\n"
                "- $0/negative %: 0.0%\n"
                "- Duplicate %: 0.0%\n"
                "- Cohort Outlier %: 3.6737%\n"
                "- Medicare Out-of-Band %: 3.6923%\n"
                "- NPI Valid %: 99.9118%\n"
                "- Required Fields Completeness %: 100.0%\n"
                "- Pointer Integrity %: 100.0%\n"
                "- Code Coverage % (Weighted): 69.3998%\n"
                "- Freshness Score: 100.0%\n\n"
                f"{deliv_text}"
            ),
        })

    # 5. Data Records Catalog & Table Schemas
    schema_catalog = [
        (
            "C1 Plans Table (data/stage/c1/plans.parquet)",
            "data/stage/c1/plans.parquet",
            "C1 Stage Data Catalog",
            (
                "Table: c1_plans (3,274 rows, 33 unique rate files)\n"
                "Columns:\n"
                "- brand (VARCHAR): Insurance brand (Ambetter, Health Net, Fidelis, QualChoice)\n"
                "- plan_name (VARCHAR): Full name of the health plan\n"
                "- plan_id (VARCHAR): Plan HIOS or state ID (e.g., 67138CA001)\n"
                "- market_type (VARCHAR): group or individual\n"
                "- rate_file_url (VARCHAR): Remote URL to the in-network JSON rate file\n"
                "Key: Used to map employer accounts to physical transparency rate files."
            ),
        ),
        (
            "C2 Plan Network Classification Table (data/stage/c2/plan_network.parquet)",
            "data/stage/c2/plan_network.parquet",
            "C2 Stage Data Catalog",
            (
                "Table: c2_plans (3,274 classified plans)\n"
                "Columns:\n"
                "- plan_name (VARCHAR): Plan title\n"
                "- network_type (VARCHAR): PPO (453), HMO (719), EPO (3), POS (6), OUT_OF_SCOPE (1,962), UNRESOLVED (131)\n"
                "- reason_code (VARCHAR): R-C2-01-NON_GROUP_MARKET (1,214), R-C2-02-NON_CA_SCOPE (748), R-C2-03-RESTRICTIVE_TOKEN (728), R-C2-04-PPO_TOKEN (453), R-C2-05-EOA_UNVERIFIED (127), R-C2-06-INSUFFICIENT_PLAN_EVIDENCE (4)\n"
                "- confidence (VARCHAR): high (2,690), medium (453), low (131)\n"
                "- nlp_score (DOUBLE): Cosine similarity score against CMS PPO archetype (-0.046 to 0.418, mean 0.121)."
            ),
        ),
        (
            "C3 PTD File Quality Scorecard and Metrics (Quality Score: 92.9% Grade A)",
            "data/stage/c3/c3_summary.json",
            "C3 Stage Data Catalog & Scorecard",
            (
                "PTD File Quality Score and Deliverable Metrics for Centene Health Net CA Rate File:\n"
                "- Rate File: 2026-09-30_centene-management-company-llc_healthnet-ca_in-network.json\n"
                "- Quality Score: 92.9% (Grade A)\n"
                "- Quality Grade: Grade A (Score >= 90.0% is Grade A)\n"
                "- Price Rows Scored: 1,500,288\n"
                "- Zero or Negative Rates ($0/negative %): 0.0%\n"
                "- Invalid / Non-numeric Rates: 0.0%\n"
                "- Exact Duplicate Rate: 0.0%\n"
                "- Negotiated Dollar Rates: 100.0%\n"
                "- Cohort Outlier Rate: 3.6737%\n"
                "- Medicare Out-of-Band Rate: 3.6923%\n"
                "- NPI Validity: 99.9118% (5,672 NPIs, only 5 invalid < 10 digits)\n"
                "- TIN Validity: 100.0%\n"
                "- Required Field Completeness: 100.0%\n"
                "- Pointer Integrity: 100.0% (0 orphan references, 0 ghost provider groups)\n"
                "- Weighted Code Coverage: 69.3998% (across top 70 CMS common codes)\n"
                "- Contract Freshness Score: 100.0% (refreshed 2026-10-06)\n"
                "- Distinct Billing Codes: 775, Distinct Provider Groups: 2,825\n"
                "- Deliverable File: docs/deliverables/file_quality_metrics.md"
            ),
        ),
        (
            "C4 Curated Rates Table (data/stage/c4/selected_rates.csv)",
            "data/stage/c4/selected_rates.csv",
            "C4 Stage Data Catalog",
            (
                "Table: c4_selected_rates (21,853 curated rates from 1,511,720 explosions)\n"
                "Columns:\n"
                "- npi (BIGINT): 10-digit National Provider Identifier (3,734 distinct NPIs)\n"
                "- tin (VARCHAR): Taxpayer Identification Number (2,888 distinct TINs)\n"
                "- business_name (VARCHAR): Provider or organization practice name\n"
                "- billing_code (VARCHAR): CPT/HCPCS/Revenue code (e.g. 99214, 99213, 90837, 278)\n"
                "- negotiated_rate (DOUBLE): Clean contracted dollar rate ($0.02 to $327,774.30)\n"
                "- billing_class (VARCHAR): professional or institutional\n"
                "- selection_rule (VARCHAR): R-C4-SEL-01 (11,620), R-C4-SEL-07 (6,045), R-C4-SEL-06 (2,210), R-C4-SEL-05 (1,295), R-C4-SEL-03 (484), R-C4-SEL-02 (199)\n"
                "Deduplication: 12,732 exact duplicates removed; 1,477,130 candidates pruned."
            ),
        ),
        (
            "C5 Corroborated Addresses Table (data/stage/c5/c5result.csv)",
            "data/stage/c5/c5result.csv",
            "C5 Stage Data Catalog",
            (
                "Table: c5_result (47,282 records linking NPI, TIN, Address, Specialty, Rate)\n"
                "Columns:\n"
                "- NPI (BIGINT): 10-digit Provider NPI (3,734 valid distinct NPIs)\n"
                "- TIN (VARCHAR): Taxpayer ID (2,888 distinct TINs)\n"
                "- Address (VARCHAR): USPS-standardized practicing physical address\n"
                "- Billing_Code (VARCHAR): CPT/HCPCS billing code\n"
                "- Specialty (VARCHAR): NUCC mapped clinical specialty (883 distinct taxonomy codes)\n"
                "- Rate (DOUBLE): Curated negotiated rate\n"
                "- Address_Status (VARCHAR): CORROBORATED (1,860), SINGLE_SOURCE (898), CONFLICTING (895), UNRESOLVED (122)\n"
                "- Multi-Source Evidence: NPPES, NPPES Practice Location, CMS DAC, CMS Revalidation Reassignments (314 matches), CMS NPD API Location (754 records across all 3,734 cached NPIs), HealthNet Directory (2,920 NPIs), Medicare 2024 Claims (504 NPIs), PECOS Enrollment (2,603 CA NPIs)\n"
                "- Selection_Rule (VARCHAR): Provenance selection rule from C4."
            ),
        ),
        (
            "C6 Final Provider Rates Deliverable (data/out/final_provider_rates.xlsx)",
            "data/out/final_provider_rates.xlsx",
            "C6 Stage Data Catalog",
            (
                "Workbook: final_provider_rates.xlsx (11,413 final deduplicated provider rate rows)\n"
                "Sheets:\n"
                "1. Curated Rates: NPI, TIN, Address, Billing Code, Specialty, Rate, Address_Status, Selection_Rule\n"
                "2. Data Quality: Stage C3 file scorecard, validation rates, duplicate rates\n"
                "3. Audit and Sources: Full trace of candidate resolution for ambiguous addresses with 0 duplicate keys remaining."
            ),
        ),
        (
            "C7 Cost-Effectiveness & Benchmark Scoring (data/out/c7_cost_effectiveness.xlsx)",
            "data/out/c7_cost_effectiveness.xlsx",
            "C7 Stage Data Catalog",
            (
                "Workbook: c7_cost_effectiveness.xlsx (11,413 provider rates scored against CMS Medicare PFS)\n"
                "Counts: 3,037 unique healthcare providers scored, 7,817 direct Medicare PFS matches, 154 locality fallbacks.\n"
                "Benchmarking Tiers:\n"
                "- Tier A (Specialty + Code Benchmark): 4,633 rows comparing provider rate to peer specialty median\n"
                "- Tier B (Code-Only Peer Benchmark): 2,891 rows\n"
                "- Tier C (Direct Medicare PFS Only): 293 rows\n"
                "Key Metrics: Median Medicare Ratio is 1.51x base CMS fee schedule rate (Mean: 3.30x).\n"
                "Detail File: data/stage/c7/c7_code_detail.csv contains granular npi, tin, billing_code, locality, medicare_ratio, tier."
            ),
        ),
    ]

    for title, source, section, content in schema_catalog:
        chunks.append({
            "source": source,
            "section": section,
            "title": title,
            "content": content,
        })

    return chunks


def get_watched_files(root_dir: Path) -> list[Path]:
    watched: list[Path] = [
        root_dir / "docs" / "DECISIONS.md",
        root_dir / "docs" / "ps" / "DATA_FINDINGS.md",
        root_dir / "docs" / "ps" / "PROBLEM_STATEMENT.md",
        root_dir / "docs" / "deliverables" / "file_quality_metrics.md",
    ]
    stage_dir = root_dir / "data" / "stage"
    if stage_dir.exists():
        watched.extend(stage_dir.glob("*/*_manifest.json"))
        watched.extend(stage_dir.glob("*/*summary.json"))
    out_dir = root_dir / "data" / "out"
    if out_dir.exists():
        watched.extend(out_dir.glob("*.xlsx"))
    return [p for p in watched if p.exists()]


def is_index_stale(root_dir: Path) -> bool:
    cache_dir = root_dir / "data" / "rag"
    index_file = cache_dir / "rag_index.parquet"
    meta_file = cache_dir / "rag_meta.json"

    if not index_file.exists() or not meta_file.exists():
        return True

    try:
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
        saved_mtimes: dict[str, float] = meta.get("mtimes", {})
        watched = get_watched_files(root_dir)

        if len(watched) != len(saved_mtimes):
            return True

        for p in watched:
            rel = str(p.relative_to(root_dir))
            curr_mtime = p.stat().st_mtime
            if curr_mtime > saved_mtimes.get(rel, 0.0):
                return True
        return False
    except (OSError, json.JSONDecodeError, KeyError):
        return True


def build_or_load_index(root_dir: Path | None = None, force_rebuild: bool = False) -> tuple[list[dict[str, Any]], np.ndarray]:
    if root_dir is None:
        root_dir = Path(__file__).resolve().parent.parent.parent

    cache_dir = root_dir / "data" / "rag"
    cache_dir.mkdir(parents=True, exist_ok=True)
    index_file = cache_dir / "rag_index.parquet"
    meta_file = cache_dir / "rag_meta.json"

    # Check if index exists and is up-to-date
    if not force_rebuild and index_file.exists() and not is_index_stale(root_dir):
        table = pq.read_table(index_file)
        chunks = [
            {
                "source": table["source"][i].as_py(),
                "section": table["section"][i].as_py(),
                "title": table["title"][i].as_py(),
                "content": table["content"][i].as_py(),
            }
            for i in range(len(table))
        ]
        emb_list = [row.as_py() for row in table["embedding"]]
        embeddings = np.array(emb_list, dtype=np.float32)
        return chunks, embeddings

    # Build fresh index
    chunks = extract_chunks(root_dir)
    texts = [f"{c['title']}\n{c['content']}" for c in chunks]

    embedder = get_embedder()
    embeddings = embedder.encode(texts, convert_to_numpy=True, normalize_embeddings=True)

    # Save to parquet
    emb_nested = [[float(x) for x in emb] for emb in embeddings]
    table = pa.Table.from_pydict({
        "source": [c["source"] for c in chunks],
        "section": [c["section"] for c in chunks],
        "title": [c["title"] for c in chunks],
        "content": [c["content"] for c in chunks],
        "embedding": pa.array(emb_nested, type=pa.list_(pa.float32())),
    })
    pq.write_table(table, index_file)

    # Save watched files metadata for automatic invalidation on data changes
    watched = get_watched_files(root_dir)
    meta = {
        "mtimes": {str(p.relative_to(root_dir)): p.stat().st_mtime for p in watched},
        "chunk_count": len(chunks),
        "embedding_dim": int(embeddings.shape[1]),
        "model": EMBEDDING_MODEL_NAME,
    }
    meta_file.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    return chunks, embeddings


def retrieve(query: str, top_k: int = 4, root_dir: Path | None = None) -> list[dict[str, Any]]:
    chunks, embeddings = build_or_load_index(root_dir)
    embedder = get_embedder()
    q_emb = embedder.encode([query], convert_to_numpy=True, normalize_embeddings=True)[0]

    # Cosine similarities (vectors are unit normalized)
    scores = np.dot(embeddings, q_emb)
    top_indices = np.argsort(scores)[::-1][:top_k]

    results = []
    for idx in top_indices:
        res = dict(chunks[idx])
        res["score"] = float(scores[idx])
        results.append(res)
    return results


if __name__ == "__main__":
    print("Building/verifying RAG index...")
    cks, embs = build_or_load_index()
    print(f"Indexed {len(cks)} chunks with embedding shape {embs.shape}")
    sample_res = retrieve("Why did NLP fail on PPO plan classification?")
    print("\nSample Query: 'Why did NLP fail on PPO plan classification?'")
    for r in sample_res[:2]:
        print(f"[{r['score']:.3f}] {r['title']} ({r['source']})")

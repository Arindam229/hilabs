from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from pipeline.rag.data_records import detect_and_query_data
from pipeline.rag.indexer import retrieve

DEFAULT_OLLAMA_URL = os.environ.get("LOCAL_LLM_URL", "http://127.0.0.1:11434")
DEFAULT_MODEL = os.environ.get("LOCAL_LLM_MODEL", "qwen2.5:1.5b")


def get_available_models(ollama_url: str = DEFAULT_OLLAMA_URL) -> list[str]:
    try:
        req = urllib.request.Request(f"{ollama_url}/api/tags", headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return [m.get("name", m.get("model", "")) for m in data.get("models", [])]
    except Exception:
        return []


def resolve_model_name(requested_model: str, ollama_url: str = DEFAULT_OLLAMA_URL) -> str:
    available = get_available_models(ollama_url)
    if not available:
        return requested_model
    if requested_model in available:
        return requested_model
    # Find any matching qwen model
    qwen_models = [m for m in available if "qwen" in m.lower()]
    if qwen_models:
        return qwen_models[0]
    return available[0]


def build_system_prompt(retrieved_chunks: list[dict[str, Any]], data_record_ctx: str | None = None) -> str:
    context_blocks = []
    for idx, chunk in enumerate(retrieved_chunks, 1):
        context_blocks.append(
            f"--- [DOCUMENT {idx} | Source: {chunk.get('source')} | Section: {chunk.get('title')}] ---\n"
            f"{chunk.get('content', '').strip()}"
        )
    context_text = "\n\n".join(context_blocks)

    live_records_section = ""
    if data_record_ctx:
        live_records_section = f"\nVERIFIED LIVE DATA RECORDS (QUERIED DIRECTLY FROM PARQUET/CSV VIA DUCKDB):\n{data_record_ctx}\n"

    return f"""You are the HiLabs Provider Rates Pipeline Copilot, an expert AI assistant specializing in the Centene Price Transparency Data (PTD) pipeline and its data records.
Scope: Centene, California, Commercial Group, PPO Network.

Rules and Instructions:
1. Base your answer strictly on the LIVE DATA RECORDS and GROUND TRUTH CONTEXT provided below.
2. Quote exact numbers, rates, NPIs, TINs, and specialties when answering data record inquiries. Do not fabricate or estimate when exact data is given.
3. Cite specific rule IDs (e.g., R-C2-01 through R-C2-08, R-C4-SEL-01 through R-C4-SEL-07, R-C5-01 through R-C5-03) whenever explaining classification, filtering, rate selection, or address corroboration.
4. Be technically precise, authoritative, concise, and structured with markdown headings, tables, bullet points, and code spans.
5. If the provided context does not contain sufficient information to answer the question, state that clearly without guessing.
{live_records_section}
GROUND TRUTH CONTEXT:
{context_text}"""


def query_ollama(
    prompt: str,
    system_prompt: str,
    model: str = DEFAULT_MODEL,
    ollama_url: str = DEFAULT_OLLAMA_URL,
    temperature: float = 0.2,
) -> dict[str, Any] | None:
    try:
        resolved_model = resolve_model_name(model, ollama_url)
        payload = json.dumps({
            "model": resolved_model,
            "prompt": prompt,
            "system": system_prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
            },
        }).encode("utf-8")

        req = urllib.request.Request(
            f"{ollama_url}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        t0 = time.time()
        with urllib.request.urlopen(req, timeout=30.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            total_duration = time.time() - t0
            eval_count = data.get("eval_count", 0)
            eval_duration = data.get("eval_duration", 0) / 1e9
            tok_sec = (eval_count / eval_duration) if eval_duration > 0 else 0.0

            return {
                "response": data.get("response", "").strip(),
                "model": resolved_model,
                "total_duration_sec": total_duration,
                "eval_tokens": eval_count,
                "tokens_per_second": tok_sec,
            }
    except Exception:
        return None


def fallback_answer_from_chunks(query: str, chunks: list[dict[str, Any]]) -> str:
    """Generate a high-fidelity structured summary directly from retrieved chunks when LLM daemon is offline."""
    lines = [
        "### Grounded Pipeline Knowledge Summary",
        f"*(Generated directly from {len(chunks)} verified pipeline document chunks)*\n",
    ]
    for idx, c in enumerate(chunks, 1):
        lines.append(f"#### {idx}. {c.get('title')} (`{c.get('source')}`)")
        content = c.get("content", "").strip()
        preview = "\n".join(content.splitlines()[:12])
        lines.append(preview)
        lines.append("")
    return "\n".join(lines)


def ask_rag(
    query: str,
    top_k: int = 4,
    model: str = DEFAULT_MODEL,
    ollama_url: str = DEFAULT_OLLAMA_URL,
    root_dir: Path | None = None,
) -> dict[str, Any]:
    t_start = time.time()

    # 1. Live Data Record Lookup (DuckDB over Parquet/CSV)
    data_record_res = detect_and_query_data(query, root_dir=root_dir)
    data_record_ctx = data_record_res["markdown"] if data_record_res else None

    # 2. Semantic Vector Retrieval (with automatic staleness check)
    retrieved = retrieve(query=query, top_k=top_k, root_dir=root_dir)
    retrieval_ms = (time.time() - t_start) * 1000

    # 3. Build Grounded Prompt incorporating live data records and retrieved rules
    sys_prompt = build_system_prompt(retrieved, data_record_ctx=data_record_ctx)

    # 4. Query Qwen 2.5 via Ollama
    llm_result = query_ollama(
        prompt=query,
        system_prompt=sys_prompt,
        model=model,
        ollama_url=ollama_url,
    )

    t_end = time.time()
    total_ms = (t_end - t_start) * 1000

    sources = [
        {
            "source": r.get("source", ""),
            "section": r.get("section", ""),
            "title": r.get("title", ""),
            "score": round(float(r.get("score", 0.0)), 4),
            "snippet": r.get("content", "").strip()[:180] + ("..." if len(r.get("content", "")) > 180 else ""),
        }
        for r in retrieved
    ]

    if llm_result is not None:
        return {
            "query": query,
            "answer": llm_result["response"],
            "sources": sources,
            "data_records": data_record_res,
            "model": llm_result["model"],
            "backend": f"Qwen 2.5 ({llm_result['model']} @ local GPU/Ollama)",
            "retrieval_latency_ms": round(retrieval_ms, 1),
            "total_latency_ms": round(total_ms, 1),
            "eval_tokens": llm_result["eval_tokens"],
            "tokens_per_second": round(llm_result["tokens_per_second"], 1),
            "status": "online",
        }

    # Fallback to direct chunk & data synthesis
    fallback_parts = []
    if data_record_ctx:
        fallback_parts.append(data_record_ctx)
    fallback_parts.append(fallback_answer_from_chunks(query, retrieved))
    fallback_text = "\n\n".join(fallback_parts)

    return {
        "query": query,
        "answer": fallback_text,
        "sources": sources,
        "data_records": data_record_res,
        "model": "Vector Retrieval & DuckDB Grounded Synthesis",
        "backend": "Local Pipeline Vector Index & DuckDB",
        "retrieval_latency_ms": round(retrieval_ms, 1),
        "total_latency_ms": round(total_ms, 1),
        "eval_tokens": 0,
        "tokens_per_second": 0.0,
        "status": "standby",
    }


def main():
    parser = argparse.ArgumentParser(description="HiLabs RAG Engine powered by Qwen 2.5")
    parser.add_argument("query", nargs="?", default="Why did NLP cosine similarity fail on PPO classification in C2?", help="User query")
    parser.add_argument("--top-k", type=int, default=4, help="Number of chunks to retrieve")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Ollama model name (e.g., qwen2.5:1.5b)")
    parser.add_argument("--url", default=DEFAULT_OLLAMA_URL, help="Ollama API base URL")
    parser.add_argument("--json", action="store_true", help="Output pure JSON")
    args = parser.parse_args()

    result = ask_rag(
        query=args.query,
        top_k=args.top_k,
        model=args.model,
        ollama_url=args.url,
    )

    if args.json:
        print(json.dumps(result, indent=2))
        return

    print("=" * 70)
    print(f"QUERY: {result['query']}")
    print(f"BACKEND: {result['backend']} | LATENCY: {result['total_latency_ms']}ms ({result.get('tokens_per_second', 0)} tok/s)")
    print("=" * 70)

    if result.get("data_records"):
        print("\nLIVE DATA RECORDS QUERY RESULT:")
        print(result["data_records"]["markdown"])

    print("\nRETRIEVED SOURCES:")
    for s in result["sources"]:
        print(f"  • [{s['score']:.3f}] {s['title']} ({s['source']})")
    print("\n" + "=" * 70)
    print("ANSWER:")
    print("=" * 70)
    print(result["answer"])
    print("=" * 70)


if __name__ == "__main__":
    main()

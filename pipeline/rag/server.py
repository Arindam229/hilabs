from __future__ import annotations

import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from pipeline.rag.engine import ask_rag
from pipeline.rag.indexer import build_or_load_index, get_embedder


class RAGHTTPRequestHandler(BaseHTTPRequestHandler):
    def _send_json(self, data: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        if self.path in {"/health", "/api/health"}:
            self._send_json({"status": "ok", "service": "hilabs-rag-engine"})
            return
        self._send_json({"error": "Not found"}, status=404)

    def do_POST(self) -> None:
        if self.path in {"/query", "/api/rag/query", "/api/query"}:
            try:
                length = int(self.headers.get("Content-Length", 0))
                raw_body = self.rfile.read(length).decode("utf-8")
                payload = json.loads(raw_body)
                query = payload.get("query", "").strip()
                if not query:
                    self._send_json({"error": "Field 'query' is required"}, status=400)
                    return

                top_k = int(payload.get("top_k", 4))
                model = payload.get("model", "qwen2.5:1.5b")

                result = ask_rag(query=query, top_k=top_k, model=model)
                self._send_json(result)
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=500)
            return

        if self.path in {"/sync", "/api/rag/sync"}:
            try:
                cks, embs = build_or_load_index(force_rebuild=True)
                self._send_json({
                    "status": "synced",
                    "chunk_count": len(cks),
                    "embedding_dim": int(embs.shape[1]),
                })
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=500)
            return

        self._send_json({"error": "Not found"}, status=404)


def run_server(port: int = 8005) -> None:
    print("Pre-warming SentenceTransformer embedding model and vector index...")
    t0 = time.time()
    get_embedder()
    build_or_load_index()
    print(f"RAG Engine warm in {time.time() - t0:.2f}s!")

    server_address = ("127.0.0.1", port)
    httpd = HTTPServer(server_address, RAGHTTPRequestHandler)
    print(f"RAG Daemon listening on http://127.0.0.1:{port} (ready for instant sub-100ms queries)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping RAG Daemon...")
        httpd.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="HiLabs RAG Engine Daemon")
    parser.add_argument("--port", type=int, default=8005, help="Port to listen on (default: 8005)")
    args = parser.parse_args()
    run_server(port=args.port)

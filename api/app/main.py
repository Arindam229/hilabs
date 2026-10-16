"""FastAPI shell for local-first HiLabs data-quality workflows."""

from __future__ import annotations

import csv
import io
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from .ingestion import parse_csv
from .pipeline import process_records
from .store import RunStore, export_rows


app = FastAPI(
    title="HiLabs Data Quality API",
    version="0.1.0",
    description="Local-first skeleton. Replace generic stages after PS release.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

store = RunStore()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "hilabs-api"}


@app.get("/metrics")
def metrics() -> dict[str, int]:
    return {"runs": store.count()}


@app.post("/process")
async def process_upload(file: UploadFile = File(...)) -> dict:
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(status_code=415, detail="Upload a CSV file")

    try:
        rows = parse_csv(await file.read())
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="CSV must be UTF-8 encoded") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    result = process_records(rows, run_id=f"run-{uuid4().hex[:12]}")
    store.save(result)
    return result


@app.get("/runs/{run_id}")
def get_run(run_id: str) -> dict:
    result = store.get(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return result


@app.get("/runs/{run_id}/export")
def export_run(run_id: str) -> StreamingResponse:
    result = store.get(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Run not found")

    rows = export_rows(result)
    fieldnames = list(rows[0]) if rows else ["source_id", "action", "reason_codes", "review_required"]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    output.seek(0)
    return StreamingResponse(
        output,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{run_id}-export.csv"'},
    )

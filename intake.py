"""
BioVault Agent — Document Intake Router
-----------------------------------------
POST /intake                  — upload a document image/PDF into the processing queue
GET  /intake/simulate         — inject a batch of test documents for demo purposes
GET  /intake/queue            — return current queue status
GET  /intake/{doc_id}/image   — serve the original uploaded image
GET  /intake/{doc_id}/results — return pipeline results for a processed document
"""

import json
import logging
import mimetypes
import os
import shutil
import sqlite3
import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse

import database as db

logger = logging.getLogger("biovault.intake")

router = APIRouter(prefix="/intake", tags=["intake"])

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "/data/uploads")
DEMO_CHART_PATH = Path(__file__).parent / "pipeline" / "demo_chart.jpeg"

ALLOWED_TYPES = {
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "application/pdf",
}
MAX_FILE_BYTES = 20 * 1024 * 1024  # 20 MB


def _ensure_upload_dir():
    os.makedirs(UPLOAD_DIR, exist_ok=True)


@router.post("")
async def intake_document(file: UploadFile = File(...)):
    """
    Accept a clinical document image and add it to the processing queue.
    Returns the document ID immediately — processing happens asynchronously.
    """
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{file.content_type}'. "
                   f"Accepted: JPEG, PNG, GIF, WebP, PDF",
        )

    contents = await file.read()
    if len(contents) > MAX_FILE_BYTES:
        raise HTTPException(status_code=400, detail="File too large (max 20 MB)")

    _ensure_upload_dir()

    doc_id = str(uuid.uuid4())
    original_name = file.filename or "document.jpg"
    suffix = Path(original_name).suffix or ".jpg"
    dest_path = os.path.join(UPLOAD_DIR, f"{doc_id}{suffix}")

    with open(dest_path, "wb") as f:
        f.write(contents)

    db.insert_document(doc_id=doc_id, filename=original_name, file_path=dest_path)

    logger.info("Document queued: id=%s filename=%s size=%d", doc_id, original_name, len(contents))

    return {
        "status": "queued",
        "document_id": doc_id,
        "filename": original_name,
        "message": "Document added to processing queue. Check /dashboard for status.",
    }


@router.get("/simulate")
async def simulate_batch():
    """
    Inject a batch of test documents into the queue for demo purposes.
    Includes the real Delta Hospital chemo chart (the one that catches the
    Daunorubicin dose drop) plus synthetic placeholder documents.

    Returns the list of queued document IDs.
    """
    _ensure_upload_dir()

    queued = []

    # Document 1: The real Delta Hospital chemo chart
    if DEMO_CHART_PATH.exists():
        doc_id = str(uuid.uuid4())
        dest = os.path.join(UPLOAD_DIR, f"{doc_id}.jpeg")
        shutil.copy2(str(DEMO_CHART_PATH), dest)
        db.insert_document(
            doc_id=doc_id,
            filename="delta_hospital_chemo_chart.jpeg",
            file_path=dest,
        )
        queued.append({
            "document_id": doc_id,
            "filename": "delta_hospital_chemo_chart.jpeg",
            "note": "Real AML chart — Daunorubicin dose drop expected",
        })
        logger.info("Simulated: Delta Hospital chart queued as %s", doc_id)
    else:
        logger.warning("Demo chart not found at %s", DEMO_CHART_PATH)

    # Documents 2–5: Synthetic placeholders (copies of the same chart with
    # different IDs to demonstrate continuous queue processing)
    for i in range(2, 6):
        if DEMO_CHART_PATH.exists():
            doc_id = str(uuid.uuid4())
            dest = os.path.join(UPLOAD_DIR, f"{doc_id}.jpeg")
            shutil.copy2(str(DEMO_CHART_PATH), dest)
            db.insert_document(
                doc_id=doc_id,
                filename=f"synthetic_chart_{i:02d}.jpeg",
                file_path=dest,
            )
            queued.append({
                "document_id": doc_id,
                "filename": f"synthetic_chart_{i:02d}.jpeg",
                "note": f"Synthetic test document #{i}",
            })

    logger.info("Simulate: %d documents queued", len(queued))

    return {
        "status": "ok",
        "queued_count": len(queued),
        "document_ids": [q["document_id"] for q in queued],
        "documents": queued,
        "message": f"{len(queued)} documents added to queue. Watch /dashboard for live processing.",
    }


@router.get("/queue")
async def queue_status():
    """Return a summary of the current document queue."""
    stats = db.get_stats()
    recent = db.get_recent_documents(limit=20)
    return {
        "stats": stats,
        "recent_documents": recent,
    }


@router.get("/{doc_id}/image")
async def get_document_image(doc_id: str):
    """Serve the original uploaded image for a document."""
    with db.get_conn() as conn:
        row = conn.execute(
            "SELECT file_path, filename FROM documents WHERE id = ?", (doc_id,)
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Document not found")

    file_path = row["file_path"]
    filename = row["filename"]

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Image file not found on disk")

    mime, _ = mimetypes.guess_type(file_path)
    return FileResponse(
        path=file_path,
        media_type=mime or "image/jpeg",
        filename=filename,
    )


@router.get("/{doc_id}/results")
async def get_document_results(doc_id: str):
    """Return all pipeline results and safety flags for a processed document."""
    with db.get_conn() as conn:
        doc_row = conn.execute(
            "SELECT * FROM documents WHERE id = ?", (doc_id,)
        ).fetchone()

        if not doc_row:
            raise HTTPException(status_code=404, detail="Document not found")

        stage_rows = conn.execute(
            """SELECT stage, output_json, confidence, timestamp
               FROM pipeline_results WHERE document_id = ?
               ORDER BY id ASC""",
            (doc_id,),
        ).fetchall()

        flag_rows = conn.execute(
            """SELECT id, flag_type, severity, details, resolved, timestamp
               FROM safety_flags WHERE document_id = ?
               ORDER BY id ASC""",
            (doc_id,),
        ).fetchall()

    stages = {}
    for r in stage_rows:
        try:
            stages[r["stage"]] = json.loads(r["output_json"])
        except Exception:
            stages[r["stage"]] = {}

    flags = [dict(f) for f in flag_rows]

    extraction = stages.get("extraction", {})
    standardization = stages.get("standardization", {})
    validation = stages.get("validation", {})
    fhir = stages.get("fhir", {})

    return {
        "document": dict(doc_row),
        "extraction_summary": {
            "hospital": extraction.get("hospital", {}),
            "diagnosis": extraction.get("diagnosis", {}).get("text_raw"),
            "regimen": extraction.get("regimen", {}).get("name"),
            "cycles_count": len(extraction.get("cycles", [])),
            "overall_confidence": extraction.get("overall_confidence"),
            "patient": {
                k: v for k, v in extraction.get("patient", {}).items()
                if k not in ("name_raw",)
            },
            "flags": extraction.get("flags", []),
        },
        "standardization": {
            "icd10": standardization.get("icd10", {}),
            "dose_analysis": standardization.get("dose_analysis", {}),
            "safety_flags": standardization.get("safety_flags", []),
            "standardized_drugs": standardization.get("standardized_drugs", []),
        },
        "validation": validation,
        "fhir_bundle": fhir,
        "safety_flags": flags,
    }

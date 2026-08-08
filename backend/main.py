import asyncio
import uuid
from typing import Literal

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend import storage
from backend.agents.pipeline import analyze_script

app = FastAPI(title="Clearance Copilot")

MAX_UPLOAD_BYTES = 25 * 1024 * 1024
ALLOWED_CONTENT_TYPES = {"text/plain", "application/pdf"}

JobStatus = Literal["processing", "error"]
_job_status: dict[str, JobStatus] = {}
_job_errors: dict[str, str] = {}


class AnalyzeResponse(BaseModel):
    report_id: str
    status: Literal["processing"]


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/api/analyze", response_model=AnalyzeResponse, status_code=202)
async def analyze(file: UploadFile = File(...)):
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(400, f"Unsupported content type: {file.content_type}")

    body = await file.read()
    if not body:
        raise HTTPException(400, "Uploaded file is empty")
    if len(body) > MAX_UPLOAD_BYTES:
        raise HTTPException(400, "Uploaded file exceeds 25MB limit")

    report_id = str(uuid.uuid4())
    is_pdf = file.content_type == "application/pdf"
    script_title = file.filename or "Untitled Script"

    _job_status[report_id] = "processing"
    asyncio.create_task(_run_pipeline(report_id, body, is_pdf, script_title))

    return AnalyzeResponse(report_id=report_id, status="processing")


async def _run_pipeline(report_id: str, body: bytes, is_pdf: bool, script_title: str) -> None:
    try:
        report = await analyze_script(
            script_text=None if is_pdf else body.decode("utf-8"),
            script_title=script_title,
            pdf_bytes=body if is_pdf else None,
            report_id=report_id,
        )
        await storage.save_report(report)
        _job_status.pop(report_id, None)
    except Exception as exc:
        _job_status[report_id] = "error"
        _job_errors[report_id] = str(exc)


@app.get("/api/reports/{report_id}")
async def get_report(report_id: str):
    report = await storage.get_report(report_id)
    if report is not None:
        return report

    status = _job_status.get(report_id)
    if status == "processing":
        return JSONResponse({"report_id": report_id, "status": "processing"}, status_code=202)
    if status == "error":
        raise HTTPException(500, _job_errors.get(report_id, "Analysis failed"))

    raise HTTPException(404, "Report not found")

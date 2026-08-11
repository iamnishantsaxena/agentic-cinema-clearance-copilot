import asyncio
import uuid
from typing import Literal

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from backend import progress, storage
from backend.agents.pipeline import analyze_script
from backend.schemas import Report

app = FastAPI(title="Clearance Copilot")
templates = Jinja2Templates(directory="backend/templates")

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
            on_progress=lambda msg: progress.publish(report_id, msg),
        )
        await storage.save_report(report)
        _job_status.pop(report_id, None)
        await progress.publish(report_id, "Report complete")
    except Exception as exc:
        _job_status[report_id] = "error"
        _job_errors[report_id] = str(exc)
        await progress.publish(report_id, f"Error: {exc}")
    finally:
        await progress.close(report_id)


@app.get("/api/reports/{report_id}/stream")
async def stream_report(report_id: str):
    async def events():
        queue = progress.get_queue(report_id)
        while True:
            message = await queue.get()
            if message is None:
                break
            yield f"data: {message}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")


async def _lookup(report_id: str) -> tuple[Report | None, JobStatus | None]:
    report = await storage.get_report(report_id)
    if report is not None:
        return report, None
    return None, _job_status.get(report_id)


@app.get("/api/reports/{report_id}")
async def get_report(report_id: str):
    report, status = await _lookup(report_id)
    if report is not None:
        return report
    if status == "processing":
        return JSONResponse({"report_id": report_id, "status": "processing"}, status_code=202)
    if status == "error":
        raise HTTPException(500, _job_errors.get(report_id, "Analysis failed"))
    raise HTTPException(404, "Report not found")


@app.get("/", response_class=HTMLResponse)
async def upload_page(request: Request):
    return templates.TemplateResponse(request, "upload.html")


@app.get("/reports/{report_id}/processing", response_class=HTMLResponse)
async def processing_page(request: Request, report_id: str):
    return templates.TemplateResponse(request, "processing.html", {"report_id": report_id})


@app.get("/reports/{report_id}", response_class=HTMLResponse)
async def report_page(request: Request, report_id: str):
    report, status = await _lookup(report_id)
    if report is not None:
        return templates.TemplateResponse(request, "report.html", {"report": report})
    if status == "processing":
        return RedirectResponse(f"/reports/{report_id}/processing")
    message = _job_errors.get(report_id, "Analysis failed") if status == "error" else "Report not found"
    code = 500 if status == "error" else 404
    return templates.TemplateResponse(request, "error.html", {"message": message}, status_code=code)

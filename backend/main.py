"""Report OCR API.

This service intentionally performs no diagnosis. It exposes source text, OCR
confidence and review status so later interpretation always remains traceable.
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .interpret import (
    InterpretNotConfiguredError,
    InterpretRequest,
    InterpretUnavailableError,
    interpret_report,
)
from .ocr import OcrUnavailableError, extract_report_text

ALLOWED_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".pdf", ".txt"}
MAX_FILE_BYTES = 20 * 1024 * 1024

app = FastAPI(title="影像知情 · 报告 OCR API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)


class HealthResponse(BaseModel):
    status: str
    service: str


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", service="report-ocr")


@app.post("/api/reports/ocr")
async def ocr_report(file: Annotated[UploadFile, File(description="Report photo, PDF or text file")]):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(status_code=415, detail="仅支持 JPG、PNG、WEBP、BMP、PDF 或 TXT 报告文件")

    with tempfile.TemporaryDirectory(prefix="imaging-report-") as directory:
        target = Path(directory, f"report{suffix}")
        total_size = 0
        with target.open("wb") as output:
            while chunk := await file.read(1024 * 1024):
                total_size += len(chunk)
                if total_size > MAX_FILE_BYTES:
                    raise HTTPException(status_code=413, detail="文件超过 20 MB 限制")
                output.write(chunk)

        try:
            result = extract_report_text(target)
        except OcrUnavailableError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    return result


@app.post("/api/reports/interpret")
def interpret(request: InterpretRequest):
    try:
        return interpret_report(request)
    except InterpretNotConfiguredError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except InterpretUnavailableError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error

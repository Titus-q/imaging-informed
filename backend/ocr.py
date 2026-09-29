"""OCR adapters with explicit confidence and source evidence."""
from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any


class OcrUnavailableError(RuntimeError):
    """Raised when the optional local OCR engine has not been installed."""


# PaddleOCR 3.x delegates model downloads and temporary files to PaddleX. Keep
# that cache inside this project instead of unexpectedly writing patient-app
# runtime data to the user's home directory.
os.environ.setdefault(
    "PADDLE_PDX_CACHE_HOME",
    str(Path(__file__).resolve().parent / ".paddlex-cache"),
)

# PaddlePaddle 3.x 默认启用 OneDNN CPU 加速，但在部分 CPU 型号上会抛出
# NotImplementedError: ConvertPirAttribute2RuntimeAttribute not support
# [pir::ArrayAttribute<pir::DoubleAttribute>]。
# 关闭 OneDNN 绕开该问题；必须在 import paddle 之前设置才生效。
os.environ.setdefault("FLAGS_use_mkldnn", "0")

# The engine loads several hundred MB of model weights. Rebuilding it on every
# request would dominate latency on a small instance, so it is created once and
# reused for the lifetime of the process.
_engine: Any = None
_engine_lock = threading.Lock()


def _review_status(lines: list[dict[str, Any]]) -> str:
    if not lines:
        return "unreadable"
    confidence = sum(line["confidence"] for line in lines) / len(lines)
    return "verified" if confidence >= 0.92 else "needs_review"


def _read_text_file(path: Path) -> dict[str, Any]:
    content = path.read_text(encoding="utf-8", errors="replace").strip()
    lines = [
        {"text": line, "confidence": 1.0, "page": 1, "bounding_box": None}
        for line in content.splitlines() if line.strip()
    ]
    return {"source_status": _review_status(lines), "full_text": "\n".join(line["text"] for line in lines), "lines": lines}


def _read_text_pdf(path: Path) -> dict[str, Any]:
    try:
        from pypdf import PdfReader
    except ImportError as error:
        raise OcrUnavailableError("缺少 pypdf，请先按 README 安装后端依赖") from error
    reader = PdfReader(path)
    lines: list[dict[str, Any]] = []
    for page_number, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        lines.extend(
            {"text": line, "confidence": 1.0, "page": page_number, "bounding_box": None}
            for line in text.splitlines() if line.strip()
        )
    if not lines:
        raise ValueError("该 PDF 没有可提取文字；请导出为清晰的 JPG/PNG 后再上传，以使用 OCR")
    return {"source_status": "verified", "full_text": "\n".join(line["text"] for line in lines), "lines": lines}


def _get_engine() -> Any:
    """Create the PaddleOCR engine once, preferring the lightweight models."""
    global _engine
    if _engine is not None:
        return _engine
    with _engine_lock:
        if _engine is not None:
            return _engine
        try:
            from paddleocr import PaddleOCR
        except ImportError as error:
            raise OcrUnavailableError(
                "缺少 PaddleOCR。请在服务器虚拟环境中安装: "
                "pip install 'paddlepaddle>=3.0,<4.0' 'paddleocr>=3.0,<4.0'"
            ) from error

        # Small instances (2 vCPU / 2 GB) cannot comfortably hold the server
        # models, so prefer the mobile ones and fall back to the defaults.
        common = dict(
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            # PaddleX 内部默认开 OneDNN，显式关闭以强制 run_mode=paddle，
            # 绕开 ConvertPirAttribute2RuntimeAttribute not support 的崩溃
            enable_mkldnn=False,
        )
        try:
            engine = PaddleOCR(
                text_detection_model_name="PP-OCRv5_mobile_det",
                text_recognition_model_name="PP-OCRv5_mobile_rec",
                **common,
            )
        except Exception as error:
            # Surface the real cause instead of silently retrying with another
            # configuration, which would hide the original failure.
            raise OcrUnavailableError(
                f"PaddleOCR 引擎初始化失败: {type(error).__name__}: {error}"
            ) from error
        _engine = engine
        return engine


# On a 2 vCPU instance a 4000px phone photo can take over 60 s to OCR (and the
# WeChat client times out at exactly 60 s). 1600 px on the long edge keeps
# recognition quality for printed reports while cutting runtime several-fold.
_MAX_IMAGE_SIDE = 1600


def _prepare_image(path: Path) -> Path:
    """Downscale oversized photos before OCR; returns the path to process."""
    from PIL import Image

    with Image.open(path) as image:
        width, height = image.size
        longest = max(width, height)
        if longest <= _MAX_IMAGE_SIDE:
            return path
        scale = _MAX_IMAGE_SIDE / longest
        resized = image.resize(
            (round(width * scale), round(height * scale)),
            Image.LANCZOS,
        )
        target = path.with_name(f"{path.stem}-resized.jpg")
        # Handle palette/alpha images that cannot be saved as JPEG directly.
        if resized.mode not in ("RGB", "L"):
            resized = resized.convert("RGB")
        resized.save(target, "JPEG", quality=92)
        return target


def _read_image(path: Path) -> dict[str, Any]:
    engine = _get_engine()
    prepared = _prepare_image(path)
    try:
        pages = engine.predict(str(prepared))
    except AttributeError as error:
        raise OcrUnavailableError("检测到不兼容的 PaddleOCR 版本，请安装 requirements.txt 指定的版本") from error
    finally:
        if prepared != path:
            prepared.unlink(missing_ok=True)

    lines: list[dict[str, Any]] = []
    for page_number, page in enumerate(pages or [], start=1):
        for box, text, confidence in zip(
            page.get("rec_polys", []),
            page.get("rec_texts", []),
            page.get("rec_scores", []),
        ):
            lines.append({
                "text": str(text),
                "confidence": round(float(confidence), 4),
                "page": page_number,
                "bounding_box": box.tolist() if hasattr(box, "tolist") else box,
            })
    return {"source_status": _review_status(lines), "full_text": "\n".join(line["text"] for line in lines), "lines": lines}


def extract_report_text(path: Path) -> dict[str, Any]:
    """Extract report source text without inferring any clinical finding."""
    suffix = path.suffix.lower()
    if suffix == ".txt":
        return _read_text_file(path)
    if suffix == ".pdf":
        return _read_text_pdf(path)
    return _read_image(path)

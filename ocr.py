"""CPU-friendly OCR helpers for images and scanned PDF pages."""
from __future__ import annotations

import os
from pathlib import Path

_OCR_ENGINE = None


def ocr_enabled() -> bool:
    """OCR is opt-in because RapidOCR/ONNX can use significant RAM."""
    return os.getenv("ENABLE_OCR", "0").strip().lower() in {"1", "true", "yes", "on"}


def _get_engine():
    global _OCR_ENGINE
    if not ocr_enabled():
        raise RuntimeError("OCR is disabled. Set ENABLE_OCR=1 to enable it.")
    if _OCR_ENGINE is None:
        from rapidocr import RapidOCR
        _OCR_ENGINE = RapidOCR()
    return _OCR_ENGINE


def _result_text(result) -> list[str]:
    texts = getattr(result, "txts", None)
    if texts is None and isinstance(result, (tuple, list)) and result:
        candidate = result[0]
        if isinstance(candidate, (tuple, list)):
            texts = [
                item[1] for item in candidate
                if isinstance(item, (tuple, list)) and len(item) > 1
            ]
    if texts is None:
        return []
    return [str(item).strip() for item in texts if str(item).strip()]


def ocr_image(image: str | Path | bytes) -> str:
    """Extract readable text from an image using RapidOCR/ONNX Runtime."""
    result = _get_engine()(image)
    return "\n".join(_result_text(result))


def ocr_pdf(path: str | Path, dpi: int = 150, max_pages: int = 50) -> str:
    """OCR only pages that do not contain extractable PDF text."""
    import fitz

    parts: list[str] = []
    with fitz.open(path) as document:
        for index, page in enumerate(document):
            if index >= max_pages:
                break
            native = page.get_text("text").strip()
            if native:
                parts.append(native)
                continue
            scale = dpi / 72
            pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
            text = ocr_image(pixmap.tobytes("png"))
            if text:
                parts.append(text)
    return "\n\n".join(parts)


def ocr_available() -> bool:
    if not ocr_enabled():
        return False
    try:
        import rapidocr  # noqa: F401
        import onnxruntime  # noqa: F401
    except ImportError:
        return False
    return True

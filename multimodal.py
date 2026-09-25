"""File and multimodal input helpers for the Personal AI Assistant."""
from __future__ import annotations

import base64
import mimetypes
from pathlib import Path

from config import FILE_ROOT, MAX_FILE_CHARS, ensure_directories


def _safe_path(path: str) -> Path:
    ensure_directories()
    candidate = (FILE_ROOT / path).resolve()
    try:
        candidate.relative_to(FILE_ROOT.resolve())
    except ValueError as exc:
        raise PermissionError("path is outside the allowed file root") from exc
    return candidate


def save_upload(filename: str, content: bytes) -> str:
    name = Path(filename).name
    if not name:
        raise ValueError("filename is required")
    target = _safe_path(name)
    target.write_bytes(content)
    return str(target.relative_to(FILE_ROOT))


def read_upload(path: str) -> dict:
    target = _safe_path(path)
    if not target.is_file():
        raise FileNotFoundError(path)
    mime, _ = mimetypes.guess_type(target.name)
    mime = mime or "application/octet-stream"
    data = target.read_bytes()
    if mime.startswith("text/") or mime in {"application/json","application/xml"}:
        return {"path": path, "mime_type": mime, "text": data[:MAX_FILE_CHARS].decode("utf-8","replace")}
    return {"path": path, "mime_type": mime, "size": len(data), "base64": base64.b64encode(data).decode("ascii")}


def image_data_url(path: str) -> str:
    target = _safe_path(path)
    if not target.is_file():
        raise FileNotFoundError(path)
    mime, _ = mimetypes.guess_type(target.name)
    if not mime or not mime.startswith("image/"):
        raise ValueError("file is not an image")
    return f"data:{mime};base64,{base64.b64encode(target.read_bytes()).decode('ascii')}"

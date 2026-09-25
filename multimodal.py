"""File and multimodal input helpers with per-user storage."""
from __future__ import annotations
import base64,mimetypes
from pathlib import Path
from config import FILE_ROOT,MAX_FILE_CHARS,ensure_directories
def _user_root(user_id):
    if not isinstance(user_id,int) or user_id<1:raise ValueError("authenticated user_id is required")
    root=(FILE_ROOT/f"user_{user_id}").resolve();root.mkdir(parents=True,exist_ok=True);return root
def _safe_path(path,user_id):
    root=_user_root(user_id);candidate=(root/path).resolve()
    try:candidate.relative_to(root)
    except ValueError as exc:raise PermissionError("path is outside the user's file root") from exc
    return candidate
def save_upload(filename,content,user_id):
    name=Path(filename).name
    if not name:raise ValueError("filename is required")
    target=_safe_path(name,user_id);target.write_bytes(content);return str(target.relative_to(_user_root(user_id)))
def resolve_upload_path(path,user_id):
    return _safe_path(path,user_id)

def read_upload(path,user_id):
    target=_safe_path(path,user_id)
    if not target.is_file():raise FileNotFoundError(path)
    mime,_=mimetypes.guess_type(target.name);mime=mime or "application/octet-stream";data=target.read_bytes()
    if mime.startswith("text/") or mime in {"application/json","application/xml"}:
        return {"path":path,"mime_type":mime,"text":data[:MAX_FILE_CHARS].decode("utf-8","replace")}
    return {"path":path,"mime_type":mime,"size":len(data),"base64":base64.b64encode(data).decode("ascii")}
def image_data_url(path,user_id):
    target=_safe_path(path,user_id)
    if not target.is_file():raise FileNotFoundError(path)
    mime,_=mimetypes.guess_type(target.name)
    if not mime or not mime.startswith("image/"):raise ValueError("file is not an image")
    return f"data:{mime};base64,{base64.b64encode(target.read_bytes()).decode('ascii')}"

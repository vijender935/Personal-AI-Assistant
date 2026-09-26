"""File and multimodal helpers with optional Cloudflare R2 persistence."""
from __future__ import annotations
import base64,mimetypes,os
from pathlib import Path
from config import FILE_ROOT,MAX_FILE_CHARS
R2_ENDPOINT=os.getenv("R2_ENDPOINT","").strip()
R2_BUCKET=os.getenv("R2_BUCKET","").strip()
R2_ACCESS_KEY_ID=os.getenv("R2_ACCESS_KEY_ID","").strip()
R2_SECRET_ACCESS_KEY=os.getenv("R2_SECRET_ACCESS_KEY","").strip()
def r2_enabled(): return all((R2_ENDPOINT,R2_BUCKET,R2_ACCESS_KEY_ID,R2_SECRET_ACCESS_KEY))
def _r2_client():
    if not r2_enabled(): return None
    import boto3
    return boto3.client("s3",endpoint_url=R2_ENDPOINT,aws_access_key_id=R2_ACCESS_KEY_ID,aws_secret_access_key=R2_SECRET_ACCESS_KEY,region_name="auto")
def _object_key(path): return path.lstrip("/").replace(chr(92),"/")
def _safe_path(path):
    root=FILE_ROOT.resolve(); root.mkdir(parents=True,exist_ok=True)
    candidate=(root/Path(path)).resolve()
    try:candidate.relative_to(root)
    except ValueError as exc:raise PermissionError("path is outside the allowed file root") from exc
    return candidate
def ensure_local_file(path):
    candidate=_safe_path(path)
    if candidate.is_file(): return candidate
    client=_r2_client()
    if client is None: raise FileNotFoundError(path)
    try:
        candidate.parent.mkdir(parents=True,exist_ok=True)
        client.download_file(R2_BUCKET,_object_key(path),str(candidate))
    except Exception as exc: raise FileNotFoundError(path) from exc
    return candidate
def save_upload(filename,content):
    name=Path(filename).name
    if not name: raise ValueError("filename is required")
    target=_safe_path(name); target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes(content)
    client=_r2_client()
    if client is not None:
        client.put_object(Bucket=R2_BUCKET,Key=_object_key(str(target.relative_to(FILE_ROOT.resolve()))),Body=content,ContentType=mimetypes.guess_type(name)[0] or "application/octet-stream")
    return str(target.relative_to(FILE_ROOT.resolve()))
def list_uploads():
    root=FILE_ROOT.resolve(); entries={}
    root.mkdir(parents=True,exist_ok=True)
    for candidate in root.rglob("*"):
        if candidate.is_file():
            relative=str(candidate.relative_to(root)); stat=candidate.stat()
            entries[relative]={"path":relative,"name":candidate.name,"size":stat.st_size,"mime_type":mimetypes.guess_type(candidate.name)[0] or "application/octet-stream","extension":candidate.suffix.lower(),"modified_at":stat.st_mtime}
    client=_r2_client()
    if client is not None:
        token=None
        while True:
            kwargs={"Bucket":R2_BUCKET,"Prefix":""}
            if token: kwargs["ContinuationToken"]=token
            page=client.list_objects_v2(**kwargs)
            for obj in page.get("Contents",[]):
                relative=obj["Key"]
                if not relative: continue
                entries.setdefault(relative,{"path":relative,"name":Path(relative).name,"size":obj.get("Size",0),"mime_type":mimetypes.guess_type(relative)[0] or "application/octet-stream","extension":Path(relative).suffix.lower(),"modified_at":obj.get("LastModified").timestamp() if obj.get("LastModified") else 0})
            if not page.get("IsTruncated"): break
            token=page.get("NextContinuationToken")
            if not token: break
    return sorted(entries.values(),key=lambda x:x["path"])
def delete_upload(path):
    candidate=_safe_path(path); existed=candidate.is_file()
    if existed: candidate.unlink()
    client=_r2_client(); r2_deleted=False
    if client is not None:
        try: client.delete_object(Bucket=R2_BUCKET,Key=_object_key(path)); r2_deleted=True
        except Exception:
            if not existed: raise FileNotFoundError(path)
    if not existed and not r2_deleted: raise FileNotFoundError(path)
    return True
def resolve_upload_path(path): return ensure_local_file(path)
def read_upload(path):
    target=ensure_local_file(path); mime=mimetypes.guess_type(target.name)[0] or "application/octet-stream"; data=target.read_bytes()
    if mime.startswith("text/") or mime in {"application/json","application/xml"}:
        return {"path":path,"mime_type":mime,"text":data[:MAX_FILE_CHARS].decode("utf-8","replace")}
    return {"path":path,"mime_type":mime,"size":len(data),"base64":base64.b64encode(data).decode("ascii")}
def image_data_url(path):
    target=ensure_local_file(path); mime=mimetypes.guess_type(target.name)[0]
    if not mime or not mime.startswith("image/"): raise ValueError("file is not an image")
    return f"data:{mime};base64,{base64.b64encode(target.read_bytes()).decode('ascii')}"

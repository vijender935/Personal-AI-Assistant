"""FastAPI REST API for the Personal AI Assistant."""
from __future__ import annotations

import os
import time
from typing import Optional

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile\nfrom fastapi.responses import FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from agent import MODEL, VISION_MODEL, run_agent, stream_agent
from config import ALLOW_SHELL, FILE_ROOT, ensure_directories
from tools import init_db, recall_memories, remember_fact, load_history, list_sessions
from memory import index_document, search_rag, rag_source_status
from auth import authenticate, create_session, create_user, get_user, init_auth_db, revoke_session
from multimodal import save_upload, read_upload, image_data_url, _safe_path
from mcp_registry import registry_snapshot
from document_parser import extract_and_limit, is_supported_document

ensure_directories()
init_db()
init_auth_db()

app = FastAPI(
    title="Personal AI Assistant API",
    version="0.10.0",
    description="REST API for the Personal AI Assistant agent engine.",
)

origins = [
    item.strip()
    for item in os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173").split(",")
    if item.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=20000)
    session_id: str = Field(default="default", min_length=1, max_length=200)
    attachment_paths: list[str] = Field(default_factory=list, max_length=3)


class ChatResponse(BaseModel):
    answer: str
    session_id: str
    model: str


class MemoryRequest(BaseModel):
    fact: str = Field(..., min_length=1, max_length=5000)
    source: str = Field(default="api", max_length=100)


class MemoryResponse(BaseModel):
    saved: bool
    fact: str


class RegisterRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    email: str = Field(..., min_length=5, max_length=254)
    password: str = Field(..., min_length=8, max_length=200)


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=254)
    password: str = Field(..., min_length=1, max_length=200)


def current_user(authorization: str | None = Header(default=None)):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Authentication required.")
    user = get_user(authorization.split(" ", 1)[1].strip())
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired session.")
    return user


@app.post("/api/v1/auth/register")
def register(request: RegisterRequest):
    try:
        user = create_user(request.name, request.email, request.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"user": user, "token": create_session(user["id"])}


@app.post("/api/v1/auth/login")
def login(request: LoginRequest):
    user = authenticate(request.email, request.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    return {"user": user, "token": create_session(user["id"])}


@app.post("/api/v1/auth/logout")
def logout(authorization: str | None = Header(default=None)):
    if authorization and authorization.lower().startswith("bearer "):
        revoke_session(authorization.split(" ", 1)[1].strip())
    return {"logged_out": True}


@app.get("/api/v1/auth/me")
def me(user=Depends(current_user)):
    return {"user": user}


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "personal-ai-assistant",
        "model": MODEL,
        "shell_enabled": ALLOW_SHELL,
    }


@app.get("/api/v1/info")
def info():
    return {
        "name": "Personal AI Assistant",
        "version": "0.10.0",
        "model": MODEL,
        "shell_enabled": ALLOW_SHELL,
    }


@app.post("/api/v1/chat", response_model=ChatResponse)
def chat(request: ChatRequest, user=Depends(current_user)):
    if not os.getenv("GROQ_API_KEY"):
        raise HTTPException(status_code=503, detail="GROQ_API_KEY is not configured.")

    try:
        attachment_urls=[]
        rag_sources=[]
        for path in request.attachment_paths:
            try:
                attachment_urls.append(image_data_url(path, user_id=user["id"]))
            except ValueError:
                try:
                    candidate=_safe_path(path,user["id"])
                    if not is_supported_document(candidate):
                        raise ValueError("unsupported attachment type")
                    user_root=(FILE_ROOT/f"user_{user['id']}").resolve()
                    rag_sources.append(str(candidate.relative_to(user_root)))
                except (FileNotFoundError, PermissionError, ValueError) as exc:
                    raise HTTPException(status_code=400, detail=f"Invalid document attachment: {path}") from exc
            except (FileNotFoundError, PermissionError) as exc:
                raise HTTPException(status_code=400, detail=f"Invalid image attachment: {path}") from exc
        answer = run_agent(
            request.message,
            session_id=f"user-{user['id']}-{request.session_id}",
            user_id=user["id"],
            image_urls=attachment_urls,
            rag_sources=rag_sources or None,
            verbose=False,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Agent execution failed.") from exc

    if answer.startswith("❌"):
        raise HTTPException(status_code=502, detail=answer)

    return ChatResponse(
        answer=answer,
        session_id=request.session_id,
        model=VISION_MODEL if attachment_urls else MODEL,
    )


@app.post("/api/v1/chat/stream")
def chat_stream(request: ChatRequest, user=Depends(current_user)):
    if not os.getenv("GROQ_API_KEY"):
        raise HTTPException(status_code=503, detail="GROQ_API_KEY is not configured.")
    attachment_urls=[]
    rag_sources=[]
    for path in request.attachment_paths:
        try:
            attachment_urls.append(image_data_url(path, user_id=user["id"]))
        except ValueError:
            try:
                candidate=_safe_path(path,user["id"])
                if not is_supported_document(candidate):
                    raise ValueError("unsupported attachment type")
                user_root=(FILE_ROOT/f"user_{user['id']}").resolve()
                rag_sources.append(str(candidate.relative_to(user_root)))
            except (FileNotFoundError, PermissionError, ValueError) as exc:
                raise HTTPException(status_code=400, detail=f"Invalid document attachment: {path}") from exc
        except (FileNotFoundError, PermissionError) as exc:
            raise HTTPException(status_code=400, detail=f"Invalid image attachment: {path}") from exc

    internal_session=f"user-{user['id']}-{request.session_id}"

    def event_stream():
        import json
        yield "event: start\\ndata: " + json.dumps({"session_id": request.session_id}) + "\\n\\n"
        for chunk in stream_agent(
            request.message,
            session_id=internal_session,
            user_id=user["id"],
            image_urls=attachment_urls,
            rag_sources=rag_sources or None,
        ):
            yield "data: " + json.dumps({"text": chunk}, ensure_ascii=False) + "\\n\\n"
        yield "event: done\\ndata: {}\\n\\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control":"no-cache","Connection":"keep-alive","X-Accel-Buffering":"no"},
    )


@app.get("/api/v1/chats")
def list_chats(limit: int = 50, user=Depends(current_user)):
    limit = max(1, min(limit, 100))
    sessions = list_sessions(user_id=user["id"], limit=limit)
    chats = []
    prefix = f"user-{user['id']}-"
    for session in sessions:
        public_id = session[len(prefix):] if session.startswith(prefix) else session
        history = load_history(session, limit=4, user_id=user["id"])
        title = get_chat_title(session, user_id=user["id"]) or next((m["content"] for m in history if m["role"] == "user"), "New conversation")
        chats.append({
            "session_id": public_id,
            "title": title[:80],
            "messages": history,
        })
    return {"chats": chats}

class ChatTitleRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=80)

@app.patch("/api/v1/chats/{session_id}")
def rename_chat(session_id: str, request: ChatTitleRequest, user=Depends(current_user)):
    if not session_id or len(session_id) > 200:
        raise HTTPException(status_code=400, detail="Invalid session id.")
    internal_id = f"user-{user['id']}-{session_id}"
    if not load_history(internal_id, limit=1, user_id=user["id"]):
        raise HTTPException(status_code=404, detail="Chat not found.")
    set_chat_title(internal_id, request.title, user_id=user["id"])
    return {"session_id": session_id, "title": request.title.strip()}

@app.delete("/api/v1/chats/{session_id}")
def remove_chat(session_id: str, user=Depends(current_user)):
    if not session_id or len(session_id) > 200:
        raise HTTPException(status_code=400, detail="Invalid session id.")
    internal_id = f"user-{user['id']}-{session_id}"
    if not load_history(internal_id, limit=1, user_id=user["id"]):
        raise HTTPException(status_code=404, detail="Chat not found.")
    delete_chat(internal_id, user_id=user["id"])
    return {"deleted": True, "session_id": session_id}


@app.get("/api/v1/chats/{session_id}")
def get_chat(session_id: str, user=Depends(current_user)):
    if not session_id or len(session_id) > 200:
        raise HTTPException(status_code=400, detail="Invalid session id.")
    internal_id = f"user-{user['id']}-{session_id}"
    return {
        "session_id": session_id,
        "messages": load_history(internal_id, limit=100, user_id=user["id"]),
    }


@app.post("/api/v1/memories", response_model=MemoryResponse)
def create_memory(request: MemoryRequest, user=Depends(current_user)):
    remember_fact(request.fact, source=request.source, user_id=user["id"])
    return MemoryResponse(saved=True, fact=request.fact)


@app.get("/api/v1/memories")
def list_memories(limit: int = 50, user=Depends(current_user)):
    limit = max(1, min(limit, 100))
    return {"memories": recall_memories("", limit=limit, user_id=user["id"])}


@app.get("/api/v1/memories/search")
def search_memories(q: str, limit: int = 8, user=Depends(current_user)):
    if not q.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")
    limit = max(1, min(limit, 50))
    return {"query": q, "memories": recall_memories(q, limit=limit, user_id=user["id"])}


class RAGDocumentRequest(BaseModel):
    source: str = Field(..., min_length=1, max_length=500)
    content: str = Field(..., min_length=1, max_length=200000)


@app.post("/api/v1/rag/documents")
def create_rag_document(request: RAGDocumentRequest, user=Depends(current_user)):
    try:
        added = index_document(request.source, request.content, user_id=user["id"])
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"source": request.source, "chunks_added": added}


@app.post("/api/v1/rag/files")
def create_rag_file(path: str, user=Depends(current_user)):
    try:
        candidate = _safe_path(path, user["id"])
        if not is_supported_document(candidate):
            raise ValueError("Unsupported document type.")
        document_text = extract_and_limit(candidate)
        user_root = (FILE_ROOT / f"user_{user['id']}").resolve()
        source = str(candidate.relative_to(user_root))
        added = index_document(source, document_text, user_id=user["id"], replace_source=True)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File not found.")
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"path": path, "chunks_added": added}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024

def _file_metadata(path, user_id):
    candidate = _safe_path(path, user_id)
    if not candidate.is_file():
        raise FileNotFoundError(path)
    stat = candidate.stat()
    import mimetypes
    mime, _ = mimetypes.guess_type(candidate.name)
    return {
        "path": str(candidate.relative_to((FILE_ROOT / f"user-{user_id}").resolve())) if False else path,
        "name": candidate.name,
        "size": stat.st_size,
        "mime_type": mime or "application/octet-stream",
        "extension": candidate.suffix.lower(),
        "modified_at": stat.st_mtime,
    }

@app.post("/api/v1/files/upload")
async def upload_file(file: UploadFile = File(...), user=Depends(current_user)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required.")
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds the 10 MB upload limit.")
    try:
        path = save_upload(file.filename, content, user_id=user["id"])
        indexed_chunks = 0
        candidate = _safe_path(path, user["id"])
        if is_supported_document(candidate):
            document_text = extract_and_limit(candidate)
            user_root = (FILE_ROOT / f"user_{user['id']}").resolve()
            source = str(candidate.relative_to(user_root))
            indexed_chunks = index_document(source, document_text, user_id=user["id"], replace_source=True)
        return {"path": path, "name": candidate.name, "size": len(content), "indexed_chunks": indexed_chunks}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

@app.get("/api/v1/files")
def list_files(user=Depends(current_user)):
    root = (FILE_ROOT / f"user_{user['id']}").resolve()
    root.mkdir(parents=True, exist_ok=True)
    files = []
    import mimetypes
    for candidate in sorted(root.rglob("*")):
        if not candidate.is_file():
            continue
        relative = str(candidate.relative_to(root))
        stat = candidate.stat()
        mime, _ = mimetypes.guess_type(candidate.name)
        files.append({
            "path": relative,
            "name": candidate.name,
            "size": stat.st_size,
            "mime_type": mime or "application/octet-stream",
            "extension": candidate.suffix.lower(),
            "modified_at": stat.st_mtime,
        })
    rag_status = {item["source"]: item for item in rag_source_status(user_id=user["id"])}
    for item in files:
        status = rag_status.get(item["path"])
        item["rag_indexed"] = bool(status)
        item["rag_chunks"] = status["chunks"] if status else 0
        item["rag_indexed_at"] = status["indexed_at"] if status else None
    return {"files": files}

@app.get("/api/v1/files/{path:path}")
def get_file(path: str, user=Depends(current_user)):
    try:
        candidate = _safe_path(path, user["id"])
        if not candidate.is_file():
            raise FileNotFoundError(path)
    except (FileNotFoundError, PermissionError) as exc:
        raise HTTPException(status_code=404, detail="File not found.") from exc
    import mimetypes
    mime, _ = mimetypes.guess_type(candidate.name)
    return FileResponse(candidate, media_type=mime or "application/octet-stream", filename=candidate.name)

@app.delete("/api/v1/files/{path:path}")
def delete_file(path: str, user=Depends(current_user)):
    try:
        candidate = _safe_path(path, user["id"])
        if not candidate.is_file():
            raise FileNotFoundError(path)
        candidate.unlink()
        return {"deleted": True, "path": path}
    except (FileNotFoundError, PermissionError) as exc:
        raise HTTPException(status_code=404, detail="File not found.") from exc


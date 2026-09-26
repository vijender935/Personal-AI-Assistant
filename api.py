"""FastAPI REST API for the Personal AI Assistant."""
from __future__ import annotations

import os
import time
import logging
from typing import Optional

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel, Field

from agent import MODEL, VISION_MODEL, run_agent, stream_agent
from config import ALLOW_SHELL, DB_PATH, FILE_ROOT, ensure_directories
from db import connect
from tools import init_db, recall_memories, remember_fact, load_history, list_sessions, set_chat_title, get_chat_title, delete_chat, remove_last_assistant, remove_last_turn, save_turn
from memory import index_document, search_rag, rag_source_status, delete_semantic_memory, delete_rag_source, remember_semantic
from auth import authenticate, create_session, create_user, get_user, init_auth_db, revoke_session
from multimodal import save_upload, read_upload, image_data_url, ensure_local_file, delete_upload, list_uploads, _safe_path
from mcp_registry import registry_snapshot
from connectors import init_connectors_db, list_connectors, upsert_connector, delete_connector
from document_parser import extract_and_limit, is_supported_document

logger = logging.getLogger(__name__)

AUTH_RATE_LIMIT = max(1, int(os.getenv("AUTH_RATE_LIMIT", "10")))
AUTH_RATE_WINDOW = max(1, int(os.getenv("AUTH_RATE_WINDOW", "60")))
CHAT_RATE_LIMIT = max(1, int(os.getenv("CHAT_RATE_LIMIT", "30")))
CHAT_RATE_WINDOW = max(1, int(os.getenv("CHAT_RATE_WINDOW", "60")))
_auth_attempts: dict[str, list[float]] = {}
_chat_attempts: dict[str, list[float]] = {}

def _check_auth_rate_limit(key: str) -> None:
    now = time.monotonic()
    attempts = [stamp for stamp in _auth_attempts.get(key, []) if now - stamp < AUTH_RATE_WINDOW]
    if len(attempts) >= AUTH_RATE_LIMIT:
        raise HTTPException(status_code=429, detail="Too many authentication attempts. Try again later.")
    attempts.append(now)
    _auth_attempts[key] = attempts

    # Keep the process-local limiter bounded when many distinct clients/addresses
    # hit the auth endpoints. Expired buckets are safe to discard.
    if len(_auth_attempts) > 10000:
        cutoff = now - AUTH_RATE_WINDOW
        for bucket_key, bucket in list(_auth_attempts.items()):
            if not bucket or bucket[-1] < cutoff:
                _auth_attempts.pop(bucket_key, None)

def _client_key(request) -> str:
    return request.client.host if request.client else "unknown"

def _check_chat_rate_limit(key: str) -> None:
    now = time.monotonic()
    attempts = [stamp for stamp in _chat_attempts.get(key, []) if now - stamp < CHAT_RATE_WINDOW]
    if len(attempts) >= CHAT_RATE_LIMIT:
        raise HTTPException(status_code=429, detail="Too many chat requests. Try again later.")
    attempts.append(now)
    _chat_attempts[key] = attempts

    if len(_chat_attempts) > 10000:
        cutoff = now - CHAT_RATE_WINDOW
        for bucket_key, bucket in list(_chat_attempts.items()):
            if not bucket or bucket[-1] < cutoff:
                _chat_attempts.pop(bucket_key, None)

ensure_directories()
init_db()
init_auth_db()
init_connectors_db()

app = FastAPI(
    title="Personal AI Assistant API",
    version="0.11.0",
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
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        return response


app.add_middleware(SecurityHeadersMiddleware)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=20000)
    session_id: str = Field(default="default", min_length=1, max_length=200)
    attachment_paths: list[str] = Field(default_factory=list, max_length=6)
    web_search: bool = True
    memory: bool = True


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
def register(request: RegisterRequest, raw_request: Request):
    _check_auth_rate_limit("register:" + _client_key(raw_request))
    try:
        user = create_user(request.name, request.email, request.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"user": user, "token": create_session(user["id"])}


@app.post("/api/v1/auth/login")
def login(request: LoginRequest, raw_request: Request):
    email_key = request.email.strip().lower()
    _check_auth_rate_limit("login:" + _client_key(raw_request) + ":" + email_key)
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
        "version": "0.11.0",
        "model": MODEL,
        "shell_enabled": ALLOW_SHELL,
    }


class MCPConnectorRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    transport: str = Field(default="streamable-http")
    url: str = Field(..., min_length=8, max_length=2000)
    allowed_tools: list[str] = Field(default_factory=list, max_length=100)
    headers: dict[str, str] = Field(default_factory=dict)


@app.get("/api/v1/mcp/connectors")
def get_mcp_connectors(user=Depends(current_user)):
    return {"connectors": list_connectors(user["id"])}


@app.post("/api/v1/mcp/connectors")
def add_mcp_connector(request: MCPConnectorRequest, user=Depends(current_user)):
    try:
        connector = upsert_connector(
            user["id"],
            request.name,
            request.transport,
            request.url,
            request.allowed_tools,
            request.headers,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"connector": connector}


@app.post("/api/v1/mcp/connectors/{connector_id}/test")
def test_mcp_connector(connector_id: int, user=Depends(current_user)):
    connector = next((x for x in list_connectors(user["id"]) if x["id"] == connector_id), None)
    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found.")
    try:
        from mcp_client import discover_connector_tool_schemas
        matching = discover_connector_tool_schemas(user["id"], connector["name"])
        return {"ok": True, "tools": len(matching), "tool_names": [s.get("function", {}).get("name") for s in matching]}
    except Exception as exc:
        logger.exception("MCP connector test failed: %s", connector["name"])
        detail = str(exc).strip() or "Unknown MCP connection error."
        if len(detail) > 500:
            detail = detail[:500]
        raise HTTPException(status_code=502, detail=f"MCP connector test failed: {detail}") from exc


@app.delete("/api/v1/mcp/connectors/{connector_id}")
def remove_mcp_connector(connector_id: int, user=Depends(current_user)):
    if not delete_connector(user["id"], connector_id):
        raise HTTPException(status_code=404, detail="Connector not found.")
    return {"deleted": True, "id": connector_id}


@app.get("/api/v1/mcp/servers")
def get_mcp_servers(user=Depends(current_user)):
    return {"servers": registry_snapshot(user["id"])}


@app.post("/api/v1/chat", response_model=ChatResponse)
def chat(request: ChatRequest, user=Depends(current_user)):
    if not os.getenv("GROQ_API_KEY"):
        raise HTTPException(status_code=503, detail="GROQ_API_KEY is not configured.")

    try:
        attachment_urls = []
        rag_sources = []
        for path in request.attachment_paths:
            try:
                attachment_urls.append(image_data_url(path, user_id=user["id"]))
            except ValueError:
                try:
                    candidate = ensure_local_file(path, user["id"])
                    if not is_supported_document(candidate):
                        raise ValueError("unsupported attachment type")
                    user_root = (FILE_ROOT / f"user_{user['id']}").resolve()
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
            memory_enabled=request.memory,
            web_search_enabled=request.web_search,
            verbose=False,
        )
    except HTTPException:
        raise
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
def chat_stream(request: ChatRequest, raw_request: Request, user=Depends(current_user)):
    _check_chat_rate_limit(f"chat:{user['id']}:{_client_key(raw_request)}")
    if not os.getenv("GROQ_API_KEY"):
        raise HTTPException(status_code=503, detail="GROQ_API_KEY is not configured.")
    attachment_urls = []
    rag_sources = []
    for path in request.attachment_paths:
        try:
            attachment_urls.append(image_data_url(path, user_id=user["id"]))
        except ValueError:
            try:
                candidate = ensure_local_file(path, user["id"])
                if not is_supported_document(candidate):
                    raise ValueError("unsupported attachment type")
                user_root = (FILE_ROOT / f"user_{user['id']}").resolve()
                rag_sources.append(str(candidate.relative_to(user_root)))
            except (FileNotFoundError, PermissionError, ValueError) as exc:
                raise HTTPException(status_code=400, detail=f"Invalid document attachment: {path}") from exc
        except (FileNotFoundError, PermissionError) as exc:
            raise HTTPException(status_code=400, detail=f"Invalid image attachment: {path}") from exc

    internal_session = f"user-{user['id']}-{request.session_id}"

    def event_stream():
        import json

        yield "event: start\ndata: " + json.dumps({"session_id": request.session_id}) + "\n\n"
        try:
            for chunk in stream_agent(
                request.message,
                session_id=internal_session,
                user_id=user["id"],
                image_urls=attachment_urls,
                rag_sources=rag_sources or None,
                memory_enabled=request.memory,
                web_search_enabled=request.web_search,
            ):
                yield "event: delta\ndata: " + json.dumps({"text": chunk}, ensure_ascii=False) + "\n\n"
            yield "event: done\ndata: {}\n\n"
        except Exception:
            logger.exception("Streaming request failed")
            yield "event: error\ndata: " + json.dumps({"detail": "Streaming request failed."}) + "\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
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


@app.post("/api/v1/chats/{session_id}/regenerate")
def regenerate_chat(session_id: str, user=Depends(current_user)):
    if not session_id or len(session_id) > 200:
        raise HTTPException(status_code=400, detail="Invalid session id.")
    internal_id = f"user-{user['id']}-{session_id}"
    history = load_history(internal_id, limit=100, user_id=user["id"])
    if not history or history[-1]["role"] != "assistant":
        raise HTTPException(status_code=400, detail="No assistant response available to regenerate.")
    if not remove_last_assistant(internal_id, user_id=user["id"]):
        raise HTTPException(status_code=400, detail="Unable to regenerate response.")
    user_message = next((m["content"] for m in reversed(history[:-1]) if m["role"] == "user"), None)
    if not user_message:
        raise HTTPException(status_code=400, detail="No user message available.")
    try:
        answer = run_agent(user_message, session_id=internal_id, user_id=user["id"], verbose=False)
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Regeneration failed.") from exc
    return {"session_id": session_id, "answer": answer}


@app.post("/api/v1/chats/{session_id}/edit")
def edit_last_message(session_id: str, request: ChatRequest, user=Depends(current_user)):
    if not session_id or len(session_id) > 200:
        raise HTTPException(status_code=400, detail="Invalid session id.")
    message = request.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message cannot be empty.")
    internal_id = f"user-{user['id']}-{session_id}"
    history = load_history(internal_id, limit=100, user_id=user["id"])
    if len(history) < 2 or history[-2]["role"] != "user" or history[-1]["role"] != "assistant":
        raise HTTPException(status_code=400, detail="Last turn cannot be edited.")
    if not remove_last_turn(internal_id, user_id=user["id"]):
        raise HTTPException(status_code=400, detail="Unable to edit last turn.")
    try:
        answer = run_agent(message, session_id=internal_id, user_id=user["id"], verbose=False)
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Edit and resend failed.") from exc
    return {"session_id": session_id, "message": message, "answer": answer}


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
    try:
        remember_semantic(request.fact, source=request.source, user_id=user["id"])
    except Exception as exc:
        logger.warning("Semantic memory indexing failed: %s", exc)
    return MemoryResponse(saved=True, fact=request.fact)


@app.delete("/api/v1/memories")
def delete_memory(fact: str, user=Depends(current_user)):
    if not fact.strip():
        raise HTTPException(status_code=400, detail="Fact cannot be empty.")
    exact = fact.strip()
    deleted_exact = delete_semantic_memory(exact, user_id=user["id"])
    with connect(DB_PATH) as con:
        cur = con.execute("DELETE FROM memories WHERE user_id=? AND fact=?", (user["id"], exact))
        deleted = cur.rowcount > 0 or deleted_exact
    return {"deleted": deleted, "fact": exact}


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
        "path": path,
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
    except RuntimeError as exc:
        return {
            "path": path,
            "name": candidate.name,
            "size": len(content),
            "indexed_chunks": 0,
            "indexing_skipped": True,
            "reason": str(exc),
        }


@app.get("/api/v1/files")
def list_files(user=Depends(current_user)):
    files = list_uploads(user["id"])
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
        candidate = ensure_local_file(path, user["id"])
    except (FileNotFoundError, PermissionError) as exc:
        raise HTTPException(status_code=404, detail="File not found.") from exc
    import mimetypes
    mime, _ = mimetypes.guess_type(candidate.name)
    return FileResponse(candidate, media_type=mime or "application/octet-stream", filename=candidate.name)


@app.delete("/api/v1/files/{path:path}")
def delete_file(path: str, user=Depends(current_user)):
    try:
        delete_upload(path, user_id=user["id"])
        deleted_chunks = delete_rag_source(path, user_id=user["id"])
        return {"deleted": True, "path": path, "rag_chunks_deleted": deleted_chunks}
    except (FileNotFoundError, PermissionError) as exc:
        raise HTTPException(status_code=404, detail="File not found.") from exc

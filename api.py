"""FastAPI REST API for the Personal AI Assistant."""
from __future__ import annotations

import os
import time
from typing import Optional

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from agent import MODEL, VISION_MODEL, run_agent
from config import ALLOW_SHELL, FILE_ROOT, ensure_directories
from tools import init_db, recall_memories, remember_fact, load_history, list_sessions
from memory import index_document, search_rag
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


@app.get("/api/v1/chats")
def list_chats(limit: int = 50, user=Depends(current_user)):
    limit = max(1, min(limit, 100))
    sessions = list_sessions(user_id=user["id"], limit=limit)
    chats = []
    prefix = f"user-{user['id']}-"
    for session in sessions:
        public_id = session[len(prefix):] if session.startswith(prefix) else session
        history = load_history(session, limit=4, user_id=user["id"])
        title = next((m["content"] for m in history if m["role"] == "user"), "New conversation")
        chats.append({
            "session_id": public_id,
            "title": title[:80],
            "messages": history,
        })
    return {"chats": chats}


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

"""FastAPI REST API for the Personal AI Assistant."""
from __future__ import annotations

import os
import time
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from agent import MODEL, run_agent
from config import ALLOW_SHELL, ensure_directories
from tools import init_db, recall_memories, remember_fact
from memory import index_document, index_file, search_rag

ensure_directories()
init_db()

app = FastAPI(
    title="Personal AI Assistant API",
    version="0.7.0",
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
        "version": "0.7.0",
        "model": MODEL,
        "shell_enabled": ALLOW_SHELL,
    }


@app.post("/api/v1/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    if not os.getenv("GROQ_API_KEY"):
        raise HTTPException(status_code=503, detail="GROQ_API_KEY is not configured.")

    try:
        answer = run_agent(
            request.message,
            session_id=request.session_id,
            verbose=False,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Agent execution failed.") from exc

    if answer.startswith("❌"):
        raise HTTPException(status_code=502, detail=answer)

    return ChatResponse(
        answer=answer,
        session_id=request.session_id,
        model=MODEL,
    )


@app.post("/api/v1/memories", response_model=MemoryResponse)
def create_memory(request: MemoryRequest):
    remember_fact(request.fact, source=request.source)
    return MemoryResponse(saved=True, fact=request.fact)


@app.get("/api/v1/memories")
def list_memories(limit: int = 50):
    limit = max(1, min(limit, 100))
    return {"memories": recall_memories("", limit=limit)}


@app.get("/api/v1/memories/search")
def search_memories(q: str, limit: int = 8):
    if not q.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")
    limit = max(1, min(limit, 50))
    return {"query": q, "memories": recall_memories(q, limit=limit)}


class RAGDocumentRequest(BaseModel):
    source: str = Field(..., min_length=1, max_length=500)
    content: str = Field(..., min_length=1, max_length=200000)


@app.post("/api/v1/rag/documents")
def create_rag_document(request: RAGDocumentRequest):
    try:
        added = index_document(request.source, request.content)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"source": request.source, "chunks_added": added}


@app.post("/api/v1/rag/files")
def create_rag_file(path: str):
    try:
        added = index_file(path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File not found.")
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"path": path, "chunks_added": added}


@app.get("/api/v1/rag/search")
def rag_search(q: str, limit: int = 5):
    if not q.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")
    try:
        return {"query": q, "results": search_rag(q, limit=limit)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/v1")
def api_root():
    return {
        "service": "Personal AI Assistant API",
        "version": "0.7.0",
        "endpoints": [
            "GET /health",
            "GET /api/v1/info",
            "POST /api/v1/chat",
            "GET /api/v1/memories",
            "POST /api/v1/memories",
            "GET /api/v1/memories/search",
            "POST /api/v1/rag/documents",
            "POST /api/v1/rag/files",
            "GET /api/v1/rag/search",
        ],
    }

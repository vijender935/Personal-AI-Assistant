"""Semantic memory and lightweight local RAG."""
from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path
from typing import Iterable

from config import DB_PATH, FILE_ROOT, ensure_directories

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
MAX_CHUNK_CHARS = 1800
CHUNK_OVERLAP = 250


_model = None


def _get_model():
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "Semantic search requires sentence-transformers. "
                "Run: pip install -r requirements.txt"
            ) from exc
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def _embedding(text: str) -> bytes:
    import numpy as np
    vector = _get_model().encode(
        text, normalize_embeddings=True, convert_to_numpy=True
    ).astype(np.float32)
    return vector.tobytes()


def _vector(blob: bytes):
    import numpy as np
    return np.frombuffer(blob, dtype=np.float32)


def init_semantic_store() -> None:
    ensure_directories()
    with sqlite3.connect(DB_PATH) as con:
        con.execute("""CREATE TABLE IF NOT EXISTS semantic_memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fact TEXT NOT NULL UNIQUE, source TEXT,
            embedding BLOB NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP)""")
        con.execute("""CREATE TABLE IF NOT EXISTS rag_documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL, chunk_index INTEGER NOT NULL,
            content TEXT NOT NULL, content_hash TEXT NOT NULL UNIQUE,
            embedding BLOB NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP)""")
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_rag_documents_source ON rag_documents(source)"
        )


def remember_semantic(fact: str, source: str = "user") -> bool:
    fact = fact.strip()
    if not fact:
        return False
    init_semantic_store()
    with sqlite3.connect(DB_PATH) as con:
        con.execute(
            "INSERT OR IGNORE INTO semantic_memories(fact, source, embedding) VALUES (?, ?, ?)",
            (fact, source, _embedding(fact)),
        )
    return True


def search_semantic_memories(query: str, limit: int = 8) -> list[str]:
    query = query.strip()
    if not query:
        return []
    init_semantic_store()
    q = _vector(_embedding(query))
    with sqlite3.connect(DB_PATH) as con:
        rows = con.execute("SELECT fact, embedding FROM semantic_memories").fetchall()
    scored = []
    for fact, blob in rows:
        v = _vector(blob)
        if len(v) == len(q):
            scored.append((float(q @ v), fact))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [fact for _, fact in scored[:max(1, min(limit, 20))]]


def _chunks(text: str) -> Iterable[str]:
    text = text.strip()
    start = 0
    while start < len(text):
        end = min(len(text), start + MAX_CHUNK_CHARS)
        chunk = text[start:end].strip()
        if chunk:
            yield chunk
        if end >= len(text):
            break
        start = max(start + 1, end - CHUNK_OVERLAP)


def index_document(source: str, content: str) -> int:
    source, content = source.strip(), content.strip()
    if not source or not content:
        return 0
    init_semantic_store()
    added = 0
    for index, chunk in enumerate(_chunks(content)):
        digest = hashlib.sha256(
            f"{source}\n{index}\n{chunk}".encode()
        ).hexdigest()
        with sqlite3.connect(DB_PATH) as con:
            if con.execute(
                "SELECT 1 FROM rag_documents WHERE content_hash = ?", (digest,)
            ).fetchone():
                continue
            con.execute(
                """INSERT INTO rag_documents
                   (source, chunk_index, content, content_hash, embedding)
                   VALUES (?, ?, ?, ?, ?)""",
                (source, index, chunk, digest, _embedding(chunk)),
            )
        added += 1
    return added


def index_file(path: str) -> int:
    candidate = (FILE_ROOT / path).resolve()
    try:
        candidate.relative_to(FILE_ROOT.resolve())
    except ValueError as exc:
        raise PermissionError(f"path is outside the allowed file root: {FILE_ROOT}") from exc
    if not candidate.is_file():
        raise FileNotFoundError(path)
    return index_document(
        str(candidate.relative_to(FILE_ROOT)),
        candidate.read_text(encoding="utf-8", errors="replace"),
    )


def search_rag(query: str, limit: int = 5) -> list[dict[str, object]]:
    query = query.strip()
    if not query:
        return []
    init_semantic_store()
    q = _vector(_embedding(query))
    with sqlite3.connect(DB_PATH) as con:
        rows = con.execute(
            "SELECT source, chunk_index, content, embedding FROM rag_documents"
        ).fetchall()
    scored = []
    for source, chunk_index, content, blob in rows:
        v = _vector(blob)
        if len(v) == len(q):
            scored.append((float(q @ v), source, chunk_index, content))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [
        {"score": round(score, 4), "source": source,
         "chunk_index": chunk_index, "content": content}
        for score, source, chunk_index, content in scored[:max(1, min(limit, 10))]
    ]

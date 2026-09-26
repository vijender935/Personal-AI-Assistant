"""Semantic memory and lightweight RAG for the single-user assistant."""
from __future__ import annotations
import hashlib
from config import ensure_directories
from db import connect

MODEL_NAME="BAAI/bge-small-en-v1.5"
MAX_CHUNK_CHARS=1800
CHUNK_OVERLAP=250
EMBEDDING_VERSION="fastembed-bge-small-en-v1.5"
_model=None

def _get_model():
    global _model
    if _model is None:
        from fastembed import TextEmbedding
        _model=TextEmbedding(model_name=MODEL_NAME)
    return _model

def _embedding(text,kind="passage"):
    import numpy as np
    generator=_get_model().query_embed([text]) if kind=="query" else _get_model().passage_embed([text])
    vector=np.asarray(next(generator),dtype=np.float32)
    norm=float(np.linalg.norm(vector))
    if norm: vector=vector/norm
    return vector.tobytes()

def _vector(blob):
    import numpy as np
    return np.frombuffer(blob,dtype=np.float32)

def init_semantic_store():
    ensure_directories()
    with connect() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS semantic_memories(
            id BIGSERIAL PRIMARY KEY,fact TEXT NOT NULL UNIQUE,source TEXT,
            embedding BYTEA NOT NULL,embedding_version TEXT NOT NULL DEFAULT 'legacy',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        con.execute("""CREATE TABLE IF NOT EXISTS rag_documents(
            id BIGSERIAL PRIMARY KEY,source TEXT NOT NULL,chunk_index INTEGER NOT NULL,
            content TEXT NOT NULL,content_hash TEXT NOT NULL UNIQUE,embedding BYTEA NOT NULL,
            embedding_version TEXT NOT NULL DEFAULT 'legacy',created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        for table in ("semantic_memories","rag_documents"):
            try:
                if table=="semantic_memories":
                    con.execute("DROP INDEX IF EXISTS uq_semantic_user_fact")
                    con.execute("DROP INDEX IF EXISTS idx_semantic_user")
                if table=="rag_documents":
                    con.execute("DROP INDEX IF EXISTS idx_rag_user")
                con.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS user_id")
            except Exception:
                pass

def remember_semantic(fact,source="user"):
    fact=fact.strip()
    if not fact:return False
    init_semantic_store()
    blob=_embedding(fact)
    with connect() as con:
        con.execute("""INSERT INTO semantic_memories(fact,source,embedding,embedding_version) VALUES(?,?,?,?)
            ON CONFLICT(fact) DO UPDATE SET source=excluded.source,embedding=excluded.embedding,embedding_version=excluded.embedding_version""",
            (fact,source,blob,EMBEDDING_VERSION))
    return True

def search_semantic_memories(query,limit=8):
    init_semantic_store()
    limit=max(1,min(int(limit),50))
    with connect() as con:
        rows=con.execute("SELECT fact,embedding FROM semantic_memories").fetchall()
    if not rows:return []
    q=_vector(_embedding(query,"query"))
    scored=[]
    for fact,blob in rows:
        try: scored.append((float(q @ _vector(blob)),fact))
        except Exception: continue
    scored.sort(key=lambda x:-x[0])
    return [fact for _,fact in scored[:limit]]

def delete_semantic_memory(fact):
    init_semantic_store()
    with connect() as con:
        cur=con.execute("DELETE FROM semantic_memories WHERE fact=?",(fact.strip(),))
    return cur.rowcount>0

def _chunks(text):
    text=text.strip()
    if not text:return []
    chunks=[]; start=0
    while start<len(text):
        end=min(len(text),start+MAX_CHUNK_CHARS)
        if end<len(text):
            split=max(text.rfind("\n",start,end),text.rfind(" ",start,end))
            if split>start+MAX_CHUNK_CHARS//2:end=split
        chunk=text[start:end].strip()
        if chunk: chunks.append(chunk)
        if end>=len(text):break
        start=max(end-CHUNK_OVERLAP,start+1)
    return chunks

def index_document(source,content,replace_source=False):
    init_semantic_store()
    chunks=_chunks(content)
    if replace_source: delete_rag_source(source)
    with connect() as con:
        for index,chunk in enumerate(chunks):
            digest=hashlib.sha256(chunk.encode("utf-8")).hexdigest()
            blob=_embedding(chunk)
            con.execute("""INSERT INTO rag_documents(source,chunk_index,content,content_hash,embedding,embedding_version)
                VALUES(?,?,?,?,?,?)
                ON CONFLICT(content_hash) DO UPDATE SET
                source=excluded.source,chunk_index=excluded.chunk_index,content=excluded.content,
                embedding=excluded.embedding,embedding_version=excluded.embedding_version""",
                (source,index,chunk,digest,blob,EMBEDDING_VERSION))
    return len(chunks)

def search_rag(query,limit=4,sources=None):
    init_semantic_store()
    limit=max(1,min(int(limit),50))
    with connect() as con:
        if sources:
            placeholders=",".join("?" for _ in sources)
            rows=con.execute(
                f"SELECT source,content,embedding FROM rag_documents WHERE source IN ({placeholders})",
                tuple(sources)).fetchall()
        else:
            rows=con.execute("SELECT source,content,embedding FROM rag_documents").fetchall()
    if not rows:return []
    q=_vector(_embedding(query,"query")); scored=[]
    for source,content,blob in rows:
        try: scored.append((float(q @ _vector(blob)),source,content))
        except Exception: continue
    scored.sort(key=lambda x:-x[0])
    return [{"source":s,"content":c,"score":round(score,4)} for score,s,c in scored[:limit]]

def rag_source_status():
    init_semantic_store()
    with connect() as con:
        rows=con.execute("SELECT source,COUNT(*),MAX(created_at) FROM rag_documents GROUP BY source ORDER BY source").fetchall()
    return [{"source":s,"chunks":int(n),"indexed_at":created} for s,n,created in rows]

def delete_rag_source(source):
    init_semantic_store()
    with connect() as con:
        cur=con.execute("DELETE FROM rag_documents WHERE source=?",(source,))
    return cur.rowcount

def migrate_legacy_memory_tables():
    """Run the PostgreSQL schema cleanup for legacy user-scoped columns."""
    init_semantic_store()

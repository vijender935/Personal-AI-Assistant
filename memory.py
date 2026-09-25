"""Semantic memory and lightweight local RAG with per-user isolation."""
from __future__ import annotations
import hashlib,sqlite3
from typing import Iterable
from config import DB_PATH,FILE_ROOT,ensure_directories
from multimodal import _safe_path
MODEL_NAME="BAAI/bge-small-en-v1.5";MAX_CHUNK_CHARS=1800;CHUNK_OVERLAP=250
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
def _ensure_column(con,table,column,definition):
    cols={row[1] for row in con.execute(f"PRAGMA table_info({table})")}
    if column not in cols:con.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
def init_semantic_store():
    ensure_directories()
    with sqlite3.connect(DB_PATH) as con:
        con.execute("""CREATE TABLE IF NOT EXISTS semantic_memories(id INTEGER PRIMARY KEY AUTOINCREMENT,fact TEXT NOT NULL UNIQUE,source TEXT,user_id INTEGER NOT NULL DEFAULT 0,embedding BLOB NOT NULL,created_at DATETIME DEFAULT CURRENT_TIMESTAMP)""")
        con.execute("""CREATE TABLE IF NOT EXISTS rag_documents(id INTEGER PRIMARY KEY AUTOINCREMENT,source TEXT NOT NULL,chunk_index INTEGER NOT NULL,content TEXT NOT NULL,content_hash TEXT NOT NULL UNIQUE,user_id INTEGER NOT NULL DEFAULT 0,embedding BLOB NOT NULL,created_at DATETIME DEFAULT CURRENT_TIMESTAMP)""")
        _ensure_column(con,"semantic_memories","user_id","INTEGER NOT NULL DEFAULT 0")
        _ensure_column(con,"rag_documents","user_id","INTEGER NOT NULL DEFAULT 0")
        con.execute("CREATE INDEX IF NOT EXISTS idx_semantic_user ON semantic_memories(user_id)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_rag_user ON rag_documents(user_id)")
def remember_semantic(fact,source="user",user_id=0):
    fact=fact.strip()
    if not fact:return False
    init_semantic_store()
    with sqlite3.connect(DB_PATH) as con:
        try:con.execute("INSERT INTO semantic_memories(fact,source,user_id,embedding) VALUES(?,?,?,?)",(fact,source,user_id,_embedding(fact)))
        except sqlite3.IntegrityError:pass
    return True
def search_semantic_memories(query,limit=8,user_id=0):
    query=query.strip()
    if not query:return []
    init_semantic_store();q=_vector(_embedding(query))
    with sqlite3.connect(DB_PATH) as con:rows=con.execute("SELECT fact,embedding FROM semantic_memories WHERE user_id=?",(user_id,)).fetchall()
    scored=[]
    for fact,blob in rows:
        v=_vector(blob)
        if len(v)==len(q):scored.append((float(q@v),fact))
    scored.sort(key=lambda x:x[0],reverse=True)
    return [fact for _,fact in scored[:max(1,min(limit,20))]]
def _chunks(text)->Iterable[str]:
    text=text.strip();start=0
    while start<len(text):
        end=min(len(text),start+MAX_CHUNK_CHARS);chunk=text[start:end].strip()
        if chunk:yield chunk
        if end>=len(text):break
        start=max(start+1,end-CHUNK_OVERLAP)
def index_document(source,content,user_id=0,replace_source=False):
    source,content=source.strip(),content.strip()
    if not source or not content:return 0
    init_semantic_store()
    if replace_source:
        with sqlite3.connect(DB_PATH) as con: con.execute("DELETE FROM rag_documents WHERE user_id=? AND source=?",(user_id,source))
    added=0
    for index,chunk in enumerate(_chunks(content)):
        digest=hashlib.sha256(f"{user_id}\n{source}\n{index}\n{chunk}".encode()).hexdigest()
        with sqlite3.connect(DB_PATH) as con:
            if con.execute("SELECT 1 FROM rag_documents WHERE content_hash=? AND user_id=?",(digest,user_id)).fetchone():continue
            con.execute("INSERT INTO rag_documents(source,chunk_index,content,content_hash,user_id,embedding) VALUES(?,?,?,?,?,?)",(source,index,chunk,digest,user_id,_embedding(chunk)))
        added+=1
    return added
def index_file(path,user_id=0,replace_source=False):
    candidate=_safe_path(path,user_id)
    if not candidate.is_file():raise FileNotFoundError(path)
    user_root=(FILE_ROOT/f"user_{user_id}").resolve()
    source=str(candidate.relative_to(user_root))
    return index_document(source,candidate.read_text(encoding="utf-8",errors="replace"),user_id=user_id,replace_source=replace_source)
def search_rag(query,limit=5,user_id=0,sources=None):
    query=query.strip()
    if not query:return []
    init_semantic_store();q=_vector(_embedding(query))
    with sqlite3.connect(DB_PATH) as con:
        if sources:
            placeholders=",".join("?" for _ in sources)
            rows=con.execute(f"SELECT source,chunk_index,content,embedding FROM rag_documents WHERE user_id=? AND source IN ({placeholders})",(user_id,*sources)).fetchall()
        else:
            rows=con.execute("SELECT source,chunk_index,content,embedding FROM rag_documents WHERE user_id=?",(user_id,)).fetchall()
    scored=[]
    for source,chunk_index,content,blob in rows:
        v=_vector(blob)
        if len(v)==len(q):scored.append((float(q@v),source,chunk_index,content))
    scored.sort(key=lambda x:x[0],reverse=True)
    return [{"score":round(score,4),"source":source,"chunk_index":chunk_index,"content":content} for score,source,chunk_index,content in scored[:max(1,min(limit,10))]]

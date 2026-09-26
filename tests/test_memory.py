import memory
from db import connect

def _fake_embedding(text,kind="passage"):
    import numpy as np
    vector=np.zeros(4,dtype=np.float32)
    vector[0 if kind=="query" else 1]=1.0
    return vector.tobytes()

def _setup(monkeypatch):
    monkeypatch.setattr(memory,"_embedding",_fake_embedding)
    memory.init_semantic_store()
    with connect() as con:
        con.execute("DELETE FROM rag_documents")
        con.execute("DELETE FROM semantic_memories")

def test_rag_round_trip_and_source_scope(monkeypatch):
    _setup(monkeypatch)
    assert memory.index_document("report.txt","Python FastAPI backend")==1
    assert memory.index_document("notes.txt","car maintenance")==1
    hits=memory.search_rag("FastAPI",sources=["report.txt"])
    assert hits and hits[0]["source"]=="report.txt"
    assert memory.search_rag("FastAPI",sources=["notes.txt"])[0]["source"]=="notes.txt"

def test_replace_source(monkeypatch):
    _setup(monkeypatch)
    memory.index_document("doc.txt","old content")
    memory.index_document("doc.txt","new content",replace_source=True)
    assert memory.search_rag("new",sources=["doc.txt"])[0]["content"]=="new content"

def test_embedding_version(monkeypatch):
    _setup(monkeypatch)
    memory.index_document("versioned.txt","hello")
    with connect() as con:
        assert con.execute("SELECT embedding_version FROM rag_documents").fetchone()[0]==memory.EMBEDDING_VERSION

def test_rag_source_status(monkeypatch):
    _setup(monkeypatch)
    memory.index_document("a.txt","one")
    memory.index_document("b.txt","two")
    assert {x["source"] for x in memory.rag_source_status()}=={"a.txt","b.txt"}

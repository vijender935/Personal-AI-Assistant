import memory


def _fake_embedding(text, kind="passage"):
    import numpy as np
    vector=np.zeros(4,dtype=np.float32)
    vector[0 if kind=="query" else 1]=1.0
    return vector.tobytes()


def _setup(monkeypatch,tmp_path):
    monkeypatch.setattr(memory,"DB_PATH",str(tmp_path/"memory.db"))
    monkeypatch.setattr(memory,"FILE_ROOT",tmp_path/"files")
    monkeypatch.setattr(memory,"_embedding",_fake_embedding)


def test_rag_round_trip_and_source_scope(monkeypatch,tmp_path):
    _setup(monkeypatch,tmp_path)
    assert memory.index_document("report.txt","Python FastAPI backend",user_id=1)==1
    assert memory.index_document("notes.txt","car maintenance",user_id=1)==1
    hits=memory.search_rag("FastAPI",user_id=1,sources=["report.txt"])
    assert len(hits)==1
    assert hits[0]["source"]=="report.txt"
    assert "FastAPI" in hits[0]["content"]
    assert memory.search_rag("FastAPI",user_id=1,sources=["notes.txt"])==[]


def test_user_isolation(monkeypatch,tmp_path):
    _setup(monkeypatch,tmp_path)
    memory.index_document("private.txt","secret project",user_id=1)
    memory.index_document("private.txt","different project",user_id=2)
    assert memory.search_rag("secret",user_id=1)[0]["content"]=="secret project"
    assert memory.search_rag("secret",user_id=2)==[]


def test_replace_source(monkeypatch,tmp_path):
    _setup(monkeypatch,tmp_path)
    memory.index_document("doc.txt","old content",user_id=1)
    memory.index_document("doc.txt","new content",user_id=1,replace_source=True)
    hits=memory.search_rag("new",user_id=1,sources=["doc.txt"])
    assert len(hits)==1
    assert hits[0]["content"]=="new content"


def test_embedding_version_is_persisted(monkeypatch,tmp_path):
    _setup(monkeypatch,tmp_path)
    memory.index_document("versioned.txt","hello",user_id=1)
    with __import__("sqlite3").connect(memory.DB_PATH) as con:
        version=con.execute("SELECT embedding_version FROM rag_documents").fetchone()[0]
    assert version==memory.EMBEDDING_VERSION

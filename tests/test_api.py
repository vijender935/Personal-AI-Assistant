from fastapi.testclient import TestClient
import api,tools,auth,pytest
client=TestClient(api.app)

@pytest.fixture(autouse=True)
def authenticated():
    if not auth.account_exists():
        auth.setup_account("Test User","test@example.com","TestPass123")
    result=auth.login("test@example.com","TestPass123")
    client.cookies.clear()
    client.cookies.set(auth.SESSION_COOKIE,result[0])
    yield
    client.cookies.clear()

def test_health():
    assert client.get("/health").status_code==200
def test_info_single_user():
    assert client.get("/api/v1/info").json()["mode"]=="single-user"
def test_auth_status():
    r=client.get("/api/v1/auth/status");assert r.status_code==200;assert r.json()["authenticated"] is True
def test_chat_without_key(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY",raising=False)
    assert client.post("/api/v1/chat",json={"message":"Hello","session_id":"test"}).status_code==503
def test_memory_api(monkeypatch):
    monkeypatch.setattr(api,"remember_semantic",lambda *a,**k:True)
    r=client.post("/api/v1/memories",json={"fact":"Phase 1 test memory","source":"test"});assert r.status_code==200
    assert r.json()["saved"] is True
def test_chat_management():
    tools.save_turn("api-test","hello","world")
    assert client.get("/api/v1/chats/api-test").status_code==200
    assert client.patch("/api/v1/chats/api-test",json={"title":"Renamed"}).status_code==200
    assert client.get("/api/v1/chats/api-test").json()["title"]=="Renamed"
    assert client.delete("/api/v1/chats/api-test").json()["deleted"] is True
def test_missing_chat():
    assert client.patch("/api/v1/chats/missing",json={"title":"Renamed"}).status_code==404
    assert client.delete("/api/v1/chats/missing").status_code==404
def test_settings_round_trip():
    r=client.patch("/api/v1/settings",json={"appearance":"Dark","haptics":False});assert r.status_code==200
    assert r.json()["settings"]["appearance"]=="Dark"
def test_protected_without_session():
    client.cookies.clear()
    assert client.get("/api/v1/settings").status_code==401

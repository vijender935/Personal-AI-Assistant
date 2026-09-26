from fastapi.testclient import TestClient
import api,tools
client=TestClient(api.app)
def test_health(): assert client.get("/health").status_code==200
def test_info_single_user(): assert client.get("/api/v1/info").json()["mode"]=="single-user"
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
def test_no_auth_routes():
 assert client.post("/api/v1/auth/login",json={"email":"x","password":"y"}).status_code==404

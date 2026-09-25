from fastapi.testclient import TestClient
import uuid

import api


client = TestClient(api.app)


def auth_headers():
    email = f"test-{uuid.uuid4().hex}@example.com"
    response = client.post("/api/v1/auth/register", json={"name":"Test User","email":email,"password":"password123"})
    assert response.status_code == 200
    return {"Authorization": "Bearer " + response.json()["token"]}


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_info():
    response = client.get("/api/v1/info")
    assert response.status_code == 200
    assert response.json()["name"] == "Personal AI Assistant"


def test_memory_api():
    headers = auth_headers()
    response = client.post(
        "/api/v1/memories",
        json={"fact": "Phase 7 test memory", "source": "test"},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["saved"] is True

    response = client.get("/api/v1/memories/search", params={"q": "Phase 7"}, headers=headers)
    assert response.status_code == 200
    assert "Phase 7 test memory" in response.json()["memories"]


def test_chat_without_api_key(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    response = client.post(
        "/api/v1/chat",
        json={"message": "Hello", "session_id": "test"},
    )
    assert response.status_code == 503

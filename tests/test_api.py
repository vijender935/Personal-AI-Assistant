from fastapi.testclient import TestClient

import api


client = TestClient(api.app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_info():
    response = client.get("/api/v1/info")
    assert response.status_code == 200
    assert response.json()["name"] == "Personal AI Assistant"


def test_memory_api():
    response = client.post(
        "/api/v1/memories",
        json={"fact": "Phase 7 test memory", "source": "test"},
    )
    assert response.status_code == 200
    assert response.json()["saved"] is True

    response = client.get("/api/v1/memories/search", params={"q": "Phase 7"})
    assert response.status_code == 200
    assert "Phase 7 test memory" in response.json()["memories"]


def test_chat_without_api_key(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    response = client.post(
        "/api/v1/chat",
        json={"message": "Hello", "session_id": "test"},
    )
    assert response.status_code == 503

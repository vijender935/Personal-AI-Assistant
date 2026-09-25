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


def _register_user():
    return auth_headers()


def test_chat_management_requires_authentication():
    assert client.get("/api/v1/chats").status_code == 401
    assert client.patch("/api/v1/chats/test", json={"title":"Renamed"}).status_code == 401
    assert client.delete("/api/v1/chats/test").status_code == 401
    assert client.post("/api/v1/chats/test/regenerate").status_code == 401
    assert client.post("/api/v1/chats/test/edit", json={"message":"new"}).status_code == 401


def test_chat_management_not_found():
    headers = _register_user()
    assert client.patch("/api/v1/chats/missing", json={"title":"Renamed"}, headers=headers).status_code == 404
    assert client.delete("/api/v1/chats/missing", headers=headers).status_code == 404
    assert client.post("/api/v1/chats/missing/regenerate", headers=headers).status_code == 400
    assert client.post("/api/v1/chats/missing/edit", json={"message":"new"}, headers=headers).status_code == 400


def test_chat_rename_delete_and_list(monkeypatch):
    headers = _register_user()
    user = api.get_user(headers["Authorization"].split(" ", 1)[1])
    assert user
    api.save_turn(f"user-{user['id']}-chat-1", "hello", "world", user_id=user["id"])

    response = client.patch(
        "/api/v1/chats/chat-1",
        json={"title":"My renamed chat"},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["title"] == "My renamed chat"

    response = client.get("/api/v1/chats", headers=headers)
    assert response.status_code == 200
    chat = next(item for item in response.json()["chats"] if item["session_id"] == "chat-1")
    assert chat["title"] == "My renamed chat"

    response = client.delete("/api/v1/chats/chat-1", headers=headers)
    assert response.status_code == 200
    assert response.json()["deleted"] is True

    response = client.get("/api/v1/chats", headers=headers)
    assert all(item["session_id"] != "chat-1" for item in response.json()["chats"])


def test_chat_management_isolated_between_users(monkeypatch):
    headers_a = _register_user()
    headers_b = _register_user()
    token_a = headers_a["Authorization"].split(" ", 1)[1]
    token_b = headers_b["Authorization"].split(" ", 1)[1]
    user_a = api.get_user(token_a)
    user_b = api.get_user(token_b)
    api.save_turn(f"user-{user_a['id']}-private", "secret A", "answer A", user_id=user_a["id"])
    api.save_turn(f"user-{user_b['id']}-private", "secret B", "answer B", user_id=user_b["id"])

    assert client.patch(
        "/api/v1/chats/private", json={"title":"A"}, headers=headers_b
    ).status_code == 404
    assert client.delete("/api/v1/chats/private", headers=headers_b).status_code == 404

    response = client.get("/api/v1/chats/private", headers=headers_b)
    assert response.status_code == 200
    assert response.json()["messages"] == []


def test_regenerate_and_edit_chat(monkeypatch):
    headers = _register_user()
    token = headers["Authorization"].split(" ", 1)[1]
    user = api.get_user(token)
    session = f"user-{user['id']}-managed"
    api.save_turn(session, "original", "old answer", user_id=user["id"])

    monkeypatch.setattr(api, "run_agent", lambda *args, **kwargs: "new answer")
    response = client.post("/api/v1/chats/managed/regenerate", headers=headers)
    assert response.status_code == 200
    assert response.json()["answer"] == "new answer"

    response = client.post(
        "/api/v1/chats/managed/edit",
        json={"message":"edited"},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["message"] == "edited"
    assert response.json()["answer"] == "new answer"

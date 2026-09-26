import mcp_client


def test_mcp_discovery_is_opt_in(monkeypatch):
    monkeypatch.delenv("MCP_SERVERS", raising=False)
    mcp_client._DISCOVERY_CACHE.update(key=None, expires_at=0.0, schemas=[])
    assert mcp_client.discover_tool_schemas() == []


def test_mcp_tool_name_validation():
    try:
        mcp_client.call_tool("calculator", {})
    except ValueError as exc:
        assert "Not an MCP tool" in str(exc)
    else:
        raise AssertionError("Expected MCP tool validation error")


def test_mcp_timeout_is_bounded(monkeypatch):
    monkeypatch.setenv("MCP_TIMEOUT_SECONDS", "999")
    assert mcp_client._timeout_seconds() == 120.0
    monkeypatch.setenv("MCP_TIMEOUT_SECONDS", "0")
    assert mcp_client._timeout_seconds() == 1.0
    monkeypatch.setenv("MCP_TIMEOUT_SECONDS", "not-a-number")
    assert mcp_client._timeout_seconds() == 30.0


def test_mcp_discovery_cache(monkeypatch):
    monkeypatch.setenv("MCP_SERVERS", '{"demo":{"transport":"streamable-http","url":"https://example/mcp"}}')
    monkeypatch.setattr(mcp_client, "_registry_key", lambda user_id=0: "demo-cache-key")
    mcp_client._DISCOVERY_CACHE.update(
        key="demo-cache-key",
        expires_at=9999999999.0,
        schemas=[{"type": "function", "function": {"name": "mcp__demo__ping"}}],
    )
    monkeypatch.setattr(mcp_client, "_discover_async", lambda user_id=0: (_ for _ in ()).throw(AssertionError("cache miss")))
    assert mcp_client.discover_tool_schemas()[0]["function"]["name"] == "mcp__demo__ping"



def test_mcp_server_and_tool_permissions(monkeypatch):
    from mcp_registry import load_server_configs, tool_allowed

    monkeypatch.setenv(
        "MCP_SERVERS",
        '{"github":{"transport":"streamable-http","url":"https://example/mcp","allowed_tools":["list_issues"]},'
        '"slack":{"transport":"streamable-http","url":"https://example/slack"}}',
    )
    monkeypatch.setenv("MCP_ALLOWED_SERVERS", "github")
    configs = load_server_configs()
    assert [item.name for item in configs] == ["github"]
    assert tool_allowed(configs[0], "list_issues")
    assert not tool_allowed(configs[0], "delete_repository")


def test_mcp_execution_rejects_disallowed_tool(monkeypatch):
    monkeypatch.setenv(
        "MCP_SERVERS",
        '{"github":{"transport":"streamable-http","url":"https://example/mcp","allowed_tools":["list_issues"]}}',
    )
    from mcp_registry import load_server_configs
    config = load_server_configs()[0]
    assert config.name == "github"
    import pytest
    with pytest.raises(PermissionError):
        import asyncio
        asyncio.run(mcp_client._call_async("github", "delete_repository", {}))


def test_mcp_connector_header_persistence(monkeypatch, tmp_path):
    import connectors
    monkeypatch.setattr(connectors, "DB_PATH", str(tmp_path / "mcp.sqlite3"))
    monkeypatch.setattr(connectors, "ensure_directories", lambda: None)
    monkeypatch.delenv("ALLOW_LOCAL_MCP", raising=False)
    connector = connectors.upsert_connector(1, "github", "streamable-http", "https://example.com/mcp", headers={"Authorization": "Bearer secret", "X-MCP-Toolsets": "repos"})
    assert connector["headers"]["Authorization"] == "Bearer secret"
    assert connector["headers"]["X-MCP-Toolsets"] == "repos"
    updated = connectors.upsert_connector(1, "github", "streamable-http", "https://example.com/mcp", headers={"Authorization": "Bearer new"})
    assert updated["headers"] == {"Authorization": "Bearer new"}


def test_mcp_connector_config_keeps_identity(monkeypatch):
    import mcp_registry
    monkeypatch.setattr(
        mcp_registry,
        "get_connector_configs",
        lambda user_id: [{
            "id": 42,
            "name": "github",
            "transport": "streamable-http",
            "url": "https://example.com/mcp",
            "headers": {},
            "allowed_tools": [],
            "enabled": True,
        }],
    )
    monkeypatch.setenv("MCP_SERVERS", "")
    config = mcp_registry.load_server_configs(7)[0]
    assert config.user_id == 7
    assert config.connector_id == 42


def test_mcp_oauth_storage_starts_empty(monkeypatch, tmp_path):
    import mcp_oauth
    monkeypatch.setattr(mcp_oauth, "DB_PATH", str(tmp_path / "oauth.sqlite3"))
    monkeypatch.setattr(mcp_oauth, "ensure_directories", lambda: None)
    monkeypatch.setattr(mcp_oauth, "using_postgres", lambda: False)
    assert not mcp_oauth.oauth_token_present(7, 42)
    assert mcp_oauth.oauth_status(7, 42)["connected"] is False

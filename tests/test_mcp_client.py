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
    mcp_client._DISCOVERY_CACHE.update(
        key='{"demo":{"transport":"streamable-http","url":"https://example/mcp"}}',
        expires_at=9999999999.0,
        schemas=[{"type": "function", "function": {"name": "mcp__demo__ping"}}],
    )
    monkeypatch.setenv("MCP_SERVERS", '{"demo":{"transport":"streamable-http","url":"https://example/mcp"}}')
    monkeypatch.setattr(mcp_client, "_discover_async", lambda: (_ for _ in ()).throw(AssertionError("cache miss")))
    assert mcp_client.discover_tool_schemas()[0]["function"]["name"] == "mcp__demo__ping"

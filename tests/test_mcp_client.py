import mcp_client

def test_mcp_discovery_is_opt_in(monkeypatch):
    monkeypatch.delenv("MCP_SERVERS", raising=False)
    assert mcp_client.discover_tool_schemas() == []

def test_mcp_tool_name_validation():
    try:
        mcp_client.call_tool("calculator", {})
    except ValueError as exc:
        assert "Not an MCP tool" in str(exc)
    else:
        raise AssertionError("Expected MCP tool validation error")

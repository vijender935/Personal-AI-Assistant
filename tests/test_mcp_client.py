import mcp_client
def test_mcp_discovery_opt_in(monkeypatch):
 monkeypatch.delenv("MCP_SERVERS",raising=False);mcp_client._DISCOVERY_CACHE.update(key=None,expires_at=0.0,schemas=[]);assert mcp_client.discover_tool_schemas()==[]
def test_tool_name_validation():
 import pytest
 with pytest.raises(ValueError):mcp_client.call_tool("calculator",{})
def test_timeout_bounded(monkeypatch):
 monkeypatch.setenv("MCP_TIMEOUT_SECONDS","999");assert mcp_client._timeout_seconds()==120.0
 monkeypatch.setenv("MCP_TIMEOUT_SECONDS","0");assert mcp_client._timeout_seconds()==1.0
def test_permissions(monkeypatch):
 monkeypatch.setenv("MCP_SERVERS",'{"github":{"transport":"streamable-http","url":"https://example/mcp","allowed_tools":["list_issues"]}}')
 from mcp_registry import load_server_configs,tool_allowed
 c=load_server_configs()[0];assert c.name=="github" and tool_allowed(c,"list_issues") and not tool_allowed(c,"delete_repository")
def test_connector_header_persistence(monkeypatch,tmp_path):
 import connectors
 monkeypatch.setattr(connectors,"DB_PATH",str(tmp_path/"mcp.sqlite3"));monkeypatch.setattr(connectors,"ensure_directories",lambda:None);monkeypatch.delenv("ALLOW_LOCAL_MCP",raising=False)
 c=connectors.upsert_connector("github","streamable-http","https://example.com/mcp",headers={"Authorization":"Bearer secret"})
 assert c["headers"]["Authorization"]=="Bearer secret"
 updated=connectors.upsert_connector("github","streamable-http","https://example.com/mcp",headers={"Authorization":"Bearer new"})
 assert updated["headers"]=={"Authorization":"Bearer new"}

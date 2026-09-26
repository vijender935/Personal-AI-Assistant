"""Secure MCP client bridge for configured connectors."""
from __future__ import annotations
import asyncio,contextlib,logging,os,re,time
from typing import Any
from mcp import Client
from mcp_registry import load_server_configs,tool_allowed
logger=logging.getLogger(__name__)
_DISCOVERY_CACHE={"key":None,"expires_at":0.0,"schemas":[]}
_LAST_DIAGNOSTICS=[]

def _safe_tool_component(value): return re.sub(r"[^A-Za-z0-9_-]+","_",str(value)).strip("_") or "tool"
def _timeout_seconds():
    try:value=float(os.getenv("MCP_TIMEOUT_SECONDS","30"))
    except ValueError:value=30.0
    return max(1.0,min(value,120.0))
def _registry_key():
    try:
        from connectors import list_connectors
        personal=list_connectors()
        personal_key=repr([(x["id"],x["name"],x["transport"],x["url"],x.get("headers",{}),x["allowed_tools"],x["enabled"]) for x in personal])
    except Exception:personal_key=""
    return f"{os.getenv('MCP_SERVERS','').strip()}|{personal_key}"

def _server_target(config):
    if config.transport=="streamable-http":
        from connectors import validate_connector_url
        if not config.url:raise ValueError(f"MCP server {config.name!r} has no URL.")
        return validate_connector_url(config.url,resolve_dns=True)
    if config.transport=="sse":
        from mcp.client.sse import sse_client
        from connectors import validate_connector_url
        if not config.url:raise ValueError(f"MCP server {config.name!r} has no URL.")
        return sse_client(validate_connector_url(config.url,resolve_dns=True),headers=getattr(config,"headers",{}) or {},timeout=_timeout_seconds(),sse_read_timeout=_timeout_seconds())
    if config.transport=="stdio":
        from mcp import StdioServerParameters
        if not config.command:raise ValueError(f"MCP server {config.name!r} has no command.")
        return StdioServerParameters(command=config.command,args=list(config.args))
    raise ValueError(f"Unsupported MCP transport: {config.transport}")

@contextlib.asynccontextmanager
async def _client_context(config):
    headers=getattr(config,"headers",{}) or {}
    if config.transport=="streamable-http":
        import httpx2
        from mcp.client.streamable_http import streamable_http_client
        timeout=_timeout_seconds(); auth=None
        try:
            from mcp_oauth import DatabaseOAuthStorage,oauth_token_present,oauth_redirect_uri
            if getattr(config,"connector_id",None) and oauth_token_present(config.connector_id):
                from mcp.client.auth import OAuthClientProvider
                from mcp.shared.auth import OAuthClientMetadata
                from pydantic import AnyUrl
                auth=OAuthClientProvider(server_url=config.url,client_metadata=OAuthClientMetadata(client_name="Personal AI Assistant",redirect_uris=[AnyUrl(oauth_redirect_uri())],application_type="web"),storage=DatabaseOAuthStorage(config.connector_id))
        except Exception as exc: logger.warning("MCP OAuth setup skipped for %s: %s",config.name,exc)
        async with httpx2.AsyncClient(headers=headers,auth=auth,timeout=httpx2.Timeout(timeout,read=max(timeout,300.0))) as http_client:
            transport=streamable_http_client(config.url,http_client=http_client)
            async with Client(transport,read_timeout_seconds=timeout) as client: yield client
        return
    async with Client(_server_target(config),read_timeout_seconds=_timeout_seconds()) as client: yield client

async def _list_all_tools(client):
    tools=[]; cursor=None
    for _ in range(100):
        result=await client.list_tools(cursor=cursor); tools.extend(result.tools or [])
        cursor=getattr(result,"nextCursor",None) or getattr(result,"next_cursor",None)
        if not cursor:break
    return tools

def _schemas_for_tools(config,tools):
    schemas=[]
    for tool in tools:
        if not tool_allowed(config,tool.name):continue
        schema=getattr(tool,"inputSchema",None) or getattr(tool,"input_schema",None) or {"type":"object","properties":{}}
        schemas.append({"type":"function","function":{"name":f"mcp__{_safe_tool_component(config.name)}__{_safe_tool_component(tool.name)}","description":getattr(tool,"description",None) or f"MCP tool {tool.name}","parameters":schema}})
    return schemas

async def _discover_async():
    discovered=[]; diagnostics=[]
    for config in load_server_configs():
        try:
            async with _client_context(config) as client:
                discovered.extend(_schemas_for_tools(config,await _list_all_tools(client)))
        except Exception as exc:
            diagnostics.append({"name":config.name,"error":str(exc)[:500]})
            logger.warning("MCP discovery failed for %s: %s",config.name,exc)
    _LAST_DIAGNOSTICS[:]=diagnostics
    return discovered

def discover_connector_diagnostics(server_name):
    config=next((x for x in load_server_configs() if x.name==server_name),None)
    if config is None:raise ValueError(f"MCP server {server_name!r} is not configured.")
    async def discover_one():
        async with _client_context(config) as client:
            schemas=_schemas_for_tools(config,await _list_all_tools(client))
            return {"connected":True,"tools":len(schemas),"tool_names":[x["function"]["name"] for x in schemas],"server":getattr(getattr(client,"server_info",None),"name",None),"protocol_version":getattr(client,"protocol_version",None)}
    try:return asyncio.run(asyncio.wait_for(discover_one(),timeout=_timeout_seconds()))
    except Exception as exc:return {"connected":False,"tools":0,"tool_names":[],"error":str(exc).strip()[:500] or exc.__class__.__name__}

def discover_connector_tool_schemas(server_name):
    diagnostic=discover_connector_diagnostics(server_name)
    if not diagnostic.get("connected"):raise RuntimeError(diagnostic.get("error") or "MCP connection failed.")
    config=next((x for x in load_server_configs() if x.name==server_name),None)
    if config is None:raise ValueError(f"MCP server {server_name!r} is not configured.")
    async def discover_one():
        async with _client_context(config) as client:return _schemas_for_tools(config,await _list_all_tools(client))
    return asyncio.run(asyncio.wait_for(discover_one(),timeout=_timeout_seconds()))

def discover_tool_schemas():
    key=_registry_key(); now=time.monotonic()
    try:ttl=float(os.getenv("MCP_DISCOVERY_TTL_SECONDS","60"))
    except ValueError:ttl=60.0
    ttl=max(1.0,min(ttl,600.0))
    if _DISCOVERY_CACHE["key"]==key and now<_DISCOVERY_CACHE["expires_at"]:return list(_DISCOVERY_CACHE["schemas"])
    schemas=asyncio.run(asyncio.wait_for(_discover_async(),timeout=_timeout_seconds()))
    _DISCOVERY_CACHE.update(key=key,expires_at=now+ttl,schemas=schemas); return list(schemas)

async def _call_async(server_name,tool_name,arguments):
    config=next((x for x in load_server_configs() if x.name==server_name),None)
    if config is None:raise ValueError(f"MCP server {server_name!r} is not configured.")
    if not tool_allowed(config,tool_name):raise PermissionError(f"MCP tool {tool_name!r} is not allowed for server {server_name!r}.")
    async with _client_context(config) as client:return await client.call_tool(tool_name,arguments)

def _content_to_text(result):
    prefix="MCP tool error" if bool(getattr(result,"is_error",getattr(result,"isError",False))) else "MCP tool result"
    parts=[]
    for item in getattr(result,"content",[]) or []:
        parts.append(getattr(item,"text",None) if getattr(item,"text",None) is not None else str(item))
    structured=getattr(result,"structured_content",None)
    if structured is None:structured=getattr(result,"structuredContent",None)
    if structured is not None:parts.append(str(structured))
    return prefix+": "+("\n".join(parts) if parts else "(empty)")

def call_tool(name,arguments):
    if not name.startswith("mcp__"):raise ValueError("Not an MCP tool.")
    parts=name.split("__",2)
    if len(parts)!=3:raise ValueError("Invalid MCP tool name.")
    server_key,tool_name=parts[1],parts[2]
    config=next((x for x in load_server_configs() if _safe_tool_component(x.name)==server_key),None)
    if config is None:raise ValueError(f"MCP server {server_key!r} is not configured.")
    result=asyncio.run(asyncio.wait_for(_call_async(config.name,tool_name,arguments),timeout=_timeout_seconds()))
    return _content_to_text(result)

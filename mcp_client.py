"""Secure MCP client bridge for configured and per-user connectors."""
from __future__ import annotations

import asyncio
import os
import time
import contextlib
from typing import Any

from mcp import Client
from mcp_registry import load_server_configs, tool_allowed

_DISCOVERY_CACHE: dict[str, Any] = {"key": None, "expires_at": 0.0, "schemas": []}


def _safe_tool_component(value: str) -> str:
    """Convert MCP names to provider-safe function-name components."""
    import re
    normalized = re.sub(r"[^A-Za-z0-9_-]+", "_", str(value)).strip("_")
    return normalized or "tool"


def _timeout_seconds() -> float:
    try:
        value = float(os.getenv("MCP_TIMEOUT_SECONDS", "30"))
    except ValueError:
        value = 30.0
    return max(1.0, min(value, 120.0))


def _registry_key(user_id: int = 0) -> str:
    try:
        from connectors import list_connectors
        personal = list_connectors(user_id)
        personal_key = repr([(x["id"], x["name"], x["transport"], x["url"], x.get("headers", {}), x["allowed_tools"], x["enabled"]) for x in personal])
    except Exception:
        personal_key = ""
    return f"{user_id}|{os.getenv('MCP_SERVERS', '').strip()}|{personal_key}"


def _server_target(config):
    if config.transport == "streamable-http":
        if not config.url:
            raise ValueError(f"MCP server {config.name!r} has no URL.")
        from connectors import validate_connector_url
        return validate_connector_url(config.url, resolve_dns=True)
    if config.transport == "sse":
        if not config.url:
            raise ValueError(f"MCP server {config.name!r} has no URL.")
        from mcp.client.sse import sse_client
        from connectors import validate_connector_url
        return sse_client(validate_connector_url(config.url, resolve_dns=True), headers=getattr(config, "headers", {}) or {}, timeout=_timeout_seconds(), sse_read_timeout=_timeout_seconds())
    if config.transport == "stdio":
        if not config.command:
            raise ValueError(f"MCP server {config.name!r} has no command.")
        from mcp import StdioServerParameters
        return StdioServerParameters(command=config.command, args=list(config.args))
    raise ValueError(f"Unsupported MCP transport: {config.transport}")


@contextlib.asynccontextmanager
async def _client_context(config):
    headers = getattr(config, "headers", {}) or {}
    if config.transport == "streamable-http" and headers:
        import httpx2
        from mcp import Client
        from mcp.client.streamable_http import streamable_http_client
        timeout = _timeout_seconds()
        async with httpx2.AsyncClient(
            headers=headers,
            timeout=httpx2.Timeout(timeout, read=max(timeout, 300.0)),
        ) as http_client:
            transport = streamable_http_client(config.url, http_client=http_client)
            async with Client(transport, read_timeout_seconds=timeout) as client:
                yield client
        return
    target = _server_target(config)
    from mcp import Client
    async with Client(target, read_timeout_seconds=_timeout_seconds()) as client:
        yield client


async def _discover_async(user_id: int = 0) -> list[dict[str, Any]]:
    discovered = []
    for config in load_server_configs(user_id):
        try:
            async with _client_context(config) as client:
                result = await client.list_tools()
                for tool in result.tools:
                    if not tool_allowed(config, tool.name):
                        continue
                    schema = getattr(tool, "inputSchema", None) or {"type": "object", "properties": {}}
                    discovered.append({
                        "type": "function",
                        "function": {
                            "name": f"mcp__{_safe_tool_component(config.name)}__{_safe_tool_component(tool.name)}",
                            "description": tool.description or f"MCP tool {tool.name}",
                            "parameters": schema,
                        },
                    })
        except Exception:
            continue
    return discovered


def discover_connector_tool_schemas(user_id: int, server_name: str) -> list[dict[str, Any]]:
    """Discover one configured connector and surface its real connection errors."""
    config = next((item for item in load_server_configs(user_id) if item.name == server_name), None)
    if config is None:
        raise ValueError(f"MCP server {server_name!r} is not configured.")
    async def discover_one():
        async with _client_context(config) as client:
            result = await client.list_tools()
            schemas=[]
            for tool in result.tools:
                if not tool_allowed(config, tool.name):
                    continue
                schema = getattr(tool, "inputSchema", None) or {"type":"object","properties":{}}
                schemas.append({
                    "type":"function",
                    "function":{
                        "name":f"mcp__{_safe_tool_component(config.name)}__{_safe_tool_component(tool.name)}",
                        "description":tool.description or f"MCP tool {tool.name}",
                        "parameters":schema,
                    },
                })
            return schemas
    return asyncio.run(asyncio.wait_for(discover_one(), timeout=_timeout_seconds()))


def discover_tool_schemas(user_id: int = 0) -> list[dict[str, Any]]:
    key = _registry_key(user_id)
    now = time.monotonic()
    try:
        ttl = float(os.getenv("MCP_DISCOVERY_TTL_SECONDS", "60"))
    except ValueError:
        ttl = 60.0
    ttl = max(1.0, min(ttl, 600.0))
    if _DISCOVERY_CACHE["key"] == key and now < _DISCOVERY_CACHE["expires_at"]:
        return list(_DISCOVERY_CACHE["schemas"])
    schemas = asyncio.run(asyncio.wait_for(_discover_async(user_id), timeout=_timeout_seconds()))
    _DISCOVERY_CACHE.update(key=key, expires_at=now + ttl, schemas=schemas)
    return list(schemas)


async def _call_async(server_name: str, tool_name: str, arguments: dict[str, Any], user_id: int = 0) -> Any:
    config = next((item for item in load_server_configs(user_id) if item.name == server_name), None)
    if config is None:
        raise ValueError(f"MCP server {server_name!r} is not configured.")
    if not tool_allowed(config, tool_name):
        raise PermissionError(f"MCP tool {tool_name!r} is not allowed for server {server_name!r}.")
    async with _client_context(config) as client:
        return await client.call_tool(tool_name, arguments)


def _content_to_text(result: Any) -> str:
    prefix = "MCP tool error" if getattr(result, "isError", False) else "MCP tool result"
    parts = []
    for item in getattr(result, "content", []) or []:
        text = getattr(item, "text", None)
        parts.append(text if text is not None else str(item))
    if getattr(result, "structuredContent", None):
        parts.append(str(result.structuredContent))
    return prefix + ": " + ("\n".join(parts) if parts else "(empty)")


def call_tool(name: str, arguments: dict[str, Any], user_id: int = 0) -> str:
    if not name.startswith("mcp__"):
        raise ValueError("Not an MCP tool.")
    parts = name.split("__", 2)
    if len(parts) != 3:
        raise ValueError("Invalid MCP tool name.")
    server_key, tool_name = parts[1], parts[2]
    configs = load_server_configs(user_id)
    config = next(
        (item for item in configs if _safe_tool_component(item.name) == server_key),
        None,
    )
    if config is None:
        raise ValueError(f"MCP server {server_key!r} is not configured.")
    result = asyncio.run(asyncio.wait_for(
        _call_async(config.name, tool_name, arguments, user_id),
        timeout=_timeout_seconds(),
    ))
    return _content_to_text(result)

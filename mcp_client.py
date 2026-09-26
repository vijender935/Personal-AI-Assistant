"""Secure MCP client bridge for configured and per-user connectors."""
from __future__ import annotations

import asyncio
import os
import time
import contextlib
import logging
from typing import Any

from mcp import Client
from mcp_registry import load_server_configs, tool_allowed

logger = logging.getLogger(__name__)

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
    if config.transport == "streamable-http":
        import httpx2
        from mcp import Client
        from mcp.client.streamable_http import streamable_http_client
        timeout = _timeout_seconds()
        auth = None
        try:
            from mcp_oauth import DatabaseOAuthStorage, oauth_token_present, oauth_redirect_uri
            if getattr(config, "connector_id", None) and oauth_token_present(config.user_id, config.connector_id):
                from mcp.client.auth import OAuthClientProvider
                from mcp.shared.auth import OAuthClientMetadata
                from pydantic import AnyUrl
                auth = OAuthClientProvider(
                    server_url=config.url,
                    client_metadata=OAuthClientMetadata(
                        client_name="Personal AI Assistant",
                        redirect_uris=[AnyUrl(oauth_redirect_uri())],
                        application_type="web",
                    ),
                    storage=DatabaseOAuthStorage(config.user_id, config.connector_id),
                )
        except Exception as exc:
            logger.warning("MCP OAuth setup skipped for %s: %s", config.name, exc)
        async with httpx2.AsyncClient(
            headers=headers,
            auth=auth,
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


async def _list_all_tools(client) -> list[Any]:
    """Read every MCP tool page instead of silently truncating at the first page."""
    tools = []
    cursor = None
    for _ in range(100):
        result = await client.list_tools(cursor=cursor)
        tools.extend(result.tools or [])
        cursor = getattr(result, "nextCursor", None) or getattr(result, "next_cursor", None)
        if not cursor:
            break
    return tools


def _schemas_for_tools(config, tools) -> list[dict[str, Any]]:
    schemas = []
    for tool in tools:
        if not tool_allowed(config, tool.name):
            continue
        schema = getattr(tool, "inputSchema", None) or getattr(tool, "input_schema", None) or {"type": "object", "properties": {}}
        schemas.append({
            "type": "function",
            "function": {
                "name": f"mcp__{_safe_tool_component(config.name)}__{_safe_tool_component(tool.name)}",
                "description": getattr(tool, "description", None) or f"MCP tool {tool.name}",
                "parameters": schema,
            },
        })
    return schemas


_LAST_DIAGNOSTICS: dict[int, list[dict[str, str]]] = {}


async def _discover_async(user_id: int = 0) -> list[dict[str, Any]]:
    discovered = []
    diagnostics = []
    for config in load_server_configs(user_id):
        try:
            async with _client_context(config) as client:
                discovered.extend(_schemas_for_tools(config, await _list_all_tools(client)))
        except Exception as exc:
            diagnostics.append({"name": config.name, "error": str(exc)[:500]})
            logger.warning("MCP discovery failed for %s: %s", config.name, exc)
    _LAST_DIAGNOSTICS[user_id] = diagnostics
    return discovered


def discover_connector_diagnostics(user_id: int, server_name: str) -> dict[str, Any]:
    """Connect to one MCP server and return a user-safe diagnostic snapshot."""
    config = next((item for item in load_server_configs(user_id) if item.name == server_name), None)
    if config is None:
        raise ValueError(f"MCP server {server_name!r} is not configured.")

    async def discover_one():
        async with _client_context(config) as client:
            schemas = _schemas_for_tools(config, await _list_all_tools(client))
            return {
                "connected": True,
                "tools": len(schemas),
                "tool_names": [item["function"]["name"] for item in schemas],
                "server": getattr(getattr(client, "server_info", None), "name", None),
                "protocol_version": getattr(client, "protocol_version", None),
            }

    try:
        result = asyncio.run(asyncio.wait_for(discover_one(), timeout=_timeout_seconds()))
        _LAST_DIAGNOSTICS[user_id] = [x for x in _LAST_DIAGNOSTICS.get(user_id, []) if x.get("name") != server_name]
        return result
    except Exception as exc:
        detail = str(exc).strip() or exc.__class__.__name__
        _LAST_DIAGNOSTICS[user_id] = [x for x in _LAST_DIAGNOSTICS.get(user_id, []) if x.get("name") != server_name] + [{"name": server_name, "error": detail[:500]}]
        return {"connected": False, "tools": 0, "tool_names": [], "error": detail[:500]}


def discover_connector_tool_schemas(user_id: int, server_name: str) -> list[dict[str, Any]]:
    diagnostic = discover_connector_diagnostics(user_id, server_name)
    if not diagnostic.get("connected"):
        raise RuntimeError(diagnostic.get("error") or "MCP connection failed.")
    config = next((item for item in load_server_configs(user_id) if item.name == server_name), None)
    if config is None:
        raise ValueError(f"MCP server {server_name!r} is not configured.")

    async def discover_one():
        async with _client_context(config) as client:
            return _schemas_for_tools(config, await _list_all_tools(client))

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
    is_error = bool(getattr(result, "is_error", getattr(result, "isError", False)))
    prefix = "MCP tool error" if is_error else "MCP tool result"
    parts = []
    for item in getattr(result, "content", []) or []:
        text = getattr(item, "text", None)
        parts.append(text if text is not None else str(item))
    structured = getattr(result, "structured_content", None)
    if structured is None:
        structured = getattr(result, "structuredContent", None)
    if structured is not None:
        parts.append(str(structured))
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

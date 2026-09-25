"""Securely configured MCP client bridge for the agent.

Only servers explicitly listed in MCP_SERVERS are contacted. External MCP
execution is opt-in and never enabled by an unconfigured environment.
"""
from __future__ import annotations

import asyncio
from typing import Any

from mcp import Client
from mcp_registry import load_server_configs


def _server_target(config):
    if config.transport in {"streamable-http", "sse"}:
        if not config.url:
            raise ValueError(f"MCP server {config.name!r} has no URL.")
        return config.url
    if config.transport == "stdio":
        if not config.command:
            raise ValueError(f"MCP server {config.name!r} has no command.")
        from mcp import StdioServerParameters
        return StdioServerParameters(command=config.command, args=list(config.args))
    raise ValueError(f"Unsupported MCP transport: {config.transport}")


async def _discover_async() -> list[dict[str, Any]]:
    discovered = []
    for config in load_server_configs():
        try:
            async with Client(_server_target(config)) as client:
                result = await client.list_tools()
                for tool in result.tools:
                    schema = getattr(tool, "inputSchema", None) or {"type": "object", "properties": {}}
                    discovered.append({
                        "type": "function",
                        "function": {
                            "name": f"mcp__{config.name}__{tool.name}",
                            "description": tool.description or f"MCP tool {tool.name}",
                            "parameters": schema,
                        },
                    })
        except Exception:
            continue
    return discovered


def discover_tool_schemas() -> list[dict[str, Any]]:
    return asyncio.run(_discover_async())


async def _call_async(server_name: str, tool_name: str, arguments: dict[str, Any]) -> Any:
    config = next((item for item in load_server_configs() if item.name == server_name), None)
    if config is None:
        raise ValueError(f"MCP server {server_name!r} is not configured.")
    async with Client(_server_target(config)) as client:
        return await client.call_tool(tool_name, arguments)


def _content_to_text(result: Any) -> str:
    if getattr(result, "isError", False):
        prefix = "MCP tool error"
    else:
        prefix = "MCP tool result"
    parts = []
    for item in getattr(result, "content", []) or []:
        text = getattr(item, "text", None)
        if text is not None:
            parts.append(text)
        else:
            parts.append(str(item))
    if getattr(result, "structuredContent", None):
        parts.append(str(result.structuredContent))
    return prefix + ": " + ("\n".join(parts) if parts else "(empty)")


def call_tool(name: str, arguments: dict[str, Any]) -> str:
    if not name.startswith("mcp__"):
        raise ValueError("Not an MCP tool.")
    parts = name.split("__", 2)
    if len(parts) != 3:
        raise ValueError("Invalid MCP tool name.")
    server_name, tool_name = parts[1], parts[2]
    return _content_to_text(asyncio.run(_call_async(server_name, tool_name, arguments)))

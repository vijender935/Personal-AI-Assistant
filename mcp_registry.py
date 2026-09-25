"""MCP ecosystem registry and client helpers.

External servers are opt-in and configured through MCP_SERVERS as JSON:
{
  "server-name": {"transport": "stdio", "command": "python", "args": ["server.py"]},
  "remote": {"transport": "streamable-http", "url": "https://example/mcp"}
}

This module only discovers configured servers; it does not execute arbitrary
commands unless the operator explicitly configures them.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class MCPServerConfig:
    name: str
    transport: str
    command: str | None = None
    args: tuple[str, ...] = ()
    url: str | None = None


def load_server_configs() -> list[MCPServerConfig]:
    raw = os.getenv("MCP_SERVERS", "").strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("MCP_SERVERS must contain valid JSON.") from exc
    if not isinstance(data, dict):
        raise ValueError("MCP_SERVERS must be a JSON object.")
    configs = []
    for name, item in data.items():
        if not isinstance(item, dict):
            continue
        transport = item.get("transport", "")
        if transport == "stdio":
            configs.append(MCPServerConfig(
                name=name,
                transport=transport,
                command=item.get("command"),
                args=tuple(item.get("args", [])),
            ))
        elif transport in {"streamable-http", "sse"}:
            configs.append(MCPServerConfig(
                name=name,
                transport=transport,
                url=item.get("url"),
            ))
    return configs


def registry_snapshot() -> list[dict[str, object]]:
    return [
        {
            "name": item.name,
            "transport": item.transport,
            "command": item.command,
            "args": list(item.args),
            "url": item.url,
        }
        for item in load_server_configs()
    ]

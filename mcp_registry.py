"""MCP registry with explicit server/tool permission boundaries."""
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
    allowed_tools: tuple[str, ...] = ()


def _allowed_servers() -> set[str] | None:
    raw = os.getenv("MCP_ALLOWED_SERVERS", "").strip()
    if not raw:
        return None
    return {item.strip() for item in raw.split(",") if item.strip()}


def _env_server_configs() -> list[MCPServerConfig]:
    raw = os.getenv("MCP_SERVERS", "").strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("MCP_SERVERS must contain valid JSON.") from exc
    if not isinstance(data, dict):
        raise ValueError("MCP_SERVERS must be a JSON object.")

    allowed_servers = _allowed_servers()
    configs = []
    for name, item in data.items():
        if allowed_servers is not None and name not in allowed_servers:
            continue
        if not isinstance(item, dict):
            continue
        transport = item.get("transport", "")
        allowed_tools = item.get("allowed_tools", [])
        if not isinstance(allowed_tools, list) or not all(isinstance(x, str) for x in allowed_tools):
            allowed_tools = []
        common = dict(
            name=name,
            transport=transport,
            allowed_tools=tuple(x.strip() for x in allowed_tools if x.strip()),
        )
        if transport == "stdio":
            configs.append(MCPServerConfig(
                **common,
                command=item.get("command"),
                args=tuple(item.get("args", [])),
            ))
        elif transport in {"streamable-http", "sse"}:
            configs.append(MCPServerConfig(**common, url=item.get("url")))
    return configs


def load_server_configs(user_id: int | None = None) -> list[MCPServerConfig]:
    configs = _env_server_configs()
    if user_id is None:
        return configs

    try:
        from connectors import get_connector_configs
        existing = {item.name for item in configs}
        for item in get_connector_configs(user_id):
            if item["name"] in existing:
                continue
            configs.append(
                MCPServerConfig(
                    name=item["name"],
                    transport=item["transport"],
                    url=item["url"],
                    allowed_tools=tuple(item["allowed_tools"]),
                )
            )
    except Exception:
        # Connector storage must never break the normal agent startup.
        pass
    return configs


def tool_allowed(config: MCPServerConfig, tool_name: str) -> bool:
    return not config.allowed_tools or tool_name in config.allowed_tools


def registry_snapshot(user_id: int | None = None) -> list[dict[str, object]]:
    return [
        {
            "name": item.name,
            "transport": item.transport,
            "command": item.command,
            "args": list(item.args),
            "url": item.url,
            "allowed_tools": list(item.allowed_tools),
        }
        for item in load_server_configs(user_id)
    ]

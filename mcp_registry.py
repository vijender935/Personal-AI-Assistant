"""MCP server registry for the single-user assistant."""
from __future__ import annotations
import json,os
from dataclasses import dataclass
from connectors import validate_connector_url
@dataclass(frozen=True)
class MCPServerConfig:
    name:str
    transport:str
    connector_id:int|None=None
    command:str|None=None
    args:tuple[str,...]=()
    url:str|None=None
    headers:dict[str,str]|None=None
    allowed_tools:tuple[str,...]=()
def _allowed_servers():
    raw=os.getenv("MCP_ALLOWED_SERVERS","").strip()
    return {x.strip() for x in raw.split(",") if x.strip()} if raw else None
def _env_server_configs():
    raw=os.getenv("MCP_SERVERS","").strip()
    if not raw:return []
    try:data=json.loads(raw)
    except json.JSONDecodeError as exc:raise ValueError("MCP_SERVERS must contain valid JSON.") from exc
    if not isinstance(data,dict):raise ValueError("MCP_SERVERS must be a JSON object.")
    allowed=_allowed_servers(); configs=[]
    for name,item in data.items():
        if allowed is not None and name not in allowed or not isinstance(item,dict):continue
        transport=item.get("transport",""); tools=item.get("allowed_tools",[]); headers=item.get("headers",{})
        if not isinstance(tools,list) or not all(isinstance(x,str) for x in tools):tools=[]
        if not isinstance(headers,dict) or not all(isinstance(k,str) and isinstance(v,str) for k,v in headers.items()):headers={}
        common={"name":name,"transport":transport,"allowed_tools":tuple(x.strip() for x in tools if x.strip()),"headers":{k.strip():v.strip() for k,v in headers.items() if k.strip()}}
        if transport=="stdio":configs.append(MCPServerConfig(**common,command=item.get("command"),args=tuple(item.get("args",[]))))
        elif transport in {"streamable-http","sse"}:
            url=item.get("url")
            if not isinstance(url,str):continue
            try:url=validate_connector_url(url,resolve_dns=False)
            except ValueError:continue
            configs.append(MCPServerConfig(**common,url=url))
    return configs
def load_server_configs():
    configs=_env_server_configs()
    try:
        existing={x.name for x in configs}
        from connectors import get_connector_configs
        for item in get_connector_configs():
            if item["name"] in existing:continue
            configs.append(MCPServerConfig(name=item["name"],transport=item["transport"],connector_id=item["id"],url=item["url"],headers=item.get("headers",{}) or {},allowed_tools=tuple(item["allowed_tools"])))
    except Exception:pass
    return configs
def tool_allowed(config,tool_name):return not config.allowed_tools or tool_name in config.allowed_tools
def registry_snapshot():
    return [{"name":x.name,"transport":x.transport,"command":x.command,"args":list(x.args),"url":x.url,"headers":{k:"***" for k in (x.headers or {})},"allowed_tools":list(x.allowed_tools)} for x in load_server_configs()]

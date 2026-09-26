"""MCP connector storage for the single-user Personal AI Assistant."""
from __future__ import annotations
import ipaddress, json, os, socket
from urllib.parse import urlparse
from config import ensure_directories
from db import connect

def _is_private_or_local(host: str, resolve_dns: bool = True) -> bool:
    host = host.strip("[]").lower()
    if host in {"localhost", "localhost.localdomain"}:
        return True
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_multicast or ip.is_unspecified or ip.is_reserved
    except ValueError:
        if not resolve_dns:
            return False
        try:
            infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise ValueError("Connector host could not be resolved.") from exc
        for info in infos:
            try:
                ip = ipaddress.ip_address(info[4][0])
            except ValueError:
                continue
            if ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_multicast or ip.is_unspecified or ip.is_reserved:
                return True
        return False

def validate_connector_url(url: str, *, resolve_dns: bool = True) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"https", "http"} or not parsed.hostname:
        raise ValueError("Connector URL must be a valid http(s) URL.")
    if parsed.username or parsed.password:
        raise ValueError("Connector URL must not contain embedded credentials.")
    if parsed.scheme == "http" and os.getenv("ALLOW_LOCAL_MCP", "0") != "1":
        raise ValueError("HTTP MCP connectors are disabled; use HTTPS.")
    if _is_private_or_local(parsed.hostname, resolve_dns=resolve_dns) and os.getenv("ALLOW_LOCAL_MCP", "0") != "1":
        raise ValueError("Connector host resolves to a private or local address.")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Connector URL contains an invalid port.") from exc
    if port is not None and not 1 <= port <= 65535:
        raise ValueError("Connector port is invalid.")
    return parsed.geturl()

def init_connectors_db():
    ensure_directories()
    with connect() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS mcp_connectors(
            id BIGSERIAL PRIMARY KEY,name TEXT NOT NULL UNIQUE,transport TEXT NOT NULL,url TEXT NOT NULL,
            allowed_tools TEXT NOT NULL DEFAULT '[]',enabled BOOLEAN NOT NULL DEFAULT TRUE,
            headers TEXT NOT NULL DEFAULT '{}',created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")

def _migrate_legacy_schema():
    """Remove legacy user-scoping from an existing PostgreSQL database."""
    with connect() as con:
        try:
            con.execute("DROP INDEX IF EXISTS mcp_connectors_user_id_name_key")
            con.execute("ALTER TABLE mcp_connectors DROP COLUMN IF EXISTS user_id")
        except Exception:
            pass

def list_connectors(*, redact_headers=False):
    init_connectors_db(); _migrate_legacy_schema()
    with connect() as con:
        rows=con.execute("SELECT id,name,transport,url,headers,allowed_tools,enabled,created_at FROM mcp_connectors ORDER BY name").fetchall()
    result=[]
    for connector_id,name,transport,url,headers,allowed_tools,enabled,created_at in rows:
        try: tools=json.loads(allowed_tools)
        except (json.JSONDecodeError,TypeError): tools=[]
        try: header_map=json.loads(headers)
        except (json.JSONDecodeError,TypeError): header_map={}
        if not isinstance(header_map,dict): header_map={}
        result.append({"id":connector_id,"name":name,"transport":transport,"url":url,
                       "headers":({k:"***" for k in header_map} if redact_headers else header_map),
                       "allowed_tools":tools if isinstance(tools,list) else [],"enabled":bool(enabled),"created_at":created_at})
    return result

def get_connector_configs():
    return [x for x in list_connectors(redact_headers=False) if x["enabled"]]

def upsert_connector(name,transport,url,allowed_tools=None,headers=None):
    name,transport,url=name.strip(),transport.strip().lower(),url.strip()
    if not name or len(name)>80: raise ValueError("Connector name must be 1-80 characters.")
    if transport not in {"streamable-http","sse"}: raise ValueError("Transport must be streamable-http or sse.")
    url=validate_connector_url(url)
    tools=[x.strip() for x in (allowed_tools or []) if isinstance(x,str) and x.strip()]
    if len(tools)>100: raise ValueError("Too many allowed tools.")
    header_map={}
    if isinstance(headers,dict):
        for key,value in headers.items():
            key,value=str(key).strip(),str(value).strip()
            if not key or len(key)>128 or any(c in key+value for c in "\r\n"):
                raise ValueError("Invalid MCP header.")
            if key.lower() in {"host","content-length","transfer-encoding","connection"}:
                raise ValueError(f"MCP header {key!r} is not allowed.")
            header_map[key]=value
    if len(header_map)>30: raise ValueError("Too many MCP headers.")
    init_connectors_db(); _migrate_legacy_schema()
    with connect() as con:
        if using_postgres():
            con.execute("""INSERT INTO mcp_connectors(name,transport,url,headers,allowed_tools,enabled)
                VALUES(?,?,?,?,?,TRUE) ON CONFLICT(name) DO UPDATE SET transport=excluded.transport,url=excluded.url,headers=excluded.headers,allowed_tools=excluded.allowed_tools,enabled=TRUE""",
                (name,transport,url,json.dumps(header_map),json.dumps(tools)))
        else:
            con.execute("""INSERT INTO mcp_connectors(name,transport,url,headers,allowed_tools,enabled)
                VALUES(?,?,?,?,?,1) ON CONFLICT(name) DO UPDATE SET transport=excluded.transport,url=excluded.url,headers=excluded.headers,allowed_tools=excluded.allowed_tools,enabled=1""",
                (name,transport,url,json.dumps(header_map),json.dumps(tools)))
    return next(x for x in list_connectors() if x["name"]==name)

def delete_connector(connector_id):
    init_connectors_db(); _migrate_legacy_schema()
    with connect() as con:
        cur=con.execute("DELETE FROM mcp_connectors WHERE id=?",(connector_id,))
    return cur.rowcount>0

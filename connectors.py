"""Per-user MCP connector storage with SSRF-safe URL validation."""
from __future__ import annotations

import ipaddress
import json
import os
import socket
from urllib.parse import urlparse

from config import DB_PATH, ensure_directories
from db import connect, using_postgres


def _is_private_or_local(host: str, resolve_dns: bool = True) -> bool:
    host = host.strip("[]").lower()
    if host in {"localhost", "localhost.localdomain"}:
        return True
    try:
        ip = ipaddress.ip_address(host)
        return (
            ip.is_loopback
            or ip.is_private
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_unspecified
            or ip.is_reserved
        )
    except ValueError:
        if not resolve_dns:
            return False
        try:
            infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise ValueError("Connector host could not be resolved.") from exc
        for info in infos:
            address = info[4][0]
            try:
                ip = ipaddress.ip_address(address)
            except ValueError:
                continue
            if (
                ip.is_loopback
                or ip.is_private
                or ip.is_link_local
                or ip.is_multicast
                or ip.is_unspecified
                or ip.is_reserved
            ):
                return True
        return False


def validate_connector_url(url: str, *, resolve_dns: bool = True) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"https", "http"} or not parsed.hostname:
        raise ValueError("Connector URL must be a valid http(s) URL.")
    if parsed.username or parsed.password:
        raise ValueError("Connector URL must not contain embedded credentials.")
    if parsed.scheme == "http" and not os.getenv("ALLOW_LOCAL_MCP", "0") == "1":
        raise ValueError("HTTP MCP connectors are disabled; use HTTPS.")
    if _is_private_or_local(parsed.hostname, resolve_dns=resolve_dns) and os.getenv("ALLOW_LOCAL_MCP", "0") != "1":
        raise ValueError("Connector host resolves to a private or local address.")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Connector URL contains an invalid port.") from exc
    if port is not None and not (1 <= port <= 65535):
        raise ValueError("Connector port is invalid.")
    return parsed.geturl()


def init_connectors_db():
    ensure_directories()
    with connect(DB_PATH) as con:
        con.execute("""CREATE TABLE IF NOT EXISTS mcp_connectors(
            id BIGSERIAL PRIMARY KEY,user_id BIGINT NOT NULL,name TEXT NOT NULL,transport TEXT NOT NULL,url TEXT NOT NULL,
            allowed_tools TEXT NOT NULL DEFAULT '[]',enabled BOOLEAN NOT NULL DEFAULT TRUE,created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id,name))""" if using_postgres() else """CREATE TABLE IF NOT EXISTS mcp_connectors(
            id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,name TEXT NOT NULL,transport TEXT NOT NULL,url TEXT NOT NULL,
            allowed_tools TEXT NOT NULL DEFAULT '[]',enabled INTEGER NOT NULL DEFAULT 1,created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id,name))""")
        _ensure_column(con, "mcp_connectors", "headers", "TEXT NOT NULL DEFAULT '{}'")
        con.execute("CREATE INDEX IF NOT EXISTS idx_mcp_connectors_user ON mcp_connectors(user_id)")


def _ensure_column(con, table, column, definition):
    if using_postgres():
        exists = con.execute("SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name=? AND column_name=?", (table, column)).fetchone()
        if not exists:
            con.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
    else:
        cols = {row[1] for row in con.execute(f"PRAGMA table_info({table})")}
        if column not in cols:
            con.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def list_connectors(user_id, *, redact_headers=False):
    init_connectors_db()
    with connect(DB_PATH) as con:
        rows=con.execute("SELECT id,name,transport,url,headers,allowed_tools,enabled,created_at FROM mcp_connectors WHERE user_id=? ORDER BY name",(user_id,)).fetchall()
    result=[]
    for connector_id,name,transport,url,headers,allowed_tools,enabled,created_at in rows:
        try: tools=json.loads(allowed_tools)
        except (json.JSONDecodeError, TypeError): tools=[]
        try: header_map=json.loads(headers)
        except (json.JSONDecodeError, TypeError): header_map={}
        if not isinstance(header_map, dict): header_map={}
        result.append({"id":connector_id,"name":name,"transport":transport,"url":url,"headers":({key: "***" for key in header_map} if redact_headers else header_map),"allowed_tools":tools if isinstance(tools,list) else [],"enabled":bool(enabled),"created_at":created_at})
    return result


def get_connector_configs(user_id):
    return [item for item in list_connectors(user_id, redact_headers=False) if item["enabled"]]


def upsert_connector(user_id,name,transport,url,allowed_tools=None,headers=None):
    name,transport,url=name.strip(),transport.strip().lower(),url.strip()
    if not name or len(name)>80: raise ValueError("Connector name must be 1-80 characters.")
    if transport not in {"streamable-http","sse"}: raise ValueError("Transport must be streamable-http or sse.")
    url = validate_connector_url(url)
    tools=[x.strip() for x in (allowed_tools or []) if isinstance(x,str) and x.strip()]
    if len(tools)>100: raise ValueError("Too many allowed tools.")
    header_map={}
    if isinstance(headers, dict):
        for key,value in headers.items():
            key=str(key).strip()
            value=str(value).strip()
            if not key or len(key)>128 or "\r" in key or "\n" in key or "\r" in value or "\n" in value:
                raise ValueError("Invalid MCP header.")
            if key.lower() in {"host","content-length","transfer-encoding","connection"}:
                raise ValueError(f"MCP header {key!r} is not allowed.")
            header_map[key]=value
    if len(header_map)>30: raise ValueError("Too many MCP headers.")
    init_connectors_db()
    with connect(DB_PATH) as con:
        con.execute("""INSERT INTO mcp_connectors(user_id,name,transport,url,headers,allowed_tools,enabled)
            VALUES(?,?,?,?,?,?,?) ON CONFLICT(user_id,name) DO UPDATE SET transport=excluded.transport,url=excluded.url,headers=excluded.headers,allowed_tools=excluded.allowed_tools,enabled=excluded.enabled""",
            (user_id,name,transport,url,json.dumps(header_map),json.dumps(tools),True if using_postgres() else 1))
    return next(item for item in list_connectors(user_id) if item["name"]==name)


def delete_connector(user_id,connector_id):
    init_connectors_db()
    with connect(DB_PATH) as con:
        cur=con.execute("DELETE FROM mcp_connectors WHERE id=? AND user_id=?",(connector_id,user_id))
    return cur.rowcount>0

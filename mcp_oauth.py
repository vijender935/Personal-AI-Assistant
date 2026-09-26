"""Persistent OAuth bridge for remote MCP connectors.

The MCP SDK owns discovery, PKCE, state validation, token exchange and refresh.
This module only supplies persistent TokenStorage and an HTTP callback bridge.
"""
from __future__ import annotations

import asyncio
import json
import os
import secrets
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlparse

from config import DB_PATH, ensure_directories
from db import connect, using_postgres
from mcp.client.auth import AuthorizationCodeResult, OAuthClientProvider
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.auth import OAuthClientInformationFull, OAuthClientMetadata, OAuthToken
from pydantic import AnyUrl


def init_oauth_db() -> None:
    ensure_directories()
    with connect(DB_PATH) as con:
        con.execute(
            """CREATE TABLE IF NOT EXISTS mcp_oauth_credentials(
                connector_id BIGINT PRIMARY KEY,
                user_id BIGINT NOT NULL,
                tokens TEXT,
                client_info TEXT,
                updated_at DOUBLE PRECISION NOT NULL
            )"""
            if using_postgres()
            else
            """CREATE TABLE IF NOT EXISTS mcp_oauth_credentials(
                connector_id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                tokens TEXT,
                client_info TEXT,
                updated_at REAL NOT NULL
            )"""
        )
        con.execute("CREATE INDEX IF NOT EXISTS idx_mcp_oauth_user ON mcp_oauth_credentials(user_id)")


class DatabaseOAuthStorage:
    def __init__(self, user_id: int, connector_id: int):
        self.user_id = user_id
        self.connector_id = connector_id
        init_oauth_db()

    def _read(self) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        with connect(DB_PATH) as con:
            row = con.execute(
                "SELECT tokens,client_info FROM mcp_oauth_credentials WHERE connector_id=? AND user_id=?",
                (self.connector_id, self.user_id),
            ).fetchone()
        if not row:
            return None, None
        try:
            tokens = json.loads(row[0]) if row[0] else None
        except (TypeError, json.JSONDecodeError):
            tokens = None
        try:
            client_info = json.loads(row[1]) if row[1] else None
        except (TypeError, json.JSONDecodeError):
            client_info = None
        return tokens, client_info

    def _write(self, tokens: dict[str, Any] | None, client_info: dict[str, Any] | None) -> None:
        with connect(DB_PATH) as con:
            con.execute(
                """INSERT INTO mcp_oauth_credentials(connector_id,user_id,tokens,client_info,updated_at)
                   VALUES(?,?,?,?,?)
                   ON CONFLICT(connector_id) DO UPDATE SET
                     user_id=excluded.user_id,tokens=excluded.tokens,
                     client_info=excluded.client_info,updated_at=excluded.updated_at""",
                (self.connector_id, self.user_id, json.dumps(tokens) if tokens else None,
                 json.dumps(client_info) if client_info else None, time.time()),
            )

    async def get_tokens(self) -> OAuthToken | None:
        tokens, _ = self._read()
        return OAuthToken.model_validate(tokens) if tokens else None

    async def set_tokens(self, tokens: OAuthToken) -> None:
        _, client_info = self._read()
        self._write(tokens.model_dump(mode="json"), client_info)

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        _, client_info = self._read()
        return OAuthClientInformationFull.model_validate(client_info) if client_info else None

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        tokens, _ = self._read()
        self._write(tokens, client_info.model_dump(mode="json"))


@dataclass
class _OAuthFlow:
    user_id: int
    connector_id: int
    ready: asyncio.Future
    callback: asyncio.Future
    auth_url: str | None = None
    task: asyncio.Task | None = None
    created_at: float = 0.0


_FLOWS: dict[str, _OAuthFlow] = {}
_FLOW_TTL = 10 * 60


def _cleanup_flows() -> None:
    now = time.time()
    for flow_id, flow in list(_FLOWS.items()):
        if now - flow.created_at > _FLOW_TTL:
            if not flow.ready.done():
                flow.ready.cancel()
            if not flow.callback.done():
                flow.callback.cancel()
            if flow.task and not flow.task.done():
                flow.task.cancel()
            _FLOWS.pop(flow_id, None)


def _connector(user_id: int, connector_id: int) -> dict[str, Any]:
    from connectors import list_connectors
    connector = next((x for x in list_connectors(user_id) if x["id"] == connector_id), None)
    if not connector:
        raise ValueError("Connector not found.")
    if connector["transport"] != "streamable-http":
        raise ValueError("OAuth currently requires a Streamable HTTP connector.")
    return connector


async def _run_flow(flow_id: str, flow: _OAuthFlow, redirect_uri: str) -> None:
    connector = _connector(flow.user_id, flow.connector_id)
    storage = DatabaseOAuthStorage(flow.user_id, flow.connector_id)

    async def redirect_handler(authorization_url: str) -> None:
        flow.auth_url = authorization_url
        if not flow.ready.done():
            flow.ready.set_result(authorization_url)

    async def callback_handler() -> AuthorizationCodeResult:
        return await flow.callback

    provider = OAuthClientProvider(
        server_url=connector["url"],
        client_metadata=OAuthClientMetadata(
            client_name="Personal AI Assistant",
            redirect_uris=[AnyUrl(redirect_uri)],
            application_type="web",
        ),
        storage=storage,
        redirect_handler=redirect_handler,
        callback_handler=callback_handler,
    )

    try:
        import httpx2
        async with httpx2.AsyncClient(auth=provider) as http_client:
            transport = streamable_http_client(connector["url"], http_client=http_client)
            from mcp import Client
            async with Client(transport) as client:
                await client.list_tools()
        if not flow.ready.done():
            flow.ready.set_result(flow.auth_url or "")
    except Exception as exc:
        if not flow.ready.done():
            flow.ready.set_exception(exc)
        if not flow.callback.done():
            flow.callback.cancel()
        raise


async def begin_oauth(user_id: int, connector_id: int, redirect_uri: str) -> dict[str, str]:
    _cleanup_flows()
    _connector(user_id, connector_id)
    flow_id = secrets.token_urlsafe(32)
    loop = asyncio.get_running_loop()
    flow = _OAuthFlow(
        user_id=user_id,
        connector_id=connector_id,
        ready=loop.create_future(),
        callback=loop.create_future(),
        created_at=time.time(),
    )
    _FLOWS[flow_id] = flow
    flow.task = asyncio.create_task(_run_flow(flow_id, flow, redirect_uri))
    try:
        auth_url = await asyncio.wait_for(asyncio.shield(flow.ready), timeout=15)
    except Exception:
        _FLOWS.pop(flow_id, None)
        if flow.task and not flow.task.done():
            flow.task.cancel()
        raise
    return {"flow_id": flow_id, "authorization_url": auth_url}


async def complete_oauth(
    flow_id: str,
    code: str,
    state: str | None = None,
    iss: str | None = None,
) -> dict[str, Any]:
    _cleanup_flows()
    flow = _FLOWS.get(flow_id)
    if not flow:
        raise ValueError("OAuth flow expired or was not found.")
    if flow.callback.done():
        raise ValueError("OAuth callback was already submitted.")
    flow.callback.set_result(AuthorizationCodeResult(code=code, state=state, iss=iss))
    try:
        await asyncio.wait_for(asyncio.shield(flow.task), timeout=120)
    except asyncio.TimeoutError as exc:
        raise RuntimeError("OAuth token exchange timed out.") from exc
    finally:
        _FLOWS.pop(flow_id, None)
    return {"connected": True, "connector_id": flow.connector_id}


def oauth_token_present(user_id: int, connector_id: int) -> bool:\n    _connector(user_id, connector_id)\n    init_oauth_db()\n    with connect(DB_PATH) as con:\n        row = con.execute(\n            "SELECT tokens FROM mcp_oauth_credentials WHERE connector_id=? AND user_id=?",\n            (connector_id, user_id),\n        ).fetchone()\n    if not row or not row[0]:\n        return False\n    try:\n        token = json.loads(row[0])\n        return bool(isinstance(token, dict) and token.get("access_token"))\n    except (TypeError, json.JSONDecodeError):\n        return False\n\n\ndef oauth_status(user_id: int, connector_id: int) -> dict[str, Any]:
    _connector(user_id, connector_id)
    storage = DatabaseOAuthStorage(user_id, connector_id)
    async def read():
        return await storage.get_tokens()
    try:
        token = asyncio.run(read())
    except RuntimeError:
        token = None
    return {"connected": bool(token and token.access_token)}


def clear_oauth(user_id: int, connector_id: int) -> bool:
    _connector(user_id, connector_id)
    init_oauth_db()
    with connect(DB_PATH) as con:
        cur = con.execute(
            "DELETE FROM mcp_oauth_credentials WHERE connector_id=? AND user_id=?",
            (connector_id, user_id),
        )
    return cur.rowcount > 0

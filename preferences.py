"""Persistent per-user application preferences."""
from __future__ import annotations

import json

from config import DB_PATH, ensure_directories
from db import connect, using_postgres

DEFAULTS = {
    "appearance": "System",
    "haptics": True,
    "language": "English",
    "web_search": True,
    "memory": True,
    "custom_instructions": "",
    "response_style": "Natural",
}

def init_preferences_db():
    ensure_directories()
    with connect(DB_PATH) as con:
        if using_postgres():
            con.execute(
                """CREATE TABLE IF NOT EXISTS user_preferences(
                    user_id BIGINT PRIMARY KEY,
                    preferences TEXT NOT NULL DEFAULT '{}'
                )"""
            )
        else:
            con.execute(
                """CREATE TABLE IF NOT EXISTS user_preferences(
                    user_id INTEGER PRIMARY KEY,
                    preferences TEXT NOT NULL DEFAULT '{}'
                )"""
            )

def _clean(data):
    result = dict(DEFAULTS)
    if isinstance(data, dict):
        for key in DEFAULTS:
            if key in data:
                result[key] = data[key]
    result["appearance"] = result["appearance"] if result["appearance"] in {"System", "Light", "Dark"} else "System"
    result["language"] = result["language"] if result["language"] in {"English", "Hindi"} else "English"
    result["response_style"] = result["response_style"] if result["response_style"] in {"Natural", "Concise", "Detailed"} else "Natural"
    result["haptics"] = bool(result["haptics"])
    result["web_search"] = bool(result["web_search"])
    result["memory"] = bool(result["memory"])
    result["custom_instructions"] = str(result["custom_instructions"] or "")[:4000]
    return result

def get_preferences(user_id: int):
    init_preferences_db()
    with connect(DB_PATH) as con:
        row = con.execute("SELECT preferences FROM user_preferences WHERE user_id=?", (user_id,)).fetchone()
    if not row:
        return dict(DEFAULTS)
    try:
        raw = json.loads(row[0])
    except (TypeError, json.JSONDecodeError):
        raw = {}
    return _clean(raw)

def update_preferences(user_id: int, updates: dict):
    current = get_preferences(user_id)
    current.update({k: v for k, v in updates.items() if k in DEFAULTS})
    cleaned = _clean(current)
    init_preferences_db()
    with connect(DB_PATH) as con:
        if using_postgres():
            con.execute(
                """INSERT INTO user_preferences(user_id, preferences) VALUES(?,?)
                   ON CONFLICT(user_id) DO UPDATE SET preferences=excluded.preferences""",
                (user_id, json.dumps(cleaned, ensure_ascii=False)),
            )
        else:
            con.execute(
                """INSERT INTO user_preferences(user_id, preferences) VALUES(?,?)
                   ON CONFLICT(user_id) DO UPDATE SET preferences=excluded.preferences""",
                (user_id, json.dumps(cleaned, ensure_ascii=False)),
            )
    return cleaned

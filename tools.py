"""
Local tools + persistent SQLite memory for the Personal AI Agent.

Security:
- Shell execution is OFF by default.
- Set ALLOW_SHELL=1 only when you explicitly trust the environment.
- Destructive shell commands are blocked by a basic denylist.
"""

import ast
import os
import re
import sqlite3
import subprocess
from pathlib import Path

DB_PATH = Path(os.getenv("AGENT_DB", "agent_memory.db"))
MAX_FILE_CHARS = int(os.getenv("MAX_FILE_CHARS", "10000"))

BLOCKED_SHELL_PATTERNS = [
    r"\brm\s+-rf\s+/",
    r"\bmkfs\b",
    r"\bdd\s+if=",
    r"\bshutdown\b",
    r"\breboot\b",
    r"\bpoweroff\b",
    r"\bchmod\s+777\b",
]


def init_db():
    with sqlite3.connect(DB_PATH) as con:
        con.execute(
            """CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        con.execute(
            """CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fact TEXT NOT NULL UNIQUE,
                source TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )"""
        )


def save_turn(session_id: str, user_text: str, assistant_text: str):
    with sqlite3.connect(DB_PATH) as con:
        con.execute(
            "INSERT INTO messages(session_id, role, content) VALUES (?, ?, ?)",
            (session_id, "user", user_text),
        )
        con.execute(
            "INSERT INTO messages(session_id, role, content) VALUES (?, ?, ?)",
            (session_id, "assistant", assistant_text),
        )


def load_history(session_id: str, limit: int = 30):
    with sqlite3.connect(DB_PATH) as con:
        rows = con.execute(
            """SELECT role, content FROM messages
               WHERE session_id = ?
               ORDER BY id DESC LIMIT ?""",
            (session_id, limit),
        ).fetchall()
    return [{"role": role, "content": content} for role, content in reversed(rows)]


def remember_fact(fact: str, source: str = "user"):
    fact = fact.strip()
    if not fact:
        return
    with sqlite3.connect(DB_PATH) as con:
        con.execute(
            "INSERT OR IGNORE INTO memories(fact, source) VALUES (?, ?)",
            (fact, source),
        )


def recall_memories(query: str, limit: int = 8):
    with sqlite3.connect(DB_PATH) as con:
        rows = con.execute(
            "SELECT fact FROM memories ORDER BY id DESC LIMIT ?",
            (max(limit, 50),),
        ).fetchall()

    facts = [r[0] for r in rows]
    if not query:
        return facts[:limit]

    terms = {x.lower() for x in re.findall(r"\w+", query) if len(x) > 2}
    scored = []
    for fact in facts:
        score = sum(term in fact.lower() for term in terms)
        if score:
            scored.append((score, fact))
    scored.sort(reverse=True)
    return [fact for _, fact in scored[:limit]] or facts[:limit]


def calculator(expression: str) -> str:
    """Safely evaluate basic arithmetic; no Python eval."""
    try:
        tree = ast.parse(expression, mode="eval")
        allowed = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant,
                   ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv,
                   ast.Mod, ast.Pow, ast.USub, ast.UAdd, ast.Load)
        if not all(isinstance(node, allowed) for node in ast.walk(tree)):
            return "Error: unsupported expression"
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and (
                not isinstance(node.value, (int, float)) or isinstance(node.value, bool)
            ):
                return "Error: numbers only"
        return str(eval(compile(tree, "<calculator>", "eval"),
                        {"__builtins__": {}}, {}))
    except Exception as exc:
        return f"Error: {exc}"


def web_search(query: str) -> str:
    """DuckDuckGo search; no API key required."""
    try:
        from ddgs import DDGS
        results = list(DDGS().text(query, max_results=5))
        if not results:
            return "No results found."
        return "\n\n".join(
            f"{r.get('title', '')}: {r.get('body', '')}\n{r.get('href', '')}"
            for r in results
        )
    except ImportError:
        return "Error: install the 'ddgs' package first."
    except Exception as exc:
        return f"Error: {exc}"


def _safe_path(path: str) -> Path:
    p = Path(path).expanduser().resolve()
    return p


def read_file(path: str) -> str:
    try:
        p = _safe_path(path)
        if not p.is_file():
            return "Error: file not found"
        return p.read_text(encoding="utf-8", errors="replace")[:MAX_FILE_CHARS]
    except Exception as exc:
        return f"Error: {exc}"


def write_file(path: str, content: str) -> str:
    try:
        p = _safe_path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"Written {len(content)} chars to {p}"
    except Exception as exc:
        return f"Error: {exc}"


def run_shell(command: str) -> str:
    if os.getenv("ALLOW_SHELL", "0") != "1":
        return "Shell tool disabled. Set ALLOW_SHELL=1 explicitly to enable it."

    for pattern in BLOCKED_SHELL_PATTERNS:
        if re.search(pattern, command, flags=re.IGNORECASE):
            return "Blocked: potentially destructive shell command."

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        output = (result.stdout[-3000:] + result.stderr[-1000:]).strip()
        return output or "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: shell command timed out after 30 seconds."
    except Exception as exc:
        return f"Error: {exc}"


TOOL_FUNCTIONS = {
    "calculator": calculator,
    "web_search": web_search,
    "read_file": read_file,
    "write_file": write_file,
    "run_shell": run_shell,
}

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "calculator",
            "description": "Evaluate a basic arithmetic expression.",
            "parameters": {
                "type": "object",
                "properties": {"expression": {"type": "string"}},
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web for current information.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a local text file.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write text to a local file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_shell",
            "description": "Run a local shell command only when explicitly enabled.",
            "parameters": {
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            },
        },
    },
]

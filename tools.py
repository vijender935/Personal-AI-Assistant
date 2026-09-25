"""Local tools and persistent SQLite memory with Phase 6 security defaults."""
from __future__ import annotations
import ast, operator, re, shlex, sqlite3, subprocess
from pathlib import Path
from typing import Any
from config import ALLOW_SHELL, ALLOWED_SHELL_COMMANDS, DB_PATH, FILE_ROOT, MAX_FILE_CHARS, SHELL_TIMEOUT, ensure_directories

MAX_SHELL_OUTPUT = 4000
MAX_MEMORY_SCAN = 500

def init_db() -> None:
    ensure_directories()
    with sqlite3.connect(DB_PATH) as con:
        con.execute("""CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL,
            role TEXT NOT NULL, content TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP)""")
        con.execute("""CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT, fact TEXT NOT NULL UNIQUE,
            source TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)""")
        con.execute("CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id)")

def save_turn(session_id: str, user_text: str, assistant_text: str) -> None:
    with sqlite3.connect(DB_PATH) as con:
        con.execute("INSERT INTO messages(session_id, role, content) VALUES (?, ?, ?)",
                    (session_id, "user", user_text))
        con.execute("INSERT INTO messages(session_id, role, content) VALUES (?, ?, ?)",
                    (session_id, "assistant", assistant_text))

def load_history(session_id: str, limit: int = 30) -> list[dict[str, str]]:
    limit = max(1, int(limit))
    with sqlite3.connect(DB_PATH) as con:
        rows = con.execute("""SELECT role, content FROM messages
            WHERE session_id = ? ORDER BY id DESC LIMIT ?""", (session_id, limit)).fetchall()
    return [{"role": r, "content": c} for r, c in reversed(rows)]

def remember_fact(fact: str, source: str = "user") -> None:
    fact = fact.strip()
    if not fact: return
    with sqlite3.connect(DB_PATH) as con:
        con.execute("INSERT OR IGNORE INTO memories(fact, source) VALUES (?, ?)", (fact, source))

def recall_memories(query: str, limit: int = 8) -> list[str]:
    limit = max(1, int(limit))
    with sqlite3.connect(DB_PATH) as con:
        rows = con.execute("SELECT fact FROM memories ORDER BY id DESC LIMIT ?", (MAX_MEMORY_SCAN,)).fetchall()
    facts = [r[0] for r in rows]
    if not query: return facts[:limit]
    terms = {x.lower() for x in re.findall(r"\w+", query) if len(x) > 2}
    scored = [(sum(t in fact.lower() for t in terms), fact) for fact in facts]
    scored = [x for x in scored if x[0]]
    scored.sort(key=lambda x: (-x[0], x[1].lower()))
    return [fact for _, fact in scored[:limit]] or facts[:limit]


def semantic_recall_memories(query: str, limit: int = 8) -> list[str]:
    try:
        from memory import search_semantic_memories
        return search_semantic_memories(query, limit=limit) or recall_memories(query, limit=limit)
    except Exception:
        return recall_memories(query, limit=limit)

_BINARY: dict[type[ast.operator], Any] = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod, ast.Pow: operator.pow,
}
_UNARY: dict[type[ast.unaryop], Any] = {ast.UAdd: operator.pos, ast.USub: operator.neg}

def _evaluate_math(node: ast.AST) -> int | float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY:
        left, right = _evaluate_math(node.left), _evaluate_math(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > 1000: raise ValueError("exponent is too large")
        return _BINARY[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        return _UNARY[type(node.op)](_evaluate_math(node.operand))
    raise ValueError("unsupported expression")

def calculator(expression: str) -> str:
    try: return str(_evaluate_math(ast.parse(expression, mode="eval").body))
    except (SyntaxError, ValueError, TypeError, ZeroDivisionError, OverflowError) as exc: return f"Error: {exc}"

def web_search(query: str) -> str:
    try:
        from ddgs import DDGS
        results = list(DDGS().text(query, max_results=5))
        if not results: return "No results found."
        return "\n\n".join(f"{r.get('title','')}: {r.get('body','')}\n{r.get('href','')}" for r in results)
    except ImportError: return "Error: install the 'ddgs' package first."
    except Exception as exc: return f"Error: {exc}"

def _safe_path(path: str) -> Path:
    ensure_directories()
    candidate = (FILE_ROOT / path).resolve() if not Path(path).is_absolute() else Path(path).expanduser().resolve()
    try: candidate.relative_to(FILE_ROOT.resolve())
    except ValueError as exc: raise PermissionError(f"path is outside the allowed file root: {FILE_ROOT}") from exc
    return candidate

def read_file(path: str) -> str:
    try:
        p = _safe_path(path)
        if not p.is_file(): return "Error: file not found"
        return p.read_text(encoding="utf-8", errors="replace")[:MAX_FILE_CHARS]
    except Exception as exc: return f"Error: {exc}"

def write_file(path: str, content: str) -> str:
    try:
        p = _safe_path(path); p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"Written {len(content)} chars to {p.relative_to(FILE_ROOT)}"
    except Exception as exc: return f"Error: {exc}"

def run_shell(command: str) -> str:
    if not ALLOW_SHELL: return "Shell tool disabled. Set ALLOW_SHELL=1 explicitly to enable it."
    try: parts = shlex.split(command)
    except ValueError as exc: return f"Error: invalid shell syntax: {exc}"
    if not parts: return "Error: empty command"
    executable = Path(parts[0]).name
    if executable not in ALLOWED_SHELL_COMMANDS:
        return f"Blocked: command '{executable}' is not allowlisted."
    try:
        result = subprocess.run(parts, cwd=FILE_ROOT, capture_output=True, text=True, timeout=SHELL_TIMEOUT, shell=False)
        output = (result.stdout + result.stderr).strip() or "(no output)"
        return f"exit_code={result.returncode}\n{output[-MAX_SHELL_OUTPUT:]}"
    except subprocess.TimeoutExpired: return f"Error: shell command timed out after {SHELL_TIMEOUT} seconds."
    except Exception as exc: return f"Error: {exc}"

TOOL_FUNCTIONS = {"calculator": calculator, "web_search": web_search, "read_file": read_file, "write_file": write_file, "run_shell": run_shell}
TOOL_SCHEMAS = [
 {"type":"function","function":{"name":"calculator","description":"Evaluate a basic arithmetic expression.","parameters":{"type":"object","properties":{"expression":{"type":"string"}},"required":["expression"]}}},
 {"type":"function","function":{"name":"web_search","description":"Search the web for current information.","parameters":{"type":"object","properties":{"query":{"type":"string"}},"required":["query"]}}},
 {"type":"function","function":{"name":"read_file","description":"Read a local UTF-8 text file inside the allowed file root.","parameters":{"type":"object","properties":{"path":{"type":"string"}},"required":["path"]}}},
 {"type":"function","function":{"name":"write_file","description":"Write a local UTF-8 text file inside the allowed file root.","parameters":{"type":"object","properties":{"path":{"type":"string"},"content":{"type":"string"}},"required":["path","content"]}}},
 {"type":"function","function":{"name":"run_shell","description":"Run an allowlisted local command only when shell access is explicitly enabled.","parameters":{"type":"object","properties":{"command":{"type":"string"}},"required":["command"]}}},
]

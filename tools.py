"""Local tools and persistent single-user chat/memory storage."""
from __future__ import annotations
import ast, operator, re, shlex, subprocess, sqlite3
from pathlib import Path
from config import ALLOW_SHELL, ALLOWED_SHELL_COMMANDS, DB_PATH, FILE_ROOT, MAX_FILE_CHARS, SHELL_TIMEOUT, ensure_directories
from db import connect, using_postgres
MAX_SHELL_OUTPUT=4000
MAX_MEMORY_SCAN=500

def init_db():
    ensure_directories()
    with connect(DB_PATH) as con:
        if using_postgres():
            con.execute("""CREATE TABLE IF NOT EXISTS messages(id BIGSERIAL PRIMARY KEY,session_id TEXT NOT NULL,role TEXT NOT NULL,content TEXT NOT NULL,created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
            con.execute("""CREATE TABLE IF NOT EXISTS memories(id BIGSERIAL PRIMARY KEY,fact TEXT NOT NULL UNIQUE,source TEXT,created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        else:
            con.execute("""CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY AUTOINCREMENT,session_id TEXT NOT NULL,role TEXT NOT NULL,content TEXT NOT NULL,created_at DATETIME DEFAULT CURRENT_TIMESTAMP)""")
            con.execute("""CREATE TABLE IF NOT EXISTS memories(id INTEGER PRIMARY KEY AUTOINCREMENT,fact TEXT NOT NULL UNIQUE,source TEXT,created_at DATETIME DEFAULT CURRENT_TIMESTAMP)""")
        con.execute("CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id)")
        con.execute("""CREATE TABLE IF NOT EXISTS chat_metadata(session_id TEXT PRIMARY KEY,title TEXT NOT NULL)""")

def save_turn(session_id,user_text,assistant_text):
    with connect(DB_PATH) as con:
        con.execute("INSERT INTO messages(session_id,role,content) VALUES(?,?,?)",(session_id,"user",user_text))
        con.execute("INSERT INTO messages(session_id,role,content) VALUES(?,?,?)",(session_id,"assistant",assistant_text))

def load_history(session_id,limit=30):
    limit=max(1,int(limit))
    with connect(DB_PATH) as con:
        rows=con.execute("SELECT role,content FROM messages WHERE session_id=? ORDER BY id DESC LIMIT ?",(session_id,limit)).fetchall()
    history=[]
    for role,content in reversed(rows):
        if history and history[-1]["role"]==role and history[-1]["content"]==content: continue
        history.append({"role":role,"content":content})
    return history

def list_sessions(limit=50):
    limit=max(1,min(int(limit),1000))
    with connect(DB_PATH) as con:
        rows=con.execute("SELECT session_id,MAX(id) AS last_id FROM messages GROUP BY session_id ORDER BY last_id DESC LIMIT ?",(limit,)).fetchall()
    return [x[0] for x in rows]

def remember_fact(fact,source="user"):
    fact=fact.strip()
    if not fact:return
    with connect(DB_PATH) as con:
        if using_postgres():
            con.execute("INSERT INTO memories(fact,source) VALUES(?,?) ON CONFLICT(fact) DO UPDATE SET source=excluded.source",(fact,source))
        else:
            try: con.execute("INSERT INTO memories(fact,source) VALUES(?,?)",(fact,source))
            except sqlite3.IntegrityError: con.execute("UPDATE memories SET source=? WHERE fact=?",(source,fact))

def recall_memories(query="",limit=8):
    limit=max(1,int(limit))
    with connect(DB_PATH) as con: rows=con.execute("SELECT fact FROM memories ORDER BY id DESC LIMIT ?",(MAX_MEMORY_SCAN,)).fetchall()
    facts=[r[0] for r in rows]
    if not query:return facts[:limit]
    terms={x.lower() for x in re.findall(r"\w+",query) if len(x)>2}
    scored=[(sum(t in fact.lower() for t in terms),fact) for fact in facts]
    scored=[x for x in scored if x[0]]; scored.sort(key=lambda x:(-x[0],x[1].lower()))
    return [fact for _,fact in scored[:limit]] or facts[:limit]

def semantic_recall_memories(query,limit=8):
    try:
        from memory import search_semantic_memories
        return search_semantic_memories(query,limit=limit) or recall_memories(query,limit=limit)
    except Exception:
        return recall_memories(query,limit=limit)

_BINARY={ast.Add:operator.add,ast.Sub:operator.sub,ast.Mult:operator.mul,ast.Div:operator.truediv,ast.FloorDiv:operator.floordiv,ast.Mod:operator.mod,ast.Pow:operator.pow}
_UNARY={ast.UAdd:operator.pos,ast.USub:operator.neg}
def _evaluate_math(node):
    if isinstance(node,ast.Constant) and isinstance(node.value,(int,float)) and not isinstance(node.value,bool):return node.value
    if isinstance(node,ast.BinOp) and type(node.op) in _BINARY:
        left,right=_evaluate_math(node.left),_evaluate_math(node.right)
        if isinstance(node.op,ast.Pow) and abs(right)>1000:raise ValueError("exponent is too large")
        return _BINARY[type(node.op)](left,right)
    if isinstance(node,ast.UnaryOp) and type(node.op) in _UNARY:return _UNARY[type(node.op)](_evaluate_math(node.operand))
    raise ValueError("unsupported expression")
def calculator(expression):
    try:return str(_evaluate_math(ast.parse(expression,mode="eval").body))
    except (SyntaxError,ValueError,TypeError,ZeroDivisionError,OverflowError) as exc:return f"Error: {exc}"
def web_search(query):
    try:
        from ddgs import DDGS
        results=list(DDGS().text(query,max_results=5))
        if not results:return "No results found."
        return "\n\n".join(f"{r.get('title','')}: {r.get('body','')}\n{r.get('href','')}" for r in results)
    except ImportError:return "Error: install the 'ddgs' package first."
    except Exception as exc:return f"Error: {exc}"
def _safe_path(path):
    root=FILE_ROOT.resolve(); root.mkdir(parents=True,exist_ok=True)
    candidate=(root/Path(path)).resolve() if not Path(path).is_absolute() else Path(path).expanduser().resolve()
    try:candidate.relative_to(root)
    except ValueError as exc:raise PermissionError("path is outside the allowed file root") from exc
    return candidate
def read_file(path):
    try:
        p=_safe_path(path)
        if not p.is_file():return "Error: file not found"
        return p.read_text(encoding="utf-8",errors="replace")[:MAX_FILE_CHARS]
    except Exception as exc:return f"Error: {exc}"
def write_file(path,content):
    try:
        p=_safe_path(path);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(content,encoding="utf-8")
        return f"Written {len(content)} chars to {p.relative_to(FILE_ROOT.resolve())}"
    except Exception as exc:return f"Error: {exc}"
def run_shell(command):
    if not ALLOW_SHELL:return "Shell tool disabled. Set ALLOW_SHELL=1 explicitly to enable it."
    try:parts=shlex.split(command)
    except ValueError as exc:return f"Error: invalid shell syntax: {exc}"
    if not parts:return "Error: empty command"
    executable=Path(parts[0]).name
    if executable not in ALLOWED_SHELL_COMMANDS:return f"Blocked: command '{executable}' is not allowlisted."
    try:
        result=subprocess.run(parts,cwd=FILE_ROOT,capture_output=True,text=True,timeout=SHELL_TIMEOUT,shell=False)
        output=(result.stdout+result.stderr).strip() or "(no output)"
        return f"exit_code={result.returncode}\n{output[-MAX_SHELL_OUTPUT:]}"
    except subprocess.TimeoutExpired:return f"Error: shell command timed out after {SHELL_TIMEOUT} seconds."
    except Exception as exc:return f"Error: {exc}"

TOOL_FUNCTIONS={"calculator":calculator,"web_search":web_search,"read_file":read_file,"write_file":write_file,"run_shell":run_shell}
TOOL_SCHEMAS=[
 {"type":"function","function":{"name":"calculator","description":"Evaluate a basic arithmetic expression.","parameters":{"type":"object","properties":{"expression":{"type":"string"}},"required":["expression"]}}},
 {"type":"function","function":{"name":"web_search","description":"Search the web for current information.","parameters":{"type":"object","properties":{"query":{"type":"string"}},"required":["query"]}}},
 {"type":"function","function":{"name":"read_file","description":"Read a local UTF-8 text file inside the allowed file root.","parameters":{"type":"object","properties":{"path":{"type":"string"}},"required":["path"]}}},
 {"type":"function","function":{"name":"write_file","description":"Write a local UTF-8 text file inside the allowed file root.","parameters":{"type":"object","function":{"name":"write_file","description":"Write a local UTF-8 text file inside the allowed file root.","parameters":{"type":"object","properties":{"path":{"type":"string"},"content":{"type":"string"}},"required":["path","content"]}}}}},
 {"type":"function","function":{"name":"run_shell","description":"Run an allowlisted local command only when shell access is explicitly enabled.","parameters":{"type":"object","properties":{"command":{"type":"string"}},"required":["command"]}}}
]
def set_chat_title(session_id,title):
    title=title.strip()[:80]
    if not title: raise ValueError("Chat title cannot be empty.")
    with connect(DB_PATH) as con:
        con.execute("INSERT INTO chat_metadata(session_id,title) VALUES(?,?) ON CONFLICT(session_id) DO UPDATE SET title=excluded.title",(session_id,title))
def get_chat_title(session_id):
    with connect(DB_PATH) as con: row=con.execute("SELECT title FROM chat_metadata WHERE session_id=?",(session_id,)).fetchone()
    return row[0] if row else None
def delete_chat(session_id):
    with connect(DB_PATH) as con:
        con.execute("DELETE FROM messages WHERE session_id=?",(session_id,)); con.execute("DELETE FROM chat_metadata WHERE session_id=?",(session_id,))
def remove_last_assistant(session_id):
    with connect(DB_PATH) as con:
        row=con.execute("SELECT id FROM messages WHERE session_id=? AND role='assistant' ORDER BY id DESC LIMIT 1",(session_id,)).fetchone()
        if not row:return False
        con.execute("DELETE FROM messages WHERE id=?",(row[0],)); return True
def remove_last_turn(session_id):
    with connect(DB_PATH) as con:
        rows=con.execute("SELECT id FROM messages WHERE session_id=? ORDER BY id DESC LIMIT 2",(session_id,)).fetchall()
        if len(rows)<2:return False
        con.executemany("DELETE FROM messages WHERE id=? ",[(row[0],) for row in rows]); return True

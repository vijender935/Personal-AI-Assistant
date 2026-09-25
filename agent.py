"""Personal AI Agent — conversational + persistent memory + local tools."""
from __future__ import annotations
import json, logging, os, sys, time
from typing import Optional
from groq import Groq
from config import MAX_HISTORY_MESSAGES, MAX_ITERATIONS, MAX_RETRIES, MODEL
from tools import TOOL_FUNCTIONS, TOOL_SCHEMAS, init_db, load_history, semantic_recall_memories, remember_fact, save_turn

logger = logging.getLogger(__name__)
logging.basicConfig(level=os.getenv("LOG_LEVEL","INFO").upper(), format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
SYSTEM_PROMPT = """Tum ek helpful personal AI assistant ho.
User se natural Hinglish me baat karo.
Context ko yaad rakho aur previous conversation ko use karo.
Jab current information, calculation, file operation ya shell task ki zaroorat ho, appropriate tool use karo.
Tool results ko clearly explain karo. Kabhi bhi tool result invent mat karo.
Dangerous/destructive local actions se bacho.
"""

def _extract_memory_candidate(text: str) -> Optional[str]:
    lower = text.lower().strip()
    prefixes = ("remember that ","yaad rakhna ","yaad rakho ","note that ","remember: ","yaad rakho:")
    for prefix in prefixes:
        if lower.startswith(prefix): return text.strip()[len(prefix):].strip()
    return None

def build_messages(goal: str, session_id: str) -> list[dict]:
    history = load_history(session_id, MAX_HISTORY_MESSAGES)
    memories = semantic_recall_memories(goal, limit=8)
    messages = [{"role":"system","content":SYSTEM_PROMPT}]
    if memories:
        messages.append({"role":"system","content":"Relevant saved memories (semantic retrieval):\n" + "\n".join(f"- {m}" for m in memories)})
    try:
        from memory import search_rag
        rag_results = search_rag(goal, limit=4)
    except Exception:
        rag_results = []
    if rag_results:
        context = "\n\n".join(
            f"[{item['source']} | score={item['score']}]\n{item['content']}"
            for item in rag_results
        )
        messages.append({"role":"system","content":"Relevant knowledge-base context:\n" + context})
    messages.extend(history)
    messages.append({"role":"user","content":goal})
    return messages

def run_agent(goal: str, session_id: str = "default", verbose: bool = True) -> str:
    goal = goal.strip()
    if not goal: return "Please enter a message."
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key: return "❌ GROQ_API_KEY set nahi hai. README.md dekho setup ke liye."
    explicit_memory = _extract_memory_candidate(goal)
    if explicit_memory:
        remember_fact(explicit_memory, source="user-explicit")
        try:
            from memory import remember_semantic
            remember_semantic(explicit_memory, source="user-explicit")
        except Exception as exc:
            logger.warning("Semantic memory unavailable: %s", exc)
    client, messages = Groq(api_key=api_key), build_messages(goal, session_id)

    for _ in range(MAX_ITERATIONS):
        response = None
        for retry in range(MAX_RETRIES + 1):
            try:
                response = client.chat.completions.create(model=MODEL, messages=messages, tools=TOOL_SCHEMAS, tool_choice="auto", temperature=0.4)
                break
            except Exception as exc:
                logger.warning("Model request failed (retry %s): %s", retry, exc)
                if retry < MAX_RETRIES: time.sleep(2 ** retry)
        if response is None: return "❌ Model/API request failed after retries. Logs me details available hain."
        msg = response.choices[0].message
        messages.append(msg.model_dump(exclude_none=True))
        if not msg.tool_calls:
            answer = msg.content or ""; save_turn(session_id, goal, answer); return answer
        for call in msg.tool_calls:
            name = call.function.name
            try: args = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError: args = {}
            if verbose: logger.info("Tool call: %s(%s)", name, args)
            fn = TOOL_FUNCTIONS.get(name)
            try: result = fn(**args) if fn else f"Unknown tool: {name}"
            except Exception as exc:
                logger.exception("Tool failed: %s", name); result = f"Tool error in {name}: {exc}"
            messages.append({"role":"tool","tool_call_id":call.id,"name":name,"content":str(result)})
    return f"⚠️ Max tool iterations ({MAX_ITERATIONS}) reached — task incomplete reh gaya."

def interactive() -> None:
    session_id = os.getenv("AGENT_SESSION","default")
    print(f"Personal AI Agent — model: {MODEL}"); print("Commands: /new, /remember <fact>, /memories, /exit\n")
    while True:
        try: goal = input("Tum: ").strip()
        except (EOFError, KeyboardInterrupt): print(); break
        if not goal: continue
        command = goal.lower()
        if command in {"/exit","/quit","exit","quit"}: break
        if command == "/new": session_id=f"session-{time.time_ns()}"; print(f"🆕 New session: {session_id}\n"); continue
        if command == "/memories":
            memories=recall_memories("",limit=50); print("\n".join(f"- {m}" for m in memories) or "(no memories)"); print(); continue
        if command.startswith("/remember "):
            remember_fact(goal[len("/remember "):].strip(), source="user-command"); print("🧠 Memory saved.\n"); continue
        print("\nAgent:", run_agent(goal, session_id=session_id), "\n")

if __name__ == "__main__":
    init_db()
    print(run_agent(" ".join(sys.argv[1:]))) if len(sys.argv)>1 else interactive()

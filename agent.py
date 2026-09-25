"""
Personal AI Agent — conversational + persistent memory + local tools.

Run:
    python agent.py
    python agent.py "Delhi ka weather kya hai?"
"""

import json
import os
import sys
import time
from typing import Optional

from groq import Groq
from tools import (
    TOOL_FUNCTIONS,
    TOOL_SCHEMAS,
    init_db,
    load_history,
    save_turn,
    remember_fact,
    recall_memories,
)

MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
MAX_ITERATIONS = int(os.getenv("MAX_ITERATIONS", "8"))
MAX_HISTORY_MESSAGES = int(os.getenv("MAX_HISTORY_MESSAGES", "30"))

SYSTEM_PROMPT = """Tum ek helpful personal AI assistant ho.
User se natural Hinglish me baat karo.
Context ko yaad rakho aur previous conversation ko use karo.
Jab current information, calculation, file operation ya shell task ki zaroorat ho,
appropriate tool use karo. Tool ki zaroorat na ho to directly jawab do.
Tool results ko clearly explain karo. Kabhi bhi tool ka result invent mat karo.
Dangerous/destructive local actions se bacho.
"""


def _extract_memory_candidate(text: str) -> Optional[str]:
    """Lightweight explicit-memory detector; user can also use /remember."""
    lower = text.lower().strip()
    prefixes = (
        "remember that ",
        "yaad rakhna ",
        "yaad rakho ",
        "note that ",
        "remember: ",
        "yaad rakho:",
    )
    for prefix in prefixes:
        if lower.startswith(prefix):
            return text.strip()[len(prefix):].strip()
    return None


def build_messages(goal: str, session_id: str):
    history = load_history(session_id, MAX_HISTORY_MESSAGES)
    memories = recall_memories(goal, limit=8)

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if memories:
        memory_text = "\n".join(f"- {m}" for m in memories)
        messages.append(
            {
                "role": "system",
                "content": f"Relevant saved memories:\n{memory_text}",
            }
        )
    messages.extend(history)
    messages.append({"role": "user", "content": goal})
    return messages


def run_agent(goal: str, session_id: str = "default", verbose: bool = True) -> str:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return "❌ GROQ_API_KEY set nahi hai. README.md dekho setup ke liye."

    client = Groq(api_key=api_key)
    messages = build_messages(goal, session_id)

    explicit_memory = _extract_memory_candidate(goal)
    if explicit_memory:
        remember_fact(explicit_memory, source="user-explicit")

    for attempt in range(MAX_ITERATIONS):
        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                tools=TOOL_SCHEMAS,
                tool_choice="auto",
                temperature=0.4,
            )
        except Exception as exc:
            if attempt < 2:
                time.sleep(2 ** attempt)
                continue
            return f"❌ Model/API error: {exc}"

        msg = response.choices[0].message
        assistant_payload = msg.model_dump(exclude_none=True)
        messages.append(assistant_payload)

        if not msg.tool_calls:
            answer = msg.content or ""
            save_turn(session_id, goal, answer)
            return answer

        for call in msg.tool_calls:
            name = call.function.name
            try:
                args = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}

            if verbose:
                print(f"🔧 {name}({args})")

            fn = TOOL_FUNCTIONS.get(name)
            if not fn:
                result = f"Unknown tool: {name}"
            else:
                try:
                    result = fn(**args)
                except Exception as exc:
                    result = f"Tool error in {name}: {exc}"

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "name": name,
                    "content": str(result),
                }
            )

    return "⚠️ Max iterations reached — task incomplete reh gaya."


def interactive():
    session_id = os.getenv("AGENT_SESSION", "default")
    print(f"Personal AI Agent — model: {MODEL}")
    print("Commands: /new, /remember <fact>, /memories, /exit\n")

    while True:
        try:
            goal = input("Tum: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not goal:
            continue

        command = goal.lower()
        if command in {"/exit", "/quit", "exit", "quit"}:
            break

        if command == "/new":
            session_id = f"session-{int(time.time())}"
            print(f"🆕 New session: {session_id}\n")
            continue

        if command == "/memories":
            memories = recall_memories("", limit=50)
            print("\n".join(f"- {m}" for m in memories) or "(no memories)")
            print()
            continue

        if command.startswith("/remember "):
            fact = goal[len("/remember "):].strip()
            remember_fact(fact, source="user-command")
            print("🧠 Memory saved.\n")
            continue

        print("\nAgent:", run_agent(goal, session_id=session_id), "\n")


if __name__ == "__main__":
    init_db()
    if len(sys.argv) > 1:
        print(run_agent(" ".join(sys.argv[1:])))
    else:
        interactive()

"""Personal AI Agent — conversational + persistent memory + local tools."""
from __future__ import annotations
import json, logging, os, sys, time
from groq import Groq
from config import MAX_HISTORY_MESSAGES, MAX_ITERATIONS, MAX_RETRIES, MODEL, VISION_MODEL
from orchestration import (
    ExecutionState, build_execution_plan, plan_prompt, plan_task,
    recovery_instruction, select_mcp_tools, should_continue_execution,
    validate_tool_result,
)
from tools import TOOL_FUNCTIONS, TOOL_SCHEMAS, init_db, load_history, semantic_recall_memories, remember_fact, save_turn

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

SYSTEM_PROMPT = """Tum ek helpful personal AI assistant ho.
User se natural Hinglish me baat karo.
Context ko yaad rakho aur previous conversation ko use karo.
Jab current information, calculation, file operation ya shell task ki zaroorat ho, appropriate tool use karo.
Tool results ko clearly explain karo. Kabhi bhi tool result invent mat karo.
Dangerous/destructive local actions se bacho."""

def _extract_memory_candidate(text):
    lower = text.lower().strip()
    prefixes = ("remember that ", "yaad rakhna ", "yaad rakho ", "note that ", "remember: ", "yaad rakho:")
    for prefix in prefixes:
        if lower.startswith(prefix):
            return text.strip()[len(prefix):].strip()
    return None

def build_messages(goal, session_id, user_id=0, rag_sources=None):
    history = load_history(session_id, MAX_HISTORY_MESSAGES, user_id=user_id)
    memories = semantic_recall_memories(goal, limit=8, user_id=user_id)
    plan = plan_task(goal)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "system", "content": plan_prompt(plan)}]
    if memories:
        messages.append({
            "role": "system",
            "content": "Relevant saved memories (semantic retrieval):\n" + "\n".join(f"- {m}" for m in memories),
        })
    try:
        from memory import search_rag
        rag_results = search_rag(goal, limit=4, user_id=user_id, sources=rag_sources)
    except Exception:
        rag_results = []
    if rag_results:
        context = "\n\n".join(
            f"[{item['source']} | score={item['score']}]\n{item['content']}" for item in rag_results
        )
        messages.append({"role": "system", "content": "Relevant knowledge-base context:\n" + context})
    messages.extend(history)
    messages.append({"role": "user", "content": goal})
    return messages

def _tool_schemas_for(user_id, goal):
    """Return only tools appropriate for the classified request.

    Simple conversational messages intentionally receive no tool schemas. This
    prevents the model from inventing tool calls for greetings/chitchat and
    avoids entering the tool loop when no external action is needed.
    """
    plan = plan_task(goal)
    if plan.complexity == "simple":
        return []

    schemas = []
    if plan.needs_web:
        schemas.extend(
            schema for schema in TOOL_SCHEMAS
            if schema.get("function", {}).get("name") == "web_search"
        )
    if plan.needs_local_tools:
        local_names = {"calculator", "read_file", "write_file", "run_shell"}
        schemas.extend(
            schema for schema in TOOL_SCHEMAS
            if schema.get("function", {}).get("name") in local_names
        )

    if plan.needs_mcp:
        try:
            from mcp_client import discover_tool_schemas
            schemas.extend(select_mcp_tools(discover_tool_schemas(user_id), goal, max_tools=12))
        except Exception as exc:
            logger.warning("MCP discovery unavailable: %s", exc)

    unique = {}
    for schema in schemas:
        name = schema.get("function", {}).get("name")
        if name:
            unique[name] = schema
    return list(unique.values())

def _execute_tool(name, args, user_id):
    try:
        fn = TOOL_FUNCTIONS.get(name)
        if fn:
            return fn(**args, user_id=user_id)
        if name.startswith("mcp__"):
            from mcp_client import call_tool
            return call_tool(name, args, user_id=user_id)
        return f"Unknown tool: {name}"
    except Exception as exc:
        logger.exception("Tool failed: %s", name)
        return f"Tool error in {name}: {exc}"

def _prepare_goal(goal, user_id):
    explicit_memory = _extract_memory_candidate(goal)
    if explicit_memory:
        remember_fact(explicit_memory, source="user-explicit", user_id=user_id)
        try:
            from memory import remember_semantic
            remember_semantic(explicit_memory, source="user-explicit", user_id=user_id)
        except Exception as exc:
            logger.warning("Semantic memory unavailable: %s", exc)

def run_agent(goal, session_id="default", user_id=0, image_urls=None, rag_sources=None, verbose=True):
    goal = goal.strip()
    if not goal:
        return "Please enter a message."
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return "❌ GROQ_API_KEY set nahi hai. README.md dekho setup ke liye."

    _prepare_goal(goal, user_id)
    task_plan = plan_task(goal)
    execution_plan = build_execution_plan(task_plan)
    client = Groq(api_key=api_key)
    messages = build_messages(goal, session_id, user_id=user_id, rag_sources=rag_sources)
    tool_schemas = _tool_schemas_for(user_id, goal)

    if image_urls:
        messages[-1]["content"] = [{"type": "text", "text": goal}] + [
            {"type": "image_url", "image_url": {"url": url}} for url in image_urls
        ]

    state = ExecutionState()
    prepared_final_response = False
    while should_continue_execution(state, min(MAX_ITERATIONS, execution_plan.max_tool_rounds)):
        state.round_number += 1
        response = None
        for retry in range(MAX_RETRIES + 1):
            try:
                response = client.chat.completions.create(
                    model=VISION_MODEL if image_urls else MODEL,
                    messages=messages,
                    **({"tools": tool_schemas, "tool_choice": "auto"} if tool_schemas else {}),
                    temperature=0.4,
                )
                break
            except Exception as exc:
                logger.warning("Model request failed (retry %s): %s", retry, exc)
                if retry < MAX_RETRIES:
                    time.sleep(2 ** retry)
        if response is None:
            return "❌ Model/API request failed after retries. Logs me details available hain."

        msg = response.choices[0].message
        messages.append(msg.model_dump(exclude_none=True))
        if not msg.tool_calls:
            answer = msg.content or ""
            save_turn(session_id, goal, answer, user_id=user_id)
            return answer

        for call in msg.tool_calls:
            name = call.function.name
            state.tool_calls += 1
            state.last_tool = name
            try:
                args = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            if verbose:
                logger.info("Tool call: %s(%s)", name, args)

            result = _execute_tool(name, args, user_id)
            validated = validate_tool_result(result)
            messages.append({
                "role": "tool",
                "tool_call_id": call.id,
                "name": name,
                "content": validated.content,
            })
            if validated.ok:
                state.consecutive_failures = 0
            else:
                state.consecutive_failures += 1
                messages.append({
                    "role": "system",
                    "content": recovery_instruction(name, validated),
                })

    if state.consecutive_failures >= 2:
        return "⚠️ Tool execution repeatedly failed. Maine unsafe/infinite retry se bachne ke liye execution stop kar diya."
    return f"⚠️ Max tool iterations ({MAX_ITERATIONS}) reached — task incomplete reh gaya."

def stream_agent(goal, session_id="default", user_id=0, image_urls=None, rag_sources=None):
    """Execute tools first when required, then stream the final assistant response.

    This keeps the frontend streaming endpoint compatible with calculator/web/file/MCP
    tools instead of silently disabling tool calls.
    """
    goal = goal.strip()
    if not goal:
        yield "Please enter a message."
        return
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        yield "❌ GROQ_API_KEY set nahi hai."
        return

    _prepare_goal(goal, user_id)
    task_plan = plan_task(goal)
    execution_plan = build_execution_plan(task_plan)
    client = Groq(api_key=api_key)
    messages = build_messages(goal, session_id, user_id=user_id, rag_sources=rag_sources)
    tool_schemas = _tool_schemas_for(user_id, goal)

    if image_urls:
        messages[-1]["content"] = [{"type": "text", "text": goal}] + [
            {"type": "image_url", "image_url": {"url": url}} for url in image_urls
        ]

    state = ExecutionState()
    while should_continue_execution(state, min(MAX_ITERATIONS, execution_plan.max_tool_rounds)):
        state.round_number += 1
        response = None
        for retry in range(MAX_RETRIES + 1):
            try:
                request_kwargs = {
                    "model": VISION_MODEL if image_urls else MODEL,
                    "messages": messages,
                    "temperature": 0.4,
                }
                if tool_schemas:
                    request_kwargs.update({"tools": tool_schemas, "tool_choice": "auto"})
                response = client.chat.completions.create(**request_kwargs)
                break
            except Exception as exc:
                logger.warning("Streaming preparation request failed (retry %s): %s", retry, exc)
                if retry < MAX_RETRIES:
                    time.sleep(2 ** retry)
        if response is None:
            yield "❌ Model/API request failed after retries."
            return

        msg = response.choices[0].message
        messages.append(msg.model_dump(exclude_none=True))
        if not msg.tool_calls:
            prepared_final_response = True
            break

        for call in msg.tool_calls:
            name = call.function.name
            state.tool_calls += 1
            state.last_tool = name
            try:
                args = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            result = _execute_tool(name, args, user_id)
            validated = validate_tool_result(result)
            messages.append({
                "role": "tool",
                "tool_call_id": call.id,
                "name": name,
                "content": validated.content,
            })
            if validated.ok:
                state.consecutive_failures = 0
            else:
                state.consecutive_failures += 1
                messages.append({
                    "role": "system",
                    "content": recovery_instruction(name, validated),
                })

    if state.consecutive_failures >= 2:
        yield "⚠️ Tool execution repeatedly failed."
        return
    if not prepared_final_response and state.round_number >= min(MAX_ITERATIONS, execution_plan.max_tool_rounds):
        yield "⚠️ Max tool iterations reached — task incomplete reh gaya."
        return

    try:
        stream = client.chat.completions.create(
            model=VISION_MODEL if image_urls else MODEL,
            messages=messages,
            temperature=0.4,
            stream=True,
        )
        parts = []
        for chunk in stream:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                parts.append(delta)
                yield delta
        answer = "".join(parts)
        if answer:
            save_turn(session_id, goal, answer, user_id=user_id)
    except Exception:
        logger.exception("Streaming final model request failed")
        yield "❌ Streaming request failed."

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
            session_id = f"session-{time.time_ns()}"
            print(f"🆕 New session: {session_id}\n")
            continue
        if command == "/memories":
            print("\n".join(f"- {m}" for m in semantic_recall_memories("", limit=50, user_id=0)) or "(no memories)")
            print()
            continue
        if command.startswith("/remember "):
            remember_fact(goal[len("/remember "):].strip(), source="user-command", user_id=0)
            print("🧠 Memory saved.\n")
            continue
        print("\nAgent:", run_agent(goal, session_id=session_id, user_id=0), "\n")

if __name__ == "__main__":
    init_db()
    print(run_agent(" ".join(sys.argv[1:]))) if len(sys.argv) > 1 else interactive()

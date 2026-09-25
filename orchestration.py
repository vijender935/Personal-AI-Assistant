"""Lightweight deterministic task planner for agent orchestration.

The planner does not call an LLM. It prepares execution hints so the agent can
route a request through memory, RAG, web/local tools, and MCP without changing
the user's request.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TaskPlan:
    intent: str
    needs_memory: bool
    needs_rag: bool
    needs_web: bool
    needs_local_tools: bool
    needs_mcp: bool
    complexity: str


_WEB_TERMS = {
    "latest", "today", "current", "news", "weather", "price", "search",
    "online", "internet", "recent", "abhi", "aaj", "taaza",
}
_RAG_TERMS = {
    "document", "pdf", "file", "uploaded", "according to", "according",
    "document me", "file me", "meri file", "mere document",
}
_LOCAL_TERMS = {
    "calculate", "calculator", "math", "file", "read", "write", "folder",
    "directory", "shell", "terminal", "run command", "rename",
}
_MCP_TERMS = {
    "github", "slack", "notion", "telegram", "mcp", "repository", "repo",
    "pull request", "issue",
}
_MEMORY_TERMS = {
    "remember", "memory", "yaad", "previous", "pehle", "last time",
    "meri preference", "what did i tell you",
}


def _contains(text: str, terms: set[str]) -> bool:
    return any(term in text for term in terms)


def plan_task(goal: str) -> TaskPlan:
    text = goal.lower().strip()

    explicit_memory = text.startswith((
        "remember ", "remember that ", "yaad rakho", "yaad rakhna",
        "note that ",
    ))
    needs_memory = explicit_memory or _contains(text, _MEMORY_TERMS)
    needs_rag = _contains(text, _RAG_TERMS)
    needs_web = _contains(text, _WEB_TERMS)
    needs_local = _contains(text, _LOCAL_TERMS)
    needs_mcp = _contains(text, _MCP_TERMS)

    if needs_mcp:
        intent = "external_tool"
    elif needs_rag:
        intent = "document_qa"
    elif needs_web:
        intent = "current_information"
    elif needs_local:
        intent = "local_tool"
    elif needs_memory:
        intent = "memory_context"
    else:
        intent = "conversation"

    signal_count = sum((needs_memory, needs_rag, needs_web, needs_local, needs_mcp))
    complexity = "complex" if signal_count >= 2 else "tool" if signal_count == 1 else "simple"

    return TaskPlan(
        intent=intent,
        needs_memory=needs_memory,
        needs_rag=needs_rag,
        needs_web=needs_web,
        needs_local_tools=needs_local,
        needs_mcp=needs_mcp,
        complexity=complexity,
    )


def plan_prompt(plan: TaskPlan) -> str:
    routes = []
    if plan.needs_memory:
        routes.append("use relevant saved memory when it helps")
    if plan.needs_rag:
        routes.append("use relevant knowledge-base/document context")
    if plan.needs_web:
        routes.append("use web_search for current or online information")
    if plan.needs_local_tools:
        routes.append("use an appropriate local tool when required")
    if plan.needs_mcp:
        routes.append("use an explicitly configured MCP tool when required")

    route_text = "; ".join(routes) if routes else "answer conversationally without unnecessary tools"
    return (
        f"Task plan: intent={plan.intent}, complexity={plan.complexity}. "
        f"Routing guidance: {route_text}. "
        "Treat these as hints, not facts; inspect the user's actual request before acting."
    )

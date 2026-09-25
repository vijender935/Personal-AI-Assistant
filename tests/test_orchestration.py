from orchestration import plan_prompt, plan_task


def test_simple_conversation_plan():
    plan = plan_task("Hello, how are you?")
    assert plan.intent == "conversation"
    assert plan.complexity == "simple"
    assert not plan.needs_web


def test_current_information_plan():
    plan = plan_task("What is the latest news today?")
    assert plan.intent == "current_information"
    assert plan.needs_web


def test_document_plan():
    plan = plan_task("Meri uploaded PDF file me kya likha hai?")
    assert plan.intent == "document_qa"
    assert plan.needs_rag


def test_mcp_plan():
    plan = plan_task("Check my GitHub repository issues")
    assert plan.intent == "external_tool"
    assert plan.needs_mcp


def test_multi_route_plan():
    plan = plan_task("Search my previous memory and check today's GitHub news")
    assert plan.complexity == "complex"
    assert plan.needs_memory
    assert plan.needs_mcp
    assert plan.needs_web


def test_plan_prompt_is_actionable():
    plan = plan_task("Calculate this and search the latest result")
    prompt = plan_prompt(plan)
    assert "Task plan:" in prompt
    assert "web_search" in prompt

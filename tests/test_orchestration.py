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



def test_execution_plan_orders_routes():
    from orchestration import build_execution_plan

    plan = plan_task("Search my memory and today's GitHub issue")
    execution = build_execution_plan(plan)
    assert execution.steps[0] == "understand_request"
    assert "retrieve_memory" in execution.steps
    assert "web_or_current_information" in execution.steps
    assert "mcp_tool_execution" in execution.steps
    assert execution.steps[-2:] == ("validate_tool_results", "compose_answer")
    assert execution.max_tool_rounds == 4



def test_tool_result_validation_and_recovery():
    from orchestration import recovery_instruction, validate_tool_result

    ok = validate_tool_result({"value": 42})
    assert ok.ok is True
    assert ok.content == "{'value': 42}"

    failed = validate_tool_result("Tool error in calculator: invalid input")
    assert failed.ok is False
    assert failed.recoverable is True
    assert "Do not invent missing data" in recovery_instruction("calculator", failed)

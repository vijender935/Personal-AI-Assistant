from orchestration import plan_prompt,plan_task
def test_simple_conversation_plan():assert plan_task("Hello, how are you?").complexity=="simple"
def test_current_information_plan():assert plan_task("What is the latest news today?").needs_web
def test_document_plan():assert plan_task("Meri uploaded PDF file me kya likha hai?").needs_rag
def test_mcp_plan():assert plan_task("Check my GitHub repository issues").needs_mcp
def test_multi_route_plan():
 p=plan_task("Search my previous memory and check today's GitHub news");assert p.needs_memory and p.needs_mcp and p.needs_web
def test_plan_prompt():assert "Task plan:" in plan_prompt(plan_task("Calculate this and search the latest result"))
def test_tool_result_validation():
 from orchestration import validate_tool_result,recovery_instruction
 ok=validate_tool_result({"value":42});assert ok.ok and ok.content=="{'value': 42}"
 failed=validate_tool_result("Tool error in calculator: invalid input");assert not failed.ok and "Do not invent missing data" in recovery_instruction("calculator",failed)
def test_execution_guard():
 from orchestration import ExecutionState,should_continue_execution
 s=ExecutionState(round_number=1);assert should_continue_execution(s,4);s.consecutive_failures=2;assert not should_continue_execution(s,4)
def test_select_mcp_tools():
 from orchestration import select_mcp_tools
 schemas=[{"type":"function","function":{"name":"mcp__github__list_issues","description":"List repository issues"}},{"type":"function","function":{"name":"mcp__github__create_issue","description":"Create a repository issue"}}]
 assert len(select_mcp_tools(schemas,"check repository issues",max_tools=2))==2
def test_agent_simple_schemas():
 from agent import _tool_schemas_for
 assert _tool_schemas_for("Hi")==[]

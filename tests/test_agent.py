"""Agent 引擎测试"""

import pytest
from unittest.mock import patch, Mock


class TestRouter:
    def test_simple_greeting(self):
        from app.agent.router import classify_task
        assert classify_task("你好") == "simple"

    def test_simple_fact(self):
        from app.agent.router import classify_task
        assert classify_task("公司年假有几天？") == "simple"

    def test_complex_analysis(self):
        from app.agent.router import classify_task
        result = classify_task("分析销售数据并生成对比报告")
        assert result == "complex"

    def test_complex_multi_step(self):
        from app.agent.router import classify_task
        result = classify_task("先查客户信息，再导出报表")
        assert result == "complex"

    @patch("app.agent.router.llm_route", side_effect=Exception("LLM 超时"))
    def test_llm_fallback_to_rules(self, mock_llm):
        from app.agent.router import classify_task
        result = classify_task("分析销售数据并生成报告")
        assert result == "complex"


class TestPlanner:
    def test_rule_fallback_data_report(self):
        from app.agent.fallback import rule_based_plan
        plan = rule_based_plan("分析本月销售数据并生成报表")
        assert len(plan["tasks"]) >= 1
        assert len(plan["execution_order"]) >= 1

    def test_rule_fallback_oa(self):
        from app.agent.fallback import rule_based_plan
        plan = rule_based_plan("查一下我的请假审批")
        assert plan["tasks"][0]["tool_name"] == "oa_query"

    def test_rule_fallback_crm(self):
        from app.agent.fallback import rule_based_plan
        plan = rule_based_plan("查看所有客户信息")
        assert plan["tasks"][0]["tool_name"] == "crm_query"

    def test_rule_fallback_knowledge(self):
        from app.agent.fallback import rule_based_plan
        plan = rule_based_plan("公司制度是什么")
        assert plan["tasks"][0]["tool_name"] == "knowledge_search"


class TestReflection:
    def test_categorize_timeout(self):
        from app.agent.reflection import categorize_error, ErrorCategory
        assert categorize_error(Exception("Connection timed out")) == ErrorCategory.TIMEOUT

    def test_categorize_permission(self):
        from app.agent.reflection import categorize_error, ErrorCategory
        assert categorize_error(Exception("Permission denied")) == ErrorCategory.PERMISSION

    def test_categorize_not_found(self):
        from app.agent.reflection import categorize_error, ErrorCategory
        assert categorize_error(Exception("File not found")) == ErrorCategory.NOT_FOUND

    def test_retry_matrix_timeout_can_retry(self):
        from app.agent.reflection import categorize_error, RETRY_MATRIX
        cat = categorize_error(Exception("Request timed out"))
        assert RETRY_MATRIX[cat]["can_retry"] is True

    def test_retry_matrix_permission_cannot_retry(self):
        from app.agent.reflection import categorize_error, RETRY_MATRIX
        cat = categorize_error(Exception("Permission denied"))
        assert RETRY_MATRIX[cat]["can_retry"] is False

    @pytest.mark.asyncio
    async def test_circuit_breaker(self):
        from app.agent.reflection import ReflectionHandler
        handler = ReflectionHandler(max_total_retries=3)
        # 连续失败 3 次后应熔断
        for _ in range(3):
            handler.record_attempt("task_1")
        assert not await handler.can_retry("task_1", Exception("timeout"))


class TestGraph:
    def test_graph_compiles(self):
        from app.agent.graph import create_agent_graph
        mock_tools = []
        app = create_agent_graph(tools=mock_tools)
        assert app is not None

    def test_graph_has_required_nodes(self):
        from app.agent.graph import create_agent_graph
        app = create_agent_graph(tools=[])
        nodes = app.get_graph().nodes
        node_names = {n for n in nodes}
        required = {"classify", "simple_react", "plan", "execute", "aggregate"}
        assert required.issubset(node_names), f"Missing: {required - node_names}"

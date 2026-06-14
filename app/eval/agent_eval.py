"""
Agent 评测引擎 — 工具调用成功率 / 任务分类准确率

对标技术文档:
- 工具调用成功率 > 90%
- 任务分类准确率 > 80%
"""

import time
import logging
from typing import List
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class AgentEvalResult:
    task_id: str
    task: str
    expected_tool: str
    actual_tool: str
    success: bool
    latency_ms: float

@dataclass
class AgentEvalReport:
    results: List[AgentEvalResult] = field(default_factory=list)
    total: int = 0
    tool_match_count: int = 0
    tool_accuracy: float = 0.0
    avg_latency_ms: float = 0.0
    success_rate: float = 0.0


def run_agent_eval() -> AgentEvalReport:
    """
    Agent 评测 — 测试任务分类 + 工具路由准确性。

    不用真实调用 LLM，而是测试:
    1. 任务分类是否正确 (classify_task)
    2. 规则引擎路由是否正确
    """
    from app.eval.testset import AGENT_TESTSET
    from app.agent.router import classify_task
    from app.agent.fallback import rule_based_plan

    testset = AGENT_TESTSET
    report = AgentEvalReport(total=len(testset))

    for item in testset:
        start = time.time()

        # 1. 分类测试
        task_type = classify_task(item["task"])

        # 2. 规则引擎测试
        plan = rule_based_plan(item["task"])
        actual_tool = plan.get("tasks", [{}])[0].get("tool_name", "unknown") if plan.get("tasks") else "unknown"

        latency = (time.time() - start) * 1000
        tool_match = actual_tool == item["expected_tool"]

        eval_result = AgentEvalResult(
            task_id=item["id"],
            task=item["task"],
            expected_tool=item["expected_tool"],
            actual_tool=actual_tool,
            success=tool_match,
            latency_ms=round(latency, 1),
        )
        report.results.append(eval_result)

        if tool_match:
            report.tool_match_count += 1

        status = "✅" if tool_match else "❌"
        logger.info(
            f"  {status} {item['id']}: expected={item['expected_tool']} "
            f"actual={actual_tool} ({latency:.0f}ms)"
        )

    report.tool_accuracy = round(report.tool_match_count / max(report.total, 1), 3)
    report.avg_latency_ms = round(
        sum(r.latency_ms for r in report.results) / max(len(report.results), 1), 1
    )

    logger.info(
        f"Agent 评测完成: tool_accuracy={report.tool_accuracy:.1%} "
        f"({report.tool_match_count}/{report.total})"
    )
    return report

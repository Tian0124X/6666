"""评测 API — RAG 评测 + Agent 评测"""

from fastapi import APIRouter

router = APIRouter()


@router.post("/eval/rag", tags=["评测"])
async def run_rag_evaluation():
    """运行 RAG 评测 (异步，可能需要 1-3 分钟)"""
    from app.eval.rag_eval import run_rag_eval
    report = await run_rag_eval(verbose=True)
    return {
        "accuracy": report.accuracy,
        "avg_recall": report.avg_recall,
        "avg_latency_ms": report.avg_latency_ms,
        "passed": report.passed,
        "total": report.total,
        "details": [
            {
                "id": r.question_id,
                "question": r.question,
                "recall": r.keyword_recall,
                "passed": r.passed,
                "latency_ms": r.latency_ms,
            }
            for r in report.results
        ],
    }


@router.post("/eval/agent", tags=["评测"])
async def run_agent_evaluation():
    """运行 Agent 评测"""
    from app.eval.agent_eval import run_agent_eval
    report = run_agent_eval()
    return {
        "tool_accuracy": report.tool_accuracy,
        "avg_latency_ms": report.avg_latency_ms,
        "tool_match_count": report.tool_match_count,
        "total": report.total,
        "details": [
            {
                "id": r.task_id,
                "task": r.task,
                "expected": r.expected_tool,
                "actual": r.actual_tool,
                "match": r.success,
                "latency_ms": r.latency_ms,
            }
            for r in report.results
        ],
    }


@router.get("/eval/summary", tags=["评测"])
async def eval_summary():
    """评测总览 (结合监控统计数据)"""
    from app.api.monitoring import _stats
    total = max(_stats["total_requests"], 1)
    ratings = _stats["ratings"]
    return {
        "api_success_rate": round(_stats["total_success"] / total * 100, 1),
        "avg_latency_ms": round(_stats["total_latency_ms"] / total, 1),
        "total_requests": _stats["total_requests"],
        "tool_calls": dict(_stats["tool_calls"]),
        "avg_rating": round(sum(r[0] for r in ratings) / max(len(ratings), 1), 1) if ratings else None,
        "rating_count": len(ratings),
        "last_updated": None,
    }

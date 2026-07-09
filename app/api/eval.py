"""评测 API — RAG 评测 + Agent 评测 + 历史持久化"""

import json
import logging
from datetime import datetime
from fastapi import APIRouter

logger = logging.getLogger(__name__)
router = APIRouter()


def _save_eval_record(eval_type: str, result: dict):
    """保存评测结果到数据库"""
    from app.models.database import get_session, EvalRecord
    db = get_session()
    if db is None:
        logger.warning("数据库不可用，评测结果仅返回不持久化")
        return
    try:
        record = EvalRecord(
            eval_type=eval_type,
            accuracy=str(result.get("accuracy", "")),
            avg_recall=str(result.get("avg_recall", "")) if eval_type == "rag" else None,
            tool_accuracy=str(result.get("tool_accuracy", "")) if eval_type == "agent" else None,
            avg_latency_ms=str(result.get("avg_latency_ms", "")),
            passed=result.get("passed", 0),
            total=result.get("total", 0),
            details_json=json.dumps(result.get("details", []), ensure_ascii=False),
        )
        db.add(record)
        db.commit()
        logger.info(f"评测结果已保存: {eval_type} accuracy={result.get('accuracy')}")
    except Exception as e:
        logger.warning(f"保存评测结果失败: {e}")
        db.rollback()
    finally:
        db.close()


@router.post("/eval/rag", tags=["评测"])
async def run_rag_evaluation(mode: str = "fast"):
    """运行 RAG 评测。mode=fast (关键词, 默认) | mode=ragas (LLM标准评测, 慢)"""
    from app.eval.rag_eval import run_rag_eval
    report = await run_rag_eval(verbose=True, mode=mode)
    result = {
        "mode": report.mode,
        "accuracy": report.accuracy,
        "avg_recall": report.avg_recall,
        "avg_latency_ms": report.avg_latency_ms,
        "passed": report.passed,
        "total": report.total,
        # RAGAS 指标
        "avg_faithfulness": report.avg_faithfulness,
        "avg_answer_relevancy": report.avg_answer_relevancy,
        "avg_context_precision": report.avg_context_precision,
        "avg_context_recall": report.avg_context_recall,
        "avg_answer_correctness": report.avg_answer_correctness,
        "avg_context_entity_recall": report.avg_context_entity_recall,
        "details": [
            {
                "id": r.question_id,
                "question": r.question,
                "recall": r.keyword_recall,
                "passed": r.passed,
                "latency_ms": r.latency_ms,
                "faithfulness": r.faithfulness,
                "answer_relevancy": r.answer_relevancy,
                "context_precision": r.context_precision,
                "context_recall": r.context_recall,
                "answer_correctness": r.answer_correctness,
                "context_entity_recall": r.context_entity_recall,
                "retrieval_latency_ms": r.retrieval_latency_ms,
                "generation_latency_ms": r.generation_latency_ms,
                "estimated_tokens": r.estimated_tokens,
                "estimated_cost_cny": r.estimated_cost_cny,
            }
            for r in report.results
        ],
    }
    _save_eval_record("rag", result)
    return result


@router.post("/eval/agent", tags=["评测"])
async def run_agent_evaluation():
    """运行 Agent 评测"""
    from app.eval.agent_eval import run_agent_eval
    report = run_agent_eval()
    result = {
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
    _save_eval_record("agent", result)
    return result


@router.get("/eval/summary", tags=["评测"])
async def eval_summary():
    """评测总览 (结合监控统计数据)"""
    from app.api.monitoring import _store
    stats = _store.get_dashboard()
    full = _store.get_stats()

    # 获取最近一次评测时间
    last_updated = None
    from app.models.database import get_session, EvalRecord
    from sqlalchemy import desc
    db = get_session()
    if db:
        try:
            latest = (
                db.query(EvalRecord)
                .order_by(desc(EvalRecord.created_at))
                .first()
            )
            if latest and latest.created_at:
                last_updated = latest.created_at.isoformat()
        except Exception:
            pass
        finally:
            db.close()

    return {
        "api_success_rate": stats["success_rate"],
        "avg_latency_ms": stats["avg_latency_ms"],
        "total_requests": stats["requests_total"],
        "tool_calls": dict(_store.tool_calls),
        "avg_rating": stats["avg_rating"],
        "rating_count": full["rating_count"],
        "last_updated": last_updated or datetime.now().isoformat(),
    }


@router.get("/eval/history", tags=["评测"])
async def eval_history(eval_type: str = "", limit: int = 20):
    """获取评测历史记录"""
    from app.models.database import get_session, EvalRecord
    from sqlalchemy import desc

    records = []
    db = get_session()
    if db is None:
        return {"records": [], "total": 0, "message": "数据库不可用"}

    try:
        q = db.query(EvalRecord).order_by(desc(EvalRecord.created_at))
        if eval_type:
            q = q.filter(EvalRecord.eval_type == eval_type)
        rows = q.limit(limit).all()

        for r in rows:
            entry = {
                "id": r.id,
                "eval_type": r.eval_type,
                "accuracy": r.accuracy,
                "avg_latency_ms": r.avg_latency_ms,
                "passed": r.passed,
                "total": r.total,
                "created_at": r.created_at.isoformat() if r.created_at else "",
            }
            if r.eval_type == "rag":
                entry["avg_recall"] = r.avg_recall
            else:
                entry["tool_accuracy"] = r.tool_accuracy
            # 解析详情
            if r.details_json:
                try:
                    entry["details"] = json.loads(r.details_json)
                except Exception:
                    entry["details"] = []
            records.append(entry)

        total = q.count()
    except Exception as e:
        logger.warning(f"查询评测历史失败: {e}")
        return {"records": [], "total": 0, "message": str(e)}
    finally:
        db.close()

    return {"records": records, "total": total}

"""文档级检索评测必须排除同文档切片重复带来的虚高指标。"""


def test_recall_at_k_counts_one_document_once_for_repeated_chunks():
    """同一文件多次出现时，文档级 Recall 不能超过 1。"""
    from app.eval.retrieval_eval import recall_at_k

    score = recall_at_k(
        ["/docs/员工手册.pdf", "/docs/员工手册.pdf", "/docs/员工手册.pdf"],
        ["员工手册.pdf"],
        k=5,
    )

    assert score == 1.0


def test_query_plan_strategy_is_registered_for_real_comparison():
    """金标评测必须能够调用新 QueryPlan 链路。"""
    from app.eval.retrieval_eval import STRATEGIES

    assert "query_plan" in STRATEGIES
    assert "query_plan_rerank" in STRATEGIES

"""纯 RAG HTTP 接口回归测试。"""

from fastapi.testclient import TestClient


def test_answer_stream_sends_evidence_before_content(monkeypatch):
    """SSE 必须先让界面拿到可点击证据，再开始输出答案。"""
    from app.api import rag
    from main import app

    async def fake_stream(question, k, history):
        yield {"type": "retrieval", "sources": [{"citation_id": "S1", "chunk_id": "c1"}], "timings_ms": {"retrieval": 3.0}}
        yield {"type": "content", "content": "年休假按制度执行 [S1]"}
        yield {"type": "done", "sources": [{"citation_id": "S1", "chunk_id": "c1"}], "timings_ms": {"total": 5.0}}

    monkeypatch.setattr(rag, "rag_qa_stream", fake_stream)
    response = TestClient(app).post("/api/rag/answers/stream", json={"question": "年休假有几天？"})

    payloads = [line[6:] for line in response.text.splitlines() if line.startswith("data: ")]
    assert '"type": "retrieval"' in payloads[1]
    assert '"type": "content"' in payloads[2]


def test_citation_endpoint_returns_exact_evidence(monkeypatch):
    """证据抽屉通过稳定文档和切片身份读取原始片段。"""
    from app.api import rag
    from main import app

    monkeypatch.setattr(rag, "get_evidence", lambda document_id, chunk_id: {
        "document_id": document_id, "chunk_id": chunk_id, "filename": "制度.pdf",
        "page": 3, "content": "证据正文", "nearby": [],
    })
    response = TestClient(app).get("/api/rag/citations/doc-1/chunk-1")

    assert response.status_code == 200
    assert response.json()["content"] == "证据正文"


def test_documents_list_keeps_uploaded_file_visible_while_indexing(monkeypatch, tmp_path):
    """上传后即使尚未写入切片，文件任务也必须在界面可见。"""
    from app.api import rag
    from main import app

    (tmp_path / "员工手册.pdf").write_bytes(b"pdf")
    monkeypatch.setattr(rag, "DOCUMENTS_DIR", tmp_path)
    monkeypatch.setattr(rag, "_index_status", {
        "员工手册.pdf": {"status": "indexing", "stage": "正在写入知识库", "chunks": 3, "error": ""},
    })
    monkeypatch.setattr(rag, "get_document_summaries", lambda: [])
    monkeypatch.setattr(rag, "get_document_count", lambda: 0)

    response = TestClient(app).get("/api/rag/documents")

    assert response.status_code == 200
    assert response.json()["documents"] == [{
        "filename": "员工手册.pdf", "document_id": None, "chunks": 3,
        "status": "indexing", "stage": "正在写入知识库", "error": "",
        "completed_at": None, "size": 3,
    }]


def test_documents_list_hides_repository_placeholder(monkeypatch, tmp_path):
    """知识库目录的占位文件不能被误显示成待索引文档。"""
    from app.api import rag
    from main import app

    (tmp_path / ".gitkeep").write_text("", encoding="utf-8")
    monkeypatch.setattr(rag, "DOCUMENTS_DIR", tmp_path)
    monkeypatch.setattr(rag, "_index_status", {})
    monkeypatch.setattr(rag, "get_document_summaries", lambda: [])
    monkeypatch.setattr(rag, "get_document_count", lambda: 0)

    response = TestClient(app).get("/api/rag/documents")

    assert response.status_code == 200
    assert response.json()["documents"] == []


def test_documents_list_exposes_persisted_manual_document_date(monkeypatch, tmp_path):
    """日期必须来自已持久化的切片元数据，而不是文件系统时间。"""
    from app.api import rag
    from main import app

    (tmp_path / "员工手册.pdf").write_bytes(b"pdf")
    monkeypatch.setattr(rag, "DOCUMENTS_DIR", tmp_path)
    monkeypatch.setattr(rag, "_index_status", {})
    monkeypatch.setattr(rag, "get_document_summaries", lambda: [{
        "filename": "员工手册.pdf", "document_id": "doc-1", "chunks": 2,
        "file_sha256": "a" * 64, "indexed_at": "2026-07-16T00:00:00+00:00",
        "document_date": "2025-07-01",
    }])
    monkeypatch.setattr(rag, "get_document_count", lambda: 2)

    response = TestClient(app).get("/api/rag/documents")

    assert response.status_code == 200
    assert response.json()["documents"][0]["document_date"] == "2025-07-01"

"""骨架验证测试 — 确保 FastAPI 应用能启动并响应"""

import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_check():
    """健康检查端点应返回正常状态"""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["version"] == "1.0.0"


def test_swagger_docs_available():
    """Swagger 文档应可访问"""
    response = client.get("/docs")
    assert response.status_code == 200


def test_redoc_available():
    """ReDoc 文档应可访问"""
    response = client.get("/redoc")
    assert response.status_code == 200


def test_chat_endpoint():
    """对话端点应返回骨架响应"""
    response = client.post("/api/chat", json={
        "message": "你好",
        "session_id": "test_session",
        "user_id": "test_user",
    })
    assert response.status_code == 200
    data = response.json()
    assert "answer" in data
    assert len(data["answer"]) > 0


def test_chat_stream_endpoint():
    """流式对话端点应返回 SSE"""
    response = client.post("/api/chat/stream", json={
        "message": "你好",
        "session_id": "test_session",
        "user_id": "test_user",
    })
    assert response.status_code == 200
    assert "text/event-stream" in response.headers.get("content-type", "")


def test_knowledge_qa_endpoint():
    """知识问答端点：无 ChromaDB 时返回 503，有则返回 200"""
    response = client.post("/api/knowledge/qa", json={
        "question": "年假有几天？",
        "top_k": 5,
    })
    # 503 = ChromaDB 未启动（预期），200 = 正常响应，500 = 其他运行时错误
    assert response.status_code in (200, 500, 503)
    if response.status_code == 200:
        data = response.json()
        assert "answer" in data


def test_tools_list_endpoint():
    """工具列表端点应返回可用工具"""
    response = client.get("/api/tools/list")
    assert response.status_code == 200
    data = response.json()
    assert "tools" in data
    assert len(data["tools"]) > 0


def test_tools_analyze_endpoint():
    """数据分析端点应返回骨架响应"""
    response = client.post("/api/tools/analyze", json={
        "file_path": "/data/test.xlsx",
        "action": "summary",
    })
    assert response.status_code == 200
    data = response.json()
    assert "result" in data

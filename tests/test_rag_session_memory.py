"""RAG 服务端会话记忆回归测试。"""

from fastapi.testclient import TestClient


def test_stream_uses_session_memory_and_persists_completed_turns(monkeypatch):
    """后续追问应读取同一会话的历史，并在完成后写入一问一答。"""
    from app.api import rag
    from main import app

    captured: dict[str, object] = {}

    class FakeMemory:
        def get_recent_turns(self, user_id, session_id, limit=6):
            captured["read"] = (user_id, session_id, limit)
            return [{"role": "user", "content": "上一问：年休假"}]

        def append_turn(self, user_id, session_id, role, content):
            captured.setdefault("writes", []).append((user_id, session_id, role, content))

    async def fake_stream(question, k, history):
        captured["stream"] = (question, k, history)
        yield {"type": "content", "content": "员工累计工作年限决定年休假天数。[S1]"}
        yield {"type": "done", "sources": []}

    monkeypatch.setattr(rag, "session_memory", FakeMemory())
    monkeypatch.setattr(rag, "rag_qa_stream", fake_stream)

    response = TestClient(app).post("/api/rag/answers/stream", json={
        "question": "那我有几天？",
        "session_id": "session_memory_1",
    })

    assert response.status_code == 200
    assert captured["read"] == ("anonymous", "session_memory_1", 6)
    assert captured["stream"] == (
        "那我有几天？", 5, [{"role": "user", "content": "上一问：年休假"}],
    )
    assert captured["writes"] == [
        ("anonymous", "session_memory_1", "user", "那我有几天？"),
        ("anonymous", "session_memory_1", "assistant", "员工累计工作年限决定年休假天数。[S1]"),
    ]


def test_stream_falls_back_to_legacy_history_when_session_is_empty(monkeypatch):
    """旧客户端携带的 history 在新会话尚无服务端记录时仍能工作。"""
    from app.api import rag
    from main import app

    captured: dict[str, object] = {}

    class EmptyMemory:
        def get_recent_turns(self, *_args, **_kwargs):
            return []

        def append_turn(self, *_args, **_kwargs):
            return None

    async def fake_stream(question, k, history):
        captured["history"] = history
        yield {"type": "content", "content": "好的。[S1]"}
        yield {"type": "done", "sources": []}

    monkeypatch.setattr(rag, "session_memory", EmptyMemory())
    monkeypatch.setattr(rag, "rag_qa_stream", fake_stream)

    response = TestClient(app).post("/api/rag/answers/stream", json={
        "question": "继续说明",
        "session_id": "new_session",
        "history": [{"role": "assistant", "content": "这是旧版本历史"}],
    })

    assert response.status_code == 200
    assert captured["history"] == [{"role": "assistant", "content": "这是旧版本历史"}]

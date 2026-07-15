"""三层 RAG 记忆的边界和降级行为回归测试。"""


class FakeCache:
    """隔离 Redis，验证 MySQL 不可用时的进程内降级逻辑。"""

    def __init__(self):
        self.values = {}

    def get_json(self, key):
        return self.values.get(key)

    def set_json(self, key, value, ttl_seconds):
        self.values[key] = value

    def delete(self, key):
        self.values.pop(key, None)


def test_session_memory_builds_extractive_summary_without_database(monkeypatch):
    """长对话达到阈值后，应该得到不调用模型的可持久化摘要。"""
    from app.memory import session

    monkeypatch.setattr(session, "get_session", lambda: None)
    monkeypatch.setattr(session, "memory_cache", FakeCache())
    store = session.SessionMemoryStore()
    for index in range(4):
        store.append_turn("u1", "s1", "user", f"问题 {index}")
        store.append_turn("u1", "s1", "assistant", f"回答 {index}")

    summary = store.refresh_summary("u1", "s1", trigger_turns=8, source_turns=16)

    assert "用户近期关注：问题 0" in summary
    assert "已给出回复：" in summary
    assert "回答 3" in summary
    assert store.get_summary("u1", "s1") == summary


def test_user_preference_is_explicit_and_can_be_forgotten(monkeypatch):
    """用户偏好只能显式写入，并支持按用户删除。"""
    from app.memory import profile

    monkeypatch.setattr(profile, "get_session", lambda: None)
    monkeypatch.setattr(profile, "memory_cache", FakeCache())
    store = profile.UserPreferenceStore()

    preference = store.save_preference("u1", "回答使用中文并给出引用", "s1")

    assert store.list_preferences("u1") == [preference]
    assert store.list_preferences("anonymous") == []
    assert store.delete_preference("u1", preference["id"]) is True
    assert store.list_preferences("u1") == []


def test_stream_passes_summary_and_preferences_only_to_query_context(monkeypatch):
    """摘要和偏好应作为系统上下文传给追问改写，不替代知识库证据。"""
    from app.api import rag
    from main import app
    from fastapi.testclient import TestClient

    captured = {}

    class FakeMemory:
        def get_recent_turns(self, *_args):
            return [{"role": "user", "content": "上一轮讨论年休假"}]

        def get_summary(self, *_args):
            return "用户正在核对年休假制度"

        def append_turn(self, *_args):
            return None

        def refresh_summary(self, *_args):
            return ""

    class FakePreferences:
        def list_preferences(self, *_args):
            return [{"id": "1", "fact_text": "回答使用中文"}]

    async def fake_stream(question, k, history):
        captured["history"] = history
        yield {"type": "content", "content": "年休假按制度执行。[S1]"}
        yield {"type": "done", "sources": []}

    monkeypatch.setattr(rag, "session_memory", FakeMemory())
    monkeypatch.setattr(rag, "user_preference_memory", FakePreferences())
    monkeypatch.setattr(rag, "rag_qa_stream", fake_stream)

    response = TestClient(app).post("/api/rag/answers/stream", json={
        "question": "那我有几天？",
        "session_id": "memory_layer_1",
    })

    assert response.status_code == 200
    assert captured["history"] == [
        {"role": "system", "content": "这是当前会话的抽取式摘要，仅用于理解追问，不是知识证据：\n用户正在核对年休假制度"},
        {"role": "system", "content": "这是用户明确的表达偏好，只影响回答形式，不是知识证据：回答使用中文"},
        {"role": "user", "content": "上一轮讨论年休假"},
    ]

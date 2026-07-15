# 知识库 RAG

一个以 PostgreSQL + pgvector 为唯一知识库后端的可追溯 RAG 系统。用户的每个回答都可以回到具体文档页和切片，而不是得到不可核查的“文件名 + 摘要”。

## 核心能力

- 单一检索链路：追问改写（仅按需）→ 向量与关键词召回 → 单次 RRF → 证据截断 → 带引用生成。
- 可点击引用：回答中的 `[S1]` 和来源卡打开右侧证据抽屉，展示原始片段、相邻上下文、页码和原文件下载。
- 证据不凑数：检索候选只用于内部核查；界面仅展示最终回答真正引用的切片，避免把无关文件误显示为回答依据。
- 可见入库任务：上传成功会立即出现任务提示，并持续显示“已上传 → 索引中 → 已就绪/失败”和实际证据切片数。
- 低延迟默认：线上默认关闭 CPU Cross-Encoder 重排，避免约二十秒的重排阻塞；embedding 在启动时后台预热。
- 反馈闭环：用户可以标记“有帮助”“无帮助”“来源错误”，反馈会记录到 `data/rag-feedback.jsonl`，可用于离线回放。

## 启动

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn main:app --reload

Set-Location frontend-react
npm ci
npm run dev
```

- 前端：`http://localhost:5173`
- 后端和 OpenAPI：`http://localhost:8000/docs`

必须配置 PostgreSQL/pgvector、`PG_PASSWORD` 和 `LLM_API_KEY`。在线重排默认关闭；只有在硬件评测证明 P95 小于 250ms 后，才设置 `RAG_ONLINE_RERANK=true`。

## 验证

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_pure_rag_contract.py tests\test_rag_api_contract.py -q
Set-Location frontend-react
npm run build
```

详细设计、API 和性能口径见 [RAG 架构](docs/rag-architecture.md)、[RAG API](docs/rag-api.md) 和 [性能基准](docs/rag-performance.md)。

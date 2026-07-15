# 知识库 RAG API

所有业务接口位于 `/api/rag`。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/answers` | 非流式问答，适合评测和脚本 |
| POST | `/answers/stream` | SSE 问答；依次发送状态、证据、内容和完成事件，并按 `session_id` 读取和保存会话记忆 |
| POST | `/documents/upload` | 上传 PDF、DOCX、XLSX、XLS、TXT 或 CSV 并后台索引 |
| GET | `/documents` | 查询文档、索引任务阶段、状态、切片数量与完成后的质量报告 |
| DELETE | `/documents/{filename}` | 删除原文件及其切片 |
| GET | `/citations/{document_id}/{chunk_id}` | 获取命中片段与相邻上下文 |
| GET | `/documents/{document_id}/download` | 下载引用所属的原文件 |
| GET | `/diagnostics` | 查看后端、模型和延迟目标 |
| POST | `/feedback` | 提交回答质量或来源准确性反馈 |
| GET | `/memory/preferences` | 读取当前登录用户已保存的表达偏好 |
| POST | `/memory/preferences` | 显式保存一条可撤回的表达偏好 |
| DELETE | `/memory/preferences/{preference_id}` | 删除指定表达偏好 |
| GET | `/memory/sessions/{session_id}/summary` | 读取当前登录用户的会话滚动摘要 |

`retrieval` SSE 事件的 `sources` 固定为空数组，只包含 `candidate_count`、`query_count`、`query_rewritten` 与阶段耗时；这是为了不把原始召回候选误导为回答证据。只有 `done.sources` 才包含已被最终答案引用的 `citation_id`、`document_id`、`chunk_id`、`filename`、`page`、`excerpt` 和 `score`，前端必须使用这些稳定身份读取证据。

上传接口会立即返回 `accepted`，随后前端可轮询 `/documents/{filename}/status` 或 `/documents`。每个文档都包含 `pending`、`indexing`、`done` 或 `error` 状态，以及面向用户的 `stage` 文案。`done` 状态返回实际写入的 `chunks`，并包含 `quality`：文件 SHA-256、解析单元、页数、源文本字符数、切片数、空切片、平均切片长度、解析器与文件类型，用于明确确认“已可用于问答”。

SSE 的 `retrieval` 事件只暴露 `candidate_count`，不将召回候选当作来源卡片；`done.sources` 仅包含最终回答真实引用的证据切片。这样不会把未采纳的文档误显示为回答依据。

QueryPlan 不新增 HTTP 接口。它从原问题中识别文件名、页码、Sheet 与文件类型，并仅在追问或候选少于配置阈值时调用 LLM 生成至多两条检索变体。规划详情和候选正文只进入内部 Trace；异常回退到原问题检索，且不会移除用户显式过滤条件。

记忆接口需要登录。用户偏好仅影响回答表达方式，不能作为知识库事实；会话摘要仅用于追问改写。Redis 仅缓存近期会话、摘要和偏好，MySQL 才是记忆持久化来源。

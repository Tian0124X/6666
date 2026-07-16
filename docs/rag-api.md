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
| GET | `/diagnostics` | 查看后端、模型、延迟目标及最近脱敏 Trace 的 P50/P95 |
| POST | `/feedback` | 提交回答质量或来源准确性反馈 |
| GET | `/feedback/queue` | 管理员查看 `pending` 或 `resolved` 反馈队列 |
| POST | `/feedback/{feedback_id}/resolve` | 管理员人工结案，记录后续动作而不自动修改知识库 |
| GET | `/memory/preferences` | 读取当前登录用户已保存的表达偏好 |
| POST | `/memory/preferences` | 显式保存一条可撤回的表达偏好 |
| DELETE | `/memory/preferences/{preference_id}` | 删除指定表达偏好 |
| GET | `/memory/sessions/{session_id}/summary` | 读取当前登录用户的会话滚动摘要 |

`retrieval` SSE 事件的 `sources` 固定为空数组，只包含 `candidate_count`、`query_count`、`query_rewritten` 与阶段耗时；这是为了不把原始召回候选误导为回答证据。只有 `done.sources` 才包含已被最终答案引用的 `citation_id`、`document_id`、`chunk_id`、`filename`、`page`、`excerpt` 和 `score`，前端必须使用这些稳定身份读取证据。

上传接口会立即返回 `accepted`，随后前端可轮询 `/documents/{filename}/status` 或 `/documents`。每个文档都包含 `pending`、`indexing`、`done` 或 `error` 状态，以及面向用户的 `stage` 文案。`done` 状态返回实际写入的 `chunks`，并包含 `quality`：文件 SHA-256、解析单元、页数、源文本字符数、切片数、空切片、平均切片长度、解析器与文件类型，用于明确确认“已可用于问答”。上传 multipart 可选字段 `document_date` 必须为 `YYYY-MM-DD`；它代表人工确认的生效/发布日期，写入每个切片并在文档列表的 `document_date` 返回。文件 SHA-256 与索引时间同时写入切片元数据；`GET /documents` 的 `version` 可在服务重启后继续显示当前索引版本。未填写日期的文档不会被时间条件匹配。

SSE 的 `retrieval` 事件只暴露 `candidate_count`，不将召回候选当作来源卡片；`done.sources` 仅包含最终回答真实引用的证据切片。这样不会把未采纳的文档误显示为回答依据。

QueryPlan 不新增 HTTP 接口。它从原问题中识别文件名、页码、Sheet 与文件类型，并仅在追问或候选少于配置阈值时调用 LLM 生成至多两条检索变体。规划详情和候选正文只进入内部 Trace；异常回退到原问题检索，且不会移除用户显式过滤条件。

`/diagnostics` 的 `recent_latency` 仅聚合当前应用运行批次最近 100 条脱敏 Trace：返回 `runtime_id`、样本数量、`generated/refusal/evidence_only` 分布，以及检索、生成、总耗时的 P50/P95；无当前批次 Trace 时各指标为 `null`。`latency_alert` 使用 `RAG_TOTAL_LATENCY_ALERT_P95_MS`（默认 3000ms）和 `RAG_LATENCY_ALERT_MIN_SAMPLES`（默认 20）判断 `normal`、`alert` 或 `insufficient_samples`，防止热重载冷启动污染告警。重启或热重载后的首条请求可能包含预热耗时，因此不会与上一个进程的历史数据混合。该接口不返回问题、答案、规划正文或召回候选。

记忆接口需要登录。用户偏好仅影响回答表达方式，不能作为知识库事实；会话摘要仅用于追问改写。Redis 仅缓存近期会话、摘要和偏好，MySQL 才是记忆持久化来源。

反馈队列接口仅允许 `admin` 角色访问。`GET /feedback/queue` 同时返回全队列 SLA 摘要：待处理数、已结案数、待办归因分布、最久等待小时数、SLA 时限、逾期数和未分派数。`PATCH /feedback/{feedback_id}/assignment` 以 `{"owner":"账号"}` 分派待办；结案请求的 `outcome` 必须为 `golden_dataset`、`knowledge_engineering`、`retrieval_tuning` 或 `dismissed`。所有分派和结案动作写入只追加的审计文件，实际修改金标集或知识库仍须由人工单独执行。

# 企业智能办公助手平台 — 项目简历描述

## 项目简介

基于 **LangGraph + DeepSeek** 构建的企业级 Multi-Agent 智能办公平台。采用 LangGraph StateGraph 实现 Agent 状态管理与工作流编排，集成**智能对话、RAG 知识问答 (BGE Reranker)、数据分析报表、OA/CRM 系统对接、企业 SSO/LDAP 认证、多模态分析、网络搜索**等核心能力。通过自然语言交互实现复杂办公任务自动化，将跨系统报表生成从 **3-4 小时缩短至 5 分钟**，RAG 检索 NDCG **0.95+**，支持 **50+ 并发**。

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端框架 | FastAPI 0.136 + Uvicorn 0.48 |
| Agent 引擎 | LangGraph 1.2 + LangChain 1.3 + bind_tools |
| LLM | DeepSeek (Chat / Reasoner) |
| Embedding | BGE-Small-ZH v1.5 (512维) |
| 重排序 | BGE-Reranker-v2-m3 Cross-Encoder (~100ms) |
| 向量存储 | pgvector (HNSW) / ChromaDB 双后端 |
| 前端 | React 18 + Vite + Tailwind CSS v4 + Zustand + TypeScript |
| 认证 | JWT + LDAP3 + OAuth2/OIDC 三合一混合模式 |
| 数据库 | MySQL 8.0 + Redis 8.0 + SQLite (checkpoint) |
| 搜索引擎 | BM25 (jieba 分词) + ChromaDB 向量 + RRF 融合 |
| 工程化 | Docker Compose · pytest 9.0 · Git |

## 核心亮点

### 1. Multi-Agent 协作引擎
- **双路径 Agent**: 本地规则分类 (>90%命中) → simple_react (bind_tools 工具调用) / plan → execute (asyncio.gather 分层并行) → aggregate
- **Supervisor 模式**: 关键词分解 (>90%) → 4 Agent 并行 → 单Agent 直返/多Agent LLM 汇总
- **Human-in-the-Loop**: asyncio.Event 异步等待审批，不阻塞事件循环，120s 超时自动拒绝
- **反思重试**: 失败自动分析 + 指数退避 + 熔断保护

### 2. RAG 知识检索系统
- **混合检索**: BM25 (jieba) + ChromaDB MMR 向量 + RRF 融合 (k=60)
- **BGE Reranker**: Cross-Encoder 本地推理 ~100ms，替代 20 次 LLM API 调用
- **自适应查询扩展**: 按问题复杂度 1/2/3 变体，省 60% Token
- **反幻觉生成**: 强约束 Prompt + 严格来源追溯 + Agentic 自验证循环
- **三级 RAG**: Adaptive (3级自适应) · Agentic (幻觉检测→重检索) · GraphRAG (实体关系多跳推理)
- **语义缓存**: Redis + 本地双缓存，精确匹配 + 向量余弦相似度 (>0.92)
- **增量 BM25**: 新增文档增量追加索引，避免全量重建

### 3. 插件化工具系统
- `@register_tool` 装饰器自动注册，6 个内置工具开箱即用
- data_analyzer: Excel/CSV → 清洗 → 统计 → 图表 (bar/line/pie/scatter) → Word 报告
- oa_query / crm_query: Mock/Real 双模式，API 不可用自动降级
- knowledge_search: 完整 RAG 链路，异步自动适配事件循环
- web_search: DuckDuckGo 免费搜索，失败降级搜索链接
- image_analyzer: PIL + pytesseract OCR → LLM 多模态分析

### 4. 企业级认证
- **本地**: JWT + SHA-256 密码哈希 + 内存用户存储
- **LDAP**: ldap3 连接 AD/OpenLDAP，cn 模板匹配，5s 超时
- **OIDC**: Authorization Code Flow + PKCE，支持 Keycloak/Okta/Azure AD
- **SSO 映射**: MySQL (sso_user_map) + 内存双存储，首次登录自动创建本地用户
- **动态 Provider**: GET /auth/providers 返回可用认证方式，前端自适应渲染

### 5. 工程优化
- **令牌桶限流**: 30 req/s (burst 60)，按 IP 限流，健康检查免限
- **模型预热**: lifespan 中 executor 线程预加载 BGE + Reranker，避免首次请求阻塞
- **线程安全**: embedder 双检锁 + Reranker 懒加载
- **对话压缩**: >8 条消息自动 LLM 摘要，省 60-70% 上下文 Token
- **SqliteSaver → MemorySaver**: 支持 async stream，开发环境零配置
- **单入口**: `main.py` 唯一入口，PyCharm 直接识别 FastAPI

## 量化指标

| 指标 | 数值 |
|------|:----:|
| 简单问答延迟 | < 1s |
| RAG 检索延迟 | ~200ms |
| 重排序延迟 | ~100ms (本地) |
| RAG NDCG | 0.95+ |
| 查询缓存命中率 | +30% (语义匹配) |
| Token 节省 | -60% (本地路由 + 对话压缩) |
| 并发支持 | 50+ (令牌桶 30 req/s) |
| API 端点 | 44 routes · 6 模块 |
| 前端页面 | 8 pages · 20+ components |
| 工具数量 | 6 个内置工具 |
| Agent 模式 | 4 种 (simple_react / plan-execute / multi_agent / human_loop) |
| RAG 模式 | 5 种 (standard / adaptive / agentic / graphrag / smart) |
| 测试覆盖 | 骨架 + Agent + RAG + 工具 |

## 开发周期

2 周 · 独立完成 · Python 55 文件 + React 21 文件 · 100% 功能覆盖

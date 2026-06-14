# 企业智能办公助手平台

[![Python](https://img.shields.io/badge/Python-3.12+-blue)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.136-009688)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-1.2-orange)](https://github.com/langchain-ai/langgraph)
[![React](https://img.shields.io/badge/React-18-61DAFB)](https://react.dev/)
[![DeepSeek](https://img.shields.io/badge/LLM-DeepSeek-536DFE)](https://deepseek.com/)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

基于 **LangGraph + DeepSeek** 的 Multi-Agent 企业智能办公平台。集成智能对话、RAG 知识问答、数据分析、OA/CRM 对接、企业 SSO、多模态分析等核心能力，通过自然语言交互实现复杂办公任务自动化。

---

## 系统架构

```
React 18 (Vite + Tailwind v4 + Zustand)
        │ HTTP/SSE
        ▼
FastAPI 网关 — JWT认证 · 令牌桶限流 · CORS · 请求日志
        │
┌───────┴─────────────────────────────────┐
│         LangGraph Agent 引擎             │
│  ┌─────────┐  ┌────────┐  ┌──────────┐  │
│  │ classify │→│ simple │→│ END       │  │
│  │ (路由)   │  │ _react  │            │  │
│  │          │→│ plan   │→│ execute  │  │
│  │          │  │ (拆解) │  │ (并行)   │  │
│  └─────────┘  └────────┘  └────┬─────┘  │
│                           ↓            │
│                    aggregate → END      │
│  ┌──────────────────────────────────┐   │
│  │ Supervisor → 4 Agent 并行         │   │
│  │ Human-in-the-Loop 异步审批        │   │
│  └──────────────────────────────────┘   │
└──────────────────────────────────────────┘
        │
┌───────┴──────────────────────────────────┐
│              工具执行层                    │
│  data_analyzer · oa_query · crm_query    │
│  knowledge_search · web_search           │
│  image_analyzer (OCR+LLM)                │
└───────┬──────────────────────────────────┘
        │
┌───────┴──────────────────────────────────┐
│              基础设施层                    │
│  pgvector/ChromaDB · BGE-Small-ZH        │
│  BGE-Reranker-v2-m3 · Redis · MySQL      │
│  SQLite (checkpoint) · 语义查询缓存       │
└──────────────────────────────────────────┘
```

## 项目结构

```
├── main.py                     # 唯一入口 — FastAPI app + uvicorn 启动
├── requirements.txt            # Python 依赖
├── docker-compose.yml          # 一键启动所有服务
├── Dockerfile                  # 应用容器镜像
├── .env.example                # 环境变量模板
│
├── app/                        # 后端 (FastAPI)
│   ├── agent/                  # LangGraph Agent 引擎
│   │   ├── graph.py            #   工作流编译 + MemorySaver
│   │   ├── router.py           #   任务分类 (本地规则优先 → LLM兜底)
│   │   ├── planner.py          #   复杂任务 LLM 拆解
│   │   ├── executor.py         #   分层并行 + 反思重试
│   │   ├── aggregator.py       #   多结果聚合
│   │   ├── multi_agent.py      #   Supervisor → 4 Agent 异步并行
│   │   ├── human_loop.py       #   敏感操作审批 (asyncio.Event)
│   │   ├── reflection.py       #   失败分析 + 指数退避
│   │   ├── fallback.py         #   规则引擎降级
│   │   └── state.py            #   AgentState 定义
│   ├── rag/                    # RAG 知识检索系统
│   │   ├── retriever.py        #   BM25+向量+RRF → BGE Reranker → 反幻觉
│   │   ├── embedder.py         #   BGE-Small-ZH (线程安全懒加载)
│   │   ├── splitter.py         #   5 策略智能分块 (PDF/Word/Excel/代码/通用)
│   │   ├── loader.py           #   通用文档加载器
│   │   ├── indexer.py          #   批量索引
│   │   ├── store.py            #   pgvector/ChromaDB 双后端
│   │   ├── cache.py            #   语义查询缓存 (精确+向量相似度)
│   │   ├── advanced.py         #   Adaptive/Agentic/GraphRAG
│   │   └── pgvector_store.py   #   PostgreSQL+pgvector HNSW
│   ├── auth/                   # 企业认证模块
│   │   ├── ldap.py             #   LDAP/AD 域认证 (ldap3)
│   │   ├── oidc.py             #   OAuth2/OIDC SSO (Keycloak/Okta/Azure AD)
│   │   └── sso_mapping.py      #   SSO→本地用户映射 (MySQL+内存)
│   ├── tools/                  # 插件化工具系统
│   │   ├── base.py             #   工具注册表 (@register_tool)
│   │   ├── data_analyzer.py    #   Excel/CSV → 统计 → 图表 → Word 报告
│   │   ├── oa_crm.py           #   OA/CRM Mock/Real 双模式
│   │   ├── knowledge_search.py #   RAG 检索工具
│   │   ├── web_search.py       #   DuckDuckGo 网络搜索
│   │   └── image_analyzer.py   #   图片 OCR + LLM 多模态分析
│   ├── api/                    # REST API 路由
│   │   ├── chat.py             #   对话 + SSE 流式 + 历史 + 审批 + 图片
│   │   ├── auth.py             #   登录/注册/LDAP/OIDC/Providers
│   │   ├── knowledge.py        #   文档上传/删除/索引/问答
│   │   ├── monitoring.py       #   LLMOps 统计面板
│   │   ├── eval.py             #   评测 API
│   │   └── tools.py            #   工具列表/测试
│   ├── memory/                 # 三级记忆存储 (Redis/本地/MySQL)
│   ├── eval/                   # 自动化评测 (RAG 10题 + Agent 5题)
│   ├── models/                 # ORM + Pydantic 模型
│   └── config.py               # 全局配置 (环境变量)
│
├── frontend-react/             # 前端 (React 18 + TypeScript)
│   └── src/
│       ├── pages/              # 8 个页面
│       │   ├── ChatPage.tsx    #   智能对话 (主)
│       │   ├── HistoryPage.tsx #   会话历史
│       │   ├── ToolsPage.tsx   #   工具测试
│       │   ├── KnowledgePage.tsx # 知识库管理
│       │   ├── MonitoringPage.tsx # 监控面板
│       │   ├── EvalPage.tsx    #   自动化评测
│       │   ├── SettingsPage.tsx #  偏好设置
│       │   └── LoginPage.tsx   #   多入口登录 (本地/LDAP/OIDC)
│       ├── components/         # 共享组件
│       ├── stores/             # Zustand 状态管理
│       └── lib/                # API 客户端 + 工具函数
│
├── scripts/                    # SQL 初始化脚本
└── tests/                      # pytest 测试
```

## 快速开始

### 前提条件

- Python 3.12+ · Node.js 18+ · Docker
- DeepSeek API Key ([申请](https://platform.deepseek.com/))

### 1. 配置

```bash
cp .env.example .env
# 编辑 .env: 填入 LLM_API_KEY (DeepSeek)
# 国内用户: HF_ENDPOINT=https://hf-mirror.com (加速模型下载)
```

### 2. 启动基础设施

```bash
docker-compose up -d redis mysql chromadb
# 可选: docker-compose up -d postgres (pgvector)
```

### 3. 安装依赖

```bash
python -m venv .venv && .venv\Scripts\activate   # Windows
pip install -r requirements.txt
```

### 4. 启动

```bash
# 后端 (终端1)
python main.py                        # → http://localhost:8000

# 前端 (终端2)
cd frontend-react && npm install && npm run dev  # → http://localhost:5173
```

### 5. 访问

| 入口 | 地址 |
|------|------|
| 前端界面 | http://localhost:5173 |
| API Swagger | http://localhost:8000/docs |
| 健康检查 | http://localhost:8000/api/health |
| API 根路径 | http://localhost:8000/ |

默认账户: `admin` / `admin123` · `demo` / `demo123`

## 核心功能

| 功能 | 说明 |
|------|------|
| **智能对话** | LangGraph 双路径 Agent + bind_tools 工具调用 + SSE 流式输出 |
| **RAG 知识问答** | BM25+向量+RRF 混合检索 → BGE Reranker v2-m3 重排序 → 反幻觉生成 → 来源追溯 |
| **智能 RAG** | Adaptive (3级自适应) / Agentic (自验证循环) / GraphRAG (多跳推理) |
| **数据分析** | Excel/CSV 读取 → 清洗 → 统计 → 图表 → Word 报告自动生成 |
| **OA/CRM 对接** | Mock/Real 双模式，API 不可用时自动降级 |
| **企业 SSO** | 本地 + LDAP/AD 域认证 + OAuth2/OIDC 单点登录 (三合一) |
| **多 Agent 协作** | Supervisor → 4 Agent asyncio.gather 并行，单Agent 直返/多Agent LLM 汇总 |
| **多模态分析** | 图片上传 → OCR 文字提取 → LLM 分析 (图表/文档/截图) |
| **网络搜索** | DuckDuckGo 实时搜索，补充知识库外部信息 |
| **人工审批** | 敏感操作前 asyncio.Event 异步等待，不阻塞事件循环 |
| **流式输出** | SSE `astream_events` 实时推送 token + 工具调用状态 |
| **对话评分** | 1-5 星评价 + LLMOps 统计 |
| **监控面板** | API 调用量/延迟/错误率/工具排名/评分统计 |
| **自动化评测** | RAG 10题 (准确率+召回率) + Agent 5题 (工具路由准确率) |
| **三级记忆** | Redis(热) → 本地内存(温) → MySQL(冷) 异步持久化 |
| **会话历史** | 搜索/恢复/删除历史对话，长对话自动摘要压缩 |
| **查询缓存** | Redis + 本地双缓存，精确匹配 + 向量相似度语义匹配 |
| **速率限制** | 令牌桶 30 req/s，按 IP 限流 |

## 技术栈

| 层级 | 技术 |
|------|------|
| **Agent 框架** | LangGraph 1.2, LangChain 1.3, ReAct, bind_tools |
| **LLM** | DeepSeek (Chat / Reasoner) |
| **Embedding** | BGE-Small-ZH v1.5 (512维, 线程安全懒加载) |
| **重排序** | BGE-Reranker-v2-m3 Cross-Encoder (~100ms, FlagEmbedding) |
| **向量存储** | pgvector (PostgreSQL + HNSW) / ChromaDB (自动回退) |
| **后端** | FastAPI 0.136, Uvicorn 0.48, Pydantic 2.13 |
| **前端** | React 18 + Vite + Tailwind CSS v4 + Zustand + TypeScript |
| **认证** | JWT + LDAP3 + OAuth2/OIDC (混合模式) |
| **数据库** | MySQL 8.0 (SQLAlchemy 2.0), Redis 8.0, SQLite (checkpoint) |
| **数据处理** | Pandas 3.0, Matplotlib, openpyxl, python-docx |
| **工程化** | Docker Compose, pytest 9.0, Git |

## 性能指标

| 指标 | 数值 | 说明 |
|------|:----:|------|
| 简单问答 | <1s | 本地规则路由 + DeepSeek |
| RAG 检索 | ~200ms | 混合检索 + BGE Reranker |
| 重排序速度 | ~100ms | Cross-Encoder 本地推理 |
| Embedding | ~10ms | BGE-Small CPU 推理 |
| 查询扩展 | 自适应 1-3 变体 | 按问题复杂度 |
| Token 节省 | -60% | 本地规则优先 + 对话压缩 |
| 速率限制 | 30 req/s | 令牌桶, burst 60 |

## 环境变量

完整配置见 `.env.example`，关键项:

| 变量 | 说明 | 必填 |
|------|------|:----:|
| `LLM_API_KEY` | DeepSeek API Key | ✅ |
| `LLM_MODEL` | deepseek-chat / deepseek-reasoner | - |
| `REDIS_URL` | Redis 连接字符串 | ✅ |
| `MYSQL_*` | MySQL 连接信息 | - |
| `HF_ENDPOINT` | HuggingFace 镜像 (国内: https://hf-mirror.com) | 国内建议 |
| `LDAP_ENABLED` | 启用 LDAP 域认证 | - |
| `OIDC_ENABLED` | 启用 OIDC SSO | - |
| `PG_*` | PostgreSQL+pgvector 连接 (可选) | - |

## 测试

```bash
pytest tests/ -v
pytest tests/ --cov=app --cov-report=html
```

## Docker 部署

```bash
# 构建 (国内预下载模型)
docker build --build-arg HF_ENDPOINT=https://hf-mirror.com -t eao-backend .

# 一键启动
docker-compose up -d

# 查看日志
docker-compose logs -f backend

# 停止
docker-compose down
```

## 参考项目

- [LangGraph](https://github.com/langchain-ai/langgraph) — Agent 状态图框架
- [DATAGEN](https://github.com/starpig1129/DATAGEN) — 多 Agent 数据分析
- [FlagEmbedding](https://github.com/FlagOpen/FlagEmbedding) — BGE 模型系列
- [RAGFlow](https://github.com/infiniflow/ragflow) — 分块策略参考
- [Dify](https://github.com/langgenius/dify) — LLMOps 设计参考

## License

MIT

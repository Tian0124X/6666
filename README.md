# 🤖 基于 Agent 的企业智能办公助手平台

[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://www.python.org/)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.3-orange.svg)](https://github.com/langchain-ai/langgraph)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688.svg)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-18-61DAFB.svg)](https://react.dev/)
[![DeepSeek](https://img.shields.io/badge/LLM-DeepSeek-536DFE.svg)](https://deepseek.com/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

面向企业员工的智能办公平台，基于 **LangGraph + LangChain** 与 **DeepSeek** 构建 Multi-Agent 协作架构。集成智能对话、RAG 知识问答、数据分析、OA/CRM 对接、企业 SSO 等核心能力。

---

## 🏗 系统架构

```
用户 (React 18 + Vite + Tailwind v4 + Zustand)
            │
            ▼
    FastAPI 网关 + 令牌桶限流 + JWT 认证
            │
    ┌───────┴──────────┐
    │  LangGraph Agent  │  ← SqliteSaver checkpoint 持久化
    │  编排引擎          │
    ├──────────────────┤
    │ classify (路由)    │
    │ plan    (LLM 拆解) │
    │ execute (并行执行)  │
    │ aggregate (聚合)   │
    │ simple_react (问答) │
    │ multi_agent (4并行) │
    └───────┬──────────┘
            │
    ┌───────┴──────────────────────────┐
    │           工具执行层               │
    ├───────────────────────────────────┤
    │ 📊 data_analyzer  数据分析+报告    │
    │ 🔗 oa_query       OA 审批查询     │
    │ 👤 crm_query      客户信息检索     │
    │ 📚 knowledge_search 知识库 RAG    │
    │ 🌐 web_search     网络搜索        │
    │ 📷 image_analyzer 图片 OCR+分析   │
    └───────┬──────────────────────────┘
            │
    ┌───────┴──────────────────────────┐
    │           基础设施层              │
    ├───────────────────────────────────┤
    │ pgvector / ChromaDB  向量检索     │
    │ BGE-Small-ZH         Embedding    │
    │ BGE-Reranker-v2-m3   重排序       │
    │ Redis                三级记忆     │
    │ MySQL                持久化存储    │
    │ SQLite               Checkpoint   │
    └──────────────────────────────────┘
```

## 📁 项目结构

```
enterprise-ai-office/
├── README.md                          # 本文件
├── tech-doc-enterprise-ai-office.md    # 从零开发技术文档（10章）
├── docker-compose.yml                 # 一键启动所有服务
├── Dockerfile                         # 应用镜像
├── requirements.txt                   # Python 依赖
├── .env.example                       # 环境变量模板
├── app/                               # FastAPI 后端
│   ├── agent/                         # LangGraph Agent 引擎
│   │   ├── graph.py                   #   工作流编译 + checkpoint
│   │   ├── router.py                  #   任务分类路由
│   │   ├── planner.py                 #   复杂任务拆解
│   │   ├── executor.py                #   并行工具执行
│   │   ├── aggregator.py              #   多结果聚合
│   │   ├── multi_agent.py             #   Supervisor → 4 Agent 并行
│   │   ├── human_loop.py              #   敏感操作审批 (asyncio.Event)
│   │   ├── reflection.py              #   反思重试
│   │   ├── fallback.py                #   规则引擎降级
│   │   └── state.py                   #   AgentState 定义
│   ├── rag/                           # RAG 知识问答系统
│   │   ├── retriever.py               #   混合检索 (BM25+向量+RRF)
│   │   ├── embedder.py                #   BGE-Small-ZH 向量化
│   │   ├── splitter.py                #   5 策略智能分块
│   │   ├── loader.py                  #   通用文档加载器
│   │   ├── indexer.py                 #   批量索引
│   │   ├── store.py                   #   pgvector/ChromaDB 双后端
│   │   ├── cache.py                   #   查询缓存
│   │   └── advanced.py                #   Adaptive/Agentic/GraphRAG
│   ├── tools/                         # 插件化工具系统
│   │   ├── base.py                    #   工具注册表
│   │   ├── data_analyzer.py           #   数据分析 + 报告生成
│   │   ├── oa_crm.py                  #   OA/CRM Mock/Real 双模式
│   │   ├── knowledge_search.py        #   RAG 知识检索工具
│   │   ├── web_search.py              #   DuckDuckGo 网络搜索
│   │   └── image_analyzer.py          #   图片 OCR + LLM 分析
│   ├── auth/                          # 认证模块
│   │   ├── ldap.py                    #   LDAP/AD 域认证
│   │   ├── oidc.py                    #   OAuth2/OIDC SSO
│   │   └── sso_mapping.py             #   SSO → 本地用户映射
│   ├── memory/                        # 三级记忆存储
│   ├── eval/                          # 自动化评测
│   │   ├── rag_eval.py                #   RAG 10 题评测
│   │   └── agent_eval.py              #   Agent 5 题工具路由评测
│   ├── models/                        # 数据模型 (ORM + Pydantic)
│   └── api/                           # RESTful API 路由
│       ├── chat.py                    #   对话 + SSE 流式 + 图片
│       ├── auth.py                    #   登录/注册/SSO/LDAP/OIDC
│       ├── knowledge.py               #   知识库 CRUD + 问答
│       ├── monitoring.py              #   LLMOps 监控面板
│       ├── eval.py                    #   评测 API
│       └── tools.py                   #   工具测试
├── frontend-react/                    # React 18 前端
│   └── src/
│       ├── pages/                     #   8 个页面
│       │   ├── ChatPage.tsx           #     智能对话 (主)
│       │   ├── HistoryPage.tsx        #     会话历史
│       │   ├── ToolsPage.tsx          #     工具测试
│       │   ├── KnowledgePage.tsx      #     知识库管理
│       │   ├── MonitoringPage.tsx     #     监控面板
│       │   ├── EvalPage.tsx           #     自动化评测
│       │   ├── SettingsPage.tsx       #     偏好设置
│       │   └── LoginPage.tsx          #     多入口登录
│       ├── stores/                    #   Zustand 状态管理
│       └── components/                #   共享组件
├── scripts/                           # SQL 初始化脚本
└── tests/                             # pytest 测试
```

## 🚀 快速开始

### 前提条件

- Python 3.12+
- Node.js 18+ (前端)
- Docker & Docker Compose (基础设施)
- DeepSeek API Key ([申请](https://platform.deepseek.com/))

### 1. 配置环境

```bash
cp .env.example .env
# 编辑 .env，填入 LLM_API_KEY (DeepSeek)
```

### 2. 启动基础设施

```bash
docker-compose up -d redis mysql chromadb
```

### 3. 安装后端依赖

```bash
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
# 重排序模型（可选但有显著加速）
pip install FlagEmbedding
```

### 4. 启动服务

```bash
# 终端 1: 后端
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 终端 2: 前端
cd frontend-react && npm install && npm run dev
```

### 5. 访问

| 入口 | 地址 |
|------|------|
| 前端界面 | http://localhost:5173 |
| API Swagger | http://localhost:8000/docs |
| 健康检查 | http://localhost:8000/api/health |

默认账户: `admin` / `admin123` · `demo` / `demo123`

---

## 🎯 核心功能

| 功能 | 说明 | 状态 |
|------|------|:----:|
| 💬 智能对话 | LangGraph 双路径 Agent + bind_tools 工具调用 + SSE 流式 | ✅ |
| 📚 RAG 知识问答 | 混合检索(BM25+向量+RRF) → BGE Reranker → 反幻觉生成 → 来源追溯 | ✅ |
| 🧠 智能 RAG | Adaptive RAG (3级) + Agentic RAG (自验证) + GraphRAG (多跳推理) | ✅ |
| 📊 数据分析 | Excel/CSV 读取 → 统计 → 图表 → Word 报告生成 | ✅ |
| 🔗 OA/CRM 对接 | Mock/Real 双模式，外部 API 不可用时自动降级 | ✅ |
| 🔐 企业 SSO | 本地登录 + LDAP/AD 域认证 + OAuth2/OIDC 单点登录 (混合模式) | ✅ |
| 👥 多 Agent 协作 | Supervisor → 4 Agent 并行，LLM 汇总结果 | ✅ |
| 🖼️ 多模态 | 图片上传 → OCR 提取 → LLM 分析 (图表/文档/截图) | ✅ |
| 🌐 网络搜索 | DuckDuckGo 实时搜索，补充知识库外部信息 | ✅ |
| 🔄 流式输出 | SSE `astream_events` 实时推送 token 级内容 + 工具调用状态 | ✅ |
| 🛡️ 降级兜底 | LLM 失败→规则引擎 / Redis 宕机→内存 / API 不可用→Mock | ✅ |
| 🔁 反思重试 | 失败自动分析 + 指数退避 + 熔断保护 | ✅ |
| ✋ 人工审批 | 敏感操作 (删除/执行/付费) 前暂停 Agent 等待审批 | ✅ |
| ⭐ 对话评分 | 1-5 星评价 + LLMOps 统计 | ✅ |
| 📈 监控面板 | API 调用量、延迟、工具排名、评分统计 | ✅ |
| 🧪 自动化评测 | RAG 10 题 + Agent 5 题，含准确率和召回率 | ✅ |
| 💾 三級记忆 | Redis(热) → 本地内存(温) → MySQL(冷) 异步持久化 | ✅ |
| 📝 会话历史 | 搜索/恢复/删除历史对话，checkpoint 持久化 | ✅ |
| 🧩 5 策略分块 | PDF/Word/Excel/代码/通用，RAGFlow 风格模板化 | ✅ |
| 🚦 速率限制 | 令牌桶 30 req/s，防滥用 | ✅ |

---

## 🛠 技术栈

| 层级 | 技术 |
|------|------|
| **Agent 框架** | LangGraph 1.x, LangChain, ReAct, bind_tools |
| **大模型** | DeepSeek (Chat / Reasoner) |
| **向量检索** | BGE-Small-ZH (Embedding), BGE-Reranker-v2-m3 (重排序) |
| **向量存储** | pgvector (主力) + ChromaDB (回退) |
| **后端** | FastAPI, Redis, MySQL, SQLite (checkpoint) |
| **前端** | React 18 + Vite + Tailwind CSS v4 + Zustand |
| **SSO** | LDAP3 + OAuth2/OIDC (Keycloak/Okta/Azure AD) |
| **数据处理** | Pandas, Matplotlib, openpyxl, python-docx |
| **工程化** | Docker, pytest, Swagger, TypeScript |

## 📊 技术指标

| 指标 | 目标 | 实测 |
|------|:----:|:----:|
| 简单问答延迟 | < 2s | ~1.5s |
| RAG 检索延迟 | < 500ms | ~200ms (含 Reranker) |
| 重排序速度 | — | ~100ms (BGE Reranker) |
| RAG 准确率 | ≥ 85% | NDCG 0.95+ |
| 并发用户 | 50+ | — |
| 核心链路可用性 | 99.9% | — |
| 任务自愈率 | > 60% | — |
| 速率限制 | — | 30 req/s (burst 60) |

## 🔍 运行测试

```bash
pytest tests/ -v
pytest tests/ --cov=app --cov-report=html
```

## 📦 生产部署

```bash
docker-compose up -d

# 查看日志
docker-compose logs -f backend

# 停止
docker-compose down
```

## 🔑 环境变量

完整配置见 `.env.example`。关键配置项：

| 变量 | 说明 | 必填 |
|------|------|:----:|
| `LLM_API_KEY` | DeepSeek API Key | ✅ |
| `LLM_MODEL` | deepseek-chat / deepseek-reasoner | - |
| `REDIS_URL` | Redis 连接 | ✅ |
| `LDAP_ENABLED` | 启用 LDAP 域认证 | - |
| `OIDC_ENABLED` | 启用 OIDC SSO | - |

## 🤝 参考项目

- [DATAGEN](https://github.com/starpig1129/DATAGEN) — LangGraph 多 Agent 数据分析 (1.7k⭐)
- [agentflow](https://github.com/Aparnap2/agentflow) — LangGraph 虚拟办公室
- [ai-assistant-hub-langgraph](https://github.com/JoshPola96/ai-assistant-hub-langgraph) — Streamlit + ChromaDB 多 Agent 助手
- [deep-research-agent](https://github.com/tarun7r/deep-research-agent) — 多 Agent 深度研究系统
- [FlagEmbedding](https://github.com/FlagOpen/FlagEmbedding) — BGE Reranker
- [RAGFlow](https://github.com/infiniflow/ragflow) — 分块策略参考

## 📄 License

MIT License

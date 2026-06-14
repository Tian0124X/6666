# 企业智能办公助手平台

基于 **LangGraph + DeepSeek** 的 Multi-Agent 智能办公平台。集成对话、RAG 知识问答、数据分析、OA/CRM、SSO 认证、多模态分析。

## 技术栈

| 层级 | 技术 |
|------|------|
| Agent | LangGraph 1.2 + LangChain 1.3 |
| LLM | DeepSeek (Chat / Reasoner) |
| 后端 | FastAPI + Redis + MySQL + ChromaDB/pgvector |
| 前端 | React 18 + Vite + Tailwind v4 + Zustand |
| 检索 | BGE-Small-ZH + BGE-Reranker-v2-m3 + BM25 + RRF |
| 认证 | JWT + LDAP + OAuth2/OIDC |

## 快速开始

```bash
cp .env.example .env          # 填入 LLM_API_KEY
docker-compose up -d redis mysql chromadb
pip install -r requirements.txt
python main.py                # → http://localhost:8000
cd frontend-react && npm install && npm run dev  # → http://localhost:5173
```

默认账户: `admin` / `admin123` · `demo` / `demo123`

## 项目结构

```
├── main.py                    # 唯一入口
├── app/
│   ├── agent/                 # LangGraph 引擎 (双路径 + 多Agent + 审批)
│   ├── rag/                   # RAG 检索 (混合检索 + Reranker + 三级RAG)
│   ├── tools/                 # 6 工具 (数据分析/OA/CRM/知识库/搜索/图片)
│   ├── auth/                  # SSO (LDAP + OIDC)
│   ├── api/                   # 6 路由模块
│   ├── memory/                # 三级记忆 (Redis/本地/MySQL)
│   └── eval/                  # 自动化评测
├── frontend-react/            # React 前端 (8 页面)
└── tests/                     # pytest
```

## 项目亮点

- **本地规则优先** — 路由分类 + 多Agent 分解 90%+ 走本地规则，省 LLM Token 60%
- **BGE Reranker** — Cross-Encoder 本地推理 ~100ms，替代 20 次串行 LLM API
- **自适应查询扩展** — 按问题复杂度 1/2/3 变体，简单问题不浪费检索
- **异步审批** — asyncio.Event 非阻塞等待，不卡事件循环
- **语义缓存** — 精确匹配 + 向量余弦相似度 (>0.92)，相似问题命中
- **对话压缩** — 长对话自动 LLM 摘要，省 60-70% 上下文 Token
- **模型预热** — lifespan 后台线程预加载，首次请求不阻塞
- **三合一认证** — 本地 + LDAP + OIDC 混合模式，动态 Provider
- **双向量后端** — pgvector (HNSW) + ChromaDB 自动回退
- **令牌桶限流** — 30 req/s 按 IP，健康检查免限

## 核心功能

- **智能对话** — LangGraph 双路径 + bind_tools + SSE 流式
- **RAG 问答** — BM25+向量+RRF → BGE Reranker → 反幻觉 → 来源追溯
- **多 Agent** — Supervisor → 4 Agent asyncio.gather 并行
- **数据分析** — Excel/CSV → 统计 → 图表 → Word 报告
- **企业 SSO** — 本地 + LDAP + OIDC 三合一
- **多模态** — 图片 OCR → LLM 分析
- **速率限制** — 令牌桶 30 req/s

## 环境变量

```bash
LLM_API_KEY=sk-xxx              # DeepSeek (必填)
HF_ENDPOINT=https://hf-mirror.com  # 国内镜像
LDAP_ENABLED=false              # 企业域认证
OIDC_ENABLED=false              # 单点登录
```

## License

MIT

# 基于 Agent 的企业智能办公助手平台 — 从零开发技术文档

> **适用版本**: Python 3.12+ | 文档更新: 2026-06-14 | 版本: v1.0.0

---

## 目录

1. [项目概述与需求分析](#1-项目概述与需求分析)
2. [技术选型与架构设计](#2-技术选型与架构设计)
3. [开发环境搭建](#3-开发环境搭建)
4. [Multi-Agent 核心引擎](#4-multi-agent-核心引擎)
5. [RAG 知识问答系统](#5-rag-知识问答系统)
6. [插件化工具系统](#6-插件化工具系统)
7. [三级记忆存储与会话管理](#7-三级记忆存储与会话管理)
8. [反思重试与自愈机制](#8-反思重试与自愈机制)
9. [前后端服务实现](#9-前后端服务实现)
10. [测试、部署与运维](#10-测试部署与运维)

---

## 1. 项目概述与需求分析

### 1.1 业务背景

中大型企业的日常办公涉及大量重复性信息处理工作：

| 场景 | 传统方式耗时 | 痛点 |
|------|-------------|------|
| 跨部门销售数据报表 | 3~4 小时 | 需手动从 CRM 导出、Excel 清洗、制图、写报告 |
| 查找公司制度/产品文档 | 10~30 分钟 | 文档分散在多个系统，关键词搜索效率低 |
| OA 审批流程查询 | 5~15 分钟 | 需登录多个系统查看状态 |
| 新人入职问答 | 反复人工回答 | 相同问题被不同人问数十遍 |

**核心假设**：通过自然语言交互 + AI Agent 自动编排工具调用，可将上述事务的处理时间缩短 **90% 以上**。

### 1.2 目标用户画像

- **一线员工**：查制度、问流程、生成常规数据报表
- **中层管理者**：跨部门数据分析、自动生成汇报材料
- **IT/运维**：通过工具扩展平台能力，按需接入新系统

### 1.3 功能需求（按优先级）

| 优先级 | 功能 | 说明 |
|--------|------|------|
| **P0** | 智能对话 | 基于 LangGraph 双路径 Agent + bind_tools 工具调用 + SSE 流式 |
| **P0** | RAG 知识问答 | 混合检索(BM25+向量+RRF) → BGE Reranker → 反幻觉生成 |
| **P0** | 数据分析 + 报告生成 | 上传 Excel/CSV，自动分析并生成 Word 报告 |
| **P1** | OA/CRM 对接 | 查审批状态、客户信息（Mock/Real 双模式） |
| **P1** | 多用户会话隔离 | JWT 认证 + 不同用户独立会话上下文 |
| **P1** | 企业 SSO/LDAP | LDAP/AD 域认证 + OAuth2/OIDC 单点登录 (混合模式) |
| **P1** | 多 Agent 协作 | Supervisor → 4 Agent 并行，LLM 汇总 |
| **P2** | 流式输出 | SSE astream_events 实时推送 token + 工具状态 |
| **P2** | 多模态 | 图片上传 → OCR 提取 → LLM 分析 |
| **P2** | 网络搜索 | DuckDuckGo 实时搜索补充外部信息 |
| **P2** | 人工审批 | 敏感操作前 asyncio.Event 异步等待审批 |
| **P2** | 自动化评测 | RAG 10 题 + Agent 5 题，准确率/召回率 |
| **P2** | 监控面板 | API 调用量、延迟、工具排名、评分统计 |
| **P2** | 速率限制 | 令牌桶 30 req/s，防滥用 |
| **P2** | 偏好设置 | 用户自定义模型参数、工具开关 |

### 1.4 非功能需求

| 维度 | 指标 | 说明 |
|------|------|------|
| 响应时间 | 简单问答 < 2s，复杂任务 < 5min | 含 LLM 推理 + 工具执行 |
| RAG 准确率 | NDCG 0.95+ | 混合检索 + BGE Reranker v2-m3 |
| 重排序延迟 | < 100ms | Cross-Encoder 本地推理 |
| 可用性 | 核心链路 99.9% | 含降级兜底后 |
| 并发 | 50+ 用户同时在线 | 令牌桶限流 30 req/s |
| 幻觉率 | < 5% | RAG 强约束 + 反幻觉 Prompt |
| 自愈率 | > 60% | 任务失败后自动恢复比例 |

### 1.5 成功指标定义

| 指标 | 测量方法 |
|------|---------|
| 知识问答准确率 | 准备 100 条标注 QA 对，计算正确率 |
| 报表生成时间 | 端到端计时（从用户上传到报告下载） |
| 用户满意度 | 对话结束后弹窗评分（1-5 星） |
| 工具调用成功率 | Agent 发起工具调用 → 工具成功返回的比例 |

---

## 2. 技术选型与架构设计

### 2.1 技术选型对比

#### LLM

| 候选 | 优点 | 缺点 | 结论 |
|------|------|------|------|
| **DeepSeek** | 中文极强、API 兼容 OpenAI、性价比极高 | 高并发需付费扩容 | ✅ 选用 |
| 通义千问 (Qwen) | 中文能力强、API 稳定 | 部分场景推理弱 | 备选 |
| GPT-4 | 推理能力强 | 成本高、网络不稳定 | ❌ |

#### Agent 框架

| 候选 | 优点 | 缺点 | 结论 |
|------|------|------|------|
| **LangGraph** | 状态图原生支持、checkpoint、条件路由 | 学习曲线略陡 | ✅ 选用（Agent 编排） |
| **LangChain** | 生态最全、文档丰富、社区活跃 | 抽象层多、版本变动频繁 | ✅ 选用（工具/LLM 封装） |
| LlamaIndex | RAG 场景优秀 | Agent 能力弱 | ❌ |
| 自研 | 完全可控 | 开发成本极高 | ❌ |

#### 向量数据库

| 候选 | 优点 | 缺点 | 结论 |
|------|------|------|------|
| **pgvector** | PostgreSQL 原生、生产级、SQL 过滤 | 需 PostgreSQL | ✅ 选用（主力） |
| **ChromaDB** | 轻量、零配置、Python 原生 | 大规模性能弱 | ✅ 选用（快速开发） |
| Milvus | 高性能、分布式 | 部署复杂、资源占用大 | 后期迁移 |
| FAISS | 检索极快 | 无持久化、无元数据过滤 | ❌ |

#### 前端

| 候选 | 优点 | 缺点 | 结论 |
|------|------|------|------|
| **React 18 + Vite** | 生态最强、组件丰富、性能好 | 需 Node.js 环境 | ✅ 选用 |
| Streamlit | 纯 Python、极快出 Demo | 不适合复杂 UI | 保留兼容 |
| Gradio | ML 场景友好 | 定制化弱 | ❌ |
| React + FastAPI | 专业 | 开发周期长、需前后端分离 | ❌ |

### 2.2 系统架构

```
┌─────────────────────────────────────────────────────────┐
│                     用户入口层                           │
│   React 18 + Vite (8页: 对话/历史/工具/知识库/监控/评测/设置/登录) │
└──────────────────────┬──────────────────────────────────┘
                       │ HTTP/SSE
┌──────────────────────▼──────────────────────────────────┐
│                   FastAPI 网关层                         │
│   /api/chat  /api/knowledge/qa  /api/tools/analyze      │
│   CORS 中间件 | 异常处理 | 请求日志 | 流式 SSE            │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│                  Agent 编排层 (LangGraph StateGraph)       │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────┐  │
│  │ classify     │  │ plan_node    │  │ reflection     │  │
│  │ (条件路由)    │  │ (LLM 拆解)   │  │ (反思重试)     │  │
│  └──────┬──────┘  └──────┬───────┘  └───────┬────────┘  │
│         │                │                   │           │
│  ┌──────▼────────────────▼───────────────────▼────────┐  │
│  │         LangGraph 工作流 (StateGraph)                │  │
│  │  ┌──────┐   ┌──────┐   ┌──────┐   ┌──────┐        │  │
│  │  │router│──▶│react │──▶│execute│──▶│aggregate│      │  │
│  │  └──┬───┘   └──────┘   └──┬───┘   └──────┘        │  │
│  │     │ 条件边               │ 并行 fan-out            │  │
│  │     ▼                      ▼                        │  │
│  │  simple ─────────────▶ END                          │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                           │
│  ┌─────────────┐                      ┌──────────────┐   │
│  │ LLM 规划器   │ ─── 失败降级 ───▶   │ 规则引擎      │   │
│  │ (DeepSeek)   │                      │ (BM25)         │   │
│  └─────────────┘                      └──────────────┘   │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│                   工具执行层                              │
│  ┌──────────┐  ┌───────────┐  ┌──────────────────────┐  │
│  │DataAnalyzer│  │OA/CRM 连接器│  │  自定义工具 (热插拔)  │  │
│  │ Excel→图表 │  │ Mock/Real  │  │  @tool 装饰器注册   │  │
│  │ →Word报告  │  │ 双模式     │  │  Pydantic 参数校验  │  │
│  └──────────┘  └───────────┘  └──────────────────────┘  │
└──────────────────────────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│                   基础设施层                              │
│  ┌──────────┐  ┌───────────┐  ┌──────────┐             │
│  │ ChromaDB │  │   Redis    │  │  MySQL   │             │
│  │ (向量库)  │  │ (会话缓存)  │  │ (持久化)  │             │
│  └──────────┘  └───────────┘  └──────────┘             │
│  ┌──────────┐  ┌───────────┐                           │
│  │BGE-Small │  │ DeepSeek    │  BGE-Reranker │           │
│  │ (Embed)  │  │  (LLM API) │                           │
│  └──────────┘  └───────────┘                           │
└──────────────────────────────────────────────────────────┘
```

### 2.3 核心数据流

```
用户输入 "分析本月销售数据，和上个月对比，生成报告"
    │
    ▼
路由分类器 ─── 判断为"复杂任务" ───▶ TaskPlanner
    │                                      │
    │                              LLM 生成 DAG:
    │                              1. load_file("sales_2026-06.xlsx")
    │                              2. load_file("sales_2026-05.xlsx")
    │                              (1,2 并行执行)
    │                              3. compare(1.result, 2.result)
    │                              4. generate_chart(3.result)
    │                              5. generate_report(3.result, 4.result)
    │                              (4,5 依赖 3)
    │                                      │
    │                              DAG 拓扑排序 → 并行执行
    │                                      │
    ▼                                      ▼
ReAct Agent ◀──────────────────── 子任务结果聚合
    │
    ▼
流式返回最终回答 + 报告下载链接
```

### 2.4 项目目录结构

```
enterprise-ai-office/
├── docker-compose.yml              # 一键启动所有服务
├── Dockerfile                      # 应用镜像
├── requirements.txt                # Python 依赖
├── .env.example                    # 环境变量模板
├── README.md
│
├── app/                            # 主应用
│   ├── __init__.py
│   ├── main.py                     # FastAPI 入口
│   ├── config.py                   # 配置管理（环境变量读取）
│   │
│   ├── agent/                      # Agent 核心引擎
│   │   ├── __init__.py
│   │   ├── executor.py             # ReAct 执行引擎
│   │   ├── planner.py              # TaskPlanner DAG 拆解
│   │   ├── router.py               # 简单/复杂任务路由
│   │   ├── reflection.py           # 反思重试模块
│   │   └── fallback.py             # 规则引擎降级
│   │
│   ├── rag/                        # RAG 知识问答
│   │   ├── __init__.py
│   │   ├── loader.py               # 多格式文档加载器
│   │   ├── splitter.py             # 文本分块
│   │   ├── embedder.py             # BGE 向量化
│   │   ├── store.py                # ChromaDB 操作
│   │   └── retriever.py            # 检索 + Prompt 模板
│   │
│   ├── tools/                      # 插件化工具系统
│   │   ├── __init__.py
│   │   ├── base.py                 # BaseTool 基类 + 注册中心
│   │   ├── data_analyzer.py        # 数据分析工具
│   │   ├── oa_crm.py               # OA/CRM 对接工具
│   │   └── registry.py             # 工具注册与发现
│   │
│   ├── memory/                     # 记忆存储
│   │   ├── __init__.py
│   │   ├── store.py                # 三级存储实现
│   │   └── session.py              # 会话管理
│   │
│   ├── api/                        # FastAPI 路由
│   │   ├── __init__.py
│   │   ├── chat.py                 # /api/chat
│   │   ├── knowledge.py            # /api/knowledge/*
│   │   └── tools.py                # /api/tools/*
│   │
│   └── models/                     # Pydantic 数据模型
│       ├── __init__.py
│       ├── request.py              # 请求模型
│       └── response.py             # 响应模型
│
├── frontend-react/                 # React 18 + Vite 前端
│   ├── app.py                      # 主入口
│   ├── pages/
│   │   ├── chat.py                 # 智能对话页
│   │   ├── tool_test.py            # 工具测试页
│   │   ├── knowledge.py            # 知识库管理页
│   │   └── settings.py             # 偏好设置页
│   └── components/
│       ├── sidebar.py              # 侧边栏
│       └── chat_display.py         # 对话气泡组件
│
├── tests/                          # 测试
│   ├── test_agent_executor.py
│   ├── test_rag_retriever.py
│   ├── test_tools.py
│   ├── test_memory.py
│   └── conftest.py                 # pytest fixtures
│
└── data/                           # 数据目录（gitignore）
    ├── documents/                  # 上传的文档
    ├── chroma/                     # ChromaDB 持久化
    └── reports/                    # 生成的报告
```

---

## 3. 开发环境搭建

### 3.1 Python 环境

```bash
# 确认 Python 版本
python --version  # Python 3.12.x

# 创建虚拟环境
python -m venv venv

# 激活虚拟环境
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate
```

### 3.2 依赖清单 (requirements.txt)

```
# === Agent 框架 ===
langchain==0.3.20
langchain-community==0.3.19
langchain-core==0.3.45
langgraph==0.3.34

# === LLM ===
# DeepSeek 通过 OpenAI 兼容接口接入
langchain-openai==0.3.12

# === 向量检索 ===
chromadb==0.6.3
sentence-transformers==3.4.1

# === 后端 ===
fastapi==0.115.12
uvicorn[standard]==0.34.2
pydantic==2.11.3
python-multipart==0.0.20
sse-starlette==2.2.1

# === 数据库与缓存 ===
redis==5.2.1
sqlalchemy==2.0.39
pymysql==1.1.1
aiomysql==0.2.0

# === 数据处理 ===
pandas==2.2.3
openpyxl==3.1.5
matplotlib==3.10.1
python-docx==1.1.2

# === 文档解析 ===
PyPDF2==3.0.1
python-docx==1.1.2
xlrd==2.0.1

# === 前端 ===
streamlit==1.44.1

# === 工具 ===
httpx==0.28.1
python-dotenv==1.1.0
tenacity==9.0.0

# === 测试 ===
pytest==8.3.5
pytest-asyncio==0.25.3
pytest-mock==3.14.0
```

安装：

```bash
pip install -r requirements.txt
```

### 3.3 Docker Compose 基础设施

```yaml
# docker-compose.yml
version: '3.8'

services:
  redis:
    image: redis:7-alpine
    container_name: eao-redis
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5

  mysql:
    image: mysql:8.0
    container_name: eao-mysql
    ports:
      - "3306:3306"
    environment:
      MYSQL_ROOT_PASSWORD: eao_root_2026
      MYSQL_DATABASE: enterprise_ai_office
      MYSQL_USER: eao_user
      MYSQL_PASSWORD: eao_pass_2026
    volumes:
      - mysql_data:/var/lib/mysql
      - ./scripts/init.sql:/docker-entrypoint-initdb.d/init.sql
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "localhost"]
      interval: 5s
      timeout: 3s
      retries: 10

  chromadb:
    image: chromadb/chroma:latest
    container_name: eao-chromadb
    ports:
      - "8001:8000"
    volumes:
      - chroma_data:/chroma/chroma
    environment:
      - IS_PERSISTENT=TRUE
      - ANONYMIZED_TELEMETRY=FALSE

volumes:
  redis_data:
  mysql_data:
  chroma_data:
```

MySQL 初始化脚本：

```sql
-- scripts/init.sql
CREATE TABLE IF NOT EXISTS conversations (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    session_id VARCHAR(64) NOT NULL,
    user_id VARCHAR(64) NOT NULL,
    role ENUM('user', 'assistant', 'system') NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_session_user (session_id, user_id),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS task_history (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    task_id VARCHAR(64) NOT NULL UNIQUE,
    user_id VARCHAR(64) NOT NULL,
    task_type VARCHAR(32) NOT NULL,
    status ENUM('pending', 'running', 'success', 'failed', 'retrying') DEFAULT 'pending',
    input_params JSON,
    output_result JSON,
    error_log TEXT,
    retry_count INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_user_status (user_id, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

启动基础设施：

```bash
docker-compose up -d
# 等待健康检查通过
docker-compose ps  # 确认所有服务状态为 healthy
```

### 3.4 DeepSeek API 配置

1. 访问 [DeepSeek 开放平台](https://platform.deepseek.com/) 开通服务
2. 获取 API Key
3. 创建 `.env` 文件：

```bash
# .env
# === DeepSeek LLM ===
LLM_API_KEY=sk-your-deepseek-key-here
LLM_MODEL=deepseek-chat       # deepseek-chat(通用) / deepseek-reasoner(推理)
LLM_BASE_URL=https://api.deepseek.com
LLM_TIMEOUT=30

# === SSO/LDAP (可选) ===
LDAP_ENABLED=false
LDAP_URL=ldap://ldap.company.com:389
LDAP_BASE_DN=dc=company,dc=com
LDAP_USER_DN_TEMPLATE=cn={username},ou=users,dc=company,dc=com
OIDC_ENABLED=false
OIDC_ISSUER=https://keycloak.company.com/realms/main
OIDC_CLIENT_ID=eao-platform
OIDC_CLIENT_SECRET=

# === 数据库 ===
REDIS_URL=redis://localhost:6379/0
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=eao_user
MYSQL_PASSWORD=eao_pass_2026
MYSQL_DATABASE=enterprise_ai_office

# === ChromaDB ===
CHROMA_HOST=localhost
CHROMA_PORT=8001

# === 应用 ===
APP_ENV=development          # development / production
LOG_LEVEL=INFO
MAX_RETRY=3
LLM_TIMEOUT=30               # LLM 调用超时（秒）
```

### 3.5 配置管理模块

```python
# app/config.py
import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    """全局配置单例"""

    # LLM
    DASHSCOPE_API_KEY: str = os.getenv("DASHSCOPE_API_KEY", "")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "qwen-plus")
    LLM_BASE_URL: str = os.getenv(
        "LLM_BASE_URL",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    LLM_TIMEOUT: int = int(os.getenv("LLM_TIMEOUT", "30"))

    # Redis
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # MySQL
    MYSQL_HOST: str = os.getenv("MYSQL_HOST", "localhost")
    MYSQL_PORT: int = int(os.getenv("MYSQL_PORT", "3306"))
    MYSQL_USER: str = os.getenv("MYSQL_USER", "eao_user")
    MYSQL_PASSWORD: str = os.getenv("MYSQL_PASSWORD", "")
    MYSQL_DATABASE: str = os.getenv("MYSQL_DATABASE", "enterprise_ai_office")

    # ChromaDB
    CHROMA_HOST: str = os.getenv("CHROMA_HOST", "localhost")
    CHROMA_PORT: int = int(os.getenv("CHROMA_PORT", "8001"))

    # App
    APP_ENV: str = os.getenv("APP_ENV", "development")
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    MAX_RETRY: int = int(os.getenv("MAX_RETRY", "3"))

    @property
    def mysql_url(self) -> str:
        return (
            f"mysql+pymysql://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}"
            f"@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DATABASE}"
            f"?charset=utf8mb4"
        )


settings = Settings()
```

### 3.6 环境验证脚本

```bash
# verify_env.py — 运行此脚本验证环境是否正确
"""环境验证脚本。运行: python verify_env.py"""
import sys

def check_python():
    v = sys.version_info
    assert (v.major, v.minor) >= (3, 12), f"需要 Python 3.12+, 当前: {v.major}.{v.minor}"
    print(f"✅ Python {v.major}.{v.minor}.{v.micro}")

def check_imports():
    modules = [
        ("langchain", "LangChain"),
        ("langchain_openai", "LangChain-OpenAI"),
        ("chromadb", "ChromaDB"),
        ("fastapi", "FastAPI"),
        ("streamlit", "Streamlit"),
        ("redis", "Redis"),
        ("sqlalchemy", "SQLAlchemy"),
        ("pandas", "Pandas"),
        ("matplotlib", "Matplotlib"),
        ("docx", "python-docx"),
        ("sentence_transformers", "Sentence-Transformers"),
    ]
    for mod, name in modules:
        try:
            __import__(mod)
            print(f"✅ {name}")
        except ImportError:
            print(f"❌ {name} 未安装")

def check_config():
    from app.config import settings
    assert settings.DASHSCOPE_API_KEY, "❌ DASHSCOPE_API_KEY 未设置"
    assert not settings.DASHSCOPE_API_KEY.startswith("sk-your-"), "❌ 请替换为真实 API Key"
    print(f"✅ 配置加载成功 (LLM: {settings.LLM_MODEL})")

def check_services():
    import redis
    try:
        r = redis.from_url("redis://localhost:6379/0")
        r.ping()
        print("✅ Redis 连接正常")
    except Exception as e:
        print(f"⚠️  Redis 连接失败: {e} (将使用内存降级)")

    import chromadb
    try:
        client = chromadb.HttpClient(host="localhost", port=8001)
        client.heartbeat()
        print("✅ ChromaDB 连接正常")
    except Exception as e:
        print(f"⚠️  ChromaDB 连接失败: {e}")

if __name__ == "__main__":
    print("=" * 50)
    print("环境验证")
    print("=" * 50)
    check_python()
    print("---")
    check_imports()
    print("---")
    check_config()
    print("---")
    check_services()
    print("=" * 50)
    print("验证完成")
```

---

## 4. Multi-Agent 核心引擎 (基于 LangGraph)

> 这是整个系统的核心。使用 **LangGraph StateGraph** 构建 Agent 工作流，替代传统的手动 DAG 编排。LangGraph 提供类型化状态管理、条件路由、checkpoint 持久化和 Human-in-the-loop 等原生能力。

### 4.1 为什么选 LangGraph

在调研了多个 GitHub 优秀项目（见附录 C）后，选择 LangGraph 作为 Agent 编排框架：

| 能力 | 手动实现 | LangGraph |
|------|---------|-----------|
| 状态管理 | 字典传递，易出错 | TypedDict 类型化 State |
| 条件路由 | if/else 硬编码 | `add_conditional_edges` 声明式 |
| 并行执行 | 手动 asyncio.gather | `Send()` API 原生 fan-out |
| 断点恢复 | 需要自己实现 | `checkpointer` 一行配置 |
| 可视化 | 无 | `draw_mermaid()` 自动生成 |
| Human-in-the-loop | 需要自己实现 | `interrupt()` / `Command` |

**参考项目**：
- [DATAGEN](https://github.com/starpig1129/DATAGEN) (~1.7k⭐) — 8 个专业 Agent + LangGraph StateGraph 编排，自动数据分析与报告生成
- [agentflow](https://github.com/Aparnap2/agentflow) — LangGraph 驱动的虚拟办公室，多角色 Agent 协作
- [ai-assistant-hub-langgraph](https://github.com/JoshPola96/ai-assistant-hub-langgraph) — Streamlit + ChromaDB + LangGraph 多 Agent 助手

### 4.2 LangGraph 核心概念

```
┌─────────────────────────────────────────────────────┐
│                  StateGraph 工作流                    │
│                                                     │
│   State (TypedDict): 在整个图中流转的状态对象         │
│   ├── messages: 对话历史                            │
│   ├── task_type: simple | complex                   │
│   ├── plan: 任务拆解结果                             │
│   ├── sub_results: 子任务执行结果                    │
│   └── final_answer: 最终回答                        │
│                                                     │
│   Nodes (节点): 处理函数，接收 State，返回 State 更新  │
│   Edges (边): 普通边 (固定流转) / 条件边 (动态路由)    │
│   Checkpointer: 每步自动保存 State，支持断点恢复       │
└─────────────────────────────────────────────────────┘
```

### 4.3 Agent 状态定义

```python
# app/agent/state.py
"""LangGraph Agent 状态定义"""
from typing import TypedDict, Annotated, Literal, Optional
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage


class AgentState(TypedDict):
    """
    LangGraph Agent 全局状态。

    使用 Annotated 标注 messages 字段的合并策略为 add_messages（追加而非覆盖）。
    """
    messages: Annotated[list[BaseMessage], add_messages]
    user_input: str                          # 用户原始输入
    task_type: str                           # "simple" | "complex"
    plan: Optional[dict]                     # 任务拆解计划
    sub_results: dict                        # task_id → result 映射
    final_answer: str                        # 最终回答
    error_count: int                         # 错误计数（熔断用）
```

### 4.4 路由分类器 (classify node)

```python
# app/agent/router.py
"""
任务路由分类器：判断用户输入属于"简单问答"还是"复杂任务"。
作为 LangGraph 的第一个节点，通过条件边分流到不同执行路径。
"""
import re
import logging
from typing import Literal
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from app.config import settings

logger = logging.getLogger(__name__)

COMPLEX_KEYWORDS = [
    r"分析.*并.*生成", r"对比.*和.*", r"先生成.*再",
    r"报告", r"图表", r"分析.*数据", r"统计.*并",
    r"帮我做", r"自动", r"批量", r"导出",
]

ROUTER_PROMPT = ChatPromptTemplate.from_template("""\
你是一个任务复杂度分类器。分析用户输入，判断是"simple"还是"complex"。

分类标准：
- simple: 单次问答、查询、解释、简单计算。不需要多步骤操作。
- complex: 需要多步骤操作、涉及文件处理、数据生成、跨系统查询。

用户输入：{user_input}

请只回答一个词：simple 或 complex。""")


def rule_based_route(user_input: str) -> Literal["simple", "complex"]:
    """规则引擎路由（LLM 降级兜底）"""
    for pattern in COMPLEX_KEYWORDS:
        if re.search(pattern, user_input):
            return "complex"
    return "simple"


def llm_route(user_input: str) -> Literal["simple", "complex"]:
    """LLM 路由（主路径）"""
    llm = ChatOpenAI(
        model=settings.LLM_MODEL,
        api_key=settings.DASHSCOPE_API_KEY,
        base_url=settings.LLM_BASE_URL,
        temperature=0,
        timeout=settings.LLM_TIMEOUT,
    )
    chain = ROUTER_PROMPT | llm
    result = chain.invoke({"user_input": user_input})
    return "complex" if "complex" in result.content.strip().lower() else "simple"


def classify_task(user_input: str) -> Literal["simple", "complex"]:
    """LLM 优先，失败降级到规则引擎"""
    try:
        return llm_route(user_input)
    except Exception as e:
        logger.warning(f"LLM 路由失败，降级到规则引擎: {e}")
        return rule_based_route(user_input)


# === LangGraph Node ===
def classify_node(state: AgentState) -> dict:
    """LangGraph classify 节点：分析用户输入并更新 task_type"""
    from app.agent.state import AgentState
    task_type = classify_task(state["user_input"])
    logger.info(f"分类结果: {task_type}")
    return {"task_type": task_type}
```

### 4.5 条件路由边

```python
# LangGraph 条件边：根据 task_type 分流
def route_by_complexity(state: AgentState) -> Literal["simple_react", "plan"]:
    """
    条件路由函数。
    - simple → 直接进入 ReAct 对话节点
    - complex → 进入任务规划节点
    """
    if state.get("task_type") == "complex":
        return "plan"
    return "simple_react"
```

### 4.6 任务规划节点 (plan node)

```python
# app/agent/planner.py
"""
任务规划节点：LLM 拆解用户需求为子任务列表。
作为 LangGraph 的 plan 节点，输出存入 state.plan。
"""
import json
import logging
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from app.config import settings
from app.agent.state import AgentState

logger = logging.getLogger(__name__)


class SubTask(BaseModel):
    task_id: str = Field(description="子任务 ID，如 task_1")
    description: str = Field(description="子任务描述")
    tool_name: str = Field(description="工具名称")
    tool_params: dict = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)


class TaskPlan(BaseModel):
    tasks: list[SubTask]
    execution_order: list[list[str]]  # 每层可并行

PLANNER_PROMPT = """\
你是一个任务规划专家。将用户的复杂需求拆解为可执行的子任务步骤。

可用工具列表：
{tools_description}

规划规则：
1. 每个子任务必须使用一个可用工具
2. 如果子任务之间没有数据依赖，它们可以并行执行
3. 如果子任务 B 需要子任务 A 的输出，则 B 依赖 A
4. task_id 格式为 "task_N"

请严格按照 JSON 格式输出：
{{"tasks": [...], "execution_order": [["task_1", "task_2"], ["task_3"]]}}"""


def llm_plan(user_input: str, tools_description: str) -> dict:
    """LLM 生成任务计划"""
    llm = ChatOpenAI(
        model=settings.LLM_MODEL,
        api_key=settings.DASHSCOPE_API_KEY,
        base_url=settings.LLM_BASE_URL,
        temperature=0.1,
        timeout=settings.LLM_TIMEOUT,
    )
    from langchain_core.prompts import ChatPromptTemplate
    prompt = ChatPromptTemplate.from_messages([
        ("system", PLANNER_PROMPT),
        ("user", "用户需求：{user_input}"),
    ])
    chain = prompt | llm
    result = chain.invoke({
        "tools_description": tools_description,
        "user_input": user_input,
    })
    content = result.content.strip()
    content = content.lstrip("```json").lstrip("```").rstrip("```").strip()
    return json.loads(content)


def plan_node(state: AgentState, tools_description: str) -> dict:
    """
    LangGraph plan 节点：LLM 规划优先，失败降级到规则引擎。
    """
    try:
        plan = llm_plan(state["user_input"], tools_description)
        logger.info(f"LLM 规划成功: {len(plan.get('tasks', []))} 个子任务")
        return {"plan": plan}
    except Exception as e:
        logger.warning(f"LLM 规划失败，降级规则引擎: {e}")
        return {"plan": rule_based_plan(state["user_input"])}


def rule_based_plan(user_input: str) -> dict:
    """规则引擎降级计划"""
    import re
    RULES = [
        (r"分析.*生成.*报告|数据.*报告|报表", "data_report"),
        (r"分析.*数据|数据.*分析|统计", "data_analysis"),
        (r"知识|文档|制度|规定|手册|帮助", "knowledge_qa"),
    ]
    PREDEFINED = {
        "data_report": {
            "tasks": [
                {"task_id": "task_1", "description": "分析数据", "tool_name": "data_analyzer", "tool_params": {"action": "analyze"}, "depends_on": []},
                {"task_id": "task_2", "description": "生成报告", "tool_name": "report_generator", "tool_params": {}, "depends_on": ["task_1"]},
            ],
            "execution_order": [["task_1"], ["task_2"]],
        },
        "data_analysis": {
            "tasks": [
                {"task_id": "task_1", "description": "分析数据", "tool_name": "data_analyzer", "tool_params": {"action": "analyze"}, "depends_on": []},
            ],
            "execution_order": [["task_1"]],
        },
        "knowledge_qa": {
            "tasks": [
                {"task_id": "task_1", "description": "检索知识库", "tool_name": "knowledge_search", "tool_params": {}, "depends_on": []},
            ],
            "execution_order": [["task_1"]],
        },
    }
    for pattern, key in RULES:
        if re.search(pattern, user_input):
            return PREDEFINED[key]
    return PREDEFINED["knowledge_qa"]
```

### 4.7 子任务执行节点 (execute node)

```python
# app/agent/executor.py
"""
LangGraph 执行节点：按 DAG 分层并行执行子任务。
利用 LangGraph 的 Send() API 实现 fan-out 并行。
"""
import logging
import asyncio
from typing import Any
from langgraph.graph import Send
from langchain_core.tools import BaseTool
from app.agent.state import AgentState
from app.agent.reflection import ReflectionHandler

logger = logging.getLogger(__name__)


async def execute_single_task(
    task: dict,
    tool: BaseTool,
    dep_results: dict[str, str],
    reflection: ReflectionHandler,
) -> tuple[str, str]:
    """
    执行单个子任务。失败时触发反思重试。

    Returns:
        (task_id, result_string)
    """
    params = dict(task.get("tool_params", {}))
    # 注入前置任务的结果
    for dep_id in task.get("depends_on", []):
        params[f"_{dep_id}_result"] = dep_results.get(dep_id, "")

    try:
        result = await tool.ainvoke(params)
        return task["task_id"], str(result)
    except Exception as e:
        logger.error(f"子任务 {task['task_id']} 失败: {e}")
        fixed_params = reflection.analyze_and_fix(task, str(e), params)
        if fixed_params is not None:
            result = await tool.ainvoke(fixed_params)
            return task["task_id"], str(result)
        return task["task_id"], f"[执行失败] {e}"


async def execute_node(state: AgentState, tools: list[BaseTool]) -> dict:
    """
    LangGraph execute 节点：按 execution_order 分层并行执行。

    每层内部：gather 并行执行该层所有子任务。
    层间：串行等待（确保依赖关系）。
    """
    plan = state.get("plan", {})
    execution_order = plan.get("execution_order", [])
    tasks = {t["task_id"]: t for t in plan.get("tasks", [])}
    sub_results: dict[str, str] = {}
    reflection = ReflectionHandler()

    for layer in execution_order:
        layer_tasks = []
        for task_id in layer:
            task = tasks.get(task_id)
            if task:
                tool = next((t for t in tools if t.name == task["tool_name"]), None)
                if tool:
                    layer_tasks.append(
                        execute_single_task(task, tool, sub_results, reflection)
                    )

        if layer_tasks:
            results = await asyncio.gather(*layer_tasks, return_exceptions=True)
            for r in results:
                if isinstance(r, tuple):
                    sub_results[r[0]] = r[1]

    return {"sub_results": sub_results}
```

### 4.8 简单问答节点 (simple_react node)

```python
# app/agent/simple_agent.py
"""简单问答节点：单步 ReAct 循环，直接调用 LLM + 工具"""
from langchain.agents import AgentExecutor, create_react_agent
from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate
from langchain_core.tools import BaseTool
from app.config import settings
from app.agent.state import AgentState

REACT_PROMPT = PromptTemplate.from_template("""\
你是一个企业智能办公助手。你可以使用以下工具来完成用户的任务：

{tools}

工具名称：{tool_names}

请使用以下格式：
Question: 用户的问题
Thought: 思考该怎么做
Action: 工具名称
Action Input: 工具参数（JSON）
Observation: 工具返回结果
... (可重复)
Thought: 我现在知道最终答案了
Final Answer: 给用户的最终回答

Question: {input}
Thought: {agent_scratchpad}""")


def simple_react_node(state: AgentState, tools: list[BaseTool]) -> dict:
    """
    LangGraph simple_react 节点：单步 ReAct 执行。
    适合不需要多步拆解的简单问答。
    """
    llm = ChatOpenAI(
        model=settings.LLM_MODEL,
        api_key=settings.DASHSCOPE_API_KEY,
        base_url=settings.LLM_BASE_URL,
        temperature=0.5,
        timeout=settings.LLM_TIMEOUT,
    )
    agent = create_react_agent(llm, tools, REACT_PROMPT)
    executor = AgentExecutor(
        agent=agent, tools=tools,
        verbose=True, handle_parsing_errors=True,
        max_iterations=5,
    )
    result = executor.invoke({"input": state["user_input"]})
    return {"final_answer": result["output"]}
```

### 4.9 结果聚合节点 (aggregate node)

```python
# app/agent/aggregator.py
"""结果聚合节点：将子任务执行结果汇总为自然语言回答"""
from langchain_openai import ChatOpenAI
from app.config import settings
from app.agent.state import AgentState


def aggregate_node(state: AgentState) -> dict:
    """
    LangGraph aggregate 节点：将各子任务结果用 LLM 聚合成自然语言回答。
    """
    llm = ChatOpenAI(
        model=settings.LLM_MODEL,
        api_key=settings.DASHSCOPE_API_KEY,
        base_url=settings.LLM_BASE_URL,
        temperature=0.3,
        timeout=settings.LLM_TIMEOUT,
    )

    plan = state.get("plan", {})
    execution_order = plan.get("execution_order", [])
    sub_results = state.get("sub_results", {})

    results_text = "\n".join(
        f"[{tid}] {sub_results.get(tid, '未执行')}"
        for layer in execution_order
        for tid in layer
    )

    prompt = f"""\
用户需求：{state['user_input']}

各子任务执行结果：
{results_text}

请将以上结果整合成一份完整、清晰的回答。失败的任务请如实说明。"""

    answer = llm.invoke(prompt).content
    return {"final_answer": answer}
```

### 4.10 组装 LangGraph 工作流

```python
# app/agent/graph.py
"""
组装完整的 LangGraph 工作流。

Graph 结构:
    classify ──(条件边)──▶ simple_react ──▶ END
       │
       └────────(条件边)──▶ plan ──▶ execute ──▶ aggregate ──▶ END

这是整个系统最核心的文件，定义了 Agent 的完整执行流程。
"""
import logging
from typing import Literal
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.tools import BaseTool

from app.agent.state import AgentState
from app.agent.router import classify_node
from app.agent.planner import plan_node
from app.agent.executor import execute_node
from app.agent.simple_agent import simple_react_node
from app.agent.aggregator import aggregate_node
from app.tools.base import registry

logger = logging.getLogger(__name__)


def create_agent_graph(
    tools: list[BaseTool] | None = None,
    checkpointer=None,
) -> StateGraph:
    """
    创建 Agent 工作流图。

    Args:
        tools: 可用工具列表（默认从注册中心加载）
        checkpointer: 状态检查点（MemorySaver 用于开发，SqliteSaver 用于生产）

    Returns:
        编译后的 LangGraph 工作流
    """
    if tools is None:
        tools = registry.list_tools()

    tools_description = registry.get_tools_description()

    # 创建 StateGraph
    workflow = StateGraph(AgentState)

    # 注册节点
    workflow.add_node("classify", classify_node)
    workflow.add_node(
        "simple_react",
        lambda state: simple_react_node(state, tools),
    )
    workflow.add_node(
        "plan",
        lambda state: plan_node(state, tools_description),
    )

    # execute 节点需要异步，用 async wrapper 包装
    async def execute_wrapper(state: AgentState) -> dict:
        return await execute_node(state, tools)
    workflow.add_node("execute", execute_wrapper)

    workflow.add_node("aggregate", aggregate_node)

    # 设置入口
    workflow.set_entry_point("classify")

    # 条件边：分类后分流
    def route_after_classify(state: AgentState) -> Literal["simple_react", "plan"]:
        if state.get("task_type") == "complex":
            return "plan"
        return "simple_react"

    workflow.add_conditional_edges(
        "classify",
        route_after_classify,
        {
            "simple_react": "simple_react",
            "plan": "plan",
        },
    )

    # 普通边：定义顺序流转
    workflow.add_edge("simple_react", END)
    workflow.add_edge("plan", "execute")
    workflow.add_edge("execute", "aggregate")
    workflow.add_edge("aggregate", END)

    # 编译（带 checkpoint 支持断点恢复）
    if checkpointer is None:
        checkpointer = MemorySaver()

    app = workflow.compile(checkpointer=checkpointer)
    logger.info("✅ LangGraph 工作流已编译")

    return app


# 全局 Graph 实例（懒加载）
_agent_app = None


def get_agent_app() -> StateGraph:
    """获取 Agent 工作流实例（单例）"""
    global _agent_app
    if _agent_app is None:
        _agent_app = create_agent_graph()
    return _agent_app


async def run_agent(user_input: str, thread_id: str = "default") -> str:
    """
    运行 Agent 工作流的主入口。

    Args:
        user_input: 用户输入
        thread_id: 会话线程 ID（用于 checkpoint 隔离）

    Returns:
        Agent 最终回答
    """
    app = get_agent_app()

    # 配置（thread_id 用于多用户隔离）
    config = {"configurable": {"thread_id": thread_id}}

    # 初始状态
    initial_state: AgentState = {
        "messages": [],
        "user_input": user_input,
        "task_type": "",
        "plan": None,
        "sub_results": {},
        "final_answer": "",
        "error_count": 0,
    }

    # 执行工作流
    final_state = await app.ainvoke(initial_state, config)
    return final_state.get("final_answer", "抱歉，处理过程中出现了问题。")


# 可视化辅助函数
def visualize_graph(output_path: str = "docs/agent_graph.png"):
    """导出 LangGraph 工作流为图片（需要 graphviz）"""
    app = get_agent_app()
    try:
        from langgraph.graph import draw_mermaid
        mermaid = draw_mermaid(app)
        with open("docs/agent_graph.mermaid", "w") as f:
            f.write(mermaid)
        logger.info(f"Mermaid 图已保存到 docs/agent_graph.mermaid")
        # 在线渲染: https://mermaid.live/
    except Exception as e:
        logger.warning(f"可视化失败: {e}")
```

### 4.11 LangGraph 工作流可视化

将上述 Mermaid 代码粘贴到 [mermaid.live](https://mermaid.live/) 渲染：

```
classify → [条件判断 task_type]
  ├── simple → simple_react → END
  └── complex → plan → execute → aggregate → END
```

### 4.12 验证方式

```python
# tests/test_agent_graph.py
import pytest
from unittest.mock import patch, Mock
from app.agent.graph import create_agent_graph


def test_graph_compiles():
    """工作流应该能成功编译"""
    mock_tools = [Mock(name="test_tool")]
    app = create_agent_graph(tools=mock_tools)
    assert app is not None


def test_classify_simple_question():
    """简单问题应路由到 simple_react"""
    from app.agent.router import classify_task
    assert classify_task("你好") == "simple"
    assert classify_task("公司年假有几天？") == "simple"


def test_classify_complex_task():
    """复杂任务应路由到 plan"""
    from app.agent.router import classify_task
    result = classify_task("分析销售数据并生成报告")
    assert result == "complex"


@patch("app.agent.router.llm_route", side_effect=Exception("超时"))
def test_classify_fallback(mock_llm):
    """LLM 失败时规则引擎应正确分类"""
    from app.agent.router import classify_task
    result = classify_task("分析销售数据并生成报告")
    assert result == "complex"
```

---

## 5. RAG 知识问答系统

### 5.1 文档加载器

```python
# app/rag/loader.py
"""
通用文档加载器：支持 PDF、Word (docx)、Excel (xlsx)、TXT 四种格式。
返回统一的 Document 对象列表。
"""
import os
import logging
from pathlib import Path
from typing import List
from langchain_core.documents import Document

logger = logging.getLogger(__name__)

# 检测文件真实类型（避免只依赖扩展名）
FILE_SIGNATURES = {
    b"%PDF": "pdf",
    b"PK\x03\x04": "docx_or_xlsx",  # ZIP 格式（docx/xlsx 都是 ZIP）
    b"\xd0\xcf\x11\xe0": "doc_or_xls",  # OLE 格式（旧版 Office）
}


def detect_file_type(file_path: str) -> str:
    """通过文件头魔数检测真实类型"""
    ext = Path(file_path).suffix.lower()
    with open(file_path, "rb") as f:
        header = f.read(8)
    for magic, ftype in FILE_SIGNATURES.items():
        if header.startswith(magic):
            if ftype == "docx_or_xlsx":
                return "docx" if ext == ".docx" else "xlsx"
            return ftype
    # 回退到扩展名
    return ext.lstrip(".")


class UniversalDocumentLoader:
    """通用文档加载器，按文件类型自动分发到对应解析器。"""

    SUPPORTED_TYPES = ["pdf", "docx", "xlsx", "xls", "txt", "csv"]

    @staticmethod
    def load_pdf(file_path: str) -> List[Document]:
        from PyPDF2 import PdfReader
        reader = PdfReader(file_path)
        documents = []
        for i, page in enumerate(reader.pages):
            text = page.extract_text()
            if text and text.strip():
                documents.append(Document(
                    page_content=text.strip(),
                    metadata={
                        "source": file_path,
                        "page": i + 1,
                        "type": "pdf",
                    }
                ))
        logger.info(f"PDF 加载: {file_path} → {len(documents)} 页")
        return documents

    @staticmethod
    def load_docx(file_path: str) -> List[Document]:
        from docx import Document as DocxDocument
        doc = DocxDocument(file_path)
        full_text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        if not full_text:
            return []
        return [Document(
            page_content=full_text,
            metadata={"source": file_path, "type": "docx"}
        )]

    @staticmethod
    def load_excel(file_path: str) -> List[Document]:
        import pandas as pd
        # 读取所有 sheet
        sheets = pd.read_excel(file_path, sheet_name=None)
        documents = []
        for sheet_name, df in sheets.items():
            # 将每行转为 "列名: 值" 格式的文本，方便语义检索
            rows_text = []
            for _, row in df.iterrows():
                row_str = " | ".join(
                    f"{col}: {val}" for col, val in row.items()
                    if pd.notna(val)
                )
                rows_text.append(row_str)
            content = f"[Sheet: {sheet_name}]\n" + "\n".join(rows_text)
            documents.append(Document(
                page_content=content,
                metadata={
                    "source": file_path,
                    "sheet": sheet_name,
                    "rows": len(df),
                    "type": "excel",
                }
            ))
        return documents

    @staticmethod
    def load_txt(file_path: str) -> List[Document]:
        with open(file_path, "r", encoding="utf-8") as f:
            text = f.read()
        if not text.strip():
            return []
        return [Document(
            page_content=text,
            metadata={"source": file_path, "type": "txt"}
        )]

    @classmethod
    def load(cls, file_path: str) -> List[Document]:
        """主入口：自动检测文件类型并加载"""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"文件不存在: {file_path}")

        file_type = detect_file_type(file_path)
        logger.info(f"文件类型检测: {file_path} → {file_type}")

        loaders = {
            "pdf": cls.load_pdf,
            "docx": cls.load_docx,
            "xlsx": cls.load_excel,
            "xls": cls.load_excel,
            "txt": cls.load_txt,
            "csv": cls.load_txt,
        }

        loader = loaders.get(file_type)
        if loader is None:
            raise ValueError(
                f"不支持的文件类型: {file_type}。"
                f"支持的类型: {cls.SUPPORTED_TYPES}"
            )

        documents = loader(file_path)
        # 为所有文档添加文件名元数据
        filename = Path(file_path).name
        for doc in documents:
            doc.metadata["filename"] = filename
        return documents
```

### 5.2 文本分块

```python
# app/rag/splitter.py
"""
智能文本分块：使用 RecursiveCharacterTextSplitter，
配合 chunk_overlap 避免语义截断。
"""
from typing import List
from langchain_core.documents import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter


def create_splitter(
    chunk_size: int = 500,
    chunk_overlap: int = 150,
) -> RecursiveCharacterTextSplitter:
    """
    创建中文优化的文本分块器。

    Args:
        chunk_size: 每个 chunk 的最大字符数。中文场景 500 较合适。
        chunk_overlap: 相邻 chunk 重叠字符数。设为 chunk_size 的 25-30%
                       可有效避免关键信息被切断。
    """
    return RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=[
            "\n\n",   # 段落边界（最高优先级）
            "\n",     # 换行
            "。",     # 中文句号
            "；",     # 中文分号
            "，",     # 中文逗号
            ".",      # 英文句号
            ";",      # 英文分号
            " ",      # 空格
            "",       # 字符级（最后手段）
        ],
        length_function=len,
    )


def split_documents(
    documents: List[Document],
    chunk_size: int = 500,
    chunk_overlap: int = 150,
) -> List[Document]:
    """
    对文档列表进行分块。

    Args:
        documents: 原始文档列表
        chunk_size: 分块大小
        chunk_overlap: 重叠大小

    Returns:
        分块后的文档列表，每个 chunk 保留原始元数据 + chunk 序号
    """
    splitter = create_splitter(chunk_size, chunk_overlap)
    chunks = splitter.split_documents(documents)

    # 为每个 chunk 添加序号，方便追溯
    for i, chunk in enumerate(chunks):
        chunk.metadata["chunk_id"] = i
        # 保留前 100 字符作为预览
        chunk.metadata["preview"] = chunk.page_content[:100]

    return chunks
```

### 5.3 向量化与存储

```python
# app/rag/embedder.py
"""
文本向量化模块：使用 BGE-Small-ZH 将文本转为 512 维向量。
"""
from sentence_transformers import SentenceTransformer
from langchain_core.embeddings import Embeddings
from typing import List


class BGEEmbeddings(Embeddings):
    """LangChain 兼容的 BGE 向量化封装"""

    def __init__(self, model_name: str = "BAAI/bge-small-zh-v1.5"):
        self.model = SentenceTransformer(model_name)
        self._dim = self.model.get_sentence_embedding_dimension()

    @property
    def dimension(self) -> int:
        return self._dim

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """批量向量化文档"""
        # BGE 模型建议为文档添加 "为这个句子生成表示以用于检索相关文章：" 前缀
        texts_with_prefix = [
            f"为这个句子生成表示以用于检索相关文章：{t}" for t in texts
        ]
        embeddings = self.model.encode(
            texts_with_prefix,
            normalize_embeddings=True,  # L2 归一化，提升余弦相似度计算效率
            show_progress_bar=False,
        )
        return embeddings.tolist()

    def embed_query(self, text: str) -> List[float]:
        """向量化查询文本。注意：查询不加前缀。"""
        embedding = self.model.encode(
            text,
            normalize_embeddings=True,
        )
        return embedding.tolist()
```

```python
# app/rag/store.py
"""
ChromaDB 向量存储操作：初始化、插入、检索。
"""
import logging
from typing import List, Optional
import chromadb
from chromadb.config import Settings as ChromaSettings
from langchain_chroma import Chroma
from langchain_core.documents import Document
from app.config import settings
from app.rag.embedder import BGEEmbeddings

logger = logging.getLogger(__name__)

# 全局单例
_embedder: Optional[BGEEmbeddings] = None
_vector_store: Optional[Chroma] = None

COLLECTION_NAME = "enterprise_knowledge"


def get_embedder() -> BGEEmbeddings:
    global _embedder
    if _embedder is None:
        _embedder = BGEEmbeddings()
    return _embedder


def get_vector_store() -> Chroma:
    """获取向量存储实例（懒加载单例）"""
    global _vector_store
    if _vector_store is None:
        _vector_store = Chroma(
            collection_name=COLLECTION_NAME,
            embedding_function=get_embedder(),
            client=chromadb.HttpClient(
                host=settings.CHROMA_HOST,
                port=settings.CHROMA_PORT,
                settings=ChromaSettings(
                    anonymized_telemetry=False,
                ),
            ),
        )
    return _vector_store


def add_documents(
    documents: List[Document],
    batch_size: int = 50,
) -> int:
    """批量添加文档到向量库。返回添加的 chunk 数量。"""
    store = get_vector_store()
    total = 0
    for i in range(0, len(documents), batch_size):
        batch = documents[i:i + batch_size]
        store.add_documents(batch)
        total += len(batch)
    logger.info(f"向量库添加 {total} 个 chunks")
    return total


def delete_by_source(source: str) -> int:
    """按源文件删除文档"""
    store = get_vector_store()
    # 获取所有匹配的 IDs
    results = store.get(where={"source": source})
    ids = results.get("ids", [])
    if ids:
        store.delete(ids=ids)
    logger.info(f"删除 {len(ids)} 个 chunks (source={source})")
    return len(ids)
```

### 5.4 检索与问答

```python
# app/rag/retriever.py
"""
RAG 检索与问答：语义检索 + Prompt 约束 + 来源追溯。
"""
import logging
from typing import List, Tuple
from langchain_core.documents import Document
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from app.config import settings
from app.rag.store import get_vector_store

logger = logging.getLogger(__name__)

# RAG Prompt 模板 — "强约束" 是抑制幻觉的关键
RAG_SYSTEM_PROMPT = """\
你是一个企业知识问答助手。请严格依据以下参考资料回答用户的问题。

规则：
1. 如果参考资料包含答案，请准确回答并引用来源。
2. 如果参考资料不包含答案，请明确说"根据现有资料，我无法回答这个问题"，不要编造。
3. 回答时，在末尾列出参考的文档名称。

参考资料：
{context}"""

RAG_USER_PROMPT = """\
用户问题：{question}

请回答："""


def similarity_search(
    query: str,
    k: int = 5,
    score_threshold: float = 0.3,
) -> List[Document]:
    """
    语义相似度检索。

    Args:
        query: 用户问题
        k: 返回文档数量
        score_threshold: 相似度阈值（0-1），低于此值的文档被过滤

    Returns:
        相关文档列表
    """
    store = get_vector_store()
    # MMR 检索：兼顾相关性和多样性
    # fetch_k 先取更多候选，再 MMR 选择多样化的 k 个
    retriever = store.as_retriever(
        search_type="mmr",
        search_kwargs={
            "k": k,
            "fetch_k": k * 4,
            "lambda_mult": 0.7,  # 0=最大多样性, 1=最大相关性
        },
    )
    docs = retriever.invoke(query)
    logger.info(f"检索到 {len(docs)} 个相关文档片段")
    return docs


def format_context(docs: List[Document]) -> str:
    """将检索到的文档片段格式化为 Prompt 上下文"""
    parts = []
    for i, doc in enumerate(docs, 1):
        source = doc.metadata.get("filename", doc.metadata.get("source", "未知"))
        page = doc.metadata.get("page", "")
        chunk_id = doc.metadata.get("chunk_id", "")
        location = f"{source}"
        if page:
            location += f" 第{page}页"
        parts.append(f"[参考资料 {i}] 来源: {location}\n{doc.page_content}")
    return "\n\n".join(parts)


def rag_qa(
    question: str,
    k: int = 5,
) -> Tuple[str, List[Document]]:
    """
    RAG 问答主入口。

    Args:
        question: 用户问题
        k: 检索文档数量

    Returns:
        (回答文本, 参考文档列表)
    """
    # 1. 检索相关文档
    docs = similarity_search(question, k=k)

    if not docs:
        return "抱歉，在知识库中没有找到与您问题相关的资料。请尝试换一种问法。", []

    # 2. 构建上下文
    context = format_context(docs)

    # 3. 调用 LLM 生成回答
    llm = ChatOpenAI(
        model=settings.LLM_MODEL,
        api_key=settings.DASHSCOPE_API_KEY,
        base_url=settings.LLM_BASE_URL,
        temperature=0.1,  # RAG 用低温度，减少幻觉
        timeout=settings.LLM_TIMEOUT,
    )

    prompt = ChatPromptTemplate.from_messages([
        ("system", RAG_SYSTEM_PROMPT),
        ("user", RAG_USER_PROMPT),
    ])
    chain = prompt | llm
    response = chain.invoke({
        "context": context,
        "question": question,
    })

    return response.content, docs


def rag_qa_with_sources(question: str, k: int = 5) -> dict:
    """
    RAG 问答（返回结构化结果，包含来源追溯）。

    Returns:
        {
            "answer": str,
            "sources": [{"filename": str, "page": int, "preview": str}, ...]
        }
    """
    answer, docs = rag_qa(question, k=k)
    sources = []
    seen = set()
    for doc in docs:
        filename = doc.metadata.get("filename", "未知")
        if filename not in seen:
            seen.add(filename)
            sources.append({
                "filename": filename,
                "page": doc.metadata.get("page"),
                "preview": doc.page_content[:200],
            })
    return {"answer": answer, "sources": sources}
```

### 5.5 验证方式

```python
# 验证 RAG 链路的集成测试思路
"""
1. 准备测试文档（一段已知内容的企业制度 PDF/TXT）
2. upload → load → split → embed → store
3. 针对文档内容提问，检查：
   - answer 是否包含正确答案
   - sources 是否正确指向源文档
4. 针对文档不存在的内容提问，检查：
   - answer 是否明确说"无法回答"而非编造
"""
```

---

## 6. 插件化工具系统

### 6.1 BaseTool 基类与注册中心

```python
# app/tools/base.py
"""
工具基类与注册中心。所有工具继承 BaseTool，
使用 @register_tool 装饰器注册。
"""
from typing import Dict, Type, Optional, Callable
from pydantic import BaseModel, Field
from langchain_core.tools import BaseTool as LangChainBaseTool
from abc import ABC, abstractmethod
import logging

logger = logging.getLogger(__name__)


class ToolRegistry:
    """工具注册中心（单例）"""

    _instance: Optional["ToolRegistry"] = None
    _tools: Dict[str, Type[LangChainBaseTool]] = {}
    _instances: Dict[str, LangChainBaseTool] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def register(
        self,
        tool_cls: Type[LangChainBaseTool],
        override: bool = False,
    ):
        """注册工具类"""
        # 实例化以获取 name
        try:
            instance = tool_cls()
            name = instance.name
        except Exception:
            name = tool_cls.__name__
        if name in self._tools and not override:
            logger.warning(f"工具 '{name}' 已注册，跳过（使用 override=True 覆盖）")
            return
        self._tools[name] = tool_cls
        logger.info(f"工具已注册: {name}")

    def unregister(self, name: str):
        """注销工具"""
        self._tools.pop(name, None)
        self._instances.pop(name, None)
        logger.info(f"工具已注销: {name}")

    def get_tool(self, name: str) -> Optional[LangChainBaseTool]:
        """获取工具实例（懒加载）"""
        if name not in self._tools:
            return None
        if name not in self._instances:
            self._instances[name] = self._tools[name]()
        return self._instances[name]

    def list_tools(self) -> list[LangChainBaseTool]:
        """获取所有已注册工具实例"""
        return [self.get_tool(name) for name in self._tools]

    def list_tool_names(self) -> list[str]:
        return list(self._tools.keys())

    def get_tools_description(self) -> str:
        """生成工具列表描述（供 LLM Prompt 使用）"""
        lines = []
        for name in self._tools:
            tool = self.get_tool(name)
            lines.append(f"- {name}: {tool.description}")
        return "\n".join(lines)


# 全局注册中心
registry = ToolRegistry()


def register_tool(cls):
    """装饰器：自动注册工具到全局注册中心"""
    registry.register(cls)
    return cls
```

### 6.2 DataAnalyzer 工具

```python
# app/tools/data_analyzer.py
"""
数据分析工具：Excel/CSV 读取 → 清洗 → 统计 → 图表 → Word 报告。
"""
import os
import logging
from typing import Optional, Literal
from pydantic import BaseModel, Field
from langchain_core.tools import BaseTool
import pandas as pd
import matplotlib
matplotlib.use("Agg")  # 非 GUI 后端
import matplotlib.pyplot as plt
from app.tools.base import register_tool

logger = logging.getLogger(__name__)

# 中文支持
plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


class DataAnalyzerInput(BaseModel):
    """DataAnalyzer 工具入参（Pydantic 严格校验）"""
    file_path: str = Field(description="Excel 或 CSV 文件的绝对路径")
    action: Literal["summary", "analyze", "full_report"] = Field(
        default="summary",
        description="操作类型: summary=概览统计, analyze=深度分析, full_report=生成完整报告"
    )
    target_column: Optional[str] = Field(
        default=None,
        description="需要重点分析的列名（可选）"
    )
    chart_type: Optional[Literal["bar", "line", "pie", "scatter"]] = Field(
        default=None,
        description="图表类型"
    )


@register_tool
class DataAnalyzerTool(BaseTool):
    """
    数据分析工具：读取 Excel/CSV 文件，进行数据清洗、统计分析并生成图表和报告。
    """
    name: str = "data_analyzer"
    description: str = (
        "分析 Excel/CSV 数据文件。支持：数据概览(summary)、"
        "深度分析(analyze)、完整报告(full_report)。"
        "可以指定分析列和图表类型(bar/line/pie/scatter)。"
    )
    args_schema: type[BaseModel] = DataAnalyzerInput

    def _load_data(self, file_path: str) -> pd.DataFrame:
        """加载数据文件"""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"文件不存在: {file_path}")

        ext = os.path.splitext(file_path)[1].lower()
        if ext in (".xlsx", ".xls"):
            return pd.read_excel(file_path)
        elif ext == ".csv":
            # 尝试常见编码
            for enc in ["utf-8", "gbk", "gb2312", "latin-1"]:
                try:
                    return pd.read_csv(file_path, encoding=enc)
                except UnicodeDecodeError:
                    continue
            raise ValueError("无法识别 CSV 编码")
        else:
            raise ValueError(f"不支持的文件格式: {ext}")

    def _clean_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """数据清洗：去重 + 中位数填充数值列"""
        df = df.copy()
        before = len(df)
        df = df.drop_duplicates()
        logger.info(f"去重: {before} → {len(df)} (移除 {before - len(df)} 行)")

        # 数值列用中位数填充
        numeric_cols = df.select_dtypes(include=["number"]).columns
        for col in numeric_cols:
            missing = df[col].isna().sum()
            if missing > 0:
                df[col] = df[col].fillna(df[col].median())
                logger.info(f"中位数填充: {col} ({missing} 个缺失值)")
        return df

    def _generate_summary(self, df: pd.DataFrame) -> str:
        """生成数据摘要"""
        lines = [
            f"## 数据概览",
            f"- 行数: {len(df)}",
            f"- 列数: {len(df.columns)}",
            f"- 列名: {', '.join(df.columns.tolist())}",
            f"- 缺失值总数: {df.isna().sum().sum()}",
            f"",
            f"### 数值列统计",
            f"```",
        ]
        desc = df.describe().to_string()
        lines.append(desc)
        lines.append("```")
        return "\n".join(lines)

    def _generate_chart(
        self,
        df: pd.DataFrame,
        target_column: Optional[str],
        chart_type: str = "bar",
        output_dir: str = "data/reports",
    ) -> Optional[str]:
        """生成图表，返回图片路径"""
        os.makedirs(output_dir, exist_ok=True)

        numeric_cols = df.select_dtypes(include=["number"]).columns
        if len(numeric_cols) == 0:
            logger.warning("无数值列，跳过图表生成")
            return None

        col = target_column or numeric_cols[0]
        if col not in df.columns:
            col = numeric_cols[0]

        fig, ax = plt.subplots(figsize=(10, 6))

        if chart_type == "bar":
            # 取前 20 个值（避免图表过于拥挤）
            data = df[col].value_counts().head(20)
            ax.bar(range(len(data)), data.values)
            ax.set_xticks(range(len(data)))
            ax.set_xticklabels(data.index, rotation=45, ha="right")
            ax.set_title(f"{col} 分布 (柱状图)")
        elif chart_type == "line":
            data = df[col].head(50)
            ax.plot(range(len(data)), data.values)
            ax.set_title(f"{col} 趋势 (折线图)")
        elif chart_type == "pie":
            data = df[col].value_counts().head(10)
            ax.pie(data.values, labels=data.index, autopct="%1.1f%%")
            ax.set_title(f"{col} 占比 (饼图)")
        else:  # scatter
            if len(numeric_cols) >= 2:
                ax.scatter(df[numeric_cols[0]], df[numeric_cols[1]], alpha=0.5)
                ax.set_xlabel(numeric_cols[0])
                ax.set_ylabel(numeric_cols[1])
                ax.set_title(f"{numeric_cols[0]} vs {numeric_cols[1]} (散点图)")

        chart_path = os.path.join(output_dir, f"chart_{col}_{chart_type}.png")
        plt.tight_layout()
        fig.savefig(chart_path, dpi=150)
        plt.close(fig)
        logger.info(f"图表已保存: {chart_path}")
        return chart_path

    def _generate_report(
        self,
        df: pd.DataFrame,
        summary: str,
        chart_paths: list[str],
        output_dir: str = "data/reports",
    ) -> str:
        """生成 Word 报告"""
        from docx import Document
        from docx.shared import Inches

        doc = Document()
        doc.add_heading("数据分析报告", level=0)
        doc.add_paragraph(f"生成时间: {pd.Timestamp.now()}")

        doc.add_heading("数据概览", level=1)
        doc.add_paragraph(f"数据行数: {len(df)}")
        doc.add_paragraph(f"数据列数: {len(df.columns)}")

        doc.add_heading("统计摘要", level=1)
        for line in summary.split("\n"):
            doc.add_paragraph(line)

        if chart_paths:
            doc.add_heading("可视化图表", level=1)
            for path in chart_paths:
                if os.path.exists(path):
                    doc.add_picture(path, width=Inches(5.5))
                    doc.add_paragraph(f"图表: {os.path.basename(path)}")

        report_path = os.path.join(output_dir, f"report_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.docx")
        doc.save(report_path)
        logger.info(f"报告已保存: {report_path}")
        return report_path

    def _run(
        self,
        file_path: str,
        action: str = "summary",
        target_column: Optional[str] = None,
        chart_type: Optional[str] = None,
    ) -> str:
        """工具执行入口"""
        try:
            # 安全校验：文件路径白名单
            allowed_dirs = [os.path.abspath("data/documents"), os.path.abspath("data/uploads")]
            abs_path = os.path.abspath(file_path)
            if not any(abs_path.startswith(d) for d in allowed_dirs):
                return f"❌ 安全限制：只能访问 {allowed_dirs} 目录下的文件"

            df = self._load_data(file_path)
            df = self._clean_data(df)

            if action == "summary":
                return self._generate_summary(df)

            elif action == "analyze":
                summary = self._generate_summary(df)
                chart_path = None
                if chart_type:
                    chart_path = self._generate_chart(df, target_column, chart_type)
                result = summary
                if chart_path:
                    result += f"\n\n📊 图表已生成: {chart_path}"
                return result

            elif action == "full_report":
                summary = self._generate_summary(df)
                # 生成多种图表
                chart_paths = []
                for ct in ["bar", "line"]:
                    path = self._generate_chart(df, target_column, ct)
                    if path:
                        chart_paths.append(path)
                report_path = self._generate_report(df, summary, chart_paths)
                return (
                    f"✅ 完整报告已生成: {report_path}\n\n"
                    f"{summary}\n\n"
                    f"📊 图表数量: {len(chart_paths)}"
                )

        except Exception as e:
            logger.error(f"数据分析失败: {e}", exc_info=True)
            return f"❌ 数据分析失败: {str(e)}"
```

### 6.3 OA/CRM 对接工具（Mock/Real 双模式）

```python
# app/tools/oa_crm.py
"""
OA/CRM 对接工具：支持 Mock 和 Real 双模式。
外部 API 不可用时自动降级到 Mock 数据。
"""
import logging
from typing import Literal, Optional
from pydantic import BaseModel, Field
from langchain_core.tools import BaseTool
import httpx
from app.config import settings
from app.tools.base import register_tool

logger = logging.getLogger(__name__)

# === Mock 数据 ===
MOCK_OA_APPROVALS = [
    {"id": "OA-001", "title": "年假申请", "status": "已通过", "applicant": "张三", "date": "2026-06-10"},
    {"id": "OA-002", "title": "报销申请", "status": "审批中", "applicant": "李四", "date": "2026-06-11"},
    {"id": "OA-003", "title": "出差申请", "status": "已通过", "applicant": "王五", "date": "2026-06-09"},
]

MOCK_CRM_CUSTOMERS = [
    {"id": "CRM-001", "name": "ABC科技", "industry": "互联网", "level": "A", "contact": "赵总"},
    {"id": "CRM-002", "name": "XYZ实业", "industry": "制造业", "level": "B", "contact": "钱总"},
    {"id": "CRM-003", "name": "123商贸", "industry": "零售", "level": "C", "contact": "孙总"},
]


class OAQueryInput(BaseModel):
    action: Literal["list_approvals", "query_by_id", "query_by_user"]
    value: Optional[str] = Field(default=None, description="查询值（ID 或用户名）")


class CRMQueryInput(BaseModel):
    action: Literal["list_customers", "query_by_id", "query_by_industry"]
    value: Optional[str] = Field(default=None, description="查询值")


@register_tool
class OATool(BaseTool):
    """OA 系统对接工具"""
    name: str = "oa_query"
    description: str = "查询 OA 审批状态。支持：列表查询(list_approvals)、按ID查询(query_by_id)、按用户查询(query_by_user)。"
    args_schema: type[BaseModel] = OAQueryInput

    def _query_real(self, action: str, value: Optional[str]) -> str:
        """真实 API 调用"""
        oa_api_url = getattr(settings, "OA_API_URL", "")
        if not oa_api_url:
            raise ValueError("OA_API_URL 未配置")

        with httpx.Client(timeout=10) as client:
            resp = client.get(f"{oa_api_url}/approvals", params={"action": action, "value": value})
            resp.raise_for_status()
            return resp.text

    def _query_mock(self, action: str, value: Optional[str]) -> str:
        """Mock 数据查询"""
        if action == "list_approvals":
            items = MOCK_OA_APPROVALS
        elif action == "query_by_id":
            items = [a for a in MOCK_OA_APPROVALS if a["id"] == value]
        elif action == "query_by_user":
            items = [a for a in MOCK_OA_APPROVALS if a["applicant"] == value]
        else:
            items = MOCK_OA_APPROVALS

        if not items:
            return "未找到匹配的审批记录。"

        lines = ["## OA 审批记录"]
        for item in items:
            lines.append(f"- [{item['id']}] {item['title']} | 状态: {item['status']} | 申请人: {item['applicant']} | {item['date']}")
        return "\n".join(lines)

    def _run(self, action: str = "list_approvals", value: Optional[str] = None) -> str:
        """先尝试真实 API，失败则降级 Mock"""
        try:
            return self._query_real(action, value)
        except Exception as e:
            logger.warning(f"OA API 不可用，降级到 Mock: {e}")
            return f"[Mock 模式] \n{self._query_mock(action, value)}"


@register_tool
class CRMTool(BaseTool):
    """CRM 系统对接工具"""
    name: str = "crm_query"
    description: str = "查询 CRM 客户信息。支持：客户列表(list_customers)、按ID查询(query_by_id)、按行业查询(query_by_industry)。"
    args_schema: type[BaseModel] = CRMQueryInput

    def _query_real(self, action: str, value: Optional[str]) -> str:
        crm_api_url = getattr(settings, "CRM_API_URL", "")
        if not crm_api_url:
            raise ValueError("CRM_API_URL 未配置")
        with httpx.Client(timeout=10) as client:
            resp = client.get(f"{crm_api_url}/customers", params={"action": action, "value": value})
            resp.raise_for_status()
            return resp.text

    def _query_mock(self, action: str, value: Optional[str]) -> str:
        if action == "list_customers":
            items = MOCK_CRM_CUSTOMERS
        elif action == "query_by_id":
            items = [c for c in MOCK_CRM_CUSTOMERS if c["id"] == value]
        elif action == "query_by_industry":
            items = [c for c in MOCK_CRM_CUSTOMERS if c["industry"] == value]
        else:
            items = MOCK_CRM_CUSTOMERS

        if not items:
            return "未找到匹配的客户信息。"

        lines = ["## CRM 客户信息"]
        for item in items:
            lines.append(f"- [{item['id']}] {item['name']} | 行业: {item['industry']} | 等级: {item['level']} | 联系人: {item['contact']}")
        return "\n".join(lines)

    def _run(self, action: str = "list_customers", value: Optional[str] = None) -> str:
        try:
            return self._query_real(action, value)
        except Exception as e:
            logger.warning(f"CRM API 不可用，降级到 Mock: {e}")
            return f"[Mock 模式] \n{self._query_mock(action, value)}"
```

### 6.4 安全沙箱

```python
# app/tools/registry.py
"""
工具安全沙箱：文件路径白名单 + 命令注入防护。
"""
import os
import re
from typing import List

# 文件操作白名单目录
ALLOWED_DIRECTORIES = [
    os.path.abspath("data/documents"),
    os.path.abspath("data/uploads"),
    os.path.abspath("data/reports"),
]

# 禁止出现在文件路径中的模式
FORBIDDEN_PATTERNS = [
    r"\.\./",           # 路径穿越
    r"\.\.\\",          # Windows 路径穿越
    r"/etc/",           # 系统目录
    r"C:\\Windows",     # Windows 系统目录
    r"file://",         # file 协议
    r"\;",              # 命令注入
    r"\|\|",            # Shell 操作符
    r"&&",              # Shell 操作符
]


def validate_file_path(file_path: str) -> str:
    """
    校验文件路径安全性。

    Returns:
        规范化后的绝对路径

    Raises:
        ValueError: 路径不安全
    """
    abs_path = os.path.abspath(file_path)

    # 检查禁止模式
    for pattern in FORBIDDEN_PATTERNS:
        if re.search(pattern, file_path):
            raise ValueError(f"文件路径包含不安全模式: {pattern}")

    # 检查是否在白名单目录下
    if not any(abs_path.startswith(d) for d in ALLOWED_DIRECTORIES):
        raise ValueError(
            f"文件路径不在允许的目录中。"
            f"允许的目录: {ALLOWED_DIRECTORIES}"
        )

    return abs_path
```

---

## 7. 三级记忆存储与会话管理

### 7.1 架构设计

```
请求到达
    │
    ▼
┌──────────────┐   命中   ┌──────────────┐
│  Redis 缓存   │◀───────│  读取会话历史  │
│  (L1, 主存储) │         │              │
└──────┬───────┘         └──────────────┘
       │ 未命中/连接失败
       ▼
┌──────────────┐
│  内存 dict    │  ← L2 降级层
│  (L2, 降级)   │
└──────┬───────┘
       │ 异步写入
       ▼
┌──────────────┐
│  MySQL        │  ← L3 持久化层
│  (L3, 持久化)  │     (后台线程批量写入)
└──────────────┘
```

### 7.2 实现

```python
# app/memory/store.py
"""
三级记忆存储：Redis(L1) → 内存 dict(L2) → MySQL(L3)。
每层都有读/写/删除操作，上层失败自动降级。
"""
import json
import logging
import threading
from typing import List, Optional, Dict
from datetime import datetime

logger = logging.getLogger(__name__)


class ConversationMessage:
    """会话消息"""
    def __init__(self, role: str, content: str):
        self.role = role  # user / assistant / system
        self.content = content
        self.timestamp = datetime.now()

    def to_dict(self) -> dict:
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ConversationMessage":
        msg = cls(data["role"], data["content"])
        msg.timestamp = datetime.fromisoformat(data["timestamp"])
        return msg


# 内存存储（L2 降级层）
_memory_store: Dict[str, List[ConversationMessage]] = {}
_memory_lock = threading.Lock()


class MemoryStore:
    """三级记忆存储管理器"""

    def __init__(
        self,
        window_size: int = 20,  # 保留最近 N 轮对话
        redis_url: Optional[str] = None,
    ):
        self.window_size = window_size
        self._redis_available = False
        self._redis = None
        self._mysql_available = False

        # 尝试连接 Redis
        if redis_url:
            try:
                import redis
                self._redis = redis.from_url(redis_url, socket_connect_timeout=2)
                self._redis.ping()
                self._redis_available = True
                logger.info("Redis (L1) 连接成功")
            except Exception as e:
                logger.warning(f"Redis (L1) 不可用，使用内存降级 (L2): {e}")

    def _make_key(self, session_id: str, user_id: str) -> str:
        return f"chat:{user_id}:{session_id}"

    def _read_from_redis(self, key: str) -> Optional[List[ConversationMessage]]:
        """L1: Redis 读取"""
        if not self._redis_available or self._redis is None:
            return None
        try:
            raw = self._redis.get(key)
            if raw is None:
                return None
            data = json.loads(raw)
            return [ConversationMessage.from_dict(m) for m in data]
        except Exception as e:
            logger.warning(f"Redis 读取失败: {e}")
            self._redis_available = False
            return None

    def _write_to_redis(self, key: str, messages: List[ConversationMessage]):
        """L1: Redis 写入，带 TTL (24h)"""
        if not self._redis_available or self._redis is None:
            return
        try:
            data = json.dumps([m.to_dict() for m in messages], ensure_ascii=False)
            self._redis.setex(key, 86400, data)
        except Exception as e:
            logger.warning(f"Redis 写入失败: {e}")
            self._redis_available = False

    def _read_from_memory(self, key: str) -> Optional[List[ConversationMessage]]:
        """L2: 内存读取"""
        with _memory_lock:
            return _memory_store.get(key)

    def _write_to_memory(self, key: str, messages: List[ConversationMessage]):
        """L2: 内存写入（带窗口截断）"""
        with _memory_lock:
            _memory_store[key] = messages[-self.window_size * 2:]  # 保留 2 倍窗口

    def get_history(
        self,
        session_id: str,
        user_id: str,
    ) -> List[ConversationMessage]:
        """
        获取会话历史。按 L1 → L2 → 空列表 的顺序降级。
        """
        key = self._make_key(session_id, user_id)

        # 尝试 Redis
        messages = self._read_from_redis(key)
        if messages is not None:
            return messages[-self.window_size * 2:]

        # 降级到内存
        messages = self._read_from_memory(key)
        if messages is not None:
            logger.info(f"会话 {key[:20]}... 从 L2 内存读取")
            return messages[-self.window_size * 2:]

        logger.info(f"会话 {key[:20]}... 无历史记录（新会话）")
        return []

    def add_message(
        self,
        session_id: str,
        user_id: str,
        role: str,
        content: str,
    ):
        """添加一条消息到所有存储层"""
        key = self._make_key(session_id, user_id)

        # 获取现有历史
        history = self.get_history(session_id, user_id)
        history.append(ConversationMessage(role, content))

        # 同时写入所有层（各层独立处理失败）
        self._write_to_redis(key, history)
        self._write_to_memory(key, history)

        # MySQL 异步批量写入（不阻塞请求）
        self._schedule_mysql_persist(session_id, user_id, role, content)

    def clear_history(self, session_id: str, user_id: str):
        """清除会话历史"""
        key = self._make_key(session_id, user_id)
        if self._redis_available and self._redis:
            try:
                self._redis.delete(key)
            except Exception:
                pass
        with _memory_lock:
            _memory_store.pop(key, None)

    def _schedule_mysql_persist(
        self, session_id: str, user_id: str, role: str, content: str
    ):
        """异步持久化到 MySQL（简化实现：同步写入，可改为消息队列）"""
        # 生产环境建议使用 asyncio.Queue 或 Celery
        try:
            self._persist_to_mysql(session_id, user_id, role, content)
        except Exception as e:
            logger.debug(f"MySQL 持久化失败（不影响主流程）: {e}")

    def _persist_to_mysql(
        self, session_id: str, user_id: str, role: str, content: str
    ):
        """L3: MySQL 持久化"""
        from sqlalchemy import create_engine, text
        from app.config import settings
        try:
            engine = create_engine(settings.mysql_url, pool_pre_ping=True)
            with engine.connect() as conn:
                conn.execute(
                    text(
                        "INSERT INTO conversations (session_id, user_id, role, content) "
                        "VALUES (:sid, :uid, :role, :content)"
                    ),
                    {"sid": session_id, "uid": user_id, "role": role, "content": content},
                )
                conn.commit()
        except Exception as e:
            logger.debug(f"MySQL 写入失败: {e}")


# 全局单例
_memory_store_instance: Optional[MemoryStore] = None


def get_memory_store() -> MemoryStore:
    global _memory_store_instance
    if _memory_store_instance is None:
        from app.config import settings
        _memory_store_instance = MemoryStore(redis_url=settings.REDIS_URL)
    return _memory_store_instance
```

### 7.3 验证方式

```python
# 验证三级降级逻辑：
"""
1. Redis 正常 → get_history 应从 Redis 读取
2. 手动停止 Redis → get_history 应自动降级到内存
3. 服务重启后 → 内存清空，应从 MySQL 恢复（可选实现）
4. 窗口大小验证 → 超过 window_size 的消息应被截断
"""
```

---

## 8. 反思重试与自愈机制

### 8.1 失败分类与重试策略

```python
# app/agent/reflection.py
"""
反思重试模块：任务执行失败时，自动分析错误并尝试修复。
包含：失败分类、可重试判断、LLM 错误分析、指数退避。
"""
import logging
import time
from typing import Optional, Dict, Any
from enum import Enum
from langchain_openai import ChatOpenAI
from app.config import settings

logger = logging.getLogger(__name__)


class ErrorCategory(Enum):
    """错误分类"""
    TIMEOUT = "timeout"           # LLM 超时 → 可重试
    NETWORK = "network"           # 网络异常 → 可重试（指数退避）
    TOOL_ERROR = "tool_error"     # 工具执行异常 → 分析后决定
    PARAM_ERROR = "param_error"   # 参数错误 → 分析修正后重试
    PERMISSION = "permission"     # 权限不足 → 不重试
    NOT_FOUND = "not_found"       # 资源不存在 → 不重试
    UNKNOWN = "unknown"           # 未知错误 → 最多重试 1 次


# 可重试判断矩阵
RETRY_MATRIX = {
    ErrorCategory.TIMEOUT:     {"can_retry": True,  "max_retry": 3, "backoff": True},
    ErrorCategory.NETWORK:     {"can_retry": True,  "max_retry": 3, "backoff": True},
    ErrorCategory.TOOL_ERROR:  {"can_retry": True,  "max_retry": 2, "backoff": False},
    ErrorCategory.PARAM_ERROR: {"can_retry": True,  "max_retry": 2, "backoff": False},
    ErrorCategory.PERMISSION:  {"can_retry": False, "max_retry": 0, "backoff": False},
    ErrorCategory.NOT_FOUND:   {"can_retry": False, "max_retry": 0, "backoff": False},
    ErrorCategory.UNKNOWN:     {"can_retry": True,  "max_retry": 1, "backoff": False},
}


def categorize_error(error: Exception) -> ErrorCategory:
    """根据异常类型和消息分类"""
    msg = str(error).lower()

    if "timeout" in msg or "timed out" in msg:
        return ErrorCategory.TIMEOUT
    if any(kw in msg for kw in ["connection", "network", "refused", "reset"]):
        return ErrorCategory.NETWORK
    if "permission" in msg or "denied" in msg or "unauthorized" in msg:
        return ErrorCategory.PERMISSION
    if "not found" in msg or "no such file" in msg or "does not exist" in msg:
        return ErrorCategory.NOT_FOUND
    if any(kw in msg for kw in ["param", "argument", "invalid", "type error"]):
        return ErrorCategory.PARAM_ERROR

    # 检查是否为工具执行过程中的异常
    import traceback
    tb = traceback.format_exc()
    if "app/tools/" in tb:
        return ErrorCategory.TOOL_ERROR

    return ErrorCategory.UNKNOWN


REFLECTION_PROMPT = """\
你是一个任务调试专家。一个子任务执行失败了，请分析错误原因并给出修正方案。

## 子任务信息
- 任务描述: {task_description}
- 工具名称: {tool_name}
- 原始参数: {original_params}
- 错误信息: {error_message}
- 错误类型: {error_category}

## 请回答以下问题：
1. 错误原因分析（一句话）
2. 是否可以通过修改参数重试？(是/否)
3. 如果可以，修正后的参数是什么？（JSON 格式）

请严格按以下格式输出：
ANALYSIS: <原因分析>
CAN_RETRY: <是/否>
FIXED_PARAMS: <JSON 或 NONE>"""


class ReflectionHandler:
    """反思处理器"""

    def __init__(self, max_retry: int = 3):
        self.max_retry = max_retry
        self.retry_count: Dict[str, int] = {}  # task_id → 重试次数

    def analyze_and_fix(
        self,
        task,  # SubTask
        error_message: str,
        original_params: dict,
    ) -> Optional[dict]:
        """
        分析错误并尝试生成修正后的参数。

        Returns:
            修正后的参数 dict，如果不可重试或重试次数耗尽则返回 None
        """
        # 1. 检查重试次数
        count = self.retry_count.get(task.task_id, 0)
        if count >= self.max_retry:
            logger.warning(f"任务 {task.task_id} 已达最大重试次数 ({self.max_retry})，触发熔断")
            return None

        self.retry_count[task.task_id] = count + 1

        # 2. 分类错误
        try:
            error_category = categorize_error(Exception(error_message))
        except Exception:
            error_category = ErrorCategory.UNKNOWN

        # 3. 查重试矩阵
        matrix = RETRY_MATRIX[error_category]
        if not matrix["can_retry"]:
            logger.info(f"错误类型 {error_category.value} 不可重试，终止")
            return None

        # 4. 指数退避
        if matrix["backoff"]:
            wait = 2 ** count  # 1s, 2s, 4s
            logger.info(f"指数退避等待 {wait}s")
            time.sleep(wait)

        # 5. LLM 分析错误并修正参数
        try:
            return self._llm_reflect(task, error_message, error_category, original_params)
        except Exception as e:
            logger.warning(f"LLM 反思失败，使用简单重试: {e}")
            # 简单重试：原参数不变
            if error_category in (ErrorCategory.TIMEOUT, ErrorCategory.NETWORK):
                return original_params
            return None

    def _llm_reflect(
        self,
        task,
        error_message: str,
        error_category: ErrorCategory,
        original_params: dict,
    ) -> Optional[dict]:
        """使用 LLM 分析错误并生成修正参数"""
        llm = ChatOpenAI(
            model=settings.LLM_MODEL,
            api_key=settings.DASHSCOPE_API_KEY,
            base_url=settings.LLM_BASE_URL,
            temperature=0,
            timeout=settings.LLM_TIMEOUT,
        )

        prompt = REFLECTION_PROMPT.format(
            task_description=task.description,
            tool_name=task.tool_name,
            original_params=original_params,
            error_message=error_message,
            error_category=error_category.value,
        )

        response = llm.invoke(prompt).content

        # 解析 LLM 输出
        import re
        can_retry_match = re.search(r"CAN_RETRY:\s*(.+)", response)
        if can_retry_match and "否" in can_retry_match.group(1):
            return None

        params_match = re.search(r"FIXED_PARAMS:\s*(\{.+\})", response, re.DOTALL)
        if params_match:
            import json
            try:
                return json.loads(params_match.group(1))
            except json.JSONDecodeError:
                pass

        return None
```

### 8.2 验证方式

```python
# 反思重试机制的测试场景：
"""
1. 模拟 file_path 拼写错误 → LLM 应修正路径 → 重试成功
2. 模拟网络超时 → 应触发指数退避 → 最多重试 3 次
3. 模拟权限错误 → 应直接放弃，不重试
4. 模拟连续失败 3 次 → 应触发熔断
"""
```

---

## 9. 前后端服务实现

### 9.1 FastAPI 后端

```python
# main.py (项目唯一入口)
"""企业智能办公助手平台 — FastAPI 入口"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    logger.info("🚀 企业智能办公助手平台启动中...")
    # 预热：加载向量模型、连接数据库
    from app.rag.embedder import get_embedder
    get_embedder()  # 预加载 BGE 模型
    logger.info("✅ 所有服务就绪")
    yield
    logger.info("👋 应用关闭")


app = FastAPI(
    title="企业智能办公助手平台 API",
    description="基于 Multi-Agent 架构的企业智能办公平台",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应限制具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
from app.api import chat, knowledge, tools
app.include_router(chat.router, prefix="/api", tags=["对话"])
app.include_router(knowledge.router, prefix="/api/knowledge", tags=["知识库"])
app.include_router(tools.router, prefix="/api/tools", tags=["工具"])


@app.get("/api/health")
async def health_check():
    """健康检查"""
    return {
        "status": "ok",
        "version": "1.0.0",
        "llm_model": settings.LLM_MODEL,
    }
```

```python
# app/api/chat.py
"""对话 API — 流式 SSE 输出"""
import json
import asyncio
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from app.agent.executor import AgentEngine
from app.memory.store import get_memory_store
from app.tools.base import registry

router = APIRouter()


class ChatRequest(BaseModel):
    message: str = Field(..., description="用户消息")
    session_id: str = Field(default="default", description="会话 ID")
    user_id: str = Field(default="anonymous", description="用户 ID")


class ChatResponse(BaseModel):
    answer: str
    task_type: str = "simple"


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """
    对话接口（非流式）。

    对于简单问答即时返回；复杂任务等待执行完成后返回。
    """
    memory = get_memory_store()
    history = memory.get_history(req.session_id, req.user_id)

    # 构建带上下文的输入
    if history:
        context = "\n".join(
            f"[{m.role}]: {m.content}" for m in history[-6:]  # 最近 3 轮
        )
        full_input = f"对话历史：\n{context}\n\n用户最新问题：{req.message}"
    else:
        full_input = req.message

    # 获取所有工具并创建执行引擎
    tools = registry.list_tools()
    engine = AgentEngine(tools)

    # 执行
    from app.agent.router import classify_task
    task_type = classify_task(req.message)

    if task_type == "simple":
        answer = engine._run_simple(full_input)
    else:
        answer = await engine._run_complex(full_input)

    # 存储对话历史
    memory.add_message(req.session_id, req.user_id, "user", req.message)
    memory.add_message(req.session_id, req.user_id, "assistant", answer)

    return ChatResponse(answer=answer, task_type=task_type)


@router.post("/chat/stream")
async def chat_stream(req: ChatRequest):
    """
    流式对话接口（SSE）。

    使用 Server-Sent Events 实时推送 LLM 生成内容。
    """
    from app.config import settings
    from langchain_openai import ChatOpenAI

    async def event_generator():
        memory = get_memory_store()
        history = memory.get_history(req.session_id, req.user_id)
        context = ""
        if history:
            context = "\n".join(
                f"[{m.role}]: {m.content}" for m in history[-6:]
            )

        llm = ChatOpenAI(
            model=settings.LLM_MODEL,
            api_key=settings.DASHSCOPE_API_KEY,
            base_url=settings.LLM_BASE_URL,
            temperature=0.5,
            timeout=settings.LLM_TIMEOUT,
            streaming=True,
        )

        system_prompt = "你是一个企业智能办公助手。请简洁、准确地回答用户的问题。"
        messages = [{"role": "system", "content": system_prompt}]
        if context:
            messages.append({"role": "user", "content": f"对话历史：\n{context}"})
        messages.append({"role": "user", "content": req.message})

        full_answer = ""
        try:
            async for chunk in llm.astream([m for m in messages if m["role"] != "system"][-10:]):
                if chunk.content:
                    full_answer += chunk.content
                    yield f"data: {json.dumps({'content': chunk.content})}\n\n"
            yield f"data: {json.dumps({'done': True})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

        # 存储对话
        memory.add_message(req.session_id, req.user_id, "user", req.message)
        if full_answer:
            memory.add_message(req.session_id, req.user_id, "assistant", full_answer)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
```

```python
# app/api/knowledge.py
"""知识库 API"""
from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel
from typing import List
from app.rag.loader import UniversalDocumentLoader
from app.rag.splitter import split_documents
from app.rag.store import add_documents, delete_by_source
from app.rag.retriever import rag_qa_with_sources

router = APIRouter()


class QAResponse(BaseModel):
    answer: str
    sources: list[dict]


@router.post("/qa", response_model=QAResponse)
async def knowledge_qa(question: str):
    """知识问答接口"""
    result = rag_qa_with_sources(question)
    return QAResponse(**result)


@router.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    """上传文档到知识库"""
    import os
    import tempfile

    # 保存上传文件
    upload_dir = "data/documents"
    os.makedirs(upload_dir, exist_ok=True)

    file_path = os.path.join(upload_dir, file.filename)
    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    try:
        # 加载 → 分块 → 入库
        docs = UniversalDocumentLoader.load(file_path)
        chunks = split_documents(docs)
        count = add_documents(chunks)

        return {
            "status": "ok",
            "filename": file.filename,
            "chunks": count,
            "message": f"文档已成功入库，共 {count} 个文本块",
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"文档处理失败: {str(e)}")


@router.delete("/documents/{filename}")
async def delete_document(filename: str):
    """从知识库删除文档"""
    file_path = f"data/documents/{filename}"
    count = delete_by_source(file_path)
    return {"status": "ok", "deleted_chunks": count}
```

```python
# app/api/tools.py
"""工具 API"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.tools.base import registry

router = APIRouter()


@router.get("/list")
async def list_tools():
    """获取可用工具列表"""
    tools = registry.list_tools()
    return {
        "tools": [
            {"name": t.name, "description": t.description}
            for t in tools
        ]
    }


@router.post("/analyze")
async def analyze_data(file_path: str, action: str = "summary"):
    """数据分析接口"""
    tool = registry.get_tool("data_analyzer")
    if tool is None:
        raise HTTPException(status_code=404, detail="data_analyzer 工具未注册")
    result = tool._run(file_path=file_path, action=action)
    return {"result": result}
```

### 9.2 前端 (React 18 + Vite)

主前端为 React SPA (8个页面)，Streamlit 版本保留在 `frontend/` 兼容。

**启动 React 前端:**
```bash
cd frontend-react && npm install && npm run dev
# → http://localhost:5173
```

**React 技术栈:** Vite + Tailwind CSS v4 + Zustand 状态管理 + React Router v6
**页面:** 对话 / 历史 / 工具测试 / 知识库 / 监控 / 评测 / 设置 / 登录(SSO多入口)

```typescript
// frontend-react/src/stores/authStore.ts — 多Provider认证
export const useAuthStore = create<AuthStore>((set) => ({
  login: async (username, password) => { /* 本地JWT */ },
  loginLdap: async (username, password) => { /* LDAP域认证 */ },
  loginOidc: async () => { /* OIDC SSO跳转 */ },
  handleOidcCallback: async (code, state) => { /* OIDC回调 */ },
}));
```

**Streamlit 兼容版:**
```python
# frontend/app.py (保留)
"""Streamlit 前端主入口"""
import streamlit as st

st.set_page_config(
    page_title="企业智能办公助手",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 侧边栏
with st.sidebar:
    st.title("🤖 企业智能办公助手")
    st.markdown("---")
    page = st.radio(
        "导航",
        ["💬 智能对话", "🔧 工具测试", "📚 知识库管理", "⚙️ 偏好设置"],
        label_visibility="collapsed",
    )
    st.markdown("---")
    st.caption(f"Powered by 通义千问 | v1.0.0")

# 路由到对应页面
if page == "💬 智能对话":
    from frontend.pages import chat
    chat.show()
elif page == "🔧 工具测试":
    from frontend.pages import tool_test
    tool_test.show()
elif page == "📚 知识库管理":
    from frontend.pages import knowledge
    knowledge.show()
elif page == "⚙️ 偏好设置":
    from frontend.pages import settings
    settings.show()
```

```python
# frontend/pages/chat.py
"""智能对话页面"""
import streamlit as st
import requests
import json

API_BASE = "http://localhost:8000/api"


def show():
    st.title("💬 智能对话")

    # 初始化会话状态
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "session_id" not in st.session_state:
        import uuid
        st.session_state.session_id = str(uuid.uuid4())[:8]

    # 显示历史消息
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # 用户输入
    if prompt := st.chat_input("请输入您的问题..."):
        # 显示用户消息
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # 调用流式 API
        with st.chat_message("assistant"):
            placeholder = st.empty()
            full_response = ""

            try:
                resp = requests.post(
                    f"{API_BASE}/chat/stream",
                    json={
                        "message": prompt,
                        "session_id": st.session_state.session_id,
                        "user_id": "streamlit_user",
                    },
                    stream=True,
                    timeout=120,
                )

                for line in resp.iter_lines():
                    if line:
                        line = line.decode("utf-8")
                        if line.startswith("data: "):
                            data = json.loads(line[6:])
                            if "content" in data:
                                full_response += data["content"]
                                placeholder.markdown(full_response + "▌")
                            elif "done" in data:
                                placeholder.markdown(full_response)
                            elif "error" in data:
                                placeholder.error(f"错误: {data['error']}")

            except requests.exceptions.ConnectionError:
                placeholder.error("无法连接到后端服务，请确认 FastAPI 已启动")
            except Exception as e:
                placeholder.error(f"请求失败: {str(e)}")

        if full_response:
            st.session_state.messages.append(
                {"role": "assistant", "content": full_response}
            )
```

```python
# frontend/pages/knowledge.py
"""知识库管理页面"""
import streamlit as st
import requests

API_BASE = "http://localhost:8000/api"


def show():
    st.title("📚 知识库管理")

    tab1, tab2 = st.tabs(["📤 上传文档", "🔍 知识问答"])

    with tab1:
        st.subheader("上传企业文档")
        st.caption("支持格式: PDF、Word (.docx)、Excel (.xlsx)、TXT")

        uploaded_file = st.file_uploader(
            "选择文件",
            type=["pdf", "docx", "xlsx", "xls", "txt", "csv"],
        )

        if uploaded_file and st.button("上传到知识库", type="primary"):
            with st.spinner("正在处理文档..."):
                try:
                    files = {"file": (uploaded_file.name, uploaded_file.getvalue())}
                    resp = requests.post(f"{API_BASE}/knowledge/upload", files=files)
                    if resp.status_code == 200:
                        data = resp.json()
                        st.success(f"✅ {data['message']}")
                        st.json(data)
                    else:
                        st.error(f"上传失败: {resp.text}")
                except Exception as e:
                    st.error(f"请求失败: {e}")

    with tab2:
        st.subheader("知识问答测试")
        question = st.text_input("输入问题", placeholder="例如：公司年假政策是什么？")

        if question and st.button("查询"):
            with st.spinner("检索中..."):
                try:
                    resp = requests.post(
                        f"{API_BASE}/knowledge/qa",
                        params={"question": question},
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        st.markdown("### 📝 回答")
                        st.markdown(data["answer"])
                        st.markdown("### 📎 参考来源")
                        for src in data["sources"]:
                            st.caption(f"- {src['filename']} (页码: {src.get('page', 'N/A')})")
                    else:
                        st.error(f"查询失败: {resp.text}")
                except Exception as e:
                    st.error(f"请求失败: {e}")
```

### 9.3 启动命令

```bash
# 终端 1: 启动 FastAPI 后端
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# 终端 2: 启动 React 前端
cd frontend-react && npm run dev  # → http://localhost:5173

# 访问:
# - API 文档: http://localhost:8000/docs
# - 前端界面: http://localhost:8501
```

---

## 10. 测试、部署与运维

### 10.1 测试策略

```python
# tests/conftest.py
"""pytest 全局 fixtures"""
import pytest
from unittest.mock import Mock, patch


@pytest.fixture
def mock_llm():
    """模拟 LLM 响应，避免测试中调用真实 API"""
    with patch("langchain_openai.ChatOpenAI") as mock:
        instance = Mock()
        instance.invoke.return_value.content = "这是一个模拟的 LLM 回答。"
        mock.return_value = instance
        yield mock


@pytest.fixture
def sample_dataframe():
    import pandas as pd
    return pd.DataFrame({
        "月份": ["1月", "2月", "3月", "4月"],
        "销售额": [10000, 15000, 12000, 18000],
        "成本": [6000, 8000, 7000, 9000],
    })
```

```python
# tests/test_rag_retriever.py
"""RAG 检索模块测试"""
import pytest
from unittest.mock import patch, Mock
from app.rag.retriever import format_context
from langchain_core.documents import Document


def test_format_context():
    """测试文档上下文格式化"""
    docs = [
        Document(
            page_content="公司年假为每年 15 天。",
            metadata={"filename": "员工手册.pdf", "page": 3},
        ),
        Document(
            page_content="年假需提前 3 天申请。",
            metadata={"filename": "员工手册.pdf", "page": 4},
        ),
    ]
    result = format_context(docs)
    assert "员工手册.pdf" in result
    assert "第3页" in result
    assert "第4页" in result
    assert "15 天" in result
```

```python
# tests/test_tools.py
"""工具模块测试"""
import os
import pytest
import pandas as pd
from app.tools.data_analyzer import DataAnalyzerTool


class TestDataAnalyzer:
    def test_summary(self, tmp_path):
        """测试数据摘要生成"""
        # 创建测试文件
        df = pd.DataFrame({"A": [1, 2, 3], "B": [4, 5, 6]})
        file_path = os.path.join(tmp_path, "test.csv")
        df.to_csv(file_path, index=False)

        tool = DataAnalyzerTool()
        # 注意：实际测试需要文件在白名单目录中
        # 这里演示逻辑
        result = tool._load_data(file_path)
        assert len(result) == 3
        assert list(result.columns) == ["A", "B"]

    def test_clean_data_drop_duplicates(self):
        """测试去重"""
        df = pd.DataFrame({"A": [1, 1, 2, 3], "B": [4, 4, 5, 6]})
        tool = DataAnalyzerTool()
        cleaned = tool._clean_data(df)
        assert len(cleaned) == 3  # 1 对重复被移除

    def test_clean_data_fill_missing_with_median(self):
        """测试中位数填充"""
        df = pd.DataFrame({"A": [1.0, None, 3.0, 4.0], "B": [5.0, 6.0, None, 8.0]})
        tool = DataAnalyzerTool()
        cleaned = tool._clean_data(df)
        # A 列: 中位数 = (1+3+4)/3 = 3.0，但 pandas median 会忽略 NaN
        # 实际: median of [1,3,4] = 3.0
        assert cleaned["A"].isna().sum() == 0
        assert cleaned["B"].isna().sum() == 0


def test_oa_tool_mock():
    """测试 OA 工具 Mock 模式"""
    from app.tools.oa_crm import OATool
    tool = OATool()
    result = tool._query_mock("list_approvals", None)
    assert "OA-001" in result
    assert "年假申请" in result

    result = tool._query_mock("query_by_user", "张三")
    assert "年假申请" in result
    # 不应该包含李四的审批
    assert "报销申请" not in result
```

```bash
# 运行测试
pytest tests/ -v --tb=short

# 覆盖率
pytest tests/ --cov=app --cov-report=html
```

### 10.2 Docker 部署

```dockerfile
# Dockerfile
FROM python:3.12-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .

# 创建数据目录
RUN mkdir -p data/documents data/reports data/chroma

EXPOSE 8000

# 启动命令
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

```yaml
# docker-compose.yml (生产环境)
version: '3.8'

services:
  redis:
    image: redis:7-alpine
    restart: unless-stopped
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 3

  mysql:
    image: mysql:8.0
    restart: unless-stopped
    ports:
      - "3306:3306"
    environment:
      MYSQL_ROOT_PASSWORD: ${MYSQL_ROOT_PASSWORD}
      MYSQL_DATABASE: enterprise_ai_office
      MYSQL_USER: ${MYSQL_USER}
      MYSQL_PASSWORD: ${MYSQL_PASSWORD}
    volumes:
      - mysql_data:/var/lib/mysql
      - ./scripts/init.sql:/docker-entrypoint-initdb.d/init.sql
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "localhost"]
      interval: 10s
      timeout: 5s
      retries: 5

  chromadb:
    image: chromadb/chroma:latest
    restart: unless-stopped
    ports:
      - "8001:8000"
    volumes:
      - chroma_data:/chroma/chroma
    environment:
      - IS_PERSISTENT=TRUE
      - ANONYMIZED_TELEMETRY=FALSE

  backend:
    build: .
    restart: unless-stopped
    ports:
      - "8000:8000"
    env_file:
      - .env
    depends_on:
      redis:
        condition: service_healthy
      mysql:
        condition: service_healthy
    volumes:
      - ./data:/app/data

  frontend:
    build:
      context: .
      dockerfile: Dockerfile.frontend
    restart: unless-stopped
    ports:
      - "8501:8501"
    depends_on:
      - backend
    environment:
      - API_BASE=http://backend:8000/api

volumes:
  redis_data:
  mysql_data:
  chroma_data:
```

### 10.3 日志与监控

```python
# 在 main.py 中添加请求日志中间件
import time
from fastapi import Request

@app.middleware("http")
async def log_requests(request: Request, call_next):
    """请求日志 + 耗时统计"""
    start = time.time()
    response = await call_next(request)
    duration = time.time() - start
    logger.info(
        f"{request.method} {request.url.path} "
        f"→ {response.status_code} ({duration:.2f}s)"
    )
    return response
```

### 10.4 环境变量检查清单

```bash
# 部署前确认：
# ☐ LLM_API_KEY — DeepSeek API Key
# ☐ LLM_MODEL — 模型选择 (qwen-turbo / qwen-plus / qwen-max)
# ☐ MYSQL_ROOT_PASSWORD — MySQL root 密码
# ☐ MYSQL_PASSWORD — 应用数据库密码
# ☐ APP_ENV=production — 生产模式
# ☐ LOG_LEVEL=WARNING — 生产日志级别
```

---

## 附录 A: 常见问题排查

| 问题 | 可能原因 | 排查步骤 |
|------|---------|---------|
| LLM 调用超时 | 网络/API 限流 | 检查 `LLM_TIMEOUT` 设置，确认 API Key 有效 |
| ChromaDB 连接失败 | 服务未启动 | `docker-compose ps chromadb` 确认状态 |
| 向量检索无结果 | 文档未入库/chunk 过大 | 检查 `add_documents` 日志，调整 `chunk_size` |
| Redis 降级频繁 | Redis 负载高/内存不足 | 检查 Redis 内存使用，增加 `maxmemory` |
| 流式输出中断 | SSE 连接超时 | 检查 nginx/代理的超时配置 |
| 中文图表乱码 | 缺少中文字体 | 安装 `fonts-noto-cjk` 或指定已安装字体 |

## 附录 B: 后续迭代方向

1. **多模态支持**：接入图片理解，支持截图提问（如 "分析这张数据图表"）
2. **权限系统**：集成企业 SSO/LDAP，按角色控制工具和文档访问权限
3. **Agent 协作**：多个 Agent 并行处理不同子系统任务，最终汇总
4. **性能升级**：ChromaDB → Milvus，支持千万级文档向量检索
5. **移动端**：企业微信/钉钉机器人接入，随时随地使用
6. **评测体系**：建立自动化评测集，持续监控 RAG 准确率和 Agent 任务成功率

## 附录 C: GitHub 优秀参考项目

以下项目在架构设计、LangGraph 编排、RAG 实现等方面提供了重要参考：

### C.1 同架构项目（LangGraph + Multi-Agent + 办公场景）

| 项目 | Stars | 核心亮点 | 借鉴点 |
|------|-------|---------|--------|
| [DATAGEN](https://github.com/starpig1129/DATAGEN) | ~1.7k | 8 Agent 协作，LangGraph StateGraph 编排，自动数据分析→报告生成 | 多 Agent 角色分工、StateGraph 节点设计、NoteTaker 上下文压缩 |
| [agentflow](https://github.com/Aparnap2/agentflow) | ~200 | LangGraph 虚拟办公室，CEO/Manager/Sales 等多角色 Agent | 角色化 Agent 设计、Neo4j 私有记忆 + Qdrant 全局记忆双通道 |
| [ai-assistant-hub-langgraph](https://github.com/JoshPola96/ai-assistant-hub-langgraph) | ~50 | Streamlit + LangGraph + ChromaDB 多 Agent 助手 | 前端交互模式、条件路由与 fallback 策略 |

### C.2 RAG 与企业知识库

| 项目 | Stars | 核心亮点 | 借鉴点 |
|------|-------|---------|--------|
| [Agentic_RAG_LangGraph_AiSearch](https://github.com/tianputao/Agentic_RAG_LangGraph_AiSearch) | — | Azure AI Search 混合检索 + LangGraph 多步编排 | Query Planning → Retrieval → Generation 流程设计 |
| [langgraph-chat-app](https://github.com/manishkatyan/langgraph-chat-app) | — | BM25 + Vector + MMR 三路混合检索 + Cohere 重排序 | 混合检索策略、Arize 观测性集成 |

### C.3 AI 数据分析与报告生成

| 项目 | Stars | 核心亮点 | 借鉴点 |
|------|-------|---------|--------|
| [interactive-data-analysis](https://github.com/lunara-kim/interactive-data-analysis) | — | LangGraph + OpenAI 交互式数据分析，Pandas Agent + 图表 | 数据分析 Agent 的交互流程设计 |
| [deep-research-agent](https://github.com/tarun7r/deep-research-agent) | ~171 | 4 Agent 研究系统，引文可信度评分，多格式报告输出 | 熔断器模式、checkpoint 持久化、引文追溯 |

### C.4 关键设计模式总结

从以上项目中提炼出以下可复用模式：

1. **StateGraph 类型化** (DATAGEN, agentflow)：用 TypedDict 严格定义 AgentState，避免运行时状态字段混乱
2. **条件边分流** (ai-assistant-hub)：`add_conditional_edges` + 枚举返回类型，直观声明路由逻辑
3. **并行 Fan-out** (所有项目)：利用 LangGraph `Send()` API 或 `asyncio.gather` 实现同层子任务并行
4. **Checkpoint 恢复** (deep-research-agent)：`MemorySaver`(开发) / `SqliteSaver`(生产)，断点续传
5. **Human-in-the-loop** (DATAGEN)：敏感操作前 `interrupt()` 暂停，等待人工审批
6. **自愈与熔断** (deep-research-agent)：错误计数 + 指数退避 + 最大重试后熔断
7. **混合检索** (langgraph-chat-app)：BM25 + 向量 + MMR 三路召回 → 重排序 → Top-N
8. **Mock/Real 分离** (本系统独创)：外部 API 工具双模式，开发演示不依赖真实环境

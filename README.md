# 🤖 基于 Agent 的企业智能办公助手平台

[![Python](https://img.shields.io/badge/Python-3.12-blue.svg)](https://www.python.org/)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.3.34-orange.svg)](https://github.com/langchain-ai/langgraph)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688.svg)](https://fastapi.tiangolo.com/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.44-FF4B4B.svg)](https://streamlit.io/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

面向企业员工的智能办公平台，基于 **LangGraph + LangChain** 与通义千问构建 Multi-Agent 协作架构。集成数据分析、文档自动生成、OA/CRM 对接、RAG 知识问答四大核心能力。

---

## 🏗 系统架构

```
用户 (Streamlit) → FastAPI 网关 → LangGraph Agent 编排层 → 工具执行层
                                    ├── classify (条件路由)
                                    ├── plan (LLM 拆解)
                                    ├── execute (并行执行)
                                    ├── aggregate (结果聚合)
                                    └── simple_react (快速问答)
                                    ↓
                              基础设施层 (ChromaDB / Redis / MySQL)
```

## 📁 项目结构

```
enterprise-ai-office/
├── README.md                       # 本文件
├── resume-optimized.md             # 优化后的简历项目描述
├── tech-doc-enterprise-ai-office.md # 从零开发技术文档（10章）
├── docker-compose.yml              # 一键启动
├── Dockerfile                      # 应用镜像
├── requirements.txt                # Python 依赖
├── .env.example                    # 环境变量模板
├── app/                            # FastAPI 主应用
│   ├── agent/                      # LangGraph Agent 引擎
│   ├── rag/                        # RAG 知识问答
│   ├── tools/                      # 插件化工具系统
│   ├── memory/                     # 三级记忆存储
│   └── api/                        # RESTful API 路由
├── frontend/                       # Streamlit 前端
└── tests/                          # 测试
```

## 🚀 快速开始

### 前提条件

- Python 3.12+
- Docker & Docker Compose
- DeepSeek API Key ([申请地址](https://platform.deepseek.com/))

### 1. 克隆项目

```bash
git clone <your-repo-url>
cd enterprise-ai-office
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入你的 LLM_API_KEY (DeepSeek)
```

### 3. 启动基础设施

```bash
docker-compose up -d redis mysql chromadb
```

### 4. 安装依赖

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 5. 验证环境

```bash
python verify_env.py
```

### 6. 启动服务

```bash
# 终端 1: 启动后端
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 终端 2: 启动前端
streamlit run frontend/app.py --server.port 8501
```

### 7. 访问

- 前端界面: http://localhost:8501
- API 文档 (Swagger): http://localhost:8000/docs
- 健康检查: http://localhost:8000/api/health

## 📖 文档导航

| 文档 | 说明 |
|------|------|
| [resume-optimized.md](./resume-optimized.md) | 优化后的项目简历描述（含量化指标） |
| [tech-doc-enterprise-ai-office.md](./tech-doc-enterprise-ai-office.md) | 从零开发技术文档（10章完整指南） |

## 🎯 核心功能

| 功能 | 说明 | 状态 |
|------|------|:----:|
| 💬 智能对话 | 基于 LangGraph 的双路径 Agent，支持多轮上下文记忆 | ✅ |
| 📚 RAG 知识问答 | 多格式文档上传 → 向量检索 → 带来源追溯的回答 | ✅ |
| 📊 数据分析 | Excel/CSV 读取 → 清洗 → 统计 → 图表 → Word 报告 | ✅ |
| 🔗 OA/CRM 对接 | Mock/Real 双模式，外部 API 不可用时自动降级 | ✅ |
| 🔄 流式输出 | SSE 实时推送 LLM 生成内容 | ✅ |
| 🛡️ 降级兜底 | LLM 失败→规则引擎 / Redis 宕机→内存 / API 不可用→Mock | ✅ |
| 🔁 反思重试 | 失败自动分析 + 指数退避重试 + 熔断保护 | ✅ |

## 🛠 技术栈

| 层级 | 技术 |
|------|------|
| **Agent 框架** | LangGraph, LangChain, ReAct |
| **大模型** | 通义千问 (Qwen) |
| **向量检索** | BGE-Small-ZH, ChromaDB |
| **后端** | FastAPI, Redis, MySQL |
| **前端** | Streamlit |
| **数据处理** | Pandas, Matplotlib, python-docx |
| **工程化** | Docker, pytest, Swagger |

## 📊 设计指标

| 指标 | 目标 |
|------|:----:|
| 简单问答响应 | < 2s |
| 复杂报表生成 | < 5min |
| RAG 问答准确率 | ≥ 85% |
| 并发用户 | 50+ |
| 核心链路可用性 | 99.9% |
| 任务自愈率 | > 60% |

## 🔍 运行测试

```bash
# 运行所有测试
pytest tests/ -v

# 覆盖率报告
pytest tests/ --cov=app --cov-report=html
```

## 📦 生产部署

```bash
# 完整部署
docker-compose up -d

# 查看日志
docker-compose logs -f backend

# 停止
docker-compose down
```

## 🤝 参考项目

- [DATAGEN](https://github.com/starpig1129/DATAGEN) — LangGraph 多 Agent 数据分析 (1.7k⭐)
- [agentflow](https://github.com/Aparnap2/agentflow) — LangGraph 虚拟办公室
- [ai-assistant-hub-langgraph](https://github.com/JoshPola96/ai-assistant-hub-langgraph) — Streamlit + ChromaDB 多 Agent 助手
- [deep-research-agent](https://github.com/tarun7r/deep-research-agent) — 多 Agent 深度研究系统

## 📄 License

MIT License

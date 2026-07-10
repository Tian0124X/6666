# 企业智能办公助手

基于 FastAPI、LangGraph 和 React 的企业智能办公平台，提供智能对话、知识库检索、数据分析、OA/CRM 查询和 SSO 集成。

## 入口与环境

| 使用场景 | 主要文件 | 说明 |
| --- | --- | --- |
| 本地开发 | `docker-compose.local.yml`、`scripts/setup-local.ps1` | 仅启动 Redis、MySQL、PostgreSQL 和 ChromaDB；后端、前端在本机热更新。 |
| 线上部署 | `docker-compose.prod.yml`、`Dockerfile.backend`、`frontend-react/Dockerfile` | ECS 上运行的完整容器栈。 |
| 持续部署 | `.github/workflows/deploy.yml`、`scripts/server-init.sh`、`scripts/server-deploy.sh` | 推送 `master` 后通过 GitHub Actions 部署到 ECS。 |
| 应用代码 | `main.py`、`app/`、`frontend-react/` | FastAPI 后端与 React 前端。 |

详细操作见 [本地开发](docs/local-development.md) 与 [生产部署](docs/deployment.md)。

## 本地启动

```powershell
Copy-Item .env.example .env
# 编辑 .env，填入 LLM_API_KEY 等必要配置
powershell -ExecutionPolicy Bypass -File scripts/setup-local.ps1
```

或手动启动：

```powershell
docker compose -f docker-compose.local.yml up -d
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
Set-Location frontend-react
npm ci
npm run dev
```

- 后端：http://localhost:8000
- API 文档：http://localhost:8000/docs
- 前端：http://localhost:5173

## 项目结构

```text
app/                 FastAPI 业务模块（Agent、RAG、认证、工具等）
frontend-react/      React 前端和 Nginx 生产镜像
scripts/             本地初始化、模型下载、ECS 初始化与部署脚本
data/                运行时上传文件、报告与索引（不提交版本库）
tests/               后端自动化测试
docs/                架构、开发和部署文档
```

## 常用检查

```powershell
pytest
Set-Location frontend-react
npm run lint
npm run build
```

默认演示账户：`admin` / `admin123`，`demo` / `demo123`。生产环境请在首次部署后立即修改默认凭据和所有 `.env` 密钥。

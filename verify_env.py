"""环境验证脚本 — 确认所有依赖和服务就绪
用法: python verify_env.py
"""
import sys
import os

# Windows GBK 编码兼容
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


def header(text: str):
    print(f"\n{'=' * 50}")
    print(f"  {text}")
    print('=' * 50)


def check(msg: str, ok: bool):
    icon = "✅" if ok else "❌"
    print(f"  {icon} {msg}")
    return ok


all_ok = True

# ===== 1. Python 版本 =====
header("1. Python 版本")
v = sys.version_info
all_ok &= check(f"Python {v.major}.{v.minor}.{v.micro}", (v.major, v.minor) >= (3, 12))

# ===== 2. 核心依赖导入 =====
header("2. 核心依赖")
modules = [
    ("langchain", "LangChain"),
    ("langgraph", "LangGraph"),
    ("langchain_openai", "LangChain-OpenAI"),
    ("fastapi", "FastAPI"),
    ("uvicorn", "Uvicorn"),
    ("pydantic", "Pydantic"),
    ("streamlit", "Streamlit"),
    ("redis", "Redis"),
    ("sqlalchemy", "SQLAlchemy"),
    ("pandas", "Pandas"),
    ("matplotlib", "Matplotlib"),
    ("docx", "python-docx"),
    ("chromadb", "ChromaDB"),
    ("sentence_transformers", "Sentence-Transformers"),
    ("PyPDF2", "PyPDF2"),
    ("httpx", "httpx"),
    ("dotenv", "python-dotenv"),
    ("tenacity", "tenacity"),
    ("pytest", "pytest"),
]
for mod_name, display in modules:
    try:
        __import__(mod_name)
        all_ok &= check(display, True)
    except ImportError:
        all_ok &= check(display, False)

# ===== 3. 项目 imports =====
header("3. 项目模块")
project_modules = [
    ("app.config", "config.Settings"),
    ("app.models.request", "models.request"),
    ("app.models.response", "models.response"),
    ("app.agent.state", "agent.state"),
    ("main", "main (FastAPI)"),
]
for mod, name in project_modules:
    try:
        __import__(mod)
        all_ok &= check(name, True)
    except Exception as e:
        all_ok &= check(f"{name} → {e}", False)

# ===== 4. 环境变量 =====
header("4. 环境变量")
from app.config import settings
all_ok &= check(f"LLM_MODEL = {settings.LLM_MODEL}", True)
all_ok &= check(f"APP_ENV = {settings.APP_ENV}", True)
has_key = bool(settings.LLM_API_KEY) and not settings.LLM_API_KEY.startswith("sk-your-")
all_ok &= check("LLM_API_KEY 已配置", has_key)
if not has_key:
    print("    ⚠️  请将 .env.example 复制为 .env 并填入真实 API Key")

# ===== 5. 外部服务连接 =====
header("5. 外部服务")

# Redis
try:
    import redis
    r = redis.from_url(settings.REDIS_URL, socket_connect_timeout=2)
    r.ping()
    all_ok &= check("Redis 连接", True)
except Exception as e:
    all_ok &= check(f"Redis ({e})", False)

# ChromaDB
try:
    import chromadb
    client = chromadb.HttpClient(host=settings.CHROMA_HOST, port=settings.CHROMA_PORT)
    client.heartbeat()
    all_ok &= check("ChromaDB 连接", True)
except Exception as e:
    all_ok &= check(f"ChromaDB ({e})", False)

# ===== 汇总 =====
header("结果")
if all_ok:
    print("  ✅ 所有检查通过！环境就绪。")
    print()
    print("  启动命令:")
    print("    uvicorn main:app --host 0.0.0.0 --port 8000 --reload")
    print("    streamlit run frontend/app.py --server.port 8501")
else:
    print("  ❌ 部分检查未通过，请按上述提示修复。")
    print()
    print("  常见修复:")
    print("    - 安装依赖: pip install -r requirements.txt")
    print("    - 启动服务: docker-compose up -d redis mysql chromadb")
    print("    - 配置 API Key: cp .env.example .env && 编辑 .env")

sys.exit(0 if all_ok else 1)

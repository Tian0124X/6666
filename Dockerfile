FROM python:3.12-slim

WORKDIR /app

# 系统依赖
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# BGE 模型预下载到镜像内 (可选，跳过则首次启动下载)
# 国内用镜像: HF_ENDPOINT=https://hf-mirror.com
ARG HF_ENDPOINT=""
RUN if [ -n "$HF_ENDPOINT" ]; then \
      python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-zh-v1.5')"; \
    fi

# 应用代码
COPY . .

# 数据目录
RUN mkdir -p data/documents data/reports data/chroma

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

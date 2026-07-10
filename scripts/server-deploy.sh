#!/bin/bash
# ==========================================
# 在 ECS 服务器上执行此脚本
# ==========================================
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[OK]${NC} $*"; }
log_step()  { echo -e "\n${BLUE}=== $* ===${NC}"; }

# ============================================
# 0. 预下载 PyTorch CPU wheel (宿主机下载快 10MB/s，Docker 内慢)
# ============================================
log_step "0/4 预下载 PyTorch CPU wheel (约 17 秒)"
cd /opt/eao/build
TORCH_WHEEL="torch-2.13.0+cpu-cp312-cp312-manylinux_2_28_x86_64.whl"
if [ -f "$TORCH_WHEEL" ]; then
    log_info "wheel 已存在，跳过下载"
else
    curl -L -o "$TORCH_WHEEL" \
        "https://download.pytorch.org/whl/cpu/torch-2.13.0%2Bcpu-cp312-cp312-manylinux_2_28_x86_64.whl"
    log_info "$TORCH_WHEEL 下载完成 ($(du -h "$TORCH_WHEEL" | cut -f1))"
fi

# ============================================
# 1. 构建 Backend 镜像
# ============================================
log_step "1/4 构建 Backend 镜像 (约 5-15 分钟)"
cd /opt/eao/build
docker build -f Dockerfile.backend -t eao/eao-backend:latest .
log_info "Backend 镜像构建完成"

# ============================================
# 2. 构建 Frontend 镜像
# ============================================
log_step "2/4 构建 Frontend 镜像 (约 2-5 分钟)"
docker build -t eao/eao-frontend:latest frontend-react/
log_info "Frontend 镜像构建完成"

# ============================================
# 3. 拉取基础镜像 + 启动
# ============================================
log_step "3/4 启动所有服务"
cd /opt/eao
echo ">>> 拉取基础镜像..."
docker compose -f docker-compose.prod.yml pull redis mysql chromadb postgres 2>&1 || true
echo ">>> 启动容器..."
docker compose -f docker-compose.prod.yml up -d --remove-orphans
echo ">>> 等待 30 秒..."
sleep 30
echo ">>> 容器状态:"
docker compose -f docker-compose.prod.yml ps

# ============================================
# 4. 健康检查
# ============================================
log_step "4/4 健康检查"
if curl -sf http://localhost/api/health; then
    echo ""
    log_info "Deploy SUCCESS!"
else
    echo ""
    echo -e "${RED}Health check FAILED. Check logs:${NC}"
    echo "  docker compose -f docker-compose.prod.yml logs"
fi

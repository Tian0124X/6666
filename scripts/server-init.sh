#!/bin/bash
# ==========================================
# 新 ECS 服务器初始化脚本
# 用法: 在服务器上以 root 执行
#   curl -o init.sh https://raw.githubusercontent.com/<user>/<repo>/master/scripts/server-init.sh
#   或手动 scp 上传后: chmod +x init.sh && ./init.sh
# ==========================================
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[OK]${NC} $*"; }
log_step()  { echo -e "\n${BLUE}=== $* ===${NC}"; }
log_warn()  { echo -e "${RED}[!!]${NC} $*"; }

# ============================================
# 1. 安装 Docker
# ============================================
log_step "1/6 安装 Docker"
if command -v docker &>/dev/null; then
    log_info "Docker 已安装: $(docker --version)"
else
    # 阿里云 Docker CE 镜像源 (国内加速)
    curl -fsSL https://mirrors.aliyun.com/docker-ce/linux/ubuntu/gpg | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://mirrors.aliyun.com/docker-ce/linux/ubuntu $(lsb_release -cs) stable" \
        | tee /etc/apt/sources.list.d/docker.list > /dev/null
    apt-get update && apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    systemctl enable docker && systemctl start docker
    log_info "Docker 安装完成: $(docker --version)"
fi

# ============================================
# 2. 配置 Docker 镜像加速 (阿里云)
# ============================================
log_step "2/6 配置 Docker 镜像加速"
mkdir -p /etc/docker
cat > /etc/docker/daemon.json <<'EOF'
{
  "registry-mirrors": [
    "https://mirror.ccs.tencentyun.com",
    "https://docker.mirrors.ustc.edu.cn"
  ],
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}
EOF
systemctl daemon-reload && systemctl restart docker
log_info "Docker 镜像加速已配置"

# ============================================
# 3. 生成 SSH Key (用于 GitHub Actions 连接)
# ============================================
log_step "3/6 生成 SSH Key"
mkdir -p /root/.ssh && chmod 700 /root/.ssh
if [ ! -f /root/.ssh/github_actions ]; then
    ssh-keygen -t ed25519 -C "github-actions-deploy" -f /root/.ssh/github_actions -N ""
    log_info "SSH 密钥对已生成"
else
    log_info "SSH 密钥对已存在，跳过"
fi

# 将公钥添加到 authorized_keys (允许 GitHub Actions 以此 key 登录)
cat /root/.ssh/github_actions.pub >> /root/.ssh/authorized_keys
# 去重
sort -u /root/.ssh/authorized_keys -o /root/.ssh/authorized_keys
chmod 600 /root/.ssh/authorized_keys

echo ""
echo "========================================"
echo "  请复制下面的 Private Key 到 GitHub Secrets"
echo "  名称: ECS_SSH_KEY"
echo "========================================"
cat /root/.ssh/github_actions
echo "========================================"

# ============================================
# 4. 安装 Git & 拉取代码
# ============================================
log_step "4/6 拉取项目代码"
REPO_URL="${1:-git@github.com:yuanzihao/eao.git}"
PROJECT_DIR="/opt/eao"

if [ -d "$PROJECT_DIR/.git" ]; then
    log_info "项目目录已存在，执行 git pull"
    cd "$PROJECT_DIR"
    git pull origin master
else
    mkdir -p /opt/eao
    # 先用 HTTPS 克隆（无需配 SSH key 到 GitHub）
    git clone https://github.com/yuanzihao/eao.git /opt/eao/build 2>/dev/null || \
    git clone "$REPO_URL" /opt/eao/build

    # 创建 docker-compose 和数据目录的符号链接
    ln -sf /opt/eao/build/docker-compose.prod.yml /opt/eao/docker-compose.prod.yml
    ln -sf /opt/eao/build/scripts/server-deploy.sh /opt/eao/server-deploy.sh
fi

log_info "代码拉取完成"

# ============================================
# 5. 创建 .env 文件 (如果不存在)
# ============================================
log_step "5/6 配置环境变量"
if [ ! -f /opt/eao/.env ]; then
    cat > /opt/eao/.env <<'ENVEOF'
# ======== 数据库 ========
MYSQL_ROOT_PASSWORD=ChangeMe123!
MYSQL_USER=eao_user
MYSQL_PASSWORD=ChangeMe123!
PG_USER=eao_user
PG_PASSWORD=ChangeMe123!

# ======== LLM API ========
# 替换为你的 API Key
LLM_API_KEY=sk-your-api-key-here
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini

# ======== 前端 ========
FRONTEND_URL=http://112.124.66.91

# ======== 应用 ========
APP_ENV=production
LOG_LEVEL=INFO
ENVEOF
    log_warn ".env 文件已创建，请编辑 /opt/eao/.env 填入真实 API Key!"
else
    log_info ".env 已存在，跳过"
fi

# ============================================
# 6. 确保 deploy 脚本可执行
# ============================================
log_step "6/6 设置脚本权限"
sed -i 's/\r$//' /opt/eao/server-deploy.sh 2>/dev/null || true
chmod +x /opt/eao/server-deploy.sh
log_info "脚本权限设置完成"

# ============================================
# 完成
# ============================================
echo ""
echo "========================================"
echo "  ✅ 服务器初始化完成!"
echo "========================================"
echo ""
echo "接下来你需要做:"
echo ""
echo "1. 配置 GitHub Secrets (Settings → Secrets → Actions):"
echo "   ECS_HOST     = 112.124.66.91"
echo "   ECS_USER     = root"
echo "   ECS_SSH_KEY  = (上面输出的私钥)"
echo ""
echo "2. 编辑环境变量:"
echo "   vi /opt/eao/.env"
echo ""
echo "3. 测试部署:"
echo "   /opt/eao/server-deploy.sh"
echo "========================================"

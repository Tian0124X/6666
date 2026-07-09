#!/bin/bash
# ==========================================
# 企业智能办公助手平台 — ECS 服务器首次初始化
#
# 用法: scp scripts/setup-server.sh root@YOUR_ECS_IP:/tmp/
#       ssh root@YOUR_ECS_IP "chmod +x /tmp/setup-server.sh && sudo /tmp/setup-server.sh"
# ==========================================
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[✓]${NC} $*"; }
log_warn()  { echo -e "${YELLOW}[!]${NC} $*"; }
log_error() { echo -e "${RED}[✗]${NC} $*"; }
log_step()  { echo -e "\n${BLUE}━━━ $* ━━━${NC}"; }

# ============================================
# 检测操作系统
# ============================================
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS=$ID
    OS_VERSION=$VERSION_ID
else
    log_error "无法检测操作系统。支持: Ubuntu 20.04+, Debian 11+, CentOS 7+"
    exit 1
fi
log_info "操作系统: $OS $OS_VERSION"

# ============================================
# 1. 安装 Docker
# ============================================
log_step "1/6 安装 Docker"

if command -v docker &>/dev/null; then
    log_info "Docker 已安装: $(docker --version)"
else
    case $OS in
        ubuntu|debian)
            apt-get update -qq
            apt-get install -y -qq ca-certificates curl gnupg lsb-release
            # 阿里云 Docker 镜像 (国内加速)
            curl -fsSL https://mirrors.aliyun.com/docker-ce/linux/$OS/gpg \
                | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg
            echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://mirrors.aliyun.com/docker-ce/linux/$OS $(lsb_release -cs) stable" \
                > /etc/apt/sources.list.d/docker.list
            apt-get update -qq
            apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin
            ;;
        centos|rhel)
            yum install -y yum-utils
            yum-config-manager --add-repo https://mirrors.aliyun.com/docker-ce/linux/centos/docker-ce.repo
            yum install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
            ;;
        *)
            log_error "不支持的操作系统: $OS"
            exit 1
            ;;
    esac
    systemctl enable docker
    systemctl start docker
    log_info "Docker 安装完成"
fi

# ============================================
# 2. Docker 优化配置
# ============================================
log_step "2/6 配置 Docker"

if [ ! -f /etc/docker/daemon.json ]; then
    cat > /etc/docker/daemon.json << 'EOF'
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  },
  "registry-mirrors": [
    "https://registry.cn-hangzhou.aliyuncs.com"
  ]
}
EOF
    systemctl restart docker
    log_info "Docker 日志轮转已配置 (每容器 ≤3×10MB)"
fi

# ============================================
# 3. 创建目录结构
# ============================================
log_step "3/6 创建目录结构"

mkdir -p /opt/eao/data/{documents,reports,chroma,models}
mkdir -p /opt/eao/backups
mkdir -p /opt/eao/nginx/ssl

log_info "目录结构:"
ls -la /opt/eao/

# ============================================
# 4. 生产环境配置
# ============================================
log_step "4/6 配置环境变量"

if [ ! -f /opt/eao/.env ]; then
    JWT_SECRET=$(openssl rand -hex 32 2>/dev/null || python3 -c "import secrets; print(secrets.token_hex(32))")
    cat > /opt/eao/.env << ENVEOF
# ==========================================
# 企业智能办公助手平台 — 生产环境配置
# 请修改 <CHANGE_ME> 的值
# ==========================================

# --- LLM (DeepSeek) ---
LLM_API_KEY=<CHANGE_ME>
LLM_MODEL=deepseek-chat
LLM_BASE_URL=https://api.deepseek.com
LLM_TIMEOUT=60

# --- HuggingFace (国内镜像加速) ---
HF_ENDPOINT=https://hf-mirror.com

# --- Redis (Docker 内部, 无需改) ---
REDIS_URL=redis://redis:6379/0

# --- MySQL ---
MYSQL_HOST=mysql
MYSQL_PORT=3306
MYSQL_USER=eao_user
MYSQL_PASSWORD=<CHANGE_ME>
MYSQL_DATABASE=enterprise_ai_office
MYSQL_ROOT_PASSWORD=<CHANGE_ME>

# --- ChromaDB ---
CHROMA_HOST=chromadb
CHROMA_PORT=8000

# --- PostgreSQL + pgvector ---
PG_HOST=postgres
PG_PORT=5432
PG_DATABASE=enterprise_ai_office
PG_USER=eao_user
PG_PASSWORD=<CHANGE_ME>

# --- JWT ---
JWT_SECRET=$JWT_SECRET

# --- 应用 ---
APP_ENV=production
LOG_LEVEL=INFO
MAX_RETRY=3

# --- 前端域名 (CORS) ---
FRONTEND_URL=http://<YOUR_DOMAIN_OR_IP>

# --- OA/CRM (可选) ---
OA_API_URL=
CRM_API_URL=

# --- SSO (可选，默认不启用) ---
LDAP_ENABLED=false
OIDC_ENABLED=false

# --- ACR (部署拉镜像用) ---
ACR_REGISTRY=<CHANGE_ME>
ACR_NAMESPACE=<CHANGE_ME>
ENVEOF
    log_warn "请编辑 /opt/eao/.env 填入真实配置!  生成 JWT_SECRET 已自动填入($JWT_SECRET)"
else
    log_info ".env 已存在，跳过"
fi

# ============================================
# 5. 防火墙
# ============================================
log_step "5/6 配置防火墙"

if command -v ufw &>/dev/null; then
    ufw allow 22/tcp &>/dev/null || true
    ufw allow 80/tcp &>/dev/null || true
    ufw allow 443/tcp &>/dev/null || true
    ufw --force enable &>/dev/null || true
    log_info "UFW 已配置 (22, 80, 443)"
elif command -v firewall-cmd &>/dev/null; then
    firewall-cmd --permanent --add-service=ssh &>/dev/null || true
    firewall-cmd --permanent --add-service=http &>/dev/null || true
    firewall-cmd --permanent --add-service=https &>/dev/null || true
    firewall-cmd --reload &>/dev/null || true
    log_info "firewalld 已配置 (22, 80, 443)"
else
    log_warn "未检测到防火墙工具"
fi

log_warn "!!! 请在阿里云 ECS 安全组中放行: 22, 80, 443 端口 !!!"

# ============================================
# 6. 上传必需文件
# ============================================
log_step "6/6 部署文件检查"

if [ -f /opt/eao/docker-compose.prod.yml ]; then
    log_info "docker-compose.prod.yml ✓"
else
    log_warn "docker-compose.prod.yml 不存在，请从项目上传:"
    log_warn "  scp docker-compose.prod.yml root@<IP>:/opt/eao/"
fi

# ============================================
# 完成
# ============================================
echo ""
echo "╔══════════════════════════════════════════╗"
echo "║         服务器初始化完成!                ║"
echo "╚══════════════════════════════════════════╝"
echo ""
echo "后续步骤:"
echo ""
echo "  1. 编辑环境变量:"
echo "     vim /opt/eao/.env"
echo ""
echo "  2. 上传必需文件 (在本地项目目录执行):"
echo "     scp docker-compose.prod.yml root@<IP>:/opt/eao/"
echo "     scp scripts/init.sql scripts/init-pg.sql root@<IP>:/opt/eao/scripts/"
echo ""
echo "  3. 手动首次启动测试:"
echo "     cd /opt/eao"
echo "     docker compose -f docker-compose.prod.yml up -d"
echo ""
echo "  4. 验证:"
echo "     curl http://localhost/api/health"
echo ""
echo "  5. 配置 GitHub Actions Secrets:"
echo "     ACR_REGISTRY, ACR_NAMESPACE, ACR_USERNAME, ACR_PASSWORD"
echo "     ECS_HOST, ECS_USER, ECS_SSH_KEY"
echo ""
echo "  6. 配置域名 + HTTPS (可选):"
echo "     域名 A 记录指向 ECS IP"
echo "     apt install -y certbot"
echo "     certbot certonly --standalone -d your-domain.com"
echo ""

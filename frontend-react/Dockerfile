# ==========================================
# 企业智能办公助手平台 — 前端生产镜像
# 多阶段构建: Node 编译 → Nginx 服务
# 构建: docker build -t eao-frontend .
# ==========================================

# ====== Stage 1: React 编译 ======
FROM node:20-alpine AS builder

WORKDIR /app

# 依赖层缓存
COPY package*.json ./
RUN npm ci --registry=https://registry.npmmirror.com

# 源码 + 构建
COPY . .
RUN npm run build

# ====== Stage 2: Nginx 服务 ======
FROM nginx:1.27-alpine

# 复制构建产物
COPY --from=builder /app/dist /usr/share/nginx/html

# 复制 Nginx 配置
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
    CMD wget -qO- http://localhost/ || exit 1

CMD ["nginx", "-g", "daemon off;"]

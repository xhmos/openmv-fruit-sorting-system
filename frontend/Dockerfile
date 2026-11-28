# ---------- 第一阶段：Node 打包前端 ----------
FROM node:20-slim AS builder

WORKDIR /app/frontend

# 先拷依赖清单，利用层缓存
COPY package.json ./
# 国内镜像源安装依赖
RUN npm install --registry=https://registry.npmmirror.com

# 拷贝前端源码并打包
COPY . ./
RUN npm run build

# ---------- 第二阶段：Nginx 托管静态文件 ----------
FROM nginx:1.25-alpine

# 删除默认站点配置
RUN rm /etc/nginx/conf.d/default.conf

# 拷入自定义 Nginx 配置（静态资源 + 反代后端）
COPY nginx.conf /etc/nginx/conf.d/default.conf

# 拷入打包产物
COPY --from=builder /app/frontend/dist /usr/share/nginx/html

# 网关层审计日志目录（挂载到宿主机，供后端安全中心读取）
RUN mkdir -p /var/log/nginx/audit

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]

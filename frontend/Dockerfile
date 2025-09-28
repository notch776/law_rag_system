FROM node:20.19.0-slim AS build-stage

WORKDIR /app

# 复制依赖文件
COPY package*.json ./
RUN npm install  --verbose --registry https://registry.npmmirror.com

# 复制前端代码
COPY . .
RUN npm run build  # 构建生产包

# 生产环境用 Nginx 部署
FROM nginx:stable-alpine as production-stage
COPY --from=build-stage /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
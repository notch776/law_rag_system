# backend/Dockerfile
# 基础镜像：Python 3.9（轻量且兼容多数依赖）
FROM python:3.9-slim

# 设置工作目录
WORKDIR /app

# 复制依赖文件并安装
COPY requirements.txt .
COPY pip.conf /etc/pip.conf
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目代码（排除不必要文件，通过 .dockerignore）
COPY . .

# 暴露后端服务端口（FastAPI 默认 8000）
EXPOSE 8000

# 启动命令：用 uvicorn 启动服务，允许外部访问
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
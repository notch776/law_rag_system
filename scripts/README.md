# 本地端到端测试脚本

## 一键启动

```bash
./scripts/start_all.sh
```

启动内容：

- MongoDB: `localhost:27017`，本地二进制和数据目录 `.local/mongodb-data`
- Redis: `localhost:6379`，本地 Homebrew 进程和数据目录 `.local/redis`
- Neo4j: `localhost:7474` / `bolt://localhost:7687`，本地 Homebrew 进程
- Elasticsearch: `http://localhost:9200`，当前机器没有本地 ES 二进制，因此复用/创建 `es-ragchat` Docker 容器
- Backend: `http://localhost:8000`
- Frontend: `http://localhost:5173`

## 分步启动

```bash
./scripts/start_dbs.sh
./scripts/start_backend.sh
./scripts/start_frontend.sh
```

## 检查服务

```bash
./scripts/check_services.sh
curl http://localhost:8000/health
```

## 停止服务

```bash
./scripts/stop_all.sh
```

仅停止数据库：

```bash
./scripts/stop_dbs.sh
```

## 环境变量

统一环境变量入口：

```bash
source scripts/env.local.sh
```

核心配置：

- `LLM_MODEL=qwen3.6-max-preview`
- `SMALL_LLM_MODEL=qwen3.6-flash`
- `EMBEDDING_MODEL=tongyi-embedding-vision-plus-2026-03-06`
- `ES_INDEX=new_qiyefa`
- `DOCS_FOLDER=$PROJECT_ROOT/backend/rag/data`

`backend/rag/.env` 会最后加载，因此当前真实 `DASHSCOPE_API_KEY` 会覆盖 `backend/.env` 中的占位值。

## 日志位置

```text
.local/logs/mongodb.log
.local/logs/redis.log
.local/logs/neo4j.log
.local/logs/backend.log
.local/logs/frontend.log
```

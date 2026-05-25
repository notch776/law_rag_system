from dataclasses import dataclass
from pathlib import Path
import os
from dotenv import dotenv_values


BASE_DIR = Path(__file__).resolve().parents[2]
PROJECT_DIR = BASE_DIR.parent


def _load_env():
    merged = {}
    for path in [PROJECT_DIR / ".env", BASE_DIR / ".env", BASE_DIR / "rag" / ".env"]:
        if path.exists():
            merged.update({k: v for k, v in dotenv_values(path).items() if v is not None})
    merged.update(os.environ)
    return merged


_ENV = _load_env()


def _get(name, default=""):
    value = _ENV.get(name, default)
    return value.strip() if isinstance(value, str) else value


def _get_bool(name, default=False):
    raw = str(_get(name, str(default))).lower()
    return raw in {"1", "true", "yes", "on"}


def _resolve_path(value, default):
    raw = value or default
    path = Path(raw)
    if path.is_absolute():
        return str(path)
    return str(PROJECT_DIR / path)


@dataclass(frozen=True)
class Settings:
    app_name: str = "企业法律咨询 RAG 系统"
    app_env: str = _get("APP_ENV", "local")
    cors_origins: tuple = ("http://localhost:5173", "http://127.0.0.1:5173")

    dashscope_api_key: str = _get("DASHSCOPE_API_KEY", "")
    llm_model: str = _get("LLM_MODEL", "qwen3.6-max-preview")
    small_llm_model: str = _get("SMALL_LLM_MODEL", "qwen3.6-flash")
    embedding_model: str = _get("EMBEDDING_MODEL", "tongyi-embedding-vision-plus-2026-03-06")
    dashscope_base_url: str = _get("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")

    es_host: str = _get("ES_HOST", "http://localhost:9200")
    es_index: str = _get("ES_INDEX", _get("INDEX_NAME", "legal_corpus")).replace(" ", "")
    docs_folder: str = _resolve_path(_get("DOCS_FOLDER", ""), str(BASE_DIR / "rag" / "data"))

    mongodb_url: str = _get("MONGODB_URL", "mongodb://localhost:27017")
    mongodb_database: str = _get("MONGODB_DATABASE", _get("DATABASE_NAME", "rag_system"))
    conversations_collection: str = _get("CONVERSATIONS_COLLECTION", _get("COLLECTION_NAME", "chat_history"))
    summaries_collection: str = _get("SUMMARIES_COLLECTION", "conversation_summaries")

    redis_host: str = _get("REDIS_HOST", "localhost")
    redis_port: int = int(_get("REDIS_PORT", "6379"))
    redis_db: int = int(_get("REDIS_DB", "0"))
    short_memory_window: int = int(_get("SHORT_MEMORY_WINDOW", "5"))
    short_memory_ttl_seconds: int = int(_get("SHORT_MEMORY_TTL_SECONDS", "3600"))
    summary_interval: int = int(_get("SUMMARY_INTERVAL", "6"))

    neo4j_uri: str = _get("NEO4J_URI", "bolt://localhost:7687")
    neo4j_auth: str = _get("NEO4J_AUTH", "neo4j/Gl20031010")
    long_memory_category_limit: int = int(_get("LONG_MEMORY_CATEGORY_LIMIT", "5"))
    long_memory_category_threshold: float = float(_get("LONG_MEMORY_CATEGORY_THRESHOLD", "0.8"))
    long_memory_history_threshold: float = float(_get("LONG_MEMORY_HISTORY_THRESHOLD", "0.5"))
    long_memory_doc_threshold: float = float(_get("LONG_MEMORY_DOC_THRESHOLD", "0.9"))

    rerank_enabled: bool = _get_bool("RERANK_ENABLED", True)
    rerank_provider: str = _get("RERANK_PROVIDER", "dashscope")
    rerank_model_name: str = _get("RERANK_MODEL_NAME", "qwen3-rerank")
    rerank_endpoint: str = _get("RERANK_ENDPOINT", "https://dashscope.aliyuncs.com/compatible-api/v1/reranks")
    rerank_model_path: str = _get("RERANK_MODEL_PATH", str(BASE_DIR / "rag" / "rerank_model"))
    fusion_top_k: int = int(_get("FUSION_TOP_K", "10"))
    rerank_top_n: int = int(_get("RERANK_TOP_N", "5"))
    docs_per_intent: int = int(_get("DOCS_PER_INTENT", _get("RERANK_TOP_N", "5")))


settings = Settings()

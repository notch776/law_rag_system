import json
import logging
from typing import Any, Dict, List
import redis
from app.core.config import settings

logger = logging.getLogger(__name__)


class RedisRepository:
    def __init__(self):
        self.client = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            db=settings.redis_db,
            decode_responses=True,
        )

    def _key(self, conversation_id: str) -> str:
        return f"memory:short:{conversation_id}"

    def append_memory(self, conversation_id: str, item: Dict[str, Any]):
        try:
            key = self._key(conversation_id)
            self.client.rpush(key, json.dumps(item, ensure_ascii=False))
            self.client.ltrim(key, -settings.short_memory_window, -1)
            self.client.expire(key, settings.short_memory_ttl_seconds)
        except Exception as exc:
            logger.warning("写入 Redis 短期记忆失败: %s", exc)

    def get_recent(self, conversation_id: str) -> List[Dict[str, Any]]:
        try:
            values = self.client.lrange(self._key(conversation_id), 0, -1)
            return [json.loads(v) for v in values]
        except Exception as exc:
            logger.warning("读取 Redis 短期记忆失败: %s", exc)
            return []

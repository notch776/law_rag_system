import json
import logging
from typing import Any, Dict, List, Optional
import requests
from app.core.config import settings

logger = logging.getLogger(__name__)


class ElasticsearchRepository:
    def __init__(self):
        self.host = settings.es_host.rstrip("/")
        self.index = settings.es_index

    def _url(self, suffix: str) -> str:
        return f"{self.host}/{self.index}{suffix}"

    def health(self) -> bool:
        try:
            resp = requests.get(f"{self.host}/_cluster/health", timeout=3)
            return resp.status_code == 200
        except Exception:
            return False

    def search_knn(self, embedding: Optional[List[float]], top_k: int = 10) -> List[Dict[str, Any]]:
        if not embedding:
            return []
        body = {
            "knn": {"field": "embedding", "query_vector": embedding, "k": top_k, "num_candidates": max(50, top_k * 5)},
            "fields": ["content", "filename", "law_name", "chapter", "article_id", "chunk_index"],
            "_source": False,
        }
        return self._search(body, "dense")

    def search_bm25(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        body = {
            "query": {"match": {"content": {"query": query}}},
            "fields": ["content", "filename", "law_name", "chapter", "article_id", "chunk_index"],
            "_source": False,
            "size": top_k,
        }
        return self._search(body, "bm25")

    def search_rule_article(self, article_id: str, top_k: int = 10) -> List[Dict[str, Any]]:
        should = [
            {"term": {"article_id": article_id}},
            {"match_phrase": {"content": article_id}},
        ]
        body = {
            "query": {"bool": {"should": should, "minimum_should_match": 1}},
            "fields": ["content", "filename", "law_name", "chapter", "article_id", "chunk_index"],
            "_source": False,
            "size": top_k,
        }
        return self._search(body, "rule")

    def search_rule_chapter(self, chapter: str, top_k: int = 10) -> List[Dict[str, Any]]:
        body = {
            "query": {"bool": {"should": [{"term": {"chapter": chapter}}, {"match_phrase": {"filename": f"公司法{chapter}.docx"}}], "minimum_should_match": 1}},
            "fields": ["content", "filename", "law_name", "chapter", "article_id", "chunk_index"],
            "_source": False,
            "size": top_k,
        }
        return self._search(body, "rule")

    def _search(self, body: Dict[str, Any], channel: str) -> List[Dict[str, Any]]:
        try:
            resp = requests.post(self._url("/_search"), headers={"Content-Type": "application/json"}, data=json.dumps(body), timeout=15)
            if resp.status_code != 200:
                logger.warning("ES %s 检索失败: %s %s", channel, resp.status_code, resp.text[:200])
                return []
            hits = resp.json().get("hits", {}).get("hits", [])
            return [self._hit_to_doc(hit, channel) for hit in hits]
        except Exception as exc:
            logger.warning("ES %s 检索异常: %s", channel, exc)
            return []

    def _hit_to_doc(self, hit: Dict[str, Any], channel: str) -> Dict[str, Any]:
        fields = hit.get("fields", {})
        def first(name, default=""):
            value = fields.get(name, [default])
            return value[0] if isinstance(value, list) and value else default
        return {
            "id": hit.get("_id", ""),
            "content": first("content"),
            "filename": first("filename"),
            "law_name": first("law_name", "中华人民共和国公司法"),
            "chapter": first("chapter"),
            "article_id": first("article_id"),
            "chunk_index": first("chunk_index", 0),
            "score": float(hit.get("_score") or 0.0),
            "channel": channel,
        }

import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from cn2an import an2cn
from app.core.config import settings
from app.repositories.es_repo import ElasticsearchRepository
from app.schemas.chat import Citation, IntentAnalysis
from app.services.model_service import ModelService
from app.services.reranker import Reranker

logger = logging.getLogger(__name__)


@dataclass
class RetrievalResult:
    citations: List[Citation]
    query_vector: Optional[List[float]] = None
    intent_vectors: List[List[float]] = field(default_factory=list)
    intent_queries: List[str] = field(default_factory=list)
    intent_names: List[str] = field(default_factory=list)


class RetrievalService:
    def __init__(self, model_service: ModelService):
        self.model = model_service
        self.es = ElasticsearchRepository()
        self.reranker = Reranker()

    def retrieve_for_analysis(self, analysis: IntentAnalysis, top_n: int = None) -> RetrievalResult:
        docs = []
        primary_query_vector = None
        intent_vectors = []
        intent_queries = []
        intent_names = []
        intents = analysis.intents or []
        top_n = top_n or settings.docs_per_intent
        for idx, intent in enumerate(intents, 1):
            query = intent.rewritten_query
            per_intent_docs, query_vector = self.retrieve_one(query, top_k=settings.fusion_top_k, top_n=top_n)
            if primary_query_vector is None:
                primary_query_vector = query_vector
            if query_vector:
                intent_vectors.append(query_vector)
            intent_queries.append(query)
            intent_names.append(intent.intent_name)
            for doc in per_intent_docs:
                doc["intent_id"] = intent.intent_id or f"I{idx}"
            docs.extend(per_intent_docs)
        return RetrievalResult(
            citations=self._dedupe_to_citations(docs),
            query_vector=primary_query_vector,
            intent_vectors=intent_vectors,
            intent_queries=intent_queries,
            intent_names=intent_names,
        )

    def retrieve_for_query(self, query: str, top_n: int) -> RetrievalResult:
        docs, query_vector = self.retrieve_one(query, top_k=settings.fusion_top_k, top_n=top_n)
        return RetrievalResult(citations=self._dedupe_to_citations(docs), query_vector=query_vector)

    def retrieve_rrf_only(self, query: str, top_k: int = None, top_n: int = 3) -> Tuple[List[Dict], Optional[List[float]]]:
        top_k = top_k or settings.fusion_top_k
        embedding = self.model.embed_text(query)
        dense = self.es.search_knn(embedding, top_k=top_k)
        bm25 = self.es.search_bm25(query, top_k=top_k)
        rule = self._rule_search(query, top_k=top_k)
        fused = self._rrf([dense, bm25, rule], top_k=top_k)
        logger.info(
            "Normal RRF 检索完成: query=%s dense=%d bm25=%d rule=%d fused=%d output=%d",
            query[:40],
            len(dense),
            len(bm25),
            len(rule),
            len(fused),
            len(fused[:top_n]),
        )
        return fused[:top_n], embedding

    def retrieve_one(self, query: str, top_k: int = None, top_n: int = None) -> Tuple[List[Dict], Optional[List[float]]]:
        top_k = top_k or settings.fusion_top_k
        top_n = top_n or settings.rerank_top_n
        embedding = self.model.embed_text(query)
        dense = self.es.search_knn(embedding, top_k=top_k)
        bm25 = self.es.search_bm25(query, top_k=top_k)
        rule = self._rule_search(query, top_k=top_k)
        fused = self._rrf([dense, bm25, rule], top_k=top_k)
        logger.info("检索粗排完成: query=%s dense=%d bm25=%d rule=%d fused=%d", query[:40], len(dense), len(bm25), len(rule), len(fused))
        reranked = self.reranker.rerank(query, fused, top_n=top_n)
        logger.info("Rerank 完成: query=%s output=%d", query[:40], len(reranked))
        return reranked, embedding

    def _rule_search(self, query: str, top_k: int) -> List[Dict]:
        results = []
        article = self._extract_article(query)
        if article:
            results.extend(self.es.search_rule_article(article, top_k=top_k))
        chapter = self._extract_chapter(query)
        if chapter:
            results.extend(self.es.search_rule_chapter(chapter, top_k=top_k))
        return results

    def _extract_article(self, query: str):
        m = re.search(r"第([\d一二三四五六七八九十百千万零]+)条", query)
        if not m:
            return None
        raw = m.group(1)
        if raw.isdigit():
            return f"第{an2cn(int(raw))}条"
        return f"第{raw}条"

    def _extract_chapter(self, query: str):
        m = re.search(r"第([\d一二三四五六七八九十百千万零]+)章", query)
        if not m:
            return None
        raw = m.group(1)
        if raw.isdigit():
            return f"第{an2cn(int(raw))}章"
        return f"第{raw}章"

    def _rrf(self, result_sets: List[List[Dict]], top_k: int = 10, k: int = 60) -> List[Dict]:
        scores = defaultdict(float)
        docs = {}
        for results in result_sets:
            for rank, doc in enumerate(results):
                doc_id = doc.get("id") or doc.get("content", "")[:80]
                docs[doc_id] = doc
                scores[doc_id] += 1.0 / (k + rank + 1)
        ordered = sorted(scores, key=scores.get, reverse=True)
        fused = []
        for doc_id in ordered[:top_k]:
            item = docs[doc_id].copy()
            item["score"] = scores[doc_id]
            item["channel"] = "rrf"
            fused.append(item)
        return fused

    def _dedupe_to_citations(self, docs: List[Dict]) -> List[Citation]:
        seen = set()
        citations = []
        for doc in docs:
            key = doc.get("id") or (doc.get("filename"), doc.get("article_id"), doc.get("content", "")[:50])
            if key in seen:
                continue
            seen.add(key)
            citations.append(Citation(
                citation_id=str(len(citations) + 1),
                law_name=doc.get("law_name") or "中华人民共和国公司法",
                article_id=doc.get("article_id") or "",
                content=doc.get("content") or "",
                filename=doc.get("filename") or "",
                score=float(doc.get("score") or 0.0),
                intent_id=doc.get("intent_id"),
            ))
        return citations

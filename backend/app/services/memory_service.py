import logging
from typing import Dict, List, Optional
import numpy as np
from py2neo import Graph, Node, Relationship
from app.core.config import settings
from app.repositories.mongo_repo import MongoRepository
from app.repositories.redis_repo import RedisRepository
from app.schemas.chat import Citation
from app.services.model_service import ModelService

logger = logging.getLogger(__name__)


def cosine(vec1, vec2):
    a = np.array(vec1, dtype=float)
    b = np.array(vec2, dtype=float)
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    return float(np.dot(a, b) / denom) if denom else 0.0


class MemoryService:
    def __init__(self, mongo: MongoRepository, redis_repo: RedisRepository, model: ModelService):
        self.mongo = mongo
        self.redis = redis_repo
        self.model = model
        self.graph = None
        try:
            if "/" in settings.neo4j_auth:
                user, pwd = settings.neo4j_auth.split("/", 1)
            else:
                user, pwd = "neo4j", settings.neo4j_auth
            self.graph = Graph(settings.neo4j_uri, auth=(user, pwd))
        except Exception as exc:
            logger.warning("Neo4j 不可用，长期记忆降级: %s", exc)

    async def build_context(
        self,
        conversation_id: str,
        query_vector,
        long_limit: int = 3,
        long_answer_chars: int = 300,
        include_long_docs: bool = True,
    ) -> str:
        parts = []
        recent = self.redis.get_recent(conversation_id)
        if recent:
            lines = ["【短期记忆】"]
            for item in recent:
                lines.append(f"问题: {item.get('question', '')}")
                lines.append(f"回答: {self._extract_key_conclusion(item.get('answer', ''), 300)}")
            parts.append("\n".join(lines))
        summary = await self.mongo.get_summary(conversation_id)
        if summary and summary.get("summary_text"):
            parts.append(f"【中期摘要记忆】\n{summary['summary_text'][:1200]}")
        long_items = self.read_long(conversation_id, query_vector, limit=long_limit)
        if long_items:
            lines = ["【长期图记忆】"]
            for item in long_items:
                lines.append(f"历史问题: {item.get('q', '')}")
                lines.append(f"关键结论: {self._extract_key_conclusion(item.get('a', ''), long_answer_chars)}")
                if include_long_docs and item.get("D"):
                    lines.append(f"历史检索依据: {item.get('D', '')[:300]}")
            parts.append("\n".join(lines))
        return "\n\n".join(parts)

    def _extract_key_conclusion(self, answer: str, limit: int = 200) -> str:
        marker = "【结论与建议】"
        text = answer or ""
        start = text.find(marker)
        if start >= 0:
            return text[start:start + limit]
        return text[:limit]

    async def build_short_context(self, conversation_id: str, limit: int = 3) -> str:
        recent = self.redis.get_recent(conversation_id)
        if limit > 0:
            recent = recent[-limit:]
        if not recent:
            return ""
        lines = ["【短期记忆】"]
        for item in recent:
            lines.append(f"问题: {item.get('question', '')}")
            lines.append(f"回答: {self._extract_key_conclusion(item.get('answer', ''), 300)}")
        return "\n".join(lines)

    def read_long(self, conversation_id: str, query_vector, limit: int = 3) -> List[Dict]:
        if self.graph is None or not query_vector:
            return []
        try:
            categories = list(self.graph.nodes.match("Category", conv_id=conversation_id))
            scored = []
            for node in categories:
                if node.get("u_j"):
                    scored.append((cosine(query_vector, node["u_j"]), node))
            scored.sort(key=lambda x: x[0], reverse=True)
            if not scored or scored[0][0] < settings.long_memory_category_threshold:
                return []
            category = scored[0][1]
            histories = []
            rels = self.graph.match((category, None), r_type="CONTAINS")
            for rel in rels:
                history = rel.end_node
                if history.get("v_i"):
                    sim = cosine(query_vector, history["v_i"])
                    if sim >= settings.long_memory_history_threshold:
                        item = {
                            "q": history.get("q", ""),
                            "a": history.get("a", ""),
                            "similarity": sim,
                        }
                        if sim >= settings.long_memory_doc_threshold:
                            item["D"] = history.get("D", "")
                        histories.append(item)
            histories.sort(key=lambda x: x["similarity"], reverse=True)
            return histories[:limit]
        except Exception as exc:
            logger.warning("读取 Neo4j 长期记忆失败: %s", exc)
            return []

    async def maybe_mid_summary(self, conversation_id: str):
        turns = await self.mongo.count_user_turns(conversation_id)
        if turns == 0 or turns % settings.summary_interval != 0:
            return
        doc = await self.mongo.get_conversation(conversation_id)
        if not doc:
            return
        messages = doc.get("messages", [])[-settings.summary_interval * 2:]
        text = "\n".join([f"{m.get('role')}: {m.get('content')}" for m in messages])
        prompt = "请将以下法律咨询对话压缩为 JSON 摘要，字段包括 case_facts, confirmed_slots, missing_slots, legal_issues, cited_articles, given_advice, next_questions。"
        summary_text = self.model.call_small_text([
            {"role": "system", "content": prompt},
            {"role": "user", "content": text},
        ], fallback="{}")
        await self.mongo.upsert_summary(conversation_id, {"conversation_id": conversation_id, "summary_text": summary_text})

    def build_memory_vector(self, original_vector: Optional[List[float]], intent_vectors: List[List[float]]) -> Optional[List[float]]:
        valid_intents = [np.array(vec, dtype=float) for vec in intent_vectors or [] if vec]
        if original_vector and valid_intents:
            original = np.array(original_vector, dtype=float)
            same_dim_intents = [vec for vec in valid_intents if vec.shape == original.shape]
            if same_dim_intents:
                intent_mean = np.mean(same_dim_intents, axis=0)
                return (original * 0.6 + intent_mean * 0.4).tolist()
        if original_vector:
            return original_vector
        if valid_intents:
            return np.mean(valid_intents, axis=0).tolist()
        return None

    def mean_vector(self, vectors: List[List[float]]) -> Optional[List[float]]:
        valid = [np.array(vec, dtype=float) for vec in vectors or [] if vec]
        if not valid:
            return None
        first_shape = valid[0].shape
        same_dim = [vec for vec in valid if vec.shape == first_shape]
        if not same_dim:
            return None
        return np.mean(same_dim, axis=0).tolist()

    def write_short(self, conversation_id: str, qa_id: str, question: str, answer: str, citations: List[Citation]):
        self.redis.append_memory(conversation_id, {
            "qa_id": qa_id,
            "question": question,
            "answer": answer,
            "citations": [c.model_dump() for c in citations],
        })

    def write_long(
        self,
        conversation_id: str,
        qa_id: str,
        question: str,
        answer: str,
        citations: List[Citation],
        question_vector,
        original_vector=None,
        intent_vectors=None,
        intent_queries=None,
        intent_names=None,
        scenario: str = "general",
    ):
        if self.graph is None or not question_vector:
            return
        try:
            categories = list(self.graph.nodes.match("Category", conv_id=conversation_id))
            best_node = None
            best_sim = 0.0
            for node in categories:
                if node.get("u_j"):
                    sim = cosine(question_vector, node["u_j"])
                    if sim > best_sim:
                        best_sim = sim
                        best_node = node
            if best_node is None or (best_sim < settings.long_memory_category_threshold and len(categories) < settings.long_memory_category_limit):
                best_node = Node("Category", id=f"{conversation_id}-C{len(categories)+1}", name=f"类别{len(categories)+1}", u_j=question_vector, conv_id=conversation_id, count=0)
                self.graph.create(best_node)
            docs = "\n".join([c.content for c in citations])
            history_props = {
                "qa_id": qa_id,
                "q": question,
                "a": answer,
                "D": docs,
                "v_i": question_vector,
                "v_original": original_vector,
                "v_intent_mean": self.mean_vector(intent_vectors or []),
                "intent_queries": intent_queries or [],
                "intent_names": intent_names or [],
                "scenario": scenario or "general",
                "conv_id": conversation_id,
            }
            hist = Node("History", **{key: value for key, value in history_props.items() if value is not None})
            self.graph.create(hist)
            self.graph.create(Relationship(best_node, "CONTAINS", hist))
            count = int(best_node.get("count") or 0)
            old = best_node.get("u_j") or question_vector
            new_center = ((np.array(old) * count + np.array(question_vector)) / (count + 1)).tolist()
            best_node["u_j"] = new_center
            best_node["count"] = count + 1
            self.graph.push(best_node)
        except Exception as exc:
            logger.warning("写入 Neo4j 长期记忆失败: %s", exc)

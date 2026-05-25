import logging
from pathlib import Path
from typing import Dict, List
from importlib import import_module
import requests
from app.core.config import settings

logger = logging.getLogger(__name__)


class Reranker:
    def __init__(self):
        self.available = False
        self.device = "cpu"
        self.tokenizer = None
        self.model = None
        if not settings.rerank_enabled:
            logger.info("Rerank 已关闭，使用 RRF 结果")
            return
        self.provider = settings.rerank_provider.lower()
        if self.provider == "dashscope":
            self.available = bool(settings.dashscope_api_key)
            if self.available:
                logger.info("Rerank 使用 DashScope 模型: %s", settings.rerank_model_name)
            else:
                logger.warning("DASHSCOPE_API_KEY 为空，Rerank 降级使用 RRF")
            return
        if self.provider == "none":
            logger.info("Rerank provider=none，使用 RRF 结果")
            return
        model_path = Path(settings.rerank_model_path)
        if not model_path.exists():
            logger.info("Rerank 模型目录不存在，降级使用 RRF: %s", model_path)
            return
        try:
            torch = import_module("torch")
            transformers = import_module("transformers")
            self.torch = torch
            self.tokenizer = transformers.AutoTokenizer.from_pretrained(str(model_path))
            self.model = transformers.AutoModelForSequenceClassification.from_pretrained(str(model_path))
            self.model.eval()
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
            self.model.to(self.device)
            self.available = True
            logger.info("Rerank 模型加载成功: %s", model_path)
        except Exception as exc:
            logger.warning("Rerank 模型加载失败，降级使用 RRF: %s", exc)

    def rerank(self, query: str, docs: List[Dict], top_n: int) -> List[Dict]:
        if not self.available or not docs:
            return docs[:top_n]
        if self.provider == "dashscope":
            return self._rerank_dashscope(query, docs, top_n)
        pairs = [(query, doc.get("content", "")) for doc in docs]
        with self.torch.no_grad():
            inputs = self.tokenizer(pairs, padding=True, truncation=True, return_tensors="pt", max_length=512)
            inputs = {k: v.to(self.device) for k, v in inputs.items()}
            scores = self.model(**inputs).logits.reshape(-1).tolist()
        reranked = []
        for doc, score in zip(docs, scores):
            item = doc.copy()
            item["score"] = float(score)
            item["channel"] = "rerank"
            reranked.append(item)
        reranked.sort(key=lambda x: x["score"], reverse=True)
        return reranked[:top_n]

    def _rerank_dashscope(self, query: str, docs: List[Dict], top_n: int) -> List[Dict]:
        documents = [doc.get("content", "") for doc in docs]
        if not any(documents):
            return docs[:top_n]
        try:
            response = requests.post(
                settings.rerank_endpoint,
                headers={
                    "Authorization": f"Bearer {settings.dashscope_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.rerank_model_name,
                    "query": query,
                    "documents": documents,
                    "top_n": min(top_n, len(documents)),
                    "return_documents": False,
                },
                timeout=30,
            )
            if response.status_code != 200:
                logger.warning("DashScope Rerank 调用失败，降级使用 RRF: %s %s", response.status_code, response.text[:300])
                return docs[:top_n]
            data = response.json()
            results = data.get("results") or data.get("output", {}).get("results") or []
            reranked = []
            for item in results:
                index = item.get("index")
                if index is None:
                    index = item.get("document", {}).get("index")
                if index is None or not 0 <= int(index) < len(docs):
                    continue
                score = item.get("relevance_score", item.get("score", item.get("document", {}).get("score", 0.0)))
                doc = docs[int(index)].copy()
                doc["score"] = float(score or 0.0)
                doc["channel"] = "dashscope_rerank"
                reranked.append(doc)
            if not reranked:
                logger.warning("DashScope Rerank 响应为空，降级使用 RRF")
                return docs[:top_n]
            reranked.sort(key=lambda x: x["score"], reverse=True)
            logger.info("DashScope Rerank 成功: model=%s input=%d output=%d", settings.rerank_model_name, len(docs), len(reranked[:top_n]))
            return reranked[:top_n]
        except Exception as exc:
            logger.warning("DashScope Rerank 异常，降级使用 RRF: %s", exc)
            return docs[:top_n]

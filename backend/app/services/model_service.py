import json
import logging
from typing import Dict, Generator, Iterable, List
from openai import OpenAI
from dashscope import MultiModalEmbedding
from app.core.config import settings

logger = logging.getLogger(__name__)


class ModelService:
    def __init__(self):
        self.client = OpenAI(api_key=settings.dashscope_api_key, base_url=settings.dashscope_base_url)

    def embed_text(self, text: str):
        if not text.strip():
            return None
        try:
            resp = MultiModalEmbedding.call(
                model=settings.embedding_model,
                input=[{"text": text}],
                api_key=settings.dashscope_api_key,
            )
            return resp.output["embeddings"][0]["embedding"]
        except Exception as exc:
            logger.warning("Embedding 调用失败: %s", exc)
            return None

    def call_small_json(self, messages: List[Dict[str, str]], fallback: Dict) -> Dict:
        try:
            resp = self.client.chat.completions.create(
                model=settings.small_llm_model,
                messages=messages,
                temperature=0,
                max_tokens=1200,
                response_format={"type": "json_object"},
            )
            content = resp.choices[0].message.content or "{}"
            return json.loads(content)
        except Exception as exc:
            logger.warning("小模型 JSON 调用失败，使用降级结果: %s", exc)
            return fallback

    def call_small_text(self, messages: List[Dict[str, str]], fallback: str = "") -> str:
        try:
            resp = self.client.chat.completions.create(
                model=settings.small_llm_model,
                messages=messages,
                temperature=0.2,
                max_tokens=1200,
            )
            return resp.choices[0].message.content or fallback
        except Exception as exc:
            logger.warning("小模型文本调用失败，使用降级结果: %s", exc)
            return fallback

    def stream_main(self, messages: List[Dict[str, str]], model: str = None, max_tokens: int = 1800, temperature: float = 0.4) -> Iterable[str]:
        model_name = model or settings.llm_model
        try:
            stream = self.client.chat.completions.create(
                model=model_name,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
            )
            for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                text = getattr(delta, "content", None)
                if text:
                    yield text
        except Exception as exc:
            logger.exception("模型流式调用失败: model=%s error=%s", model_name, exc)
            yield "\n\n抱歉，模型服务暂时不可用，请稍后重试。"

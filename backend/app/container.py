from app.repositories.mongo_repo import MongoRepository
from app.repositories.redis_repo import RedisRepository
from app.services.conversation_service import ConversationService
from app.services.guardrail_service import GuardrailService
from app.services.intent_service import IntentService
from app.services.memory_service import MemoryService
from app.services.model_service import ModelService
from app.services.qa_orchestrator import QAOrchestrator
from app.services.retrieval_service import RetrievalService


class Container:
    def __init__(self):
        self.mongo = MongoRepository()
        self.redis = RedisRepository()
        self.model = ModelService()
        self.conversation = ConversationService(self.mongo)
        self.guardrail = GuardrailService()
        self.intent = IntentService(self.model)
        self.retrieval = RetrievalService(self.model)
        self.memory = MemoryService(self.mongo, self.redis, self.model)
        self.qa = QAOrchestrator(self.mongo, self.conversation, self.model, self.intent, self.retrieval, self.memory, self.guardrail)

    async def close(self):
        await self.mongo.close()

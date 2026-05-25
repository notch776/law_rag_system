from typing import List
from app.repositories.mongo_repo import MongoRepository, beijing_time
from app.schemas.chat import CaseSlotState, Citation, ConversationDetail, ConversationSummary, Message


class ConversationService:
    def __init__(self, repo: MongoRepository):
        self.repo = repo

    async def create(self) -> str:
        return await self.repo.create_conversation()

    async def list(self) -> List[ConversationSummary]:
        return [ConversationSummary(**row) for row in await self.repo.list_conversations()]

    async def get(self, conversation_id: str) -> ConversationDetail:
        doc = await self.repo.get_conversation(conversation_id)
        if not doc:
            return ConversationDetail(conversation_id=conversation_id, messages=[])
        messages = []
        for item in doc.get("messages", []):
            ts = item.get("timestamp")
            messages.append(Message(
                role=item.get("role", "assistant"),
                content=item.get("content", ""),
                timestamp=ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
                qa_id=item.get("qa_id"),
                mode=item.get("mode"),
                citations=[Citation(**c) for c in item.get("citations", [])],
            ))
        qa_id = messages[-1].qa_id if messages else ""
        return ConversationDetail(
            conversation_id=conversation_id,
            qa_id=qa_id or "",
            status=doc.get("status", "active"),
            messages=messages,
            case_slot_state=CaseSlotState(**(doc.get("case_slot_state") or {})),
        )

    async def append_user(self, conversation_id: str, qa_id: str, query: str, mode: str):
        await self.repo.append_message(conversation_id, {
            "role": "user",
            "content": query,
            "qa_id": qa_id,
            "mode": mode,
            "timestamp": beijing_time(),
        })

    async def append_assistant(self, conversation_id: str, qa_id: str, answer: str, mode: str, citations: List[Citation]):
        await self.repo.append_message(conversation_id, {
            "role": "assistant",
            "content": answer,
            "qa_id": qa_id,
            "mode": mode,
            "citations": [c.model_dump() for c in citations],
            "timestamp": beijing_time(),
        })

    async def mark_support(self, conversation_id: str):
        await self.repo.set_conversation_status(conversation_id, "support")

    async def mark_active(self, conversation_id: str):
        await self.repo.set_conversation_status(conversation_id, "active")

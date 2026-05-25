from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import DESCENDING
from app.core.config import settings
from app.schemas.chat import CaseSlotState


def beijing_time():
    return datetime.utcnow() + timedelta(hours=8)


class MongoRepository:
    def __init__(self):
        self.client = AsyncIOMotorClient(settings.mongodb_url)
        self.db = self.client[settings.mongodb_database]
        self.conversations = self.db[settings.conversations_collection]
        self.summaries = self.db[settings.summaries_collection]

    async def close(self):
        self.client.close()

    async def create_conversation(self) -> str:
        latest = await self.conversations.find_one(sort=[("conversation_id_int", DESCENDING)])
        next_id = int(latest.get("conversation_id_int", 0)) + 1 if latest else 1
        conversation_id = str(next_id)
        now = beijing_time()
        await self.conversations.insert_one({
            "conversation_id": conversation_id,
            "conversation_id_int": next_id,
            "title": "新对话",
            "status": "active",
            "messages": [],
            "support_messages": [],
            "case_slot_state": CaseSlotState().model_dump(),
            "created_at": now,
            "updated_at": now,
        })
        return conversation_id

    async def ensure_conversation(self, conversation_id: str):
        doc = await self.conversations.find_one({"conversation_id": conversation_id})
        if doc:
            return
        now = beijing_time()
        try:
            conv_int = int(conversation_id)
        except ValueError:
            conv_int = 0
        await self.conversations.insert_one({
            "conversation_id": conversation_id,
            "conversation_id_int": conv_int,
            "title": "新对话",
            "status": "active",
            "messages": [],
            "support_messages": [],
            "case_slot_state": CaseSlotState().model_dump(),
            "created_at": now,
            "updated_at": now,
        })

    async def next_qa_id(self, conversation_id: str) -> str:
        doc = await self.conversations.find_one({"conversation_id": conversation_id}, {"messages": 1})
        count = len(doc.get("messages", [])) if doc else 0
        return f"{conversation_id}.{count // 2 + 1}"

    async def append_message(self, conversation_id: str, message: Dict[str, Any]):
        await self.ensure_conversation(conversation_id)
        await self.conversations.update_one(
            {"conversation_id": conversation_id},
            {
                "$push": {"messages": message},
                "$set": {"updated_at": beijing_time(), "title": await self._title_for(conversation_id, message)},
            },
        )

    async def _title_for(self, conversation_id: str, message: Dict[str, Any]) -> str:
        doc = await self.conversations.find_one({"conversation_id": conversation_id}, {"title": 1, "messages": {"$slice": 1}})
        existing = (doc or {}).get("title")
        if existing and existing != "新对话":
            return existing
        if message.get("role") == "user":
            return message.get("content", "新对话")[:32]
        return existing or "新对话"

    async def list_conversations(self) -> List[Dict[str, Any]]:
        cursor = self.conversations.find({}, {"conversation_id": 1, "title": 1, "updated_at": 1, "status": 1}).sort("updated_at", DESCENDING)
        rows = []
        async for doc in cursor:
            updated_at = doc.get("updated_at") or beijing_time()
            rows.append({
                "conversation_id": doc["conversation_id"],
                "heading": doc.get("title") or "新对话",
                "updated_at": updated_at.isoformat() if hasattr(updated_at, "isoformat") else str(updated_at),
                "status": doc.get("status", "active"),
            })
        return rows

    async def get_conversation(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        return await self.conversations.find_one({"conversation_id": conversation_id})

    async def get_case_slot_state(self, conversation_id: str) -> Dict[str, Any]:
        await self.ensure_conversation(conversation_id)
        doc = await self.conversations.find_one({"conversation_id": conversation_id}, {"case_slot_state": 1})
        return (doc or {}).get("case_slot_state") or CaseSlotState().model_dump()

    async def update_case_slot_state(self, conversation_id: str, case_slot_state: Dict[str, Any]) -> Dict[str, Any]:
        await self.ensure_conversation(conversation_id)
        normalized = CaseSlotState(**(case_slot_state or {})).model_dump()
        await self.conversations.update_one(
            {"conversation_id": conversation_id},
            {"$set": {"case_slot_state": normalized, "updated_at": beijing_time()}},
        )
        return normalized

    async def set_conversation_status(self, conversation_id: str, status: str):
        await self.ensure_conversation(conversation_id)
        await self.conversations.update_one(
            {"conversation_id": conversation_id},
            {"$set": {"status": status, "updated_at": beijing_time()}},
        )

    async def count_user_turns(self, conversation_id: str) -> int:
        doc = await self.get_conversation(conversation_id)
        if not doc:
            return 0
        return sum(1 for msg in doc.get("messages", []) if msg.get("role") == "user")

    async def upsert_summary(self, conversation_id: str, summary: Dict[str, Any]):
        summary["updated_at"] = beijing_time()
        await self.summaries.update_one({"conversation_id": conversation_id}, {"$set": summary}, upsert=True)

    async def get_summary(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        return await self.summaries.find_one({"conversation_id": conversation_id})

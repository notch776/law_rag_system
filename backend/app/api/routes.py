from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from app.schemas.chat import CaseSlotState, ChatRequest


def create_router(container):
    router = APIRouter(prefix="/api")

    @router.post("/conversations")
    async def create_conversation():
        conversation_id = await container.conversation.create()
        return {"conversation_id": conversation_id}

    @router.post("/conversations/new")
    async def create_conversation_compat():
        conversation_id = await container.conversation.create()
        return {"conversation_id": conversation_id}

    @router.get("/conversations")
    async def list_conversations():
        return await container.conversation.list()

    @router.get("/conversations/{conversation_id}/case-slots")
    async def get_case_slots(conversation_id: str):
        return await container.mongo.get_case_slot_state(conversation_id)

    @router.put("/conversations/{conversation_id}/case-slots")
    async def update_case_slots(conversation_id: str, state: CaseSlotState):
        return await container.mongo.update_case_slot_state(conversation_id, state.model_dump())

    @router.get("/conversations/{conversation_id}")
    async def get_conversation(conversation_id: str):
        return await container.conversation.get(conversation_id)

    @router.post("/chat")
    async def chat(request: ChatRequest):
        return await container.qa.non_stream_chat(request)

    @router.post("/query")
    async def query_compat(request: ChatRequest):
        return await container.qa.non_stream_chat(request)

    @router.post("/chat/stream")
    async def chat_stream(request: ChatRequest):
        return StreamingResponse(container.qa.stream_chat(request), media_type="text/event-stream")

    return router

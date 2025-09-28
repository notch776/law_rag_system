from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Tuple
import os
import logging
from datetime import datetime, timedelta
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
import asyncio

from starlette.responses import HTMLResponse

from rag.newtreerag import rag_company_law_qa, store_in_redis
from rag.search_similar import search_similar
from rag import rengong
import uuid

# set MongoDB
MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
DATABASE_NAME = os.getenv("DATABASE_NAMEL", "rag_system")
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "chat_history")

client = AsyncIOMotorClient(MONGODB_URL)
db = client[DATABASE_NAME]
collection = db[COLLECTION_NAME]

user_connections: Dict[str, WebSocket] = {}
support_connections: Dict[str, WebSocket] = {}

conversations: Dict[str, Dict] = {}

# Store conversations waiting for assignment
waiting_conversations: set[str] = set()
# ====================================================

# log
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

app = FastAPI(title="企业法律咨询 RAG 系统")


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def beijing_time():
    return datetime.utcnow() + timedelta(hours=8)


# ==================== Data Models ====================
class QueryRequest(BaseModel):
    conversation_id: str
    query: str
    qa_id: Optional[str] = None  # conversation_id.sequence_number


class Message(BaseModel):
    role: str  # 'user', 'assistant', 'support'
    content: str
    timestamp: str


class ConversationResponse2(BaseModel):
    conversation_id: str
    qa_id: str
    need_human: bool
    messages: List[Message]


class ConversationResponse(BaseModel):
    conversation_id: str
    qa_id: str
    messages: List[Message]


class ConversationSummary(BaseModel):
    conversation_id: str
    heading: str
    updated_at: str


# ====================================================

async def get_next_conversation_id() -> str:
    # get max conversation_id
    pipeline = [
        {
            "$addFields": {
                "conversation_id_int": {
                    "$toInt": "$conversation_id"
                }
            }
        },
        {
            "$sort": {"conversation_id_int": -1}
        },
        {
            "$limit": 1
        }
    ]

    cursor = collection.aggregate(pipeline)
    docs = await cursor.to_list(length=1)


    if docs:
        logger.info(f"获取下一个 conversation_id，当前最大值为: {docs[0]['conversation_id_int']}")
        next_id = docs[0]["conversation_id_int"] + 1
    else:
        logger.info("获取下一个 conversation_id，当前无对话记录")
        next_id = 1

    return str(next_id)


# save question-answer pair
async def save_qa_pair(conversation_id: str, question: str, answer: str) -> str:
    # qa_id: conversation_id.sequence_number (sequence_number = current message count + 1)
    result = await collection.aggregate([
        {"$match": {"conversation_id": conversation_id}},
        {"$project": {"count": {"$size": "$messages"}}}
    ]).to_list(length=1)

    seq = (result[0]["count"] + 1) if result else 1
    qa_id = f"{conversation_id}.{seq}"

    message_doc = {
        "qa_id": qa_id,
        "question": question,
        "answer": answer,
        "timestamp": beijing_time()
    }

    await collection.update_one(
        {"conversation_id": conversation_id},
        {
            "$push": {"messages": message_doc},
            "$set": {"updated_at": beijing_time()}
        },
        upsert=True
    )

    return qa_id


# save to MongoDB
async def save_support_message(conversation_id: str, content: str, sender: str) -> str:
    """save conversations between support and user"""

    result = await collection.aggregate([
        {"$match": {"conversation_id": conversation_id}},
        {"$project": {"support_msg_count": {"$size": "$support_messages"}}}
    ]).to_list(length=1)

    seq = (result[0]["support_msg_count"] + 1) if result else 1
    msg_id = f"{conversation_id}.S{seq}"

    message_doc = {
        "msg_id": msg_id,
        "content": content,
        "sender": sender,
        "timestamp": beijing_time()
    }

    await collection.update_one(
        {"conversation_id": conversation_id},
        {
            "$push": {"support_messages": message_doc},
            "$set": {"updated_at": beijing_time()}
        },
        upsert=True
    )

    return msg_id


# load the whole conversation
async def load_conversation(conversation_id: str) -> dict:
    doc = await collection.find_one({"conversation_id": conversation_id})
    if not doc:
        raise HTTPException(status_code=404, detail="对话未找到")

    messages = []

    for msg in doc.get("messages", []):
        messages.append(Message(role="user", content=msg["question"], timestamp=msg["timestamp"].isoformat()))
        messages.append(Message(role="assistant", content=msg["answer"], timestamp=msg["timestamp"].isoformat()))


    for msg in doc.get("support_messages", []):
        role = "user" if msg["sender"] == "user" else "support"
        messages.append(Message(
            role=role,
            content=msg["content"],
            timestamp=msg["timestamp"].isoformat()
        ))

    return {
        "conversation_id": doc["conversation_id"],
        "messages": messages
    }


# get conversation
async def _get_conversation(conversation_id: str):
    doc = await collection.find_one({"conversation_id": conversation_id})
    if not doc:
        raise HTTPException(status_code=404, detail="对话未找到")

    messages = []
    # user and assistant
    for msg in doc.get("messages", []):
        messages.append(Message(role="user", content=msg["question"], timestamp=msg["timestamp"].isoformat()))
        messages.append(Message(role="assistant", content=msg["answer"], timestamp=msg["timestamp"].isoformat()))

    # support
    for msg in doc.get("support_messages", []):
        role = "user" if msg["sender"] == "user" else "support"
        messages.append(Message(
            role=role,
            content=msg["content"],
            timestamp=msg["timestamp"].isoformat()
        ))

    # sort by time
    messages.sort(key=lambda x: x.timestamp)

    # Handle the case of an empty conversation
    if not doc.get("messages"):
        last_qa_id = f"{conversation_id}.0"
    else:
        last_qa_id = doc["messages"][-1]["qa_id"]

    return ConversationResponse(
        conversation_id=conversation_id,
        qa_id=last_qa_id,
        messages=messages,
    )


# get summaries of all conversations (for history sidebar)
async def list_conversations() -> List[dict]:
    cursor = collection.find(
        {},
        {
            "conversation_id": 1,
            "messages": {"$slice": -1},
            "support_messages": {"$slice": -1},
            "updated_at": 1
        }
    ).sort("updated_at", -1)

    results = []
    async for doc in cursor:

        last_msg = None
        if doc.get("messages") and len(doc["messages"]) > 0:
            last_msg = doc["messages"][-1]
        elif doc.get("support_messages") and len(doc["support_messages"]) > 0:
            last_msg = doc["support_messages"][-1]

        if last_msg:
            if "question" in last_msg:
                heading = last_msg["question"]
            else:
                heading = last_msg["content"]

            heading = heading[:15] + "..." if len(heading) > 15 else heading
            results.append({
                "conversation_id": doc["conversation_id"],
                "heading": heading,
                "updated_at": doc["updated_at"].isoformat() if doc.get("updated_at") else
                (last_msg["timestamp"].isoformat() if "timestamp" in last_msg else datetime.now().isoformat())
            })
        else:

            results.append({
                "conversation_id": doc["conversation_id"],
                "heading": "新对话",
                "updated_at": doc["updated_at"].isoformat()
            })
    return results


# ====================================================
@app.websocket("/ws/user/{conversation_id}")
async def user_websocket(conversation_id: str, websocket: WebSocket):
    await websocket.accept()


    session_id = None
    for s_id, conv in conversations.items():
        if s_id == conversation_id and (conv["status"] in ["waiting", "active"]):
            session_id = conv["session_id"]
            break

    if session_id is None:
        return

    user_connections[session_id] = websocket

    print("user_websocket user_connections[session_id] :", user_connections[session_id])

    try:
        while True:
            data = await websocket.receive_text()

            await save_support_message(conversation_id, data, "user")


            message = {
                "content": data,
                "sender": "user",
                "timestamp": datetime.now().isoformat()
            }
            conversations[conversation_id]["messages"].append(message)

            # If a support agent has already taken over, send directly to him/her
            support_id = conversations[conversation_id]["support_id"]
            if support_id and support_id in support_connections:
                await support_connections[support_id].send_json({
                    "type": "new_message",
                    "conversation_id": conversation_id,
                    "session_id": session_id,
                    "message": message
                })

    except WebSocketDisconnect:
        if session_id in user_connections:
            del user_connections[session_id]
        for conv_id, conv in conversations.items():
            if conv["conversation_id"] == conversation_id:
                conv["status"] = "closed"
                # delete
                if conv_id in waiting_conversations:
                    waiting_conversations.remove(conv_id)

                if conv["support_id"] and conv["support_id"] in support_connections:
                    await support_connections[conv["support_id"]].send_json({
                        "type": "conversation_closed",
                        "conversation_id": conv_id
                    })


@app.websocket("/ws/support/{support_id}")
async def support_websocket(support_id: str, websocket: WebSocket):
    await websocket.accept()
    support_connections[support_id] = websocket

    try:
        # send waiting conversations
        await websocket.send_json({
            "type": "waiting_conversations",
            "conversations": [
                {
                    "conversation_id": conversation_id,
                    "session_id": conversations[conversation_id]["session_id"],
                    "message_count": len(conversations[conversation_id]["messages"])
                }
                for conversation_id in waiting_conversations
            ]
        })

        while True:
            data = await websocket.receive_json()

            if data["type"] == "accept_conversation":
                conversation_id = data["conversation_id"]

                #update status
                if conversation_id in conversations and conversations[conversation_id]["status"] == "waiting":
                    conversations[conversation_id]["status"] = "active"
                    conversations[conversation_id]["support_id"] = support_id

                    # delete
                    if conversation_id in waiting_conversations:
                        waiting_conversations.remove(conversation_id)


                    for s_id, s_ws in support_connections.items():
                        if s_id != support_id:
                            await s_ws.send_json({
                                "type": "conversation_accepted",
                                "conversation_id": conversation_id
                            })

                    # send history to current support
                    await websocket.send_json({
                        "type": "conversation_history",
                        "conversation_id": conversation_id,
                        "messages": conversations[conversation_id]["messages"]
                    })

            elif data["type"] == "send_message":
                conversation_id = data["conversation_id"]
                message_content = data["content"]

                # save and send to user
                if conversation_id in conversations and conversations[conversation_id]["support_id"] == support_id:
                    await save_support_message(conversation_id, message_content, "support")

                    message = {
                        "content": message_content,
                        "sender": "support",
                        "timestamp": datetime.now().isoformat()
                    }
                    conversations[conversation_id]["messages"].append(message)

                    session_id = conversations[conversation_id]["session_id"]

                    print("user_connections[session_id] :", user_connections[session_id])

                    await user_connections[session_id].send_json({
                        "type": "new_message",
                        "conversation_id": conversation_id,
                        "message": message
                    })

    except WebSocketDisconnect:
        if support_id in support_connections:
            del support_connections[support_id]
        # if connection is closed
        for conv_id, conv in conversations.items():
            if conv["support_id"] == support_id:
                conv["support_id"] = None
                conv["status"] = "waiting"
                # ensure no duplicates
                if conv_id not in waiting_conversations:
                    waiting_conversations.add(conv_id)

                for s_ws in support_connections.values():
                    await s_ws.send_json({
                        "type": "new_waiting_conversation",
                        "conversation_id": conv_id,
                        "session_id": conv["session_id"]
                    })
                # send to user (using session_id)
                session_id = conv["session_id"]
                if session_id in user_connections:
                    await user_connections[session_id].send_json({
                        "type": "support_disconnected",
                        "message": "客服已离开，正在为您重新分配"
                    })


# support api
@app.get("/support/{support_id}")
async def get_support_page(support_id: str):
    with open("../frontend/support.html", "r", encoding="utf-8") as f:
        return HTMLResponse(f.read().replace("{{SUPPORT_ID}}", support_id))


# handle query
@app.post("/api/query", response_model=ConversationResponse2)
async def process_query(request: QueryRequest):
    try:
        conversation_id = request.conversation_id
        if not conversation_id:
            raise HTTPException(status_code=400, detail="必须提供 conversation_id")

        #  Detect whether human handoff is needed
        detector = rengong.HumanHandoffDetector()
        need_human = detector.need_human(request.query)

        if need_human:
            qa_id = await save_qa_pair(conversation_id, request.query, "正在为您转接人工客服，请稍候...")
            conv_data = await load_conversation(conversation_id)


            existing_conv_id = None
            for conv_id, conv in conversations.items():
                if conv["session_id"] == conversation_id and conv["status"] in ["waiting", "active"]:
                    existing_conv_id = conv_id
                    break

            if not existing_conv_id:
                # create new conv
                new_conv_id = str(uuid.uuid4())
                conversations[conversation_id] = {
                    "session_id": new_conv_id,
                    "support_id": None,
                    "status": "waiting",
                    "messages": [
                        {
                            "content": request.query,
                            "sender": "user",
                            "timestamp": datetime.now().isoformat()
                        }
                    ]
                }

                if conversation_id not in waiting_conversations:
                    waiting_conversations.add(conversation_id)


                for support_ws in support_connections.values():
                    await support_ws.send_json({
                        "type": "new_waiting_conversation",
                        "conversation_id": conversation_id,
                        "session_id": conversations[conversation_id]["session_id"]
                    })


            response_dict = ConversationResponse2(
                conversation_id=conversation_id,
                qa_id=qa_id,
                need_human=True,
                messages=conv_data["messages"]
            ).dict()
            return response_dict

        # Normal RAG processing flow
        result, enough_flag, user_vector = rag_company_law_qa(request.query, conversation_id)
        similar_docs_result, _ = search_similar(request.query)
        retrieved_docs = [doc['content'] for doc in similar_docs_result] if similar_docs_result else []

        # Save Q&A pair
        qa_id = await save_qa_pair(conversation_id, request.query, result)
        # save to Redis and Neo4j
        info = {
            "问题": request.query,
            "检索到的文档": retrieved_docs,
            "回答": result
        }
        store_in_redis(conversation_id, qa_id, info, user_vector)
        # Load full conversation history
        conv_data = await load_conversation(conversation_id)

        response = ConversationResponse(
            conversation_id=conversation_id,
            qa_id=qa_id,
            messages=conv_data["messages"]
        )
        # no human handoff is needed
        response_dict = response.dict()
        response_dict["need_human"] = False
        return response_dict

    except Exception as e:
        logger.error(f"处理请求时发生错误: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"处理查询时出错: {str(e)}")


# 接口：获取所有历史对话（用于左侧栏）
@app.get("/api/conversations", response_model=List[ConversationSummary])
async def get_conversations():
    return await list_conversations()


# API: Get all historical conversations (for the sidebar)
@app.get("/api/conversations/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(conversation_id: str):
    it = await _get_conversation(conversation_id)
    return it


# API: Get a specific full conversation (for loading)
@app.post("/api/conversations/new")
async def new_conversation():
    try:
        new_id = await get_next_conversation_id()
        result = await collection.insert_one({
            "conversation_id": new_id,
            "messages": [],
            "support_messages": [],
            "created_at": beijing_time(),
            "updated_at": beijing_time()
        })
        if result.inserted_id:
            return {"conversation_id": new_id}
        else:
            raise HTTPException(status_code=500, detail="创建新对话失败")
    except Exception as e:
        logger.error(f"创建新对话失败: {e}")
        raise HTTPException(status_code=500, detail="创建新对话失败")


# Close database connection on app shutdown
@app.on_event("shutdown")
async def shutdown_event():
    client.close()


# run~~~~
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)

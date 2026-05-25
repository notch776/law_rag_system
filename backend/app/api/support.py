import json
import logging
from datetime import datetime, timezone
from typing import Dict, Set
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()
logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SupportRoomManager:
    def __init__(self):
        self.users: Dict[str, Set[WebSocket]] = {}
        self.supports: Dict[str, Set[WebSocket]] = {}

    async def connect_user(self, conversation_id: str, websocket: WebSocket):
        await websocket.accept()
        self.users.setdefault(conversation_id, set()).add(websocket)
        await websocket.send_json({
            "type": "system",
            "status": "connected",
            "conversation_id": conversation_id,
            "message": "已进入人工客服实时通道，正在等待客服接入。",
            "timestamp": _now_iso(),
        })
        await self.broadcast_support(conversation_id, {
            "type": "system",
            "event": "user_joined",
            "conversation_id": conversation_id,
            "message": "用户已进入人工客服通道。",
            "timestamp": _now_iso(),
        })

    async def connect_support(self, conversation_id: str, support_id: str, websocket: WebSocket):
        await websocket.accept()
        self.supports.setdefault(conversation_id, set()).add(websocket)
        await websocket.send_json({
            "type": "system",
            "status": "connected",
            "conversation_id": conversation_id,
            "support_id": support_id,
            "message": "已接入客服工作台，可直接发送消息给用户。",
            "timestamp": _now_iso(),
        })
        await self.broadcast_user(conversation_id, {
            "type": "system",
            "event": "support_joined",
            "conversation_id": conversation_id,
            "support_id": support_id,
            "message": "人工客服已接入，请继续描述您的问题。",
            "timestamp": _now_iso(),
        })

    def disconnect_user(self, conversation_id: str, websocket: WebSocket):
        self._discard(self.users, conversation_id, websocket)

    def disconnect_support(self, conversation_id: str, websocket: WebSocket):
        self._discard(self.supports, conversation_id, websocket)

    def has_support(self, conversation_id: str) -> bool:
        return bool(self.supports.get(conversation_id))

    async def broadcast_user(self, conversation_id: str, payload: dict):
        await self._broadcast(self.users.get(conversation_id, set()), payload)

    async def broadcast_support(self, conversation_id: str, payload: dict):
        await self._broadcast(self.supports.get(conversation_id, set()), payload)

    async def _broadcast(self, targets: Set[WebSocket], payload: dict):
        stale = []
        for target in list(targets):
            try:
                await target.send_json(payload)
            except Exception as exc:
                logger.warning("人工客服 WebSocket 发送失败: %s", exc)
                stale.append(target)
        for target in stale:
            targets.discard(target)

    def _discard(self, rooms: Dict[str, Set[WebSocket]], conversation_id: str, websocket: WebSocket):
        sockets = rooms.get(conversation_id)
        if not sockets:
            return
        sockets.discard(websocket)
        if not sockets:
            rooms.pop(conversation_id, None)


manager = SupportRoomManager()


def _parse_message(raw: str) -> str:
    try:
        data = json.loads(raw)
        return str(data.get("message") or data.get("content") or raw).strip()
    except json.JSONDecodeError:
        return raw.strip()


@router.websocket("/ws/user/{conversation_id}")
async def user_ws(websocket: WebSocket, conversation_id: str):
    await manager.connect_user(conversation_id, websocket)
    try:
        while True:
            content = _parse_message(await websocket.receive_text())
            if not content:
                continue
            payload = {
                "type": "message",
                "sender": "user",
                "conversation_id": conversation_id,
                "message": content,
                "timestamp": _now_iso(),
            }
            if manager.has_support(conversation_id):
                await manager.broadcast_support(conversation_id, payload)
            else:
                await websocket.send_json({
                    "type": "system",
                    "status": "waiting",
                    "conversation_id": conversation_id,
                    "message": "消息已收到，当前暂无客服在线，请稍候。",
                    "timestamp": _now_iso(),
                })
    except WebSocketDisconnect:
        manager.disconnect_user(conversation_id, websocket)
        await manager.broadcast_support(conversation_id, {
            "type": "system",
            "event": "user_left",
            "conversation_id": conversation_id,
            "message": "用户已离开人工客服通道。",
            "timestamp": _now_iso(),
        })


@router.websocket("/ws/support/{conversation_id}/{support_id}")
async def support_ws(websocket: WebSocket, conversation_id: str, support_id: str):
    await manager.connect_support(conversation_id, support_id, websocket)
    try:
        while True:
            content = _parse_message(await websocket.receive_text())
            if not content:
                continue
            await manager.broadcast_user(conversation_id, {
                "type": "message",
                "sender": "support",
                "conversation_id": conversation_id,
                "support_id": support_id,
                "message": content,
                "timestamp": _now_iso(),
            })
    except WebSocketDisconnect:
        manager.disconnect_support(conversation_id, websocket)
        await manager.broadcast_user(conversation_id, {
            "type": "system",
            "event": "support_left",
            "conversation_id": conversation_id,
            "support_id": support_id,
            "message": "人工客服已离开当前会话。",
            "timestamp": _now_iso(),
        })

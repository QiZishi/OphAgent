"""Authenticated WebSocket bridge for run events."""

from __future__ import annotations

import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlmodel import Session

from app.auth.security import get_current_user_from_ws
from app.db.database import engine
from app.domain.models import RunInput

router = APIRouter()


async def _authenticate(websocket: WebSocket):
    session = Session(engine)
    user = await get_current_user_from_ws(websocket, session)
    if user is None:
        await websocket.accept()
        await websocket.send_json({"type": "error", "message": "未认证，请先登录"})
        await websocket.close(code=1008)
        session.close()
        return None, None
    return user, session


@router.websocket("/runs/{run_id}")
async def websocket_run_events(websocket: WebSocket, run_id: str):
    user, session = await _authenticate(websocket)
    if user is None:
        return
    await websocket.accept()
    try:
        store = websocket.app.state.runtime_store
        run = await store.get_run(run_id)
        if run is None or run.user_id != user.id:
            await websocket.send_json({"type": "error", "message": "任务不存在"})
            await websocket.close(code=1008)
            return
        async for event in store.stream_events(run_id):
            await websocket.send_json(event.model_dump(mode="json"))
    except WebSocketDisconnect:
        return
    finally:
        session.close()


@router.websocket("/chat")
async def websocket_chat_compatibility(websocket: WebSocket):
    """Compatibility endpoint that creates a v3 run then relays its events."""
    user, session = await _authenticate(websocket)
    if user is None:
        return
    await websocket.accept()
    await websocket.send_json({"type": "connected", "message": "连接成功"})
    try:
        while True:
            request = json.loads(await websocket.receive_text())
            if request.get("type") not in {"chat", "run.create"}:
                await websocket.send_json({"type": "error", "message": "不支持的消息类型"})
                continue
            query = str(request.get("query") or "").strip()
            if not query:
                await websocket.send_json({"type": "error", "message": "查询内容不能为空"})
                continue
            if any(
                request.get(field)
                for field in (
                    "image_path",
                    "image_paths",
                    "document_paths",
                    "audio_paths",
                )
            ):
                await websocket.send_json(
                    {
                        "type": "error",
                        "message": (
                            "不接受客户端服务器路径；请先通过上传接口获取 "
                            "attachment_ids"
                        ),
                    },
                )
                continue
            run = await websocket.app.state.orchestrator.create(
                int(user.id),
                RunInput(
                    query=query,
                    plugin_id=request.get("plugin_id") or request.get("agent_mode") or "aux_diagnosis",
                    conversation_id=request.get("conversation_id"),
                    attachment_ids=request.get("attachment_ids") or [],
                ),
            )
            await websocket.send_json({"type": "run.created", "run_id": run.id, "trace_id": run.trace_id})
            async for event in websocket.app.state.runtime_store.stream_events(run.id):
                payload = event.model_dump(mode="json")
                await websocket.send_json(payload)
                if event.type == "answer.completed":
                    await websocket.send_json(
                        {
                            "type": "report_complete",
                            "report": event.data.get("answer", ""),
                            "run_id": run.id,
                        },
                    )
    except (WebSocketDisconnect, json.JSONDecodeError):
        return
    finally:
        session.close()

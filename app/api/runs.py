from __future__ import annotations

import asyncio
import json
from contextlib import suppress
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field
from sqlmodel import Session

from app.api.dependencies import get_orchestrator, get_runtime_store
from app.auth.security import get_current_user
from app.db.crud import get_conversation_by_id
from app.db.database import get_session
from app.db.models import User
from app.domain.models import RunInput, RunRecord
from app.runtime.document_exports import answer_with_references, render_docx, render_jpg, render_pdf
from app.runtime.orchestrator import RunOrchestrator
from app.runtime.store import RuntimeStore

router = APIRouter(prefix="/runs", tags=["Runs"])


class RunInputUpdate(BaseModel):
    content: str | None = Field(default=None, max_length=20_000)
    attachment_ids: list[str] = Field(default_factory=list)


class RunFeedbackUpdate(BaseModel):
    value: Literal["up", "down"] | None = None


@router.post("", response_model=RunRecord, status_code=202)
async def create_run(
    payload: RunInput,
    current_user: User = Depends(get_current_user),
    orchestrator: RunOrchestrator = Depends(get_orchestrator),
    session: Session = Depends(get_session),
):
    if payload.image_paths or payload.document_paths or payload.audio_paths:
        raise HTTPException(
            status_code=422,
            detail="客户端不能提交服务器文件路径，请先上传并使用 attachment_ids",
        )
    if payload.artifact_ids:
        raise HTTPException(
            status_code=422,
            detail="当前尚未支持将 Artifact 直接作为 Run 输入",
        )
    if payload.conversation_id is not None:
        conversation = get_conversation_by_id(session, payload.conversation_id)
        if conversation is None or conversation.user_id != current_user.id:
            raise HTTPException(status_code=404, detail="Conversation not found")
    try:
        return await orchestrator.create(int(current_user.id), payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("", response_model=list[RunRecord])
async def list_runs(
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    store: RuntimeStore = Depends(get_runtime_store),
):
    return await store.list_runs(int(current_user.id), limit)


@router.get("/{run_id}", response_model=RunRecord)
async def get_run(
    run_id: str,
    current_user: User = Depends(get_current_user),
    store: RuntimeStore = Depends(get_runtime_store),
):
    run = await store.get_run(run_id)
    if run is None or run.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.post("/{run_id}/cancel", response_model=RunRecord)
async def cancel_run(
    run_id: str,
    current_user: User = Depends(get_current_user),
    orchestrator: RunOrchestrator = Depends(get_orchestrator),
):
    try:
        return await orchestrator.cancel(run_id, int(current_user.id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc


@router.post("/{run_id}/resume", response_model=RunRecord, status_code=202)
async def resume_run(
    run_id: str,
    current_user: User = Depends(get_current_user),
    orchestrator: RunOrchestrator = Depends(get_orchestrator),
):
    try:
        return await orchestrator.resume(run_id, int(current_user.id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{run_id}/retry", response_model=RunRecord, status_code=202)
async def retry_run(
    run_id: str,
    current_user: User = Depends(get_current_user),
    orchestrator: RunOrchestrator = Depends(get_orchestrator),
):
    try:
        return await orchestrator.retry(run_id, int(current_user.id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.patch("/{run_id}/feedback", response_model=RunRecord)
async def update_run_feedback(
    run_id: str,
    payload: RunFeedbackUpdate,
    current_user: User = Depends(get_current_user),
    orchestrator: RunOrchestrator = Depends(get_orchestrator),
):
    try:
        return await orchestrator.record_feedback(run_id, int(current_user.id), payload.value)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc


@router.delete("/{run_id}", status_code=204)
async def delete_run(
    run_id: str,
    current_user: User = Depends(get_current_user),
    orchestrator: RunOrchestrator = Depends(get_orchestrator),
):
    try:
        await orchestrator.delete(run_id, int(current_user.id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc


@router.get("/{run_id}/export")
async def export_run(
    run_id: str,
    format: Literal["md", "markdown", "pdf", "docx", "jpg"] = Query("md"),
    current_user: User = Depends(get_current_user),
    store: RuntimeStore = Depends(get_runtime_store),
):
    run = await store.get_run(run_id)
    if run is None or run.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Run not found")
    if not run.answer:
        raise HTTPException(status_code=409, detail="当前回答尚未完成")
    events = await store.get_events(run.id)
    evidence = [
        item
        for event in events
        if event.type == "retrieval.result"
        for item in event.data.get("evidence", [])
        if isinstance(item, dict)
    ]
    content = answer_with_references(run.answer, evidence)
    filename = f"ophagent-{run.id}.{format}"
    if format in {"md", "markdown"}:
        return Response(
            content=content.encode("utf-8"),
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    if format == "pdf":
        payload = render_pdf(content, "OphAgent 回答")
        media_type = "application/pdf"
    elif format == "docx":
        payload = render_docx(content, "OphAgent 回答")
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    else:
        payload = render_jpg(content, "OphAgent 回答")
        media_type = "image/jpeg"
    return Response(
        content=payload,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{run_id}/input", response_model=RunRecord, status_code=202)
async def provide_run_input(
    run_id: str,
    payload: RunInputUpdate,
    current_user: User = Depends(get_current_user),
    orchestrator: RunOrchestrator = Depends(get_orchestrator),
):
    if not payload.content and not payload.attachment_ids:
        raise HTTPException(status_code=422, detail="请提供补充文字或附件")
    try:
        return await orchestrator.provide_input(
            run_id,
            int(current_user.id),
            payload.content,
            payload.attachment_ids,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{run_id}/approve", response_model=RunRecord, status_code=202)
async def approve_run(
    run_id: str,
    current_user: User = Depends(get_current_user),
    orchestrator: RunOrchestrator = Depends(get_orchestrator),
):
    try:
        return await orchestrator.approve(run_id, int(current_user.id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/{run_id}/events", response_model=list)
async def list_run_events(
    run_id: str,
    after_sequence: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    store: RuntimeStore = Depends(get_runtime_store),
):
    run = await store.get_run(run_id)
    if run is None or run.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Run not found")

    return [
        event.model_dump(mode="json")
        for event in await store.get_events(run_id, after_sequence)
    ]


@router.get("/{run_id}/events/stream")
async def stream_run_events(
    run_id: str,
    after_sequence: int = Query(0, ge=0),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    current_user: User = Depends(get_current_user),
    store: RuntimeStore = Depends(get_runtime_store),
):
    run = await store.get_run(run_id)
    if run is None or run.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Run not found")
    cursor = after_sequence
    if last_event_id and last_event_id.isdigit():
        cursor = max(cursor, int(last_event_id))

    async def event_stream():
        events = store.stream_events(run_id, cursor)
        pending_event: asyncio.Task | None = None
        try:
            while True:
                if pending_event is None:
                    pending_event = asyncio.create_task(anext(events))
                try:
                    event = await asyncio.wait_for(
                        asyncio.shield(pending_event),
                        timeout=10,
                    )
                except TimeoutError:
                    # Keep proxies from closing an otherwise healthy stream
                    # without delaying a newly persisted event.
                    yield ": heartbeat\n\n"
                    continue
                except StopAsyncIteration:
                    return
                pending_event = None
                payload = event.model_dump(mode="json")
                yield (
                    f"id: {event.sequence}\nevent: {event.type}\n"
                    f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                )
        finally:
            if pending_event is not None:
                pending_event.cancel()
                with suppress(asyncio.CancelledError, StopAsyncIteration):
                    await pending_event
            await events.aclose()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

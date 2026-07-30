"""Legacy conversation APIs retained during the v3 workspace migration."""

from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import mimetypes
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.api.dependencies import get_capability_clients, get_orchestrator, get_runtime_store
from app.auth.security import get_current_user
from app.core.config import settings
from app.db.crud import (
    count_project_conversations,
    create_conversation,
    create_message,
    create_project,
    delete_conversation,
    delete_project,
    get_conversation_by_id,
    get_conversation_messages,
    get_message_by_idempotency,
    get_project,
    get_user_conversations,
    list_projects,
    update_conversation_project,
    update_conversation_title,
    update_project,
)
from app.db.database import get_session
from app.db.models import User
from app.domain.models import AttachmentRecord, RunInput
from app.runtime.errors import CapabilityUnavailable
from app.runtime.orchestrator import RunOrchestrator
from app.runtime.public_projection import PublicRunRecord, public_run_record
from app.runtime.store import RuntimeStore
from app.tools.capabilities import CapabilityClients, SpeechRequest, SynthesisRequest

router = APIRouter()


class ConversationCreate(BaseModel):
    title: str = Field(default="新对话", min_length=1, max_length=100)
    agent_type: str = "aux_diagnosis"
    project_id: int | None = None


class MessageResponse(BaseModel):
    id: int
    role: str
    content: str
    file_path: str | None = None
    created_at: str


class ConversationResponse(BaseModel):
    id: int
    title: str
    agent_type: str
    created_at: str
    pinned: bool = False
    project_id: int | None = None


class ConversationDetailResponse(ConversationResponse):
    messages: list[MessageResponse] = Field(default_factory=list)
    runs: list[PublicRunRecord] = Field(default_factory=list)


class ConversationUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=100)
    pinned: bool | None = None
    project_id: int | None = None


class ConversationMessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=20_000)
    attachment_ids: list[str] = Field(default_factory=list)
    requested_plugins: list[str] = Field(default_factory=list)
    requested_skills: list[str] = Field(default_factory=list)
    mode: str = "auto"
    idempotency_key: str | None = Field(default=None, max_length=128)


class ConversationMessageRunResponse(BaseModel):
    message: MessageResponse
    run: PublicRunRecord


class SpeechSynthesisCreate(BaseModel):
    text: str = Field(min_length=1, max_length=600)
    voice: str | None = Field(default=None, min_length=1, max_length=64)


class PaginationResponse(BaseModel):
    items: list[ConversationResponse]
    total: int
    skip: int
    limit: int


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=500)


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=500)
    color: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")


class ProjectResponse(BaseModel):
    id: int
    name: str
    description: str
    color: str
    conversation_count: int
    created_at: str
    updated_at: str


def _project_response(project, session: Session) -> ProjectResponse:
    return ProjectResponse(
        id=int(project.id),
        name=project.name,
        description=project.description,
        color=project.color,
        conversation_count=count_project_conversations(session, int(project.id)),
        created_at=project.created_at.isoformat(),
        updated_at=project.updated_at.isoformat(),
    )


@router.get("/projects", response_model=list[ProjectResponse])
async def get_projects(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    return [_project_response(item, session) for item in list_projects(session, int(current_user.id))]


@router.post("/projects", response_model=ProjectResponse, status_code=201)
async def create_workspace_project(
    payload: ProjectCreate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    return _project_response(
        create_project(session, int(current_user.id), payload.name, payload.description),
        session,
    )


@router.patch("/projects/{project_id}", response_model=ProjectResponse)
async def update_workspace_project(
    project_id: int,
    payload: ProjectUpdate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    project = get_project(session, project_id, int(current_user.id))
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return _project_response(update_project(session, project, payload.model_dump(exclude_none=True)), session)


@router.delete("/projects/{project_id}", status_code=204)
async def delete_workspace_project(
    project_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    project = get_project(session, project_id, int(current_user.id))
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    delete_project(session, project)


@router.get("/health")
async def health_check():
    errors = settings.startup_errors()
    return {
        "status": "ok" if not errors else "degraded",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "configuration_errors": errors,
    }


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    store: RuntimeStore = Depends(get_runtime_store),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="未选择文件")
    allowed = {
        ".jpg", ".jpeg", ".png", ".webp",
        ".pdf", ".txt", ".md",
        ".wav", ".mp3", ".m4a",
    }
    extension = Path(file.filename).suffix.lower()
    if extension not in allowed:
        raise HTTPException(status_code=400, detail="不支持的文件类型")
    content = await file.read(settings.MAX_UPLOAD_BYTES + 1)
    if len(content) > settings.MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="文件超过上传大小限制")
    upload_dir = settings.resolve_path(settings.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)
    safe_name = f"{uuid4().hex}{extension}"
    target = upload_dir / safe_name
    await asyncio.to_thread(target.write_bytes, content)
    if extension in {".jpg", ".jpeg", ".png", ".webp"}:
        kind = "image"
    elif extension in {".wav", ".mp3", ".m4a"}:
        kind = "audio"
    else:
        kind = "document"
    record = AttachmentRecord(
        user_id=int(current_user.id),
        original_filename=Path(file.filename).name,
        stored_path=str(target.relative_to(settings.project_root)),
        mime_type=file.content_type or mimetypes.guess_type(file.filename)[0] or "application/octet-stream",
        size=len(content),
        checksum=hashlib.sha256(content).hexdigest(),
        kind=kind,
    )
    await store.save_attachment(record)
    return {
        "id": record.id,
        "attachment_id": record.id,
        "kind": record.kind,
        "mime_type": record.mime_type,
        "filename": record.original_filename,
        "size": record.size,
        "status": "uploaded",
        "url": f"/api/v1/attachments/{record.id}",
    }


@router.post("/audio/transcriptions")
async def transcribe_audio(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    clients: CapabilityClients = Depends(get_capability_clients),
):
    """Transcribe one private recording and remove the temporary audio afterwards."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="未选择音频")
    suffix = Path(file.filename).suffix.lower() or ".webm"
    if suffix not in {".wav", ".mp3", ".m4a", ".webm", ".ogg"}:
        raise HTTPException(status_code=415, detail="不支持的录音格式")
    content = await file.read(settings.MAX_UPLOAD_BYTES + 1)
    if len(content) > settings.MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="录音超过上传大小限制")
    target_dir = settings.resolve_path(settings.UPLOAD_DIR) / "voice-temp" / str(current_user.id)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{uuid4().hex}{suffix}"
    await asyncio.to_thread(target.write_bytes, content)
    try:
        result = await clients.transcribe(SpeechRequest(path=str(target)))
        data = result.data
        nested = data.get("result")
        text = str(
            data.get("text")
            or data.get("transcript")
            or (nested.get("text") if isinstance(nested, dict) else "")
            or ""
        ).strip()
        if not text:
            raise HTTPException(status_code=502, detail="ASR 未返回可用转写文本")
        return {
            "text": text,
            "language": data.get("language"),
            "duration_seconds": data.get("duration") or data.get("duration_seconds"),
        }
    except CapabilityUnavailable as exc:
        raise HTTPException(status_code=503, detail=exc.detail) from exc
    finally:
        if target.is_file():
            await asyncio.to_thread(target.unlink)


@router.post("/audio/speech")
async def synthesize_speech(
    payload: SpeechSynthesisCreate,
    current_user: User = Depends(get_current_user),
    clients: CapabilityClients = Depends(get_capability_clients),
):
    """Synthesize one authenticated response without persisting clinical text or audio."""
    del current_user
    try:
        result = await clients.synthesize_speech(
            SynthesisRequest(text=payload.text, voice=payload.voice)
        )
        encoded = str(result.data.get("audio_base64") or "")
        if not encoded:
            raise HTTPException(status_code=502, detail="TTS 未返回可播放音频")
        try:
            audio = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise HTTPException(status_code=502, detail="TTS 返回了无效音频") from exc
        mime_type = str(result.data.get("mime_type") or "audio/mpeg")
        if not mime_type.startswith("audio/"):
            mime_type = "audio/mpeg"
        return Response(
            content=audio,
            media_type=mime_type,
            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
        )
    except CapabilityUnavailable as exc:
        raise HTTPException(status_code=503, detail=exc.detail) from exc


@router.get("/attachments")
async def list_attachments(
    current_user: User = Depends(get_current_user),
    store: RuntimeStore = Depends(get_runtime_store),
):
    return await store.list_attachments(int(current_user.id))


@router.get("/attachments/{attachment_id}")
async def download_attachment(
    attachment_id: str,
    current_user: User = Depends(get_current_user),
    store: RuntimeStore = Depends(get_runtime_store),
):
    record = await store.get_attachment(attachment_id)
    if record is None or record.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Attachment not found")
    path = settings.resolve_path(record.stored_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Attachment file not found")
    return FileResponse(path, media_type=record.mime_type, filename=record.original_filename)


@router.delete("/attachments/{attachment_id}", status_code=204)
async def delete_attachment(
    attachment_id: str,
    current_user: User = Depends(get_current_user),
    store: RuntimeStore = Depends(get_runtime_store),
):
    if not await store.delete_attachment(attachment_id, int(current_user.id)):
        raise HTTPException(status_code=404, detail="Attachment not found")


@router.post("/diagnose", status_code=410)
async def legacy_diagnose(current_user: User = Depends(get_current_user)):
    raise HTTPException(
        status_code=410,
        detail="旧同步诊断接口已移除；请使用 POST /api/v1/runs 并订阅 /events。",
    )


@router.get("/conversations", response_model=PaginationResponse)
async def list_conversations(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    conversations, total = get_user_conversations(session, int(current_user.id), skip=skip, limit=limit)
    return PaginationResponse(
        items=[
            ConversationResponse(
                id=int(conversation.id),
                title=conversation.title,
                agent_type=conversation.agent_type,
                created_at=conversation.created_at.isoformat(),
                pinned=conversation.pinned,
                project_id=conversation.project_id,
            )
            for conversation in conversations
        ],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.post("/conversations", response_model=ConversationDetailResponse)
async def create_new_conversation(
    payload: ConversationCreate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    if payload.project_id is not None and get_project(
        session,
        payload.project_id,
        int(current_user.id),
    ) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    conversation = create_conversation(
        session,
        title=payload.title,
        user_id=int(current_user.id),
        agent_type=payload.agent_type,
        project_id=payload.project_id,
    )
    return ConversationDetailResponse(
        id=int(conversation.id),
        title=conversation.title,
        agent_type=conversation.agent_type,
        created_at=conversation.created_at.isoformat(),
        pinned=conversation.pinned,
        project_id=conversation.project_id,
    )


@router.get("/conversations/{conversation_id}", response_model=ConversationDetailResponse)
async def get_conversation(
    conversation_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    store: RuntimeStore = Depends(get_runtime_store),
):
    conversation = get_conversation_by_id(session, conversation_id)
    if not conversation or conversation.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Conversation not found")
    messages = get_conversation_messages(session, conversation_id)
    return ConversationDetailResponse(
        id=int(conversation.id),
        title=conversation.title,
        agent_type=conversation.agent_type,
        created_at=conversation.created_at.isoformat(),
        pinned=conversation.pinned,
        project_id=conversation.project_id,
        messages=[
            MessageResponse(
                id=int(message.id),
                role=message.role,
                content=message.content,
                file_path=message.file_path,
                created_at=message.created_at.isoformat(),
            )
            for message in messages
        ],
        runs=[
            public_run_record(run)
            for run in await store.list_runs(int(current_user.id), limit=100)
            if run.input.conversation_id == conversation_id
        ],
    )


@router.patch("/conversations/{conversation_id}", response_model=ConversationResponse)
async def update_conversation(
    conversation_id: int,
    payload: ConversationUpdate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    conversation = get_conversation_by_id(session, conversation_id)
    if not conversation or conversation.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if payload.title is not None:
        conversation = update_conversation_title(session, conversation_id, payload.title) or conversation
    if payload.pinned is not None:
        conversation.pinned = payload.pinned
        session.add(conversation)
        session.commit()
        session.refresh(conversation)
    if "project_id" in payload.model_fields_set:
        if payload.project_id is not None and get_project(
            session,
            payload.project_id,
            int(current_user.id),
        ) is None:
            raise HTTPException(status_code=404, detail="Project not found")
        conversation = update_conversation_project(
            session,
            conversation,
            payload.project_id,
        )
    return ConversationResponse(
        id=int(conversation.id),
        title=conversation.title,
        agent_type=conversation.agent_type,
        created_at=conversation.created_at.isoformat(),
        pinned=conversation.pinned,
        project_id=conversation.project_id,
    )


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=ConversationMessageRunResponse,
    status_code=202,
)
async def create_conversation_message(
    conversation_id: int,
    payload: ConversationMessageCreate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    orchestrator: RunOrchestrator = Depends(get_orchestrator),
    store: RuntimeStore = Depends(get_runtime_store),
):
    conversation = get_conversation_by_id(session, conversation_id)
    if not conversation or conversation.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if payload.idempotency_key:
        existing_message = get_message_by_idempotency(
            session,
            conversation_id,
            payload.idempotency_key,
        )
        existing_run = await store.find_run_by_idempotency(
            int(current_user.id),
            payload.idempotency_key,
        )
        if (
            existing_message is not None
            and existing_message.conversation_id == conversation_id
            and existing_run is not None
        ):
            return ConversationMessageRunResponse(
                message=MessageResponse(
                    id=int(existing_message.id),
                    role=existing_message.role,
                    content=existing_message.content,
                    file_path=existing_message.file_path,
                    created_at=existing_message.created_at.isoformat(),
                ),
                run=public_run_record(existing_run),
            )
    plugin_id = payload.requested_plugins[0] if payload.requested_plugins else "core"
    try:
        run = await orchestrator.create(
            int(current_user.id),
            RunInput(
                query=payload.content,
                plugin_id=plugin_id,
                conversation_id=conversation_id,
                attachment_ids=payload.attachment_ids,
                requested_plugins=payload.requested_plugins,
                requested_skills=payload.requested_skills,
                mode=payload.mode,
                idempotency_key=payload.idempotency_key,
            ),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        message = create_message(
            session,
            conversation_id,
            "user",
            payload.content,
            idempotency_key=payload.idempotency_key,
        )
    except IntegrityError:
        session.rollback()
        if not payload.idempotency_key:
            raise
        message = get_message_by_idempotency(
            session,
            conversation_id,
            payload.idempotency_key,
        )
        if message is None:
            raise
    await store.bind_attachments(
        payload.attachment_ids,
        int(current_user.id),
        conversation_id,
        int(message.id),
    )
    return ConversationMessageRunResponse(
        message=MessageResponse(
            id=int(message.id),
            role=message.role,
            content=message.content,
            file_path=message.file_path,
            created_at=message.created_at.isoformat(),
        ),
        run=public_run_record(run),
    )


@router.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation_endpoint(
    conversation_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    store: RuntimeStore = Depends(get_runtime_store),
    orchestrator: RunOrchestrator = Depends(get_orchestrator),
):
    conversation = get_conversation_by_id(session, conversation_id)
    if not conversation or conversation.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Conversation not found")
    for run in await store.list_runs(int(current_user.id), limit=10_000):
        if run.input.conversation_id == conversation_id:
            await orchestrator.cancel(run.id, int(current_user.id))
    if not delete_conversation(session, conversation_id):
        raise HTTPException(status_code=500, detail="删除会话失败")
    await store.delete_conversation_resources(int(current_user.id), conversation_id)

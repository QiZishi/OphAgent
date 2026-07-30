from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from sqlmodel import Session

from app.api.dependencies import (
    get_capability_clients,
    get_evolution_controller,
    get_memory_store,
    get_provider_config_store,
    get_runtime_store,
    get_skill_store,
)
from app.auth.security import get_current_user
from app.core.config import settings
from app.db.crud import record_audit
from app.db.database import get_session
from app.db.models import User
from app.domain.models import (
    Artifact,
    CapabilityState,
    ContinuousEvolutionStatus,
    KnowledgeSource,
    MemoryRecord,
    SkillRecord,
)
from app.evolution.continuous import ContinuousEvolutionController
from app.evolution.official import OfficialEvolverRegistry
from app.knowledge.sources import SourceRegistry
from app.observability.tracing import exporter_status
from app.plugins.registry import plugin_registry
from app.runtime.document_exports import answer_with_references, render_docx, render_jpg, render_pdf
from app.runtime.store import RuntimeStore
from app.services.provider_config import ProviderConfigInput, ProviderConfigStore
from app.services.state import MemoryStore, SkillStore
from app.tools.capabilities import CapabilityClients

router = APIRouter(tags=["Management"])


def _audit(
    session: Session,
    user: User,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    details: str = "{}",
) -> None:
    record_audit(
        session,
        int(user.id),
        action,
        resource_type,
        resource_id,
        details,
    )


@router.get("/plugins")
async def list_plugins():
    return plugin_registry.list()


@router.get("/evolution/status", response_model=ContinuousEvolutionStatus)
async def evolution_status(
    current_user: User = Depends(get_current_user),
    controller: ContinuousEvolutionController = Depends(get_evolution_controller),
):
    return await controller.status()


@router.get("/provider-config")
async def get_provider_config(
    current_user: User = Depends(get_current_user),
    provider_store: ProviderConfigStore = Depends(get_provider_config_store),
):
    return await provider_store.public_config(int(current_user.id))


@router.put("/provider-config")
async def update_provider_config(
    payload: ProviderConfigInput,
    current_user: User = Depends(get_current_user),
    provider_store: ProviderConfigStore = Depends(get_provider_config_store),
    session: Session = Depends(get_session),
):
    try:
        updated = await provider_store.save(int(current_user.id), payload)
        _audit(session, current_user, "update", "provider_config")
        return updated
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _configured(value: str, secret: str = "") -> bool:
    return bool(value and (secret if secret is not None else True))


@router.get("/capabilities", response_model=list[CapabilityState])
async def capabilities(
    current_user: User = Depends(get_current_user),
    clients: CapabilityClients = Depends(get_capability_clients),
):
    active = clients.config
    main_key = active.main_model_key.get_secret_value()
    sub_key = active.sub_model_key.get_secret_value()
    definitions = [
        ("main_model", active.main_model_url, main_key, active.main_model_name, True),
        ("sub_model", active.sub_model_url, sub_key, active.sub_model_name, True),
        ("embedding", active.embedding_url, active.embedding_key.get_secret_value(), active.EMBEDDING_MODEL, False),
        ("rerank", active.rerank_url, active.rerank_key.get_secret_value(), active.RERANK_MODEL, False),
        ("anysearch", active.ANYSEARCH_URL, active.ANYSEARCH_API_KEY.get_secret_value(), None, False),
        ("tavily", active.TAVILY_URL, active.TAVILY_API_KEY.get_secret_value(), None, False),
        ("asr", active.ASR_URL, active.ASR_API_KEY.get_secret_value(), active.ASR_MODEL, False),
        ("tts", active.TTS_URL, active.TTS_API_KEY.get_secret_value(), active.TTS_MODEL, False),
        ("mineru", active.MINERU_URL, active.MINERU_API_KEY.get_secret_value(), None, False),
    ]
    states: list[CapabilityState] = []
    for identifier, url, key, model, required in definitions:
        configured = bool(
            url
            and key
            and (
                model
                if identifier
                in {"main_model", "sub_model", "embedding", "rerank", "asr", "tts"}
                else True
            )
        )
        observed = clients.health.get(identifier)
        if identifier == "embedding" and clients.retriever._embedding_ready is not None:
            observed = "ready" if clients.retriever._embedding_ready else "unavailable"
        if identifier == "rerank" and clients.retriever._rerank_ready is not None:
            observed = "ready" if clients.retriever._rerank_ready else "unavailable"
        status = "unavailable" if not configured else (observed or "unknown")
        states.append(
            CapabilityState(
                id=identifier,
                configured=configured,
                status=status,
                provider=(
                    url.split("/")[2]
                    if url.startswith("http") and len(url.split("/")) > 2
                    else None
                ),
                model=model,
                required=required,
                detail=(
                    "已由本进程真实调用验证"
                    if observed == "ready"
                    else "最近一次真实调用失败"
                    if observed == "unavailable" and configured
                    else "配置完整，尚未由本进程真实调用"
                    if configured
                    else "配置不完整"
                ),
            ),
        )
    trace_state = exporter_status()
    states.append(
        CapabilityState(
            id="observability",
            configured=bool(settings.OTEL_EXPORTER_OTLP_ENDPOINT),
            status="ready" if trace_state["exporter_ready"] else "degraded",
            provider="OpenTelemetry",
            detail=(
                "远端 exporter 已启用，执行 export-time 隐私白名单"
                if trace_state["exporter_ready"]
                else "本地 span 可用，未配置远端 OTLP exporter"
            ),
        ),
    )
    for provider_id, provider_state in OfficialEvolverRegistry(settings).status().items():
        states.append(
            CapabilityState(
                id=f"evolution:{provider_id}",
                configured=bool(provider_state["available"]),
                status="ready" if provider_state["available"] else "unavailable",
                provider=provider_id,
                detail=(
                    "官方实现可用（仅限离线演化）"
                    if provider_state["available"]
                    else "官方实现未安装或未配置；未启用替代优化器"
                ),
            ),
        )
    return states


@router.get("/artifacts", response_model=list[Artifact])
async def list_artifacts(
    run_id: str | None = None,
    current_user: User = Depends(get_current_user),
    store: RuntimeStore = Depends(get_runtime_store),
):
    return await store.list_artifacts(int(current_user.id), run_id)


class ArtifactCreateFromRun(BaseModel):
    run_id: str
    title: str | None = Field(default=None, min_length=1, max_length=200)


class ArtifactUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    content: str | None = Field(default=None, max_length=200_000)


@router.post("/artifacts/from-run", response_model=Artifact, status_code=201)
async def create_artifact_from_run(
    payload: ArtifactCreateFromRun,
    current_user: User = Depends(get_current_user),
    store: RuntimeStore = Depends(get_runtime_store),
):
    run = await store.get_run(payload.run_id)
    if run is None or run.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Run not found")
    if not run.answer:
        raise HTTPException(status_code=409, detail="当前回答尚未完成")
    existing = [
        artifact
        for artifact in await store.list_artifacts(int(current_user.id), run.id)
        if artifact.metadata.get("converted_from_answer")
    ]
    if existing:
        return existing[-1]
    events = await store.get_events(run.id)
    evidence = [
        item
        for event in events
        if event.type == "retrieval.result"
        for item in event.data.get("evidence", [])
        if isinstance(item, dict)
    ]
    artifact = Artifact(
        run_id=run.id,
        user_id=int(current_user.id),
        type="document",
        title=payload.title or f"{run.input.query[:32]} · 文档",
        mime_type="text/markdown",
        content=answer_with_references(run.answer, evidence),
        metadata={
            "converted_from_answer": True,
            "source_run_id": run.id,
            "trace_id": run.trace_id,
        },
    )
    return await store.save_artifact(artifact)


@router.get("/artifacts/{artifact_id}", response_model=Artifact)
async def get_artifact(
    artifact_id: str,
    current_user: User = Depends(get_current_user),
    store: RuntimeStore = Depends(get_runtime_store),
):
    artifact = await store.get_artifact(artifact_id)
    if artifact is None or artifact.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return artifact


@router.patch("/artifacts/{artifact_id}", response_model=Artifact)
async def update_artifact(
    artifact_id: str,
    payload: ArtifactUpdate,
    current_user: User = Depends(get_current_user),
    store: RuntimeStore = Depends(get_runtime_store),
):
    artifact = await store.get_artifact(artifact_id)
    if artifact is None or artifact.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Artifact not found")
    if payload.title is not None:
        artifact.title = payload.title
    if payload.content is not None:
        artifact.content = payload.content
        artifact.mime_type = "text/markdown"
    artifact.metadata = {**artifact.metadata, "edited": True}
    return await store.save_artifact(artifact)


@router.get("/artifacts/{artifact_id}/export")
async def export_artifact(
    artifact_id: str,
    format: Literal["md", "pdf", "docx", "jpg"] = Query("md"),
    current_user: User = Depends(get_current_user),
    store: RuntimeStore = Depends(get_runtime_store),
):
    artifact = await store.get_artifact(artifact_id)
    if artifact is None or artifact.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Artifact not found")
    if not artifact.content:
        raise HTTPException(status_code=409, detail="该产物没有可导出的文本内容")
    filename = f"ophagent-{artifact.id}.{format}"
    if format == "md":
        payload = artifact.content.encode("utf-8")
        media_type = "text/markdown; charset=utf-8"
    elif format == "pdf":
        payload = render_pdf(artifact.content, artifact.title)
        media_type = "application/pdf"
    elif format == "docx":
        payload = render_docx(artifact.content, artifact.title)
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    else:
        payload = render_jpg(artifact.content, artifact.title)
        media_type = "image/jpeg"
    return Response(
        content=payload,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/artifacts/{artifact_id}/download")
async def download_artifact(
    artifact_id: str,
    current_user: User = Depends(get_current_user),
    store: RuntimeStore = Depends(get_runtime_store),
):
    artifact = await store.get_artifact(artifact_id)
    if artifact is None or artifact.user_id != current_user.id or not artifact.path:
        raise HTTPException(status_code=404, detail="Artifact file not found")
    path = settings.resolve_path(artifact.path)
    if not path.is_file() or settings.resolve_path(settings.ARTIFACT_DIR) not in path.resolve().parents:
        raise HTTPException(status_code=404, detail="Artifact file not found")
    return FileResponse(path, media_type=artifact.mime_type, filename=path.name)


class MemoryCreate(BaseModel):
    category: Literal[
        "preference",
        "history",
        "medication",
        "allergy",
        "follow_up",
        "workspace",
    ]
    content: str = Field(min_length=1, max_length=5000)
    source: str = Field(min_length=1, max_length=500)
    key: str | None = Field(default=None, max_length=500)


class MemoryUpdate(BaseModel):
    content: str | None = Field(default=None, min_length=1, max_length=5000)
    status: Literal["proposed", "confirmed", "rejected"] | None = None
    confirmation_note: str | None = Field(default=None, max_length=1000)


async def _record_memory_evolution(
    store: MemoryStore,
    memory: MemoryRecord,
    action: str,
) -> None:
    controller = getattr(store, "evolution", None)
    if controller is None:
        return
    try:
        await controller.record_memory_action(memory, action)
    except (OSError, TypeError, ValueError):
        # Memory governance is the source of truth; optional improvement
        # telemetry may never turn a successful edit into an API failure.
        return


@router.get("/memories", response_model=list[MemoryRecord])
async def list_memories(
    current_user: User = Depends(get_current_user),
    store: MemoryStore = Depends(get_memory_store),
):
    return await store.list(int(current_user.id))


@router.get("/memories/preference")
async def get_memory_preference(
    current_user: User = Depends(get_current_user),
    store: MemoryStore = Depends(get_memory_store),
):
    return {"enabled": await store.enabled(int(current_user.id))}


class MemoryPreferenceUpdate(BaseModel):
    enabled: bool


@router.patch("/memories/preference")
async def update_memory_preference(
    payload: MemoryPreferenceUpdate,
    current_user: User = Depends(get_current_user),
    store: MemoryStore = Depends(get_memory_store),
    session: Session = Depends(get_session),
):
    enabled = await store.set_enabled(int(current_user.id), payload.enabled)
    _audit(session, current_user, "update_preference", "memory", details=f'{{"enabled":{str(enabled).lower()}}}')
    return {"enabled": enabled}


@router.get("/memories/search", response_model=list[MemoryRecord])
async def search_memories(
    q: str = Query(min_length=1, max_length=2000),
    limit: int = Query(default=8, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    store: MemoryStore = Depends(get_memory_store),
):
    return await store.search(int(current_user.id), q, limit=limit)


@router.post("/memories", response_model=MemoryRecord)
async def create_memory(
    payload: MemoryCreate,
    current_user: User = Depends(get_current_user),
    store: MemoryStore = Depends(get_memory_store),
    session: Session = Depends(get_session),
):
    try:
        created = await store.create(
            MemoryRecord(user_id=int(current_user.id), **payload.model_dump()),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await _record_memory_evolution(store, created, "created")
    _audit(session, current_user, "create", "memory", created.id)
    return created


@router.patch("/memories/{memory_id}", response_model=MemoryRecord)
async def update_memory(
    memory_id: str,
    payload: MemoryUpdate,
    current_user: User = Depends(get_current_user),
    store: MemoryStore = Depends(get_memory_store),
    session: Session = Depends(get_session),
):
    try:
        previous = next(
            (
                item
                for item in await store.list(int(current_user.id))
                if item.id == memory_id
            ),
            None,
        )
        updated = await store.update(memory_id, int(current_user.id), payload.model_dump(exclude_none=True))
        action = (
            updated.status
            if previous is None or previous.status != updated.status
            else "edited"
            if previous.content != updated.content
            else "reviewed"
        )
        await _record_memory_evolution(store, updated, action)
        _audit(session, current_user, "update", "memory", memory_id)
        return updated
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Memory not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/memories/{memory_id}", status_code=204)
async def delete_memory(
    memory_id: str,
    current_user: User = Depends(get_current_user),
    store: MemoryStore = Depends(get_memory_store),
    session: Session = Depends(get_session),
):
    try:
        previous = next(
            (
                item
                for item in await store.list(int(current_user.id))
                if item.id == memory_id
            ),
            None,
        )
        await store.delete(memory_id, int(current_user.id))
        if previous is not None:
            await _record_memory_evolution(store, previous, "deleted")
        _audit(session, current_user, "delete", "memory", memory_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Memory not found") from exc


class SkillStatusUpdate(BaseModel):
    status: Literal["enabled", "disabled", "rejected"]
    force: bool = False
    risk_acknowledgement: str | None = Field(default=None, max_length=1000)


class SkillImport(BaseModel):
    markdown: str = Field(min_length=1, max_length=100_000)


@router.get("/skills", response_model=list[SkillRecord])
async def list_skills(
    current_user: User = Depends(get_current_user),
    store: SkillStore = Depends(get_skill_store),
):
    return await store.list()


@router.post("/skills/import", response_model=SkillRecord, status_code=201)
async def import_skill(
    payload: SkillImport,
    current_user: User = Depends(get_current_user),
    store: SkillStore = Depends(get_skill_store),
    session: Session = Depends(get_session),
):
    try:
        created = await store.import_candidate(payload.markdown)
        _audit(session, current_user, "import", "skill", created.id)
        return created
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/skills/{skill_id}/validate", response_model=SkillRecord)
async def validate_skill(
    skill_id: str,
    current_user: User = Depends(get_current_user),
    store: SkillStore = Depends(get_skill_store),
    session: Session = Depends(get_session),
):
    try:
        validated = await store.validate(skill_id)
        _audit(session, current_user, "validate", "skill", skill_id)
        return validated
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Skill not found") from exc


@router.patch("/skills/{skill_id}", response_model=SkillRecord)
async def update_skill(
    skill_id: str,
    payload: SkillStatusUpdate,
    current_user: User = Depends(get_current_user),
    store: SkillStore = Depends(get_skill_store),
    session: Session = Depends(get_session),
):
    try:
        updated = await store.set_status(
            skill_id,
            payload.status,
            force=payload.force,
            approved_by=f"user:{current_user.id}",
            acknowledgement=payload.risk_acknowledgement,
        )
        _audit(
            session,
            current_user,
            "set_status",
            "skill",
            skill_id,
            (
                f'{{"status":"{payload.status}",'
                f'"force":{str(payload.force).lower()}}}'
            ),
        )
        return updated
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Skill not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/knowledge/search")
async def search_knowledge(
    q: str = Query(min_length=1, max_length=2000),
    top_k: int = Query(6, ge=1, le=20),
    current_user: User = Depends(get_current_user),
    clients: CapabilityClients = Depends(get_capability_clients),
):
    result = await clients.retrieve_medical_evidence(
        q,
        top_k,
        user_id=int(current_user.id),
    )
    return {"query": q, **result.data}


@router.get("/knowledge/status")
async def knowledge_status(
    current_user: User = Depends(get_current_user),
    clients: CapabilityClients = Depends(get_capability_clients),
):
    await clients.retriever._ensure_index()
    status = clients.retriever.status().model_dump(mode="json")
    status["retrieval"] = ["BM25", "BGE-M3", "Rerank", "page_evidence", "OphthaKG"]
    return status


@router.get("/knowledge/sources", response_model=list[KnowledgeSource])
async def list_knowledge_sources(current_user: User = Depends(get_current_user)):
    return SourceRegistry(settings).list(
        user_id=int(current_user.id),
        include_private=False,
    )


class KnowledgeSourceUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    institution: str | None = Field(default=None, max_length=500)
    region: str | None = Field(default=None, max_length=100)
    published_at: str | None = Field(default=None, max_length=100)
    version: str | None = Field(default=None, max_length=100)
    population: str | None = Field(default=None, max_length=500)
    status: Literal["current", "expired", "superseded", "unknown"] | None = None
    superseded_by: str | None = Field(default=None, max_length=500)
    verified: bool | None = None
    verification_note: str | None = Field(default=None, max_length=1000)


@router.patch("/knowledge/sources/{source_id}", response_model=KnowledgeSource)
async def update_knowledge_source(
    source_id: str,
    payload: KnowledgeSourceUpdate,
    current_user: User = Depends(get_current_user),
    clients: CapabilityClients = Depends(get_capability_clients),
    session: Session = Depends(get_session),
):
    registry = SourceRegistry(settings)
    try:
        source = registry.get(source_id)
        if (
            source.imported_by is not None
            and source.imported_by != int(current_user.id)
        ):
            raise HTTPException(status_code=404, detail="Knowledge source not found")
        updated = registry.update(
            source_id,
            payload.model_dump(exclude_none=True),
            verified_by=int(current_user.id),
        )
        clients.retriever.invalidate()
        _audit(session, current_user, "update", "knowledge_source", source_id)
        return updated
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Knowledge source not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/knowledge/import", response_model=KnowledgeSource, status_code=201)
async def import_knowledge_source(
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    institution: str | None = Form(default=None),
    region: str | None = Form(default=None),
    published_at: str | None = Form(default=None),
    current_user: User = Depends(get_current_user),
    clients: CapabilityClients = Depends(get_capability_clients),
    session: Session = Depends(get_session),
):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".md", ".txt", ".pdf"}:
        raise HTTPException(status_code=415, detail="仅支持 md、txt、pdf")
    content = await file.read(settings.MAX_UPLOAD_BYTES + 1)
    if len(content) > settings.MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="文件超过上传大小限制")
    from uuid import uuid4

    target = settings.resolve_path(settings.KNOWLEDGE_RAW_DIR) / (
        f"user_{current_user.id}_{uuid4().hex}{suffix}"
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    registered = SourceRegistry(settings).register_upload(
        target,
        user_id=int(current_user.id),
        title=title or Path(file.filename or "").stem or None,
        institution=institution,
        region=region,
        published_at=published_at,
    )
    clients.retriever.invalidate()
    _audit(session, current_user, "import", "knowledge_source", registered.id)
    return registered


@router.post("/knowledge/index", status_code=202)
async def rebuild_knowledge_index(
    background_tasks: BackgroundTasks,
    include_embeddings: bool = True,
    current_user: User = Depends(get_current_user),
    clients: CapabilityClients = Depends(get_capability_clients),
    session: Session = Depends(get_session),
):
    if clients.retriever.status().status == "building":
        raise HTTPException(status_code=409, detail="知识索引正在构建")
    background_tasks.add_task(
        clients.retriever.rebuild,
        include_embeddings=include_embeddings,
    )
    _audit(
        session,
        current_user,
        "rebuild_index",
        "knowledge",
        details=f'{{"include_embeddings":{str(include_embeddings).lower()}}}',
    )
    return {
        "status": "accepted",
        "include_embeddings": include_embeddings,
        "detail": "索引构建已排队；请轮询 /api/v1/knowledge/status",
    }

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import fitz
import pytest

from app.core.config import Settings
from app.domain.models import MemoryRecord
from app.knowledge.retrieval import HybridKnowledgeRetriever
from app.knowledge.sources import SourceRegistry, _atomic_json
from app.runtime.agents import AgentScopeRunner
from app.services.state import (
    MemoryStore,
    PersistentStateError,
    SkillStore,
    atomic_json,
)
from scripts.build_knowledge_base import SourceSpec, collect_documents
from tests.fakes import FakeCapabilityClients


def build_settings(tmp_path) -> Settings:
    return Settings(
        _env_file=None,
        ENVIRONMENT="test",
        STRICT_STARTUP=False,
        KNOWLEDGE_RAW_DIR=str(tmp_path / "knowledge" / "raw"),
        KNOWLEDGE_INDEX_DIR=str(tmp_path / "knowledge" / "index"),
        MEMORY_STATE_PATH=str(tmp_path / "memories.json"),
        MEMORY_PREFERENCE_PATH=str(tmp_path / "memory-preferences.json"),
        SKILL_STATE_PATH=str(tmp_path / "skill-states.json"),
        SKILL_ROOT=str(tmp_path / "skills"),
        SKILL_EVALUATION_DIR=str(tmp_path / "skill-evaluations"),
        EMBEDDING_MODEL="",
        RERANK_MODEL="",
    )


@pytest.mark.asyncio
async def test_page_level_index_and_source_lifecycle(tmp_path):
    config = build_settings(tmp_path)
    raw = config.resolve_path(config.KNOWLEDGE_RAW_DIR)
    raw.mkdir(parents=True)
    (raw / "青光眼指南（2024）.md").write_text(
        "# 青光眼\n\n青光眼评估应记录眼压、视野与视神经结构，并结合患者情况复核。",
        "utf-8",
    )
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "OCT page visual evidence " * 8)
    document.save(raw / "OCT流程（2025）.pdf")
    document.close()

    retriever = HybridKnowledgeRetriever(config)
    status = await retriever.load()
    assert status.documents == 2
    assert status.page_visuals >= 1
    assert status.graph_nodes >= 1
    assert (await retriever.rebuild(include_embeddings=False)).status == "ready"
    result = await retriever.search("青光眼眼压检查", top_k=2)
    assert result
    assert result[0].locator
    assert result[0].source_status == "unknown"
    glaucoma = next(
        item for item in SourceRegistry(config).list() if "青光眼" in item.title
    )
    SourceRegistry(config).update(glaucoma.id, {"status": "expired"})
    retriever.invalidate()
    after_expiry = await retriever.search("青光眼眼压检查", top_k=2)
    assert all(item.title != glaucoma.title for item in after_expiry)


def test_portable_knowledge_collection_deduplicates_content(tmp_path):
    source = tmp_path / "external"
    target = tmp_path / "raw"
    source.mkdir()
    (source / "guide.md").write_text("# 指南\n\n青光眼检查建议。", "utf-8")
    nested = source / "nested"
    nested.mkdir()
    (nested / "copy.md").write_text("# 指南\n\n青光眼检查建议。", "utf-8")

    imported, skipped = collect_documents(
        [SourceSpec(name="local", path=source)],
        target,
    )

    assert imported == 1
    assert skipped == 1
    assert len(list(target.glob("*.md"))) == 1


def test_atomic_source_registry_writes_are_safe_under_concurrency(tmp_path):
    path = tmp_path / "index" / "sources.json"

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(lambda index: _atomic_json(path, {"writer": index}), range(64)))

    payload = json.loads(path.read_text("utf-8"))
    assert payload["writer"] in range(64)
    assert list(path.parent.glob(".sources.json.*.tmp")) == []


@pytest.mark.asyncio
async def test_user_knowledge_sources_are_isolated_in_listing_and_retrieval(tmp_path):
    config = build_settings(tmp_path)
    raw = config.resolve_path(config.KNOWLEDGE_RAW_DIR)
    raw.mkdir(parents=True)
    public_path = raw / "public.md"
    public_path.write_text(
        "# Public\n\npublicbaseline retinal evidence available to every authenticated user.",
        "utf-8",
    )
    owner_path = raw / "owner-a.md"
    owner_path.write_text(
        "# Private\n\nowneralpha confidential retinal observation only for the importing user.",
        "utf-8",
    )
    registry = SourceRegistry(config)
    private_source = registry.register_upload(
        owner_path,
        user_id=101,
        title="Owner A private source",
    )

    owner_sources = registry.list(user_id=101)
    other_sources = registry.list(user_id=202)
    assert private_source.id in {item.id for item in owner_sources}
    assert private_source.id not in {item.id for item in other_sources}
    assert any(item.imported_by is None for item in other_sources)

    retriever = HybridKnowledgeRetriever(config)
    owner_results = await retriever.search(
        "owneralpha",
        top_k=3,
        user_id=101,
    )
    other_results = await retriever.search(
        "owneralpha",
        top_k=3,
        user_id=202,
    )
    assert any(item.title == private_source.title for item in owner_results)
    assert all(item.title != private_source.title for item in other_results)


@pytest.mark.asyncio
async def test_memory_conflict_ranking_and_disable(tmp_path):
    store = MemoryStore(build_settings(tmp_path))
    first = await store.create(
        MemoryRecord(
            user_id=1,
            category="history",
            key="lens-status:right",
            content="右眼仍保留晶状体",
            source="用户确认",
            status="confirmed",
        ),
    )
    second = await store.create(
        MemoryRecord(
            user_id=1,
            category="history",
            key="lens-status:right",
            content="右眼已植入人工晶状体",
            source="后续用户输入",
        ),
    )
    assert first.id in second.conflicts_with
    records = await store.list(1)
    assert second.id in next(item for item in records if item.id == first.id).conflicts_with
    assert await store.search(1, "右眼晶状体")
    await store.set_enabled(1, False)
    assert await store.search(1, "右眼晶状体") == []


@pytest.mark.asyncio
async def test_corrupt_memory_state_fails_closed_without_overwrite(tmp_path):
    config = build_settings(tmp_path)
    path = config.resolve_path(config.MEMORY_STATE_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{broken-json", "utf-8")
    store = MemoryStore(config)

    with pytest.raises(PersistentStateError):
        await store.list(1)
    with pytest.raises(PersistentStateError):
        await store.create(
            MemoryRecord(
                user_id=1,
                category="preference",
                content="回答简洁",
                source="用户确认",
            ),
        )
    assert path.read_text("utf-8") == "{broken-json"


@pytest.mark.asyncio
async def test_confirmed_conflicting_memories_are_withheld_from_model_context(tmp_path):
    store = MemoryStore(build_settings(tmp_path))
    first = await store.create(
        MemoryRecord(
            user_id=3,
            category="medication",
            key="current-eye-drop",
            content="当前使用噻吗洛尔滴眼液",
            source="用户确认",
            status="confirmed",
        ),
    )
    second = await store.create(
        MemoryRecord(
            user_id=3,
            category="medication",
            key="current-eye-drop",
            content="已停用噻吗洛尔滴眼液",
            source="用户确认",
            status="confirmed",
        ),
    )

    result = await store.search(
        3,
        "我现在使用什么眼药？",
        categories={"medication"},
    )

    assert first.id in second.conflicts_with
    assert result == []


@pytest.mark.asyncio
async def test_skill_candidate_requires_matching_evaluation(tmp_path):
    store = SkillStore(build_settings(tmp_path))
    markdown = """---
name: candidate_triage
version: 1.2.0
description: 测试候选红旗分诊技能
risk_level: high
capabilities: [triage]
plugins: [aux_diagnosis]
---

# 红旗分诊

遇到高风险情况优先提示急诊或线下眼科评估，陈述不确定性并绑定证据。
"""
    imported = await store.import_candidate(markdown)
    assert imported.status == "candidate"
    with pytest.raises(ValueError):
        await store.set_status(imported.id, "enabled")
    validated = await store.validate(imported.id)
    assert validated.status == "validated"
    assert validated.evaluation["passed"] is True
    assert validated.evaluation["offline_review_required"] is True
    with pytest.raises(ValueError, match="离线人工审核"):
        await store.set_status(imported.id, "enabled")
    tampered = store._states()
    tampered[imported.id]["status"] = "enabled"
    atomic_json(store.path, tampered)
    runner = AgentScopeRunner(FakeCapabilityClients(), store.config)
    runner.set_run_context("aux_diagnosis")
    assert not any(
        path.name == "1.2.0"
        for path in runner._enabled_skill_paths("ClinicalReasoningAgent")
    )
    tampered[imported.id]["status"] = "validated"
    atomic_json(store.path, tampered)
    await store.approve_offline(imported.id, "clinical-safety-reviewer")
    enabled = await store.set_status(imported.id, "enabled")
    assert enabled.status == "enabled"
    assert any(
        path.name == "1.2.0"
        for path in runner._enabled_skill_paths("ClinicalReasoningAgent")
    )
    assert not any(
        path.name == "1.2.0"
        for path in runner._enabled_skill_paths("EvidenceAgent")
    )
    skill_md = Path(enabled.path) / "SKILL.md"
    skill_md.write_text(skill_md.read_text("utf-8") + "\n内容被修改。\n", "utf-8")
    assert not any(
        path.name == "1.2.0"
        for path in runner._enabled_skill_paths("ClinicalReasoningAgent")
    )


@pytest.mark.asyncio
async def test_safety_critical_skill_cannot_be_disabled_online(tmp_path):
    store = SkillStore(build_settings(tmp_path))
    with pytest.raises(ValueError, match="安全关键"):
        await store.set_status("red_flag_triage", "disabled")

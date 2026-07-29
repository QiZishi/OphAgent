from __future__ import annotations

import json

import pytest

from app.core.config import Settings
from app.domain.models import MemoryRecord, RunEvent, RunInput, RunRecord, RunStatus
from app.evolution.continuous import ContinuousEvolutionController
from app.plugins.registry import plugin_registry


def build_controller(tmp_path) -> ContinuousEvolutionController:
    config = Settings(
        _env_file=None,
        ENVIRONMENT="test",
        STRICT_STARTUP=False,
        EVOLUTION_STATE_DIR=str(tmp_path / "evolution"),
        EVOLUTION_MIN_FEEDBACK_SAMPLES=3,
        EVOLUTION_NEGATIVE_RATE_THRESHOLD=0.6,
    )
    return ContinuousEvolutionController(config)


def build_run(index: int) -> RunRecord:
    return RunRecord(
        id=f"run_{index:032x}",
        user_id=42,
        status=RunStatus.COMPLETED,
        input=RunInput(query=f"private clinical query {index}"),
        plugin=plugin_registry.get("core"),
    )


@pytest.mark.asyncio
async def test_feedback_drives_bounded_memory_and_skill_candidates_without_content(tmp_path):
    controller = build_controller(tmp_path)
    memory_id = "mem_" + "a" * 32
    for index in range(3):
        run = build_run(index)
        events = [
            RunEvent(
                run_id=run.id,
                trace_id=run.trace_id,
                type="memory.recalled",
                public_summary="memory used",
                data={
                    "memories": [
                        {"id": memory_id, "category": "history"},
                    ],
                },
            ),
            RunEvent(
                run_id=run.id,
                trace_id=run.trace_id,
                type="agent.completed",
                public_summary="agent completed",
                data={"used_skills": ["guideline_retrieval"]},
            ),
        ]
        await controller.record_run_outcome(run, events)
        await controller.record_feedback(run, None, "down", events)

    status = await controller.status()
    assert status.ready_candidate_count >= 2
    assert any(
        item.kind == "memory_retrieval" and item.target == "history"
        for item in status.candidates
    )
    assert any(item.kind == "skill" for item in status.candidates)
    assert controller.memory_utility_factor(memory_id, "history") == 1.0

    signals = controller.signal_path.read_text("utf-8")
    assert "private clinical query" not in signals
    assert '"user_id"' not in signals
    for line in signals.splitlines():
        json.loads(line)


@pytest.mark.asyncio
async def test_rejected_memory_candidates_create_extraction_work_item(tmp_path):
    controller = build_controller(tmp_path)
    for index in range(3):
        memory = MemoryRecord(
            id=f"mem_{index:032x}",
            user_id=7,
            category="medication",
            content=f"private medication {index}",
            source="user",
            status="rejected",
        )
        await controller.record_memory_action(memory, "rejected")

    status = await controller.status()
    candidate = next(
        item
        for item in status.candidates
        if item.kind == "memory_extraction" and item.target == "medication"
    )
    assert candidate.requires_human_approval
    assert candidate.allowed_mutation_paths == ["app/services/state.py"]
    assert "private medication" not in controller.signal_path.read_text("utf-8")


@pytest.mark.asyncio
async def test_only_repeated_positive_feedback_boosts_nonclinical_memory(tmp_path):
    controller = build_controller(tmp_path)
    memory_id = "mem_" + "b" * 32
    for index in range(3):
        run = build_run(index)
        events = [
            RunEvent(
                run_id=run.id,
                trace_id=run.trace_id,
                type="memory.recalled",
                public_summary="memory used",
                data={"memories": [{"id": memory_id, "category": "preference"}]},
            ),
        ]
        await controller.record_feedback(run, None, "up", events)

    assert controller.memory_utility_factor(memory_id, "preference") > 1
    assert controller.memory_utility_factor(memory_id, "medication") == 1

    run = build_run(0)
    await controller.record_feedback(run, "up", "down", events)
    assert controller.memory_utility_factor(memory_id, "preference") == 1

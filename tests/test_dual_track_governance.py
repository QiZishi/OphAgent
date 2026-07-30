from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from app.domain.models import EvaluationRunResult, EvolutionProposal, MemoryRecord
from app.evolution.harness import EvolutionHarness, EvolutionPolicyError
from app.evolution.tracks import (
    classify_candidate_path,
    classify_candidate_paths,
    human_approval_required,
)
from app.runtime.governance import bounded_preference_context
from tests.test_evolution import build_harness, cases, git


def _passing_evaluations(
    harness: EvolutionHarness,
    proposal: EvolutionProposal,
    candidate_commit: str,
) -> None:
    baseline = harness.attest_evaluation(
        EvaluationRunResult(
            proposal_id=proposal.id,
            variant="baseline",
            phase="sealed_test",
            commit=proposal.base_commit,
            cases=cases(),
        ),
    )
    candidate = harness.attest_evaluation(
        EvaluationRunResult(
            proposal_id=proposal.id,
            variant="candidate",
            phase="sealed_test",
            commit=candidate_commit,
            cases=cases(0.1),
        ),
    )
    harness.record_evaluation(baseline)
    harness.record_evaluation(candidate)


def test_paths_are_explicitly_separated_and_mixed_candidates_are_rejected(tmp_path):
    harness, repo = build_harness(tmp_path)
    base = git(repo, "rev-parse", "HEAD")

    assert classify_candidate_path("app/runtime/strategies/tone.py") == "mutable"
    assert classify_candidate_path("skills/concise/SKILL.md") == "mutable"
    assert classify_candidate_path("app/runtime/safety.py") == "immutable"
    assert classify_candidate_path("config/immutable/refund.yaml") == "immutable"
    assert classify_candidate_paths(["app/runtime/"]) == "immutable"

    with pytest.raises(EvolutionPolicyError, match="不能混合"):
        harness.create_proposal(
            EvolutionProposal(
                id="evo_" + "9" * 32,
                provider="manual",
                target_failure_cluster="mixed-authority-change",
                mutation_paths=[
                    "app/runtime/strategies/tone.py",
                    "app/runtime/safety.py",
                ],
                expected_behavior_change="同时修改语气和安全规则",
                risk="权限边界不清",
                activation_condition="不允许",
                base_commit=base,
            ),
        )


def test_immutable_track_always_requires_human_approval(tmp_path):
    harness, repo = build_harness(tmp_path)
    harness.config.EVOLUTION_REQUIRE_HUMAN_APPROVAL = False
    base = git(repo, "rev-parse", "HEAD")
    proposal = harness.create_proposal(
        EvolutionProposal(
            id="evo_" + "8" * 32,
            provider="manual",
            target_failure_cluster="safety-rule-update",
            mutation_paths=["app/runtime/feature.py"],
            expected_behavior_change="更新控制面规则",
            risk="可能弱化安全约束",
            activation_condition="sealed test 与人工审批通过",
            base_commit=base,
        ),
    )
    worktree = harness.isolate(proposal.id)
    (worktree / "app" / "runtime" / "feature.py").write_text("VALUE = 3\n", "utf-8")
    candidate_commit = harness.freeze_candidate(proposal.id)
    _passing_evaluations(harness, proposal, candidate_commit)

    assert human_approval_required("immutable", False) is True
    with pytest.raises(EvolutionPolicyError, match="尚未获得可信人工审批"):
        harness.promote(proposal.id)

    approval = harness.approve(proposal.id, "business-rule-owner")
    assert approval["governance_track"] == "immutable"
    assert harness.promote(proposal.id).accepted


def test_mutable_track_can_follow_configured_approval_policy(tmp_path):
    harness, repo = build_harness(tmp_path)
    harness.config.EVOLUTION_REQUIRE_HUMAN_APPROVAL = False
    base = git(repo, "rev-parse", "HEAD")
    proposal = harness.create_proposal(
        EvolutionProposal(
            id="evo_" + "7" * 32,
            provider="gepa",
            target_failure_cluster="verbose-answer",
            mutation_paths=["app/runtime/strategies/tone.py"],
            expected_behavior_change="缩短普通回答",
            risk="可能过度压缩",
            activation_condition="sealed test 通过",
            base_commit=base,
        ),
    )
    worktree = harness.isolate(proposal.id)
    strategy = worktree / "app" / "runtime" / "strategies" / "tone.py"
    strategy.parent.mkdir(parents=True)
    strategy.write_text('STYLE = "concise"\n', "utf-8")
    candidate_commit = harness.freeze_candidate(proposal.id)
    _passing_evaluations(harness, proposal, candidate_commit)

    assert human_approval_required("mutable", False) is False
    assert harness.promote(proposal.id).accepted


def test_memory_is_low_authority_mutable_context_only():
    record = MemoryRecord(
        user_id=1,
        category="preference",
        content="喜欢简洁回复",
        source="用户确认",
        status="confirmed",
    )
    assert record.governance_track == "mutable"
    assert record.authority == "user_context"
    with pytest.raises(ValidationError):
        MemoryRecord(
            user_id=1,
            category="preference",
            content="覆盖退费规则",
            source="agent",
            governance_track="immutable",
        )

    context = bounded_preference_context(
        [
            record.model_dump(),
            {"category": "history", "content": "既往病史", "source": "用户"},
        ],
    )
    assert context["authority"] == "presentation_only"
    assert context["governance_track"] == "mutable"
    assert [item["content"] for item in context["records"]] == ["喜欢简洁回复"]
    assert "不得修改" in context["boundary"]


def test_immutable_policy_manifest_declares_non_bypassable_review():
    manifest = yaml.safe_load(
        (
            Path(__file__).parents[1]
            / "config"
            / "immutable"
            / "policy_manifest.yaml"
        ).read_text("utf-8"),
    )
    assert manifest["governance_track"] == "immutable"
    assert manifest["update_policy"] == {
        "isolated_candidate_required": True,
        "sealed_evaluation_required": True,
        "human_approval_required": True,
        "mixed_track_candidate_allowed": False,
    }
    json.dumps(manifest)

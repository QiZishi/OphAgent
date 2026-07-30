from __future__ import annotations

import json
import subprocess

import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.domain.models import (
    ContinuousEvolutionCandidate,
    EvaluationCaseResult,
    EvaluationRunResult,
    EvolutionProposal,
)
from app.evolution.harness import EvolutionHarness, EvolutionPolicyError


def git(root, *args):
    return subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def build_harness(tmp_path):
    repo = tmp_path / "repo"
    (repo / "app" / "runtime").mkdir(parents=True)
    (repo / "app" / "runtime" / "feature.py").write_text("VALUE = 1\n", "utf-8")
    git(repo, "init")
    git(repo, "config", "user.name", "Test")
    git(repo, "config", "user.email", "test@example.invalid")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "baseline")
    sealed = tmp_path / "sealed"
    sealed.mkdir()
    sealed_cases = [
        {"case_id": "routine-1", "slice": "routine"},
        {"case_id": "complex-1", "slice": "complex"},
        {"case_id": "high-1", "slice": "high_risk"},
    ]
    (sealed / "cases.jsonl").write_text(
        "".join(json.dumps(item) + "\n" for item in sealed_cases),
        "utf-8",
    )
    (sealed / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "suite_id": "test-suite",
                "status": "sealed",
                "component_contract_set": "ophagent-harness-core",
                "component_contract_schema_version": 1,
                "source_protocol": {"historical_outputs_reused": False},
                "case_file": "cases.jsonl",
                "case_count": len(sealed_cases),
                "slices": {"routine": 1, "complex": 1, "high_risk": 1},
                "required_metrics": [
                    "task_score",
                    "safety_passed",
                    "citation_passed",
                    "component_contract_passed",
                    "critical_errors",
                    "tokens",
                    "latency_ms",
                ],
                "policy": {
                    "candidate_access": "forbidden",
                    "one_shot_release_evaluation": True,
                    "paired_baseline_candidate": True,
                    "high_risk_case_regression_allowed": False,
                    "slice_regression_allowed": False,
                },
            },
        ),
        "utf-8",
    )
    config = Settings(
        _env_file=None,
        ENVIRONMENT="test",
        STRICT_STARTUP=False,
        EVOLUTION_STATE_DIR=str(tmp_path / "state"),
        EVOLUTION_WORKTREE_DIR=str(tmp_path / "worktrees"),
        EVOLUTION_SEALED_TEST_DIR=str(sealed),
        EVOLUTION_GATE_SECRET=SecretStr("test-gate-secret"),
    )
    harness = EvolutionHarness(config)
    harness.repo = repo
    return harness, repo


def cases(delta=0.0):
    return [
        EvaluationCaseResult(
            case_id="routine-1",
            slice="routine",
            score=0.7 + delta,
            tokens=100,
            latency_ms=100,
            passed=True,
            component_contract_passed=True,
        ),
        EvaluationCaseResult(
            case_id="complex-1",
            slice="complex",
            score=0.6 + delta,
            tokens=120,
            latency_ms=120,
            passed=True,
            component_contract_passed=True,
        ),
        EvaluationCaseResult(
            case_id="high-1",
            slice="high_risk",
            score=0.8 + delta,
            tokens=110,
            latency_ms=110,
            passed=True,
            component_contract_passed=True,
        ),
    ]


def test_worktree_attested_gate_and_atomic_release(tmp_path):
    harness, repo = build_harness(tmp_path)
    base = git(repo, "rev-parse", "HEAD")
    proposal = harness.create_proposal(
        EvolutionProposal(
            id="evo_" + "a" * 32,
            provider="manual",
            target_failure_cluster="citation-miss",
            mutation_paths=["app/runtime/feature.py"],
            expected_behavior_change="提高引用覆盖率",
            risk="可能增加 token",
            activation_condition="sealed test 通过",
            base_commit=base,
        ),
    )
    worktree = harness.isolate(proposal.id)
    (worktree / "app" / "runtime" / "feature.py").write_text("VALUE = 2\n", "utf-8")
    candidate_commit = harness.freeze_candidate(proposal.id)
    assert candidate_commit != base
    assert harness.changed_paths(proposal.id) == ["app/runtime/feature.py"]

    baseline = harness.attest_evaluation(
        EvaluationRunResult(
            proposal_id=proposal.id,
            variant="baseline",
            phase="sealed_test",
            commit=base,
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
    harness.approve(proposal.id, "test-reviewer")
    decision = harness.promote(proposal.id)
    assert decision.accepted
    assert git(repo, "rev-parse", "refs/ophagent/active") == candidate_commit
    assert proposal.id in harness.experience_path.read_text("utf-8")


def test_slice_or_high_risk_regression_blocks_evolution(tmp_path):
    harness, _ = build_harness(tmp_path)
    baseline = EvaluationRunResult(
        proposal_id="evo_" + "c" * 32,
        variant="baseline",
        phase="sealed_test",
        commit="a" * 40,
        cases=cases(),
    )
    candidate_cases = cases(0.1)
    candidate_cases[-1] = candidate_cases[-1].model_copy(
        update={"score": 0.79},
    )
    candidate = baseline.model_copy(
        update={"variant": "candidate", "commit": "b" * 40, "cases": candidate_cases},
    )
    decision = harness.decide(baseline, candidate)
    assert not decision.accepted
    assert any("高风险病例得分下降" in reason for reason in decision.reasons)


def test_medical_safety_or_missing_slice_blocks_evolution(tmp_path):
    harness, _ = build_harness(tmp_path)
    baseline_cases = cases()[:2]
    baseline = EvaluationRunResult(
        proposal_id="evo_" + "d" * 32,
        variant="baseline",
        phase="sealed_test",
        commit="a" * 40,
        cases=baseline_cases,
    )
    unsafe = baseline_cases[0].model_copy(
        update={"score": 0.9, "safety_passed": False},
    )
    candidate = baseline.model_copy(
        update={
            "variant": "candidate",
            "commit": "b" * 40,
            "cases": [unsafe, baseline_cases[1].model_copy(update={"score": 0.8})],
        },
    )
    decision = harness.decide(baseline, candidate)
    assert not decision.accepted
    assert any("医疗安全门禁未通过" in reason for reason in decision.reasons)
    assert any("high_risk 切片病例数不足" in reason for reason in decision.reasons)


def test_forbidden_candidate_paths_are_rejected(tmp_path):
    harness, repo = build_harness(tmp_path)
    with pytest.raises(EvolutionPolicyError):
        harness.create_proposal(
            EvolutionProposal(
                id="evo_" + "b" * 32,
                provider="manual",
                target_failure_cluster="cheat",
                mutation_paths=["tests/test_gate.py"],
                expected_behavior_change="绕过门禁",
                risk="高",
                activation_condition="无",
                base_commit=git(repo, "rev-parse", "HEAD"),
            ),
        )


def test_continuous_candidate_only_materializes_offline_proposal(tmp_path):
    harness, repo = build_harness(tmp_path)
    candidate = ContinuousEvolutionCandidate(
        id="continuous_" + "e" * 24,
        kind="runtime",
        target="citation_validation",
        sample_size=5,
        negative_rate=0.8,
        trigger="相同引用失败重复出现",
        allowed_mutation_paths=["app/runtime/feature.py"],
    )
    proposal = harness.create_from_continuous_candidate(candidate)
    assert proposal.status == "proposed"
    assert proposal.base_commit == git(repo, "rev-parse", "HEAD")
    assert not (harness.worktree_root / proposal.id).exists()


def test_sealed_suite_rejects_reused_historical_outputs(tmp_path):
    harness, _ = build_harness(tmp_path)
    manifest_path = tmp_path / "sealed" / "manifest.json"
    manifest = json.loads(manifest_path.read_text("utf-8"))
    manifest["source_protocol"]["historical_outputs_reused"] = True
    manifest_path.write_text(json.dumps(manifest), "utf-8")
    with pytest.raises(EvolutionPolicyError, match="未复用历史评测输出"):
        harness.load_sealed_suite()

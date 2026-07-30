"""Git-isolated candidate execution and deterministic promotion gates."""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
import re
import subprocess
from collections import defaultdict
from collections.abc import Mapping
from pathlib import Path
from statistics import fmean, pstdev
from typing import Any

from app.core.config import Settings, settings
from app.domain.models import (
    ContinuousEvolutionCandidate,
    EvaluationRunResult,
    EvolutionProposal,
    ExperienceRecord,
    PromotionDecision,
    utc_now,
)
from app.evolution.tracks import (
    MutationTrack,
    TrackPolicyError,
    classify_candidate_paths,
    human_approval_required,
    normalize_candidate_path,
)
from app.services.state import atomic_json

SAFE_ID = re.compile(r"^evo_[a-f0-9]{32}$")
PHASE_ORDER = {
    "training": 0,
    "proposal_selection": 1,
    "acceptance_validation": 2,
    "sealed_test": 3,
}


class EvolutionPolicyError(RuntimeError):
    pass


def _run_git(root: Path, arguments: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *arguments],
        cwd=root,
        check=check,
        capture_output=True,
        text=True,
        timeout=120,
    )


def _validate_relative_path(value: str) -> str:
    try:
        return normalize_candidate_path(value)
    except TrackPolicyError as exc:
        raise EvolutionPolicyError(str(exc)) from exc


def _proposal_track(paths: list[str]) -> MutationTrack:
    try:
        return classify_candidate_paths(paths)
    except TrackPolicyError as exc:
        raise EvolutionPolicyError(str(exc)) from exc


class EvolutionHarness:
    def __init__(self, config: Settings = settings) -> None:
        self.config = config
        self.repo = config.project_root
        self.state_dir = config.resolve_path(config.EVOLUTION_STATE_DIR)
        self.proposal_dir = self.state_dir / "proposals"
        self.evaluation_dir = self.state_dir / "evaluations"
        self.audit_path = self.state_dir / "audit.jsonl"
        self.experience_path = self.state_dir / "experience.jsonl"
        self.approval_dir = self.state_dir / "approvals"
        self.worktree_root = config.resolve_path(config.EVOLUTION_WORKTREE_DIR)

    def create_proposal(self, proposal: EvolutionProposal) -> EvolutionProposal:
        if not SAFE_ID.fullmatch(proposal.id):
            raise EvolutionPolicyError("proposal id 格式不合法")
        proposal.mutation_paths = [
            _validate_relative_path(path)
            for path in proposal.mutation_paths
        ]
        track = _proposal_track(proposal.mutation_paths)
        resolved = _run_git(
            self.repo,
            ["rev-parse", "--verify", f"{proposal.base_commit}^{{commit}}"],
        ).stdout.strip()
        proposal.base_commit = resolved
        self.proposal_dir.mkdir(parents=True, exist_ok=True)
        path = self.proposal_dir / f"{proposal.id}.json"
        if path.exists():
            raise EvolutionPolicyError("proposal 已存在")
        atomic_json(path, proposal.model_dump(mode="json"))
        self._audit(
            "proposal.created",
            proposal.id,
            {
                "provider": proposal.provider,
                "governance_track": track,
                "human_approval_required": human_approval_required(
                    track,
                    self.config.EVOLUTION_REQUIRE_HUMAN_APPROVAL,
                ),
            },
        )
        return proposal

    def create_from_continuous_candidate(
        self,
        candidate: ContinuousEvolutionCandidate,
        *,
        provider: str = "manual",
    ) -> EvolutionProposal:
        """Materialize a content-free online finding as an offline proposal.

        This creates only proposal metadata. It does not isolate, generate,
        freeze, evaluate, approve or promote a mutation.
        """
        if candidate.status != "ready_for_offline_evaluation":
            raise EvolutionPolicyError("只有待离线评测候选可以转为 proposal")
        base_commit = _run_git(self.repo, ["rev-parse", "HEAD"]).stdout.strip()
        proposal = EvolutionProposal(
            provider=provider,
            target_failure_cluster=(
                f"{candidate.kind}:{candidate.target}; "
                f"samples={candidate.sample_size}; "
                f"negative_rate={candidate.negative_rate:.3f}"
            ),
            mutation_paths=candidate.allowed_mutation_paths,
            expected_behavior_change=candidate.trigger,
            risk="线上信号仅表示相关性；错误归因或过拟合可能造成负优化",
            activation_condition=(
                "相同病例配对评测全切片非劣、高风险单病例不降分、"
                "医疗安全与引用门禁通过，并完成可信人工审批"
            ),
            base_commit=base_commit,
        )
        return self.create_proposal(proposal)

    def load_proposal(self, proposal_id: str) -> EvolutionProposal:
        if not SAFE_ID.fullmatch(proposal_id):
            raise EvolutionPolicyError("proposal id 格式不合法")
        path = self.proposal_dir / f"{proposal_id}.json"
        if not path.is_file():
            raise KeyError(proposal_id)
        return EvolutionProposal.model_validate_json(path.read_text("utf-8"))

    def _save_proposal(self, proposal: EvolutionProposal) -> None:
        atomic_json(
            self.proposal_dir / f"{proposal.id}.json",
            proposal.model_dump(mode="json"),
        )

    def isolate(self, proposal_id: str) -> Path:
        proposal = self.load_proposal(proposal_id)
        target = (self.worktree_root / proposal.id).resolve()
        root = self.worktree_root.resolve()
        if root not in target.parents:
            raise EvolutionPolicyError("worktree 路径越界")
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise EvolutionPolicyError("候选 worktree 已存在")
        branch = f"evolution/{proposal.id}"
        _run_git(
            self.repo,
            ["worktree", "add", "-b", branch, str(target), proposal.base_commit],
        )
        proposal.status = "isolated"
        self._save_proposal(proposal)
        self._audit("proposal.isolated", proposal.id, {"worktree": str(target)})
        return target

    def changed_paths(self, proposal_id: str) -> list[str]:
        proposal = self.load_proposal(proposal_id)
        declared_track = _proposal_track(proposal.mutation_paths)
        worktree = self.worktree_root / proposal.id
        if not worktree.is_dir():
            raise EvolutionPolicyError("候选 worktree 不存在")
        committed = _run_git(
            worktree,
            ["diff", "--name-only", f"{proposal.base_commit}...HEAD"],
        ).stdout.splitlines()
        status = _run_git(
            worktree,
            ["status", "--porcelain", "--untracked-files=all"],
        ).stdout.splitlines()
        pending = [line[3:] for line in status if len(line) > 3]
        paths = sorted({path.strip() for path in [*committed, *pending] if path.strip()})
        for path in paths:
            _validate_relative_path(path)
            if (worktree / path).is_symlink():
                raise EvolutionPolicyError(f"候选修改禁止使用符号链接：{path}")
            if not any(
                path == declared or path.startswith(declared.rstrip("/") + "/")
                for declared in proposal.mutation_paths
            ):
                raise EvolutionPolicyError(f"候选修改未声明路径：{path}")
        if paths and _proposal_track(paths) != declared_track:
            raise EvolutionPolicyError("候选实际修改跨越声明的治理轨道")
        return paths

    def freeze_candidate(self, proposal_id: str) -> str:
        """Commit the isolated candidate before any acceptance evaluation."""
        proposal = self.load_proposal(proposal_id)
        worktree = self.worktree_root / proposal.id
        changed = self.changed_paths(proposal_id)
        if not changed:
            raise EvolutionPolicyError("候选没有真实修改")
        pending = _run_git(worktree, ["status", "--porcelain"]).stdout.strip()
        if pending:
            _run_git(worktree, ["add", "--", *changed])
            environment = {
                **os.environ,
                "GIT_AUTHOR_NAME": "OphAgent Evolution Candidate",
                "GIT_AUTHOR_EMAIL": "evolution@localhost",
                "GIT_COMMITTER_NAME": "OphAgent Evolution Candidate",
                "GIT_COMMITTER_EMAIL": "evolution@localhost",
            }
            subprocess.run(
                ["git", "commit", "-m", f"evolve: freeze {proposal.id}"],
                cwd=worktree,
                check=True,
                capture_output=True,
                text=True,
                timeout=120,
                env=environment,
            )
        commit = _run_git(worktree, ["rev-parse", "HEAD"]).stdout.strip()
        self._audit("proposal.frozen", proposal.id, {"commit": commit})
        return commit

    def record_evaluation(self, result: EvaluationRunResult) -> EvaluationRunResult:
        proposal = self.load_proposal(result.proposal_id)
        _run_git(
            self.repo,
            ["rev-parse", "--verify", f"{result.commit}^{{commit}}"],
        )
        if result.variant == "baseline" and result.commit != proposal.base_commit:
            raise EvolutionPolicyError("baseline 评测未绑定 proposal.base_commit")
        if result.variant == "candidate":
            worktree = self.worktree_root / proposal.id
            if not worktree.is_dir():
                raise EvolutionPolicyError("candidate worktree 不存在")
            head = _run_git(worktree, ["rev-parse", "HEAD"]).stdout.strip()
            if result.commit != head:
                raise EvolutionPolicyError("candidate 评测未绑定冻结后的 HEAD")
            if _run_git(worktree, ["status", "--porcelain"]).stdout.strip():
                raise EvolutionPolicyError("candidate 评测前存在未冻结修改")
        if not result.cases:
            raise EvolutionPolicyError("评测结果不能为空")
        if result.phase in {"acceptance_validation", "sealed_test"}:
            self._verify_attestation(result)
        case_ids = [item.case_id for item in result.cases]
        if len(case_ids) != len(set(case_ids)):
            raise EvolutionPolicyError("评测 case_id 重复")
        directory = self.evaluation_dir / result.proposal_id
        directory.mkdir(parents=True, exist_ok=True)
        atomic_json(
            directory / f"{result.phase}.{result.variant}.json",
            result.model_dump(mode="json"),
        )
        proposal.status = "evaluated"
        self._save_proposal(proposal)
        self._audit(
            "evaluation.recorded",
            proposal.id,
            {"phase": result.phase, "case_count": len(result.cases)},
        )
        return result

    def load_evaluation(
        self,
        proposal_id: str,
        phase: str,
        variant: str = "candidate",
    ) -> EvaluationRunResult:
        if phase not in PHASE_ORDER:
            raise EvolutionPolicyError("未知评测阶段")
        if variant not in {"baseline", "candidate"}:
            raise EvolutionPolicyError("未知评测 variant")
        path = self.evaluation_dir / proposal_id / f"{phase}.{variant}.json"
        if not path.is_file():
            raise KeyError(f"{proposal_id}:{phase}")
        return EvaluationRunResult.model_validate_json(path.read_text("utf-8"))

    def _gate_secret(self) -> str:
        direct = self.config.EVOLUTION_GATE_SECRET.get_secret_value()
        if direct:
            return direct
        configured = self.config.EVOLUTION_GATE_SECRET_FILE.strip()
        if not configured:
            raise EvolutionPolicyError("EVOLUTION_GATE_SECRET 或密钥文件未配置")
        path = self.config.resolve_path(configured).resolve()
        try:
            secret = path.read_text("utf-8").strip()
        except OSError as exc:
            raise EvolutionPolicyError("演化门禁密钥文件不可读") from exc
        if len(secret) < 32:
            raise EvolutionPolicyError("演化门禁密钥长度不足")
        return secret

    def load_sealed_suite(self) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Load and validate the controller-owned, candidate-invisible suite."""
        configured = self.config.EVOLUTION_SEALED_TEST_DIR.strip()
        if not configured:
            raise EvolutionPolicyError("sealed test 目录未配置，禁止晋升")
        sealed_dir = self.config.resolve_path(configured).resolve()
        repo = self.repo.resolve()
        worktree_root = self.worktree_root.resolve()
        if (
            sealed_dir == repo
            or repo in sealed_dir.parents
            or sealed_dir == worktree_root
            or worktree_root in sealed_dir.parents
        ):
            raise EvolutionPolicyError("sealed test 必须存放在仓库与候选 worktree 之外")
        manifest_path = sealed_dir / "manifest.json"
        if not manifest_path.is_file():
            raise EvolutionPolicyError("sealed test manifest.json 不存在")
        try:
            manifest = json.loads(manifest_path.read_text("utf-8"))
        except (OSError, TypeError, ValueError) as exc:
            raise EvolutionPolicyError("sealed test manifest.json 无效") from exc
        if not isinstance(manifest, dict) or manifest.get("status") != "sealed":
            raise EvolutionPolicyError("sealed test manifest 状态无效")
        if (
            manifest.get("component_contract_set") != "ophagent-harness-core"
            or manifest.get("component_contract_schema_version") != 1
        ):
            raise EvolutionPolicyError("sealed test 未绑定当前 Harness 组件核心契约")
        source_protocol = manifest.get("source_protocol")
        if (
            not isinstance(source_protocol, Mapping)
            or source_protocol.get("historical_outputs_reused") is not False
        ):
            raise EvolutionPolicyError("sealed test 必须声明未复用历史评测输出")
        case_file = manifest.get("case_file")
        if not isinstance(case_file, str):
            raise EvolutionPolicyError("sealed test case_file 未配置")
        relative_case_file = Path(case_file)
        if (
            relative_case_file.is_absolute()
            or ".." in relative_case_file.parts
            or not relative_case_file.parts
        ):
            raise EvolutionPolicyError("sealed test case_file 路径不安全")
        case_path = (sealed_dir / relative_case_file).resolve()
        if sealed_dir not in case_path.parents or not case_path.is_file():
            raise EvolutionPolicyError("sealed test 病例文件不存在或越界")
        cases: list[dict[str, Any]] = []
        try:
            for line_number, line in enumerate(
                case_path.read_text("utf-8").splitlines(),
                start=1,
            ):
                if not line.strip():
                    continue
                item = json.loads(line)
                if not isinstance(item, dict):
                    raise ValueError(f"line {line_number}")
                cases.append(item)
        except (OSError, TypeError, ValueError) as exc:
            raise EvolutionPolicyError("sealed test 病例文件无效") from exc
        case_ids = [str(item.get("case_id", "")).strip() for item in cases]
        if not case_ids or any(not case_id for case_id in case_ids):
            raise EvolutionPolicyError("sealed test 存在空 case_id")
        if len(case_ids) != len(set(case_ids)):
            raise EvolutionPolicyError("sealed test case_id 重复")
        if manifest.get("case_count") != len(cases):
            raise EvolutionPolicyError("sealed test case_count 与病例文件不一致")
        slice_counts: dict[str, int] = defaultdict(int)
        for item in cases:
            slice_name = str(item.get("slice", "")).strip()
            if slice_name not in {"routine", "complex", "high_risk"}:
                raise EvolutionPolicyError("sealed test 存在未知切片")
            slice_counts[slice_name] += 1
        declared_slices = manifest.get("slices")
        if not isinstance(declared_slices, Mapping) or any(
            declared_slices.get(name) != slice_counts[name]
            for name in ("routine", "complex", "high_risk")
        ):
            raise EvolutionPolicyError("sealed test 切片计数与 manifest 不一致")
        if any(
            slice_counts[name] < self.config.EVOLUTION_MIN_CASES_PER_SLICE
            for name in ("routine", "complex", "high_risk")
        ):
            raise EvolutionPolicyError("sealed test 切片病例数不足")
        declared_metrics = manifest.get("required_metrics")
        if not isinstance(declared_metrics, list) or not all(
            isinstance(metric, str) for metric in declared_metrics
        ):
            raise EvolutionPolicyError("sealed test required_metrics 无效")
        required_metrics = set(declared_metrics)
        if not {
            "task_score",
            "safety_passed",
            "citation_passed",
            "component_contract_passed",
            "critical_errors",
            "tokens",
            "latency_ms",
        }.issubset(required_metrics):
            raise EvolutionPolicyError("sealed test 缺少强制评测指标")
        policy = manifest.get("policy")
        required_policy = {
            "candidate_access": "forbidden",
            "one_shot_release_evaluation": True,
            "paired_baseline_candidate": True,
            "high_risk_case_regression_allowed": False,
            "slice_regression_allowed": False,
        }
        if not isinstance(policy, Mapping) or any(
            policy.get(key) != expected
            for key, expected in required_policy.items()
        ):
            raise EvolutionPolicyError("sealed test 防泄漏或非劣策略无效")
        return manifest, cases

    def attest_evaluation(self, result: EvaluationRunResult) -> EvaluationRunResult:
        """Attest in the trusted controller, never inside a candidate process."""
        secret = self._gate_secret()
        payload = result.model_copy(update={"attestation": None})
        signature = hmac.new(
            secret.encode("utf-8"),
            payload.model_dump_json().encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return result.model_copy(update={"attestation": signature})

    def _verify_attestation(self, result: EvaluationRunResult) -> None:
        expected = self.attest_evaluation(
            result.model_copy(update={"attestation": None}),
        ).attestation
        if not result.attestation or not hmac.compare_digest(
            result.attestation,
            expected or "",
        ):
            raise EvolutionPolicyError("评测 attestation 无效")

    def decide(
        self,
        baseline: EvaluationRunResult,
        candidate: EvaluationRunResult,
    ) -> PromotionDecision:
        baseline_by_id = {item.case_id: item for item in baseline.cases}
        candidate_by_id = {item.case_id: item for item in candidate.cases}
        if baseline_by_id.keys() != candidate_by_id.keys():
            raise EvolutionPolicyError("baseline/candidate 必须使用完全相同的配对病例")
        differences = [
            candidate_by_id[case_id].score - baseline_by_id[case_id].score
            for case_id in sorted(baseline_by_id)
        ]
        mean = fmean(differences)
        standard_error = (
            pstdev(differences) / math.sqrt(len(differences))
            if len(differences) > 1
            else 0.0
        )
        interval = (mean - 1.96 * standard_error, mean + 1.96 * standard_error)
        baseline_tokens = sum(item.tokens for item in baseline.cases)
        candidate_tokens = sum(item.tokens for item in candidate.cases)
        baseline_latency = sum(item.latency_ms for item in baseline.cases)
        candidate_latency = sum(item.latency_ms for item in candidate.cases)
        token_ratio = candidate_tokens / max(baseline_tokens, 1)
        latency_ratio = candidate_latency / max(baseline_latency, 1)
        by_slice: dict[str, list[float]] = defaultdict(list)
        reasons: list[str] = []
        for case_id in sorted(baseline_by_id):
            previous = baseline_by_id[case_id]
            current = candidate_by_id[case_id]
            by_slice[current.slice].append(
                current.score - previous.score,
            )
            if previous.passed and not current.passed:
                reasons.append(f"已通过病例发生回归：{case_id}")
            if not current.safety_passed:
                reasons.append(f"医疗安全门禁未通过：{case_id}")
            if not current.citation_passed:
                reasons.append(f"引用门禁未通过：{case_id}")
            if not current.component_contract_passed:
                reasons.append(f"组件核心契约门禁未通过：{case_id}")
            if current.critical_errors:
                reasons.append(f"存在关键错误：{case_id}")
            if current.slice == "high_risk" and not current.passed:
                reasons.append(f"高风险病例未通过：{case_id}")
            if current.slice == "high_risk" and current.score < previous.score:
                reasons.append(f"高风险病例得分下降：{case_id}")
        slice_differences = {
            slice_name: fmean(values)
            for slice_name, values in by_slice.items()
        }
        for required_slice in ("routine", "complex", "high_risk"):
            if (
                len(by_slice.get(required_slice, []))
                < self.config.EVOLUTION_MIN_CASES_PER_SLICE
            ):
                reasons.append(f"{required_slice} 切片病例数不足")
        if mean < self.config.EVOLUTION_MIN_MEAN_IMPROVEMENT:
            reasons.append("配对平均提升未达到门槛")
        if interval[0] < 0:
            reasons.append("95% 置信区间下界小于 0")
        for slice_name, difference in slice_differences.items():
            if difference < -self.config.EVOLUTION_MAX_SLICE_REGRESSION:
                reasons.append(f"{slice_name} 切片发生回归")
        if token_ratio > self.config.EVOLUTION_MAX_TOKEN_RATIO:
            reasons.append("token 成本超过门槛")
        if latency_ratio > self.config.EVOLUTION_MAX_LATENCY_RATIO:
            reasons.append("延迟超过门槛")
        if not baseline.command_succeeded or not candidate.command_succeeded:
            reasons.append("评测命令未成功完成")
        return PromotionDecision(
            accepted=not reasons,
            mean_difference=mean,
            confidence_interval_95=interval,
            token_ratio=token_ratio,
            latency_ratio=latency_ratio,
            slice_differences=slice_differences,
            reasons=reasons,
        )

    def approve(self, proposal_id: str, reviewer: str) -> dict[str, Any]:
        """Bind explicit trusted human approval to the sealed candidate."""
        reviewer = reviewer.strip()
        if not reviewer or len(reviewer) > 120:
            raise EvolutionPolicyError("审批人标识不合法")
        baseline = self.load_evaluation(proposal_id, "sealed_test", "baseline")
        candidate = self.load_evaluation(proposal_id, "sealed_test", "candidate")
        self._verify_attestation(baseline)
        self._verify_attestation(candidate)
        decision = self.decide(baseline, candidate)
        if not decision.accepted:
            raise EvolutionPolicyError("未通过非劣与收益门禁的候选不能审批")
        track = _proposal_track(self.load_proposal(proposal_id).mutation_paths)
        payload = {
            "proposal_id": proposal_id,
            "candidate_commit": candidate.commit,
            "governance_track": track,
            "reviewer": reviewer,
            "approved_at": utc_now().isoformat(),
        }
        secret = self._gate_secret()
        signature = hmac.new(
            secret.encode("utf-8"),
            json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        record = {**payload, "signature": signature}
        self.approval_dir.mkdir(parents=True, exist_ok=True)
        atomic_json(self.approval_dir / f"{proposal_id}.json", record)
        self._audit(
            "proposal.approved",
            proposal_id,
            {"candidate_commit": candidate.commit, "reviewer": reviewer},
        )
        return record

    def _verify_approval(
        self,
        proposal_id: str,
        candidate_commit: str,
        track: MutationTrack,
    ) -> None:
        path = self.approval_dir / f"{proposal_id}.json"
        if not path.is_file():
            raise EvolutionPolicyError("候选尚未获得可信人工审批")
        try:
            record = json.loads(path.read_text("utf-8"))
        except (OSError, TypeError, ValueError) as exc:
            raise EvolutionPolicyError("候选审批记录损坏") from exc
        signature = str(record.pop("signature", ""))
        secret = self._gate_secret()
        expected = hmac.new(
            secret.encode("utf-8"),
            json.dumps(record, ensure_ascii=False, sort_keys=True).encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        if (
            not signature
            or not hmac.compare_digest(signature, expected)
            or record.get("proposal_id") != proposal_id
            or record.get("candidate_commit") != candidate_commit
            or record.get("governance_track") != track
        ):
            raise EvolutionPolicyError("候选审批记录无效或未绑定当前 commit")

    def promote(
        self,
        proposal_id: str,
    ) -> PromotionDecision:
        proposal = self.load_proposal(proposal_id)
        track = _proposal_track(proposal.mutation_paths)
        _, sealed_cases = self.load_sealed_suite()
        baseline = self.load_evaluation(proposal_id, "sealed_test", "baseline")
        candidate = self.load_evaluation(proposal_id, "sealed_test", "candidate")
        sealed_case_ids = {str(item["case_id"]) for item in sealed_cases}
        if (
            {item.case_id for item in baseline.cases} != sealed_case_ids
            or {item.case_id for item in candidate.cases} != sealed_case_ids
        ):
            raise EvolutionPolicyError("sealed 评测结果未覆盖 manifest 中的完整病例集合")
        self._verify_attestation(baseline)
        self._verify_attestation(candidate)
        changed = self.changed_paths(proposal_id)
        if not changed:
            raise EvolutionPolicyError("候选没有真实激活的代码或配置修改")
        decision = self.decide(baseline, candidate)
        proposal.status = "accepted" if decision.accepted else "rejected"
        self._save_proposal(proposal)
        if not decision.accepted:
            self._audit(
                "proposal.rejected",
                proposal.id,
                {"reasons": decision.reasons},
            )
            return decision
        if human_approval_required(
            track,
            self.config.EVOLUTION_REQUIRE_HUMAN_APPROVAL,
        ):
            self._verify_approval(proposal.id, candidate.commit, track)
        worktree = self.worktree_root / proposal.id
        pending = _run_git(worktree, ["status", "--porcelain"]).stdout.strip()
        if pending:
            raise EvolutionPolicyError("晋升前候选出现未评测修改")
        commit = _run_git(worktree, ["rev-parse", "HEAD"]).stdout.strip()
        if candidate.commit != commit:
            raise EvolutionPolicyError("sealed candidate commit 与 worktree HEAD 不一致")
        experience = ExperienceRecord(
            proposal_id=proposal.id,
            failure_pattern=proposal.target_failure_cluster,
            strategy=proposal.expected_behavior_change,
            release_commit=commit,
            evaluation=decision.model_dump(mode="json"),
        )
        self._validate_experience(experience)
        release_ref = f"refs/ophagent/releases/{proposal.id}"
        active_ref = "refs/ophagent/active"
        previous = _run_git(
            self.repo,
            ["rev-parse", "--verify", active_ref],
            check=False,
        ).stdout.strip()
        expected = previous or "0" * 40
        transaction = (
            "start\n"
            f"update {release_ref} {commit} {'0' * 40}\n"
            f"update {active_ref} {commit} {expected}\n"
            "prepare\n"
            "commit\n"
        )
        subprocess.run(
            ["git", "update-ref", "--stdin"],
            cwd=self.repo,
            input=transaction,
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
        proposal.status = "promoted"
        self._save_proposal(proposal)
        self._record_experience(experience)
        self._audit(
            "proposal.promoted",
            proposal.id,
            {
                "commit": commit,
                "previous": previous or None,
                "governance_track": track,
            },
        )
        return decision

    def rollback(self, release_commit: str) -> str:
        allowed = set(
            _run_git(
                self.repo,
                [
                    "for-each-ref",
                    "--format=%(objectname)",
                    "refs/ophagent/releases/",
                ],
            ).stdout.splitlines(),
        )
        if release_commit not in allowed:
            raise EvolutionPolicyError("只能回滚到已冻结的 release")
        active_ref = "refs/ophagent/active"
        previous = _run_git(
            self.repo,
            ["rev-parse", "--verify", active_ref],
            check=False,
        ).stdout.strip()
        _run_git(
            self.repo,
            ["update-ref", active_ref, release_commit, previous or "0" * 40],
        )
        self._audit(
            "release.rollback",
            "release",
            {"commit": release_commit, "previous": previous or None},
        )
        return release_commit

    def _record_experience(self, record: ExperienceRecord) -> None:
        self._validate_experience(record)
        self.experience_path.parent.mkdir(parents=True, exist_ok=True)
        with self.experience_path.open("a", encoding="utf-8") as handle:
            handle.write(record.model_dump_json() + "\n")

    @staticmethod
    def _validate_experience(record: ExperienceRecord) -> None:
        combined = f"{record.failure_pattern}\n{record.strategy}"
        sensitive_patterns = (
            r"\b1\d{10}\b",
            r"\b\d{17}[\dXx]\b",
            r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}",
            r"(?:患者姓名|身份证号|联系电话)\s*[:：]",
        )
        if any(re.search(pattern, combined) for pattern in sensitive_patterns):
            raise EvolutionPolicyError("经验 memory 检测到患者标识信息")

    def _audit(self, event: str, proposal_id: str, data: dict[str, Any]) -> None:
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "event": event,
            "proposal_id": proposal_id,
            "timestamp": utc_now().isoformat(),
            "data": data,
        }
        with self.audit_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

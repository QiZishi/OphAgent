"""AgentScope-backed agent construction and invocation."""

from __future__ import annotations

import hashlib
import inspect
import json
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import frontmatter
import httpx
from agentscope.agent import ReActAgent
from agentscope.formatter import OpenAIChatFormatter
from agentscope.memory import InMemoryMemory
from agentscope.message import Msg
from agentscope.model import OpenAIChatModel
from agentscope.plan import PlanNotebook
from agentscope.tool import Toolkit, ToolResponse

from app.core.config import Settings, settings
from app.services.skill_policy import (
    SAFETY_CRITICAL_SKILLS,
    requires_offline_skill_review,
)
from app.tools.capabilities import CapabilityClients, SearchRequest

AGENT_PROMPTS = {
    "DirectAnswerAgent": (
        "你是 OphAgent 的直接回答组件。对简单问题给出简短、准确的回答；"
        "不调用工具，不编造来源，不输出报告模板或隐藏推理。"
    ),
    "AnswerSynthesizer": (
        "你是 OphAgent 的回答整合组件。先解决用户的具体问题，再组织最少但充分的依据。"
        "只依据给定上下文，区分事实、推测和未知；不重复免责声明，不输出隐藏推理。"
    ),
    "SupervisorAgent": (
        "你是 OphAgent-Pro 的主编排智能体。识别用户意图、输入充分性与风险，"
        "只输出可公开的简短计划摘要，不输出隐藏推理过程。不得编造医疗事实。"
    ),
    "ClinicalReasoningAgent": (
        "你是结构化临床推理智能体。ClinicalState 是唯一事实源。"
        "只抽取用户明确提供的事实与缺失信息；不得提前形成诊断，不得把推测写成事实。"
    ),
    "DifferentialAssessmentAgent": (
        "你是眼科鉴别评估智能体。综合结构化病史、可见影像观察和可追踪证据，"
        "输出定性候选鉴别及其支持、反对和缺失信息。使用 low/medium/high 表示"
        "当前资料支持程度，不得输出伪造的疾病概率，不得宣称确诊或输出隐藏推理。"
    ),
    "EvidenceAgent": (
        "你是证据智能体。优先本地指南，必要时联网；每个陈述绑定 evidence id。"
        "证据不足时明确拒绝以模型常识补充来源。"
    ),
    "ReportAgent": (
        "你是眼科报告智能体。只依据提供的 ClinicalState、影像观察和证据生成中文报告。"
        "逐条使用 [ev_xxx] 引用，区分事实、推测与未知，给出不确定性和就医升级建议。"
        "不得输出隐藏推理过程。"
    ),
    "CriticAgent": (
        "你是高风险输出审查智能体。检查事实越界、引用缺失、药物/过敏冲突、红旗遗漏"
        "和过度确定表述。只输出问题清单和可执行修订要求。"
    ),
    "OphthalmologySpecialistAgent": (
        "你是眼科专科复核智能体。只依据提供的结构化病史、检查观察和可追踪证据，"
        "从指定亚专科角度给出独立、简洁的公开复核意见。明确支持项、反对项、"
        "危险信号、证据缺口和下一步检查；不得宣称确诊，不得输出隐藏推理。"
    ),
}

ROLE_SKILLS = {
    "SupervisorAgent": ["red_flag_triage"],
    "ClinicalReasoningAgent": ["ophthalmic_interview"],
    "DifferentialAssessmentAgent": ["ophthalmic_interview", "evidence_synthesis"],
    "EvidenceAgent": ["guideline_retrieval"],
    "ReportAgent": ["ophthalmic_report"],
    "CriticAgent": ["red_flag_triage"],
    "OphthalmologySpecialistAgent": ["red_flag_triage", "guideline_retrieval"],
}

ROLE_CAPABILITIES = {
    "DirectAnswerAgent": {"answer"},
    "AnswerSynthesizer": {"answer", "citation"},
    "SupervisorAgent": {"planning", "routing", "triage"},
    "ClinicalReasoningAgent": {"clinical_reasoning", "interview", "triage"},
    "DifferentialAssessmentAgent": {"clinical_reasoning", "assessment", "evidence"},
    "EvidenceAgent": {"retrieval", "evidence", "knowledge"},
    "ReportAgent": {"report", "citation"},
    "CriticAgent": {"critic", "safety", "triage"},
    "OphthalmologySpecialistAgent": {
        "clinical_reasoning",
        "specialist_review",
        "retrieval",
        "triage",
    },
}
@dataclass(slots=True)
class AgentReply:
    text: str
    model_calls: int = 1
    prompt_tokens: int = 0
    completion_tokens: int = 0
    usage_estimated: bool = False


class AgentRunner(Protocol):
    async def ask(self, role: str, prompt: str) -> AgentReply: ...


class CountingOpenAIChatModel(OpenAIChatModel):
    """OpenAI-compatible model that exposes actual call and usage totals."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.call_count = 0
        self.prompt_token_count = 0
        self.completion_token_count = 0

    async def __call__(self, *args, **kwargs):
        response = await super().__call__(*args, **kwargs)
        self.call_count += 1
        usage = getattr(response, "usage", None)
        if usage is not None:
            self.prompt_token_count += int(getattr(usage, "input_tokens", 0) or 0)
            self.completion_token_count += int(getattr(usage, "output_tokens", 0) or 0)
        return response


class AgentScopeRunner:
    """Creates isolated AgentScope agents per run/role.

    Isolation prevents patient context from leaking between runs. Long-term
    memory is handled separately through confirmed MemoryRecords.
    """

    def __init__(self, clients: CapabilityClients, config: Settings = settings) -> None:
        if config.AGENTSCOPE_DISABLE_CONSOLE_OUTPUT:
            os.environ["AGENTSCOPE_DISABLE_CONSOLE_OUTPUT"] = "true"
        self.clients = clients
        self.config = config
        self._agents: dict[str, ReActAgent] = {}
        self.active_plugin_ids: set[str] = set()
        self.requested_skill_ids: set[str] = set()
        self.user_id: int | None = None
        self.used_skill_ids: set[str] = set()
        self._skill_utility_provider: Callable[[str, str], float] | None = None

    def set_run_context(
        self,
        plugin_id: str | list[str],
        requested_skill_ids: list[str] | None = None,
        user_id: int | None = None,
    ) -> None:
        self.active_plugin_ids = {plugin_id} if isinstance(plugin_id, str) else set(plugin_id)
        self.requested_skill_ids = set(requested_skill_ids or [])
        self.user_id = user_id

    def set_skill_utility_provider(
        self,
        provider: Callable[[str, str], float] | None,
    ) -> None:
        """Attach the privacy-minimized online skill utility signal."""
        self._skill_utility_provider = provider

    def _skill_utility(self, skill_id: str, risk_level: str) -> float:
        if self._skill_utility_provider is None:
            return 1.0
        try:
            value = float(self._skill_utility_provider(skill_id, risk_level))
        except (TypeError, ValueError):
            return 1.0
        bound = self.config.EVOLUTION_SKILL_RANKING_BOUND
        return min(1.0 + bound, max(1.0 - bound, value))

    def _model(self, role: str) -> CountingOpenAIChatModel:
        key = self.config.main_model_key.get_secret_value()
        return CountingOpenAIChatModel(
            model_name=self.config.main_model_name,
            api_key=key,
            stream=False,
            reasoning_effort=self.config.AGENT_REASONING_EFFORT,
            client_kwargs={
                "base_url": self.config.main_model_url,
                "timeout": self.config.REQUEST_TIMEOUT_SECONDS,
                "max_retries": self.config.MAX_RETRIES,
            },
            generate_kwargs={
                "temperature": self.config.TEMPERATURE,
                "max_tokens": self._max_output_tokens(role),
            },
        )

    def _toolkit(self, role: str) -> Toolkit:
        base_role = self._base_role(role)
        toolkit = Toolkit()

        async def medical_retrieval(query: str, top_k: int = 6) -> ToolResponse:
            """检索本地眼科指南，返回带来源与定位的证据。"""
            result = await self.clients.retrieve_medical_evidence(
                query,
                top_k,
                user_id=self.user_id,
            )
            return ToolResponse(content=[{"type": "text", "text": result.model_dump_json()}])

        async def web_search(query: str, max_results: int = 5) -> ToolResponse:
            """在本地证据不足或需要最新信息时检索外部资料。"""
            result = await self.clients.search_web(SearchRequest(query=query, max_results=max_results))
            return ToolResponse(content=[{"type": "text", "text": result.model_dump_json()}])

        if base_role in {
            "SupervisorAgent",
            "EvidenceAgent",
            "OphthalmologySpecialistAgent",
        }:
            toolkit.register_tool_function(medical_retrieval)
            toolkit.register_tool_function(web_search)

        for path in self._enabled_skill_paths(base_role):
            toolkit.register_agent_skill(str(path))
            try:
                post = frontmatter.load(path / "SKILL.md")
                skill_id = str(post.get("name") or path.name)
            except (OSError, ValueError, TypeError):
                skill_id = path.name
            self.used_skill_ids.add(skill_id)
        return toolkit

    def _enabled_skill_paths(self, role: str) -> list[Path]:
        skill_root = self.config.resolve_path(self.config.SKILL_ROOT)
        state_path = self.config.resolve_path(self.config.SKILL_STATE_PATH)
        states: dict[str, dict] = {}
        if state_path.is_file():
            try:
                raw = json.loads(state_path.read_text("utf-8"))
                states = {
                    str(key): ({"status": value} if isinstance(value, str) else dict(value))
                    for key, value in raw.items()
                }
            except (OSError, ValueError, TypeError):
                states = {}
        selected: list[tuple[int, float, str, Path]] = []
        for skill_name in ROLE_SKILLS.get(role, []):
            path = skill_root / skill_name
            if path.is_dir() and states.get(skill_name, {}).get("status", "enabled") == "enabled":
                try:
                    post = frontmatter.load(path / "SKILL.md")
                    risk_level = str(post.get("risk_level") or "routine")
                except (OSError, ValueError, TypeError):
                    risk_level = "routine"
                priority = 3 if skill_name in SAFETY_CRITICAL_SKILLS else 2
                selected.append(
                    (
                        priority,
                        self._skill_utility(skill_name, risk_level),
                        skill_name,
                        path,
                    ),
                )
        for skill_md in sorted((skill_root / ".candidates").glob("**/SKILL.md")):
            try:
                post = frontmatter.load(skill_md)
            except (OSError, ValueError, TypeError):
                continue
            skill_id = str(post.get("name") or "")
            risk_level = str(post.get("risk_level") or "routine")
            dependencies = list(post.get("dependencies") or [])
            if states.get(skill_id, {}).get("status") != "enabled":
                continue
            if self.requested_skill_ids and skill_id not in self.requested_skill_ids:
                continue
            plugins = set(post.get("plugins") or [])
            capabilities = set(post.get("capabilities") or [])
            if self.active_plugin_ids and plugins and not self.active_plugin_ids.intersection(plugins):
                continue
            if capabilities and not capabilities.intersection(ROLE_CAPABILITIES.get(role, set())):
                continue
            evaluation_path = (
                self.config.resolve_path(self.config.SKILL_EVALUATION_DIR)
                / f"{skill_id}.json"
            )
            try:
                evaluation = json.loads(evaluation_path.read_text("utf-8"))
                checksum = hashlib.sha256(skill_md.read_bytes()).hexdigest()
            except (OSError, ValueError, TypeError):
                continue
            if evaluation.get("passed") and evaluation.get("checksum") == checksum:
                offline_review_required = requires_offline_skill_review(
                    risk_level=risk_level,
                    dependencies=dependencies,
                    capabilities=list(capabilities),
                )
                if offline_review_required:
                    approval = evaluation.get("offline_approval")
                    if (
                        not isinstance(approval, dict)
                        or approval.get("checksum") != checksum
                        or not approval.get("reviewer")
                    ):
                        continue
                utility = self._skill_utility(
                    skill_id,
                    "high" if offline_review_required else risk_level,
                )
                online_adaptation_allowed = not offline_review_required
                explicitly_requested = skill_id in self.requested_skill_ids
                if (
                    online_adaptation_allowed
                    and not explicitly_requested
                    and utility < self.config.EVOLUTION_SKILL_AUTO_SUPPRESS_THRESHOLD
                ):
                    continue
                selected.append(
                    (
                        4 if explicitly_requested else 1,
                        utility,
                        skill_id,
                        skill_md.parent,
                    ),
                )
        selected.sort(
            key=lambda item: (item[0], item[1], item[2]),
            reverse=True,
        )
        return [item[3] for item in selected]

    def _agent(self, role: str) -> ReActAgent:
        base_role = self._base_role(role)
        if role not in self._agents:
            toolkit = self._toolkit(role)
            skill_prompt = toolkit.get_agent_skill_prompt() or ""
            self._agents[role] = ReActAgent(
                name=role.replace(":", "_"),
                sys_prompt=AGENT_PROMPTS[base_role] + "\n" + skill_prompt,
                model=self._model(base_role),
                formatter=OpenAIChatFormatter(),
                toolkit=toolkit,
                memory=InMemoryMemory(),
                plan_notebook=(
                    PlanNotebook(max_subtasks=12)
                    if base_role == "SupervisorAgent"
                    else None
                ),
                parallel_tool_calls=True,
                max_iters=max(2, min(self.config.AGENT_MAX_ITERS, 8)),
            )
        return self._agents[role]

    @staticmethod
    def _base_role(role: str) -> str:
        base_role = role.partition(":")[0]
        if base_role not in AGENT_PROMPTS:
            raise ValueError(f"未知智能体角色：{role}")
        return base_role

    def _max_output_tokens(self, role: str) -> int:
        base_role = self._base_role(role)
        role_limits = {
            "DirectAnswerAgent": 700,
            "SupervisorAgent": 256,
            "OphthalmologySpecialistAgent": 900,
            "CriticAgent": 900,
            "ClinicalReasoningAgent": 1_600,
            "DifferentialAssessmentAgent": 1_600,
            "EvidenceAgent": 1_500,
            "AnswerSynthesizer": 1_800,
            "ReportAgent": 2_400,
        }
        return min(
            role_limits.get(base_role, 2_000),
            self.config.MODEL_MAX_OUTPUT_TOKENS,
        )

    async def ask(self, role: str, prompt: str) -> AgentReply:
        if not self.config.main_model_name or not self.config.main_model_url:
            raise RuntimeError("主模型未配置")
        agent = self._agent(role)
        # Conversation context is packed explicitly by the harness. Reusing
        # AgentScope's implicit per-agent chat memory here would duplicate old
        # prompts on draft/review/final calls and make token use unpredictable.
        cleared = agent.memory.clear()
        if inspect.isawaitable(cleared):
            await cleared
        model = agent.model
        before_calls = model.call_count
        before_prompt = model.prompt_token_count
        before_completion = model.completion_token_count
        try:
            response = await agent(
                Msg(name="user", content=prompt, role="user"),
            )
            self.clients.health["main_model"] = "ready"
        except Exception:
            self.clients.health["main_model"] = "unavailable"
            raise
        prompt_tokens = model.prompt_token_count - before_prompt
        completion_tokens = model.completion_token_count - before_completion
        model_calls = model.call_count - before_calls
        text = response.get_text_content() or ""
        estimated = prompt_tokens == 0 and completion_tokens == 0
        if estimated:
            # Conservative fallback for OpenAI-compatible providers that do
            # not propagate usage through AgentScope Msg metadata.
            prompt_tokens = max(1, len(prompt) // 3)
            completion_tokens = max(1, len(text) // 3)
        return AgentReply(
            text=text,
            model_calls=max(model_calls, 1),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            usage_estimated=estimated,
        )

    async def ask_stream(
        self,
        role: str,
        prompt: str,
        on_delta: Callable[[str], Awaitable[None]],
    ) -> AgentReply:
        """Stream terminal prose from an OpenAI-compatible provider.

        Structured clinical extraction continues through AgentScope; only
        user-visible prose uses this transport so partial text reaches SSE
        before the provider finishes.
        """
        if not self.config.main_model_name or not self.config.main_model_url:
            raise RuntimeError("主模型未配置")
        endpoint = self.config.main_model_url.rstrip("/")
        if not endpoint.endswith("/chat/completions"):
            endpoint += "/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.config.main_model_key.get_secret_value()}",
            "Content-Type": "application/json",
        }
        body: dict[str, Any] = {
            "model": self.config.main_model_name,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        AGENT_PROMPTS[self._base_role(role)]
                        + "\n"
                        + (self._toolkit(role).get_agent_skill_prompt() or "")
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": self.config.TEMPERATURE,
            "max_tokens": self._max_output_tokens(role),
            "reasoning_effort": self.config.AGENT_REASONING_EFFORT,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        chunks: list[str] = []
        prompt_tokens = 0
        completion_tokens = 0
        try:
            async with httpx.AsyncClient(
                timeout=self.config.REQUEST_TIMEOUT_SECONDS,
                follow_redirects=True,
            ) as client:
                async with client.stream("POST", endpoint, headers=headers, json=body) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        raw = line.removeprefix("data:").strip()
                        if not raw or raw == "[DONE]":
                            continue
                        payload = json.loads(raw)
                        usage = payload.get("usage") or {}
                        prompt_tokens = int(
                            usage.get("prompt_tokens")
                            or usage.get("input_tokens")
                            or prompt_tokens
                        )
                        completion_tokens = int(
                            usage.get("completion_tokens")
                            or usage.get("output_tokens")
                            or completion_tokens
                        )
                        choices = payload.get("choices") or []
                        if not choices:
                            continue
                        delta = choices[0].get("delta") or {}
                        text = delta.get("content")
                        if isinstance(text, str) and text:
                            chunks.append(text)
                            await on_delta(text)
        except Exception:
            self.clients.health["main_model"] = "unavailable"
            raise
        answer = "".join(chunks)
        estimated = prompt_tokens == 0 and completion_tokens == 0
        if estimated:
            prompt_tokens = max(1, len(prompt) // 3)
            completion_tokens = max(1, len(answer) // 3)
        self.clients.health["main_model"] = "ready"
        return AgentReply(
            text=answer,
            model_calls=1,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            usage_estimated=estimated,
        )


def parse_json_object(text: str) -> dict:
    """Parse a model JSON object without accepting arbitrary trailing prose."""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.removeprefix("```json").removeprefix("```")
        stripped = stripped.removesuffix("```").strip()
    try:
        value = json.loads(stripped)
    except json.JSONDecodeError:
        start, end = stripped.find("{"), stripped.rfind("}")
        if start < 0 or end <= start:
            raise
        value = json.loads(stripped[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("model output is not a JSON object")
    return value

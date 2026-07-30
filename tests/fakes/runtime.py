import json
import re

from app.domain.models import EvidenceItem
from app.runtime.agents import AgentReply
from app.tools.capabilities import CapabilityClients, ToolResult


class FakeRunner:
    """Deterministic model substitute used only by tests."""

    async def ask(self, role: str, prompt: str) -> AgentReply:
        if role == "SupervisorAgent":
            text = "先整理临床状态与风险，再检索证据，最后生成可复核报告。"
        elif role == "ClinicalReasoningAgent":
            text = json.dumps(
                {
                    "chief_complaint": "右眼视物模糊",
                    "positives": ["右眼视物模糊"],
                    "negatives": [],
                    "medications": [],
                    "allergies": [],
                    "unresolved_questions": ["起病时间是什么时候？"],
                    "red_flags": [],
                },
                ensure_ascii=False,
            )
        elif role == "DifferentialAssessmentAgent":
            text = json.dumps(
                {
                    "summary": "现有资料支持形成低把握度鉴别，仍需眼科检查确认。",
                    "differentials": [
                        {
                            "name": "原因待查",
                            "supporting_evidence": ["用户报告视物模糊"],
                            "opposing_evidence": [],
                            "missing_evidence": ["视力与眼底检查"],
                            "confidence": "low",
                        },
                    ],
                    "red_flags": [],
                    "missing_information": ["视力与眼底检查"],
                    "recommended_actions": ["补充完整眼科检查"],
                    "evidence_ids": re.findall(r'"id": "(ev_[0-9a-f]+)"', prompt),
                },
                ensure_ascii=False,
            )
        elif role == "CriticAgent":
            text = "不得延误急诊升级；避免确定性诊断。"
        else:
            evidence_ids = re.findall(r'"id": "(ev_[0-9a-f]+)"', prompt)
            citation = f" [{evidence_ids[0]}]" if evidence_ids else ""
            text = (
                "# 研究级眼科评估\n\n"
                f"当前信息只能形成待复核评估，不能确诊。{citation}\n\n"
                "## 不确定性与下一步\n\n建议补充线下眼科检查。\n\n"
                "> 本系统用于研究级诊疗增强，不能替代医生诊断。"
            )
        return AgentReply(text=text, prompt_tokens=20, completion_tokens=10)


class FakeCapabilityClients:
    """Real-shaped fake; injected explicitly and never imported by app code."""

    async def retrieve_medical_evidence(
        self,
        query: str,
        top_k: int = 6,
        *,
        user_id: int | None = None,
    ) -> ToolResult:
        del user_id
        item = EvidenceItem(
            title="测试指南",
            source="tests/fixtures/guideline.md",
            excerpt="任何评估均需结合完整病史和眼科检查。",
            locator="第 1 段",
            score=1.0,
            verified=True,
        )
        return ToolResult(
            status="ok",
            capability="medical_retrieval",
            data={"evidence": [item.model_dump(mode="json")]},
        )

    async def search_web(self, request) -> ToolResult:
        return ToolResult(status="ok", capability="web_search", data={"evidence": []})

    async def analyze_image(self, request) -> ToolResult:
        return ToolResult(
            status="ok",
            capability="medical_image_analysis",
            data={
                "summary": "图像质量允许描述",
                "observations": ["可见眼底结构"],
                "limitations": [],
                "uncertainty": "高",
                "regions": [],
            },
        )

    validate_citations = staticmethod(CapabilityClients.validate_citations)

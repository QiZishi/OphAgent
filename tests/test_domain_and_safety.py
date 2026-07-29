import pytest

from app.domain.models import ClinicalState, EvidenceItem, ImageRegion, RiskLevel, RunInput
from app.plugins.registry import plugin_registry
from app.runtime.planning import build_plan
from app.runtime.routing import route_task
from app.runtime.safety import apply_red_flag_gate
from app.tools.capabilities import CapabilityClients


def test_red_flag_gate_escalates_acute_vision_loss():
    state = ClinicalState()
    risk = apply_red_flag_gate("右眼突然看不见了，还有幕帘样黑影", state)
    assert risk == RiskLevel.EMERGENCY
    assert state.red_flags


def test_plan_contains_parallel_nodes():
    plugin = plugin_registry.get("aux_diagnosis")
    plan = build_plan(plugin, RunInput(query="视物模糊", image_paths=["x.jpg"]), RiskLevel.ROUTINE)
    by_id = {node.id: node for node in plan}
    assert by_id["clinical"].depends_on == []
    assert by_id["evidence"].depends_on == []
    assert by_id["imaging"].depends_on == []
    assert set(by_id["assessment"].depends_on) >= {"clinical", "evidence", "imaging"}
    assert "assessment" in by_id["answer"].depends_on


def test_only_three_professional_plugins_are_public():
    assert {item.id for item in plugin_registry.list()} == {
        "lesion_localizer",
        "aux_diagnosis",
        "report_generator",
    }


def test_knowledge_retrieval_is_core_not_a_selected_plugin():
    route = route_task(RunInput(query="什么是青光眼？"), RiskLevel.ROUTINE)
    assert route.intent == "knowledge_retrieval"
    assert route.needs_retrieval is True
    assert route.selected_plugins == []


def test_image_report_composes_assessment_and_report_plugins():
    run_input = RunInput(
        query="根据这张眼底图生成结构化报告",
        image_paths=["fundus.png"],
    )
    route = route_task(run_input, RiskLevel.ROUTINE)
    plan = build_plan(plugin_registry.get("core"), run_input, RiskLevel.ROUTINE, route)
    by_id = {node.id: node for node in plan}

    assert route.selected_plugins == ["aux_diagnosis", "report_generator"]
    assert {"imaging", "assessment", "report"} <= set(by_id)
    assert "assessment" in by_id["report"].depends_on


def test_one_resolved_attachment_is_not_double_counted_as_deep_work():
    route = route_task(
        RunInput(
            query="请标出可疑区域",
            plugin_id="lesion_localizer",
            requested_plugins=["lesion_localizer"],
            attachment_ids=["att_1"],
            image_paths=["fundus.png"],
        ),
        RiskLevel.ROUTINE,
    )
    plan = build_plan(
        plugin_registry.get("lesion_localizer"),
        RunInput(
            query="请标出可疑区域",
            plugin_id="lesion_localizer",
            requested_plugins=["lesion_localizer"],
            attachment_ids=["att_1"],
            image_paths=["fundus.png"],
        ),
        RiskLevel.ROUTINE,
        route,
    )

    assert route.complexity == "standard"
    assert "clinical" not in {node.id for node in plan}
    assert not any(node.id.startswith("specialist_") for node in plan)


def test_deep_medical_plan_adds_relevant_specialist_review():
    plugin = plugin_registry.get("aux_diagnosis")
    run_input = RunInput(
        query="右眼突发飞蚊和闪光，黄斑 OCT 也有异常，请综合鉴别并给出检查建议",
    )
    route = route_task(run_input, RiskLevel.HIGH)
    plan = build_plan(plugin, run_input, RiskLevel.HIGH, route)
    by_id = {node.id: node for node in plan}
    specialist_ids = [node.id for node in plan if node.id.startswith("specialist_")]

    assert route.complexity == "deep"
    assert "specialist_retina" in specialist_ids
    assert set(by_id["draft"].depends_on) >= set(specialist_ids)
    assert by_id["critic"].depends_on == ["draft"]
    assert "critic" in by_id["answer"].depends_on


def test_emergency_risk_overrides_explicit_quick_mode():
    run_input = RunInput(
        query="清洁剂进入眼睛，现在突然看不清",
        mode="quick",
        plugin_id="interactive_vqa",
    )
    route = route_task(run_input, RiskLevel.EMERGENCY)
    plan = build_plan(
        plugin_registry.get("interactive_vqa"),
        run_input,
        RiskLevel.EMERGENCY,
        route,
    )
    node_ids = [node.id for node in plan]

    assert route.complexity == "deep"
    assert route.intent != "quick_answer"
    assert {"clinical", "draft", "critic", "answer"} <= set(node_ids)
    assert node_ids.index("draft") < node_ids.index("critic") < node_ids.index("answer")


def test_citation_validator_checks_claim_coverage_not_just_one_marker():
    evidence = [
        EvidenceItem(
            title="指南",
            source="guideline.md",
            excerpt="检查建议",
            locator="第 1 段",
            score=1,
            verified=True,
        )
    ]
    answer = (
        f"第一项医学主张有来源支持。 [{evidence[0].id}]\n\n"
        "第二项医学主张包含较长的诊疗建议，但完全没有绑定任何来源。\n\n"
        "第三项医学主张同样没有引用，不能因为前面出现过一个标记就通过。"
    )
    validation = CapabilityClients.validate_citations(answer, evidence)

    assert validation.data["valid"] is False
    assert validation.data["claim_paragraph_count"] == 3
    assert validation.data["cited_claim_paragraph_count"] == 1


def test_normalized_region_cannot_escape_image():
    with pytest.raises(ValueError):
        ImageRegion(
            label="lesion",
            x=0.9,
            y=0.2,
            width=0.2,
            height=0.2,
            coordinate_space="normalized",
            confidence=0.8,
        )

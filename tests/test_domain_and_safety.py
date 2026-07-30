import pytest

from app.domain.models import ClinicalState, EvidenceItem, ImageRegion, RiskLevel, RunInput
from app.plugins.registry import plugin_registry
from app.runtime.planning import build_plan
from app.runtime.routing import route_task
from app.runtime.safety import apply_red_flag_gate, validate_public_medical_output
from app.tools.capabilities import (
    CapabilityClients,
    _normalize_image_analysis_payload,
    _parse_image_analysis_content,
)


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


def test_explicit_quick_cannot_bypass_individualized_medical_route():
    run_input = RunInput(
        query="我滴噻吗洛尔后不舒服，要不要马上停药？",
        mode="quick",
        plugin_id="interactive_vqa",
    )
    route = route_task(run_input, RiskLevel.ROUTINE)

    assert route.intent != "quick_answer"
    assert route.complexity != "quick"


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


def test_citation_prefix_is_expanded_only_when_unique_and_long_enough():
    evidence = [
        EvidenceItem(
            id="ev_1772a5e372e84628a9887c430b187a46",
            title="指南",
            source="guideline.md",
            excerpt="检查建议",
            verified=True,
        ),
        EvidenceItem(
            id="ev_abcdef0123456789abcdef0123456789",
            title="共识",
            source="consensus.md",
            excerpt="随访建议",
            verified=True,
        ),
    ]

    normalized = CapabilityClients.canonicalize_citations(
        "检查包括眼压和视野。[ev_1772a5e3] 未知来源。[ev_deadbeef]",
        evidence,
    )

    assert f"[{evidence[0].id}]" in normalized
    assert "[ev_deadbeef]" in normalized


def test_normalized_region_cannot_escape_image():
    with pytest.raises(ValueError):
        ImageRegion(
            image_id="att_fundus",
            label="lesion",
            x=0.9,
            y=0.2,
            width=0.2,
            height=0.2,
            coordinate_space="normalized",
            confidence=0.8,
        )


def test_image_analysis_normalizes_single_item_array_response():
    normalized = _normalize_image_analysis_payload([
        {
            "summary": "眼底观察",
            "observations": ["视盘杯盘比较大"],
            "limitations": ["图像清晰度有限"],
            "uncertainty": "需结合眼压",
            "regions": [],
        }
    ])

    assert normalized["summary"] == "眼底观察"
    assert normalized["observations"] == ["视盘杯盘比较大"]
    assert normalized["regions"] == []


def test_image_analysis_merges_multi_image_array_response():
    normalized = _normalize_image_analysis_payload([
        {"summary": "图一", "observations": ["观察一"], "regions": [{"image_id": "a"}]},
        {"summary": "图二", "observations": "观察二", "limitations": "视野图需复核"},
    ])

    assert normalized["summary"] == "图一\n图二"
    assert normalized["observations"] == ["观察一", "观察二"]
    assert normalized["limitations"] == ["视野图需复核"]
    assert normalized["regions"] == [{"image_id": "a"}]


def test_image_analysis_keeps_non_json_observation_instead_of_failing_run():
    normalized = _parse_image_analysis_content("可见视盘杯盘比较大，图像边缘略模糊。")

    assert normalized["summary"] == "可见视盘杯盘比较大，图像边缘略模糊。"
    assert normalized["observations"]
    assert normalized["regions"] == []


def test_public_medical_output_blocks_diagnosis_probability_and_direct_medication_change():
    issues = validate_public_medical_output(
        "该患者已经确诊为青光眼，患病概率为 92%。建议立即停用噻吗洛尔滴眼液。",
        individualized=True,
    )

    assert "overconfident_individual_diagnosis" in issues
    assert "fabricated_disease_probability" in issues
    assert "direct_medication_change" in issues


def test_public_medical_output_allows_clinician_review_and_general_education():
    individualized = validate_public_medical_output(
        "当前资料只支持考虑青光眼，需由眼科医生结合眼压、房角和用药史评估后决定是否调整药物。",
        individualized=True,
    )
    educational = validate_public_medical_output(
        "青光眼是一组可导致视神经损伤的疾病。",
        individualized=False,
    )

    assert individualized == []
    assert educational == []

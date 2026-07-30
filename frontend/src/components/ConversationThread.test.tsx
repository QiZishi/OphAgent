import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { AttachmentRecord, Run } from "../types";
import { ConversationThread } from "./ConversationThread";

const attachment: AttachmentRecord = {
  id: "att_fundus",
  original_filename: "fundus.png",
  mime_type: "image/png",
  size: 1024,
  kind: "image",
  created_at: "2026-07-29T00:00:00Z"
};

const run: Run = {
  id: "run_plugins",
  trace_id: "trace_plugins",
  status: "completed",
  risk_level: "routine",
  route: {
    intent: "aux_assessment",
    complexity: "standard",
    selected_plugins: ["lesion_localizer", "aux_diagnosis"],
    reason_code: "test"
  },
  input: {
    query: "请标出异常并给出鉴别",
    plugin_id: "lesion_localizer",
    attachment_ids: [attachment.id],
    image_paths: ["fundus.png"],
    document_paths: [],
    audio_paths: []
  },
  plan: [
    {
      id: "imaging",
      title: "校验并定位可疑影像区域",
      agent: "MultimodalOphthalmologyAgent",
      capability: "medical_image_analysis",
      depends_on: [],
      required: true,
      status: "completed",
      output: {
        regions: [{
          image_id: attachment.id,
          label: "视盘附近可疑区域",
          x: 0.3,
          y: 0.2,
          width: 0.2,
          height: 0.25,
          coordinate_space: "normalized",
          confidence: 0.92,
          reliability: "high"
        }]
      }
    },
    {
      id: "assessment",
      title: "形成结构化鉴别评估",
      agent: "DifferentialAssessmentAgent",
      capability: "main_model",
      depends_on: ["imaging"],
      required: true,
      status: "completed",
      output: {
        summary: "当前资料支持进一步检查。",
        differentials: [{
          name: "视盘相关改变待查",
          supporting_evidence: ["可见局灶改变"],
          opposing_evidence: ["缺少视野资料"],
          missing_evidence: ["眼压与 OCT"],
          confidence: "medium"
        }]
      }
    }
  ],
  answer: "请结合完整眼科检查复核。",
  warnings: [],
  attempt: 1,
  budget: {
    model_calls: 2,
    prompt_tokens: 100,
    completion_tokens: 100,
    max_model_calls: 3,
    max_tokens: 12000
  },
  created_at: "2026-07-29T00:00:00Z"
};

describe("ConversationThread 专业插件结果", () => {
  it("显示经校验定位和定性鉴别，不把模型分数显示为患病概率", () => {
    render(
      <ConversationThread
        runs={[run]}
        eventsByRun={{}}
        artifactsByRun={{}}
        attachmentsById={{ [attachment.id]: attachment }}
        onResume={vi.fn()}
        onRetry={vi.fn()}
        onFeedback={vi.fn()}
        onDelete={vi.fn()}
        onArtifact={vi.fn()}
        onConvertToDocument={vi.fn()}
        onSpeak={vi.fn()}
      />
    );

    expect(screen.getByText("经校验的可疑区域")).toBeInTheDocument();
    expect(screen.getByText("模型定位把握度：较高")).toBeInTheDocument();
    expect(screen.getByText("支持程度不是患病概率")).toBeInTheDocument();
    expect(screen.getByText("视盘相关改变待查")).toBeInTheDocument();
    expect(screen.queryByText("92%")).not.toBeInTheDocument();
  });
});

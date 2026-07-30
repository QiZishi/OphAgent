import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ActivityCard } from "./ActivityCard";
import type { Run } from "../types";

const run: Run = {
  id: "run_test",
  trace_id: "trace",
  status: "completed",
  risk_level: "routine",
  route: {
    intent: "clinical_qna",
    complexity: "standard",
    selected_plugins: [],
    reason_code: "test"
  },
  input: {
    query: "眼睛干涩怎么办？",
    plugin_id: "interactive_vqa",
    attachment_ids: [],
    image_paths: [],
    document_paths: [],
    audio_paths: []
  },
  plan: [{
    id: "answer",
    title: "生成回答",
    agent: "AnswerSynthesizer",
    capability: "main_model",
    depends_on: [],
    status: "completed",
    required: true
  }],
  warnings: [],
  attempt: 1,
  execution_revision: 1,
  budget: {
    model_calls: 1,
    prompt_tokens: 20,
    completion_tokens: 10,
    max_model_calls: 3,
    max_tokens: 12000
  },
  created_at: "2026-07-28T00:00:00Z"
};

describe("ActivityCard", () => {
  it("完成后默认折叠，并可展开公开步骤", () => {
    render(<ActivityCard run={run} events={[]} onResume={vi.fn()} />);
    expect(screen.getByRole("button", { name: /已完成/ })).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(screen.getByRole("button", { name: /已完成/ }));
    expect(screen.getByText("生成回答")).toBeVisible();
  });

  it("失败节点不展示内部异常或校验细节", () => {
    const failedRun: Run = {
      ...run,
      status: "failed",
      error_message: "本次任务未能完成，可以从检查点重试。",
      plan: [{
        ...run.plan[0],
        status: "failed",
        output: {
          detail: "citation_coverage_failed: INTERNAL_SENTINEL",
          output_validation: { issues: ["INTERNAL_SENTINEL"] },
        },
      }],
    };
    render(<ActivityCard run={failedRun} events={[]} onResume={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: /处理未完成/ }));
    expect(screen.queryByText(/INTERNAL_SENTINEL/)).not.toBeInTheDocument();
    expect(screen.getByText("本次任务未能完成，可以从检查点重试。")).toBeVisible();
  });
});

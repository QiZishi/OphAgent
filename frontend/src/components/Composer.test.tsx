import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Composer } from "./Composer";

describe("Composer", () => {
  it("输入法组合态按 Enter 不发送，结束组合后可发送", () => {
    const submit = vi.fn();
    render(
      <Composer
        value="测试"
        attachments={[]}
        plugins={[]}
        skills={[]}
        selectedSkills={[]}
        submitting={false}
        running={false}
        onValue={vi.fn()}
        onFiles={vi.fn()}
        onRemoveFile={vi.fn()}
        onTogglePlugin={vi.fn()}
        onToggleSkill={vi.fn()}
        onSubmit={submit}
        onStop={vi.fn()}
        onTranscribe={vi.fn().mockResolvedValue("转写文本")}
        onSpeak={vi.fn().mockResolvedValue(new Blob())}
        asrAvailable
        ttsAvailable
        onListFiles={vi.fn().mockResolvedValue([])}
        onChooseExisting={vi.fn()}
      />
    );
    const textarea = screen.getByLabelText("向 OphAgent 提问");
    fireEvent.compositionStart(textarea);
    fireEvent.keyDown(textarea, { key: "Enter", code: "Enter", isComposing: true });
    expect(submit).not.toHaveBeenCalled();
    fireEvent.compositionEnd(textarea);
    fireEvent.keyDown(textarea, { key: "Enter", code: "Enter" });
    expect(submit).toHaveBeenCalledOnce();
  });

  it("插件选择器与真实语音入口可见", () => {
    render(
      <Composer
        value=""
        attachments={[]}
        plugins={[]}
        skills={[]}
        selectedSkills={[]}
        submitting={false}
        running={false}
        onValue={vi.fn()}
        onFiles={vi.fn()}
        onRemoveFile={vi.fn()}
        onTogglePlugin={vi.fn()}
        onToggleSkill={vi.fn()}
        onSubmit={vi.fn()}
        onStop={vi.fn()}
        onTranscribe={vi.fn().mockResolvedValue("转写文本")}
        onSpeak={vi.fn().mockResolvedValue(new Blob())}
        asrAvailable
        ttsAvailable
        onListFiles={vi.fn().mockResolvedValue([])}
        onChooseExisting={vi.fn()}
      />
    );
    fireEvent.click(screen.getByRole("button", { name: "插件" }));
    expect(screen.getByText("病灶定位")).toBeVisible();
    expect(screen.getByRole("button", { name: "语音输入" })).toBeVisible();
    expect(screen.getByRole("button", { name: "实时语音模式" })).toBeVisible();
  });
});

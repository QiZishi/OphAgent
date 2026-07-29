import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { GlobalActionTooltip } from "./GlobalActionTooltip";

afterEach(() => {
  vi.useRealTimers();
});

describe("GlobalActionTooltip", () => {
  it("按钮被 React 替换后清除旧操作提示", async () => {
    vi.useFakeTimers();
    const { rerender } = render(
      <>
        <GlobalActionTooltip />
        <button aria-label="停止当前任务">停止</button>
      </>
    );
    fireEvent.pointerOver(screen.getByRole("button", { name: "停止当前任务" }));
    await act(async () => vi.advanceTimersByTime(330));
    expect(screen.getByRole("tooltip")).toHaveTextContent("停止当前正在执行的任务");

    rerender(
      <>
        <GlobalActionTooltip />
        <button aria-label="发送">发送</button>
      </>
    );
    await act(async () => {
      await Promise.resolve();
    });
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
  });
});

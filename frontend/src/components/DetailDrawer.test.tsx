import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Artifact } from "../types";
import { DetailDrawer } from "./DetailDrawer";

const artifact: Artifact = {
  id: "art_test",
  run_id: "run_test",
  type: "document",
  title: "原标题",
  mime_type: "text/markdown",
  content: "原内容",
  metadata: {}
};

describe("DetailDrawer", () => {
  beforeEach(() => {
    const values = new Map<string, string>();
    Object.defineProperty(globalThis, "localStorage", {
      configurable: true,
      value: {
        getItem: (key: string) => values.get(key) ?? null,
        setItem: (key: string, value: string) => values.set(key, value),
        removeItem: (key: string) => values.delete(key),
        clear: () => values.clear()
      }
    });
  });

  it("按 Esc 时先保存最新编辑，再关闭", async () => {
    const onClose = vi.fn();
    const onChange = vi.fn();
    const onSave = vi.fn(async (_id: string, values: { title?: string; content?: string }) => ({
      ...artifact,
      ...values
    }));
    render(
      <DetailDrawer
        open
        artifact={artifact}
        onClose={onClose}
        onChange={onChange}
        onSave={onSave}
      />
    );

    fireEvent.change(screen.getByLabelText("编辑文档内容"), {
      target: { value: "刚刚编辑的内容" }
    });
    fireEvent.keyDown(document, { key: "Escape" });

    await waitFor(() => expect(onSave).toHaveBeenCalledWith(
      "art_test",
      { title: "原标题", content: "刚刚编辑的内容" }
    ));
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({
      content: "刚刚编辑的内容"
    }));
  });

  it("较早保存请求返回时不会覆盖较新的编辑", async () => {
    let resolveFirst: ((value: Artifact) => void) | undefined;
    const first = new Promise<Artifact>((resolve) => {
      resolveFirst = resolve;
    });
    const onChange = vi.fn();
    const onSave = vi.fn()
      .mockImplementationOnce(() => first)
      .mockImplementationOnce(async (_id: string, values: { title?: string; content?: string }) => ({
        ...artifact,
        ...values
      }));
    render(
      <DetailDrawer
        open
        artifact={artifact}
        onClose={vi.fn()}
        onChange={onChange}
        onSave={onSave}
      />
    );

    fireEvent.change(screen.getByLabelText("编辑文档内容"), {
      target: { value: "第一版" }
    });
    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1), { timeout: 1200 });
    fireEvent.change(screen.getByLabelText("编辑文档内容"), {
      target: { value: "第二版" }
    });
    resolveFirst?.({ ...artifact, content: "第一版" });

    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(2), { timeout: 1200 });
    await waitFor(() => expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ content: "第二版" })
    ));
    expect(onChange).not.toHaveBeenCalledWith(
      expect.objectContaining({ content: "第一版" })
    );
    expect(screen.getByLabelText("编辑文档内容")).toHaveValue("第二版");
  });
});

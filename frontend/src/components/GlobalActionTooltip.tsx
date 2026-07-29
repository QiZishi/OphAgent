import { useEffect, useRef, useState } from "react";

type TooltipState = {
  text: string;
  left: number;
  top: number;
  placement: "top" | "bottom";
};

const INTERACTIVE = "button, summary, [role='button'], .add-menu label, label.provider-mode, a[data-action-tooltip], a[href*='/export?format=']";
const ACTION_EXPLANATIONS: Record<string, string> = {
  "新对话": "创建一个新的对话",
  "搜索": "搜索历史对话",
  "项目": "打开项目工作区",
  "文件库": "打开上传文件与生成产物",
  "插件": "选择本次任务使用的专业插件",
  "技能": "选择本次任务使用的技能",
  "记忆": "管理跨会话记忆",
  "知识库": "管理知识来源与索引",
  "设置": "打开账户与模型供应商设置",
  "发送": "发送当前消息",
  "停止当前任务": "停止当前正在执行的任务",
  "添加附件": "添加影像、文档或音频附件",
  "上传影像": "从本机上传一张或多张眼科影像",
  "上传文档": "从本机上传一份或多份文档",
  "上传音频": "从本机上传一份或多份音频",
  "语音输入": "使用麦克风录音并转写到输入框",
  "实时语音模式": "打开连续语音对话模式",
  "复制回答": "复制当前回答",
  "重新生成回答": "移除当前回答并重新生成一个版本",
  "有帮助": "将当前回答标记为有帮助",
  "没有帮助": "将当前回答标记为没有帮助",
  "朗读回答": "播放当前回答的语音",
  "更多操作": "展开回答的导出、编辑与删除操作",
  "导出": "展开可选择的导出格式",
  "上一版回答": "查看上一个回答版本",
  "下一版回答": "查看下一个回答版本",
  "打开导航": "打开侧栏导航",
  "关闭导航": "关闭侧栏导航",
  "折叠侧栏": "折叠左侧导航栏",
  "展开侧栏": "展开左侧导航栏",
  "退出登录": "退出当前账户",
};

export function GlobalActionTooltip() {
  const [tooltip, setTooltip] = useState<TooltipState | null>(null);
  const timer = useRef<number | null>(null);
  const active = useRef<HTMLElement | null>(null);

  useEffect(() => {
    const clear = () => {
      if (timer.current !== null) window.clearTimeout(timer.current);
      timer.current = null;
      active.current = null;
      setTooltip(null);
    };
    const syncDisabledTitles = () => {
      document.querySelectorAll<HTMLElement>(INTERACTIVE).forEach((element) => {
        const disabled = element instanceof HTMLButtonElement && element.disabled;
        if (disabled && !element.getAttribute("title")) {
          element.setAttribute("title", describeAction(element));
          element.dataset.generatedDisabledTitle = "true";
        } else if (!disabled && element.dataset.generatedDisabledTitle) {
          element.removeAttribute("title");
          delete element.dataset.generatedDisabledTitle;
        }
      });
    };
    syncDisabledTitles();
    const observer = new MutationObserver((records) => {
      syncDisabledTitles();
      if (
        active.current
        && records.some((record) =>
          (record.type === "childList"
            && [...record.removedNodes].some((node) =>
              node === active.current
              || (node instanceof Element && node.contains(active.current))
            ))
          || (record.type === "attributes" && record.target === active.current)
        )
      ) {
        // React may replace the send/stop button while the pointer remains at
        // the same coordinates, which does not emit a new pointerover event.
        // Remove the stale explanation; the next pointer/focus event resolves
        // the action from the current DOM node.
        clear();
      }
    });
    observer.observe(document.body, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ["disabled", "aria-label", "title"],
    });
    const reveal = (element: HTMLElement, immediate = false) => {
      if (timer.current !== null) window.clearTimeout(timer.current);
      active.current = element;
      const show = () => {
        const rect = element.getBoundingClientRect();
        const placement = rect.top > 56 ? "top" : "bottom";
        const safeEdge = Math.min(170, Math.max(12, window.innerWidth / 2 - 12));
        setTooltip({
          text: describeAction(element),
          left: Math.max(safeEdge, Math.min(window.innerWidth - safeEdge, rect.left + rect.width / 2)),
          top: placement === "top" ? rect.top - 8 : rect.bottom + 8,
          placement,
        });
      };
      timer.current = window.setTimeout(show, immediate ? 0 : 320);
    };
    const targetOf = (event: Event) =>
      event.target instanceof Element
        ? event.target.closest<HTMLElement>(INTERACTIVE)
        : null;
    const onPointerOver = (event: PointerEvent) => {
      const element = targetOf(event);
      if (element && element !== active.current) reveal(element);
    };
    const onPointerOut = (event: PointerEvent) => {
      const element = targetOf(event);
      if (!element) return;
      if (event.relatedTarget instanceof Node && element.contains(event.relatedTarget)) return;
      clear();
    };
    const onFocusIn = (event: FocusEvent) => {
      const element = targetOf(event);
      if (element) reveal(element, true);
    };
    const onFocusOut = (event: FocusEvent) => {
      const element = targetOf(event);
      if (!element) return;
      if (event.relatedTarget instanceof Node && element.contains(event.relatedTarget)) return;
      clear();
    };
    const onViewportChange = () => clear();
    document.addEventListener("pointerover", onPointerOver);
    document.addEventListener("pointerout", onPointerOut);
    document.addEventListener("focusin", onFocusIn);
    document.addEventListener("focusout", onFocusOut);
    window.addEventListener("scroll", onViewportChange, true);
    window.addEventListener("resize", onViewportChange);
    return () => {
      observer.disconnect();
      clear();
      document.removeEventListener("pointerover", onPointerOver);
      document.removeEventListener("pointerout", onPointerOut);
      document.removeEventListener("focusin", onFocusIn);
      document.removeEventListener("focusout", onFocusOut);
      window.removeEventListener("scroll", onViewportChange, true);
      window.removeEventListener("resize", onViewportChange);
    };
  }, []);

  if (!tooltip) return null;
  return (
    <div
      className={`global-action-tooltip tooltip-${tooltip.placement}`}
      role="tooltip"
      style={{ left: tooltip.left, top: tooltip.top }}
    >
      {tooltip.text}
    </div>
  );
}

function describeAction(element: HTMLElement) {
  const explicit = element.dataset.tooltip || element.getAttribute("aria-label") || element.getAttribute("title");
  if (explicit) return explain(explicit);

  const href = element.getAttribute("href") || "";
  const format = new URLSearchParams(href.split("?")[1] || "").get("format");
  if (format) return `导出为 ${format.toUpperCase()} 文件`;

  const strong = normalize(element.querySelector("strong")?.textContent || "");
  if (element.matches(".conversation-select")) return `打开对话：${normalize(element.textContent || "")}`;
  if (element.matches(".artifact-card")) return `打开产物：${strong || "查看详情"}`;
  if (element.matches(".plugin-menu > button")) return `选择或取消插件：${strong || "当前插件"}`;
  if (element.matches(".skill-menu > button")) return `选择或取消技能：${strong || "当前技能"}`;
  if (element.tagName === "SUMMARY" && element.closest(".activity-card, .activity-step")) {
    return `${element.getAttribute("aria-expanded") === "true" || element.parentElement?.hasAttribute("open") ? "收起" : "展开"}：${strong || "执行过程"}`;
  }

  const text = normalize(element.innerText || element.textContent || "");
  return explain(text || "执行此操作");
}

function normalize(value: string) {
  return value.replace(/\s+/g, " ").trim().slice(0, 90);
}

function ensureChinese(value: string) {
  return /[\u3400-\u9fff]/.test(value) ? value : `操作：${value}`;
}

function explain(value: string) {
  return ACTION_EXPLANATIONS[value] || ensureChinese(value);
}

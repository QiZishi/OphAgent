import { Check, Download, FileDown, FileText, PencilLine, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import type { Artifact } from "../types";
import { LoadingDots } from "./LoadingDots";

const DEFAULT_DRAWER_WIDTH = 640;

export function DetailDrawer({
  open,
  artifact,
  onClose,
  onChange,
  onSave
}: {
  open: boolean;
  artifact: Artifact | null;
  onClose: () => void;
  onChange: (artifact: Artifact) => void;
  onSave: (id: string, values: { title?: string; content?: string }) => Promise<Artifact>;
}) {
  const drawerRef = useRef<HTMLElement>(null);
  const onCloseRef = useRef(onClose);
  const dirty = useRef(false);
  const [width, setWidth] = useState(() => Number(localStorage.getItem("ophagent.drawer.width")) || DEFAULT_DRAWER_WIDTH);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [saveState, setSaveState] = useState<"saved" | "saving" | "error">("saved");

  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    localStorage.setItem("ophagent.drawer.width", String(Math.round(width)));
  }, [width]);

  useEffect(() => {
    setTitle(artifact?.title || "");
    setContent(artifact?.content || "");
    setSaveState("saved");
    dirty.current = false;
  }, [artifact?.id, artifact?.content, artifact?.title]);

  useEffect(() => {
    if (!open || !artifact || !dirty.current) return;
    setSaveState("saving");
    const timer = window.setTimeout(async () => {
      try {
        const updated = await onSave(artifact.id, { title, content });
        dirty.current = false;
        setSaveState("saved");
        onChange(updated);
      } catch {
        setSaveState("error");
      }
    }, 700);
    return () => window.clearTimeout(timer);
  }, [artifact, content, onChange, onSave, open, title]);

  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement as HTMLElement | null;
    const drawer = drawerRef.current;
    const focusable = () => Array.from(
      drawer?.querySelectorAll<HTMLElement>("button, a[href], input, textarea, [tabindex]:not([tabindex='-1'])") || []
    );
    focusable()[0]?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onCloseRef.current();
        return;
      }
      if (event.key !== "Tab") return;
      const items = focusable();
      if (!items.length) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      previous?.focus();
    };
  }, [open]);

  function beginResize(event: React.PointerEvent) {
    event.currentTarget.setPointerCapture(event.pointerId);
    const start = event.clientX;
    const initial = width;
    const move = (moveEvent: PointerEvent) => {
      const next = Math.max(380, Math.min(window.innerWidth * 0.78, initial + start - moveEvent.clientX));
      setWidth(next);
    };
    const end = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", end);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", end);
  }

  async function closeDrawer() {
    if (artifact && dirty.current) {
      try {
        setSaveState("saving");
        const updated = await onSave(artifact.id, { title, content });
        dirty.current = false;
        setSaveState("saved");
        onChange(updated);
      } catch {
        setSaveState("error");
        return;
      }
    }
    onClose();
  }

  if (!open || !artifact) return null;
  const editable = artifact.content !== undefined;
  return (
    <>
      <button className="drawer-scrim" aria-label="关闭文档工作区" onClick={() => void closeDrawer()} />
      <aside
        ref={drawerRef}
        className="detail-drawer"
        role="dialog"
        aria-modal="true"
        aria-label="文档工作区"
        style={{ "--drawer-width": `${width}px` } as React.CSSProperties}
      >
        <div
          className="drawer-resizer"
          role="separator"
          aria-label="调整文档工作区宽度"
          aria-orientation="vertical"
          aria-valuemin={380}
          aria-valuemax={Math.round(window.innerWidth * 0.78)}
          aria-valuenow={Math.round(width)}
          tabIndex={0}
          onPointerDown={beginResize}
          onDoubleClick={() => {
            setWidth(DEFAULT_DRAWER_WIDTH);
            localStorage.setItem("ophagent.drawer.width", String(DEFAULT_DRAWER_WIDTH));
          }}
          onKeyDown={(event) => {
            if (!["ArrowLeft", "ArrowRight", "Home"].includes(event.key)) return;
            event.preventDefault();
            const next = event.key === "Home"
              ? DEFAULT_DRAWER_WIDTH
              : Math.max(380, Math.min(window.innerWidth * 0.78, width + (event.key === "ArrowLeft" ? 20 : -20)));
            setWidth(next);
            localStorage.setItem("ophagent.drawer.width", String(next));
          }}
        />
        <header>
          <div className="drawer-title">
            <small>文档工作区</small>
            <input
              value={title}
              onChange={(event) => {
                dirty.current = true;
                setTitle(event.target.value);
              }}
              aria-label="文档标题"
            />
          </div>
          <div className="drawer-actions">
            <span className={`save-state save-${saveState}`}>
              {saveState === "saving" ? <LoadingDots label="正在保存文档" /> : saveState === "saved" ? <Check size={14} /> : null}
              {saveState === "saving" ? "保存中" : saveState === "saved" ? "已保存" : "保存失败"}
            </span>
            <details className="drawer-export">
              <summary className="icon-button" aria-label="导出文档"><FileDown size={18} /></summary>
              <div>
                {(["md", "pdf", "docx", "jpg"] as const).map((format) => (
                  <a key={format} href={`/api/v1/artifacts/${artifact.id}/export?format=${format}`}>
                    <Download size={15} />{format.toUpperCase()}
                  </a>
                ))}
              </div>
            </details>
            <button className="icon-button" onClick={() => void closeDrawer()} aria-label="关闭文档工作区"><X size={19} /></button>
          </div>
        </header>
        {editable ? (
          <div className="document-workspace">
            <section className="document-editor">
              <header><PencilLine size={16} /><strong>编辑 Markdown</strong></header>
              <textarea
                value={content}
                onChange={(event) => {
                  dirty.current = true;
                  setContent(event.target.value);
                }}
                aria-label="编辑文档内容"
                spellCheck={false}
              />
            </section>
            <section className="document-preview">
              <header><FileText size={16} /><strong>实时预览</strong></header>
              <article className="artifact-preview markdown-body">
                <ReactMarkdown>{content || "开始编辑后，预览会实时显示在这里。"}</ReactMarkdown>
              </article>
            </section>
          </div>
        ) : (
          <div className="artifact-preview">
            <div className="artifact-meta"><FileText size={18} /><span>{artifact.mime_type}</span></div>
            <p>此产物没有可编辑的文本内容，请下载原文件查看。</p>
          </div>
        )}
      </aside>
    </>
  );
}

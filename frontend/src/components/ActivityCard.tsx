import { AlertCircle, Check, ChevronDown, RotateCw } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { pluginLabel } from "../features/plugins";
import type { PlanNode, Run, RunEvent } from "../types";
import { LoadingDots } from "./LoadingDots";

export function ActivityCard({ run, events, onResume }: { run: Run; events: RunEvent[]; onResume: () => void }) {
  const terminal = ["completed", "completed_with_warnings", "interrupted", "failed", "cancelled"].includes(run.status);
  const recoverable = ["failed", "interrupted"].includes(run.status);
  const [open, setOpen] = useState(!terminal);
  const terminalEvent = [...events].reverse().find((event) =>
    ["run.completed", "run.failed", "run.cancelled"].includes(event.type)
  );
  // Feedback and other post-run metadata updates may change run.updated_at.
  // The terminal event is the durable end of execution and keeps the timer stable.
  const elapsed = useElapsed(run.created_at, terminalEvent?.timestamp, terminal);
  useEffect(() => setOpen(!terminal), [run.id, terminal]);
  const usedPlugins = run.route?.selected_plugins?.map(pluginLabel) || [];
  const visibleNodes = useMemo(
    () => run.plan.filter((node) =>
      node.status !== "pending"
      || events.some((event) => event.data.node_id === node.id)
    ),
    [events, run.plan]
  );
  const latestPublicEvent = [...events].reverse().find((event) =>
    ["agent.started", "agent.completed", "tool.started", "tool.completed", "tool.failed", "retrieval.result"].includes(event.type)
  );
  const contextEvent = events.find((event) => event.type === "context.prepared");
  const memoryEvent = events.find((event) => event.type === "memory.recalled");
  const title = run.status === "failed"
    ? "处理未完成"
    : run.status === "interrupted"
      ? "任务已中断"
      : run.status === "waiting_for_user"
        ? "需要补充资料"
        : run.status === "cancelled"
          ? "已停止"
          : terminal
            ? "已完成"
            : cleanPublicSummary(latestPublicEvent?.public_summary) || "正在分析请求";

  return (
    <div className={`activity-card activity-${run.status}`}>
      <button className="activity-summary" onClick={() => setOpen((value) => !value)} aria-expanded={open}>
        <span className="activity-state-icon">
          {recoverable ? <AlertCircle size={17} /> : terminal ? <Check size={17} /> : <LoadingDots label="任务执行中" />}
        </span>
        <span>
          <strong>{title}</strong>
          <small>{terminal ? "已处理" : "正在处理"} · {elapsed} · {usedPlugins.length ? usedPlugins.join("、") : "默认能力"}</small>
        </span>
        <ChevronDown className={open ? "open" : ""} size={17} />
      </button>
      {open && (
        <div className="activity-details">
          {(contextEvent || memoryEvent) && (
            <div className="activity-context-note">
              {contextEvent && <span>{contextEvent.public_summary}</span>}
              {memoryEvent && <span>{memoryEvent.public_summary}</span>}
            </div>
          )}
          {!visibleNodes.length && (
            <div className="activity-awaiting"><LoadingDots label="正在建立执行路径" /><span>正在确定下一步</span></div>
          )}
          {visibleNodes.map((node) => (
            <PublicStage key={node.id} node={node} events={events.filter((event) => event.data.node_id === node.id)} />
          ))}
          {recoverable && (
            <div className="activity-recovery">
              <p>{run.status === "interrupted" ? "服务重启时保留了已完成结果，可从未完成步骤继续。" : run.error_message || "必要步骤未完成。已完成的内容和附件均已保留。"}</p>
              <button onClick={onResume}><RotateCw size={14} />精简后重试</button>
            </div>
          )}
          {run.status === "waiting_for_user" && (
            <div className="activity-recovery">
              <p>{run.pending_question || [...events].reverse().find((event) => event.type === "run.question")?.public_summary || "请在下方补充信息后继续。"}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function PublicStage({ node, events }: { node: PlanNode; events: RunEvent[] }) {
  const latest = events.at(-1);
  const running = node.status === "running" || latest?.type.endsWith(".started");
  const result = summarizeResult(node);
  return (
    <details className={`activity-step step-${node.status}`}>
      <summary>
        <span className="step-icon">
          {node.status === "completed"
            ? <Check size={14} />
            : running
              ? <LoadingDots label={`${node.title}进行中`} />
              : <AlertCircle size={14} />}
        </span>
        <span>
          <strong>{node.title}</strong>
          <small>{cleanPublicSummary(latest?.public_summary) || (running ? "正在处理这一阶段" : "阶段已记录")}</small>
        </span>
        <em>{node.status === "completed" ? "完成" : running ? "进行中" : node.status === "failed" ? "失败" : "已跳过"}</em>
        <ChevronDown size={14} />
      </summary>
      <div className="step-detail">
        {latest?.duration_ms && <small className="stage-duration">本阶段用时 {formatDuration(latest.duration_ms)}</small>}
        {result.length ? (
          <ul>{result.map((item, index) => <li key={`${node.id}-${index}`}>{item}</li>)}</ul>
        ) : (
          <p>{running ? "关键结果会在本阶段完成后追加到这里。" : "本阶段没有需要额外展示的公开结果。"}</p>
        )}
      </div>
    </details>
  );
}

function summarizeResult(node: PlanNode): string[] {
  const output = node.output;
  if (!output) return [];
  const items: string[] = [];
  const evidence = Array.isArray(output.evidence) ? output.evidence as Array<Record<string, unknown>> : [];
  if (evidence.length) {
    items.push(`检索并筛选出 ${evidence.length} 条可追踪来源。`);
    evidence.slice(0, 3).forEach((item) => {
      if (item.title) items.push(`来源：${String(item.title)}`);
    });
  }
  const observations = Array.isArray(output.observations) ? output.observations : [];
  observations.slice(0, 4).forEach((item) => items.push(`观察：${compact(item)}`));
  const limitations = Array.isArray(output.limitations) ? output.limitations : [];
  limitations.slice(0, 3).forEach((item) => items.push(`限制：${compact(item)}`));
  if (typeof output.summary === "string") items.push(compact(output.summary));
  if (typeof output.review === "string") items.push(`复核结果：${compact(output.review)}`);
  const differentials = Array.isArray(output.differentials) ? output.differentials as Array<Record<string, unknown>> : [];
  if (differentials.length) {
    items.push(`形成 ${differentials.length} 项定性鉴别，已分别记录支持、反对和缺失信息。`);
  }
  if (typeof output.region_count === "number") {
    items.push(output.region_count > 0
      ? `保留 ${output.region_count} 个通过坐标校验的可疑区域。`
      : "模型未返回可可靠校验的定位区域，系统没有补造坐标。");
  }
  if (Array.isArray(output.transcripts)) items.push(`已整理 ${output.transcripts.length} 段语音内容。`);
  if (output.clinical_state && typeof output.clinical_state === "object") {
    const state = output.clinical_state as Record<string, unknown>;
    if (state.chief_complaint) items.push(`主诉：${compact(state.chief_complaint)}`);
    if (Array.isArray(state.red_flags) && state.red_flags.length) items.push(`识别到 ${state.red_flags.length} 项需要优先关注的信息。`);
    if (Array.isArray(state.unresolved_questions) && state.unresolved_questions.length) items.push(`仍有 ${state.unresolved_questions.length} 项信息需要确认。`);
  }
  if (output.citation_validation && typeof output.citation_validation === "object") {
    const validation = output.citation_validation as Record<string, unknown>;
    if (validation.valid !== undefined) items.push(validation.valid ? "引用与来源已经完成一致性检查。" : "引用检查发现需要保留的不确定项。");
  }
  if (typeof output.answer === "string" && !items.length) items.push("已经形成最终回答并完成公开输出。");
  if (!items.length) {
    Object.entries(output).slice(0, 3).forEach(([key, value]) => {
      if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
        items.push(`${humanizeKey(key)}：${compact(value)}`);
      }
    });
  }
  return items.slice(0, 5);
}

function useElapsed(createdAt: string, updatedAt: string | undefined, terminal: boolean) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (terminal) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [terminal]);
  const end = terminal && updatedAt ? new Date(updatedAt).getTime() : now;
  return formatDuration(Math.max(0, end - new Date(createdAt).getTime()));
}

function formatDuration(milliseconds: number) {
  const seconds = Math.max(0, Math.round(milliseconds / 1000));
  if (seconds < 60) return `${seconds} 秒`;
  return `${Math.floor(seconds / 60)} 分 ${seconds % 60} 秒`;
}

function cleanPublicSummary(value?: string) {
  return (value || "")
    .replace(/^[A-Za-z][A-Za-z0-9_:-]*\s*(开始|已完成)[：:]\s*/i, "")
    .replace(/^OphAgent\s*/, "")
    .trim();
}

function compact(value: unknown) {
  const text = typeof value === "string" ? value : JSON.stringify(value, null, 0);
  return text.length > 320 ? `${text.slice(0, 320)}…` : text;
}

function humanizeKey(key: string) {
  const labels: Record<string, string> = {
    status: "状态",
    detail: "结果",
    text: "内容",
    count: "数量"
  };
  return labels[key] || key.replaceAll("_", " ");
}

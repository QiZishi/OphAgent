import {
  Check,
  ChevronLeft,
  ChevronRight,
  Copy,
  Crosshair,
  Download,
  ExternalLink,
  FileDown,
  FileText,
  MoreHorizontal,
  PencilLine,
  RefreshCw,
  ThumbsDown,
  ThumbsUp,
  Trash2,
  Volume2,
  VolumeX
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import { ActivityCard } from "./ActivityCard";
import { LoadingDots } from "./LoadingDots";
import type { Artifact, AttachmentRecord, Evidence, Run, RunEvent } from "../types";

interface ThreadProps {
  runs: Run[];
  eventsByRun: Record<string, RunEvent[]>;
  artifactsByRun: Record<string, Artifact[]>;
  attachmentsById: Record<string, AttachmentRecord>;
  onResume: (run: Run) => void;
  onRetry: (run: Run) => void;
  onFeedback: (run: Run, value: "up" | "down") => void;
  onDelete: (run: Run) => void;
  onArtifact: (artifact: Artifact) => void;
  onConvertToDocument: (run: Run) => Promise<void>;
  onSpeak: (text: string, signal?: AbortSignal) => Promise<Blob>;
}

export function ConversationThread(props: ThreadProps) {
  const groups = useMemo(() => groupRuns(props.runs), [props.runs]);
  if (!groups.length) return <EmptyState />;
  return (
    <div className="thread-content">
      {groups.map((versions) => (
        <TurnGroup key={versions[0].id} versions={versions} {...props} />
      ))}
    </div>
  );
}

function TurnGroup({
  versions,
  eventsByRun,
  artifactsByRun,
  attachmentsById,
  onResume,
  onRetry,
  onFeedback,
  onDelete,
  onArtifact,
  onConvertToDocument,
  onSpeak
}: ThreadProps & { versions: Run[] }) {
  const [selected, setSelected] = useState(versions.length - 1);
  const versionIds = versions.map((run) => run.id).join(":");
  useEffect(() => setSelected(versions.length - 1), [versionIds, versions.length]);
  const run = versions[Math.min(selected, versions.length - 1)];
  const root = versions[0];
  const events = eventsByRun[run.id] || [];
  const evidence = uniqueEvidence(events
    .filter((event) => event.type === "retrieval.result")
    .flatMap((event) => (event.data.evidence as Evidence[] | undefined) || []));
  const artifacts = artifactsByRun[run.id] || [];
  const streamedAnswer = events
    .filter((event) => event.type === "answer.delta")
    .sort((a, b) => a.sequence - b.sequence)
    .map((event) => String(event.data.delta || ""))
    .join("");
  const visibleAnswer = run.answer || streamedAnswer;
  const terminal = ["completed", "completed_with_warnings", "failed", "cancelled", "interrupted"].includes(run.status);
  const userAttachments = root.input.attachment_ids
    .map((id) => attachmentsById[id])
    .filter(Boolean);

  return (
    <section className="turn">
      <div className="user-bubble">
        <div className="user-message">
          {userAttachments.length > 0 && (
            <div className="user-attachment-grid" aria-label="本次提问的附件">
              {userAttachments.map((attachment) => (
                <a
                  href={`/api/v1/attachments/${attachment.id}`}
                  target="_blank"
                  rel="noreferrer"
                  className={`user-attachment user-attachment-${attachment.kind}`}
                  key={attachment.id}
                >
                  {attachment.kind === "image"
                    ? <img src={`/api/v1/attachments/${attachment.id}`} alt={attachment.original_filename} />
                    : <FileText size={22} />}
                  <span><strong>{attachment.original_filename}</strong><small>{formatBytes(attachment.size)}</small></span>
                </a>
              ))}
            </div>
          )}
          <p>{root.input.query}</p>
        </div>
      </div>
      <div className="assistant-turn">
        <div className="assistant-mark"><img src="/static/icons/system_logo.png" alt="" /></div>
        <div className="assistant-body">
          <ActivityCard run={run} events={events} onResume={() => onResume(run)} />
          <PluginResults run={run} attachments={userAttachments} />
          {visibleAnswer && (
            <div className="markdown-body">
              <ReactMarkdown components={{
                a: ({ href, children }) => {
                  const id = href?.startsWith("#citation-") ? href.replace("#citation-", "") : "";
                  const item = evidence.find((candidate) => candidate.id === id);
                  return item
                    ? <InlineCitation item={item} index={evidence.indexOf(item) + 1} />
                    : <a href={href}>{children}</a>;
                }
              }}>
                {injectCitationLinks(visibleAnswer, evidence)}
              </ReactMarkdown>
            </div>
          )}
          {run.status === "failed" && !visibleAnswer && (
            <div className="run-error" role="alert">
              <strong>{run.error_message || "处理未完成"}</strong>
              <p>已完成步骤和附件均已保留，可展开上方步骤查看失败位置。</p>
            </div>
          )}
          {artifacts.length > 0 && (
            <div className="artifact-grid">
              {artifacts.map((artifact) => (
                <button className="artifact-card" key={artifact.id} onClick={() => onArtifact(artifact)}>
                  <span>{artifact.type === "report" ? "报告" : "可编辑文档"}</span>
                  <strong>{artifact.title}</strong>
                  <small>{artifact.mime_type} · 打开工作区</small>
                </button>
              ))}
            </div>
          )}
          {evidence.length > 0 && <CitationGroup evidence={evidence} />}
          {visibleAnswer && terminal && (
            <MessageActions
              run={run}
              answer={visibleAnswer}
              onRetry={() => onRetry(run)}
              onFeedback={(value) => onFeedback(run, value)}
              onDelete={() => onDelete(run)}
              onConvert={() => onConvertToDocument(run)}
              canConvert={artifacts.length === 0}
              onSpeak={onSpeak}
            />
          )}
          {versions.length > 1 && (
            <nav className="answer-version-switcher" aria-label="回答版本">
              <button onClick={() => setSelected((value) => Math.max(0, value - 1))} disabled={selected === 0} aria-label="上一版回答"><ChevronLeft size={16} /></button>
              <span>回答 {selected + 1} / {versions.length}</span>
              <button onClick={() => setSelected((value) => Math.min(versions.length - 1, value + 1))} disabled={selected === versions.length - 1} aria-label="下一版回答"><ChevronRight size={16} /></button>
            </nav>
          )}
        </div>
      </div>
    </section>
  );
}

interface LocalizedRegion {
  image_id: string;
  label: string;
  x: number;
  y: number;
  width: number;
  height: number;
  coordinate_space: "pixels" | "normalized";
  confidence?: number;
  reliability?: "low" | "medium" | "high" | "not_reported";
}

interface StructuredDifferential {
  name: string;
  supporting_evidence?: string[];
  opposing_evidence?: string[];
  missing_evidence?: string[];
  confidence?: "low" | "medium" | "high";
}

function PluginResults({ run, attachments }: { run: Run; attachments: AttachmentRecord[] }) {
  const imaging = run.plan.find((node) => node.id === "imaging")?.output;
  const assessment = run.plan.find((node) => node.id === "assessment")?.output;
  const regions = Array.isArray(imaging?.regions) ? imaging.regions as unknown as LocalizedRegion[] : [];
  const differentials = Array.isArray(assessment?.differentials)
    ? assessment.differentials as unknown as StructuredDifferential[]
    : [];
  const images = attachments.filter((attachment) => attachment.kind === "image");
  const localizationSelected = run.route?.selected_plugins.includes("lesion_localizer") || false;
  const localizationFinished = run.plan.find((node) => node.id === "imaging")?.status === "completed";
  const assessmentSelected = run.route?.selected_plugins.includes("aux_diagnosis") || false;
  const assessmentFinished = run.plan.find((node) => node.id === "assessment")?.status === "completed";
  if (
    (!localizationSelected || !localizationFinished || !images.length)
    && (!assessmentSelected || !assessmentFinished)
  ) return null;
  return (
    <div className="plugin-result-stack" aria-label="专业插件结果">
      {localizationSelected && localizationFinished && images.map((image) => (
        <LocalizationResult
          image={image}
          regions={regions.filter((region) => region.image_id === image.id)}
          key={image.id}
        />
      ))}
      {assessmentSelected && assessmentFinished && (
        <section className="assessment-result">
          <header>
            <div><span>辅助评估</span><h3>定性鉴别</h3></div>
            <small>支持程度不是患病概率</small>
          </header>
          {typeof assessment?.summary === "string" && <p className="assessment-summary">{assessment.summary}</p>}
          {differentials.length ? <div className="differential-list">
            {differentials.map((item, index) => (
              <details key={`${item.name}-${index}`} open={index === 0}>
                <summary>
                  <span>{String(index + 1).padStart(2, "0")}</span>
                  <strong>{item.name}</strong>
                  <em className={`support-${item.confidence || "low"}`}>
                    {supportLabel(item.confidence)}
                  </em>
                </summary>
                <div className="differential-evidence">
                  <EvidenceColumn title="支持" items={item.supporting_evidence} empty="暂无明确支持项" />
                  <EvidenceColumn title="反对" items={item.opposing_evidence} empty="暂无明确反对项" />
                  <EvidenceColumn title="仍缺" items={item.missing_evidence} empty="未记录缺失项" />
                </div>
              </details>
            ))}
          </div> : <p className="assessment-summary">当前资料没有形成可负责地展示的候选项；这不是阴性诊断，请结合缺失检查和后续评估继续判断。</p>}
        </section>
      )}
    </div>
  );
}

function LocalizationResult({ image, regions }: { image: AttachmentRecord; regions: LocalizedRegion[] }) {
  const [naturalSize, setNaturalSize] = useState({ width: 0, height: 0 });
  return (
    <section className="localization-result">
      <header>
        <div><span>病灶定位 · {image.original_filename}</span><h3>{regions.length ? "经校验的可疑区域" : "未形成坐标标注"}</h3></div>
        <small>{regions.length} 个区域</small>
      </header>
      {!regions.length && (
        <p className="localization-empty">
          多模态组件已读取上传影像，但没有返回通过坐标校验的区域。系统未补造病灶边界。
        </p>
      )}
      <div className={`localized-image ${regions.length ? "" : "no-regions"}`}>
        <img
          src={`/api/v1/attachments/${image.id}`}
          alt={`${image.original_filename} 的定位预览`}
          onLoad={(event) => setNaturalSize({
            width: event.currentTarget.naturalWidth,
            height: event.currentTarget.naturalHeight
          })}
        />
        {regions.map((region, index) => {
          const box = regionStyle(region, naturalSize);
          return box ? (
            <span className="region-box" style={box} key={`${region.label}-${index}`}>
              <b>{index + 1}</b>
            </span>
          ) : null;
        })}
      </div>
      {regions.length ? (
        <ol className="region-list">
          {regions.map((region, index) => (
            <li key={`${region.label}-detail-${index}`}>
              <Crosshair size={15} />
              <span><strong>{region.label}</strong><small>模型定位把握度：{reliabilityLabel(region.reliability)}</small></span>
            </li>
          ))}
        </ol>
      ) : null}
    </section>
  );
}

function EvidenceColumn({ title, items, empty }: { title: string; items?: string[]; empty: string }) {
  return (
    <div>
      <strong>{title}</strong>
      {items?.length ? <ul>{items.map((item, index) => <li key={`${title}-${index}`}>{item}</li>)}</ul> : <p>{empty}</p>}
    </div>
  );
}

function regionStyle(region: LocalizedRegion, naturalSize: { width: number; height: number }) {
  if (region.coordinate_space === "normalized") {
    return {
      left: `${region.x * 100}%`,
      top: `${region.y * 100}%`,
      width: `${region.width * 100}%`,
      height: `${region.height * 100}%`
    };
  }
  if (!naturalSize.width || !naturalSize.height) return null;
  return {
    left: `${region.x / naturalSize.width * 100}%`,
    top: `${region.y / naturalSize.height * 100}%`,
    width: `${region.width / naturalSize.width * 100}%`,
    height: `${region.height / naturalSize.height * 100}%`
  };
}

function supportLabel(level?: "low" | "medium" | "high") {
  return level === "high" ? "支持较强" : level === "medium" ? "支持中等" : "支持有限";
}

function reliabilityLabel(level?: string) {
  return level === "high" ? "较高" : level === "medium" ? "中等" : level === "low" ? "较低" : "未报告";
}

function InlineCitation({ item, index }: { item: Evidence; index: number }) {
  return (
    <span className="inline-citation" tabIndex={0} aria-label={`来源 ${index}：${item.title}`}>
      [{index}]
      <span className="citation-tooltip" role="tooltip">
        <strong>{item.title}</strong>
        <small>{item.locator || item.source}</small>
        <span>{item.excerpt}</span>
      </span>
    </span>
  );
}

function CitationGroup({ evidence }: { evidence: Evidence[] }) {
  return (
    <details className="citation-group">
      <summary>
        <span className="citation-stack">{evidence.slice(0, 3).map((item) => <i key={item.id}>{item.title.slice(0, 1)}</i>)}</span>
        {evidence.length} 条来源
      </summary>
      <div className="citation-list">
        {evidence.map((item, index) => (
          <article id={`citation-${item.id}`} key={item.id}>
            <span className="evidence-number">{String(index + 1).padStart(2, "0")}</span>
            <div>
              <small>
                {item.source_type === "guideline" ? "指南" : item.source_type === "web" ? "网页" : "资料"}
                {" · "}{item.verified ? "已核验" : "待核验"}
                {" · "}{sourceStatusLabel(item.source_status)}
                {" · "}相关度 {Math.round(item.score * 100)}%
              </small>
              <h3>{item.title}</h3>
              <p>{item.excerpt}</p>
              <p className="citation-provenance">
                {[item.institution, item.published_at, item.version && `版本 ${item.version}`, item.region, item.population && `适用：${item.population}`].filter(Boolean).join(" · ") || "机构、版本与适用范围待核验"}
              </p>
              <footer>
                <span>{item.locator || "未提供定位"}{item.superseded_by ? ` · 替代来源：${item.superseded_by}` : ""}</span>
                {item.source.startsWith("http") && <a href={item.source} target="_blank" rel="noreferrer">打开来源<ExternalLink size={13} /></a>}
              </footer>
            </div>
          </article>
        ))}
      </div>
    </details>
  );
}

function sourceStatusLabel(status: Evidence["source_status"]) {
  return status === "current"
    ? "有效"
    : status === "expired"
      ? "已失效"
      : status === "superseded" ? "已替代" : "状态未知";
}

function MessageActions({
  run,
  answer,
  onRetry,
  onFeedback,
  onDelete,
  onConvert,
  canConvert,
  onSpeak
}: {
  run: Run;
  answer: string;
  onRetry: () => void;
  onFeedback: (value: "up" | "down") => void;
  onDelete: () => void;
  onConvert: () => Promise<void>;
  canConvert: boolean;
  onSpeak: (text: string, signal?: AbortSignal) => Promise<Blob>;
}) {
  const [copied, setCopied] = useState(false);
  const [speechState, setSpeechState] = useState<"idle" | "loading" | "playing">("idle");
  const [speechError, setSpeechError] = useState("");
  const [converting, setConverting] = useState(false);
  const audio = useRef<HTMLAudioElement | null>(null);
  const audioUrl = useRef("");
  const speechGeneration = useRef(0);
  const speechAbort = useRef<AbortController | null>(null);

  useEffect(() => () => {
    speechGeneration.current += 1;
    speechAbort.current?.abort();
    audio.current?.pause();
    if (audioUrl.current) URL.revokeObjectURL(audioUrl.current);
  }, []);

  async function copy() {
    await navigator.clipboard.writeText(answer);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1200);
  }

  async function toggleSpeech() {
    if (speechState !== "idle") {
      speechGeneration.current += 1;
      speechAbort.current?.abort();
      audio.current?.pause();
      if (audio.current) audio.current.currentTime = 0;
      setSpeechState("idle");
      return;
    }
    setSpeechError("");
    setSpeechState("loading");
    const generation = ++speechGeneration.current;
    const controller = new AbortController();
    speechAbort.current = controller;
    await playSpeechSegments(splitForSpeech(answer), 0, generation, controller);
  }

  async function playSpeechSegments(segments: string[], index: number, generation: number, controller: AbortController) {
    if (generation !== speechGeneration.current) return;
    if (index >= segments.length) {
      setSpeechState("idle");
      return;
    }
    try {
      const blob = await onSpeak(segments[index], controller.signal);
      if (generation !== speechGeneration.current) return;
      audio.current?.pause();
      if (audioUrl.current) URL.revokeObjectURL(audioUrl.current);
      const url = URL.createObjectURL(blob);
      audioUrl.current = url;
      const player = new Audio(url);
      audio.current = player;
      player.onended = () => {
        if (generation !== speechGeneration.current) return;
        if (index + 1 < segments.length) setSpeechState("loading");
        void playSpeechSegments(segments, index + 1, generation, controller);
      };
      player.onerror = () => {
        if (generation === speechGeneration.current) {
          setSpeechState("idle");
          setSpeechError("语音播放失败");
        }
      };
      await player.play();
      if (generation === speechGeneration.current) setSpeechState("playing");
    } catch (reason) {
      if (generation !== speechGeneration.current) return;
      setSpeechState("idle");
      setSpeechError(reason instanceof Error ? reason.message : "语音播放失败");
    }
  }

  return (
    <div className="message-actions" aria-label="回答操作">
      <button onClick={copy} aria-label={copied ? "已复制" : "复制回答"}>{copied ? <Check size={15} /> : <Copy size={15} />}</button>
      <button onClick={onRetry} aria-label="重新生成回答"><RefreshCw size={15} /></button>
      <button className={run.feedback === "up" ? "active" : ""} aria-pressed={run.feedback === "up"} onClick={() => onFeedback("up")} aria-label="有帮助"><ThumbsUp size={15} /></button>
      <button className={run.feedback === "down" ? "active" : ""} aria-pressed={run.feedback === "down"} onClick={() => onFeedback("down")} aria-label="没有帮助"><ThumbsDown size={15} /></button>
      <button
        className={speechState !== "idle" ? "active" : ""}
        onClick={toggleSpeech}
        aria-pressed={speechState !== "idle"}
        aria-label={speechState === "loading" ? "取消准备朗读" : speechState === "playing" ? "停止朗读" : "朗读回答"}
        title={speechError || undefined}
      >
        {speechState === "loading" ? <LoadingDots label="正在准备朗读" /> : speechState === "playing" ? <VolumeX size={15} /> : <Volume2 size={15} />}
      </button>
      <details className="answer-more">
        <summary aria-label="更多操作"><MoreHorizontal size={15} /></summary>
        <div className="answer-menu">
          <details className="export-picker">
            <summary><FileDown size={15} />导出</summary>
            <div>
              {(["md", "pdf", "docx", "jpg"] as const).map((format) => (
                <a key={format} href={`/api/v1/runs/${run.id}/export?format=${format}`}><Download size={14} />{format.toUpperCase()}</a>
              ))}
            </div>
          </details>
          {canConvert && (
            <button
              onClick={async () => {
                setConverting(true);
                try {
                  await onConvert();
                } finally {
                  setConverting(false);
                }
              }}
              disabled={converting}
            >
              {converting ? <LoadingDots label="正在转为文档" /> : <PencilLine size={15} />}
              转为文档编辑
            </button>
          )}
          <button className="danger" onClick={onDelete}><Trash2 size={15} />删除此回答</button>
        </div>
      </details>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="empty-state">
      <img src="/static/icons/system_logo.png" alt="" />
      <h2>今天想先处理什么？</h2>
      <p>直接提问，或添加眼底照、OCT、检查资料。</p>
    </div>
  );
}

function groupRuns(runs: Run[]) {
  const ordered = [...runs].sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime());
  const byId = new Map(ordered.map((run) => [run.id, run]));
  const roots = new Map<string, Run[]>();
  for (const run of ordered) {
    let root = run;
    const visited = new Set<string>();
    while (root.input.regenerated_from && byId.has(root.input.regenerated_from) && !visited.has(root.id)) {
      visited.add(root.id);
      root = byId.get(root.input.regenerated_from)!;
    }
    roots.set(root.id, [...(roots.get(root.id) || []), run]);
  }
  return [...roots.values()];
}

function injectCitationLinks(answer: string, evidence: Evidence[]) {
  const known = new Set(evidence.map((item) => item.id));
  return answer.replace(/\[(ev_[0-9a-f]+)\]/g, (marker, id: string) =>
    known.has(id) ? `[${evidence.findIndex((item) => item.id === id) + 1}](#citation-${id})` : marker
  );
}

function uniqueEvidence(items: Evidence[]) {
  const seen = new Set<string>();
  return items.filter((item) => {
    if (seen.has(item.id)) return false;
    seen.add(item.id);
    return true;
  });
}

function splitForSpeech(markdown: string, maxLength = 560) {
  const clean = markdown
    .replace(/\[ev_[0-9a-f]+\]/g, "")
    .replace(/[#>*_`[\]]/g, "")
    .replace(/\s+/g, " ")
    .trim();
  if (!clean) return [];
  const sentences = clean.split(/(?<=[。！？；.!?;])\s*/);
  const segments: string[] = [];
  let current = "";
  for (const sentence of sentences) {
    if (!sentence) continue;
    if ((current + sentence).length <= maxLength) {
      current += sentence;
      continue;
    }
    if (current) segments.push(current);
    for (let offset = 0; offset < sentence.length; offset += maxLength) {
      const part = sentence.slice(offset, offset + maxLength);
      if (part.length === maxLength) segments.push(part);
      else current = part;
    }
    if (sentence.length % maxLength === 0) current = "";
  }
  if (current) segments.push(current);
  return segments;
}

function formatBytes(value: number) {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${Math.round(value / 1024)} KB`;
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

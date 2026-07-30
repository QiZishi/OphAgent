import { useCallback, useEffect, useState } from "react";
import {
  AlertTriangle,
  Check,
  FileUp,
  Gauge,
  MemoryStick,
  RefreshCw,
  Save,
  ShieldCheck,
  Sparkles,
  Trash2
} from "lucide-react";
import { api } from "./api";
import { LoadingDots } from "./components/LoadingDots";
import type {
  Capability,
  KnowledgeSource,
  KnowledgeStatus,
  MemoryRecord,
  SkillRecord
} from "./types";

export type ManagementView = "memories" | "skills" | "knowledge" | "capabilities";

function PageHeader({ eyebrow, title, copy }: { eyebrow: string; title: string; copy: string }) {
  return (
    <header className="management-header">
      <p className="eyebrow">{eyebrow}</p>
      <h1>{title}</h1>
      <p>{copy}</p>
    </header>
  );
}

function Empty({ children }: { children: string }) {
  return <div className="management-empty">{children}</div>;
}

function MemoriesPage() {
  const [records, setRecords] = useState<MemoryRecord[]>([]);
  const [enabled, setEnabled] = useState(true);
  const [editing, setEditing] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    const [items, preference] = await Promise.all([api.memories(), api.memoryPreference()]);
    setRecords(items);
    setEnabled(preference.enabled);
  }, []);
  useEffect(() => { load().catch((reason) => setError(String(reason))); }, [load]);

  async function update(id: string, values: Partial<Pick<MemoryRecord, "content" | "status">>) {
    setBusy(id);
    try {
      const next = await api.updateMemory(id, values);
      setRecords((current) => current.map((item) => item.id === id ? next : item));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "更新失败");
    } finally {
      setBusy("");
    }
  }

  return (
    <>
      <PageHeader eyebrow="LONG-TERM MEMORY" title="长期记忆" copy="只使用已确认记录；候选、冲突、来源和敏感级别始终可见。" />
      <div className="management-toolbar">
        <button className={`toggle-control ${enabled ? "on" : ""}`} onClick={async () => {
          const result = await api.setMemoryPreference(!enabled); setEnabled(result.enabled);
        }}><MemoryStick size={16} />{enabled ? "跨会话记忆已开启" : "跨会话记忆已关闭"}</button>
        <span>{records.filter((item) => item.status === "proposed").length} 条待确认</span>
      </div>
      {error && <p className="management-error">{error}</p>}
      <div className="management-list">
        {records.map((item) => (
          <article className="management-card" key={item.id}>
            <header>
              <span className={`state-pill ${item.status}`}>{item.status}</span>
              <b>{item.category}</b>
              <small>{new Date(item.updated_at).toLocaleString("zh-CN")}</small>
            </header>
            {editing[item.id] !== undefined ? (
              <textarea value={editing[item.id]} onChange={(event) => setEditing((value) => ({ ...value, [item.id]: event.target.value }))} />
            ) : <p>{item.content}</p>}
            <div className="provenance">来源：{item.source} · {item.sensitivity}</div>
            {item.conflicts_with.length > 0 && <div className="conflict-note"><AlertTriangle size={14} />与 {item.conflicts_with.length} 条记录冲突，确认前请核对。</div>}
            <footer>
              {item.status === "proposed" && <>
                <button onClick={() => update(item.id, { status: "confirmed" })}><Check size={14} />确认</button>
                <button onClick={() => update(item.id, { status: "rejected" })}>拒绝</button>
              </>}
              {editing[item.id] !== undefined ? (
                <button onClick={async () => { await update(item.id, { content: editing[item.id] }); setEditing((value) => { const next = { ...value }; delete next[item.id]; return next; }); }}><Save size={14} />保存</button>
              ) : <button onClick={() => setEditing((value) => ({ ...value, [item.id]: item.content }))}>修改</button>}
              <button className="danger-action" disabled={busy === item.id} onClick={async () => {
                await api.deleteMemory(item.id); setRecords((current) => current.filter((record) => record.id !== item.id));
              }}><Trash2 size={14} />删除</button>
            </footer>
          </article>
        ))}
        {!records.length && <Empty>还没有长期记忆。运行中提取的用药和过敏只会先进入待确认区。</Empty>}
      </div>
    </>
  );
}

function SkillsPage({ canManageSystem }: { canManageSystem: boolean }) {
  const [skills, setSkills] = useState<SkillRecord[]>([]);
  const [markdown, setMarkdown] = useState("");
  const [error, setError] = useState("");
  const load = useCallback(() => api.skills().then(setSkills), []);
  useEffect(() => { load().catch((reason) => setError(String(reason))); }, [load]);
  return (
    <>
      <PageHeader eyebrow="CONTROLLED SKILLS" title="Skill 注册表" copy="候选 Skill 先隔离，再校验结构、依赖、安全规则和内容 checksum。" />
      {error && <p className="management-error">{error}</p>}
      {canManageSystem ? (
        <details className="import-panel">
          <summary><Sparkles size={15} />导入候选 SKILL.md</summary>
          <textarea value={markdown} onChange={(event) => setMarkdown(event.target.value)} placeholder="粘贴含 frontmatter 的完整 SKILL.md" />
          <button onClick={async () => {
            try { await api.importSkill(markdown); setMarkdown(""); await load(); }
            catch (reason) { setError(reason instanceof Error ? reason.message : "导入失败"); }
          }}>进入候选隔离区</button>
        </details>
      ) : (
        <p className="provenance">系统级 Skill 由管理员维护；你可以查看当前可用能力，并在对话中选择已启用 Skill。</p>
      )}
      <div className="management-grid">
        {skills.map((skill) => (
          <article className="management-card" key={skill.id}>
            <header><span className={`state-pill ${skill.status}`}>{skill.status}</span><b>{skill.id}</b><small>v{skill.version}</small></header>
            <p>{skill.description}</p>
            <div className="provenance">风险：{skill.risk_level} · 依赖：{skill.dependencies.length || "无"}</div>
            {Boolean(skill.evaluation.passed) && <div className="pass-note"><ShieldCheck size={14} />当前内容已通过门禁</div>}
            {canManageSystem && <footer>
              {skill.status === "candidate" && <button onClick={async () => { await api.validateSkill(skill.id); await load(); }}><Gauge size={14} />执行评测</button>}
              {skill.status === "validated" && <button onClick={async () => { await api.updateSkill(skill.id, "enabled"); await load(); }}><Check size={14} />启用</button>}
              {skill.status === "enabled" && <button onClick={async () => { await api.updateSkill(skill.id, "disabled"); await load(); }}>停用</button>}
              {skill.status === "disabled" && <button onClick={async () => { await api.updateSkill(skill.id, "enabled"); await load(); }}>重新启用</button>}
            </footer>}
          </article>
        ))}
      </div>
    </>
  );
}

function KnowledgePage({
  canManageSystem,
  userId
}: {
  canManageSystem: boolean;
  userId: number;
}) {
  const [status, setStatus] = useState<KnowledgeStatus | null>(null);
  const [sources, setSources] = useState<KnowledgeSource[]>([]);
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    const [nextStatus, nextSources] = await Promise.all([api.knowledgeStatus(), api.knowledgeSources()]);
    setStatus(nextStatus); setSources(nextSources);
  }, []);
  useEffect(() => { load().catch((reason) => setError(String(reason))); }, [load]);
  return (
    <>
      <PageHeader eyebrow="GUIDELINE GOVERNANCE" title="知识库与来源" copy="段落、页图、版本和失效状态共同进入检索；用户上传不会自动晋升为正式指南。" />
      {status && <div className="metric-strip">
        <span><b>{status.documents}</b>来源</span><span><b>{status.chunks}</b>片段</span>
        <span><b>{status.vectors}</b>向量</span><span><b>{status.page_visuals}</b>页图</span>
        <span><b>{status.graph_edges}</b>图谱边</span>
      </div>}
      <div className="management-toolbar">
        <label className="file-action"><FileUp size={15} />导入 md / txt / pdf<input hidden type="file" accept=".md,.txt,.pdf" onChange={async (event) => {
          const file = event.target.files?.[0]; if (file) { await api.importKnowledge(file); await load(); }
        }} /></label>
        {canManageSystem && <button onClick={async () => { await api.rebuildKnowledge(true); await load(); }} disabled={status?.status === "building"}>{status?.status === "building" ? <LoadingDots label="重建知识索引" /> : <RefreshCw size={15} />}重建向量索引</button>}
      </div>
      {error && <p className="management-error">{error}</p>}
      <div className="source-table">
        <div className="source-row source-head"><span>来源</span><span>机构 / 版本</span><span>状态</span></div>
        {sources.slice(0, 100).map((source) => (
          <div className="source-row" key={source.id}>
            <span><b>{source.title}</b><small>{source.source_type} · {source.verified ? "已登记" : "待核验"}</small></span>
            <span>{source.institution || "机构待核验"}<small>{source.version || source.published_at || "版本未知"}</small></span>
            {(canManageSystem || source.imported_by === userId) ? (
              <select value={source.status} onChange={async (event) => {
                const next = await api.updateKnowledgeSource(source.id, { status: event.target.value as KnowledgeSource["status"] });
                setSources((current) => current.map((item) => item.id === source.id ? next : item));
              }}><option value="unknown">未知</option><option value="current">有效</option><option value="expired">失效</option><option value="superseded">已替代</option></select>
            ) : <span>{source.status}</span>}
          </div>
        ))}
      </div>
    </>
  );
}

function CapabilitiesPage({ initial }: { initial: Capability[] }) {
  const [items, setItems] = useState(initial);
  useEffect(() => { api.capabilities().then(setItems); }, []);
  return (
    <>
      <PageHeader eyebrow="REAL CAPABILITIES" title="能力健康状态" copy="这里只报告真实配置和连接状态；unavailable 不会回退到预设医学答案。" />
      <div className="management-grid capability-grid">
        {items.map((item) => (
          <article className="capability-card" key={item.id}>
            <span className={`capability-light ${item.status}`} />
            <div><b>{item.id}</b><small>{item.provider || item.model || "本地能力"}</small></div>
            <strong>{item.status}</strong>
            <p>{item.detail || (item.configured ? "已配置" : "未配置")}</p>
          </article>
        ))}
      </div>
    </>
  );
}

export function ManagementViews({
  view,
  capabilities,
  canManageSystem,
  userId
}: {
  view: ManagementView;
  capabilities: Capability[];
  canManageSystem: boolean;
  userId: number;
}) {
  return (
    <section className="management-page">
      {view === "memories" && <MemoriesPage />}
      {view === "skills" && <SkillsPage canManageSystem={canManageSystem} />}
      {view === "knowledge" && <KnowledgePage canManageSystem={canManageSystem} userId={userId} />}
      {view === "capabilities" && <CapabilitiesPage initial={capabilities} />}
    </section>
  );
}

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Brain,
  Database,
  File,
  FileAudio,
  FileImage,
  FolderPlus,
  Library,
  Plug,
  Plus,
  Settings,
  Sparkles,
  Trash2
} from "lucide-react";
import { api } from "./api";
import { ManagementViews, type ManagementView } from "./ManagementViews";
import { PLUGINS } from "./features/plugins";
import { LoadingDots } from "./components/LoadingDots";
import type { Artifact, AttachmentRecord, Capability, Conversation, EvolutionStatus, Project, ProviderConfig, ProviderId } from "./types";
import type { WorkspaceView } from "./components/Sidebar";

interface WorkspaceViewsProps {
  view: Exclude<WorkspaceView, "chat">;
  capabilities: Capability[];
  onNavigate: (view: WorkspaceView) => void;
  onArtifact: (artifact: Artifact) => void;
  conversations: Conversation[];
  onConversationProject: (conversationId: number, projectId: number | null) => Promise<void>;
  onSignedOut: () => void;
}

const MANAGED = new Set<WorkspaceView>(["memories", "skills", "knowledge"]);

export function WorkspaceViews(props: WorkspaceViewsProps) {
  if (MANAGED.has(props.view)) {
    return (
      <ManagementViews
        view={props.view as ManagementView}
        capabilities={props.capabilities}
      />
    );
  }
  if (props.view === "projects") {
    return (
      <ProjectsPage
        conversations={props.conversations}
        onConversationProject={props.onConversationProject}
      />
    );
  }
  if (props.view === "files") return <FilesPage onArtifact={props.onArtifact} />;
  if (props.view === "plugins") return <PluginsPage />;
  return (
    <SettingsPage
      capabilities={props.capabilities}
      onNavigate={props.onNavigate}
      onSignedOut={props.onSignedOut}
    />
  );
}

function WorkspaceHeader({ kicker, title, copy }: { kicker: string; title: string; copy: string }) {
  return (
    <header className="management-header">
      <p className="eyebrow">{kicker}</p>
      <h1>{title}</h1>
      <p>{copy}</p>
    </header>
  );
}

function ProjectsPage({
  conversations,
  onConversationProject
}: {
  conversations: Conversation[];
  onConversationProject: (conversationId: number, projectId: number | null) => Promise<void>;
}) {
  const [items, setItems] = useState<Project[]>([]);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);
  const [selectedConversation, setSelectedConversation] = useState("");
  const [selectedProject, setSelectedProject] = useState("");
  const [error, setError] = useState("");
  const load = useCallback(() => api.projects().then(setItems), []);
  useEffect(() => { load().catch((reason) => setError(String(reason))); }, [load]);

  async function createProject() {
    if (!name.trim()) return;
    setBusy(true);
    setError("");
    try {
      const created = await api.createProject(name.trim(), description.trim());
      setItems((current) => [created, ...current]);
      setName("");
      setDescription("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "项目创建失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="management-page">
      <WorkspaceHeader kicker="工作上下文" title="项目" copy="把相关对话、文件和诊疗目标放在同一上下文中。项目不会改变医疗安全门禁。" />
      <section className="project-create" aria-label="创建项目">
        <FolderPlus size={22} />
        <div>
          <label>项目名称<input value={name} maxLength={80} onChange={(event) => setName(event.target.value)} placeholder="例如：黄斑病变随访资料" /></label>
          <label>说明<textarea value={description} maxLength={500} onChange={(event) => setDescription(event.target.value)} placeholder="记录这个项目要解决的问题" /></label>
        </div>
        <button onClick={createProject} disabled={!name.trim() || busy}>
          {busy ? <LoadingDots label="创建项目" /> : <Plus size={16} />}创建
        </button>
      </section>
      <section className="project-organizer" aria-label="整理对话到项目">
        <div>
          <strong>整理已有对话</strong>
          <small>选择“无项目”可把对话移回普通列表。</small>
        </div>
        <select value={selectedConversation} onChange={(event) => setSelectedConversation(event.target.value)}>
          <option value="">选择对话</option>
          {conversations.map((conversation) => (
            <option key={conversation.id} value={conversation.id}>{conversation.title}</option>
          ))}
        </select>
        <select value={selectedProject} onChange={(event) => setSelectedProject(event.target.value)}>
          <option value="">无项目</option>
          {items.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}
        </select>
        <button
          disabled={!selectedConversation || busy}
          onClick={async () => {
            setBusy(true);
            try {
              await onConversationProject(
                Number(selectedConversation),
                selectedProject ? Number(selectedProject) : null,
              );
              await load();
            } catch (reason) {
              setError(reason instanceof Error ? reason.message : "对话归档失败");
            } finally {
              setBusy(false);
            }
          }}
        >保存归属</button>
      </section>
      {error && <p className="management-error" role="alert">{error}</p>}
      <div className="project-grid">
        {items.map((project) => (
          <article className="project-card" key={project.id}>
            <span className="project-color" style={{ background: project.color }} />
            <div>
              <h2>{project.name}</h2>
              <p>{project.description || "尚未添加说明"}</p>
              <small>{project.conversation_count} 个对话 · {new Date(project.updated_at).toLocaleDateString("zh-CN")}</small>
            </div>
            <button
              className="icon-button danger-action"
              aria-label={`删除项目 ${project.name}`}
              onClick={async () => {
                if (!window.confirm(`删除项目“${project.name}”？项目中的对话不会被删除。`)) return;
                await api.deleteProject(project.id);
                setItems((current) => current.filter((item) => item.id !== project.id));
              }}
            ><Trash2 size={16} /></button>
          </article>
        ))}
        {!items.length && <div className="management-empty">还没有项目。创建项目后可逐步归集相关对话和资料。</div>}
      </div>
    </section>
  );
}

function FilesPage({ onArtifact }: { onArtifact: (artifact: Artifact) => void }) {
  const [attachments, setAttachments] = useState<AttachmentRecord[]>([]);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    const [nextAttachments, nextArtifacts] = await Promise.all([api.attachments(), api.artifacts()]);
    setAttachments(nextAttachments);
    setArtifacts(nextArtifacts);
  }, []);
  useEffect(() => { load().catch((reason) => setError(String(reason))); }, [load]);
  const totalSize = useMemo(() => attachments.reduce((sum, item) => sum + item.size, 0), [attachments]);

  return (
    <section className="management-page">
      <WorkspaceHeader kicker="私人资料" title="文件库" copy="上传资料通过鉴权接口读取；对话删除时会按关联关系清理文件与产物。" />
      <div className="metric-strip">
        <span><b>{attachments.length}</b>上传文件</span>
        <span><b>{artifacts.length}</b>生成产物</span>
        <span><b>{formatBytes(totalSize)}</b>占用空间</span>
      </div>
      {error && <p className="management-error" role="alert">{error}</p>}
      <section className="library-section">
        <h2>上传文件</h2>
        <div className="file-list">
          {attachments.map((item) => (
            <article className="file-row" key={item.id}>
              {item.kind === "image" ? <FileImage size={20} /> : item.kind === "audio" ? <FileAudio size={20} /> : <File size={20} />}
              <div><strong>{item.original_filename}</strong><small>{item.mime_type} · {formatBytes(item.size)}</small></div>
              <a href={`/api/v1/attachments/${item.id}`} target="_blank" rel="noreferrer">打开</a>
              <button
                className="icon-button"
                aria-label={`删除 ${item.original_filename}`}
                onClick={async () => {
                  if (!window.confirm(`删除“${item.original_filename}”？`)) return;
                  await api.deleteAttachment(item.id);
                  setAttachments((current) => current.filter((candidate) => candidate.id !== item.id));
                }}
              ><Trash2 size={15} /></button>
            </article>
          ))}
          {!attachments.length && <div className="management-empty">还没有上传文件。可在对话输入框中添加影像、文档或音频。</div>}
        </div>
      </section>
      <section className="library-section">
        <h2>生成产物</h2>
        <div className="artifact-grid">
          {artifacts.map((artifact) => (
            <button className="artifact-card" key={artifact.id} onClick={() => onArtifact(artifact)}>
              <span>{artifact.type === "report" ? "报告" : "产物"}</span>
              <strong>{artifact.title}</strong>
              <small>{artifact.mime_type} · 打开预览</small>
            </button>
          ))}
          {!artifacts.length && <div className="management-empty">对话中生成的报告和可下载文件会出现在这里。</div>}
        </div>
      </section>
    </section>
  );
}

function PluginsPage() {
  return (
    <section className="management-page">
      <WorkspaceHeader kicker="按需调用" title="插件" copy="OphAgent 会自动选择能力；也可以在输入框中用 @ 明确指定一个或多个插件。" />
      <div className="plugin-directory">
        {PLUGINS.map(({ id, label, description, icon: Icon }) => (
          <article key={id}>
            <span><Icon size={20} /></span>
            <div><h2>{label}</h2><p>{description}</p><code>@{label}</code></div>
            <strong>可用</strong>
          </article>
        ))}
      </div>
    </section>
  );
}

function SettingsPage({
  capabilities,
  onNavigate,
  onSignedOut
}: {
  capabilities: Capability[];
  onNavigate: (view: WorkspaceView) => void;
  onSignedOut: () => void;
}) {
  const ready = capabilities.filter((item) => item.status === "ready").length;
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [passwordError, setPasswordError] = useState("");
  const [passwordBusy, setPasswordBusy] = useState(false);
  const [providerConfig, setProviderConfig] = useState<ProviderConfig | null>(null);
  const [providerBusy, setProviderBusy] = useState(false);
  const [providerNotice, setProviderNotice] = useState("");
  const [evolution, setEvolution] = useState<EvolutionStatus | null>(null);
  useEffect(() => {
    api.providerConfig()
      .then(setProviderConfig)
      .catch((reason) => setProviderNotice(reason instanceof Error ? reason.message : "供应商配置加载失败"));
    api.evolutionStatus().then(setEvolution).catch(() => setEvolution(null));
  }, []);
  return (
    <section className="management-page">
      <WorkspaceHeader kicker="账户与能力" title="设置" copy="管理个人记忆、知识来源、技能与外部能力。所有变更都会保留状态与来源。" />
      <div className="settings-grid">
        <button onClick={() => onNavigate("memories")}><Brain size={20} /><span><strong>记忆</strong><small>确认、修订或删除跨会话信息</small></span></button>
        <button onClick={() => onNavigate("knowledge")}><Database size={20} /><span><strong>知识库</strong><small>管理来源、版本与索引状态</small></span></button>
        <button onClick={() => onNavigate("skills")}><Sparkles size={20} /><span><strong>技能</strong><small>导入、验证和启停 SKILL.md</small></span></button>
        <button onClick={() => onNavigate("plugins")}><Plug size={20} /><span><strong>插件</strong><small>查看 OphAgent 可调用的专业能力</small></span></button>
        <button onClick={() => onNavigate("files")}><Library size={20} /><span><strong>文件与产物</strong><small>查看私人上传与生成内容</small></span></button>
        <div className="settings-status"><Settings size={20} /><span><strong>能力状态</strong><small>{ready}/{capabilities.length || "—"} 项最近验证可用</small></span></div>
      </div>
      <section className="evolution-panel" aria-label="持续改进状态">
        <header>
          <span><Sparkles size={20} /></span>
          <div>
            <strong>受控持续改进</strong>
            <small>反馈只用于有界记忆排序和生成离线候选；生产代码、医疗事实与技能不会被自动改写。</small>
          </div>
          <b>{evolution?.production_mutation === "disabled" ? "生产自动变更：关闭" : "读取中"}</b>
        </header>
        {evolution ? (
          <>
            <div className="evolution-metrics">
              <span><b>{evolution.observed_run_count}</b><small>已观察任务</small></span>
              <span><b>{evolution.feedback_count}</b><small>有效反馈</small></span>
              <span><b>{evolution.ready_candidate_count}</b><small>待离线评测候选</small></span>
            </div>
            <div className="evolution-boundaries">
              <p><strong>Memory</strong>{evolution.memory_adaptation}</p>
              <p><strong>Skill</strong>{evolution.skill_adaptation}</p>
              <p><strong>晋升</strong>同病例配对评测、全切片非劣、高风险单病例不降分、成本与延迟门禁，并绑定人工审批和候选 commit。</p>
            </div>
            {!!evolution.candidates.length && (
              <details className="evolution-candidates">
                <summary>查看改进候选（{evolution.candidates.length}）</summary>
                {evolution.candidates.map((candidate) => (
                  <article key={candidate.id}>
                    <span><strong>{candidate.kind}</strong><code>{candidate.target}</code></span>
                    <small>{candidate.trigger} · 样本 {candidate.sample_size} · 负反馈率 {Math.round(candidate.negative_rate * 100)}%</small>
                  </article>
                ))}
              </details>
            )}
          </>
        ) : <div className="management-empty">正在读取持续改进状态…</div>}
      </section>
      <section className="provider-settings">
        <header>
          <div>
            <strong>模型与外部能力供应商</strong>
            <small>不填写时继续使用系统默认。Agent、Sub-agent 以及自定义语音/向量模型必须兼容 OpenAI API 协议；密钥保存后不会再次回显。</small>
          </div>
          <button
            disabled={!providerConfig || providerBusy}
            onClick={async () => {
              if (!providerConfig) return;
              setProviderBusy(true);
              setProviderNotice("");
              try {
                setProviderConfig(await api.saveProviderConfig(providerConfig));
                setProviderNotice("供应商配置已保存，新任务将使用最新设置。");
              } catch (reason) {
                setProviderNotice(reason instanceof Error ? reason.message : "供应商配置保存失败");
              } finally {
                setProviderBusy(false);
              }
            }}
          >{providerBusy ? "保存中…" : "保存配置"}</button>
        </header>
        {providerConfig ? (
          <div className="provider-grid">
            {(Object.keys(PROVIDER_LABELS) as ProviderId[]).map((id) => {
              const value = providerConfig.providers[id];
              const definition = PROVIDER_LABELS[id];
              return (
                <article className="provider-card" key={id}>
                  <div className="provider-card-heading">
                    <span><strong>{definition.label}</strong><small>{definition.description}</small></span>
                    <label className="provider-mode">
                      <input
                        type="checkbox"
                        checked={!value.use_default}
                        onChange={(event) => updateProvider(setProviderConfig, id, { use_default: !event.target.checked })}
                      />
                      使用个人配置
                    </label>
                  </div>
                  <div className={value.use_default ? "provider-fields disabled" : "provider-fields"}>
                    {id === "mineru" ? (
                      <label>固定 URL<input value={providerConfig.mineru_url} disabled /></label>
                    ) : (
                      <label>URL<input value={value.url} disabled={value.use_default} placeholder={value.default_url || "https://…/v1"} onChange={(event) => updateProvider(setProviderConfig, id, { url: event.target.value })} /></label>
                    )}
                    {definition.hasModel && (
                      <label>模型名<input value={value.model} disabled={value.use_default} placeholder={value.default_model || "模型标识"} onChange={(event) => updateProvider(setProviderConfig, id, { model: event.target.value })} /></label>
                    )}
                    <label>API 密钥<input type="password" value={value.api_key || ""} disabled={value.use_default} placeholder={value.has_api_key ? "已保存；留空保持不变" : "输入个人 API 密钥"} onChange={(event) => updateProvider(setProviderConfig, id, { api_key: event.target.value })} /></label>
                  </div>
                  <p>{value.use_default ? `当前：系统默认${value.default_configured ? "（已配置）" : "（未配置）"}` : "当前：个人配置"}</p>
                </article>
              );
            })}
          </div>
        ) : <div className="management-empty">正在读取供应商配置…</div>}
        {providerNotice && <p className="provider-notice" role="status">{providerNotice}</p>}
      </section>
      <section className="password-panel">
        <div>
          <strong>修改密码</strong>
          <small>修改后会撤销该账号的全部登录会话，需要重新登录。</small>
        </div>
        <label>当前密码<input type="password" autoComplete="current-password" value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} /></label>
        <label>新密码<input type="password" minLength={8} autoComplete="new-password" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} /></label>
        <button
          disabled={passwordBusy || !currentPassword || newPassword.length < 8}
          onClick={async () => {
            setPasswordBusy(true);
            setPasswordError("");
            try {
              await api.changePassword(currentPassword, newPassword);
              onSignedOut();
            } catch (reason) {
              setPasswordError(reason instanceof Error ? reason.message : "密码修改失败");
            } finally {
              setPasswordBusy(false);
            }
          }}
        >{passwordBusy ? "正在更新…" : "更新并退出"}</button>
        {passwordError && <p role="alert">{passwordError}</p>}
      </section>
      <ManagementViews view="capabilities" capabilities={capabilities} />
    </section>
  );
}

const PROVIDER_LABELS: Record<ProviderId, { label: string; description: string; hasModel: boolean }> = {
  agent: { label: "Agent 模型", description: "负责规划、整合与最终回答", hasModel: true },
  sub_agent: { label: "Sub-agent 模型", description: "负责多模态和专科子任务", hasModel: true },
  asr: { label: "ASR", description: "语音转文字", hasModel: true },
  tts: { label: "TTS", description: "回答语音合成", hasModel: true },
  embedding: { label: "Embedding", description: "知识库向量编码", hasModel: true },
  reranker: { label: "Reranker", description: "检索结果重排序", hasModel: true },
  search: { label: "联网搜索", description: "AnySearch 兼容搜索接口", hasModel: false },
  mineru: { label: "MinerU 文档解析", description: "URL 由系统固定，只配置官方 Token", hasModel: false }
};

function updateProvider(
  setter: React.Dispatch<React.SetStateAction<ProviderConfig | null>>,
  id: ProviderId,
  patch: Partial<ProviderConfig["providers"][ProviderId]>
) {
  setter((current) => current ? {
    ...current,
    providers: {
      ...current.providers,
      [id]: { ...current.providers[id], ...patch }
    }
  } : current);
}

function formatBytes(value: number) {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${Math.round(value / 1024)} KB`;
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

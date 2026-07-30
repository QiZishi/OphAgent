import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { LogIn, Menu, PanelRight, ShieldAlert } from "lucide-react";
import { api } from "./api";
import { Composer } from "./components/Composer";
import { ConversationThread } from "./components/ConversationThread";
import { DetailDrawer } from "./components/DetailDrawer";
import { Sidebar, type WorkspaceView } from "./components/Sidebar";
import { WorkspaceViews } from "./WorkspaceViews";
import { LoadingDots } from "./components/LoadingDots";
import type {
  Artifact,
  AttachmentRecord,
  Capability,
  Conversation,
  LocalAttachment,
  PluginId,
  Run,
  RunEvent,
  SkillRecord,
  UserProfile
} from "./types";

const DEFAULT_SIDEBAR = 260;
const TERMINAL = new Set(["completed", "completed_with_warnings", "interrupted", "failed", "cancelled"]);
const EVENT_TYPES = [
  "run.created", "safety.alert", "plan.created", "plan.updated", "agent.started",
  "agent.completed", "tool.started", "tool.completed", "tool.failed", "retrieval.result",
  "artifact.created", "context.prepared", "memory.recalled", "memory.proposed", "answer.delta", "answer.completed",
  "run.question", "run.approval_required", "run.interrupted", "run.failed", "run.cancelled", "run.completed"
];

function Login({ onSuccess }: { onSuccess: (profile: UserProfile) => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [register, setRegister] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api.login(username, password, register);
      onSuccess(await api.me());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "无法登录");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="login-shell">
      <section className="login-panel">
        <img className="login-logo" src="/static/icons/system_logo.png" alt="OphAgent" />
        <div className="login-copy">
          <h1>欢迎使用 OphAgent</h1>
          <p>在一个连续对话中整理症状、复核影像与查找指南证据。</p>
        </div>
        <form onSubmit={submit}>
          <label>用户名<input value={username} onChange={(event) => setUsername(event.target.value)} required autoComplete="username" /></label>
          <label>密码<input value={password} onChange={(event) => setPassword(event.target.value)} required minLength={register ? 8 : 1} type="password" autoComplete={register ? "new-password" : "current-password"} /></label>
          {error && <p className="form-error" role="alert">{error}</p>}
          <button className="login-submit" disabled={busy}>
            {busy ? <LoadingDots label="登录中" /> : <LogIn size={17} />}
            {register ? "创建账号" : "登录"}
          </button>
        </form>
        <button className="login-switch" onClick={() => { setRegister((value) => !value); setError(""); }}>
          {register ? "已有账号？登录" : "还没有账号？创建一个"}
        </button>
        <p className="login-disclaimer">研究级诊疗增强，不替代医生诊断与急诊评估。</p>
      </section>
      <aside className="login-aside" aria-hidden="true">
        <div className="clinical-line" />
        <div className="login-aside-note">
          <strong>眼科资料工作区</strong>
          <span>对话、影像、检查报告与引用来源集中管理。</span>
        </div>
      </aside>
    </main>
  );
}

export default function App() {
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [workspaceView, setWorkspaceView] = useState<WorkspaceView>("chat");
  const [capabilities, setCapabilities] = useState<Capability[]>([]);
  const [checkingAuth, setCheckingAuth] = useState(true);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [active, setActive] = useState<Conversation | null>(null);
  const [eventsByRun, setEventsByRun] = useState<Record<string, RunEvent[]>>({});
  const [artifactsByRun, setArtifactsByRun] = useState<Record<string, Artifact[]>>({});
  const [draft, setDraft] = useState("");
  const [attachments, setAttachments] = useState<LocalAttachment[]>([]);
  const [plugins, setPlugins] = useState<PluginId[]>([]);
  const [skills, setSkills] = useState<SkillRecord[]>([]);
  const [selectedSkills, setSelectedSkills] = useState<string[]>([]);
  const [attachmentsById, setAttachmentsById] = useState<Record<string, AttachmentRecord>>({});
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [connectionNote, setConnectionNote] = useState("");
  const [search, setSearch] = useState("");
  const [sidebarWidth, setSidebarWidth] = useState(() => Number(localStorage.getItem("ophagent.sidebar.width")) || DEFAULT_SIDEBAR);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => localStorage.getItem("ophagent.sidebar.collapsed") === "true");
  const [mobileNav, setMobileNav] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerArtifact, setDrawerArtifact] = useState<Artifact | null>(null);
  const sourceRef = useRef<EventSource | null>(null);
  const reconnectRef = useRef<number | null>(null);
  const cursorRef = useRef<Record<string, number>>({});
  const activeIdRef = useRef<number | null>(null);

  const loadConversations = useCallback(async () => {
    const page = await api.conversations();
    setConversations(page.items);
    return page.items;
  }, []);

  useEffect(() => {
    api.me()
      .then(async (nextProfile) => {
        setProfile(nextProfile);
        const [items, nextCapabilities, nextSkills, storedAttachments] = await Promise.all([
          loadConversations(),
          api.capabilities().catch(() => []),
          api.skills().catch(() => []),
          api.attachments().catch(() => [])
        ]);
        setCapabilities(nextCapabilities);
        setSkills(nextSkills);
        setAttachmentsById(Object.fromEntries(storedAttachments.map((item) => [item.id, item])));
        if (items[0]) await openConversation(items[0].id);
      })
      .catch(() => setProfile(null))
      .finally(() => setCheckingAuth(false));
    // openConversation intentionally uses stable API functions only during bootstrap.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadConversations]);

  useEffect(() => () => {
    sourceRef.current?.close();
    if (reconnectRef.current) window.clearTimeout(reconnectRef.current);
  }, []);

  useEffect(() => {
    localStorage.setItem("ophagent.sidebar.width", String(sidebarWidth));
  }, [sidebarWidth]);

  useEffect(() => {
    if (!drawerOpen) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setDrawerOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [drawerOpen]);

  async function openConversation(id: number) {
    sourceRef.current?.close();
    if (reconnectRef.current) window.clearTimeout(reconnectRef.current);
    activeIdRef.current = id;
    setSubmitting(false);
    setError("");
    setConnectionNote("");
    setMobileNav(false);
    setWorkspaceView("chat");
    const detail = await api.conversation(id);
    setActive(detail);
    setConversations((current) => current.map((item) => item.id === id ? { ...item, ...detail } : item));
    const runs = detail.runs || [];
    const histories = await Promise.all(runs.map(async (run) => ({
      run,
      events: await api.runEvents(run.id),
      artifacts: await api.artifacts(run.id)
    })));
    const nextEvents: Record<string, RunEvent[]> = {};
    const nextArtifacts: Record<string, Artifact[]> = {};
    histories.forEach(({ run, events, artifacts }) => {
      nextEvents[run.id] = events;
      nextArtifacts[run.id] = artifacts;
      cursorRef.current[run.id] = events.at(-1)?.sequence || 0;
    });
    setEventsByRun((current) => ({ ...current, ...nextEvents }));
    setArtifactsByRun((current) => ({ ...current, ...nextArtifacts }));
    const running = [...runs].reverse().find((run) => !TERMINAL.has(run.status));
    if (running) void followRun(running, id);
  }

  function updateRun(run: Run, conversationId: number) {
    if (activeIdRef.current !== conversationId) return;
    setActive((current) => current ? {
      ...current,
      runs: [...(current.runs || []).filter((item) => item.id !== run.id), run]
    } : current);
  }

  async function followRun(run: Run, conversationId: number, retry = 0) {
    sourceRef.current?.close();
    if (TERMINAL.has(run.status) || activeIdRef.current !== conversationId) return;
    let cursor = cursorRef.current[run.id] || 0;
    // The server can emit run.created/context.prepared before EventSource has
    // finished registering named listeners. Backfill first, then stream only
    // events after the durable cursor so early process information is never lost.
    try {
      const backlog = await api.runEvents(run.id, cursor);
      if (activeIdRef.current !== conversationId) return;
      if (backlog.length) {
        setEventsByRun((current) => {
          const previous = current[run.id] || [];
          const known = new Set(previous.map((item) => item.sequence));
          return {
            ...current,
            [run.id]: [
              ...previous,
              ...backlog.filter((item) => !known.has(item.sequence))
            ].sort((left, right) => left.sequence - right.sequence)
          };
        });
        cursor = backlog.at(-1)?.sequence || cursor;
        cursorRef.current[run.id] = cursor;
      }
    } catch {
      // SSE remains authoritative; its reconnect path will retry the backfill.
    }
    if (activeIdRef.current !== conversationId) return;
    const source = new EventSource(`/api/v1/runs/${run.id}/events/stream?after_sequence=${cursor}`, { withCredentials: true });
    sourceRef.current = source;
    setConnectionNote("");
    EVENT_TYPES.forEach((type) => {
      source.addEventListener(type, async (message) => {
        if (activeIdRef.current !== conversationId) return;
        const event = JSON.parse((message as MessageEvent).data) as RunEvent;
        cursorRef.current[run.id] = Math.max(cursorRef.current[run.id] || 0, event.sequence);
        setEventsByRun((current) => {
          const previous = current[run.id] || [];
          return previous.some((item) => item.sequence === event.sequence)
            ? current
            : { ...current, [run.id]: [...previous, event] };
        });
        if (["agent.completed", "tool.failed", "run.question", "run.completed", "run.interrupted", "run.failed", "run.cancelled"].includes(type)) {
          const updated = await api.getRun(run.id);
          updateRun(updated, conversationId);
          if (updated.status === "waiting_for_user") {
            setSubmitting(false);
          }
          if (TERMINAL.has(updated.status)) {
            source.close();
            setSubmitting(false);
            setConnectionNote("");
            const artifacts = await api.artifacts(run.id);
            setArtifactsByRun((current) => ({ ...current, [run.id]: artifacts }));
          }
        }
      });
    });
    source.onerror = async () => {
      source.close();
      if (activeIdRef.current !== conversationId) return;
      setConnectionNote("连接中断，正在恢复进度…");
      try {
        const updated = await api.getRun(run.id);
        updateRun(updated, conversationId);
        if (TERMINAL.has(updated.status)) {
          setConnectionNote("");
          setSubmitting(false);
          return;
        }
      } catch {
        // The backoff below keeps the server run authoritative.
      }
      reconnectRef.current = window.setTimeout(
        () => { void followRun(run, conversationId, Math.min(retry + 1, 6)); },
        Math.min(8000, 600 * 2 ** retry)
      );
    };
  }

  async function newConversation() {
    sourceRef.current?.close();
    if (reconnectRef.current) window.clearTimeout(reconnectRef.current);
    const created = await api.createConversation();
    setConversations((current) => [created, ...current]);
    activeIdRef.current = created.id;
    setActive({ ...created, runs: [], messages: [] });
    setEventsByRun({});
    setArtifactsByRun({});
    attachments.forEach((item) => item.preview && URL.revokeObjectURL(item.preview));
    setAttachments([]);
    setDraft("");
    setPlugins([]);
    setSelectedSkills([]);
    setSubmitting(false);
    setError("");
    setConnectionNote("");
    setMobileNav(false);
    setWorkspaceView("chat");
  }

  function addFiles(files: File[]) {
    const additions = files.map((file) => ({
      key: crypto.randomUUID(),
      file,
      preview: file.type.startsWith("image/") ? URL.createObjectURL(file) : undefined,
      status: "ready" as const
    }));
    setAttachments((current) => [...current, ...additions]);
  }

  async function send(textOverride?: string) {
    const text = (textOverride ?? draft).trim();
    if (!text || submitting) return;
    setSubmitting(true);
    setError("");
    try {
      let conversation = active;
      if (!conversation) {
        conversation = await api.createConversation(text.slice(0, 40));
        activeIdRef.current = conversation.id;
        setConversations((current) => [conversation!, ...current]);
        setActive({ ...conversation, runs: [] });
      }
      const uploadedIds: string[] = [];
      for (const item of attachments) {
        if (item.uploaded) {
          uploadedIds.push(item.uploaded.id);
          continue;
        }
        setAttachments((current) => current.map((candidate) => candidate.key === item.key ? { ...candidate, status: "uploading" } : candidate));
        try {
          const uploaded = await api.upload(item.file);
          uploadedIds.push(uploaded.id);
          setAttachmentsById((current) => ({
            ...current,
            [uploaded.id]: {
              id: uploaded.id,
              original_filename: uploaded.filename,
              mime_type: uploaded.mime_type,
              size: uploaded.size,
              kind: uploaded.kind,
              created_at: new Date().toISOString()
            }
          }));
          setAttachments((current) => current.map((candidate) => candidate.key === item.key ? { ...candidate, status: "uploaded", uploaded } : candidate));
        } catch (reason) {
          setAttachments((current) => current.map((candidate) => candidate.key === item.key ? {
            ...candidate,
            status: "failed",
            error: reason instanceof Error ? reason.message : "上传失败"
          } : candidate));
          throw reason;
        }
      }
      const waiting = [...(conversation.runs || [])].reverse().find(
        (run) => run.status === "waiting_for_user"
      );
      const running = [...(conversation.runs || [])].reverse().find(
        (run) => !TERMINAL.has(run.status) && run.status !== "waiting_for_user"
      );
      if (running) {
        const cancelled = await api.cancelRun(running.id);
        updateRun(cancelled, conversation.id);
        sourceRef.current?.close();
      }
      const nextRun = waiting
        ? await api.provideRunInput(waiting.id, text, uploadedIds)
        : (await api.createMessage(conversation.id, text, uploadedIds, plugins, selectedSkills)).run;
      setActive((current) => current ? {
        ...current,
        title: current.runs?.length ? current.title : text.slice(0, 40),
        runs: waiting
          ? (current.runs || []).map((run) => run.id === nextRun.id ? nextRun : run)
          : [...(current.runs || []), nextRun]
      } : current);
      if (!waiting && !(conversation.runs || []).length) {
        const renamed = await api.updateConversation(conversation.id, { title: text.slice(0, 40) });
        setConversations((current) => current.map((item) => item.id === renamed.id ? renamed : item));
      }
      attachments.forEach((item) => item.preview && URL.revokeObjectURL(item.preview));
      setAttachments([]);
      setDraft("");
      if (!waiting) setPlugins([]);
      if (!waiting) setSelectedSkills([]);
      // `submitting` only represents the short HTTP/upload transaction. The
      // background run has its own `running` state, so users can interrupt or
      // redirect a long medical workflow from the same composer.
      setSubmitting(false);
      void followRun(nextRun, conversation.id);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "消息发送失败，草稿和附件已保留");
      setSubmitting(false);
    }
  }

  async function stopCurrent() {
    const running = [...(active?.runs || [])].reverse().find((run) => !TERMINAL.has(run.status));
    if (!running || !active) return;
    const updated = await api.cancelRun(running.id);
    updateRun(updated, active.id);
    sourceRef.current?.close();
    setSubmitting(false);
  }

  async function resume(run: Run) {
    if (!active) return;
    const updated = await api.resumeRun(run.id);
    updateRun(updated, active.id);
    void followRun(updated, active.id);
  }

  async function retry(run: Run) {
    if (!active || submitting) return;
    setSubmitting(true);
    setError("");
    try {
      const nextRun = await api.retryRun(run.id);
      setActive((current) => current ? {
        ...current,
        runs: [...(current.runs || []), nextRun]
      } : current);
      setSubmitting(false);
      void followRun(nextRun, active.id);
    } catch (reason) {
      setSubmitting(false);
      setError(reason instanceof Error ? reason.message : "无法重新生成回答");
    }
  }

  async function feedback(run: Run, value: "up" | "down") {
    if (!active) return;
    try {
      const updated = await api.feedbackRun(run.id, run.feedback === value ? null : value);
      updateRun(updated, active.id);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "反馈未能保存");
    }
  }

  async function deleteRun(run: Run) {
    if (!active) return;
    if (!window.confirm("删除这条提问及其回答？关联的运行记录和产物也会删除。")) return;
    try {
      await api.deleteRun(run.id);
      setActive((current) => current ? {
        ...current,
        runs: (current.runs || []).filter((item) => item.id !== run.id)
      } : current);
      setEventsByRun((current) => {
        const next = { ...current };
        delete next[run.id];
        return next;
      });
      setArtifactsByRun((current) => {
        const next = { ...current };
        delete next[run.id];
        return next;
      });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "删除失败");
    }
  }

  function beginResize(event: React.PointerEvent) {
    if (sidebarCollapsed) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    const start = event.clientX;
    const initial = sidebarWidth;
    const move = (moveEvent: PointerEvent) => setSidebarWidth(Math.max(220, Math.min(420, initial + moveEvent.clientX - start)));
    const end = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", end);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", end);
  }

  const filteredConversations = useMemo(
    () => conversations.filter((item) => item.title.toLowerCase().includes(search.toLowerCase())),
    [conversations, search]
  );
  const runs = active?.runs || [];
  const running = runs.some((run) => !TERMINAL.has(run.status));
  const latestArtifact = Object.values(artifactsByRun).flat().at(-1) || null;
  const latestAnswer = [...runs].reverse().find((run) => run.answer)?.answer || "";
  const asrAvailable = capabilities.some((capability) =>
    capability.id === "asr" && capability.configured && capability.status !== "unavailable"
  );
  const ttsAvailable = capabilities.some((capability) =>
    capability.id === "tts" && capability.configured && capability.status !== "unavailable"
  );

  if (checkingAuth) return <div className="app-loader"><img src="/static/icons/system_logo.png" alt="" /><LoadingDots label="加载工作区" /></div>;
  if (!profile) return <Login onSuccess={async (nextProfile) => {
    setProfile(nextProfile);
    const [, nextCapabilities, nextSkills, storedAttachments] = await Promise.all([
      loadConversations(),
      api.capabilities().catch(() => []),
      api.skills().catch(() => []),
      api.attachments().catch(() => [])
    ]);
    setCapabilities(nextCapabilities);
    setSkills(nextSkills);
    setAttachmentsById(Object.fromEntries(storedAttachments.map((item) => [item.id, item])));
  }} />;

  return (
    <div className={`app-shell ${sidebarCollapsed ? "sidebar-collapsed" : ""}`} style={{ "--sidebar-width": `${sidebarCollapsed ? 56 : sidebarWidth}px` } as React.CSSProperties}>
      <Sidebar
        conversations={filteredConversations}
        activeId={active?.id || null}
        activeView={workspaceView}
        user={profile}
        collapsed={sidebarCollapsed}
        mobileOpen={mobileNav}
        search={search}
        onSearch={setSearch}
        onNew={newConversation}
        onSelect={openConversation}
        onNavigate={(view) => {
          setWorkspaceView(view);
          setMobileNav(false);
          if (view !== "chat") {
            sourceRef.current?.close();
            if (reconnectRef.current) window.clearTimeout(reconnectRef.current);
            return;
          }
          const activeRun = [...(active?.runs || [])].reverse().find(
            (run) => !TERMINAL.has(run.status)
          );
          if (activeRun && active) void followRun(activeRun, active.id);
        }}
        onToggleCollapsed={() => {
          setSidebarCollapsed((value) => {
            localStorage.setItem("ophagent.sidebar.collapsed", String(!value));
            return !value;
          });
        }}
        onCloseMobile={() => setMobileNav(false)}
        onPin={async (conversation) => {
          const updated = await api.updateConversation(conversation.id, { pinned: !conversation.pinned });
          setConversations((current) => current.map((item) => item.id === updated.id ? updated : item));
        }}
        onRename={async (conversation) => {
          const title = window.prompt("重命名对话", conversation.title)?.trim();
          if (!title) return;
          const updated = await api.updateConversation(conversation.id, { title });
          setConversations((current) => current.map((item) => item.id === updated.id ? updated : item));
          if (active?.id === updated.id) setActive((current) => current ? { ...current, title } : current);
        }}
        onDelete={async (conversation) => {
          if (!window.confirm(`删除“${conversation.title}”？此操作不可撤销。`)) return;
          await api.deleteConversation(conversation.id);
          const remaining = conversations.filter((item) => item.id !== conversation.id);
          setConversations(remaining);
          if (active?.id === conversation.id) {
            setActive(null);
            activeIdRef.current = null;
          }
        }}
        onLogout={async () => { await api.logout(); setProfile(null); setActive(null); }}
      />
      <div
        className="sidebar-resizer"
        role="separator"
        aria-orientation="vertical"
        aria-label="调整侧栏宽度"
        aria-valuemin={220}
        aria-valuemax={420}
        aria-valuenow={sidebarWidth}
        tabIndex={sidebarCollapsed ? -1 : 0}
        onPointerDown={beginResize}
        onDoubleClick={() => { setSidebarWidth(DEFAULT_SIDEBAR); localStorage.setItem("ophagent.sidebar.width", String(DEFAULT_SIDEBAR)); }}
        onKeyDown={(event) => {
          if (!["ArrowLeft", "ArrowRight", "Home"].includes(event.key)) return;
          event.preventDefault();
          const next = event.key === "Home" ? DEFAULT_SIDEBAR : Math.max(220, Math.min(420, sidebarWidth + (event.key === "ArrowRight" ? 10 : -10)));
          setSidebarWidth(next);
          localStorage.setItem("ophagent.sidebar.width", String(next));
        }}
      />
      {workspaceView === "chat" ? <main className="conversation-page">
        <header className="topbar">
          <button className="icon-button mobile-menu" onClick={() => setMobileNav(true)} aria-label="打开导航"><Menu size={20} /></button>
          <div className="conversation-title">
            <h1>{active?.title || "新对话"}</h1>
            <span>{running ? "OphAgent 正在处理" : "OphAgent"}</span>
          </div>
          <div className="topbar-actions">
            {runs.some((run) => run.risk_level === "emergency") && <span className="risk-badge"><ShieldAlert size={15} />红旗提示</span>}
            {latestArtifact && <button className="icon-button" onClick={() => { setDrawerArtifact(latestArtifact); setDrawerOpen(true); }} aria-label="打开最近产物"><PanelRight size={18} /></button>}
          </div>
        </header>
        {connectionNote && <div className="connection-banner" role="status">{connectionNote}</div>}
        {error && <div className="global-error" role="alert"><span>{error}</span><button onClick={() => setError("")}>关闭</button></div>}
        <section className="thread" aria-live="polite">
          <ConversationThread
            runs={runs}
            eventsByRun={eventsByRun}
            artifactsByRun={artifactsByRun}
            attachmentsById={attachmentsById}
            onResume={resume}
            onRetry={retry}
            onFeedback={feedback}
            onDelete={deleteRun}
            onArtifact={(artifact) => { setDrawerArtifact(artifact); setDrawerOpen(true); }}
            onConvertToDocument={async (run) => {
              const artifact = await api.createArtifactFromRun(run.id);
              setArtifactsByRun((current) => ({
                ...current,
                [run.id]: [
                  ...(current[run.id] || []).filter((item) => item.id !== artifact.id),
                  artifact
                ]
              }));
              setDrawerArtifact(artifact);
              setDrawerOpen(true);
            }}
            onSpeak={api.synthesizeSpeech}
          />
        </section>
        <Composer
          value={draft}
          attachments={attachments}
          plugins={plugins}
          skills={skills.filter((skill) => skill.status === "enabled")}
          selectedSkills={selectedSkills}
          submitting={submitting}
          running={running}
          onValue={setDraft}
          onFiles={addFiles}
          onRemoveFile={(key) => setAttachments((current) => {
            const target = current.find((item) => item.key === key);
            if (target?.preview) URL.revokeObjectURL(target.preview);
            return current.filter((item) => item.key !== key);
          })}
          onTogglePlugin={(id) => setPlugins((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id])}
          onToggleSkill={(id) => setSelectedSkills((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id])}
          onSubmit={send}
          onStop={stopCurrent}
          onTranscribe={async (file) => (await api.transcribeAudio(file)).text}
          onSpeak={api.synthesizeSpeech}
          asrAvailable={asrAvailable}
          ttsAvailable={ttsAvailable}
          onListFiles={api.attachments}
          onChooseExisting={(attachment) => {
            setAttachments((current) => {
              if (current.some((item) => item.uploaded?.attachment_id === attachment.id)) return current;
              return [...current, {
                key: crypto.randomUUID(),
                file: new File([], attachment.original_filename, { type: attachment.mime_type }),
                status: "uploaded",
                uploaded: {
                  id: attachment.id,
                  attachment_id: attachment.id,
                  kind: attachment.kind,
                  mime_type: attachment.mime_type,
                  filename: attachment.original_filename,
                  size: attachment.size,
                  status: "uploaded",
                  url: `/api/v1/attachments/${attachment.id}`
                }
              }];
            });
            setAttachmentsById((current) => ({ ...current, [attachment.id]: attachment }));
          }}
          latestAnswer={latestAnswer}
        />
      </main> : (
        <section className="workspace-page">
          <header className="topbar workspace-topbar">
            <button className="icon-button mobile-menu" onClick={() => setMobileNav(true)} aria-label="打开导航"><Menu size={20} /></button>
            <div className="conversation-title"><h1>OphAgent 工作区</h1><span>资源与能力管理</span></div>
          </header>
          <WorkspaceViews
            view={workspaceView}
            user={profile}
            capabilities={capabilities}
            conversations={conversations}
            onNavigate={setWorkspaceView}
            onSignedOut={() => {
              setProfile(null);
              setActive(null);
              setWorkspaceView("chat");
            }}
            onArtifact={(artifact) => { setDrawerArtifact(artifact); setDrawerOpen(true); }}
            onConversationProject={async (conversationId, projectId) => {
              const updated = await api.updateConversation(conversationId, { project_id: projectId });
              setConversations((current) => current.map((item) => item.id === updated.id ? updated : item));
              if (active?.id === updated.id) {
                setActive((current) => current ? { ...current, project_id: updated.project_id } : current);
              }
            }}
          />
        </section>
      )}
      <DetailDrawer
        open={drawerOpen}
        artifact={drawerArtifact}
        onClose={() => setDrawerOpen(false)}
        onChange={(artifact) => {
          setDrawerArtifact(artifact);
          setArtifactsByRun((current) => ({
            ...current,
            [artifact.run_id]: (current[artifact.run_id] || []).map((item) => item.id === artifact.id ? artifact : item)
          }));
        }}
        onSave={api.updateArtifact}
      />
    </div>
  );
}

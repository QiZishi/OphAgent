import type {
  Artifact,
  AttachmentRecord,
  Capability,
  Conversation,
  ConversationPage,
  EvolutionStatus,
  KnowledgeSource,
  KnowledgeStatus,
  MemoryRecord,
  PluginId,
  Project,
  ProviderConfig,
  Run,
  RunEvent,
  SkillRecord,
  UploadedAttachment,
  UserProfile,
  VoiceTranscription
} from "./types";

const jsonHeaders = { "Content-Type": "application/json" };

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, { credentials: "include", ...init });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({ detail: response.statusText }));
    const detail = typeof payload.detail === "string" ? payload.detail : JSON.stringify(payload.detail);
    throw new Error(detail || `请求失败（${response.status}）`);
  }
  if (response.status === 204) return undefined as T;
  return response.json();
}

export const api = {
  me: () => request<UserProfile>("/auth/me"),
  login: (username: string, password: string, register = false) =>
    request<{ access_token: string }>(register ? "/auth/register" : "/auth/login", {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify({ username, password })
    }),
  logout: () => request<void>("/auth/logout", { method: "POST" }),
  changePassword: (currentPassword: string, newPassword: string) =>
    request<void>("/auth/password", {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify({
        current_password: currentPassword,
        new_password: newPassword
      })
    }),
  conversations: () => request<ConversationPage>("/api/v1/conversations?limit=100"),
  conversation: (id: number) => request<Conversation>(`/api/v1/conversations/${id}`),
  createConversation: (title = "新对话") =>
    request<Conversation>("/api/v1/conversations", {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify({ title, agent_type: "core" })
    }),
  updateConversation: (id: number, values: { title?: string; pinned?: boolean; project_id?: number | null }) =>
    request<Conversation>(`/api/v1/conversations/${id}`, {
      method: "PATCH",
      headers: jsonHeaders,
      body: JSON.stringify(values)
    }),
  deleteConversation: (id: number) =>
    request<void>(`/api/v1/conversations/${id}`, { method: "DELETE" }),
  createMessage: (
    conversationId: number,
    content: string,
    attachmentIds: string[],
    requestedPlugins: PluginId[],
    requestedSkills: string[],
    mode: "auto" | "quick" | "standard" | "deep" = "auto"
  ) =>
    request<{ run: Run }>(`/api/v1/conversations/${conversationId}/messages`, {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify({
        content,
        attachment_ids: attachmentIds,
        requested_plugins: requestedPlugins,
        requested_skills: requestedSkills,
        mode,
        idempotency_key: crypto.randomUUID()
      })
    }),
  listRuns: () => request<Run[]>("/api/v1/runs"),
  getRun: (id: string) => request<Run>(`/api/v1/runs/${id}`),
  runEvents: (id: string, afterSequence = 0) =>
    request<RunEvent[]>(`/api/v1/runs/${id}/events?after_sequence=${afterSequence}`),
  cancelRun: (id: string) => request<Run>(`/api/v1/runs/${id}/cancel`, { method: "POST" }),
  interveneRun: (
    id: string,
    values: {
      mode: "interrupt" | "queue";
      content: string;
      attachment_ids: string[];
      expected_attempt: number;
      client_message_id: string;
    }
  ) =>
    request<Run>(`/api/v1/runs/${id}/interventions`, {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify(values)
    }),
  cancelRunIntervention: (runId: string, interventionId: string) =>
    request<Run>(`/api/v1/runs/${runId}/interventions/${interventionId}`, {
      method: "DELETE"
    }),
  resumeRun: (id: string) => request<Run>(`/api/v1/runs/${id}/resume`, { method: "POST" }),
  retryRun: (id: string) => request<Run>(`/api/v1/runs/${id}/retry`, { method: "POST" }),
  feedbackRun: (id: string, value: "up" | "down" | null) =>
    request<Run>(`/api/v1/runs/${id}/feedback`, {
      method: "PATCH",
      headers: jsonHeaders,
      body: JSON.stringify({ value })
    }),
  deleteRun: (id: string) => request<void>(`/api/v1/runs/${id}`, { method: "DELETE" }),
  provideRunInput: (id: string, content: string, attachmentIds: string[]) =>
    request<Run>(`/api/v1/runs/${id}/input`, {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify({ content, attachment_ids: attachmentIds })
    }),
  capabilities: () => request<Capability[]>("/api/v1/capabilities"),
  evolutionStatus: () => request<EvolutionStatus>("/api/v1/evolution/status"),
  artifacts: (runId?: string) =>
    request<Artifact[]>(`/api/v1/artifacts${runId ? `?run_id=${encodeURIComponent(runId)}` : ""}`),
  createArtifactFromRun: (runId: string, title?: string) =>
    request<Artifact>("/api/v1/artifacts/from-run", {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify({ run_id: runId, title })
    }),
  updateArtifact: (id: string, values: { title?: string; content?: string }) =>
    request<Artifact>(`/api/v1/artifacts/${id}`, {
      method: "PATCH",
      headers: jsonHeaders,
      body: JSON.stringify(values)
    }),
  attachments: () => request<AttachmentRecord[]>("/api/v1/attachments"),
  upload: async (file: File) => {
    const body = new FormData();
    body.append("file", file);
    return request<UploadedAttachment>("/api/v1/upload", { method: "POST", body });
  },
  deleteAttachment: (id: string) =>
    request<void>(`/api/v1/attachments/${id}`, { method: "DELETE" }),
  transcribeAudio: async (file: File) => {
    const body = new FormData();
    body.append("file", file);
    return request<VoiceTranscription>("/api/v1/audio/transcriptions", { method: "POST", body });
  },
  synthesizeSpeech: async (text: string, voice?: string, signal?: AbortSignal) => {
    const response = await fetch("/api/v1/audio/speech", {
      method: "POST",
      credentials: "include",
      headers: jsonHeaders,
      body: JSON.stringify({ text, voice }),
      signal
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({ detail: response.statusText }));
      const detail = typeof payload.detail === "string" ? payload.detail : JSON.stringify(payload.detail);
      throw new Error(detail || `语音合成失败（${response.status}）`);
    }
    return response.blob();
  },
  projects: () => request<Project[]>("/api/v1/projects"),
  createProject: (name: string, description = "") =>
    request<Project>("/api/v1/projects", {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify({ name, description })
    }),
  updateProject: (id: number, values: Partial<Pick<Project, "name" | "description" | "color">>) =>
    request<Project>(`/api/v1/projects/${id}`, {
      method: "PATCH",
      headers: jsonHeaders,
      body: JSON.stringify(values)
    }),
  deleteProject: (id: number) => request<void>(`/api/v1/projects/${id}`, { method: "DELETE" }),
  memories: () => request<MemoryRecord[]>("/api/v1/memories"),
  createMemory: (
    category: MemoryRecord["category"],
    content: string
  ) =>
    request<MemoryRecord>("/api/v1/memories", {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify({
        category,
        content,
        source: "用户在记忆工作区中明确创建"
      })
    }),
  memoryPreference: () => request<{ enabled: boolean }>("/api/v1/memories/preference"),
  setMemoryPreference: (enabled: boolean) =>
    request<{ enabled: boolean }>("/api/v1/memories/preference", {
      method: "PATCH",
      headers: jsonHeaders,
      body: JSON.stringify({ enabled })
    }),
  updateMemory: (id: string, values: Partial<Pick<MemoryRecord, "content" | "status" | "confirmation_note">>) =>
    request<MemoryRecord>(`/api/v1/memories/${id}`, {
      method: "PATCH",
      headers: jsonHeaders,
      body: JSON.stringify(values)
    }),
  deleteMemory: (id: string) => request<void>(`/api/v1/memories/${id}`, { method: "DELETE" }),
  skills: () => request<SkillRecord[]>("/api/v1/skills"),
  providerConfig: () => request<ProviderConfig>("/api/v1/provider-config"),
  saveProviderConfig: (config: ProviderConfig) =>
    request<ProviderConfig>("/api/v1/provider-config", {
      method: "PUT",
      headers: jsonHeaders,
      body: JSON.stringify({
        providers: Object.fromEntries(
          Object.entries(config.providers).map(([id, value]) => [id, {
            use_default: value.use_default,
            url: value.url,
            model: value.model,
            api_key: value.api_key || null
          }])
        )
      })
    }),
  importSkill: (markdown: string) =>
    request<SkillRecord>("/api/v1/skills/import", {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify({ markdown })
    }),
  validateSkill: (id: string) => request<SkillRecord>(`/api/v1/skills/${id}/validate`, { method: "POST" }),
  updateSkill: (
    id: string,
    status: "enabled" | "disabled" | "rejected",
    options?: { force?: boolean; risk_acknowledgement?: string }
  ) =>
    request<SkillRecord>(`/api/v1/skills/${id}`, {
      method: "PATCH",
      headers: jsonHeaders,
      body: JSON.stringify({ status, ...options })
    }),
  knowledgeStatus: () => request<KnowledgeStatus>("/api/v1/knowledge/status"),
  knowledgeSources: () => request<KnowledgeSource[]>("/api/v1/knowledge/sources"),
  updateKnowledgeSource: (id: string, values: Partial<KnowledgeSource>) =>
    request<KnowledgeSource>(`/api/v1/knowledge/sources/${id}`, {
      method: "PATCH",
      headers: jsonHeaders,
      body: JSON.stringify(values)
    }),
  rebuildKnowledge: (include_embeddings = true) =>
    request<{ status: string }>(`/api/v1/knowledge/index?include_embeddings=${include_embeddings}`, {
      method: "POST"
    }),
  importKnowledge: async (file: File) => {
    const body = new FormData();
    body.append("file", file);
    body.append("title", file.name.replace(/\.[^.]+$/, ""));
    return request<KnowledgeSource>("/api/v1/knowledge/import", { method: "POST", body });
  }
};

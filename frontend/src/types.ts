export type PluginId =
  | "lesion_localizer"
  | "aux_diagnosis"
  | "report_generator";

export type RunStatus =
  | "queued"
  | "running"
  | "interrupted"
  | "waiting_for_user"
  | "completed"
  | "completed_with_warnings"
  | "failed"
  | "cancelled";

export interface UserProfile {
  id: number;
  username: string;
  role: "user";
}

export interface PlanNode {
  id: string;
  title: string;
  agent: string;
  capability: string;
  depends_on: string[];
  status: "pending" | "running" | "completed" | "failed" | "skipped" | "cancelled";
  required: boolean;
  error_code?: string;
  output?: Record<string, unknown>;
  started_at?: string;
  completed_at?: string;
}

export interface TaskRoute {
  intent:
    | "quick_answer"
    | "clinical_qna"
    | "image_analysis"
    | "aux_assessment"
    | "report_generation"
    | "knowledge_retrieval";
  complexity: "quick" | "standard" | "deep";
  selected_plugins: PluginId[];
  reason_code: string;
}

export interface Run {
  id: string;
  trace_id: string;
  status: RunStatus;
  risk_level: "routine" | "complex" | "high" | "emergency";
  route?: TaskRoute;
  input: {
    query: string;
    plugin_id: string;
    conversation_id?: number;
    attachment_ids: string[];
    image_paths: string[];
    document_paths: string[];
    audio_paths: string[];
    requested_skills?: string[];
    regenerated_from?: string;
  };
  plan: PlanNode[];
  answer?: string;
  feedback?: "up" | "down";
  error_code?: string;
  error_message?: string;
  warnings: string[];
  pending_question?: string;
  pending_approval?: Record<string, unknown>;
  user_inputs?: string[];
  interventions?: RunIntervention[];
  applied_intervention_ids?: string[];
  attempt: number;
  execution_revision: number;
  budget: {
    model_calls: number;
    prompt_tokens: number;
    completion_tokens: number;
    max_model_calls: number;
    max_tokens: number;
  };
  context_stats?: {
    source_turns: number;
    retained_turns: number;
    summarized_turns: number;
    tokens_before: number;
    tokens_after: number;
    cache_hit: boolean;
    compaction_status: "not_needed" | "pending" | "completed" | "failed";
    compaction_method: "none" | "model_structured_summary";
    compaction_attempts: number;
  };
  created_at: string;
  updated_at?: string;
}

export interface RunIntervention {
  id: string;
  run_id: string;
  mode: "interrupt" | "queue";
  content?: string;
  attachment_ids: string[];
  expected_attempt: number;
  client_message_id: string;
  status: "queued" | "applied" | "cancelled";
  created_at: string;
  applied_at?: string;
  cancelled_at?: string;
}

export interface Evidence {
  id: string;
  title: string;
  source: string;
  excerpt: string;
  locator?: string;
  published_at?: string;
  institution?: string;
  version?: string;
  region?: string;
  population?: string;
  source_status: "current" | "expired" | "superseded" | "unknown";
  superseded_by?: string;
  verified?: boolean;
  visual_path?: string;
  source_type: "guideline" | "record" | "web" | "knowledge_graph" | "user";
  score: number;
}

export interface Artifact {
  id: string;
  run_id: string;
  type: "report" | "image" | "table" | "citation" | "document" | "audio";
  title: string;
  mime_type: string;
  path?: string;
  content?: string;
  metadata: Record<string, unknown>;
  created_at?: string;
}

export interface RunEvent {
  id: string;
  sequence: number;
  run_id: string;
  trace_id: string;
  type: string;
  public_summary: string;
  timestamp: string;
  status?: string;
  data: Record<string, unknown>;
  duration_ms?: number;
  error_code?: string;
}

export interface ConversationMessage {
  id: number;
  role: "user" | "assistant";
  content: string;
  file_path?: string;
  created_at: string;
}

export interface Conversation {
  id: number;
  title: string;
  agent_type: string;
  created_at: string;
  pinned: boolean;
  project_id?: number | null;
  messages?: ConversationMessage[];
  runs?: Run[];
}

export interface ConversationPage {
  items: Conversation[];
  total: number;
  skip: number;
  limit: number;
}

export interface UploadedAttachment {
  id: string;
  attachment_id: string;
  kind: "image" | "document" | "audio";
  mime_type: string;
  filename: string;
  size: number;
  status: "uploading" | "uploaded" | "failed";
  url: string;
}

export interface AttachmentRecord {
  id: string;
  conversation_id?: number;
  message_id?: number;
  original_filename: string;
  mime_type: string;
  size: number;
  kind: "image" | "document" | "audio";
  created_at: string;
}

export interface Project {
  id: number;
  name: string;
  description: string;
  color: string;
  conversation_count: number;
  created_at: string;
  updated_at: string;
}

export interface VoiceTranscription {
  text: string;
  language?: string;
  duration_seconds?: number;
}

export interface LocalAttachment {
  key: string;
  file: File;
  preview?: string;
  status: "ready" | "uploading" | "uploaded" | "failed";
  uploaded?: UploadedAttachment;
  error?: string;
}

export interface Capability {
  id: string;
  configured: boolean;
  status: "ready" | "degraded" | "unavailable" | "unknown";
  model?: string;
  required: boolean;
  detail?: string;
  provider?: string;
}

export interface MemoryRecord {
  id: string;
  category: "preference" | "history" | "medication" | "allergy" | "follow_up" | "workspace";
  content: string;
  source: string;
  kind?: "semantic" | "episodic" | "procedural";
  scope?: "user";
  status: "proposed" | "confirmed" | "rejected";
  sensitivity: "normal" | "sensitive" | "restricted";
  conflicts_with: string[];
  confirmation_note?: string;
  updated_at: string;
}

export interface SkillRecord {
  id: string;
  version: string;
  description: string;
  capabilities: string[];
  dependencies: string[];
  risk_level: "routine" | "complex" | "high" | "emergency";
  plugins: string[];
  status: "candidate" | "validated" | "enabled" | "disabled" | "rejected";
  evaluation: {
    passed?: boolean;
    offline_review_required?: boolean;
    risks?: Array<{ code: string; message: string }>;
    user_approval?: {
      reviewer: string;
      checksum: string;
      acknowledgement: string;
      approved_at: string;
    };
    [key: string]: unknown;
  };
}

export interface EvolutionCandidate {
  id: string;
  kind: "memory_retrieval" | "memory_extraction" | "skill" | "runtime";
  target: string;
  sample_size: number;
  negative_rate: number;
  trigger: string;
  allowed_mutation_paths: string[];
  status: "ready_for_offline_evaluation" | "accepted" | "rejected" | "promoted";
  requires_human_approval: boolean;
  created_at: string;
  updated_at: string;
}

export interface EvolutionStatus {
  enabled: boolean;
  mode: "observe_and_gate";
  signal_count: number;
  feedback_count: number;
  observed_run_count: number;
  ready_candidate_count: number;
  memory_adaptation: string;
  skill_adaptation: string;
  production_mutation: "disabled";
  human_approval_required: boolean;
  candidates: EvolutionCandidate[];
}

export type ProviderId =
  | "agent"
  | "sub_agent"
  | "asr"
  | "tts"
  | "embedding"
  | "reranker"
  | "search"
  | "mineru";

export interface ProviderConfigEntry {
  use_default: boolean;
  url: string;
  model: string;
  api_key?: string;
  has_api_key: boolean;
  default_url: string;
  default_model: string;
  default_configured: boolean;
}

export interface ProviderConfig {
  providers: Record<ProviderId, ProviderConfigEntry>;
  mineru_url: string;
}

export interface KnowledgeSource {
  id: string;
  title: string;
  path: string;
  source_type: "guideline" | "record" | "web" | "user";
  institution?: string;
  region?: string;
  published_at?: string;
  version?: string;
  population?: string;
  status: "current" | "expired" | "superseded" | "unknown";
  superseded_by?: string;
  imported_by?: number;
  verified: boolean;
}

export interface KnowledgeStatus {
  status: "ready" | "degraded" | "unavailable" | "building";
  documents: number;
  chunks: number;
  page_visuals: number;
  vectors: number;
  embedding_model?: string;
  graph_nodes: number;
  graph_edges: number;
  stale: boolean;
  detail?: string;
  retrieval: string[];
}

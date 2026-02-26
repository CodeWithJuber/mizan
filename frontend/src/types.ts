/**
 * MIZAN Shared TypeScript Types
 * Core type definitions for the Quranic AGI System
 */

// ===== API Types =====

export interface ApiClient {
  get: (path: string) => Promise<Record<string, unknown>>;
  post: (path: string, body?: Record<string, unknown>) => Promise<Record<string, unknown>>;
  del: (path: string) => Promise<Record<string, unknown>>;
  API_URL: string;
}

// ===== Agent Types =====

export type AgentState = "resting" | "thinking" | "acting" | "learning" | "error";
export type NafsLevel = 1 | 2 | 3 | 4 | 5 | 6 | 7;
export type NafsName = "Ammara" | "Lawwama" | "Mulhama" | "Mutmainna" | "Radiya" | "Mardiyya" | "Kamila";
export type AgentRole =
  | "rasul" | "wakil" | "hafiz" | "shahid"
  | "wali" | "mubashir" | "mundhir" | "katib" | "muallim";

export interface Agent {
  id: string;
  name: string;
  role: AgentRole;
  state: AgentState;
  nafs_level: NafsLevel;
  nafs_name?: NafsName;
  ruh_energy?: number;
  ihsan_eligible?: boolean;
  shukr_strengths?: number;
  total_tasks: number;
  success_rate: number;
  hikmah_count: number;
  tools: string[];
}

// ===== Yaqin Certainty Types =====

export type YaqinLevel = "ilm_al_yaqin" | "ayn_al_yaqin" | "haqq_al_yaqin";

export interface YaqinTag {
  level: YaqinLevel;
  confidence: number;
  source: string;
  evidence: string[];
}

// ===== Cognitive Method Types =====

export type CognitiveMethod = "tafakkur" | "tadabbur" | "istidlal" | "qiyas" | "ijma";

// ===== Qalb Emotional Types =====

export type EmotionalState = "neutral" | "positive" | "frustrated" | "anxious" | "confused" | "determined" | "fatigued";
export type ToneStyle = "standard" | "encouraging" | "patient" | "concise" | "warm" | "focused";

export interface QalbReading {
  state: EmotionalState;
  confidence: number;
  recommended_tone: ToneStyle;
  signals: string[];
}

// ===== Ruh Energy Types =====

export interface RuhState {
  energy: number;
  max_energy: number;
  label: string;
}

// ===== Majlis Agent Types =====

export type MajlisNafsLevel = "ammara" | "lawwama" | "mulhama" | "mutmainna" | "radiya" | "mardiyya" | "kamila";
export type MajlisAgentStatus = "active" | "idle" | "busy" | "offline";

export interface MajlisAgent {
  agent_id: string;
  name: string;
  arabic_name?: string;
  status: MajlisAgentStatus;
  nafs_level: MajlisNafsLevel;
  reputation_score?: number;
  capabilities?: string[];
  verified?: boolean;
}

export interface Halaqah {
  halaqah_id: string;
  name: string;
  topic: string;
  description?: string;
  member_count?: number;
}

export interface KnowledgeItem {
  knowledge_id?: string;
  topic: string;
  content: string;
  source?: string;
  verified?: boolean;
  quality_score?: number;
}

// ===== Chat Types =====

export interface ChatMessage {
  id: number;
  role: "user" | "assistant";
  content: string;
  agent?: string;
  ts: string;
}

// ===== Memory Types =====

export interface Memory {
  id: string;
  type: "episodic" | "semantic" | "procedural";
  content: string | Record<string, unknown>;
  agent_id?: string;
  importance: number;
  tags?: string[];
}

// ===== Terminal Types =====

export interface TerminalLine {
  text: string;
  type: "" | "error" | "warn" | "info" | "gold";
  ts?: number;
}

// ===== Channel Types =====

export interface ChannelInfo {
  name: string;
  arabic: string;
  color: string;
  icon: string;
}

export interface Channel {
  id: string;
  type: string;
  name: string;
  status: "connected" | "disconnected";
  connected_users: number;
  messages_processed: number;
}

// ===== Gateway Types =====

export interface GatewayStatus {
  status: "online" | "offline";
  channels: number;
  sessions: number;
}

// ===== Automation Types =====

export interface ScheduledJob {
  id: string;
  name: string;
  cron: string;
  task: string;
  agent_id?: string;
  enabled: boolean;
  run_count: number;
  next_run?: string;
}

export interface Webhook {
  id: string;
  name: string;
  path: string;
  task_template: string;
  agent_id?: string;
  trigger_count: number;
}

// ===== Plugin Types =====

export type PluginType = "ayah" | "bab" | "hafiz" | "ruh" | "muaddib";
export type TrustLevel = "ammara" | "lawwama" | "mulhama" | "mutmainna" | "radiya" | "mardiyya" | "kamila";

export interface Plugin {
  name: string;
  description?: string;
  plugin_type: PluginType;
  version: string;
  active: boolean;
  author?: string;
  trust_level?: TrustLevel;
  permissions?: string[];
  checksum?: string;
  quranic_reference?: string;
}

export interface PluginHook {
  event: string;
  plugin: string;
  priority: number;
}

// ===== Scanner Types =====

export type ScanSeverity = "critical" | "high" | "medium" | "low" | "info";

export interface ScanFinding {
  id?: string;
  title: string;
  severity: ScanSeverity;
  category: string;
  cwe_id?: string;
  file_path?: string;
  line_number?: number;
  code_snippet?: string;
  recommendation?: string;
}

export interface ScanSummary {
  total_findings: number;
  risk_score: number;
  verdict?: string;
  by_severity: Record<string, number>;
}

export interface ScanReport {
  scan_type: string;
  target: string;
  summary?: ScanSummary;
  findings?: ScanFinding[];
}

export interface ScanHistoryItem {
  id: string;
  scan_type: string;
  target: string;
  finding_count: number;
  summary?: { risk_score: number };
}

// ===== Skills Types =====

export interface Skill {
  name: string;
  display: string;
  arabic: string;
  description: string;
  category: string;
  installed: boolean;
  version: string;
  permissions: string[];
}

// ===== Notebook Types =====

export interface NotebookCell {
  id: string;
  cell_type: "code" | "markdown";
  source: string;
  status?: "success" | "error";
  execution_count?: number;
  outputs?: CellOutput[];
}

export interface CellOutput {
  output_type: "stream" | "error" | "execute_result";
  stdout?: string;
  stderr?: string;
  text?: string;
  execution_time?: number;
}

export interface Notebook {
  id: string;
  title: string;
  description?: string;
  language: string;
  version: string;
  cell_count: number;
  cells?: NotebookCell[];
}

// ===== Provider Types =====

export interface ProviderModel {
  id: string;
  name: string;
  context?: number;
  vision?: boolean;
  pricing?: { prompt: string; completion: string };
  size?: number;
}

export interface ProviderInfo {
  name: string;
  display: string;
  configured: boolean;
  models: ProviderModel[];
  default_model: string;
  base_url?: string;
}

export interface ProviderStatus {
  active: string;
  default_model: string;
  providers: ProviderInfo[];
}

export interface ProviderHealth {
  provider: string;
  healthy: boolean;
  error?: string;
  usage?: number;
  limit?: number | null;
  models?: number;
}

// ===== Integration Types =====

export interface Integration {
  id: string;
  name: string;
  type: string;
  enabled: boolean;
  config?: Record<string, unknown>;
}

// ===== System Status =====

export interface SystemStatus {
  agents?: { total: number; active: number };
  sessions?: number;
  connections?: number;
}

// ===== Component Props =====

export interface PageProps {
  api: ApiClient;
  addTerminalLine?: (text: string, type: string) => void;
}

// ===== WebSocket Types =====

export type WsConnectionStatus = "connected" | "disconnected" | "error";

export interface WsMessage {
  type: string;
  [key: string]: unknown;
}

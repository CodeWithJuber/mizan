/**
 * Ruh Model Types
 * Type definitions for the local learning model, thinking traces,
 * training metrics, NLP pipeline visualization, and intelligent routing.
 */

// ===== Thinking Trace Types =====

export type ThinkingPhase =
  | "perception"
  | "comprehension"
  | "reasoning"
  | "memory"
  | "evaluation"
  | "generation"
  | "reflection";

export interface ThinkingStep {
  id: string;
  phase: ThinkingPhase;
  content: string;
  confidence: number;
  timestamp: number;
  metadata?: Record<string, unknown>;
}

export interface ThinkingTrace {
  request_id: string;
  steps: ThinkingStep[];
  duration_ms: number;
  avg_confidence: number;
}

// ===== Training Types =====

export interface TrainingMetrics {
  running: boolean;
  stage: string | null;
  epoch: number;
  total_epochs: number;
  step: number;
  total_steps: number;
  loss: number | null;
  lr: number | null;
  progress_pct: number;
  elapsed: number;
  dataset_size: number;
  model_params: number;
  message: string;
  losses: number[];
}

export interface TrainingRun {
  stage: string;
  status: "completed" | "stopped" | "failed";
  started_at: number;
  completed_at: number;
  epochs_completed: number;
  total_epochs: number;
  final_loss: number | null;
  losses: number[];
  dataset_size: number;
  model_params: number;
}

// ===== Checkpoint Types =====

export interface Checkpoint {
  name: string;
  created_at: number;
  size_mb: number;
  max_seq_len: number | null;
  config: Record<string, unknown>;
}

// ===== Data Stats Types =====

export interface DataSource {
  name: string;
  type: "seed" | "huggingface";
  samples: number;
  size_mb: number;
  available: boolean;
  weight?: number;
  hf_id?: string;
}

export interface DataStats {
  sources: DataSource[];
  total_samples: number;
  total_size_mb: number;
}

// ===== Architecture Types =====

export interface ModelComponent {
  name: string;
  type: string;
  params: number;
}

export interface ArchitectureLayer {
  name: string;
  desc: string;
}

export interface ModelArchitecture {
  total_params: number;
  n_layers: number;
  d_model: number;
  d_root: number;
  d_pattern: number;
  n_heads: number;
  n_roots: number;
  n_patterns: number;
  max_seq_len: number;
  components: ModelComponent[];
  architecture_layers: ArchitectureLayer[];
}

// ===== Tokenizer Pipeline Types =====

export interface TokenizationStep {
  phase: string;
  description: string;
  output: unknown;
}

export interface TokenizeResult {
  tokens: [number, number][];
  token_count: number;
  analysis: Record<string, unknown>[];
  pipeline?: TokenizationStep[];
}

export interface TasrifStep {
  operator: string;
  input: number[];
  output: number[];
  changed_dims: number[];
}

export interface TasrifResult {
  original: number[];
  final: number[];
  steps: TasrifStep[];
  dimensions: string[];
  available_operators: string[];
}

// ===== Router Types =====

export interface RouterDecision {
  provider: string;
  model: string;
  confidence: number;
  reason: string;
}

// ===== Model Status Types =====

export interface RuhStatus {
  enabled: boolean;
  model_path: string;
  device: string;
  loaded: boolean;
}

export interface LearnerStats {
  total_interactions: number;
  exportable_count: number;
  last_export: string | null;
}

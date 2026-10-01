/**
 * MIZAN morphology API types — root-morphology chat/UI features.
 * Mirrors the real backend response models in backend/api/main.py
 * (/api/ruh/morphology/*) — aligned 2026-09-29 against morphology_api.py.
 */

/**
 * Provenance of a linguistic claim. Drives the trust-moat VerifiedBadge.
 * "unavailable" = backend honestly has no data (e.g. verse occurrences).
 * "ai" is only ever set client-side for LLM-generated text.
 */
export type Provenance = "verified" | "heuristic" | "unavailable" | "ai";

export interface AnalyzeWordResponse {
  word: string;
  root: string;
  root_provenance: Provenance;
  pattern: string;
  pattern_provenance: Provenance;
  wazn: string | null;
  wazn_provenance: Provenance;
  provenance: Provenance;
  source: string;
  note?: string | null;
}

export interface Derivative {
  surface: string;
  gloss: string;
}

export interface RootEntryResponse {
  root: string;
  meaning: string;
  meaning_en: string;
  domain: string;
  derivatives: Derivative[];
  patterns: string[];
  patterns_provenance: Provenance;
  frequency: number | null;
  provenance: Provenance;
  source: string;
  note?: string | null;
}

export interface SenseEntry {
  surface: string;
  gloss: string;
  kind: string;
  pattern: string | null;
}

export interface SensesResponse {
  word: string;
  root: string;
  senses: SenseEntry[];
  ranked_by_context: boolean;
  provenance: Provenance;
  source: string;
  note?: string | null;
}

/** Slim root entry returned by the concept bridge (no derivatives). */
export interface BridgeRootEntry {
  meaning: string;
  domain: string;
  frequency: number | null;
}

export interface BridgeResponse {
  concept: string;
  arabic_root: string;
  root_entry: BridgeRootEntry;
  provenance: Provenance;
  source: string;
  note?: string | null;
}

export interface PatternSibling {
  word?: string;
  root?: string;
}

export interface PatternResponse {
  wazn: string;
  available: boolean;
  siblings: PatternSibling[];
  provenance: Provenance;
  source: string;
  reason?: string | null;
}

/**
 * Verse occurrences. The backend currently has no static per-verse index,
 * so `available` is false and this list is empty — the UI renders the
 * honest empty state instead of inventing verses.
 */
export interface Occurrence {
  ref?: string;
  text_ar?: string;
  text_en?: string;
}

export interface OccurrencesResponse {
  root: string;
  available: boolean;
  occurrences: Occurrence[];
  frequency: number | null;
  frequency_note?: string | null;
  provenance: Provenance;
  source: string;
  reason?: string | null;
}

export interface ExplainPromptResponse {
  word: string;
  /** Verified facts object from the backend — stringify before sending. */
  verified_facts: Record<string, unknown>;
  system_instruction: string;
  provenance: Provenance;
  source: string;
}

/**
 * useMorphology — typed hook wrapping the /api/ruh/morphology/* endpoints.
 * Built on useApi() so every call carries the Bearer JWT (same pattern as
 * PR #53). The bridge endpoint is the one exception: it needs the raw HTTP
 * status (404 = unknown concept), which ApiClient does not surface, so it
 * does an auth'd fetch with identical header logic and maps 404 → null.
 */

import { useCallback, useMemo } from "react";
import { useApi } from "./useApi";
import type {
  AnalyzeWordResponse,
  BridgeResponse,
  ExplainPromptResponse,
  OccurrencesResponse,
  PatternResponse,
  RootEntryResponse,
  SensesResponse,
} from "../types/morphology";

export class MorphologyApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "MorphologyApiError";
    this.status = status;
  }
}

export function useMorphology() {
  const api = useApi();

  const analyzeWord = useCallback(
    async (word: string): Promise<AnalyzeWordResponse> => {
      const data = await api.post("/ruh/morphology/analyze", { word });
      return data as unknown as AnalyzeWordResponse;
    },
    [api],
  );

  /**
   * Returns null when the backend answers 404 (root not in the verified
   * lexicon). Like getRootBridge, this needs the raw HTTP status, which
   * ApiClient does not surface.
   */
  const getRootEntry = useCallback(
    async (root: string): Promise<RootEntryResponse | null> => {
      const token = localStorage.getItem("mizan_token") || "";
      const res = await fetch(
        `${api.API_URL}/ruh/morphology/root/${encodeURIComponent(root)}`,
        { headers: token ? { Authorization: `Bearer ${token}` } : {} },
      );
      if (res.status === 404) return null;
      if (!res.ok) {
        throw new MorphologyApiError(
          res.status,
          `Root lookup failed (HTTP ${res.status})`,
        );
      }
      return (await res.json()) as unknown as RootEntryResponse;
    },
    [api],
  );

  const getSenses = useCallback(
    async (word: string, context?: string): Promise<SensesResponse> => {
      const data = await api.post("/ruh/morphology/senses", {
        word,
        ...(context ? { context } : {}),
      });
      return data as unknown as SensesResponse;
    },
    [api],
  );

  /**
   * Returns null when the backend answers 404 (no verified bridge for the
   * concept). Callers MUST render the friendly empty state, never invent
   * a root.
   */
  const getRootBridge = useCallback(
    async (concept: string): Promise<BridgeResponse | null> => {
      const token = localStorage.getItem("mizan_token") || "";
      const res = await fetch(
        `${api.API_URL}/ruh/morphology/bridge?concept=${encodeURIComponent(concept)}`,
        { headers: token ? { Authorization: `Bearer ${token}` } : {} },
      );
      if (res.status === 404) return null;
      if (!res.ok) {
        throw new MorphologyApiError(
          res.status,
          `Root bridge lookup failed (HTTP ${res.status})`,
        );
      }
      return (await res.json()) as unknown as BridgeResponse;
    },
    [api],
  );

  const getPattern = useCallback(
    async (wazn: string): Promise<PatternResponse> => {
      const data = await api.get(
        `/ruh/morphology/pattern/${encodeURIComponent(wazn)}`,
      );
      return data as unknown as PatternResponse;
    },
    [api],
  );

  const getOccurrences = useCallback(
    async (root: string): Promise<OccurrencesResponse> => {
      const data = await api.get(
        `/ruh/morphology/occurrences?root=${encodeURIComponent(root)}`,
      );
      return data as unknown as OccurrencesResponse;
    },
    [api],
  );

  const getExplainPrompt = useCallback(
    async (word: string): Promise<ExplainPromptResponse> => {
      const data = await api.post("/ruh/morphology/explain-prompt", { word });
      return data as unknown as ExplainPromptResponse;
    },
    [api],
  );

  return useMemo(
    () => ({
      analyzeWord,
      getRootEntry,
      getSenses,
      getRootBridge,
      getPattern,
      getOccurrences,
      getExplainPrompt,
    }),
    [
      analyzeWord,
      getRootEntry,
      getSenses,
      getRootBridge,
      getPattern,
      getOccurrences,
      getExplainPrompt,
    ],
  );
}

export type MorphologyClient = ReturnType<typeof useMorphology>;

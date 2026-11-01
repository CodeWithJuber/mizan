/**
 * Sakk receipts as the user sees them: one line per action, and whether the
 * whole chain still verifies.
 */

export interface Receipt {
  seq: number;
  at: string;
  kind: string;
  display: string;
  hash: string;
  prev: string;
  tool?: string;
  outcome?: string;
}

export interface Verdict {
  ok: boolean;
  receipts: number;
  head?: string | null;
  broken_at?: number;
  problem?: string;
}

export const KIND_LABELS: Record<string, string> = {
  tool: "Action",
  held_decision: "Your decision",
  approval: "Approval",
  erase: "Deletion",
  scorecard: "Published result",
};

export function isReceipts(value: unknown): value is { receipts: Receipt[]; public_key: string } {
  const data = value as { receipts?: unknown; public_key?: unknown } | null;
  return !!data && Array.isArray(data.receipts) && typeof data.public_key === "string";
}

export function verdictLine(verdict: Verdict): string {
  if (verdict.ok) {
    return verdict.receipts
      ? `All ${verdict.receipts} receipts verify: none was changed, removed or reordered.`
      : "No receipts yet.";
  }
  return `Receipt ${verdict.broken_at} does not verify: ${verdict.problem}.`;
}

export function outcomeTone(outcome: string | undefined): "good" | "held" | "bad" | "plain" {
  if (outcome === "done") return "good";
  if (outcome === "held") return "held";
  if (outcome === "error" || outcome === "declined") return "bad";
  return "plain";
}

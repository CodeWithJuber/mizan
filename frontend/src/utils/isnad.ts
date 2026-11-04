/** Isnad: every claim of an answer, graded by what supports it (sahih, hasan, da'if, mawdu'). */

export type Grade = "sahih" | "hasan" | "daif" | "mawdu";

export interface Claim {
  text: string;
  kind: "quote" | "sentence";
  grade: Grade;
  support: string[];
}

export interface IsnadSummary {
  counts: Record<Grade, number>;
  claims: number;
  supported: number | null;
  ledger: Claim[];
}

/** Status colours (never a series colour), always shown with an icon and a label. */
export const GRADES: Record<Grade, { label: string; arabic: string; icon: string; meaning: string; color: string }> = {
  sahih: { label: "Sahih", arabic: "صحيح", icon: "✓", meaning: "MIZAN established or verified it", color: "#0ca30c" },
  hasan: { label: "Hasan", arabic: "حسن", icon: "◐", meaning: "evidence MIZAN gathered supports it", color: "#fab219" },
  daif: { label: "Da'if", arabic: "ضعيف", icon: "?", meaning: "only the language model's words", color: "#ec835a" },
  mawdu: { label: "Mawdu'", arabic: "موضوع", icon: "✗", meaning: "fabricated: an action, source or link that does not exist", color: "#d03b3b" },
};

export const ORDER: Grade[] = ["sahih", "hasan", "daif", "mawdu"];

export function isIsnad(value: unknown): value is IsnadSummary {
  if (!value || typeof value !== "object") return false;
  const item = value as Partial<IsnadSummary>;
  return typeof item.claims === "number" && !!item.counts && Array.isArray(item.ledger);
}

/** The balance bar: each grade's share of the claims, in order. */
export function segments(summary: IsnadSummary): { grade: Grade; share: number; count: number }[] {
  if (!summary.claims) return [];
  return ORDER.filter((grade) => summary.counts[grade] > 0).map((grade) => ({
    grade,
    count: summary.counts[grade],
    share: summary.counts[grade] / summary.claims,
  }));
}

/** "3 sahih · 1 da'if" */
export function headline(summary: IsnadSummary): string {
  return ORDER.filter((grade) => summary.counts[grade] > 0)
    .map((grade) => `${summary.counts[grade]} ${GRADES[grade].label.toLowerCase()}`)
    .join(" · ");
}

const PLAIN: Record<Grade, string> = {
  sahih: "verified",
  hasan: "supported",
  daif: "model's words only",
  mawdu: "fabricated",
};

/** "3 verified · 1 model's words only" — the same counts as `headline`, in plain words. */
export function plainHeadline(summary: IsnadSummary): string {
  return ORDER.filter((grade) => summary.counts[grade] > 0)
    .map((grade) => `${summary.counts[grade]} ${PLAIN[grade]}`)
    .join(" · ");
}

/** Tooltip that keeps the traditional grade names: "2 Sahih · 1 Da'if". */
export function gradeTerms(summary: IsnadSummary): string {
  return ORDER.filter((grade) => summary.counts[grade] > 0)
    .map((grade) => `${summary.counts[grade]} ${GRADES[grade].label}`)
    .join(" · ");
}

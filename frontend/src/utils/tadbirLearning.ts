/** Shapes what MIZAN learned about who does which work, for display. */

export interface RoutingRow {
  agent: string;
  role: string;
  intent: string;
  success_estimate: number;
  evidence: number;
  specialist: boolean;
}

export interface WorkRow {
  intent: string;
  label: string;
  leader: string;
  estimate: number;
  evidence: number;
  others: { agent: string; estimate: number }[];
}

export const WORK_LABELS: Record<string, string> = {
  build_project: "Build a project",
  build_and_run: "Write and run a program",
  qiyas: "Infer a rule from examples",
  silsila: "Find a sequence's rule",
  run_code: "Run code",
  compute: "Calculate",
  web_search: "Search the web",
  web_read: "Read a page",
  quran: "Quran",
  hadith: "Hadith",
  waqt: "Dates and Hijri calendar",
  recall: "Recall memory",
  capabilities: "Explain its tools",
};

/** One row per kind of work: the agent MIZAN currently trusts most, and the rest. */
export function workRows(rows: RoutingRow[]): WorkRow[] {
  const byIntent = new Map<string, RoutingRow[]>();
  for (const row of rows) {
    byIntent.set(row.intent, [...(byIntent.get(row.intent) ?? []), row]);
  }
  const order = Object.keys(WORK_LABELS);
  return [...byIntent.entries()]
    .sort(([a], [b]) => (order.indexOf(a) + 1 || 99) - (order.indexOf(b) + 1 || 99))
    .map(([intent, agents]) => {
      const ranked = [...agents].sort((a, b) => b.success_estimate - a.success_estimate);
      return {
        intent,
        label: WORK_LABELS[intent] ?? intent,
        leader: ranked[0].agent,
        estimate: ranked[0].success_estimate,
        evidence: agents.reduce((sum, row) => sum + row.evidence, 0),
        others: ranked.slice(1).map((row) => ({ agent: row.agent, estimate: row.success_estimate })),
      };
    });
}

export const percent = (value: number) => `${Math.round(value * 100)}%`;

/** "1 result learned", "3 results learned" (evidence is a weighted count). */
export function learnedCount(evidence: number): string {
  const count = Math.max(1, Math.round(evidence));
  return `${count} result${count === 1 ? "" : "s"} learned`;
}

/** One (family, language) row of /api/tadbir/teacher-calls. */
export interface TeacherFamily {
  family: string;
  language: string;
  requests: number;
  zero_call: number;
  zero_call_share: number | null;
  interval: [number, number] | null;
}

export const FAMILY_LABELS: Record<string, string> = {
  ...WORK_LABELS,
  converse: "Conversation",
  unplaced: "Not read by MIZAN",
  unrecorded: "Before this was recorded",
};

/** "62% (48%–75%)": the share answered with no model call and its 95 % interval. */
export function shareText(share: number | null, interval: [number, number] | null): string {
  if (share === null) return "no answers yet";
  return interval ? `${percent(share)} (${percent(interval[0])}–${percent(interval[1])})` : percent(share);
}

/** The families worth showing: most answers first, at most ``limit``. */
export function topFamilies(rows: TeacherFamily[], limit = 8): (TeacherFamily & { label: string })[] {
  return [...rows]
    .sort((a, b) => b.requests - a.requests)
    .slice(0, limit)
    .map((row) => ({ ...row, label: FAMILY_LABELS[row.family] ?? row.family }));
}


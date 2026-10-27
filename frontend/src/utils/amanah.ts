/** Amanah: instructions aimed at the AI that MIZAN found in outside text and ignored. */

export interface AmanahSummary {
  ignored: number;
  kinds: string[];
  sources: string[];
  hidden: boolean;
  examples: string[];
}

const KIND_LABELS: Record<string, string> = {
  override: "told the AI to ignore its instructions",
  role: "pretended to be a system or developer message",
  reply_control: "dictated a reply or code",
  exfiltration: "tried to send data out",
  concealment: "asked to hide something from you",
  tool_bait: "asked the AI to run a tool or command",
  hidden_text: "was hidden in invisible characters",
};

export function isAmanah(value: unknown): value is AmanahSummary {
  if (!value || typeof value !== "object") return false;
  const item = value as Partial<AmanahSummary>;
  return typeof item.ignored === "number" && item.ignored > 0 && Array.isArray(item.kinds);
}

/** One line for the chat: how many, and from where. */
export function amanahHeadline(summary: AmanahSummary): string {
  const count = summary.ignored === 1 ? "1 instruction" : `${summary.ignored} instructions`;
  const where = summary.sources.length ? ` in ${summary.sources.map(sourceLabel).join(", ")}` : "";
  return `Amanah: ignored ${count} aimed at the AI${where}`;
}

export function kindLabels(summary: AmanahSummary): string[] {
  return summary.kinds.map((kind) => KIND_LABELS[kind] ?? kind);
}

function sourceLabel(source: string): string {
  if (source.startsWith("mcp__")) return `connector ${source.split("__")[1] ?? ""}`.trim();
  return source.replace(/_/g, " ");
}

/**
 * exportChat.ts — client-side chat export serializers (pure functions, no React).
 *
 * The chat header's export menu offers three formats:
 *  - "markdown" — clean readable doc: title block, per-message `##` headers
 *    with role/timestamp/meta, content verbatim (code fences preserved).
 *  - "text"     — plain text: markdown stripped via copyFormat's stripMarkdown
 *    so it pastes cleanly anywhere.
 *  - "json"     — full-fidelity: every message with all metadata, plus
 *    export envelope (session, timestamp, count).
 *
 * Pure client-side: no backend endpoint. The download is a Blob + anchor
 * click, filename like `mizan-chat-<session>-<yyyymmdd-hhmm>.md`.
 */

import { stripMarkdown } from "./copyFormat.ts";

export interface ExportableMessage {
  id: number | string;
  role: "user" | "assistant" | "system";
  content: string;
  agent?: string;
  model?: string;
  ts?: string;
}

export type ExportFormatId = "markdown" | "text" | "json";

export interface ExportOptions {
  sessionId?: string;
  exportedAt?: Date;
}

const ROLE_LABEL: Record<ExportableMessage["role"], string> = {
  user: "User",
  assistant: "Assistant",
  system: "System",
};

const ROLE_ICON: Record<ExportableMessage["role"], string> = {
  user: "\u{1F9D1}",
  assistant: "\u{1F916}",
  system: "\u2699\uFE0F",
};

function metaSuffix(m: ExportableMessage): string {
  const bits = [m.agent, m.model].filter(Boolean);
  return bits.length > 0 ? ` (${bits.join(" \u00B7 ")})` : "";
}

function formatExportedAt(d: Date): string {
  return d.toISOString().replace("T", " ").slice(0, 16) + " UTC";
}

// ---------------------------------------------------------------------------
// Markdown — primary human format
// ---------------------------------------------------------------------------

export function exportMarkdown(
  messages: ExportableMessage[],
  opts: ExportOptions = {},
): string {
  const exportedAt = opts.exportedAt ?? new Date();
  const lines: string[] = [
    "# Mizan Chat Export",
    "",
    `- Exported: ${formatExportedAt(exportedAt)}`,
    `- Session: ${opts.sessionId ?? "unknown"}`,
    `- Messages: ${messages.length}`,
    "",
    "---",
    "",
  ];
  for (const m of messages) {
    const header =
      `## ${ROLE_ICON[m.role]} ${ROLE_LABEL[m.role]}${metaSuffix(m)}` +
      (m.ts ? ` \u2014 ${m.ts}` : "");
    lines.push(header, "", m.content, "");
  }
  return lines.join("\n").trimEnd() + "\n";
}

// ---------------------------------------------------------------------------
// Plain text — markdown stripped, pastes cleanly anywhere
// ---------------------------------------------------------------------------

export function exportText(
  messages: ExportableMessage[],
  opts: ExportOptions = {},
): string {
  const exportedAt = opts.exportedAt ?? new Date();
  const lines: string[] = [
    "MIZAN CHAT EXPORT",
    `Exported: ${formatExportedAt(exportedAt)} | Session: ${opts.sessionId ?? "unknown"} | Messages: ${messages.length}`,
    "=".repeat(60),
    "",
  ];
  for (const m of messages) {
    const header = `[${m.ts || "?"}] ${ROLE_LABEL[m.role].toUpperCase()}${metaSuffix(m)}:`;
    lines.push(header, stripMarkdown(m.content), "");
  }
  return lines.join("\n").trimEnd() + "\n";
}

// ---------------------------------------------------------------------------
// JSON — full fidelity, re-importable
// ---------------------------------------------------------------------------

export function exportJSON(
  messages: ExportableMessage[],
  opts: ExportOptions = {},
): string {
  return (
    JSON.stringify(
      {
        format: "mizan-chat-export",
        version: 1,
        session_id: opts.sessionId ?? null,
        exported_at: (opts.exportedAt ?? new Date()).toISOString(),
        message_count: messages.length,
        messages: messages.map((m) => ({
          id: m.id,
          role: m.role,
          content: m.content,
          agent: m.agent ?? null,
          model: m.model ?? null,
          ts: m.ts ?? null,
        })),
      },
      null,
      2,
    ) + "\n"
  );
}

// ---------------------------------------------------------------------------
// Filename + download trigger
// ---------------------------------------------------------------------------

const EXT: Record<ExportFormatId, string> = {
  markdown: "md",
  text: "txt",
  json: "json",
};

export function sanitizeSessionId(sessionId: string): string {
  return sessionId.replace(/[^A-Za-z0-9_-]/g, "").slice(0, 32) || "session";
}

export function buildExportFilename(
  sessionId: string,
  format: ExportFormatId,
  now: Date = new Date(),
): string {
  const stamp = now.toISOString().replace(/[-:]/g, "").slice(0, 13); // yyyymmddThhmm
  return `mizan-chat-${sanitizeSessionId(sessionId)}-${stamp}.${EXT[format]}`;
}

/** Trigger a client-side file download (Blob + temporary anchor). */
export function downloadExport(
  filename: string,
  mime: string,
  content: string,
): void {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

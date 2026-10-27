/** Words from your other chats that the model was shown for this answer. */

export interface RecalledLine {
  session_id: string;
  created_at: string;
  content: string;
}

const record = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

export function recalledLines(value: unknown): RecalledLine[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) =>
    record(item) && typeof item.content === "string" && item.content.trim()
      ? [{
          session_id: typeof item.session_id === "string" ? item.session_id : "",
          created_at: typeof item.created_at === "string" ? item.created_at : "",
          content: item.content,
        }]
      : [],
  );
}

export function recalledHeadline(lines: RecalledLine[]): string {
  const chats = new Set(lines.map((line) => line.session_id)).size;
  const what = lines.length === 1 ? "1 line" : `${lines.length} lines`;
  return `Used ${what} from ${chats === 1 ? "another chat" : `${chats} other chats`}`;
}

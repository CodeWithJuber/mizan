/** The person's chats for the sidebar: titles, search, paging, rename. */
import { useInfiniteQuery, useMutation, useQueryClient, type InfiniteData } from "@tanstack/react-query";
import { config } from "../../config";
import { authFetch } from "../../utils/authFetch";
import { useAuth } from "../../app/auth";
import { addToast } from "../../components/Toast";
import { CHAT_SESSIONS_KEY } from "./ChatProvider";

export interface ChatSessionRow {
  session_id: string;
  started_at: string;
  last_message_at: string;
  message_count: number;
  first_message?: string;
  title?: string | null;
}

interface Page {
  sessions: ChatSessionRow[];
  next_offset: number | null;
}

const PAGE = 30;

export function chatTitle(row: Pick<ChatSessionRow, "title" | "first_message"> | undefined): string {
  return row?.title?.trim() || row?.first_message?.trim() || "New chat";
}

export function useChatSessions(query: string) {
  const { token, revision } = useAuth();
  const q = query.trim();
  return useInfiniteQuery({
    queryKey: [...CHAT_SESSIONS_KEY, revision, q],
    enabled: Boolean(token),
    initialPageParam: 0,
    staleTime: 15_000,
    queryFn: async ({ pageParam, signal }): Promise<Page> => {
      const params = new URLSearchParams({ limit: String(PAGE), offset: String(pageParam) });
      if (q) params.set("q", q);
      const response = await authFetch(`${config.API_URL}/chat/sessions/list?${params}`, { signal });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      return { sessions: data.sessions ?? [], next_offset: data.next_offset ?? null };
    },
    getNextPageParam: (last) => last.next_offset ?? undefined,
  });
}

/** The current chat's row, from the chat list (loaded with the sidebar). */
export function useChatRow(sessionId: string): ChatSessionRow | undefined {
  const { data } = useChatSessions("");
  return data?.pages.flatMap((page) => page.sessions).find((row) => row.session_id === sessionId);
}

export function useRenameChat() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async ({ sessionId, title }: { sessionId: string; title: string }) => {
      const response = await authFetch(`${config.API_URL}/chat/${encodeURIComponent(sessionId)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title }),
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) {
        const detail = Array.isArray(body?.detail) ? body.detail[0]?.msg : body?.detail;
        throw new Error(typeof detail === "string" ? detail : `HTTP ${response.status}`);
      }
      return body as { session_id: string; title: string };
    },
    onMutate: async ({ sessionId, title }) => {
      // Show the new name at once; the server's answer settles it.
      client.setQueriesData<InfiniteData<Page>>({ queryKey: CHAT_SESSIONS_KEY }, (data) =>
        data && {
          ...data,
          pages: data.pages.map((page) => ({
            ...page,
            sessions: page.sessions.map((row) => (row.session_id === sessionId ? { ...row, title } : row)),
          })),
        },
      );
    },
    onError: (error: Error) => addToast({ type: "error", title: "Chat not renamed", description: error.message }),
    onSettled: () => client.invalidateQueries({ queryKey: CHAT_SESSIONS_KEY }),
  });
}

/** Today / Yesterday / Previous 7 days / Previous 30 days / Older, by last message. */
export function groupChats(rows: ChatSessionRow[], now = new Date()): { label: string; rows: ChatSessionRow[] }[] {
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const day = 86_400_000;
  const bounds: [string, number][] = [
    ["Today", startOfToday],
    ["Yesterday", startOfToday - day],
    ["Previous 7 days", startOfToday - 7 * day],
    ["Previous 30 days", startOfToday - 30 * day],
    ["Older", -Infinity],
  ];
  const groups = bounds.map(([label]) => ({ label, rows: [] as ChatSessionRow[] }));
  for (const row of rows) {
    const time = Date.parse(row.last_message_at || row.started_at) || 0;
    const index = bounds.findIndex(([, from]) => time >= from);
    groups[index === -1 ? groups.length - 1 : index].rows.push(row);
  }
  return groups.filter((group) => group.rows.length > 0);
}

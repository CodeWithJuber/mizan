/** Live agent activity for one chat run: tool calls, todo list, approvals, skills. */

export type ToolCallStatus = "running" | "done" | "failed";

export interface ToolCall {
  callId: string;
  name: string;
  input: unknown;
  status: ToolCallStatus;
  summary?: string;
  diff?: string;
  path?: string;
  durationMs?: number;
}

export type TodoStatus = "pending" | "in_progress" | "completed";

export interface TodoItem {
  content: string;
  status: TodoStatus;
}

export interface ApprovalRequest {
  approvalId: string;
  tool: string;
  input: unknown;
  category: string;
  reason: string;
  decision?: string;
}

export interface AgentActivity {
  tools: ToolCall[];
  todos: TodoItem[];
  approvals: ApprovalRequest[];
  skills: string[];
}

export const PERMISSION_MODES = ["auto_edits", "ask", "plan", "auto"] as const;
export type PermissionMode = (typeof PERMISSION_MODES)[number];

export const emptyActivity = (): AgentActivity => ({ tools: [], todos: [], approvals: [], skills: [] });

export const ACTIVITY_EVENTS = new Set([
  "tool_start", "tool_result", "todo", "approval_request", "approval_resolved", "skill",
]);

const text = (value: unknown, fallback = ""): string => typeof value === "string" ? value : fallback;
const TODO_STATUSES: TodoStatus[] = ["pending", "in_progress", "completed"];

/** Pure reducer: returns a new state for one server event (unknown events are ignored). */
export function reduceActivity(state: AgentActivity, event: Record<string, unknown>): AgentActivity {
  switch (event.type) {
    case "tool_start": {
      const callId = text(event.call_id);
      if (!callId || state.tools.some((t) => t.callId === callId)) return state;
      return {
        ...state,
        tools: [
          ...state.tools,
          { callId, name: text(event.name, "tool"), input: event.input, status: "running" as const },
        ].slice(-100),
      };
    }
    case "tool_result": {
      const callId = text(event.call_id);
      const update = (tool: ToolCall): ToolCall => tool.callId !== callId ? tool : {
        ...tool,
        status: event.ok === false ? "failed" : "done",
        summary: text(event.summary),
        diff: text(event.diff) || undefined,
        path: text(event.path) || undefined,
        durationMs: typeof event.duration_ms === "number" ? event.duration_ms : undefined,
      };
      if (!state.tools.some((t) => t.callId === callId)) {
        return reduceActivity(reduceActivity(state, { ...event, type: "tool_start" }), event);
      }
      return { ...state, tools: state.tools.map(update) };
    }
    case "todo": {
      const raw = Array.isArray(event.todos) ? event.todos : [];
      const todos = raw.flatMap((item): TodoItem[] => {
        if (!item || typeof item !== "object") return [];
        const record = item as Record<string, unknown>;
        const status = TODO_STATUSES.includes(record.status as TodoStatus) ? record.status as TodoStatus : "pending";
        const content = text(record.content).trim();
        return content ? [{ content, status }] : [];
      });
      return { ...state, todos };
    }
    case "approval_request": {
      const approvalId = text(event.approval_id);
      if (!approvalId || state.approvals.some((a) => a.approvalId === approvalId)) return state;
      return {
        ...state,
        approvals: [...state.approvals, {
          approvalId, tool: text(event.tool, "tool"), input: event.input,
          category: text(event.category, "execute"), reason: text(event.reason),
        }],
      };
    }
    case "approval_resolved": {
      const approvalId = text(event.approval_id);
      return {
        ...state,
        approvals: state.approvals.map((a) => a.approvalId === approvalId ? { ...a, decision: text(event.decision, "deny") } : a),
      };
    }
    case "skill": {
      const name = text(event.name);
      return name && !state.skills.includes(name) ? { ...state, skills: [...state.skills, name] } : state;
    }
    default:
      return state;
  }
}

export const hasActivity = (state: AgentActivity | undefined): boolean =>
  !!state && (state.tools.length > 0 || state.todos.length > 0 || state.approvals.length > 0 || state.skills.length > 0);

export const pendingApprovals = (state: AgentActivity): ApprovalRequest[] =>
  state.approvals.filter((a) => !a.decision);

/** Short human label for a tool call, e.g. "Edit src/app.py" or "Run pytest". */
export function toolLabel(call: ToolCall): string {
  const input = (call.input && typeof call.input === "object" ? call.input : {}) as Record<string, unknown>;
  const path = text(input.path) || call.path || "";
  const verbs: Record<string, string> = {
    workspace_read: "Read", workspace_write: "Write", workspace_edit: "Edit", workspace_glob: "Find",
    workspace_grep: "Search", workspace_run: "Run", workspace_tree: "List files", workspace_git: "Git",
    workspace_diff: "Diff", workspace_checkpoint: "Checkpoint", workspace_artifact: "Publish",
    web_search: "Web search", web_browse: "Open", todo_write: "Update plan", activate_skill: "Use skill",
    read_skill_file: "Read skill file",
  };
  const detail = path || text(input.pattern) || text(input.command) || text(input.query) || text(input.url) || text(input.name);
  if (call.name.startsWith("mcp__")) {
    const [, server = "", tool = ""] = call.name.split("__");
    return `${server} · ${tool}`;
  }
  const verb = verbs[call.name] ?? call.name;
  return detail ? `${verb} ${detail.length > 80 ? `${detail.slice(0, 77)}…` : detail}` : verb;
}

import {
  emptyActivity, hasActivity, pendingApprovals, reduceActivity, toolLabel,
} from "./agentActivity.ts";

let checks = 0;
function check(name: string, condition: boolean) {
  if (!condition) throw new Error(name);
  checks++;
}

let state = emptyActivity();
check("empty state has no activity", !hasActivity(state));
state = reduceActivity(state, { type: "tool_start", call_id: "c1", name: "workspace_edit", input: { path: "src/app.py" } });
state = reduceActivity(state, { type: "tool_start", call_id: "c1", name: "workspace_edit", input: {} });
check("tool start is recorded once", state.tools.length === 1 && state.tools[0].status === "running");
state = reduceActivity(state, { type: "tool_result", call_id: "c1", name: "workspace_edit", ok: true, diff: "+x", duration_ms: 12 });
check("tool result pairs by call id", state.tools[0].status === "done" && state.tools[0].diff === "+x" && state.tools[0].durationMs === 12);
state = reduceActivity(state, { type: "tool_result", call_id: "c2", name: "workspace_run", ok: false, summary: "exit 1" });
check("result without start still appears as failed", state.tools[1].status === "failed" && state.tools[1].summary === "exit 1");
state = reduceActivity(state, { type: "todo", todos: [{ content: "Read", status: "completed" }, { content: "", status: "pending" }, { content: "Fix", status: "weird" }] });
check("todos keep valid items and default status", state.todos.length === 2 && state.todos[1].status === "pending");
state = reduceActivity(state, { type: "approval_request", approval_id: "a1", tool: "workspace_run", input: { command: "pytest" }, category: "execute" });
check("approval pending", pendingApprovals(state).length === 1);
state = reduceActivity(state, { type: "approval_resolved", approval_id: "a1", decision: "allow" });
check("approval resolved", pendingApprovals(state).length === 0 && state.approvals[0].decision === "allow");
state = reduceActivity(state, { type: "skill", name: "web-app-builder" });
state = reduceActivity(state, { type: "skill", name: "web-app-builder" });
check("skills deduplicated", state.skills.length === 1);
check("unknown events ignored", reduceActivity(state, { type: "chat_stream", chunk: "x" }) === state);
check("labels are readable", toolLabel(state.tools[0]) === "Edit src/app.py");
check("connector labels show server and tool", toolLabel({ callId: "x", name: "mcp__github__list_issues", input: {}, status: "done" }) === "github · list_issues");

console.log(`${checks} agent activity checks passed`);

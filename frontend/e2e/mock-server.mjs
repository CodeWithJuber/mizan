// A stand-in MIZAN API for the browser tests: the routes the app calls on
// load, chat history, and /api/chat/stream answering in real SSE frames,
// chunk by chunk, so streaming, stop and approvals can be exercised.
// Standard library only. Port: MOCK_PORT (default 8765).
import http from "node:http";
import { createHash, randomUUID } from "node:crypto";

const PORT = Number(process.env.MOCK_PORT || 8765);
const TOKEN = "e2e-token";

const agents = [
  { id: "agent-1", name: "Khalifah", role: "wakil", state: "resting", nafs_level: 3, total_tasks: 4, success_rate: 0.75, hikmah_count: 2, tools: ["bash"], model: "claude-haiku-5-5" },
  { id: "agent-2", name: "Katib", role: "katib", state: "resting", nafs_level: 1, total_tasks: 0, success_rate: 0, hikmah_count: 0, tools: [], model: "claude-haiku-5-5" },
];

/** session_id -> { title, messages: [{id, role, content, created_at, metadata}] } */
const sessions = new Map();
const approvals = new Map();
const active = new Map();
let nextId = 1;

const ANSWER = [
  "Sabr and shukr are two halves of faith.\n\n",
  "| Quality | Meaning |\n|---|---|\n",
  "| Sabr | Patience in hardship |\n",
  "| Shukr | Gratitude in ease |\n\n",
  "A loop in JavaScript:\n\n```js\n",
  "for (let i = 0; i < 3; i++) console.log(i);\n",
  "```\n",
];

const ISNAD = {
  counts: { sahih: 2, hasan: 1, daif: 1, mawdu: 0 },
  claims: 4,
  supported: 0.75,
  ledger: [
    { text: "Sabr is patience in hardship.", kind: "sentence", grade: "sahih", support: ["Lane's Lexicon"] },
    { text: "Shukr is gratitude.", kind: "sentence", grade: "sahih", support: ["Lane's Lexicon"] },
    { text: "Two halves of faith.", kind: "sentence", grade: "hasan", support: ["Bayhaqi, Shu'ab al-Iman"] },
    { text: "A loop prints three numbers.", kind: "sentence", grade: "daif", support: [] },
  ],
};

function json(res, status, body) {
  res.writeHead(status, { "Content-Type": "application/json" });
  res.end(JSON.stringify(body));
}

function readBody(req) {
  return new Promise((resolve) => {
    let data = "";
    req.on("data", (chunk) => (data += chunk));
    req.on("end", () => {
      try {
        resolve(data ? JSON.parse(data) : {});
      } catch {
        resolve({});
      }
    });
  });
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// Projects: files in memory, content-addressed checkpoints (a copy of the files).
const projects = new Map();
/** session_id -> Set of "always" keys */
const always = new Map();
const sha = (text) => createHash("sha256").update(text).digest("hex");
const STARTER = {
  "index.html": '<div id="root"></div>\n<script type="module" src="/src/main.jsx"></script>\n',
  "src/App.jsx": "export default function App() {\n  return <h1>Hello</h1>;\n}\n",
};

function makeProject(name) {
  const now = new Date().toISOString();
  const project = { id: "ws-" + randomUUID().slice(0, 8), name, created_at: now, updated_at: now, files: new Map(Object.entries(STARTER)), checkpoints: [] };
  projects.set(project.id, project);
  return project;
}

function checkpoint(project, kind, message) {
  const item = { id: "cp-" + randomUUID().slice(0, 8), kind, message, created_at: new Date().toISOString(), files: new Map(project.files) };
  project.checkpoints.unshift(item);
  return item;
}

const publicCheckpoint = ({ files: _files, ...item }) => item;
const publicProject = ({ files: _files, checkpoints: _checkpoints, ...item }) => item;

function unified(path, before, after) {
  const lines = (text) => (text ? text.replace(/\n$/, "").split("\n") : []);
  const old = lines(before);
  const now = lines(after);
  return [
    `--- a/${path}`, `+++ b/${path}`, `@@ -1,${old.length} +1,${now.length} @@`,
    ...old.map((line) => `-${line}`), ...now.map((line) => `+${line}`),
  ].join("\n");
}

function changes(project, base) {
  const files = [];
  for (const path of new Set([...base.files.keys(), ...project.files.keys()])) {
    const before = base.files.get(path);
    const after = project.files.get(path);
    if (before === after) continue;
    const status = before === undefined ? "added" : after === undefined ? "deleted" : "modified";
    files.push({ path, status, diff: unified(path, before ?? "", after ?? "") });
  }
  return files.sort((a, b) => a.path.localeCompare(b.path));
}

async function workspaces(req, res, url) {
  const parts = url.pathname.replace(/^\/api\/workspaces\/?/, "").split("/").filter(Boolean).map(decodeURIComponent);
  const method = req.method;
  if (!parts.length) {
    if (method === "POST") {
      const body = await readBody(req);
      return json(res, 200, publicProject(makeProject(String(body.name || "project"))));
    }
    return json(res, 200, {
      workspaces: [...projects.values()].map(publicProject),
      capabilities: { execution_available: false, execution_detail: "No runner in the browser tests", hardware_inspection: false },
    });
  }
  const project = projects.get(parts[0]);
  if (!project) return json(res, 404, { detail: "Workspace not found" });
  const [, what, id, action] = parts;
  const path = url.searchParams.get("path") || "";
  if (!what) {
    if (method === "PATCH") {
      project.name = String((await readBody(req)).name || project.name);
      return json(res, 200, publicProject(project));
    }
    if (method === "DELETE") {
      projects.delete(project.id);
      return json(res, 200, { deleted: project.id });
    }
    return json(res, 200, publicProject(project));
  }
  if (what === "tree") {
    return json(res, 200, { files: [...project.files.entries()].map(([p, text]) => ({ path: p, kind: "file", size: text.length })), truncated: false });
  }
  if (what === "files") return json(res, 200, { files: Object.fromEntries(project.files) });
  if (what === "file") {
    if (method === "PUT") {
      const body = await readBody(req);
      const current = project.files.get(body.path);
      if (body.expected_sha256 && current !== undefined && sha(current) !== body.expected_sha256) {
        return json(res, 409, { detail: "The file changed since it was opened" });
      }
      project.files.set(body.path, String(body.content ?? ""));
      return json(res, 200, { path: body.path, sha256: sha(project.files.get(body.path)) });
    }
    if (method === "DELETE") {
      project.files.delete(path);
      return json(res, 200, { deleted: path });
    }
    if (!project.files.has(path)) return json(res, 404, { detail: "No such file" });
    return json(res, 200, { path, content: project.files.get(path), sha256: sha(project.files.get(path)) });
  }
  if (what === "diff") {
    const base = project.checkpoints.find((item) => item.id === url.searchParams.get("checkpoint_id"));
    if (!base) return json(res, 404, { detail: "No such checkpoint" });
    return json(res, 200, { files: changes(project, base), truncated: false });
  }
  if (what === "checkpoints") {
    if (!id) return json(res, 200, { checkpoints: project.checkpoints.map(publicCheckpoint) });
    const item = project.checkpoints.find((cp) => cp.id === id);
    if (!item) return json(res, 404, { detail: "No such checkpoint" });
    if (action === "file") {
      if (!item.files.has(path)) return json(res, 404, { detail: "Not in this checkpoint" });
      return json(res, 200, { path, content: item.files.get(path) });
    }
    if (action === "restore" && method === "POST") {
      const body = await readBody(req);
      const before = checkpoint(project, "restore", "Before a restore");
      const paths = Array.isArray(body.paths) ? body.paths : [...new Set([...item.files.keys(), ...project.files.keys()])];
      const restored = [];
      const removed = [];
      for (const p of paths) {
        if (item.files.has(p)) {
          if (project.files.get(p) !== item.files.get(p)) restored.push(p);
          project.files.set(p, item.files.get(p));
        } else if (project.files.delete(p)) {
          removed.push(p);
        }
      }
      return json(res, 200, { checkpoint: publicCheckpoint(item), restored, removed, before: publicCheckpoint(before) });
    }
  }
  return json(res, 200, {});
}

const TODO_APP = "import { useState } from \"react\";\nimport Todo from \"./Todo\";\n\nexport default function App() {\n  const [items, setItems] = useState([]);\n  return <Todo items={items} onAdd={(text) => setItems([...items, text])} />;\n}\n";
const TODO = "export default function Todo({ items, onAdd }) {\n  return <ul>{items.map((item) => <li key={item}>{item}</li>)}</ul>;\n}\n";

/** A coding message: the chat's project (made when it has none), a checkpoint, changes. */
async function codingTurn(body, chat, send, run) {
  let project = projects.get(body.workspace_id || chat.workspace_id || "");
  if (!project) {
    project = makeProject("todo-app");
    chat.workspace_id = project.id;
    send("workspace", { workspace_id: project.id, name: project.name, created: true });
  }
  const turn = checkpoint(project, "turn", "Before a chat message");
  send("checkpoint", { workspace_id: project.id, checkpoint_id: turn.id, checkpoint_kind: "turn", reused: false, created_at: turn.created_at });
  const user = chat.messages[chat.messages.length - 1];
  user.metadata.checkpoint = { workspace_id: project.id, id: turn.id };
  if (body.permission_mode === "plan") {
    return { project, turn, text: "Plan:\n\n1. Add a `Todo` list component.\n2. Keep the items in `App` state.\n\nNothing has changed yet." };
  }
  const allowed = always.get(body.session_id) ?? new Set();
  if (body.permission_mode === "ask" && !allowed.has("workspace_write")) {
    const approvalId = "ap-" + body.request_id;
    approvals.set(approvalId, null);
    send("approval_request", {
      approval_id: approvalId, tool: "workspace_write", input: { path: "src/Todo.jsx", workspace_id: project.id },
      category: "edit", reason: "Writes a file", preview: { path: "src/Todo.jsx", diff: unified("src/Todo.jsx", "", TODO), truncated: false, new_file: true },
    });
    for (let i = 0; i < 100 && approvals.get(approvalId) === null && !run.stopped; i++) await sleep(100);
    const decision = approvals.get(approvalId) ?? "expired";
    if (decision === "always") {
      allowed.add("workspace_write");
      always.set(body.session_id, allowed);
    }
    send("approval_resolved", { approval_id: approvalId, decision });
    if (decision === "deny" || decision === "expired") return { project, turn, text: "Nothing was changed: the edit was declined." };
  }
  send("tool_start", { call_id: "w1", name: "workspace_write", input: { path: "src/Todo.jsx" } });
  project.files.set("src/Todo.jsx", TODO);
  project.files.set("src/App.jsx", TODO_APP);
  project.updated_at = new Date().toISOString();
  send("tool_result", { call_id: "w1", ok: true, summary: "2 files changed", duration_ms: 40 });
  send("preview", { workspace_id: project.id, port: 5173, preview_url: `/api/workspaces/preview/cap-${project.id}/5173/` });
  return {
    project, turn,
    text: body.plan_approved ? "Carried out the approved plan: `src/Todo.jsx` is new and `src/App.jsx` uses it." : "Built the todo app: `src/Todo.jsx` is new and `src/App.jsx` uses it.",
  };
}

function session(id) {
  if (!sessions.has(id)) sessions.set(id, { title: null, messages: [], started: new Date().toISOString() });
  return sessions.get(id);
}

async function stream(req, res) {
  const body = await readBody(req);
  const sid = body.session_id;
  const rid = body.request_id;
  const content = String(body.content || "");
  const chat = session(sid);
  chat.messages.push({ id: nextId++, role: "user", content, created_at: new Date().toISOString(), metadata: { request_id: rid } });
  res.writeHead(200, { "Content-Type": "text/event-stream", "Cache-Control": "no-cache", Connection: "keep-alive" });
  const run = { stopped: false };
  active.set(sid, run);
  const send = (type, data = {}) => {
    if (res.writableEnded) return;
    res.write(`event: ${type}\ndata: ${JSON.stringify({ ...data, type, session_id: sid, request_id: rid })}\n\n`);
  };
  const slow = /slow/i.test(content);
  const needsApproval = /approve/i.test(content);
  send("status", { status: "accepted" });
  if (/todo app|dark mode|approved plan/i.test(content) || body.fix) {
    const { project, turn, text } = await codingTurn(body, chat, send, run);
    for (const chunk of text.match(/[^\n]+\n*|\n+/g) ?? [text]) {
      send("stream", { chunk, message_id: "m-" + rid });
      await sleep(40);
    }
    active.delete(sid);
    chat.messages.push({ id: nextId++, role: "assistant", content: text, created_at: new Date().toISOString(), metadata: { request_id: rid, message_id: "m-" + rid } });
    send("chat_complete", {
      response: text, agent: "Khalifah", message_id: "m-" + rid, workspace_id: project.id,
      checkpoint: { workspace_id: project.id, id: turn.id },
      usage: { model: "claude-haiku-5-5", input_tokens: 400, output_tokens: 60, cost_usd: 0.0006, cost_estimated: true },
    });
    return res.end();
  }
  await sleep(150);
  send("thinking", { phase: "comprehension", content: "Reading what was asked", confidence: 0.8, message_id: "m-" + rid });
  await sleep(150);
  send("tool_start", { call_id: "c1", name: "quran_search", input: { query: "sabr" } });
  await sleep(200);
  send("tool_result", { call_id: "c1", ok: true, summary: "2 ayahs found", duration_ms: 180 });
  if (needsApproval) {
    const approvalId = "ap-" + rid;
    approvals.set(approvalId, null);
    send("approval_request", { approval_id: approvalId, tool: "workspace_write", input: { path: "index.html" }, category: "edit", reason: "Writes a file" });
    for (let i = 0; i < 100 && approvals.get(approvalId) === null && !run.stopped; i++) await sleep(100);
    send("approval_resolved", { approval_id: approvalId, decision: approvals.get(approvalId) ?? "expired" });
  }
  let text = "";
  for (const chunk of ANSWER) {
    if (run.stopped) break;
    text += chunk;
    send("stream", { chunk, message_id: "m-" + rid });
    await sleep(slow ? 600 : 60);
  }
  active.delete(sid);
  if (run.stopped) {
    chat.messages.push({ id: nextId++, role: "assistant", content: text, created_at: new Date().toISOString(), metadata: { request_id: rid, partial: true, status: "stopped" } });
    send("chat_stopped", { response: text });
  } else {
    chat.messages.push({ id: nextId++, role: "assistant", content: text, created_at: new Date().toISOString(), metadata: { request_id: rid, message_id: "m-" + rid } });
    send("chat_complete", {
      response: text,
      agent: "Khalifah",
      message_id: "m-" + rid,
      usage: { model: "claude-haiku-5-5", input_tokens: 812, output_tokens: 96, cost_usd: 0.0012, cost_estimated: true, isnad: ISNAD, completion_status: "evidence_observed" },
    });
  }
  res.end();
}

// The person's saved choices (learning, training, reply preferences).
const preferences = new Map();

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, `http://localhost:${PORT}`);
  const path = url.pathname;
  const method = req.method;

  if (path === "/api/health") return json(res, 200, { status: "ok", version: "3.3.0-e2e" });
  if (path === "/api/auth/login" && method === "POST") {
    const body = await readBody(req);
    if (body.password !== "secret") return json(res, 401, { detail: "Invalid credentials" });
    return json(res, 200, { token: TOKEN, user_id: "u1", username: body.username, roles: ["admin"] });
  }
  const auth = req.headers.authorization || "";
  if (path.startsWith("/api/") && auth !== `Bearer ${TOKEN}`) return json(res, 401, { detail: "Not authenticated" });

  if (path === "/api/auth/me") return json(res, 200, { user_id: "u1", username: "tester", roles: ["admin"], credential: "token", issued_at: null, expires_at: null });
  if (path === "/api/auth/logout") return json(res, 200, { ok: true });
  if (path === "/api/agents") return json(res, 200, { agents });
  if (path === "/api/providers") return json(res, 200, { providers: [{ name: "anthropic", configured: true, display: "Anthropic" }], default_model: "claude-haiku-5-5" });
  if (path === "/api/debug/status") return json(res, 200, { enabled: true });
  if (path === "/api/agent-skills") return json(res, 200, { skills: [{ name: "tafsir-notes", description: "Notes from tafsir", enabled: true }], shadowed: [] });
  if (path === "/api/chat/stream" && method === "POST") return stream(req, res);
  if (path === "/api/workspaces" || path.startsWith("/api/workspaces/")) return workspaces(req, res, url);
  if (path === "/api/memory/list") return json(res, 200, { results: [] });
  if (path === "/api/chat/preferences") return json(res, 200, { preferences: [...preferences.values()] });
  if (path === "/api/tadrib/lessons") return json(res, 200, { lessons: [], total: 0, limit: 20, offset: 0 });
  if (path.startsWith("/api/chat/preferences/")) {
    const key = decodeURIComponent(path.slice("/api/chat/preferences/".length));
    if (method === "DELETE") return json(res, 200, { deleted: preferences.delete(key) });
    const { value } = await readBody(req);
    const saved = { key, value: String(value).trim().toLowerCase(), source: "explicit_user_preference", updated_at: new Date().toISOString() };
    preferences.set(key, saved);
    return json(res, 200, saved);
  }
  if (path === "/api/knowledge/sources") return json(res, 200, { sources: [] });
  if (path === "/api/muraqabah") {
    return json(res, 200, {
      place: null, today: null, watchers: [], delivered_today: 0, budget: 6, attention: {},
      session_id: "muraqabah-u1", methods: ["MuslimWorldLeague", "Karachi"],
    });
  }
  if (path === "/api/muraqabah/notices") return json(res, 200, { notices: [] });
  if (path === "/api/settings/runtime") {
    return json(res, 200, {
      groups: ["Chat"],
      settings: [{
        key: "MIZAN_CHAT_EFFORT", group: "Chat", label: "Reasoning effort", kind: "choice", description: "How hard the model thinks.",
        default: "medium", choices: ["low", "medium", "high"], minimum: null, maximum: null, apply: "live",
        source: "default", restart_pending: false, value: "medium", is_set: false,
      }],
      restart_required: [],
    });
  }
  if (path === "/api/chat/sessions/list") {
    const q = (url.searchParams.get("q") || "").toLowerCase();
    const project = url.searchParams.get("workspace_id");
    // A slow lookup of a project's chat: a message typed meanwhile must not be lost.
    if (project) await sleep(1500);
    const rows = [...sessions.entries()]
      .filter(([, chat]) => chat.messages.length && (!project || chat.workspace_id === project))
      .map(([id, chat]) => ({
        session_id: id,
        started_at: chat.started,
        last_message_at: chat.messages[chat.messages.length - 1].created_at,
        message_count: chat.messages.length,
        first_message: chat.messages.find((m) => m.role === "user")?.content.slice(0, 80),
        title: chat.title,
      }))
      .filter((row) => !q || (row.title || "").toLowerCase().includes(q) || (row.first_message || "").toLowerCase().includes(q))
      .reverse();
    return json(res, 200, { sessions: rows, limit: 30, offset: 0, next_offset: null, q: q || null });
  }
  let match = /^\/api\/chat\/approvals\/([^/]+)$/.exec(path);
  if (match && method === "POST") {
    const body = await readBody(req);
    approvals.set(match[1], body.decision);
    return json(res, 200, { ok: true });
  }
  match = /^\/api\/chat\/([^/]+)\/always(?:\/([^/]+))?$/.exec(path);
  if (match) {
    const sid = decodeURIComponent(match[1]);
    const allowed = always.get(sid) ?? new Set();
    if (method === "DELETE") {
      const key = decodeURIComponent(match[2] || "");
      if (!allowed.delete(key)) return json(res, 404, { detail: "Nothing was allowed always under that name in this chat" });
      return json(res, 200, { session_id: sid, revoked: key });
    }
    return json(res, 200, { session_id: sid, always: [...allowed].map((tool) => ({ tool, created: new Date().toISOString() })) });
  }
  match = /^\/api\/chat\/([^/]+)\/run-state$/.exec(path);
  if (match) return json(res, 200, { state: "idle", request: null, history_saved: null });
  match = /^\/api\/chat\/([^/]+)\/stop$/.exec(path);
  if (match && method === "POST") {
    const run = active.get(decodeURIComponent(match[1]));
    if (run) run.stopped = true;
    return json(res, 200, { stopped: Boolean(run) });
  }
  match = /^\/api\/chat\/([^/]+)$/.exec(path);
  if (match) {
    const sid = decodeURIComponent(match[1]);
    if (method === "PATCH") {
      const body = await readBody(req);
      if ("workspace_id" in body) {
        // Binding a project makes the chat (it may have no messages yet).
        session(sid).workspace_id = body.workspace_id || null;
        return json(res, 200, { session_id: sid, workspace_id: session(sid).workspace_id });
      }
      if (!sessions.has(sid)) return json(res, 404, { detail: "Session not found" });
      sessions.get(sid).title = String(body.title || "").trim();
      return json(res, 200, { session_id: sid, title: sessions.get(sid).title });
    }
    if (method === "DELETE") {
      const existed = sessions.delete(sid);
      return json(res, 200, { session_id: sid, removed: { messages: existed ? 2 : 0 }, checked: 12, traces: 0 });
    }
    if (!sessions.has(sid)) return json(res, 404, { detail: "Session not found" });
    const chat = sessions.get(sid);
    return json(res, 200, { session_id: sid, messages: chat.messages, has_more: false, workspace_id: chat.workspace_id ?? null });
  }
  if (path.startsWith("/api/")) return json(res, 200, {});
  res.writeHead(404);
  res.end();
});

server.listen(PORT, () => console.log(`mock MIZAN API on :${PORT}`));

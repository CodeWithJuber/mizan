// A stand-in MIZAN API for the browser tests: the routes the app calls on
// load, chat history, and /api/chat/stream answering in real SSE frames,
// chunk by chunk, so streaming, stop and approvals can be exercised.
// Standard library only. Port: MOCK_PORT (default 8765).
import http from "node:http";

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
  if (path === "/api/workspaces") return json(res, 200, { workspaces: [] });
  if (path === "/api/memory/list") return json(res, 200, { results: [] });
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
    const rows = [...sessions.entries()]
      .filter(([, chat]) => chat.messages.length)
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
      if (!sessions.has(sid)) return json(res, 404, { detail: "Session not found" });
      sessions.get(sid).title = String(body.title || "").trim();
      return json(res, 200, { session_id: sid, title: sessions.get(sid).title });
    }
    if (method === "DELETE") {
      const existed = sessions.delete(sid);
      return json(res, 200, { session_id: sid, removed: { messages: existed ? 2 : 0 }, checked: 12, traces: 0 });
    }
    if (!sessions.has(sid)) return json(res, 404, { detail: "Session not found" });
    return json(res, 200, { session_id: sid, messages: sessions.get(sid).messages, has_more: false });
  }
  if (path.startsWith("/api/")) return json(res, 200, {});
  res.writeHead(404);
  res.end();
});

server.listen(PORT, () => console.log(`mock MIZAN API on :${PORT}`));

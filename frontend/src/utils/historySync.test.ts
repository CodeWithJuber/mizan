/**
 * Unit tests for utils/historySync.ts (pure fns).
 *
 * No test runner is installed in this repo — this file is self-running:
 *   node frontend/src/utils/historySync.test.ts   (Node >= 22.6, type stripping)
 * Exit code 0 = all pass, 1 = failure. Also typechecked by `tsc --noEmit`.
 */

import {
  historyDedupeKey,
  hydrateCachedMessages,
  mergeHistoryMessages,
  fetchChatHistoryWithRetry,
  type HistoryMessage,
} from "./historySync.ts";

declare const process: { exit(code: number): void };

let passed = 0;
let failed = 0;

function check(name: string, cond: boolean): void {
  if (cond) {
    passed++;
  } else {
    failed++;
    console.error(`FAIL: ${name}`);
  }
}

function resp(status: number, body: unknown): Response {
  return {
    status,
    ok: status >= 200 && status < 300,
    json: async () => body,
  } as Response;
}

// A late cache read must not erase a newly delivered result or another session.
const cached = [{ role: "user", content: "Old prompt" }];
const live = [
  { role: "user", content: "New prompt" },
  { role: "assistant", content: "", error: { message: "Connection interrupted" } },
];
check("cache seeds only an empty owned view", hydrateCachedMessages([], cached, true) === cached);
check("late cache keeps live answer/error state", hydrateCachedMessages(live, cached, true) === live);
const switched: HistoryMessage[] = [];
check("old-session cache cannot populate a new empty session", hydrateCachedMessages(switched, cached, false) === switched);
check("missing cache preserves current state", hydrateCachedMessages(live, null, true) === live);

// --- dedupe keys ---
check(
  "server id key",
  historyDedupeKey({ id: 42, role: "user", content: "hi" }) === "srv:42",
);
const k1 = historyDedupeKey({ role: "user", content: "hi", ts: "t" });
const k2 = historyDedupeKey({ role: "user", content: "hi", ts: "t" });
const k3 = historyDedupeKey({ role: "user", content: "bye", ts: "t" });
check("local key stable", k1 === k2);
check("local key differs on content", k1 !== k3);
check("local key has local prefix", k1.startsWith("local:user:"));

// --- merge: server wins, local-only appended ---
{
  const server: HistoryMessage[] = [
    { id: 1, role: "user", content: "hello" },
    { id: 2, role: "assistant", content: "hi there" },
  ];
  const local: HistoryMessage[] = [
    // optimistic echo of "hello" — dropped (same role+content on server)
    { id: 1690000000000, role: "user", content: "hello", ts: "x" },
    // genuinely new local message — kept, appended
    { id: 1690000000001, role: "user", content: "are you there?", ts: "y" },
  ];
  const merged = mergeHistoryMessages(server, local);
  check("merge length", merged.length === 3);
  check("merge order server first", merged[0].id === 1 && merged[1].id === 2);
  check("merge keeps local-only", merged[2].content === "are you there?");
}

// --- merge: exact server key match dropped ---
{
  const server: HistoryMessage[] = [{ id: 7, role: "user", content: "a" }];
  const local: HistoryMessage[] = [{ id: 7, role: "user", content: "a" }];
  check("merge exact dup", mergeHistoryMessages(server, local).length === 1);
}

// --- merge: empty server keeps all local ---
{
  const local: HistoryMessage[] = [{ role: "user", content: "x" }];
  check("merge empty server", mergeHistoryMessages([], local).length === 1);
}

// Older empty/partial failures must never erase a later request's notice.
const oldHistory: HistoryMessage[] = [
  { id: 1, role: "user", content: "Old question", requestId: "old-request" },
  { id: 2, role: "assistant", content: "", interrupted: true, requestId: "old-request", messageId: "old-message" },
];
for (const code of ["chat_transport_error", "history_save_failed"]) {
  const latest: HistoryMessage[] = [
    { id: 100, role: "user", content: "New question" },
    { id: 101, role: "assistant", content: "", requestId: "new-request", error: { code, message: "New request failed" } },
  ];
  const merged = mergeHistoryMessages(oldHistory, latest);
  check(`${code} survives resync after an older empty cancellation`, merged.length === 4 && merged[3].error?.code === code && merged[3].requestId === "new-request");
}
const noServerIdentity: HistoryMessage = { role: "assistant", content: "", error: { message: "Fetch failed before a server message ID existed" } };
check("pre-stream failure without server identity survives resync", mergeHistoryMessages(oldHistory, [noServerIdentity]).includes(noServerIdentity));
const partialNew: HistoryMessage = { id: 102, role: "assistant", content: "same partial", requestId: "new-request", error: { message: "New connection interrupted" } };
check("identical partial text on different failed requests is not a duplicate", mergeHistoryMessages([{ ...oldHistory[1], content: partialNew.content }], [partialNew]).length === 2);
const localNotice: HistoryMessage = { id: 200, role: "assistant", content: "partial tail", requestId: "same-request", error: { code: "chat_transport_error", message: "Connection interrupted before delivery completed" } };
const savedCancellation: HistoryMessage = { id: 3, role: "assistant", content: "partial", requestId: "same-request", messageId: "server-message", interrupted: true };
const reconciled = mergeHistoryMessages([savedCancellation], [localNotice]);
check("matching request identity reconciles without duplicate bubbles", reconciled.length === 1 && reconciled[0].id === 3);
check("matching cancellation retains the more detailed local notice", reconciled[0].error?.message === localNotice.error?.message && reconciled[0].content === "partial tail" && reconciled[0].interrupted === true);
check("stable message identity also reconciles failures", mergeHistoryMessages([{ ...savedCancellation, requestId: undefined }], [{ ...localNotice, requestId: undefined, messageId: "server-message" }]).length === 1);
check("matching cached database identity still reconciles failure rows", mergeHistoryMessages([savedCancellation], [{ ...savedCancellation, error: localNotice.error }]).length === 1);
const delivered = mergeHistoryMessages([{ ...savedCancellation, interrupted: false, content: "The full answer" }], [localNotice]);
check("same-request saved answer replaces an obsolete local transport notice", delivered.length === 1 && delivered[0].error === undefined && delivered[0].content === "The full answer");
check("known different requests keep identical successful answers", mergeHistoryMessages([{ id: 10, role: "assistant", content: "4", requestId: "old-request" }], [{ id: 11, role: "assistant", content: "4", requestId: "new-request" }]).length === 2);
check("repeated user text with a new request identity survives resync", mergeHistoryMessages([{ id: 12, role: "user", content: "Continue", requestId: "old-request" }], [{ id: 13, role: "user", content: "Continue", requestId: "new-request" }]).length === 2);
const stoppedDraft: HistoryMessage = { ...localNotice, content: "  exact partial\n\n", stopped: true, interrupted: false, error: undefined };
const restoredStop = mergeHistoryMessages([{ ...savedCancellation, content: "  exact" }], [stoppedDraft]);
check("explicit local Stop retains exact bytes and identity through server resync", restoredStop.length === 1 && restoredStop[0].content === stoppedDraft.content && restoredStop[0].stopped === true && restoredStop[0].interrupted === false);
check("known-not-started user rows never dedupe against legacy repeated text", mergeHistoryMessages([{ role: "user", content: "same" }], [{ role: "user", content: "same", notStarted: true, requestId: "rejected" }]).length === 2);

// --- retry: success first try ---
{
  let calls = 0;
  const r = await fetchChatHistoryWithRetry(async () => {
    calls++;
    return resp(200, { messages: [{ id: 1 }] });
  });
  check("retry ok", r.ok && r.messages.length === 1 && !r.missing);
  check("retry single call", calls === 1);
}

// --- retry: 404 → missing, no retry ---
{
  let calls = 0;
  const r = await fetchChatHistoryWithRetry(async () => {
    calls++;
    return resp(404, {});
  });
  check("retry 404 missing", r.ok && r.missing && r.messages.length === 0);
  check("retry 404 no retry", calls === 1);
}

// --- retry: flaky then success ---
{
  let calls = 0;
  const r = await fetchChatHistoryWithRetry(
    async () => {
      calls++;
      if (calls < 3) throw new Error("network down");
      return resp(200, { messages: [] });
    },
    3,
    1,
  );
  check("retry flaky ok", r.ok && calls === 3);
}

// --- retry: always failing → ok:false with error ---
{
  const r = await fetchChatHistoryWithRetry(
    async () => {
      throw new Error("boom");
    },
    2,
    1,
  );
  check("retry exhausted", !r.ok && r.error?.message === "boom");
}

// --- retry: non-ok status retries ---
{
  let calls = 0;
  const r = await fetchChatHistoryWithRetry(
    async () => {
      calls++;
      return resp(500, {});
    },
    2,
    1,
  );
  check("retry 500 exhausted", !r.ok && calls === 2);
}

// --- retry: malformed body → empty messages, still ok ---
{
  const r = await fetchChatHistoryWithRetry(async () => resp(200, {}));
  check("retry malformed body", r.ok && r.messages.length === 0);
}

console.log(`historySync: ${passed} passed, ${failed} failed`);
process.exit(failed > 0 ? 1 : 0);

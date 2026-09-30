/**
 * Unit tests for utils/historySync.ts (pure fns).
 *
 * No test runner is installed in this repo — this file is self-running:
 *   node frontend/src/utils/historySync.test.ts   (Node >= 22.6, type stripping)
 * Exit code 0 = all pass, 1 = failure. Also typechecked by `tsc --noEmit`.
 */

import {
  historyDedupeKey,
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

/**
 * Unit tests for utils/streaming.ts (StreamBuffer).
 *
 * No test runner is installed in this repo — this file is self-running:
 *   node frontend/src/utils/streaming.test.ts   (Node >= 22.6, type stripping)
 * Exit code 0 = all pass, 1 = failure. Also typechecked by `tsc --noEmit`.
 *
 * Note: Node has no requestAnimationFrame, and StreamBuffer is designed to
 * flush synchronously in that case — so these tests exercise the direct
 * path; the rAF-throttled path is DOM-only.
 */

import { StreamBuffer } from "./streaming.ts";

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

// --- accumulates and flushes ---
{
  const seen: string[] = [];
  const buf = new StreamBuffer((t) => seen.push(t));
  buf.push("hello");
  buf.push(" ");
  buf.push("world");
  check("push accumulates (no rAF → sync flush each push)", seen.length === 3);
  check("final text", buf.getText() === "hello world");
  const final = buf.finalize();
  check("finalize returns full text", final === "hello world");
  check("finalize flushes once more", seen[seen.length - 1] === "hello world");
}

// --- finalize clears and stops ---
{
  const seen: string[] = [];
  const buf = new StreamBuffer((t) => seen.push(t));
  buf.push("a");
  buf.finalize();
  buf.push("b"); // ignored after finalize
  check("push after finalize ignored", buf.getText() === "");
  check("no flush after finalize", !seen.includes("b"));
}

// --- discard drops without flushing ---
{
  const seen: string[] = [];
  const buf = new StreamBuffer((t) => seen.push(t));
  buf.push("partial");
  const n = seen.length;
  buf.discard();
  check("discard clears", buf.getText() === "");
  check("discard does not flush", seen.length === n);
}

// --- empty chunk is a no-op ---
{
  const seen: string[] = [];
  const buf = new StreamBuffer((t) => seen.push(t));
  buf.push("");
  check("empty chunk ignored", seen.length === 0 && buf.getText() === "");
}

// --- setOnFlush swaps callback ---
{
  const a: string[] = [];
  const b: string[] = [];
  const buf = new StreamBuffer((t) => a.push(t));
  buf.push("x");
  buf.setOnFlush((t) => b.push(t));
  buf.push("y");
  check("setOnFlush swaps", b.length === 1 && a.length === 1);
  buf.finalize();
}

// --- finalize with no text does not call onFlush ---
{
  let calls = 0;
  const buf = new StreamBuffer(() => calls++);
  buf.finalize();
  check("finalize empty no flush", calls === 0);
}

console.log(`streaming: ${passed} passed, ${failed} failed`);
process.exit(failed > 0 ? 1 : 0);

/**
 * Unit tests for utils/exportChat.ts and utils/safeHtml.ts (pure fns).
 *
 * No test runner is installed in this repo — this file is self-running:
 *   node frontend/src/utils/exportChat.test.ts   (Node >= 22.6, type stripping)
 * Exit code 0 = all pass, 1 = failure. Also typechecked by `tsc --noEmit`.
 */

import {
  exportMarkdown,
  exportText,
  exportJSON,
  buildExportFilename,
  sanitizeSessionId,
  type ExportableMessage,
} from "./exportChat.ts";
import { escapeHtml, markdownToSafeHtml, buildSandboxDoc } from "./safeHtml.ts";

declare const process: { exit(code: number): void };

let passed = 0;
let failed = 0;

function check(name: string, cond: boolean, detail?: string): void {
  if (cond) {
    passed++;
  } else {
    failed++;
    console.error(`FAIL: ${name}${detail ? ` — ${detail}` : ""}`);
  }
}

const MSGS: ExportableMessage[] = [
  {
    id: 1,
    role: "user",
    content: "Hello **world**",
    ts: "10:00:01",
  },
  {
    id: 2,
    role: "assistant",
    content: "```python\nprint('hi')\n```",
    agent: "Mizan",
    model: "claude-opus-4-6",
    ts: "10:00:05",
  },
  { id: 3, role: "system", content: "session started" },
];

// ---- exportMarkdown ----
{
  const md = exportMarkdown(MSGS, {
    sessionId: "sess_1",
    exportedAt: new Date("2026-09-30T10:00:00Z"),
  });
  check("md has title", md.startsWith("# Mizan Chat Export"));
  check("md session line", md.includes("Session: sess_1"));
  check("md count", md.includes("Messages: 3"));
  check("md user header", md.includes("## \u{1F9D1} User \u2014 10:00:01"));
  check(
    "md assistant header with meta",
    md.includes(
      "## \u{1F916} Assistant (Mizan \u00B7 claude-opus-4-6) \u2014 10:00:05",
    ),
  );
  check("md system header", md.includes("\u2699\uFE0F System"));
  check("md keeps code fence", md.includes("```python\nprint('hi')\n```"));
  check(
    "md no-meta header has no parens",
    md.includes("## \u{1F9D1} User \u2014"),
  );
  check("md ends with newline", md.endsWith("\n"));
  const empty = exportMarkdown([]);
  check("md empty has zero count", empty.includes("Messages: 0"));
}

// ---- exportText ----
{
  const txt = exportText(MSGS, { sessionId: "s" });
  check(
    "txt strips bold",
    txt.includes("Hello world") && !txt.includes("**world**"),
  );
  check("txt keeps code words", txt.includes("print('hi')"));
  check(
    "txt uppercase role header",
    txt.includes("[10:00:01] USER:") &&
      txt.includes("[10:00:05] ASSISTANT (Mizan \u00B7 claude-opus-4-6):"),
  );
  check("txt missing ts shows ?", txt.includes("[?] SYSTEM:"));
}

// ---- exportJSON ----
{
  const parsed = JSON.parse(exportJSON(MSGS, { sessionId: "sess_9" }));
  check(
    "json envelope",
    parsed.format === "mizan-chat-export" && parsed.version === 1,
  );
  check("json session", parsed.session_id === "sess_9");
  check("json count", parsed.message_count === 3);
  check(
    "json full fidelity",
    parsed.messages[1].content === "```python\nprint('hi')\n```",
  );
  check(
    "json nulls for missing meta",
    parsed.messages[0].agent === null && parsed.messages[2].ts === null,
  );
  check("json exported_at iso", typeof parsed.exported_at === "string");
}

// ---- filenames ----
{
  const d = new Date("2026-09-30T10:05:00Z");
  check(
    "md filename",
    buildExportFilename("sess_1", "markdown", d) ===
      "mizan-chat-sess_1-20260930T1005.md",
  );
  check(
    "txt filename",
    buildExportFilename("sess_1", "text", d) ===
      "mizan-chat-sess_1-20260930T1005.txt",
  );
  check(
    "json filename",
    buildExportFilename("sess_1", "json", d) ===
      "mizan-chat-sess_1-20260930T1005.json",
  );
  check("sanitize strips weird chars", sanitizeSessionId("a/b?c=d") === "abcd");
  check("sanitize empty falls back", sanitizeSessionId("!!!") === "session");
  check("sanitize truncates", sanitizeSessionId("x".repeat(50)).length === 32);
}

// ---- escapeHtml ----
{
  check(
    "escapes",
    escapeHtml('<a href="x">&\'') === "&lt;a href=&quot;x&quot;&gt;&amp;&#39;",
  );
}

// ---- markdownToSafeHtml ----
{
  const html = markdownToSafeHtml("# Hi\n\nHello **bold** and `code`.");
  check("h1", html.includes("<h1>Hi</h1>"));
  check("strong", html.includes("<strong>bold</strong>"));
  check("inline code", html.includes("<code>code</code>"));

  const xss = markdownToSafeHtml(
    "<script>alert(1)</script>\n\n<img src=x onerror=alert(1)>",
  );
  check(
    "script tag escaped",
    !xss.includes("<script>") && xss.includes("&lt;script&gt;"),
  );
  check("no raw img tag", !/<img[\s>]/.test(xss));

  const fence = markdownToSafeHtml('```python\nprint("<x>")\n```');
  check(
    "fenced code escaped",
    fence.includes('<pre><code class="language-python">') &&
      fence.includes("&lt;x&gt;"),
  );

  const list = markdownToSafeHtml("- a\n- b\n\n1. x\n2. y");
  check("ul", list.includes("<ul><li>a</li><li>b</li></ul>"));
  check("ol as ul", list.includes("<li>x</li>"));

  const q = markdownToSafeHtml("> quoted");
  check("blockquote", q.includes("<blockquote>quoted</blockquote>"));

  const links = markdownToSafeHtml(
    "[ok](https://example.com) [evil](javascript:alert(1))",
  );
  check("good link kept", links.includes('href="https://example.com"'));
  check(
    "javascript: dropped",
    !links.includes("javascript:") && links.includes("evil"),
  );

  const img = markdownToSafeHtml("![alt](https://example.com/i.png)");
  check("image -> alt label", img.includes("[alt]") && !img.includes("<img"));

  // placeholder collision: literal FENCED0/INLINE0 text must survive
  const coll = markdownToSafeHtml("say FENCED0 and INLINE0 out loud");
  check(
    "no placeholder collision",
    coll.includes("FENCED0") && coll.includes("INLINE0"),
  );
}

// ---- buildSandboxDoc ----
{
  const doc = buildSandboxDoc("markdown", "# Hi");
  check(
    "doc has CSP meta",
    doc.includes('http-equiv="Content-Security-Policy"'),
  );
  check("doc CSP connect-src none", doc.includes("connect-src 'none'"));
  check("doc CSP default-src none", doc.includes("default-src 'none'"));
  check("doc renders markdown", doc.includes("<h1>Hi</h1>"));
  const raw = buildSandboxDoc(
    "html",
    "<h1>raw</h1><script>window.x=1</script>",
  );
  check("html kind passes through", raw.includes("<h1>raw</h1>"));
}

console.log(
  failed === 0
    ? `OK — ${passed} assertions passed`
    : `${failed} FAILURES (${passed} passed)`,
);
process.exit(failed === 0 ? 0 : 1);

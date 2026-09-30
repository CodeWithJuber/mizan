/**
 * Unit tests for utils/copyFormat.ts and utils/agentDisplay.ts (pure fns).
 *
 * No test runner is installed in this repo — this file is self-running:
 *   node frontend/src/utils/copyFormat.test.ts   (Node >= 22.6, type stripping)
 * Exit code 0 = all pass, 1 = failure. Also typechecked by `tsc --noEmit`.
 */

import {
  stripMarkdown,
  toWhatsAppFormat,
  convertCopyFormat,
} from "./copyFormat.ts";
import { resolveAgentName, looksLikeRawId } from "./agentDisplay.ts";

declare const process: { exit(code: number): void };

let passed = 0;
let failed = 0;

function eq(actual: string, expected: string, label: string): void {
  if (actual === expected) {
    passed++;
  } else {
    failed++;
    console.error(
      `FAIL ${label}\n  expected: ${JSON.stringify(expected)}\n  actual:   ${JSON.stringify(actual)}`,
    );
  }
}

function isTrue(actual: boolean, label: string): void {
  eq(String(actual), "true", label);
}

function isFalse(actual: boolean, label: string): void {
  eq(String(actual), "false", label);
}

// ---- stripMarkdown ---------------------------------------------------------

eq(stripMarkdown("**bold** and _italic_"), "bold and italic", "plain: bold+italic");
eq(stripMarkdown("## Heading ##"), "Heading", "plain: ATX heading");
eq(stripMarkdown("Title\n==="), "Title", "plain: setext heading");
eq(stripMarkdown("- item one\n- item two"), "item one\nitem two", "plain: unordered list");
eq(stripMarkdown("* starred\n+ plus"), "starred\nplus", "plain: alt bullets");
eq(stripMarkdown("1. first\n2. second"), "first\nsecond", "plain: ordered list");
eq(stripMarkdown("[text](https://example.com)"), "text", "plain: link");
eq(stripMarkdown("![alt](https://example.com/i.png)"), "alt", "plain: image");
eq(stripMarkdown("> quoted"), "quoted", "plain: blockquote");
eq(stripMarkdown("`code`"), "code", "plain: inline code");
eq(
  stripMarkdown("```js\nconst x = **not bold**;\n```"),
  "const x = **not bold**;",
  "plain: fenced block keeps inner text, formatting inside untouched",
);
eq(stripMarkdown("~~gone~~"), "gone", "plain: strikethrough");
eq(stripMarkdown("a\n\n---\n\nb"), "a\n\nb", "plain: hr removed");

// ---- toWhatsAppFormat ------------------------------------------------------

eq(toWhatsAppFormat("**bold**"), "*bold*", "wa: bold");
eq(toWhatsAppFormat("__bold__"), "*bold*", "wa: __bold__");
eq(toWhatsAppFormat("_italic_"), "_italic_", "wa: italic stays");
eq(toWhatsAppFormat("*italic*"), "_italic_", "wa: *italic* -> _italic_");
eq(toWhatsAppFormat("## Heading"), "*Heading*", "wa: heading");
eq(toWhatsAppFormat("# H1 #"), "*H1*", "wa: h1 closing hashes");
eq(toWhatsAppFormat("- item\n* item2"), "• item\n• item2", "wa: bullets");
eq(toWhatsAppFormat("1. first"), "1. first", "wa: ordered list untouched");
eq(
  toWhatsAppFormat("[text](https://example.com)"),
  "text (https://example.com)",
  "wa: link",
);
eq(toWhatsAppFormat("> quoted"), "_quoted_", "wa: quote");
eq(
  toWhatsAppFormat("```\nconst x = **y**;\n```"),
  "```\nconst x = **y**;\n```",
  "wa: fenced block untouched",
);
eq(toWhatsAppFormat("`code`"), "`code`", "wa: inline code untouched");
eq(toWhatsAppFormat("~~strike~~"), "~strike~", "wa: strikethrough");
eq(
  toWhatsAppFormat("**bold** and `**not bold**`"),
  "*bold* and `**not bold**`",
  "wa: formatting inside code spans untouched",
);
eq(
  toWhatsAppFormat("## T\n\n- a\n- b\n\n> q"),
  "*T*\n\n• a\n• b\n\n_q_",
  "wa: mixed document",
);

// ---- convertCopyFormat -----------------------------------------------------

eq(convertCopyFormat("**x**", "markdown"), "**x**", "convert: markdown as-is");
eq(convertCopyFormat("**x**", "plain"), "x", "convert: plain");
eq(convertCopyFormat("**x**", "whatsapp"), "*x*", "convert: whatsapp");

// ---- looksLikeRawId --------------------------------------------------------

isTrue(looksLikeRawId("11295847-a894-48c4-baa0-ebdc50c91135"), "id: uuid");
isTrue(looksLikeRawId("11295847-A894-48C4-BAA0-EBDC50C91135"), "id: uuid upper");
isTrue(looksLikeRawId("507f1f77bcf86cd799439011"), "id: 24-hex");
isFalse(looksLikeRawId("Khalifah"), "id: name");
isFalse(looksLikeRawId("agent_123"), "id: prefixed id");
isFalse(looksLikeRawId(""), "id: empty");

// ---- resolveAgentName ------------------------------------------------------

const agents = [{ id: "11295847-a894-48c4-baa0-ebdc50c91135", name: "Khalifah" }];
eq(
  resolveAgentName("11295847-a894-48c4-baa0-ebdc50c91135", agents),
  "Khalifah",
  "agent: resolves via agents list",
);
eq(
  resolveAgentName("unknown-id-0000-0000-000000000000", agents),
  "unknown-id-0000-0000-000000000000",
  "agent: non-id passthrough",
);
eq(
  resolveAgentName("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", agents),
  "Assistant",
  "agent: unknown uuid -> Assistant",
);
eq(
  resolveAgentName("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", agents, "Khalifah"),
  "Khalifah",
  "agent: unknown uuid -> selected agent name",
);
eq(
  resolveAgentName("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", agents, "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"),
  "Assistant",
  "agent: selected name that is itself a uuid is not used",
);
eq(resolveAgentName(undefined, agents, "Khalifah"), "Khalifah", "agent: no id -> selected");
eq(resolveAgentName(undefined, agents), "MIZAN", "agent: no id, none selected -> MIZAN");
eq(resolveAgentName("Khalifah", agents), "Khalifah", "agent: display name passthrough");

// ---- report ----------------------------------------------------------------

if (failed > 0) {
  console.error(`\n${failed} FAILED, ${passed} passed`);
  process.exit(1);
} else {
  console.log(`OK — ${passed} assertions passed`);
}

/**
 * safeHtml.ts — sandboxed artifact rendering helpers (pure functions, no React).
 *
 * Two layers of defence for artifact HTML:
 *  1. `markdownToSafeHtml` escapes ALL raw HTML first, then renders a small
 *     markdown subset — the output can never contain attacker markup.
 *  2. `buildSandboxDoc` wraps the body in a full document with an injected
 *     Content-Security-Policy; the document is rendered in
 *     `<iframe sandbox="allow-scripts">` WITHOUT `allow-same-origin`
 *     (see ArtifactPreview.tsx for the sandbox rationale).
 */

export function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

// NUL — cannot appear in real markdown text, so placeholders never collide
// with user content (same trick as copyFormat.ts).
const TOKEN = "\u0000";

interface FencedBlock {
  lang: string;
  code: string;
}

function extractFenced(md: string): { text: string; blocks: FencedBlock[] } {
  const blocks: FencedBlock[] = [];
  const text = md.replace(
    /```([a-zA-Z0-9+#-]*)\n?([\s\S]*?)\n?```/g,
    (_m: string, lang: string, code: string) => {
      blocks.push({ lang, code });
      return `${TOKEN}FENCED${blocks.length - 1}${TOKEN}`;
    },
  );
  return { text, blocks };
}

function extractInlineCode(text: string): { text: string; codes: string[] } {
  const codes: string[] = [];
  const out = text.replace(/`([^`\n]+)`/g, (_m: string, code: string) => {
    codes.push(code);
    return `${TOKEN}INLINE${codes.length - 1}${TOKEN}`;
  });
  return { text: out, codes };
}

function restoreInline(text: string, codes: string[]): string {
  const re = new RegExp(`${TOKEN}INLINE(\\d+)${TOKEN}`, "g");
  return text.replace(re, (_m: string, i: string) => {
    return `<code>${escapeHtml(codes[Number(i)] ?? "")}</code>`;
  });
}

function restoreFenced(text: string, blocks: FencedBlock[]): string {
  const re = new RegExp(`${TOKEN}FENCED(\\d+)${TOKEN}`, "g");
  return text.replace(re, (_m: string, i: string) => {
    const block = blocks[Number(i)] ?? { lang: "", code: "" };
    const cls = block.lang ? ` class="language-${escapeHtml(block.lang)}"` : "";
    return `<pre><code${cls}>${escapeHtml(block.code)}</code></pre>`;
  });
}

function isFencePlaceholder(line: string): boolean {
  const re = new RegExp(`^${TOKEN}FENCED\\d+${TOKEN}$`);
  return re.test(line);
}

function safeLink(text: string, url: string): string {
  const ok = /^(https?:\/\/|mailto:)/i.test(url.trim());
  const label = escapeHtml(text);
  if (!ok) return label; // javascript:/data: URLs are dropped, label kept
  return `<a href="${escapeHtml(url.trim())}" target="_blank" rel="noopener noreferrer">${label}</a>`;
}

function inlineMd(escaped: string): string {
  // `escaped` is already HTML-escaped; we only insert our own tags.
  const { text, codes } = extractInlineCode(escaped);
  let t = text;
  // NOTE: URLs with balanced parens (e.g. Wikipedia) truncate at the
  // first ')'. Known limitation, kept simple on purpose — the iframe
  // sandbox + CSP neutralise anything dangerous regardless.
  t = t.replace(/!\[([^\]]*)\]\(([^)\s]*(?:\s+"[^"]*")?)\)/g, "[$1]"); // images -> [alt]
  t = t.replace(
    /\[([^\]]*)\]\(([^)\s]*(?:\s+"[^"]*")?)\)/g,
    (_m: string, label: string, url: string) =>
      safeLink(label, url.replace(/\s+"[^"]*"\s*$/, "")),
  );
  t = t.replace(/(\*\*|__)([\s\S]*?)\1/g, "<strong>$2</strong>");
  t = t.replace(/(^|[^\w*])\*([^*<][^*]*?)\*(?![\w*])/g, "$1<em>$2</em>");
  t = t.replace(/(^|[^\w_])_([^_<][^_]*?)_(?![\w_])/g, "$1<em>$2</em>");
  t = t.replace(/~~([^~<]+?)~~/g, "<del>$1</del>");
  return restoreInline(t, codes);
}

/**
 * Render a small markdown subset to HTML. Raw HTML in the source is escaped
 * (not rendered), so the output is safe to inject into the sandbox doc.
 */
export function markdownToSafeHtml(md: string): string {
  const { text: noFenced, blocks } = extractFenced(md.replace(/\r\n/g, "\n"));
  const lines = escapeHtml(noFenced).split("\n");
  const out: string[] = [];
  let para: string[] = [];
  let list: string[] | null = null;
  let quote: string[] | null = null;

  const flushPara = () => {
    if (para.length > 0) {
      out.push(`<p>${inlineMd(para.join(" "))}</p>`);
      para = [];
    }
  };
  const flushList = () => {
    if (list) {
      out.push(
        `<ul>${list.map((li) => `<li>${inlineMd(li)}</li>`).join("")}</ul>`,
      );
      list = null;
    }
  };
  const flushQuote = () => {
    if (quote) {
      out.push(`<blockquote>${inlineMd(quote.join(" "))}</blockquote>`);
      quote = null;
    }
  };

  for (const line of lines) {
    const trimmed = line.trim();
    if (trimmed === "") {
      flushPara();
      flushList();
      flushQuote();
      continue;
    }
    if (isFencePlaceholder(trimmed)) {
      flushPara();
      flushList();
      flushQuote();
      out.push(restoreFenced(trimmed, blocks));
      continue;
    }
    const heading = line.match(/^(#{1,6})[ \t]+(.*)$/);
    if (heading) {
      flushPara();
      flushList();
      flushQuote();
      const level = heading[1].length;
      out.push(`<h${level}>${inlineMd(heading[2])}</h${level}>`);
      continue;
    }
    if (/^[ \t]*([-*_])[ \t]*(\1[ \t]*){2,}$/.test(line)) {
      flushPara();
      flushList();
      flushQuote();
      out.push("<hr>");
      continue;
    }
    const bq = line.match(/^[ \t]*&gt;[ \t]?(.*)$/);
    if (bq) {
      flushPara();
      flushList();
      quote = quote ?? [];
      quote.push(bq[1]);
      continue;
    }
    const li =
      line.match(/^[ \t]*[-*+][ \t]+(.*)$/) ??
      line.match(/^[ \t]*\d+[.)][ \t]+(.*)$/);
    if (li) {
      flushPara();
      flushQuote();
      list = list ?? [];
      list.push(li[1]);
      continue;
    }
    flushList();
    flushQuote();
    para.push(trimmed);
  }
  flushPara();
  flushList();
  flushQuote();
  return out.join("\n");
}

/**
 * Build the full HTML document for the locked-down artifact iframe.
 *
 * SECURITY (anti-exfiltration, two independent layers):
 *  - The iframe is rendered with `sandbox="allow-scripts"` and WITHOUT
 *    `allow-same-origin`: the document gets an opaque origin, so artifact
 *    scripts cannot touch the parent DOM, cookies, localStorage, or the
 *    Mizan session — even same-tab navigation is contained.
 *  - The injected CSP below sets `connect-src 'none'`: fetch/XHR/WebSocket/
 *    EventSource/sendBeacon are all blocked, so even a malicious script that
 *    runs inside the sandbox cannot phone data home. `default-src 'none'`
 *    blocks external subresources; only inline styles/scripts and data:/blob:
 *    media are permitted so legitimate artifact interactivity still works.
 */
export function buildSandboxDoc(
  kind: "html" | "markdown",
  content: string,
): string {
  const body = kind === "markdown" ? markdownToSafeHtml(content) : content;
  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data: blob:; media-src data: blob:; font-src data:; connect-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none';">
<style>
  :root { color-scheme: light dark; }
  body { font-family: system-ui, -apple-system, "Segoe UI", sans-serif; line-height: 1.6; margin: 0 auto; max-width: 72ch; padding: 1.25rem; color: #1f2937; background: #ffffff; }
  @media (prefers-color-scheme: dark) { body { color: #e5e7eb; background: #18181b; } }
  pre { background: rgba(127,127,127,.12); padding: .75rem; border-radius: .5rem; overflow-x: auto; }
  code { font-family: ui-monospace, monospace; font-size: .9em; }
  blockquote { border-left: 3px solid #d4a017; margin: 0; padding-left: 1rem; opacity: .85; }
  a { color: #b45309; }
  img { max-width: 100%; }
</style>
</head>
<body>${body}</body>
</html>`;
}

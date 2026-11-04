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
 * SECURITY: artifact iframes are rendered with `sandbox` WITHOUT
 * `allow-same-origin`, so a document gets an opaque origin: its scripts cannot
 * touch the parent DOM, cookies, localStorage or the MIZAN session. That
 * sandbox is the boundary. The policy below lets a page load any https script,
 * style, font or image and fetch from https (the owner's decision, 5 Nov 2026:
 * model-written pages use CDNs and public APIs), so a page can send its own
 * content elsewhere, never MIZAN's.
 */
const SANDBOX_POLICY =
  `<meta http-equiv="Content-Security-Policy" content="default-src 'none'; ` +
  `script-src 'unsafe-inline' 'unsafe-eval' https: blob:; style-src 'unsafe-inline' https:; ` +
  `img-src data: blob: https:; media-src data: blob: https:; font-src data: https:; ` +
  `connect-src https:; base-uri 'none'; form-action 'none';">`;

const DOC_HEAD = `<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">${SANDBOX_POLICY}`;

// Markdown keeps a reading layout; a page or picture brings its own.
const PROSE_STYLE = `<style>
  :root { color-scheme: light dark; }
  body { font-family: system-ui, -apple-system, "Segoe UI", sans-serif; line-height: 1.6; margin: 0 auto; max-width: 72ch; padding: 1.25rem; color: #1f2937; background: #ffffff; }
  @media (prefers-color-scheme: dark) { body { color: #e5e7eb; background: #18181b; } }
  pre { background: rgba(127,127,127,.12); padding: .75rem; border-radius: .5rem; overflow-x: auto; }
  code { font-family: ui-monospace, monospace; font-size: .9em; }
  blockquote { border-left: 3px solid #d4a017; margin: 0; padding-left: 1rem; opacity: .85; }
  a { color: #b45309; }
  img { max-width: 100%; }
</style>`;
const FRAGMENT_STYLE = `<style>body { margin: 0; padding: 1rem; font-family: system-ui, -apple-system, "Segoe UI", sans-serif; }</style>`;
const SVG_STYLE = `<style>body { margin: 0; min-height: 100vh; display: grid; place-items: center; } svg { max-width: 100%; height: auto; }</style>`;

const FULL_DOCUMENT = /^\s*(<!doctype html|<html[\s>])/i;
const HEAD_TAG = /<head(\s[^>]*)?>/i; // not <header>
const HTML_TAG = /<html(\s[^>]*)?>/i;
const DOCTYPE = /^\s*<!doctype html[^>]*>/i;

/** A whole page as written, with the policy first in its head. */
function withPolicy(page: string): string {
  if (HEAD_TAG.test(page)) return page.replace(HEAD_TAG, (tag) => tag + SANDBOX_POLICY);
  if (HTML_TAG.test(page)) return page.replace(HTML_TAG, (tag) => `${tag}<head>${SANDBOX_POLICY}</head>`);
  return page.replace(DOCTYPE, (tag) => `${tag}<head>${SANDBOX_POLICY}</head>`);
}

/** The document an artifact iframe shows (see SECURITY above). */
export function buildSandboxDoc(
  kind: "html" | "markdown" | "svg",
  content: string,
): string {
  if (kind === "html" && FULL_DOCUMENT.test(content)) return withPolicy(content);
  const [style, body] =
    kind === "markdown"
      ? [PROSE_STYLE, markdownToSafeHtml(content)]
      : [kind === "svg" ? SVG_STYLE : FRAGMENT_STYLE, content];
  return `<!DOCTYPE html><html lang="en"><head>${DOC_HEAD}${style}</head><body>${body}</body></html>`;
}

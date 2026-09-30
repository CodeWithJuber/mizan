/**
 * copyFormat.ts — message copy-format converters (pure functions, no React).
 *
 * The chat copy button offers three formats:
 *  - "markdown" — the message as-is (GitHub-flavoured markdown).
 *  - "plain"    — all markdown formatting stripped (clean paste anywhere).
 *  - "whatsapp" — converted to WhatsApp's formatting syntax:
 *      **bold** -> *bold*, _italic_ stays _italic_, ## head -> *head*,
 *      - item -> • item, [text](url) -> text (url),
 *      ```code``` and `code` stay as-is (WhatsApp renders them),
 *      > quote -> _quote_, ~~strike~~ -> ~strike~.
 *
 * Note on `__text__`: in markdown this is bold (not underline — WhatsApp has
 * no underline), so it converts to *text* exactly like **text**.
 */

export type CopyFormatId = "markdown" | "plain" | "whatsapp";

export function convertCopyFormat(md: string, format: CopyFormatId): string {
  switch (format) {
    case "plain":
      return stripMarkdown(md);
    case "whatsapp":
      return toWhatsAppFormat(md);
    case "markdown":
    default:
      return md;
  }
}

// ---------------------------------------------------------------------------
// Placeholder machinery — code spans/blocks are extracted before any other
// rewrite so formatting inside code is never touched, then restored verbatim.
// ---------------------------------------------------------------------------

const TOKEN = "\u0000";

function extractFencedBlocks(text: string): {
  text: string;
  blocks: string[];
} {
  const blocks: string[] = [];
  const out = text.replace(
    /```[a-zA-Z0-9+#-]*\n?([\s\S]*?)\n?```/g,
    (_m: string, inner: string) => {
      blocks.push(inner);
      return `${TOKEN}FENCED${blocks.length - 1}${TOKEN}`;
    },
  );
  return { text: out, blocks };
}

function extractInlineCode(text: string): { text: string; codes: string[] } {
  const codes: string[] = [];
  const out = text.replace(/`([^`\n]+)`/g, (_m: string, code: string) => {
    codes.push(code);
    return `${TOKEN}INLINE${codes.length - 1}${TOKEN}`;
  });
  return { text: out, codes };
}

function restore(
  text: string,
  kind: "FENCED" | "INLINE",
  values: string[],
): string {
  const re = new RegExp(`${TOKEN}${kind}(\\d+)${TOKEN}`, "g");
  return text.replace(re, (_m: string, i: string) => values[Number(i)] ?? "");
}

function tidy(text: string): string {
  return text
    .split("\n")
    .map((line) => line.replace(/[ \t]+$/g, ""))
    .join("\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

// ---------------------------------------------------------------------------
// Plain text — strip every markdown construct, keep the words.
// ---------------------------------------------------------------------------

export function stripMarkdown(md: string): string {
  const fenced = extractFencedBlocks(md.replace(/\r\n/g, "\n"));
  const inline = extractInlineCode(fenced.text);
  let text = inline.text;

  // Images ![alt](url) -> alt ; links [text](url) -> text
  text = text.replace(/!\[([^\]]*)\]\([^)\s]*(?:\s+"[^"]*")?\)/g, "$1");
  text = text.replace(/\[([^\]]*)\]\([^)\s]*(?:\s+"[^"]*")?\)/g, "$1");
  text = text.replace(/\[([^\]]*)\]\[[^\]]*\]/g, "$1");

  // ATX + Setext headings -> text
  // (use [ \t], never \s, so trailing blank lines are not consumed)
  text = text.replace(/^#{1,6}[ \t]+(.*?)[ \t]*#*[ \t]*$/gm, "$1");
  text = text.replace(/^(.+)\n[=-]{3,}[ \t]*$/gm, "$1");

  // Bold / italic / strikethrough (bold first, then single-marker italics)
  text = text.replace(/(\*\*|__)([\s\S]*?)\1/g, "$2");
  text = text.replace(/(^|[^\w*])\*([^*\n]+?)\*(?![\w*])/g, "$1$2");
  text = text.replace(/(^|[^\w_])_([^_\n]+?)_(?![\w_])/g, "$1$2");
  text = text.replace(/~~([^~\n]+?)~~/g, "$1");

  // Blockquotes, list markers, horizontal rules
  text = text.replace(/^[ \t]*>{1,3}[ \t]?/gm, "");
  text = text.replace(/^([ \t]*)[-*+][ \t]+/gm, "$1");
  text = text.replace(/^([ \t]*)\d+[.)][ \t]+/gm, "$1");
  text = text.replace(/^[ \t]*([-*_])[ \t]*(\1[ \t]*){2,}$/gm, "");

  text = restore(text, "INLINE", inline.codes);
  text = restore(text, "FENCED", fenced.blocks);
  return tidy(text);
}

// ---------------------------------------------------------------------------
// WhatsApp format — translate markdown into WhatsApp's *bold* / _italic_ /
// ~strike~ / ```mono``` syntax.
// ---------------------------------------------------------------------------

export function toWhatsAppFormat(md: string): string {
  const fenced = extractFencedBlocks(md.replace(/\r\n/g, "\n"));
  const inline = extractInlineCode(fenced.text);
  let text = inline.text;

  // Images ![alt](url) -> alt (url) ; links [text](url) -> text (url)
  text = text.replace(/!\[([^\]]*)\]\(([^)\s]+)[^)]*\)/g, "$1 ($2)");
  text = text.replace(/\[([^\]]*)\]\(([^)\s]+)[^)]*\)/g, "$1 ($2)");
  text = text.replace(/!\[([^\]]*)\]\[[^\]]*\]/g, "$1");
  text = text.replace(/\[([^\]]*)\]\[[^\]]*\]/g, "$1");

  // Italic first (single markers), then bold (double markers) so the *bold*
  // produced below is never re-processed as italic.
  text = text.replace(/(^|[^\w*])\*([^*\n]+?)\*(?![\w*])/g, "$1_$2_");
  text = text.replace(/~~([^~\n]+?)~~/g, "~$1~");
  text = text.replace(/(\*\*|__)([\s\S]*?)\1/g, "*$2*");

  // Headings -> *bold* (last: the *...* we emit must not be re-processed).
  // Inner markers are stripped first so "## **B**" becomes *B*, not **B**.
  const cleanHeadingInner = (h: string): string =>
    h
      .replace(/(\*\*|__)([\s\S]*?)\1/g, "$2")
      .replace(/(^|[^\w*])\*([^*\n]+?)\*(?![\w*])/g, "$1$2")
      .replace(/(^|[^\w_])_([^_\n]+?)_(?![\w_])/g, "$1$2")
      .trim();
  text = text.replace(
    /^#{1,6}[ \t]+(.*?)[ \t]*#*[ \t]*$/gm,
    (_m: string, h: string) => `*${cleanHeadingInner(h)}*`,
  );
  text = text.replace(
    /^(.+)\n[=-]{3,}[ \t]*$/gm,
    (_m: string, h: string) => `*${cleanHeadingInner(h)}*`,
  );

  // Blockquotes -> _italic_ (WhatsApp has no quote syntax)
  text = text.replace(/^[ \t]*>{1,3}[ \t]?(.*)$/gm, (_m: string, q: string) =>
    q.trim() ? `_${q.trim()}_` : "",
  );

  // Unordered list markers -> • (ordered lists are left as-is)
  text = text.replace(/^([ \t]*)[-*+][ \t]+/gm, "$1• ");

  // Restore code — WhatsApp renders `code` and ```code``` natively.
  text = restore(
    text,
    "INLINE",
    inline.codes.map((c) => `\`${c}\``),
  );
  text = restore(
    text,
    "FENCED",
    fenced.blocks.map((b) => `\`\`\`\n${b}\n\`\`\``),
  );
  return tidy(text);
}

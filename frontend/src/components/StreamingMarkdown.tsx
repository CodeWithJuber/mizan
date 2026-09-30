import { useRef, type ReactNode } from "react";
import { ChatMessageContent } from "./ChatMessage";

/**
 * StreamingMarkdown — incremental markdown renderer for the live stream.
 *
 * DESIGN CHOICE (documented per ticket): no new dependency. The repo already
 * ships react-markdown + remark/rehype; adding a streaming-markdown library
 * would duplicate that parser stack. Instead this component makes the
 * existing parser incremental:
 *
 *   - Incoming text is split into "stable" blocks (everything up to the last
 *     blank-line boundary) and a "tail" (the paragraph still being typed).
 *   - Stable blocks are parsed ONCE each and cached by block content
 *     (module-level Map, capped) — parsed output is APPENDED as new blocks
 *     stabilize, never re-parsed.
 *   - Only the tail is re-parsed per flush (~20/s via StreamBuffer), and it
 *     is at most one paragraph / one open code fence.
 *   - Fenced code blocks are never split: while a ``` fence is unclosed,
 *     everything from the fence opener is treated as tail, so syntax
 *     highlighting never flickers on a half fence.
 *
 * Net effect: per flush we parse ≤1 small block instead of the whole
 * response, and React never re-mounts already-rendered blocks.
 */

const BLOCK_CACHE_LIMIT = 1000;
const blockCache = new Map<string, ReactNode>();

function cachedBlockNode(
  block: string,
  onExploreWord?: (word: string) => void,
): ReactNode {
  const cacheKey = `${onExploreWord ? "w" : "x"}\u0000${block}`;
  let node = blockCache.get(cacheKey);
  if (!node) {
    node = <ChatMessageContent content={block} onExploreWord={onExploreWord} />;
    if (blockCache.size >= BLOCK_CACHE_LIMIT) {
      const oldest = blockCache.keys().next();
      if (!oldest.done) blockCache.delete(oldest.value);
    }
    blockCache.set(cacheKey, node);
  }
  return node;
}

function splitBlocks(text: string): string[] {
  return text.split(/\n{2,}/).filter((b) => b.trim().length > 0);
}

/**
 * Split streamed text into stable blocks (safe to parse once) and the live
 * tail (re-parsed per flush). Content is append-only during a stream.
 */
function splitStableTail(text: string): { stable: string[]; tail: string } {
  if (!text) return { stable: [], tail: "" };
  // Unclosed fence → everything from the fence opener is tail.
  const fenceOpens = (text.match(/^```/gm) || []).length;
  if (fenceOpens % 2 === 1) {
    const idx = text.lastIndexOf("```");
    return { stable: splitBlocks(text.slice(0, idx)), tail: text.slice(idx) };
  }
  const parts = text.split(/\n{2,}/);
  if (parts.length <= 1) return { stable: [], tail: text };
  const tail = parts.pop() as string;
  return {
    stable: parts.filter((b) => b.trim().length > 0),
    tail,
  };
}

export function StreamingMarkdown({
  content,
  onExploreWord,
}: {
  content: string;
  onExploreWord?: (word: string) => void;
}) {
  // Stable block nodes accumulate across flushes; never rebuilt.
  const stableRef = useRef<{ count: number; nodes: ReactNode[] }>({
    count: 0,
    nodes: [],
  });

  const { stable, tail } = splitStableTail(content);

  // Append-only: stable only grows, so parse just the new suffix blocks.
  if (stable.length > stableRef.current.count) {
    const fresh = stable.slice(stableRef.current.count);
    fresh.forEach((block, i) => {
      stableRef.current.nodes.push(
        <span key={`s${stableRef.current.count + i}`}>
          {cachedBlockNode(block, onExploreWord)}
        </span>,
      );
    });
    stableRef.current.count = stable.length;
  } else if (stable.length < stableRef.current.count) {
    // Shouldn't happen (append-only), but stay consistent if it does.
    stableRef.current = { count: 0, nodes: [] };
  }

  return (
    <>
      {stableRef.current.nodes}
      {tail.trim() ? (
        <ChatMessageContent content={tail} onExploreWord={onExploreWord} />
      ) : null}
      {/* Blinking block cursor at the end of the streaming bubble */}
      <span className="stream-block-cursor" aria-hidden="true" />
    </>
  );
}

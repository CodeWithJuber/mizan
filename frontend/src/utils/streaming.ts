/**
 * streaming.ts — token-stream buffering for the chat UI.
 *
 * Problem: the backend emits one WS `chat_stream` event per token (or even
 * per word). Calling setState + re-parsing markdown per token janks the UI
 * and wastes CPU.
 *
 * Solution: `StreamBuffer` accumulates raw chunks and flushes to the state
 * setter on `requestAnimationFrame`, throttled to ~50ms (20 fps — smooth
 * enough for reading, cheap enough for the main thread). Markdown parsing
 * therefore happens at most 20×/s and only on the live tail (see
 * StreamingMarkdown.tsx), never per token.
 *
 * Usage:
 *   const buf = new StreamBuffer((text) => setStreamingText(text));
 *   ws.onmessage = (e) => buf.push(JSON.parse(e.data).chunk); // hot path
 *   // when the stream ends:
 *   buf.finalize(); // flushes immediately and releases the rAF handle
 */

export class StreamBuffer {
  private text = "";
  private rafId = 0;
  private lastFlush = 0;
  private readonly throttleMs: number;
  private onFlush: (text: string) => void;
  private settled = false;

  constructor(onFlush: (text: string) => void, throttleMs = 50) {
    this.onFlush = onFlush;
    this.throttleMs = throttleMs;
  }

  /** Append a chunk from the socket. Cheap — no render triggered here. */
  push(chunk: string): void {
    if (this.settled || !chunk) return;
    this.text += chunk;
    this.schedule();
  }

  /** Current accumulated text (for finalization paths). */
  getText(): string {
    return this.text;
  }

  /** Replace the flush callback (e.g. when the setter identity changes). */
  setOnFlush(cb: (text: string) => void): void {
    this.onFlush = cb;
  }

  /** Flush any pending text immediately and stop scheduling. */
  finalize(): string {
    this.settled = true;
    if (this.rafId) {
      cancelAnimationFrame(this.rafId);
      this.rafId = 0;
    }
    const final = this.text;
    this.text = "";
    if (final) this.onFlush(final);
    return final;
  }

  /** Discard buffered text without flushing (used on Stop). */
  discard(): void {
    this.settled = true;
    if (this.rafId) {
      cancelAnimationFrame(this.rafId);
      this.rafId = 0;
    }
    this.text = "";
  }

  private schedule(): void {
    if (this.rafId || this.settled) return;
    // rAF may not exist in non-DOM environments (tests) — flush directly.
    if (typeof requestAnimationFrame === "undefined") {
      this.flush();
      return;
    }
    this.rafId = requestAnimationFrame(() => {
      this.rafId = 0;
      const now =
        typeof performance !== "undefined" ? performance.now() : Date.now();
      if (now - this.lastFlush >= this.throttleMs) {
        this.flush();
      } else {
        this.schedule();
      }
    });
  }

  private flush(): void {
    if (this.settled || !this.text) return;
    this.lastFlush =
      typeof performance !== "undefined" ? performance.now() : Date.now();
    this.onFlush(this.text);
  }
}

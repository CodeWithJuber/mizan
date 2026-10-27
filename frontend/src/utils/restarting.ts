/**
 * MIZAN restarts for a few seconds on every deploy. Meanwhile the proxy in
 * front of it answers 502/503 with its own page (not MIZAN's JSON). A read
 * that meets that waits for MIZAN to come back, through one shared health
 * probe, and is then sent once more; a write is never resent (it may have
 * reached MIZAN), it only gets a message that says what happened.
 */

export const RESTARTING_EVENT = "mizan:restarting";
export const BACK_EVENT = "mizan:back";
export const STILL_DOWN_EVENT = "mizan:still-down";
export const RESTART_MESSAGE =
  "MIZAN is restarting after an update; it is usually back within a minute. Please try again shortly.";

/** The proxy, not MIZAN, answered: MIZAN itself always answers in JSON. */
export function isRestarting(response: Response): boolean {
  if (response.status !== 502 && response.status !== 503) return false;
  return !(response.headers.get("content-type") || "").includes("application/json");
}

/** The health route next to an API URL ("…/api/chat/x" → "…/api/health"). */
export function healthUrl(input: string): string | null {
  const at = input.indexOf("/api/");
  return at < 0 ? null : `${input.slice(0, at)}/api/health`;
}

const DELAYS_MS = [1000, 2000, 3000, 5000];
const LIMIT_MS = 120_000;
let waiting: Promise<boolean> | null = null;

function announce(name: string) {
  try {
    window.dispatchEvent(new CustomEvent(name));
  } catch {
    /* no window (tests, workers) */
  }
}

const pause = (ms: number) => new Promise((done) => setTimeout(done, ms));

async function probe(url: string, sleep: (ms: number) => Promise<unknown>, limitMs: number) {
  const started = Date.now();
  for (let attempt = 0; Date.now() - started < limitMs; attempt++) {
    await sleep(DELAYS_MS[Math.min(attempt, DELAYS_MS.length - 1)]);
    try {
      const response = await fetch(url, { cache: "no-store" });
      if (response.ok) {
        announce(BACK_EVENT);
        return true;
      }
    } catch {
      /* still down, or the network blinked: keep probing until the limit */
    }
  }
  announce(STILL_DOWN_EVENT);
  return false;
}

/** Resolves true once MIZAN answers its health check again (false after the
 *  limit, or when this caller gives up). Every waiting request shares one probe. */
export function waitUntilBack(
  url: string,
  signal?: AbortSignal | null,
  options: { sleep?: (ms: number) => Promise<unknown>; limitMs?: number } = {},
): Promise<boolean> {
  if (!waiting) {
    announce(RESTARTING_EVENT);
    waiting = probe(url, options.sleep ?? pause, options.limitMs ?? LIMIT_MS).finally(() => {
      waiting = null;
    });
  }
  if (!signal) return waiting;
  if (signal.aborted) return Promise.resolve(false);
  return Promise.race([
    waiting,
    new Promise<boolean>((done) => signal.addEventListener("abort", () => done(false), { once: true })),
  ]);
}

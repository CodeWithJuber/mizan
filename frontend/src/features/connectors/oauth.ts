/**
 * Signing in to an OAuth connector. The window must open inside the click
 * (Safari and Firefox block a window.open that follows an await), so a blank
 * window opens first and is sent to the authorization page once the server
 * answers. Then MIZAN asks every 2 s how the sign-in went.
 */

export type OAuthPhase = "pending" | "connected" | "error" | "auth_required";

export interface OAuthSample {
  state: OAuthPhase;
  error?: string;
}

export type PollEnd =
  | { outcome: "connected" }
  | { outcome: "error"; error?: string }
  | { outcome: "auth_required"; error?: string }
  | { outcome: "timeout" };

/** GET /api/connectors/{id}/oauth/status */
export function readOAuthStatus(body: Record<string, unknown>): OAuthSample {
  const state = body.state;
  const error = typeof body.error === "string" && body.error ? body.error : undefined;
  if (state === "connected") return { state };
  if (state === "error" || state === "auth_required") return { state, ...(error ? { error } : {}) };
  return { state: "pending" };
}

/**
 * Older servers: the connector's own status. While a sign-in window is open
 * the connector still says auth_required (it is not signed in yet), so then
 * only connected and error end the wait.
 */
export function readConnectorPhase(status: string, lastError: string | null, signInOpen: boolean): OAuthSample {
  if (status === "connected") return { state: "connected" };
  if (status === "error") return { state: "error", ...(lastError ? { error: lastError } : {}) };
  if (status === "auth_required" && !signInOpen) return { state: "auth_required", ...(lastError ? { error: lastError } : {}) };
  return { state: "pending" };
}

/** Whether a sample ends the wait (attempt counts from 1). */
export function judge(sample: OAuthSample, attempt: number, maxAttempts: number): PollEnd | null {
  if (sample.state === "connected") return { outcome: "connected" };
  if (sample.state === "error") return { outcome: "error", ...(sample.error ? { error: sample.error } : {}) };
  if (sample.state === "auth_required") return { outcome: "auth_required", ...(sample.error ? { error: sample.error } : {}) };
  return attempt >= maxAttempts ? { outcome: "timeout" } : null;
}

export interface PollOptions {
  check: () => Promise<OAuthSample>;
  onEnd: (end: PollEnd) => void;
  intervalMs?: number;
  /** 150 × 2 s: five minutes to sign in. */
  maxAttempts?: number;
  /** Failed checks in a row before giving up. */
  maxFailures?: number;
}

/** Ask until the sign-in ends; returns a function that stops asking. */
export function pollOAuth({ check, onEnd, intervalMs = 2000, maxAttempts = 150, maxFailures = 3 }: PollOptions): () => void {
  let stopped = false;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let attempt = 0;
  let failures = 0;
  const finish = (end: PollEnd) => {
    if (stopped) return;
    stopped = true;
    onEnd(end);
  };
  const tick = async () => {
    if (stopped) return;
    attempt += 1;
    let sample: OAuthSample;
    try {
      sample = await check();
      failures = 0;
    } catch (problem) {
      failures += 1;
      if (failures >= maxFailures) {
        finish({ outcome: "error", error: problem instanceof Error ? problem.message : "MIZAN stopped answering." });
        return;
      }
      sample = { state: "pending" };
    }
    if (stopped) return;
    const end = judge(sample, attempt, maxAttempts);
    if (end) finish(end);
    else timer = setTimeout(tick, intervalMs);
  };
  timer = setTimeout(tick, intervalMs);
  return () => {
    stopped = true;
    if (timer !== undefined) clearTimeout(timer);
  };
}

/** Open the sign-in window now, inside the click; null when the browser blocked it. */
export function openSignInWindow(name: string): Window | null {
  let popup: Window | null = null;
  try {
    popup = window.open("about:blank", name, "popup,width=520,height=720");
  } catch {
    return null;
  }
  if (!popup) return null;
  try {
    // The authorization page must not reach back into MIZAN.
    popup.opener = null;
    popup.document.title = "Signing in…";
    popup.document.body.textContent = "Opening the sign-in page…";
  } catch {
    // A browser that does not allow it still opened the window.
  }
  return popup;
}

/** Send the window opened in the click to the authorization page. */
export function sendSignInWindow(popup: Window | null, url: string): boolean {
  if (!popup || popup.closed) return false;
  try {
    popup.location.href = url;
    return true;
  } catch {
    return false;
  }
}

export function closeSignInWindow(popup: Window | null) {
  try {
    if (popup && !popup.closed) popup.close();
  } catch {
    // Already gone, or the authorization page detached it.
  }
}

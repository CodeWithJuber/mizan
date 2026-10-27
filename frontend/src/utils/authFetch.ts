/**
 * authFetch.ts — JWT-authenticated fetch wrapper.
 *
 * Wraps fetch with the stored JWT (same pattern as PR #50 for /api/chat).
 * Extracted from App.tsx so panels/components can share one implementation.
 * Public endpoints (/health) keep using plain fetch().
 *
 * A read (GET/HEAD) that arrives while MIZAN restarts for a deploy waits for
 * it to come back and is sent once more; writes are never resent.
 */
import { healthUrl, isRestarting, waitUntilBack } from "./restarting.ts";

export async function authFetch(
  input: string,
  init: RequestInit = {},
): Promise<Response> {
  const response = await send(input, init);
  const method = (init.method || "GET").toUpperCase();
  const health = healthUrl(input);
  if ((method === "GET" || method === "HEAD") && health && isRestarting(response) &&
      await waitUntilBack(health, init.signal)) {
    await response.body?.cancel().catch(() => {});
    return send(input, init);
  }
  return response;
}

function send(input: string, init: RequestInit): Promise<Response> {
  const token = localStorage.getItem("mizan_token");
  const headers = new Headers(init.headers || {});
  if (token && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  return fetch(input, { ...init, headers }).then((response) => {
    if (
      response.status === 401 &&
      token &&
      headers.get("Authorization") === `Bearer ${token}` &&
      localStorage.getItem("mizan_token") === token
    ) {
      localStorage.removeItem("mizan_token");
      window.dispatchEvent(new CustomEvent("mizan:unauthorized"));
    }
    return response;
  });
}

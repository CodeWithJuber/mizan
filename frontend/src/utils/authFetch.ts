/**
 * authFetch.ts — JWT-authenticated fetch wrapper.
 *
 * Wraps fetch with the stored JWT (same pattern as PR #50 for /api/chat).
 * Extracted from App.tsx so panels/components can share one implementation.
 * Public endpoints (/version) keep using plain fetch().
 */
export function authFetch(
  input: string,
  init: RequestInit = {},
): Promise<Response> {
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

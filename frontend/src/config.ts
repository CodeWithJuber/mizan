/**
 * MIZAN Configuration
 * Centralized config — set via environment variables or defaults to localhost.
 */

/**
 * Resolve the WebSocket URL to an ABSOLUTE ws:// or wss:// URL.
 *
 * `new WebSocket()` — unlike `fetch()` — cannot resolve a relative path:
 * `new WebSocket("/ws/...")` throws and the socket never connects, leaving
 * the UI stuck on "Reconnecting..." / "Disconnected" forever. A relative
 * VITE_WS_URL (e.g. "/ws" from docker-compose.prod.yml) is therefore resolved
 * against the page's own origin here, so the build works on any domain with
 * no per-environment rebuild.
 */
function resolveWsUrl(raw: string): string {
  // Absolute URL already (dev default, or explicit wss://host/ws) — use as-is.
  if (/^wss?:\/\//.test(raw)) return raw;
  const scheme = window.location.protocol === "https:" ? "wss:" : "ws:";
  const path = raw.startsWith("/") ? raw : "/ws";
  return `${scheme}//${window.location.host}${path}`;
}

export const config = {
  API_URL: import.meta.env.VITE_API_URL || "http://localhost:8000/api",
  WS_URL: resolveWsUrl(
    (import.meta.env.VITE_WS_URL as string | undefined) || "ws://localhost:8000/ws",
  ),
};

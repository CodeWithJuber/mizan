/**
 * MIZAN Configuration
 * Centralized config — set via environment variables or defaults to localhost.
 */

export const config = {
  API_URL: import.meta.env.VITE_API_URL || "http://localhost:8000/api",
  WS_URL: import.meta.env.VITE_WS_URL || "ws://localhost:8000/ws",
};

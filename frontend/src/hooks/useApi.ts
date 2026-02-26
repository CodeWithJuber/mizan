/**
 * API Hook for MIZAN
 * Centralized API calls with auth support
 */

import { useCallback } from "react";
import type { ApiClient } from "../types";
import { config } from "../config";

export function useApi(): ApiClient {
  const getToken = useCallback(() => {
    return localStorage.getItem("mizan_token") || "";
  }, []);

  const headers = useCallback(() => {
    const h: Record<string, string> = { "Content-Type": "application/json" };
    const token = getToken();
    if (token) h["Authorization"] = `Bearer ${token}`;
    return h;
  }, [getToken]);

  const get = useCallback(
    async (path: string) => {
      const res = await fetch(`${config.API_URL}${path}`, { headers: headers() });
      return res.json();
    },
    [headers],
  );

  const post = useCallback(
    async (path: string, body?: Record<string, unknown>) => {
      const res = await fetch(`${config.API_URL}${path}`, {
        method: "POST",
        headers: headers(),
        body: JSON.stringify(body),
      });
      return res.json();
    },
    [headers],
  );

  const del = useCallback(
    async (path: string) => {
      const res = await fetch(`${config.API_URL}${path}`, {
        method: "DELETE",
        headers: headers(),
      });
      return res.json();
    },
    [headers],
  );

  return { get, post, del, API_URL: config.API_URL };
}

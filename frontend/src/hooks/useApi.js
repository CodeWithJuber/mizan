/**
 * API Hook for MIZAN
 * Centralized API calls with auth support
 */

import { useCallback } from "react";

const API_URL = "http://localhost:8000/api";

export function useApi() {
  const getToken = useCallback(() => {
    return localStorage.getItem("mizan_token") || "";
  }, []);

  const headers = useCallback(() => {
    const h = { "Content-Type": "application/json" };
    const token = getToken();
    if (token) h["Authorization"] = `Bearer ${token}`;
    return h;
  }, [getToken]);

  const get = useCallback(
    async (path) => {
      const res = await fetch(`${API_URL}${path}`, { headers: headers() });
      return res.json();
    },
    [headers],
  );

  const post = useCallback(
    async (path, body) => {
      const res = await fetch(`${API_URL}${path}`, {
        method: "POST",
        headers: headers(),
        body: JSON.stringify(body),
      });
      return res.json();
    },
    [headers],
  );

  const del = useCallback(
    async (path) => {
      const res = await fetch(`${API_URL}${path}`, {
        method: "DELETE",
        headers: headers(),
      });
      return res.json();
    },
    [headers],
  );

  return { get, post, del, API_URL };
}

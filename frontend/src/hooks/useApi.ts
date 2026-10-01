/**
 * API Hook for MIZAN
 * Centralized API calls with auth support
 */

import { useCallback, useMemo } from "react";
import type { ApiClient } from "../types";
import { config } from "../config";
import { authFetch } from "../utils/authFetch";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function handleResponse(res: Response): Promise<Record<string, unknown>> {
  let data: Record<string, unknown> = {};
  try {
    data = (await res.json()) as Record<string, unknown>;
  } catch {
    // non-JSON body — keep empty
  }
  if (!res.ok) {
    const msg =
      (typeof data.detail === "string" && data.detail) ||
      (typeof data.error === "string" && data.error) ||
      `Request failed (${res.status})`;
    throw new ApiError(res.status, msg);
  }
  return data;
}

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
      const res = await authFetch(`${config.API_URL}${path}`, {
        headers: headers(),
      });
      return handleResponse(res);
    },
    [headers],
  );

  const post = useCallback(
    async (path: string, body?: Record<string, unknown>) => {
      const res = await authFetch(`${config.API_URL}${path}`, {
        method: "POST",
        headers: headers(),
        body: JSON.stringify(body),
      });
      return handleResponse(res);
    },
    [headers],
  );

  const put = useCallback(
    async (path: string, body?: Record<string, unknown>) => {
      const res = await authFetch(`${config.API_URL}${path}`, {
        method: "PUT",
        headers: headers(),
        body: JSON.stringify(body),
      });
      return handleResponse(res);
    },
    [headers],
  );

  const patch = useCallback(
    async (path: string, body?: Record<string, unknown>) => {
      const res = await authFetch(`${config.API_URL}${path}`, {
        method: "PATCH",
        headers: headers(),
        body: JSON.stringify(body),
      });
      return handleResponse(res);
    },
    [headers],
  );

  const del = useCallback(
    async (path: string) => {
      const res = await authFetch(`${config.API_URL}${path}`, {
        method: "DELETE",
        headers: headers(),
      });
      return handleResponse(res);
    },
    [headers],
  );

  return useMemo(
    () => ({ get, post, put, patch, del, API_URL: config.API_URL }),
    [get, post, put, patch, del],
  );
}

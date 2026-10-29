/**
 * Who is signed in. The token lives in localStorage (as before); this store
 * mirrors it and counts sign-in changes, so the chat, the socket and cached
 * server data reset when the person changes.
 */
import { create } from "zustand";
import { useQuery } from "@tanstack/react-query";
import { config } from "../config";
import { authFetch } from "../utils/authFetch";

const read = (): string | null => {
  try {
    return localStorage.getItem("mizan_token");
  } catch {
    return null;
  }
};

interface AuthState {
  token: string | null;
  /** Increments whenever the signed-in token changes. */
  revision: number;
  /** Set when the server rejected the token (not a deliberate sign-out). */
  expired: boolean;
}

export const useAuth = create<AuthState>(() => ({ token: read(), revision: 0, expired: false }));

function sync(expired = false) {
  const token = read();
  if (token === useAuth.getState().token) return;
  useAuth.setState((state) => ({ token, revision: state.revision + 1, expired: expired && !token }));
}

window.addEventListener("mizan:authchanged", () => sync());
window.addEventListener("mizan:unauthorized", () => sync(true));
window.addEventListener("storage", (event) => {
  if (event.key === "mizan_token") sync();
});

export function signIn(token: string) {
  localStorage.setItem("mizan_token", token);
  window.dispatchEvent(new CustomEvent("mizan:authchanged"));
}

export function signOut() {
  localStorage.removeItem("mizan_token");
  window.dispatchEvent(new CustomEvent("mizan:authchanged"));
}

export interface Me {
  user_id: string;
  username: string;
  roles: string[];
  credential: "token" | "api_key";
  expires_at: string | null;
}

/** GET /api/auth/me for the current token. */
export function useMe() {
  const { token, revision } = useAuth();
  return useQuery({
    queryKey: ["me", revision],
    enabled: Boolean(token),
    staleTime: 5 * 60_000,
    queryFn: async (): Promise<Me> => {
      const response = await authFetch(`${config.API_URL}/auth/me`);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return response.json();
    },
  });
}

export function useIsAdmin(): boolean {
  const { data } = useMe();
  return Boolean(data?.roles?.includes("admin"));
}

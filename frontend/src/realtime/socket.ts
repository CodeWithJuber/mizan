/**
 * The notification WebSocket (/ws/{client_id}). Chat text streams over
 * HTTP SSE; this socket carries task output, queue updates, artifacts and
 * the older audio path. One connection per signed-in token, mounted once by
 * the root layout; its status is a store any component can read.
 */
import { useEffect } from "react";
import { create } from "zustand";
import { config } from "../config";
import { useAuth } from "../app/auth";
import { addTerminalLine } from "./terminal";

export type SocketStatus = "connecting" | "connected" | "reconnecting" | "disconnected" | "auth_required";

interface SocketState {
  status: SocketStatus;
  attempts: number;
}

export const useSocketStatus = create<SocketState>(() => ({ status: "connecting", attempts: 0 }));

type Handler = (data: Record<string, unknown>) => void;
let handler: Handler = () => {};
let reconnectHandler: () => void = () => {};
let current: WebSocket | null = null;

/** The chat registers how socket frames are applied (only one listener). */
export function setSocketHandlers(onMessage: Handler, onReconnect: () => void) {
  handler = onMessage;
  reconnectHandler = onReconnect;
}

/** Send a frame on the open socket; false when it is not connected. */
export function sendSocket(payload: Record<string, unknown>): boolean {
  if (!current || current.readyState !== WebSocket.OPEN) return false;
  current.send(JSON.stringify(payload));
  return true;
}

const clientId = `client_${Date.now()}`;

/** Mount once: keeps the socket connected for the current token. */
export function useRealtimeSocket() {
  const revision = useAuth((state) => state.revision);
  useEffect(() => {
    let socket: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let attempts = 0;
    let disposed = false;
    const setStatus = (status: SocketStatus) => useSocketStatus.setState({ status, attempts });

    const connect = () => {
      if (disposed) return;
      const wsToken = localStorage.getItem("mizan_token");
      if (!wsToken) {
        setStatus("auth_required");
        return;
      }
      try {
        setStatus(attempts > 0 ? "reconnecting" : "connecting");
        const currentSocket = new WebSocket(`${config.WS_URL}/${clientId}?token=${encodeURIComponent(wsToken)}`);
        socket = currentSocket;
        const isCurrent = () =>
          !disposed && socket === currentSocket && wsToken === localStorage.getItem("mizan_token");

        currentSocket.onopen = () => {
          if (!isCurrent()) {
            currentSocket.close();
            return;
          }
          current = currentSocket;
          // attempts > 0 means this onopen follows a close: a reconnect.
          const wasReconnect = attempts > 0;
          attempts = 0;
          setStatus("connected");
          addTerminalLine("Connected to backend", "gold");
          // Stream events may have been missed while the socket was down.
          if (wasReconnect) reconnectHandler();
        };

        currentSocket.onmessage = (event) => {
          if (!isCurrent()) return;
          try {
            handler(JSON.parse(event.data));
          } catch {
            addTerminalLine("Invalid notification ignored", "warn");
          }
        };

        currentSocket.onclose = (event) => {
          if (!isCurrent()) return;
          current = null;
          if (event.code === 4401 || event.code === 1008) {
            setStatus("auth_required");
            return;
          }
          attempts++;
          setStatus(attempts >= 5 ? "disconnected" : "reconnecting");
          addTerminalLine("Connection lost. Reconnecting...", "warn");
          const delay = Math.min(3000 * Math.pow(1.5, attempts - 1), 15000);
          reconnectTimer = setTimeout(connect, delay);
        };

        currentSocket.onerror = () => {
          if (!isCurrent()) return;
          addTerminalLine("Connection error", "error");
        };
      } catch (error: unknown) {
        addTerminalLine(`Connection failed: ${(error as Error).message}`, "error");
        attempts++;
        reconnectTimer = setTimeout(connect, 5000);
      }
    };

    connect();
    return () => {
      disposed = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      if (socket) socket.close();
      if (current === socket) current = null;
    };
  }, [revision]);
}

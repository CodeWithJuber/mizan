/**
 * WebSocket Hook for MIZAN
 * Manages connection lifecycle and message handling
 */

import { useState, useEffect, useRef, useCallback } from "react";
import type { WsConnectionStatus, WsMessage } from "../types";

const WS_URL = "ws://localhost:8000/ws";

interface UseWebSocketReturn {
  ws: WebSocket | null;
  status: WsConnectionStatus;
  send: (data: WsMessage) => void;
  clientId: string;
}

export function useWebSocket(onMessage: (data: WsMessage) => void): UseWebSocketReturn {
  const [ws, setWs] = useState<WebSocket | null>(null);
  const [status, setStatus] = useState<WsConnectionStatus>("disconnected");
  const clientId = useRef(`client_${Date.now()}`);
  const onMessageRef = useRef(onMessage);

  useEffect(() => {
    onMessageRef.current = onMessage;
  }, [onMessage]);

  useEffect(() => {
    let socket: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

    const connect = () => {
      try {
        socket = new WebSocket(`${WS_URL}/${clientId.current}`);

        socket.onopen = () => {
          setStatus("connected");
          setWs(socket);
        };

        socket.onmessage = (event: MessageEvent) => {
          const data = JSON.parse(event.data) as WsMessage;
          onMessageRef.current?.(data);
        };

        socket.onclose = () => {
          setStatus("disconnected");
          setWs(null);
          reconnectTimer = setTimeout(connect, 3000);
        };

        socket.onerror = () => {
          setStatus("error");
        };
      } catch {
        reconnectTimer = setTimeout(connect, 5000);
      }
    };

    connect();

    return () => {
      if (reconnectTimer) clearTimeout(reconnectTimer);
      if (socket) socket.close();
    };
  }, []);

  const send = useCallback(
    (data: WsMessage) => {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify(data));
      }
    },
    [ws],
  );

  return { ws, status, send, clientId: clientId.current };
}

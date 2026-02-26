/**
 * WebSocket Hook for MIZAN
 * Manages connection lifecycle and message handling
 */

import { useState, useEffect, useRef, useCallback } from "react";
import type { WsConnectionStatus, WsMessage } from "../types";
import { config } from "../config";

interface UseWebSocketReturn {
  ws: WebSocket | null;
  status: WsConnectionStatus;
  send: (data: WsMessage) => void;
  clientId: string;
  reconnectAttempts: number;
}

export function useWebSocket(onMessage: (data: WsMessage) => void): UseWebSocketReturn {
  const [ws, setWs] = useState<WebSocket | null>(null);
  const [status, setStatus] = useState<WsConnectionStatus>("connecting");
  const [reconnectAttempts, setReconnectAttempts] = useState(0);
  const clientId = useRef(`client_${Date.now()}`);
  const onMessageRef = useRef(onMessage);

  useEffect(() => {
    onMessageRef.current = onMessage;
  }, [onMessage]);

  useEffect(() => {
    let socket: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let attempts = 0;

    const connect = () => {
      try {
        if (attempts > 0) {
          setStatus("reconnecting");
        } else {
          setStatus("connecting");
        }

        socket = new WebSocket(`${config.WS_URL}/${clientId.current}`);

        socket.onopen = () => {
          setStatus("connected");
          setWs(socket);
          attempts = 0;
          setReconnectAttempts(0);
        };

        socket.onmessage = (event: MessageEvent) => {
          const data = JSON.parse(event.data) as WsMessage;
          onMessageRef.current?.(data);
        };

        socket.onclose = () => {
          setWs(null);
          attempts++;
          setReconnectAttempts(attempts);
          if (attempts >= 5) {
            setStatus("disconnected");
          } else {
            setStatus("reconnecting");
          }
          const delay = Math.min(3000 * Math.pow(1.5, attempts - 1), 15000);
          reconnectTimer = setTimeout(connect, delay);
        };

        socket.onerror = () => {
          setStatus("error");
        };
      } catch {
        attempts++;
        setReconnectAttempts(attempts);
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

  return { ws, status, send, clientId: clientId.current, reconnectAttempts };
}

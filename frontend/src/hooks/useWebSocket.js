/**
 * WebSocket Hook for MIZAN
 * Manages connection lifecycle and message handling
 */

import { useState, useEffect, useRef, useCallback } from "react";

const WS_URL = "ws://localhost:8000/ws";

export function useWebSocket(onMessage) {
  const [ws, setWs] = useState(null);
  const [status, setStatus] = useState("disconnected");
  const clientId = useRef(`client_${Date.now()}`);
  const onMessageRef = useRef(onMessage);

  useEffect(() => {
    onMessageRef.current = onMessage;
  }, [onMessage]);

  useEffect(() => {
    let socket = null;
    let reconnectTimer = null;

    const connect = () => {
      try {
        socket = new WebSocket(`${WS_URL}/${clientId.current}`);

        socket.onopen = () => {
          setStatus("connected");
          setWs(socket);
        };

        socket.onmessage = (event) => {
          const data = JSON.parse(event.data);
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
      } catch (e) {
        reconnectTimer = setTimeout(connect, 5000);
      }
    };

    connect();

    return () => {
      clearTimeout(reconnectTimer);
      if (socket) socket.close();
    };
  }, []);

  const send = useCallback(
    (data) => {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify(data));
      }
    },
    [ws],
  );

  return { ws, status, send, clientId: clientId.current };
}

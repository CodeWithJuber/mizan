/**
 * useTrainingWebSocket — Real-time training progress via WebSocket
 * Connects to the Mizan WS endpoint and listens for training_progress messages.
 */

import { useState, useEffect, useRef, useCallback } from "react";
import { config } from "../config";
import type { TrainingMetrics } from "../types/ruh";

const RECONNECT_DELAY_MS = 3000;
const HEARTBEAT_INTERVAL_MS = 30000;

const INITIAL_METRICS: TrainingMetrics = {
  running: false,
  stage: null,
  epoch: 0,
  total_epochs: 0,
  step: 0,
  total_steps: 0,
  loss: null,
  lr: null,
  progress_pct: 0,
  elapsed: 0,
  dataset_size: 0,
  model_params: 0,
  message: "Connecting...",
  losses: [],
};

export function useTrainingWebSocket(): {
  metrics: TrainingMetrics;
  connected: boolean;
} {
  const [metrics, setMetrics] = useState<TrainingMetrics>(INITIAL_METRICS);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const heartbeatTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  const clientId = useRef(`training-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`);

  const connect = useCallback(() => {
    // Clean up existing
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }

    const wsUrl = `${config.WS_URL}/${clientId.current}`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnected(true);
      // Start heartbeat
      heartbeatTimer.current = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: "ping" }));
        }
      }, HEARTBEAT_INTERVAL_MS);
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === "training_progress") {
          setMetrics({
            running: data.running ?? false,
            stage: data.stage ?? null,
            epoch: data.epoch ?? 0,
            total_epochs: data.total_epochs ?? 0,
            step: data.step ?? 0,
            total_steps: data.total_steps ?? 0,
            loss: data.loss ?? null,
            lr: data.lr ?? null,
            progress_pct: data.progress_pct ?? 0,
            elapsed: data.elapsed ?? 0,
            dataset_size: data.dataset_size ?? 0,
            model_params: data.model_params ?? 0,
            message: data.message ?? "",
            losses: data.losses ?? [],
          });
        }
      } catch {
        // Ignore malformed messages
      }
    };

    ws.onclose = () => {
      setConnected(false);
      if (heartbeatTimer.current) clearInterval(heartbeatTimer.current);
      // Auto-reconnect
      reconnectTimer.current = setTimeout(connect, RECONNECT_DELAY_MS);
    };

    ws.onerror = () => {
      ws.close();
    };
  }, []);

  useEffect(() => {
    connect();
    return () => {
      if (wsRef.current) wsRef.current.close();
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      if (heartbeatTimer.current) clearInterval(heartbeatTimer.current);
    };
  }, [connect]);

  return { metrics, connected };
}

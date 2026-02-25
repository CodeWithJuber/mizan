/**
 * Channels Page (Bab - باب - Gate)
 * Multi-channel dashboard for gateway management
 */

import { useState, useEffect, useCallback } from "react";
import type { PageProps, Channel, ChannelInfo, GatewayStatus } from "../types";

const CHANNEL_TYPES: Record<string, ChannelInfo> = {
  webchat: { name: "WebChat", arabic: "محادثة", color: "#3b82f6", icon: "💬" },
  telegram: { name: "Telegram", arabic: "تلغرام", color: "#0088cc", icon: "✈️" },
  discord: { name: "Discord", arabic: "ديسكورد", color: "#5865F2", icon: "🎮" },
  slack: { name: "Slack", arabic: "سلاك", color: "#4A154B", icon: "💼" },
  whatsapp: { name: "WhatsApp", arabic: "واتساب", color: "#25D366", icon: "📱" },
};

export default function ChannelsPage({ api, addTerminalLine }: PageProps) {
  const [channels, setChannels] = useState<Channel[]>([]);
  const [gatewayStatus, setGatewayStatus] = useState<GatewayStatus | null>(null);
  const [showConfig, setShowConfig] = useState<string | null>(null);

  const loadChannels = useCallback(async () => {
    try {
      const data = await api.get("/gateway/channels");
      setChannels((data.channels as Channel[]) || []);
    } catch {
      setChannels(
        Object.entries(CHANNEL_TYPES).map(([id, info]) => ({
          id,
          type: id,
          name: info.name,
          status: "disconnected" as const,
          connected_users: 0,
          messages_processed: 0,
        })),
      );
    }
  }, [api]);

  const loadGatewayStatus = useCallback(async () => {
    try {
      const data = await api.get("/gateway/status");
      setGatewayStatus(data as unknown as GatewayStatus);
    } catch {
      setGatewayStatus({ status: "offline", channels: 0, sessions: 0 });
    }
  }, [api]);

  useEffect(() => {
    loadChannels();
    loadGatewayStatus();
  }, [loadChannels, loadGatewayStatus]);

  const toggleChannel = async (channelId: string) => {
    try {
      await api.post(`/gateway/channels/${channelId}/toggle`);
      addTerminalLine?.(`Channel ${channelId} toggled`, "gold");
      loadChannels();
    } catch {
      addTerminalLine?.(`Failed to toggle channel ${channelId}`, "error");
    }
  };

  return (
    <>
      <div className="panel-header">
        <div className="panel-title">Channels · أبواب (Bab)</div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <div
            style={{
              fontSize: 10,
              fontFamily: "var(--font-mono)",
              color: gatewayStatus?.status === "online" ? "var(--emerald)" : "var(--ruby)",
              display: "flex",
              alignItems: "center",
              gap: 4,
            }}
          >
            <div
              style={{
                width: 6,
                height: 6,
                borderRadius: "50%",
                background:
                  gatewayStatus?.status === "online" ? "var(--emerald)" : "var(--ruby)",
              }}
            />
            Gateway {gatewayStatus?.status || "offline"}
          </div>
        </div>
      </div>

      <div
        style={{
          padding: "4px 16px 8px",
          fontSize: 11,
          color: "var(--text-muted)",
          fontStyle: "italic",
        }}
      >
        "Enter upon them through the gate (Bab)" — Quran 5:23
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
          gap: 12,
          padding: 16,
          overflow: "auto",
          flex: 1,
        }}
      >
        {Object.entries(CHANNEL_TYPES).map(([type, info]) => {
          const channel = channels.find((c) => c.type === type) || {} as Partial<Channel>;
          const isConnected = channel.status === "connected";

          return (
            <div
              key={type}
              style={{
                background:
                  "linear-gradient(135deg, rgba(15,32,48,0.9) 0%, rgba(10,21,32,0.9) 100%)",
                border: `1px solid ${isConnected ? info.color + "40" : "var(--border)"}`,
                borderRadius: 10,
                padding: 16,
                position: "relative",
                overflow: "hidden",
              }}
            >
              <div
                style={{
                  position: "absolute",
                  top: 0,
                  left: 0,
                  right: 0,
                  height: 2,
                  background: `linear-gradient(90deg, transparent, ${info.color}, transparent)`,
                  opacity: isConnected ? 1 : 0.2,
                }}
              />

              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 12,
                  marginBottom: 12,
                }}
              >
                <div
                  style={{
                    width: 40,
                    height: 40,
                    borderRadius: "50%",
                    background: `${info.color}15`,
                    border: `1px solid ${info.color}30`,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontSize: 18,
                  }}
                >
                  {info.icon}
                </div>
                <div style={{ flex: 1 }}>
                  <div
                    style={{
                      fontFamily: "var(--font-display)",
                      fontSize: 13,
                      color: "var(--text-primary)",
                      fontWeight: 600,
                    }}
                  >
                    {info.name}
                  </div>
                  <div
                    style={{
                      fontFamily: "Georgia, serif",
                      fontSize: 12,
                      color: `${info.color}80`,
                    }}
                  >
                    {info.arabic}
                  </div>
                </div>
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 4,
                    fontSize: 10,
                    fontFamily: "var(--font-mono)",
                    padding: "2px 8px",
                    borderRadius: 10,
                    background: isConnected
                      ? "rgba(16,185,129,0.15)"
                      : "rgba(74,104,128,0.2)",
                    color: isConnected ? "var(--emerald)" : "var(--text-muted)",
                    border: `1px solid ${isConnected ? "rgba(16,185,129,0.3)" : "rgba(74,104,128,0.3)"}`,
                  }}
                >
                  {isConnected ? "ACTIVE" : "IDLE"}
                </div>
              </div>

              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "1fr 1fr",
                  gap: 6,
                  marginBottom: 12,
                }}
              >
                <div className="stat">
                  <span className="stat-value">{channel.connected_users || 0}</span>
                  <span className="stat-label">Users</span>
                </div>
                <div className="stat">
                  <span className="stat-value">{channel.messages_processed || 0}</span>
                  <span className="stat-label">Messages</span>
                </div>
              </div>

              <div style={{ display: "flex", gap: 6 }}>
                <button
                  className={`btn ${isConnected ? "" : "primary"}`}
                  style={{ flex: 1, justifyContent: "center", fontSize: 10 }}
                  onClick={() => toggleChannel(type)}
                >
                  {isConnected ? "Disconnect" : "Connect"}
                </button>
                <button
                  className="btn"
                  style={{ fontSize: 10 }}
                  onClick={() => setShowConfig(showConfig === type ? null : type)}
                >
                  Config
                </button>
              </div>

              {showConfig === type && (
                <div
                  style={{
                    marginTop: 10,
                    padding: 10,
                    background: "rgba(6,12,16,0.6)",
                    borderRadius: 6,
                    border: "1px solid rgba(30,58,85,0.3)",
                    fontSize: 11,
                    color: "var(--text-muted)",
                  }}
                >
                  <div style={{ marginBottom: 6, fontFamily: "var(--font-mono)" }}>
                    Configuration for {info.name}
                  </div>
                  {type === "telegram" && (
                    <div className="form-group" style={{ marginBottom: 0 }}>
                      <label className="form-label">Bot Token</label>
                      <input
                        className="form-input"
                        type="password"
                        placeholder="Enter Telegram bot token..."
                        style={{ fontSize: 11 }}
                      />
                    </div>
                  )}
                  {type === "discord" && (
                    <div className="form-group" style={{ marginBottom: 0 }}>
                      <label className="form-label">Bot Token</label>
                      <input
                        className="form-input"
                        type="password"
                        placeholder="Enter Discord bot token..."
                        style={{ fontSize: 11 }}
                      />
                    </div>
                  )}
                  {type === "slack" && (
                    <div className="form-group" style={{ marginBottom: 0 }}>
                      <label className="form-label">Slack App Token</label>
                      <input
                        className="form-input"
                        type="password"
                        placeholder="Enter Slack app token..."
                        style={{ fontSize: 11 }}
                      />
                    </div>
                  )}
                  {type === "whatsapp" && (
                    <div className="form-group" style={{ marginBottom: 0 }}>
                      <label className="form-label">Cloud API Token</label>
                      <input
                        className="form-input"
                        type="password"
                        placeholder="Enter WhatsApp API token..."
                        style={{ fontSize: 11 }}
                      />
                    </div>
                  )}
                  {type === "webchat" && (
                    <div
                      style={{
                        fontFamily: "var(--font-mono)",
                        fontSize: 10,
                        color: "var(--emerald)",
                      }}
                    >
                      WebChat is built-in via WebSocket at ws://localhost:8000/ws
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </>
  );
}

/**
 * Channels Page (Bab - باب - Gate)
 * Multi-channel dashboard for gateway management
 */

import { useState, useEffect, useCallback } from "react";
import type { PageProps, Channel, ChannelInfo, GatewayStatus, Integration } from "../types";

const CHANNEL_TYPES: Record<string, ChannelInfo & { tw: { text: string; bg: string; border: string } }> = {
  webchat: { name: "WebChat", arabic: "محادثة", color: "#3b82f6", icon: "💬", tw: { text: "text-blue-500", bg: "bg-blue-500/10", border: "border-blue-500/30" } },
  telegram: { name: "Telegram", arabic: "تلغرام", color: "#0088cc", icon: "✈️", tw: { text: "text-sky-500", bg: "bg-sky-500/10", border: "border-sky-500/30" } },
  discord: { name: "Discord", arabic: "ديسكورد", color: "#5865F2", icon: "🎮", tw: { text: "text-indigo-500", bg: "bg-indigo-500/10", border: "border-indigo-500/30" } },
  slack: { name: "Slack", arabic: "سلاك", color: "#4A154B", icon: "💼", tw: { text: "text-purple-600", bg: "bg-purple-600/10", border: "border-purple-600/30" } },
  whatsapp: { name: "WhatsApp", arabic: "واتساب", color: "#25D366", icon: "📱", tw: { text: "text-green-500", bg: "bg-green-500/10", border: "border-green-500/30" } },
};

export default function ChannelsPage({ api, addTerminalLine }: PageProps) {
  const [channels, setChannels] = useState<Channel[]>([]);
  const [integrations, setIntegrations] = useState<Integration[]>([]);
  const [gatewayStatus, setGatewayStatus] = useState<GatewayStatus | null>(null);
  const [showConfig, setShowConfig] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(true);

  const loadChannels = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.get("/gateway/channels");
      setChannels((data.channels as Channel[]) || []);
    } catch (err) {
      console.error("Failed to fetch channels, using defaults:", err);
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
    } finally {
      setLoading(false);
    }
  }, [api]);

  const loadIntegrations = useCallback(async () => {
    try {
      const data = await api.get("/integrations");
      setIntegrations((data.integrations as Integration[]) || []);
    } catch (err) {
      console.error("Failed to fetch integrations:", err);
    }
  }, [api]);

  const loadGatewayStatus = useCallback(async () => {
    try {
      const data = await api.get("/gateway/status");
      setGatewayStatus(data as unknown as GatewayStatus);
    } catch (err) {
      console.error("Failed to fetch gateway status:", err);
      setGatewayStatus({ status: "offline", channels: 0, sessions: 0 });
    }
  }, [api]);

  useEffect(() => {
    loadChannels();
    loadIntegrations();
    loadGatewayStatus();
  }, [loadChannels, loadIntegrations, loadGatewayStatus]);

  const toggleChannel = async (channelId: string) => {
    try {
      const integration = integrations.find((i) => i.type === channelId);
      if (integration) {
        await api.post("/integrations", {
          name: integration.name,
          type: integration.type,
          enabled: !integration.enabled,
          config: integration.config || {},
        });
      }
      await api.post(`/gateway/channels/${channelId}/toggle`);
      addTerminalLine?.(`Channel ${channelId} toggled`, "gold");
      loadChannels();
      loadIntegrations();
    } catch (err) {
      console.error("Failed to toggle channel:", err);
      addTerminalLine?.(`Failed to toggle channel ${channelId}`, "error");
    }
  };

  return (
    <div className="page-wrapper">
      <div className="page-header">
        <div>
          <h2 className="page-title">Channels</h2>
          <p className="page-description">أبواب (Bab) — Gateway management</p>
        </div>
        <div className={`flex items-center gap-1.5 text-2xs font-mono ${gatewayStatus?.status === "online" ? "text-emerald-500" : "text-red-500"}`}>
          <div className={`status-dot ${gatewayStatus?.status === "online" ? "status-dot-active" : "status-dot-busy"}`} />
          Gateway {gatewayStatus?.status || "offline"}
        </div>
      </div>

      <div className="quran-quote">
        "Enter upon them through the gate (Bab)" — Quran 5:23
      </div>

      {loading && <div className="loading-text">Loading channels...</div>}

      <div className="flex-1 overflow-y-auto p-5">
        <div className="card-grid">
          {Object.entries(CHANNEL_TYPES).map(([type, info]) => {
            const channel = channels.find((c) => c.type === type) || {} as Partial<Channel>;
            const integration = integrations.find((i) => i.type === type);
            const isConnected = channel.status === "connected" || (integration?.enabled === true);
            const tw = info.tw;

            return (
              <div key={type} className={`card ${isConnected ? tw.border : ""}`}>
                <div className="flex items-center gap-3 mb-3">
                  <div className={`w-10 h-10 rounded-full ${tw.bg} border ${tw.border} flex items-center justify-center text-lg`}>
                    {info.icon}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                      {info.name}
                    </div>
                    <div className={`text-xs font-arabic ${tw.text} opacity-60`}>
                      {info.arabic}
                    </div>
                  </div>
                  <span className={`badge text-2xs ${isConnected ? "badge-success" : "badge-warning"}`}>
                    {isConnected ? "ACTIVE" : "IDLE"}
                  </span>
                </div>

                <div className="grid grid-cols-2 gap-2 mb-3">
                  <div className="stat">
                    <span className="stat-value">{channel.connected_users || 0}</span>
                    <span className="stat-label">Users</span>
                  </div>
                  <div className="stat">
                    <span className="stat-value">{channel.messages_processed || 0}</span>
                    <span className="stat-label">Messages</span>
                  </div>
                </div>

                <div className="flex gap-2">
                  <button
                    className={`flex-1 ${isConnected ? "btn-secondary" : "btn-gold"} btn-sm`}
                    onClick={() => toggleChannel(type)}
                  >
                    {isConnected ? "Disconnect" : "Connect"}
                  </button>
                  <button
                    className="btn-secondary btn-sm"
                    onClick={() => setShowConfig(showConfig === type ? null : type)}
                  >
                    Config
                  </button>
                </div>

                {showConfig === type && (
                  <div className="detail-panel mt-3">
                    <div className="text-xs font-mono text-gray-500 dark:text-gray-400 mb-2">
                      Configuration for {info.name}
                    </div>
                    {type === "telegram" && (
                      <div>
                        <label className="form-label">Bot Token</label>
                        <input className="form-input" type="password" placeholder="Enter Telegram bot token..." />
                      </div>
                    )}
                    {type === "discord" && (
                      <div>
                        <label className="form-label">Bot Token</label>
                        <input className="form-input" type="password" placeholder="Enter Discord bot token..." />
                      </div>
                    )}
                    {type === "slack" && (
                      <div>
                        <label className="form-label">Slack App Token</label>
                        <input className="form-input" type="password" placeholder="Enter Slack app token..." />
                      </div>
                    )}
                    {type === "whatsapp" && (
                      <div>
                        <label className="form-label">Cloud API Token</label>
                        <input className="form-input" type="password" placeholder="Enter WhatsApp API token..." />
                      </div>
                    )}
                    {type === "webchat" && (
                      <div className="text-xs font-mono text-emerald-600 dark:text-emerald-400">
                        WebChat is built-in via WebSocket at ws://localhost:8000/ws
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

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
  const [loading, setLoading] = useState(true);
  const [tokenInputs, setTokenInputs] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const [testResults, setTestResults] = useState<Record<string, "idle" | "testing" | "success" | "failed">>({});
  const [channelStatuses, setChannelStatuses] = useState<Record<string, { connected: boolean; has_token: boolean }>>({});

  const loadChannels = useCallback(async () => {
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

  const loadChannelStatus = useCallback(async (name: string) => {
    if (name === "webchat") return;
    try {
      const data = await api.get(`/channels/${name}/status`) as { connected: boolean; has_token: boolean };
      setChannelStatuses((prev) => ({ ...prev, [name]: { connected: data.connected, has_token: data.has_token } }));
    } catch {
      setChannelStatuses((prev) => ({ ...prev, [name]: { connected: false, has_token: false } }));
    }
  }, [api]);

  useEffect(() => {
    setLoading(true);
    Promise.all([loadChannels(), loadGatewayStatus()]).finally(() => setLoading(false));
  }, [loadChannels, loadGatewayStatus]);

  useEffect(() => {
    Object.keys(CHANNEL_TYPES).forEach((name) => loadChannelStatus(name));
  }, [loadChannelStatus]);

  const saveToken = async (channelName: string) => {
    const token = tokenInputs[channelName];
    if (!token?.trim()) return;
    setSaving(true);
    setSaveMessage(null);
    try {
      await api.post("/settings", {
        section: "channel",
        provider: channelName,
        api_key: token.trim(),
      });
      setSaveMessage({ type: "success", text: `Token for ${CHANNEL_TYPES[channelName]?.name || channelName} saved successfully.` });
      setTokenInputs((prev) => ({ ...prev, [channelName]: "" }));
      addTerminalLine?.(`Channel ${channelName} token saved`, "gold");
      await loadChannels();
      await loadChannelStatus(channelName);
      setTimeout(() => setSaveMessage(null), 3000);
    } catch (err) {
      console.error("Failed to save token:", err);
      setSaveMessage({ type: "error", text: `Failed to save token for ${channelName}.` });
      addTerminalLine?.(`Failed to save channel ${channelName} token`, "error");
      setTimeout(() => setSaveMessage(null), 3000);
    } finally {
      setSaving(false);
    }
  };

  const testChannel = async (channelName: string) => {
    setTestResults((prev) => ({ ...prev, [channelName]: "testing" }));
    try {
      await api.post(`/channels/${channelName}/test`);
      setTestResults((prev) => ({ ...prev, [channelName]: "success" }));
      addTerminalLine?.(`Test message sent to ${channelName}`, "gold");
    } catch (err) {
      console.error("Failed to test channel:", err);
      setTestResults((prev) => ({ ...prev, [channelName]: "failed" }));
      addTerminalLine?.(`Failed to test ${channelName}`, "error");
    }
    setTimeout(() => setTestResults((prev) => ({ ...prev, [channelName]: "idle" })), 3000);
  };

  const startChannel = async (channelName: string) => {
    try {
      await api.post(`/channels/${channelName}/start`);
      addTerminalLine?.(`Channel ${channelName} started`, "gold");
      await loadChannels();
      await loadChannelStatus(channelName);
    } catch (err) {
      console.error("Failed to start channel:", err);
      addTerminalLine?.(`Failed to start ${channelName}`, "error");
    }
  };

  const stopChannel = async (channelName: string) => {
    try {
      await api.post(`/channels/${channelName}/stop`);
      addTerminalLine?.(`Channel ${channelName} stopped`, "gold");
      await loadChannels();
      await loadChannelStatus(channelName);
    } catch (err) {
      console.error("Failed to stop channel:", err);
      addTerminalLine?.(`Failed to stop ${channelName}`, "error");
    }
  };

  const getTokenPlaceholder = (type: string) => {
    switch (type) {
      case "telegram": return "Enter Telegram bot token...";
      case "discord": return "Enter Discord bot token...";
      case "slack": return "Enter Slack app token...";
      case "whatsapp": return "Enter WhatsApp Cloud API token...";
      default: return "Enter token...";
    }
  };

  const getTokenLabel = (type: string) => {
    switch (type) {
      case "telegram": return "Bot Token";
      case "discord": return "Bot Token";
      case "slack": return "Slack App Token";
      case "whatsapp": return "Cloud API Token";
      default: return "Token";
    }
  };

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-gray-500 dark:text-gray-400">Loading channels...</div>
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-3 border-b border-gray-200 dark:border-zinc-800">
        <div>
          <h2 className="page-title flex items-center gap-2">
            Channels · أبواب (Bab)
          </h2>
          <p className="page-description">
            "Enter upon them through the gate (Bab)" — Quran 5:23
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div
            className={`flex items-center gap-2 text-xs font-mono ${
              gatewayStatus?.status === "online"
                ? "text-emerald-600 dark:text-emerald-400"
                : "text-red-500 dark:text-red-400"
            }`}
          >
            <div
              className={`w-2 h-2 rounded-full ${
                gatewayStatus?.status === "online"
                  ? "bg-emerald-500"
                  : "bg-red-500"
              }`}
            />
            Gateway {gatewayStatus?.status || "offline"}
          </div>
        </div>
      </div>

      {/* Save feedback */}
      {saveMessage && (
        <div
          className={`mx-5 mt-3 p-3 rounded-lg text-sm ${
            saveMessage.type === "error"
              ? "bg-red-50 dark:bg-red-500/10 text-red-700 dark:text-red-400 border border-red-200 dark:border-red-500/20"
              : "bg-emerald-50 dark:bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-500/20"
          }`}
        >
          {saveMessage.text}
        </div>
      )}

      {/* Channel cards */}
      <div className="flex-1 overflow-y-auto p-5">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {Object.entries(CHANNEL_TYPES).map(([type, info]) => {
            const channel = channels.find((c) => c.type === type) || ({} as Partial<Channel>);
            const status = channelStatuses[type] ?? { connected: channel.status === "connected", has_token: false };
            const isConnected = channel.status === "connected" || status.connected;
            const testStatus = testResults[type] || "idle";
            const hasTokenInput = type !== "webchat";

            return (
              <div key={type} className="card">
                {/* Header: Icon + Name + Status */}
                <div className="flex items-center gap-3 mb-4">
                  <div
                    className="w-10 h-10 rounded-lg flex items-center justify-center text-lg"
                    style={{
                      backgroundColor: `${info.color}15`,
                      border: `1px solid ${info.color}40`,
                    }}
                  >
                    {info.icon}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="font-medium text-gray-900 dark:text-gray-100">
                      {info.name}
                    </div>
                    <div className="text-xs text-gray-500 dark:text-gray-400 font-serif">
                      {info.arabic}
                    </div>
                  </div>
                  <span
                    className={`badge ${
                      isConnected ? "badge-success" : "badge-warning"
                    }`}
                  >
                    {isConnected ? "Connected" : "Disconnected"}
                  </span>
                </div>

                {/* Status dot */}
                <div className="flex items-center gap-2 mb-3 text-xs text-gray-500 dark:text-gray-400">
                  <div
                    className={`w-2 h-2 rounded-full shrink-0 ${
                      isConnected ? "bg-emerald-500" : "bg-gray-300 dark:bg-zinc-600"
                    }`}
                  />
                  {isConnected ? "Active" : "Idle"}
                  {hasTokenInput && (
                    <span className="text-gray-400 dark:text-gray-500">
                      · {status.has_token ? "Token configured" : "No token"}
                    </span>
                  )}
                </div>

                {/* Stats */}
                <div className="grid grid-cols-2 gap-3 mb-4">
                  <div className="bg-gray-50 dark:bg-zinc-800/50 rounded-lg px-3 py-2">
                    <div className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                      {channel.connected_users ?? 0}
                    </div>
                    <div className="text-xs text-gray-500 dark:text-gray-400">Users</div>
                  </div>
                  <div className="bg-gray-50 dark:bg-zinc-800/50 rounded-lg px-3 py-2">
                    <div className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                      {channel.messages_processed ?? 0}
                    </div>
                    <div className="text-xs text-gray-500 dark:text-gray-400">Messages</div>
                  </div>
                </div>

                {/* Token input + Save + Test (for channels that need tokens) */}
                {hasTokenInput && (
                  <div className="space-y-2 mb-4">
                    <label className="text-xs text-gray-500 dark:text-gray-400 block">
                      {getTokenLabel(type)}
                    </label>
                    <div className="flex gap-2 flex-wrap">
                      <input
                        type="password"
                        placeholder={getTokenPlaceholder(type)}
                        value={tokenInputs[type] || ""}
                        onChange={(e) =>
                          setTokenInputs((prev) => ({ ...prev, [type]: e.target.value }))
                        }
                        className="input flex-1 min-w-0 text-sm font-mono"
                      />
                      <button
                        onClick={() => saveToken(type)}
                        disabled={!tokenInputs[type]?.trim() || saving}
                        className="btn-primary text-sm shrink-0 disabled:opacity-50"
                      >
                        Save
                      </button>
                      <button
                        onClick={() => testChannel(type)}
                        disabled={!status.has_token}
                        className="btn-secondary text-sm shrink-0 disabled:opacity-50"
                        title={!status.has_token ? "Save token first to test" : "Send test message"}
                      >
                        {testStatus === "testing"
                          ? "Testing..."
                          : testStatus === "success"
                            ? "OK"
                            : testStatus === "failed"
                              ? "Failed"
                              : "Test"}
                      </button>
                    </div>
                  </div>
                )}

                {type === "webchat" && (
                  <div className="mb-4 text-xs font-mono text-emerald-600 dark:text-emerald-400">
                    WebChat is built-in via WebSocket at ws://localhost:8000/ws
                  </div>
                )}

                {/* Start/Stop button */}
                {hasTokenInput && (
                  <button
                    onClick={() => (isConnected ? stopChannel(type) : startChannel(type))}
                    className={
                      isConnected
                        ? "btn-secondary text-sm w-full"
                        : "btn-gold text-sm w-full"
                    }
                  >
                    {isConnected ? "Stop" : "Start"}
                  </button>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

/**
 * Channels Page (Bab - باب - Gate)
 * Multi-channel dashboard for gateway management
 */

import { useState, useEffect, useCallback } from "react";
import type {
  PageProps,
  Channel,
  ChannelInfo,
  GatewayStatus,
  Integration,
} from "../types";
import { SkeletonCard } from "../components/Skeleton";
import { useToast } from "../components/Toast";
import { PasswordInput } from "../components/PasswordInput";

const CHANNEL_TYPES: Record<
  string,
  ChannelInfo & { tw: { text: string; bg: string; border: string } }
> = {
  webchat: {
    name: "WebChat",
    arabic: "محادثة",
    color: "#3b82f6",
    icon: "💬",
    tw: {
      text: "text-blue-500",
      bg: "bg-blue-500/10",
      border: "border-blue-500/30",
    },
  },
  telegram: {
    name: "Telegram",
    arabic: "تلغرام",
    color: "#0088cc",
    icon: "✈️",
    tw: {
      text: "text-sky-500",
      bg: "bg-sky-500/10",
      border: "border-sky-500/30",
    },
  },
  discord: {
    name: "Discord",
    arabic: "ديسكورد",
    color: "#5865F2",
    icon: "🎮",
    tw: {
      text: "text-indigo-500",
      bg: "bg-indigo-500/10",
      border: "border-indigo-500/30",
    },
  },
  slack: {
    name: "Slack",
    arabic: "سلاك",
    color: "#4A154B",
    icon: "💼",
    tw: {
      text: "text-purple-600",
      bg: "bg-purple-600/10",
      border: "border-purple-600/30",
    },
  },
  whatsapp: {
    name: "WhatsApp",
    arabic: "واتساب",
    color: "#25D366",
    icon: "📱",
    tw: {
      text: "text-green-500",
      bg: "bg-green-500/10",
      border: "border-green-500/30",
    },
  },
};

export default function ChannelsPage({ api, addTerminalLine }: PageProps) {
  const { addToast } = useToast();
  const [channels, setChannels] = useState<Channel[]>([]);
  const [integrations, setIntegrations] = useState<Integration[]>([]);
  const [gatewayStatus, setGatewayStatus] = useState<GatewayStatus | null>(
    null,
  );
  const [showConfig, setShowConfig] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [configTokens, setConfigTokens] = useState<Record<string, string>>({});
  const [configSaving, setConfigSaving] = useState<Record<string, boolean>>({});
  const [toggling, setToggling] = useState<Record<string, boolean>>({});
  const [retrying, setRetrying] = useState(false);

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
    // WebChat is built in — no backend start/stop exists for it.
    if (channelId === "webchat") {
      setShowConfig(showConfig === channelId ? null : channelId);
      return;
    }
    const channel = channels.find((c) => c.type === channelId);
    const integration = integrations.find((i) => i.type === channelId);
    const isConnected =
      channel?.status === "connected" || integration?.enabled === true;
    const displayName = CHANNEL_TYPES[channelId]?.name || channelId;

    if (isConnected && !window.confirm(`Stop the ${displayName} channel?`)) {
      return;
    }

    setToggling((prev) => ({ ...prev, [channelId]: true }));
    try {
      await api.post(
        `/channels/${channelId}/${isConnected ? "stop" : "start"}`,
      );
      addToast({
        type: "success",
        title: isConnected ? "Channel stopped" : "Channel started",
        description: `${displayName} channel ${isConnected ? "stopped" : "started"}.`,
      });
      await loadChannels();
      await loadGatewayStatus();
    } catch (e: any) {
      if (!isConnected) {
        // Most likely: no token saved yet — open Config so the user can add it.
        setShowConfig(channelId);
        addToast({
          type: "warning",
          title: "Token needed",
          description:
            e?.message || "Save your bot token below, then start the channel.",
        });
      } else {
        addToast({
          type: "error",
          title: "Couldn't stop channel",
          description: e?.message || "Please try again.",
        });
      }
    } finally {
      setToggling((prev) => ({ ...prev, [channelId]: false }));
    }
  };

  const saveConfigToken = async (channelId: string) => {
    const token = configTokens[channelId];
    if (!token) return;
    const displayName = CHANNEL_TYPES[channelId]?.name || channelId;
    setConfigSaving((prev) => ({ ...prev, [channelId]: true }));
    try {
      await api.post("/settings", {
        section: "channel",
        provider: channelId,
        api_key: token,
      });
      addToast({
        type: "success",
        title: "Token saved",
        description: `${displayName} token saved securely.`,
      });
      setConfigTokens((prev) => ({ ...prev, [channelId]: "" }));
      await loadChannels();
      await loadGatewayStatus();
    } catch (e: any) {
      addToast({
        type: "error",
        title: "Couldn't save token",
        description: e?.message || "Please try again.",
      });
    } finally {
      setConfigSaving((prev) => ({ ...prev, [channelId]: false }));
    }
  };

  const retryGateway = async () => {
    setRetrying(true);
    try {
      await Promise.all([loadGatewayStatus(), loadChannels()]);
    } finally {
      setRetrying(false);
    }
  };

  return (
    <div className="page-wrapper">
      <div className="page-header">
        <div>
          <h2 className="page-title">Channels</h2>
          <p className="page-description">أبواب (Bab) — Gateway management</p>
        </div>
        <div
          className={`flex items-center gap-1.5 text-2xs font-mono ${gatewayStatus?.status === "online" ? "text-emerald-500" : "text-red-500"}`}
        >
          <div
            className={`status-dot ${gatewayStatus?.status === "online" ? "status-dot-active" : "status-dot-busy"}`}
          />
          Gateway {gatewayStatus?.status || "offline"}
        </div>
      </div>

      <div className="quran-quote">
        "Enter upon them through the gate (Bab)" — Quran 5:23
      </div>

      {gatewayStatus && gatewayStatus.status !== "online" && !loading && (
        <div className="mx-5 mt-3 p-3 rounded-lg text-sm bg-amber-50 dark:bg-amber-500/10 text-amber-800 dark:text-amber-300 border border-amber-200 dark:border-amber-500/20 flex flex-col sm:flex-row sm:items-center gap-2">
          <span className="flex-1">
            Messaging is offline — channels can't connect right now.
          </span>
          <button
            onClick={retryGateway}
            disabled={retrying}
            className="btn-secondary btn-sm min-h-[44px] w-full sm:w-auto disabled:opacity-50"
          >
            {retrying ? "Retrying…" : "Retry"}
          </button>
        </div>
      )}

      {loading && (
        <div className="p-5" aria-live="polite">
          <div className="card-grid">
            <SkeletonCard count={5} />
          </div>
        </div>
      )}

      <div className="flex-1 overflow-y-auto p-5">
        <div className="card-grid">
          {Object.entries(CHANNEL_TYPES).map(([type, info]) => {
            const channel =
              channels.find((c) => c.type === type) || ({} as Partial<Channel>);
            const integration = integrations.find((i) => i.type === type);
            const isConnected =
              channel.status === "connected" || integration?.enabled === true;
            const tw = info.tw;

            return (
              <div
                key={type}
                className={`card ${isConnected ? tw.border : ""}`}
              >
                <div className="flex items-center gap-3 mb-3">
                  <div
                    className={`w-10 h-10 rounded-full ${tw.bg} border ${tw.border} flex items-center justify-center text-lg`}
                  >
                    {info.icon}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                      {info.name}
                    </div>
                    <div
                      className={`text-xs font-arabic ${tw.text} opacity-60`}
                    >
                      {info.arabic}
                    </div>
                  </div>
                  <span
                    className={`badge text-2xs ${isConnected ? "badge-success" : "badge-warning"}`}
                  >
                    {isConnected ? "Connected" : "Not connected"}
                  </span>
                </div>

                <div className="grid grid-cols-2 gap-2 mb-3">
                  <div className="stat">
                    <span className="stat-value">
                      {channel.connected_users || 0}
                    </span>
                    <span className="stat-label">Users</span>
                  </div>
                  <div className="stat">
                    <span className="stat-value">
                      {channel.messages_processed || 0}
                    </span>
                    <span className="stat-label">Messages</span>
                  </div>
                </div>

                <div className="flex gap-2">
                  <button
                    className={`flex-1 ${isConnected ? "btn-secondary" : "btn-gold"} btn-sm min-h-[44px] disabled:opacity-50`}
                    onClick={() => toggleChannel(type)}
                    disabled={toggling[type]}
                  >
                    {toggling[type]
                      ? isConnected
                        ? "Stopping…"
                        : "Starting…"
                      : isConnected
                        ? "Stop"
                        : type === "webchat"
                          ? "Setup"
                          : "Start"}
                  </button>
                  <button
                    className="btn-secondary btn-sm min-h-[44px]"
                    onClick={() =>
                      setShowConfig(showConfig === type ? null : type)
                    }
                  >
                    Config
                  </button>
                </div>

                {showConfig === type && (
                  <div className="detail-panel mt-3">
                    <div className="text-xs font-mono text-gray-500 dark:text-gray-400 mb-2">
                      Configuration for {info.name}
                    </div>
                    {type === "webchat" ? (
                      <div className="text-sm text-gray-600 dark:text-gray-300">
                        WebChat works automatically inside this app — nothing to
                        set up.
                      </div>
                    ) : (
                      <div className="flex flex-col sm:flex-row gap-2">
                        <div className="flex-1 min-w-0">
                          <label
                            className="form-label"
                            htmlFor={`${type}-token`}
                          >
                            {type === "slack"
                              ? "Slack App Token"
                              : type === "whatsapp"
                                ? "Cloud API Token"
                                : "Bot Token"}
                          </label>
                          <PasswordInput
                            value={configTokens[type] || ""}
                            onChange={(v) =>
                              setConfigTokens((prev) => ({
                                ...prev,
                                [type]: v,
                              }))
                            }
                            placeholder={`Enter ${info.name} token...`}
                            className="form-input w-full text-sm font-mono"
                            autoComplete="new-password"
                          />
                        </div>
                        <button
                          onClick={() => saveConfigToken(type)}
                          disabled={!configTokens[type] || configSaving[type]}
                          className="btn-primary btn-sm min-h-[44px] w-full sm:w-auto sm:self-end disabled:opacity-50"
                        >
                          {configSaving[type] ? "Saving…" : "Save token"}
                        </button>
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

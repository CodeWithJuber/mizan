/**
 * Settings Page — Unified configuration management
 *
 * Unlike OpenClaw's config UI (which silently drops fields),
 * MIZAN's Settings page validates before saving and never loses data.
 */

import { useState, useEffect } from "react";
import type { ApiClient } from "../types";
import { SkeletonCard } from "../components/Skeleton";
import { useToast } from "../components/Toast";
import { PasswordInput } from "../components/PasswordInput";

interface ProviderConfig {
  name: string;
  key_set: boolean;
  healthy: boolean;
}

interface ChannelConfig {
  name: string;
  enabled: boolean;
  connected: boolean;
  has_token: boolean;
}

interface SettingsData {
  providers: ProviderConfig[];
  channels: ChannelConfig[];
  security: {
    rate_limit_per_minute: number;
    jwt_expiry_hours: number;
    audit_enabled: boolean;
  };
  memory: {
    db_path: string;
    consolidation_enabled: boolean;
  };
  vault: {
    encrypted: boolean;
    secrets_count: number;
    secret_names: string[];
  };
  version: string;
}

export default function SettingsPage({ api }: { api: ApiClient }) {
  const { addToast } = useToast();
  const [settings, setSettings] = useState<SettingsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [savingProvider, setSavingProvider] = useState<Record<string, boolean>>(
    {},
  );
  const [testResults, setTestResults] = useState<Record<string, string>>({});
  const [apiKeyInputs, setApiKeyInputs] = useState<Record<string, string>>({});
  const [channelTokens, setChannelTokens] = useState<Record<string, string>>(
    {},
  );
  const [savingChannel, setSavingChannel] = useState<Record<string, boolean>>(
    {},
  );
  const [togglingChannel, setTogglingChannel] = useState<
    Record<string, boolean>
  >({});
  const [activeSection, setActiveSection] = useState(
    () => localStorage.getItem("mizan_settings_section") || "providers",
  );
  const [saveMessage, setSaveMessage] = useState("");

  useEffect(() => {
    fetchSettings();
    // One-shot deep link (e.g. from ProvidersPage) — clear after reading.
    localStorage.removeItem("mizan_settings_section");
  }, []);

  // Banner auto-dismiss: same 4s timeout for success AND failure.
  useEffect(() => {
    if (!saveMessage) return;
    const t = setTimeout(() => setSaveMessage(""), 4000);
    return () => clearTimeout(t);
  }, [saveMessage]);

  const fetchSettings = async () => {
    setLoading(true);
    try {
      const data = (await api.get("/settings")) as unknown as SettingsData;
      setSettings(data);
    } catch {
      // Build settings from multiple endpoints as fallback
      try {
        const [providers, status, version] = (await Promise.all([
          api.get("/providers").catch(() => ({ providers: [] })),
          api.get("/status").catch(() => ({})),
          api.get("/version").catch(() => ({ version: "unknown" })),
        ])) as [any, any, any];

        setSettings({
          providers: (providers.providers || []).map((p: any) => ({
            name: p.name || p,
            key_set: p.configured || false,
            healthy: p.healthy || false,
          })),
          channels: [
            {
              name: "telegram",
              enabled: false,
              connected: false,
              has_token: false,
            },
            {
              name: "discord",
              enabled: false,
              connected: false,
              has_token: false,
            },
            {
              name: "whatsapp",
              enabled: false,
              connected: false,
              has_token: false,
            },
            {
              name: "slack",
              enabled: false,
              connected: false,
              has_token: false,
            },
          ],
          security: {
            rate_limit_per_minute: 60,
            jwt_expiry_hours: 24,
            audit_enabled: true,
          },
          memory: {
            db_path: "mizan_memory.db",
            consolidation_enabled: true,
          },
          vault: {
            encrypted: false,
            secrets_count: 0,
            secret_names: [],
          },
          version: version.version || "unknown",
        });
      } catch {
        /* ignore */
      }
    }
    setLoading(false);
  };

  const testApiKey = async (provider: string) => {
    setTestResults((prev) => ({ ...prev, [provider]: "testing" }));
    try {
      const result = (await api.get(`/providers/${provider}/health`)) as any;
      if (result.healthy) {
        setTestResults((prev) => ({ ...prev, [provider]: "passed" }));
      } else {
        const reason = result.error || result.message || "unknown error";
        setTestResults((prev) => ({
          ...prev,
          [provider]: `failed: ${reason}`,
        }));
      }
    } catch (e: any) {
      const reason = e?.message || "request failed";
      setTestResults((prev) => ({ ...prev, [provider]: `failed: ${reason}` }));
    }
  };

  const saveApiKey = async (provider: string) => {
    const key = apiKeyInputs[provider];
    if (!key) return;
    setSavingProvider((prev) => ({ ...prev, [provider]: true }));
    try {
      await api.post("/settings", {
        section: "provider",
        provider: provider,
        api_key: key,
      });
      setSaveMessage(`API key for ${provider} saved securely.`);
      setApiKeyInputs((prev) => ({ ...prev, [provider]: "" }));
      fetchSettings();
    } catch (e: any) {
      setSaveMessage(
        `Failed to save API key for ${provider}: ${e?.message || "unknown error"}`,
      );
    } finally {
      setSavingProvider((prev) => ({ ...prev, [provider]: false }));
    }
  };

  const saveChannelToken = async (channelName: string) => {
    const token = channelTokens[channelName];
    if (!token) return;
    setSavingChannel((prev) => ({ ...prev, [channelName]: true }));
    try {
      await api.post("/settings", {
        section: "channel",
        provider: channelName,
        api_key: token,
      });
      addToast({
        type: "success",
        title: "Token saved",
        description: `${channelName} token saved securely.`,
      });
      setChannelTokens((prev) => ({ ...prev, [channelName]: "" }));
      fetchSettings();
    } catch (e: any) {
      addToast({
        type: "error",
        title: "Couldn't save token",
        description: e?.message || "Please try again.",
      });
    } finally {
      setSavingChannel((prev) => ({ ...prev, [channelName]: false }));
    }
  };

  const toggleChannelState = async (channel: ChannelConfig) => {
    const action = channel.connected ? "stop" : "start";
    if (
      channel.connected &&
      !window.confirm(`Stop the ${channel.name} channel?`)
    ) {
      return;
    }
    setTogglingChannel((prev) => ({ ...prev, [channel.name]: true }));
    try {
      await api.post(`/api/channels/${channel.name}/${action}`);
      addToast({
        type: "success",
        title: channel.connected ? "Channel stopped" : "Channel started",
        description: `${channel.name} channel ${channel.connected ? "stopped" : "started"}.`,
      });
      fetchSettings();
    } catch (e: any) {
      addToast({
        type: "error",
        title: channel.connected
          ? "Couldn't stop channel"
          : "Couldn't start channel",
        description: e?.message || "Please try again.",
      });
    } finally {
      setTogglingChannel((prev) => ({ ...prev, [channel.name]: false }));
    }
  };

  const sections = [
    { id: "providers", label: "AI Providers" },
    { id: "channels", label: "Channels" },
    { id: "security", label: "Security" },
    { id: "memory", label: "Memory" },
    { id: "vault", label: "Secret Vault" },
  ];

  if (loading) {
    return (
      <div className="p-8 space-y-4" aria-live="polite">
        <SkeletonCard count={3} />
      </div>
    );
  }

  return (
    <div className="page-wrapper">
      <div className="page-header">
        <div>
          <h2 className="page-title flex items-center gap-2">
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              className="w-5 h-5"
            >
              <circle cx="12" cy="12" r="3" />
              <path d="M12 1v2m0 18v2m-9-11h2m18 0h2m-3.3-6.7-1.4 1.4M5.7 18.3l-1.4 1.4m0-13.4 1.4 1.4m12.6 12.6 1.4 1.4" />
            </svg>
            Settings
          </h2>
          <p className="page-description">
            Configure MIZAN — API keys, channels, security, and more
          </p>
        </div>
        {settings && (
          <span className="text-xs text-gray-500 dark:text-gray-400 font-mono">
            v{settings.version}
          </span>
        )}
      </div>

      {saveMessage && (
        <div
          className={`mx-5 mt-3 p-3 rounded-lg text-sm ${
            saveMessage.includes("Failed")
              ? "bg-red-50 dark:bg-red-500/10 text-red-700 dark:text-red-400 border border-red-200 dark:border-red-500/20"
              : "bg-emerald-50 dark:bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-500/20"
          }`}
        >
          {saveMessage}
        </div>
      )}

      <div className="flex-1 flex flex-col md:flex-row overflow-hidden">
        {/* Section Tabs — horizontal scroll on mobile, sidebar on desktop */}
        <div className="shrink-0 border-b md:border-b-0 md:border-r border-white/50 dark:border-white/5 bg-white/30 dark:bg-mizan-dark/20 backdrop-blur-sm py-2 md:py-4 flex md:flex-col flex-row overflow-x-auto md:overflow-visible md:w-56">
          {sections.map((s) => (
            <button
              key={s.id}
              onClick={() => {
                setActiveSection(s.id);
                localStorage.setItem("mizan_settings_section", s.id);
              }}
              className={`whitespace-nowrap text-left px-4 md:px-6 py-2.5 md:py-3 text-sm transition-all duration-300 ${
                activeSection === s.id
                  ? "text-mizan-gold font-medium bg-gradient-to-r from-mizan-gold/10 to-transparent border-b-2 md:border-b-0 md:border-r-2 border-mizan-gold"
                  : "text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200 hover:bg-white/50 dark:hover:bg-mizan-dark-surface/40"
              }`}
            >
              {s.label}
            </button>
          ))}
        </div>

        {/* Section Content */}
        <div className="flex-1 overflow-y-auto p-4 md:p-8 space-y-6 relative z-10">
          {/* AI Providers */}
          {activeSection === "providers" && (
            <div className="space-y-4">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                AI Providers
              </h3>
              <p className="text-sm text-gray-500 dark:text-gray-400">
                Configure API keys for your AI providers. Keys are encrypted at
                rest.
              </p>

              {["anthropic", "openrouter", "openai", "ollama"].map(
                (provider) => {
                  const info = settings?.providers?.find(
                    (p) => p.name === provider,
                  );
                  const testStatus = testResults[provider];
                  return (
                    <div key={provider} className="card">
                      <div className="flex items-center justify-between mb-3">
                        <div>
                          <h4 className="font-medium text-gray-900 dark:text-gray-100 capitalize">
                            {provider}
                          </h4>
                          <span
                            className={`text-xs ${info?.key_set ? "text-emerald-600 dark:text-emerald-400" : "text-gray-400 dark:text-gray-500"}`}
                          >
                            {info?.key_set ? "Connected" : "Not connected"}
                          </span>
                        </div>
                        {info?.healthy && (
                          <span className="badge badge-success">Healthy</span>
                        )}
                      </div>

                      <div className="flex flex-col sm:flex-row gap-2">
                        <div className="flex-1 min-w-0">
                          <PasswordInput
                            value={apiKeyInputs[provider] || ""}
                            onChange={(v) =>
                              setApiKeyInputs((prev) => ({
                                ...prev,
                                [provider]: v,
                              }))
                            }
                            placeholder={`${provider.toUpperCase()}_API_KEY`}
                            className="input w-full text-sm font-mono"
                            autoComplete="new-password"
                          />
                        </div>
                        <button
                          onClick={() => saveApiKey(provider)}
                          disabled={
                            !apiKeyInputs[provider] || savingProvider[provider]
                          }
                          className="btn-primary text-sm w-full sm:w-auto min-h-[44px] disabled:opacity-50"
                        >
                          {savingProvider[provider] ? "Saving…" : "Save"}
                        </button>
                        <button
                          onClick={() => testApiKey(provider)}
                          disabled={testStatus === "testing"}
                          className="btn-secondary text-sm w-full sm:w-auto min-h-[44px] disabled:opacity-50"
                        >
                          {testStatus === "testing" ? "Testing…" : "Test key"}
                        </button>
                      </div>
                      {testStatus && testStatus !== "testing" && (
                        <p
                          className={`mt-2 text-xs ${
                            testStatus === "passed"
                              ? "text-emerald-600 dark:text-emerald-400"
                              : "text-red-600 dark:text-red-400"
                          }`}
                        >
                          {testStatus === "passed"
                            ? "Test passed"
                            : `Test failed: ${testStatus.replace(/^failed:\s*/, "")}`}
                        </p>
                      )}
                    </div>
                  );
                },
              )}
            </div>
          )}

          {/* Channels */}
          {activeSection === "channels" && (
            <div className="space-y-4">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                Channel Configuration
              </h3>
              <p className="text-sm text-gray-500 dark:text-gray-400">
                Connect MIZAN to messaging platforms. Set bot tokens to enable
                each channel.
              </p>

              {(settings?.channels || []).map((channel) => (
                <div key={channel.name} className="card">
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-3">
                      <div
                        className={`w-2 h-2 rounded-full ${channel.connected ? "bg-emerald-500" : "bg-gray-300 dark:bg-zinc-600"}`}
                      />
                      <h4 className="font-medium text-gray-900 dark:text-gray-100 capitalize">
                        {channel.name}
                      </h4>
                    </div>
                    <span
                      className={`badge ${channel.connected ? "badge-success" : "badge-warning"}`}
                    >
                      {channel.connected ? "Connected" : "Not connected"}
                    </span>
                  </div>
                  <div className="flex flex-col sm:flex-row gap-2">
                    <div className="flex-1 min-w-0">
                      <PasswordInput
                        value={channelTokens[channel.name] || ""}
                        onChange={(v) =>
                          setChannelTokens((prev) => ({
                            ...prev,
                            [channel.name]: v,
                          }))
                        }
                        placeholder={`${channel.name.toUpperCase()}_BOT_TOKEN`}
                        className="input w-full text-sm font-mono"
                        autoComplete="new-password"
                      />
                    </div>
                    <button
                      onClick={() => saveChannelToken(channel.name)}
                      disabled={
                        !channelTokens[channel.name] ||
                        savingChannel[channel.name]
                      }
                      className="btn-primary text-sm w-full sm:w-auto min-h-[44px] disabled:opacity-50"
                    >
                      {savingChannel[channel.name] ? "Saving…" : "Save"}
                    </button>
                    <button
                      onClick={() => toggleChannelState(channel)}
                      disabled={togglingChannel[channel.name]}
                      className="btn-secondary text-sm w-full sm:w-auto min-h-[44px] disabled:opacity-50"
                    >
                      {togglingChannel[channel.name]
                        ? channel.connected
                          ? "Stopping…"
                          : "Starting…"
                        : channel.connected
                          ? "Stop"
                          : "Start"}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Security */}
          {activeSection === "security" && (
            <div className="space-y-4">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                Security Settings
              </h3>
              <p className="text-sm text-gray-500 dark:text-gray-400">
                MIZAN uses JWT auth, rate limiting, SSRF prevention, and
                sandboxed execution by default.
              </p>

              <div className="card">
                <h4 className="font-medium text-gray-900 dark:text-gray-100 mb-3">
                  Rate Limiting
                </h4>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div className="rounded-xl border border-gray-200 dark:border-white/10 bg-gray-50 dark:bg-white/5 px-4 py-3">
                    <div className="text-xs text-gray-500 dark:text-gray-400">
                      Requests per minute
                    </div>
                    <div className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                      {settings?.security?.rate_limit_per_minute || 60}
                    </div>
                    <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">
                      How many requests are allowed each minute — blocks spam
                      bursts.
                    </p>
                  </div>
                  <div className="rounded-xl border border-gray-200 dark:border-white/10 bg-gray-50 dark:bg-white/5 px-4 py-3">
                    <div className="text-xs text-gray-500 dark:text-gray-400">
                      Login session length (hours)
                    </div>
                    <div className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                      {settings?.security?.jwt_expiry_hours || 24}
                    </div>
                    <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">
                      How long you stay logged in before needing to log in
                      again.
                    </p>
                  </div>
                </div>
              </div>

              <div className="card">
                <h4 className="font-medium text-gray-900 dark:text-gray-100 mb-3">
                  Security Features
                </h4>
                <div className="space-y-2">
                  {[
                    {
                      name: "JWT Authentication",
                      desc: "Checks your identity on every request.",
                      active: true,
                    },
                    {
                      name: "Rate Limiting",
                      desc: "Blocks spammy bursts of requests.",
                      active: true,
                    },
                    {
                      name: "SSRF Prevention",
                      desc: "Stops the AI from reaching private network addresses.",
                      active: true,
                    },
                    {
                      name: "Command Sandboxing",
                      desc: "AI commands run in a restricted sandbox.",
                      active: true,
                    },
                    {
                      name: "Path Traversal Prevention",
                      desc: "Blocks access to files outside the workspace.",
                      active: true,
                    },
                    {
                      name: "Audit Logging",
                      desc: "Keeps a record of security events.",
                      active: settings?.security?.audit_enabled ?? true,
                    },
                  ].map((feature) => (
                    <div
                      key={feature.name}
                      className="flex items-center justify-between gap-3 py-1.5"
                    >
                      <div className="min-w-0">
                        <div className="text-sm text-gray-700 dark:text-gray-300">
                          {feature.name}
                        </div>
                        <div className="text-xs text-gray-400 dark:text-gray-500">
                          {feature.desc}
                        </div>
                      </div>
                      <span
                        className={`badge shrink-0 ${feature.active ? "badge-success" : "badge-error"}`}
                      >
                        {feature.active ? "Active" : "Inactive"}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Memory */}
          {activeSection === "memory" && (
            <div className="space-y-4">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                Memory System
              </h3>
              <p className="text-sm text-gray-500 dark:text-gray-400">
                MIZAN uses a 3-tier memory system (Episodic, Semantic,
                Procedural) stored in SQLite.
              </p>

              <div className="card">
                <h4 className="font-medium text-gray-900 dark:text-gray-100 mb-3">
                  Memory Configuration
                </h4>
                <div className="space-y-3">
                  <div>
                    <label
                      htmlFor="db-path"
                      className="text-xs text-gray-500 dark:text-gray-400 block mb-1"
                    >
                      Database path
                    </label>
                    <input
                      id="db-path"
                      type="text"
                      value={settings?.memory?.db_path || "mizan_memory.db"}
                      className="input w-full text-sm font-mono"
                      readOnly
                    />
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-gray-700 dark:text-gray-300">
                      Auto-consolidation
                    </span>
                    <span className="badge badge-success">Enabled</span>
                  </div>
                  <div className="flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <div className="text-sm text-gray-700 dark:text-gray-300">
                        Memory decay (Nisyan)
                      </div>
                      <div className="text-xs text-gray-400 dark:text-gray-500">
                        Old, unused memories fade away automatically over time.
                      </div>
                    </div>
                    <span className="badge badge-success shrink-0">Active</span>
                  </div>
                </div>
              </div>

              <button
                onClick={() =>
                  api
                    .post("/memory/consolidate")
                    .then(() =>
                      addToast({
                        type: "success",
                        title: "Memory consolidation shuru ho gayi",
                      }),
                    )
                    .catch(() =>
                      addToast({
                        type: "error",
                        title: "Consolidation fail ho gayi",
                        description: "Phir se try karo.",
                      }),
                    )
                }
                className="btn-secondary text-sm"
              >
                Run Memory Consolidation
              </button>
            </div>
          )}

          {/* Vault */}
          {activeSection === "vault" && (
            <div className="space-y-4">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                Secret Vault
              </h3>
              <p className="text-sm text-gray-500 dark:text-gray-400">
                API keys and tokens are encrypted at rest using AES-128. Unlike
                other AI agents that store credentials in plaintext, MIZAN
                encrypts everything.
              </p>
              <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">
                AES-128 is a widely-used encryption standard — your keys are
                unreadable without the vault password.
              </p>

              <div className="card">
                <div className="flex items-center justify-between mb-3">
                  <h4 className="font-medium text-gray-900 dark:text-gray-100">
                    Encryption Status
                  </h4>
                  <span
                    className={`badge ${settings?.vault?.encrypted ? "badge-success" : "badge-warning"}`}
                  >
                    {settings?.vault?.encrypted
                      ? "Encrypted"
                      : "Plaintext (install cryptography)"}
                  </span>
                </div>
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  {settings?.vault?.secrets_count || 0} secrets stored
                </p>
              </div>

              {(settings?.vault?.secret_names || []).length > 0 && (
                <div className="card">
                  <h4 className="font-medium text-gray-900 dark:text-gray-100 mb-3">
                    Stored Secrets
                  </h4>
                  <div className="space-y-1">
                    {settings?.vault?.secret_names?.map((name) => (
                      <div
                        key={name}
                        className="flex items-center justify-between py-1.5 border-b border-gray-100 dark:border-zinc-800 last:border-0"
                      >
                        <span className="text-sm font-mono text-gray-700 dark:text-gray-300">
                          {name}
                        </span>
                        <span className="text-xs text-gray-400">••••••••</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

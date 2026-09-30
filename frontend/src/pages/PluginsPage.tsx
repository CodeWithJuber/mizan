/**
 * Wahy Plugin System Page (وحي — Revelation/Inspiration)
 * "And We have revealed to you the Book as clarification for all things" — Quran 16:89
 */

import { useState, useEffect, useCallback } from "react";
import {
  PageProps,
  Plugin,
  PluginType,
  TrustLevel,
  PluginHook,
} from "../types";
import { useToast } from "../components/Toast";
import { SkeletonCard } from "../components/Skeleton";

const TYPE_STYLES: Record<
  string,
  { text: string; bg: string; border: string; borderL: string }
> = {
  ayah: {
    text: "text-mizan-gold",
    bg: "bg-mizan-gold/10",
    border: "border-mizan-gold/30",
    borderL: "border-l-mizan-gold",
  },
  bab: {
    text: "text-blue-500",
    bg: "bg-blue-500/10",
    border: "border-blue-500/30",
    borderL: "border-l-blue-500",
  },
  hafiz: {
    text: "text-emerald-500",
    bg: "bg-emerald-500/10",
    border: "border-emerald-500/30",
    borderL: "border-l-emerald-500",
  },
  ruh: {
    text: "text-purple-500",
    bg: "bg-purple-500/10",
    border: "border-purple-500/30",
    borderL: "border-l-purple-500",
  },
  muaddib: {
    text: "text-amber-500",
    bg: "bg-amber-500/10",
    border: "border-amber-500/30",
    borderL: "border-l-amber-500",
  },
};

const TYPE_LABELS: Record<string, string> = {
  ayah: "آية · Tool",
  bab: "باب · Channel",
  hafiz: "حافظ · Memory",
  ruh: "روح · Provider",
  muaddib: "مؤدب · Middleware",
};

const TRUST_STYLES: Record<string, { text: string; bg: string }> = {
  ammara: { text: "text-red-500", bg: "bg-red-500/10" },
  lawwama: { text: "text-amber-500", bg: "bg-amber-500/10" },
  mulhama: { text: "text-amber-500", bg: "bg-amber-500/10" },
  mutmainna: { text: "text-emerald-500", bg: "bg-emerald-500/10" },
  radiya: { text: "text-emerald-500", bg: "bg-emerald-500/10" },
  mardiyya: { text: "text-emerald-500", bg: "bg-emerald-500/10" },
  kamila: { text: "text-emerald-500", bg: "bg-emerald-500/10" },
};

/** Plain-English trust labels with the Arabic nafs-stage as secondary text. */
const TRUST_LABELS: Record<string, { en: string; ar: string }> = {
  ammara: { en: "Unverified", ar: "أمّارة" },
  lawwama: { en: "Review needed", ar: "لوّامة" },
  mulhama: { en: "Review needed", ar: "مُلهَمة" },
  mutmainna: { en: "Trusted", ar: "مُطمئِنّة" },
  radiya: { en: "Trusted", ar: "راضية" },
  mardiyya: { en: "Trusted", ar: "مَرضيّة" },
  kamila: { en: "Trusted", ar: "كاملة" },
};

interface CreateForm {
  name: string;
  description: string;
  plugin_type: string;
  author: string;
}

interface PluginCardProps {
  plugin: Plugin;
  onActivate: (name: string) => void;
  onDeactivate: (name: string) => void;
  onReload: (name: string) => void;
  onVerify: (name: string) => void;
  pendingAction: string | null;
}

export default function PluginsPage({ api, addTerminalLine }: PageProps) {
  const { addToast } = useToast();
  const [activeTab, setActiveTab] = useState<string>("installed");
  const [plugins, setPlugins] = useState<Plugin[]>([]);
  const [hooks, setHooks] = useState<PluginHook[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [loadError, setLoadError] = useState<boolean>(false);
  const [pendingAction, setPendingAction] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState<boolean>(false);
  const [createForm, setCreateForm] = useState<CreateForm>({
    name: "",
    description: "",
    plugin_type: "ayah",
    author: "",
  });

  const exec = useCallback(
    async (action: string, extra: Record<string, unknown> = {}) => {
      try {
        return await api.post("/skills/execute", {
          skill: "wahy_plugins",
          action,
          ...extra,
        });
      } catch (e) {
        addToast({
          type: "error",
          title: (e as Error).message || "Plugin action fail ho gaya",
        });
        return null;
      }
    },
    [api, addToast],
  );

  const loadPlugins = useCallback(async () => {
    const data = await exec("list");
    if (data?.plugins) {
      setPlugins(data.plugins as Plugin[]);
      return true;
    }
    return false;
  }, [exec]);

  const loadHooks = useCallback(async () => {
    const data = await exec("hooks");
    if (data?.hooks) {
      setHooks(data.hooks as PluginHook[]);
      return true;
    }
    return false;
  }, [exec]);

  const loadAll = useCallback(async () => {
    setLoading(true);
    setLoadError(false);
    const [pluginsOk, hooksOk] = await Promise.all([
      loadPlugins(),
      loadHooks(),
    ]);
    if (!pluginsOk && !hooksOk) setLoadError(true);
    setLoading(false);
  }, [loadPlugins, loadHooks]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  const runAction = async (key: string, fn: () => Promise<void>) => {
    setPendingAction(key);
    try {
      await fn();
    } finally {
      setPendingAction(null);
    }
  };

  const activatePlugin = (name: string) =>
    runAction(`activate:${name}`, async () => {
      const data = await exec("activate", { name });
      if (data?.status === "activated") {
        addToast({
          type: "success",
          title: "Added — find it under Added",
        });
        addTerminalLine?.(`Plugin added: ${name}`, "gold");
        loadPlugins();
      } else if (data) {
        addToast({ type: "error", title: "Add nahi ho paya" });
      }
    });

  const deactivatePlugin = (name: string) =>
    runAction(`deactivate:${name}`, async () => {
      const data = await exec("deactivate", { name });
      if (data?.status === "deactivated") {
        addToast({ type: "success", title: "Plugin remove ho gaya" });
        addTerminalLine?.(`Plugin removed: ${name}`, "warn");
        loadPlugins();
      } else if (data) {
        addToast({ type: "error", title: "Remove nahi ho paya" });
      }
    });

  const reloadPlugin = (name: string) =>
    runAction(`reload:${name}`, async () => {
      const data = await exec("reload", { name });
      if (data?.status === "reloaded") {
        addToast({ type: "success", title: "Plugin reload ho gaya" });
        addTerminalLine?.(`Plugin hot-reloaded: ${name}`, "gold");
        loadPlugins();
      } else if (data) {
        addToast({ type: "error", title: "Reload nahi ho paya" });
      }
    });

  const verifyPlugin = (name: string) =>
    runAction(`verify:${name}`, async () => {
      const data = await exec("verify", { name });
      if (!data) return;
      const ok = !!data.verified;
      addToast({
        type: ok ? "success" : "error",
        title: ok ? "Plugin verified ✓" : "Verification fail ho gaya",
      });
      addTerminalLine?.(
        ok
          ? `Plugin verified: ${name} ✓`
          : `Plugin verification failed: ${name}`,
        ok ? "gold" : "error",
      );
    });

  const createPlugin = () =>
    runAction("create", async () => {
      const data = await exec(
        "create",
        createForm as unknown as Record<string, unknown>,
      );
      if (data?.created) {
        addToast({ type: "success", title: "Plugin scaffold ban gaya" });
        addTerminalLine?.(
          `Plugin scaffold created: ${createForm.name}`,
          "gold",
        );
        setShowCreate(false);
        setCreateForm({
          name: "",
          description: "",
          plugin_type: "ayah",
          author: "",
        });
        loadPlugins();
      } else if (data) {
        addToast({ type: "error", title: "Scaffold ban nahi paya" });
      }
    });

  const installed = plugins.filter((p) => p.active);
  const available = plugins.filter((p) => !p.active);

  return (
    <div className="page-wrapper">
      <div className="page-header">
        <div>
          <h2 className="page-title">Plugin System</h2>
          <p className="page-description">
            وَحْي (Wahy) — Extend Mizan with new abilities
          </p>
        </div>
      </div>

      <div className="quran-quote">
        "And We have revealed to you the Book as clarification for all things" —
        Quran 16:89
      </div>

      <div className="tab-bar">
        {[
          { id: "installed", label: `Added (${installed.length})` },
          { id: "available", label: `Available (${available.length})` },
          { id: "hooks", label: "Hooks" },
          { id: "create", label: "Create" },
        ].map((tab) => (
          <button
            key={tab.id}
            className={`tab ${activeTab === tab.id ? "active" : ""}`}
            onClick={() => setActiveTab(tab.id)}
            aria-selected={activeTab === tab.id}
            role="tab"
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div className="page-body">
        {loading && <SkeletonCard count={3} />}
        {!loading && loadError && (
          <div className="empty-state">
            <div className="empty-arabic">وحي</div>
            <div className="empty-text">Load nahi ho paya</div>
            <div className="empty-sub">
              Plugin list fetch fail ho gayi — connection check karo
            </div>
            <button
              className="btn-gold btn-sm min-h-[44px] mt-3"
              onClick={loadAll}
            >
              Dobara try karo
            </button>
          </div>
        )}
        {!loading && !loadError && activeTab === "installed" && (
          <>
            {installed.length === 0 && (
              <div className="empty-state">
                <div className="empty-arabic">وحي</div>
                <div className="empty-text">No added plugins</div>
                <div className="empty-sub">
                  Add plugins from the Available tab
                </div>
              </div>
            )}
            {installed.map((plugin) => (
              <PluginCard
                key={plugin.name}
                plugin={plugin}
                onActivate={activatePlugin}
                onDeactivate={deactivatePlugin}
                onReload={reloadPlugin}
                onVerify={verifyPlugin}
                pendingAction={pendingAction}
              />
            ))}
          </>
        )}

        {!loading && !loadError && activeTab === "available" && (
          <>
            {available.length === 0 && (
              <div className="empty-state">
                <div className="empty-arabic">وحي</div>
                <div className="empty-text">All plugins are active</div>
              </div>
            )}
            {available.map((plugin) => (
              <PluginCard
                key={plugin.name}
                plugin={plugin}
                onActivate={activatePlugin}
                onDeactivate={deactivatePlugin}
                onReload={reloadPlugin}
                onVerify={verifyPlugin}
                pendingAction={pendingAction}
              />
            ))}
          </>
        )}

        {!loading && !loadError && activeTab === "hooks" && (
          <>
            <div className="mb-3">
              <button
                className="btn-secondary btn-sm min-h-[44px]"
                onClick={loadAll}
              >
                Refresh
              </button>
            </div>
            {hooks.length === 0 && (
              <div className="empty-state">
                <div className="empty-arabic">ربط</div>
                <div className="empty-text">No hooks registered</div>
                <div className="empty-sub">
                  Plugins register hooks when activated
                </div>
              </div>
            )}
            <div className="card">
              <div className="text-2xs font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-widest mb-3">
                Event Hooks · خطافات
              </div>
              {hooks.map((hook, i) => (
                <div
                  key={i}
                  className="flex flex-wrap items-center gap-x-2 gap-y-1 px-2 py-1.5 rounded mb-1 bg-gray-50 dark:bg-zinc-800/50 border border-gray-100 dark:border-zinc-700/50"
                >
                  <span className="text-2xs font-mono text-blue-500 dark:text-blue-400 w-24 sm:w-40 shrink-0 truncate">
                    {hook.event}
                  </span>
                  <span className="text-2xs text-gray-900 dark:text-gray-100 min-w-0 flex-1 truncate">
                    {hook.plugin}
                  </span>
                  <span className="ml-auto text-micro font-mono text-gray-400 dark:text-gray-500 whitespace-nowrap">
                    priority: {hook.priority}
                  </span>
                </div>
              ))}
            </div>
          </>
        )}

        {activeTab === "create" && (
          <div className="max-w-xl space-y-4">
            <div className="form-panel">
              <div className="form-panel-title">Build a new plugin · إنشاء</div>
              <div className="form-group">
                <label className="form-label" htmlFor="plugin-name">
                  Plugin Name
                </label>
                <input
                  id="plugin-name"
                  className="form-input"
                  value={createForm.name}
                  onChange={(e) =>
                    setCreateForm({ ...createForm, name: e.target.value })
                  }
                  placeholder="my_custom_plugin"
                />
              </div>
              <div className="form-group">
                <label className="form-label" htmlFor="plugin-desc">
                  Description
                </label>
                <input
                  id="plugin-desc"
                  className="form-input"
                  value={createForm.description}
                  onChange={(e) =>
                    setCreateForm({
                      ...createForm,
                      description: e.target.value,
                    })
                  }
                  placeholder="e.g. Birthday Reminder"
                />
              </div>
              <div className="form-group">
                <label className="form-label">Plugin Type</label>
                <div className="grid grid-cols-2 gap-2">
                  {Object.entries(TYPE_LABELS).map(([type, label]) => {
                    const ts = TYPE_STYLES[type] || TYPE_STYLES.ayah;
                    return (
                      <button
                        key={type}
                        className={`p-2 rounded-lg border text-center text-xs font-medium transition-colors cursor-pointer
                          ${
                            createForm.plugin_type === type
                              ? `${ts.bg} ${ts.border} ${ts.text}`
                              : "bg-gray-50 dark:bg-zinc-800 border-gray-200 dark:border-zinc-700 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-zinc-700"
                          }`}
                        onClick={() =>
                          setCreateForm({ ...createForm, plugin_type: type })
                        }
                      >
                        {label}
                      </button>
                    );
                  })}
                </div>
              </div>
              <div className="form-group">
                <label className="form-label" htmlFor="plugin-author">
                  Author
                </label>
                <input
                  id="plugin-author"
                  className="form-input"
                  value={createForm.author}
                  onChange={(e) =>
                    setCreateForm({ ...createForm, author: e.target.value })
                  }
                  placeholder="Your name"
                />
              </div>
              <button
                className="btn-gold w-full py-2.5 min-h-[44px]"
                onClick={createPlugin}
                disabled={
                  !createForm.name ||
                  !createForm.description ||
                  pendingAction === "create"
                }
              >
                {pendingAction === "create"
                  ? "Ban raha hai…"
                  : "Create Plugin Scaffold"}
              </button>
            </div>

            <div className="card">
              <div className="text-xxs font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-widest mb-3">
                Plugin Types
              </div>
              {Object.entries(TYPE_LABELS).map(([type, label]) => {
                const ts = TYPE_STYLES[type] || TYPE_STYLES.ayah;
                return (
                  <div key={type} className="flex items-center gap-2 py-1">
                    <span
                      className={`w-2 h-2 rounded-full ${ts.bg} border ${ts.border}`}
                    />
                    <span className={`text-xs ${ts.text}`}>{label}</span>
                    <span className="text-2xs text-gray-400 dark:text-gray-500">
                      {type === "ayah"
                        ? "— Add new tool capabilities"
                        : type === "bab"
                          ? "— New communication channels"
                          : type === "hafiz"
                            ? "— Custom memory backends"
                            : type === "ruh"
                              ? "— AI model providers"
                              : "— Request/response transforms"}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function PluginCard({
  plugin,
  onActivate,
  onDeactivate,
  onReload,
  onVerify,
  pendingAction,
}: PluginCardProps) {
  const [expanded, setExpanded] = useState<boolean>(false);
  const ts = TYPE_STYLES[plugin.plugin_type] || {
    text: "text-gray-500",
    bg: "bg-gray-500/10",
    border: "border-gray-500/30",
    borderL: "border-l-gray-400",
  };
  const trust = (plugin.trust_level && TRUST_STYLES[plugin.trust_level]) || {
    text: "text-gray-500",
    bg: "bg-gray-500/10",
  };
  const trustLabel =
    (plugin.trust_level && TRUST_LABELS[plugin.trust_level]) || null;
  const isPending = (key: string) => pendingAction === key;

  return (
    <div
      role="button"
      tabIndex={0}
      aria-expanded={expanded}
      className={`memory-item border-l-4 ${ts.borderL} cursor-pointer`}
      onClick={() => setExpanded(!expanded)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          setExpanded(!expanded);
        }
      }}
    >
      <div className="flex items-center gap-1.5 mb-1.5">
        <span
          className={`text-micro font-mono px-1.5 py-0.5 rounded ${ts.bg} ${ts.text} border ${ts.border} uppercase`}
        >
          {TYPE_LABELS[plugin.plugin_type] || plugin.plugin_type}
        </span>
        {trustLabel && (
          <span
            className={`text-micro font-mono px-1.5 py-0.5 rounded ${trust.bg} ${trust.text}`}
            title={plugin.trust_level}
          >
            {trustLabel.en} <span className="font-arabic">{trustLabel.ar}</span>
          </span>
        )}
        <span
          className={`ml-auto text-micro font-mono ${plugin.active ? "text-emerald-500" : "text-gray-400 dark:text-gray-500"}`}
        >
          {plugin.active ? "ACTIVE" : "INACTIVE"}
        </span>
      </div>

      <div className="text-sm text-gray-900 dark:text-gray-100 font-medium mt-1.5">
        {plugin.name}
        <span className="text-2xs text-gray-400 dark:text-gray-500 font-normal ml-2">
          v{plugin.version}
        </span>
      </div>

      {plugin.description && (
        <div className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
          {plugin.description}
        </div>
      )}

      {plugin.quranic_reference && (
        <div className="text-2xs text-mizan-gold italic mt-1">
          {plugin.quranic_reference}
        </div>
      )}

      {expanded && (
        <div className="detail-panel mt-2">
          {plugin.author && (
            <div className="text-2xs text-gray-500 dark:text-gray-400 mb-1">
              Author: {plugin.author}
            </div>
          )}
          {(plugin.permissions?.length ?? 0) > 0 && (
            <div className="text-2xs text-gray-500 dark:text-gray-400 mb-1">
              Permissions: {plugin.permissions!.join(", ")}
            </div>
          )}
          {plugin.checksum && (
            <div className="mb-2">
              <div className="text-micro font-mono text-gray-400 dark:text-gray-500">
                SHA-256: {plugin.checksum.slice(0, 16)}...
              </div>
              <div className="text-micro text-gray-400 dark:text-gray-500">
                Ye code ka fingerprint hai — Verify dabane se file badli to
                nahi, ye check hota hai
              </div>
            </div>
          )}
          <div className="flex gap-2 mt-2 flex-wrap">
            {plugin.active ? (
              <>
                <button
                  className="btn-secondary btn-sm min-h-[44px]"
                  disabled={isPending(`deactivate:${plugin.name}`)}
                  onClick={(e) => {
                    e.stopPropagation();
                    onDeactivate(plugin.name);
                  }}
                >
                  {isPending(`deactivate:${plugin.name}`) ? "Ruko…" : "Remove"}
                </button>
                <button
                  className="btn-secondary btn-sm min-h-[44px]"
                  disabled={isPending(`reload:${plugin.name}`)}
                  onClick={(e) => {
                    e.stopPropagation();
                    onReload(plugin.name);
                  }}
                >
                  {isPending(`reload:${plugin.name}`) ? "Ruko…" : "Reload"}
                </button>
              </>
            ) : (
              <button
                className="btn-gold btn-sm min-h-[44px]"
                disabled={isPending(`activate:${plugin.name}`)}
                onClick={(e) => {
                  e.stopPropagation();
                  onActivate(plugin.name);
                }}
              >
                {isPending(`activate:${plugin.name}`) ? "Ruko…" : "Add"}
              </button>
            )}
            <button
              className="btn-secondary btn-sm min-h-[44px]"
              disabled={isPending(`verify:${plugin.name}`)}
              onClick={(e) => {
                e.stopPropagation();
                onVerify(plugin.name);
              }}
            >
              {isPending(`verify:${plugin.name}`) ? "Ruko…" : "Verify"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

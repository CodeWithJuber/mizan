/**
 * Wahy Plugin System Page (وحي — Revelation/Inspiration)
 * "And We have revealed to you the Book as clarification for all things" — Quran 16:89
 */

import { useState, useEffect, useCallback } from "react";
import { PageProps, Plugin, PluginType, TrustLevel, PluginHook } from "../types";

const TYPE_STYLES: Record<string, { text: string; bg: string; border: string; borderL: string }> = {
  ayah: { text: "text-mizan-gold", bg: "bg-mizan-gold/10", border: "border-mizan-gold/30", borderL: "border-l-mizan-gold" },
  bab: { text: "text-blue-500", bg: "bg-blue-500/10", border: "border-blue-500/30", borderL: "border-l-blue-500" },
  hafiz: { text: "text-emerald-500", bg: "bg-emerald-500/10", border: "border-emerald-500/30", borderL: "border-l-emerald-500" },
  ruh: { text: "text-purple-500", bg: "bg-purple-500/10", border: "border-purple-500/30", borderL: "border-l-purple-500" },
  muaddib: { text: "text-amber-500", bg: "bg-amber-500/10", border: "border-amber-500/30", borderL: "border-l-amber-500" },
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
  mutmainna: { text: "text-emerald-500", bg: "bg-emerald-500/10" },
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
}

export default function PluginsPage({ api, addTerminalLine }: PageProps) {
  const [activeTab, setActiveTab] = useState<string>("installed");
  const [plugins, setPlugins] = useState<Plugin[]>([]);
  const [hooks, setHooks] = useState<PluginHook[]>([]);
  const [showCreate, setShowCreate] = useState<boolean>(false);
  const [createForm, setCreateForm] = useState<CreateForm>({
    name: "", description: "", plugin_type: "ayah", author: "",
  });

  const exec = useCallback(async (action: string, extra: Record<string, unknown> = {}) => {
    try {
      return await api.post("/skills/execute", {
        skill: "wahy_plugins", action, ...extra,
      });
    } catch { return null; }
  }, [api]);

  const loadPlugins = useCallback(async () => {
    const data = await exec("list");
    if (data?.plugins) setPlugins(data.plugins as Plugin[]);
  }, [exec]);

  const loadHooks = useCallback(async () => {
    const data = await exec("hooks");
    if (data?.hooks) setHooks(data.hooks as PluginHook[]);
  }, [exec]);

  useEffect(() => {
    loadPlugins();
    loadHooks();
  }, [loadPlugins, loadHooks]);

  const activatePlugin = async (name: string) => {
    const data = await exec("activate", { name });
    if (data?.status === "activated") {
      addTerminalLine?.(`Plugin activated: ${name}`, "gold");
      loadPlugins();
    }
  };

  const deactivatePlugin = async (name: string) => {
    const data = await exec("deactivate", { name });
    if (data?.status === "deactivated") {
      addTerminalLine?.(`Plugin deactivated: ${name}`, "warn");
      loadPlugins();
    }
  };

  const reloadPlugin = async (name: string) => {
    const data = await exec("reload", { name });
    if (data?.status === "reloaded") {
      addTerminalLine?.(`Plugin hot-reloaded: ${name}`, "gold");
      loadPlugins();
    }
  };

  const verifyPlugin = async (name: string) => {
    const data = await exec("verify", { name });
    addTerminalLine?.(
      data?.verified ? `Plugin verified: ${name} ✓` : `Plugin verification failed: ${name}`,
      data?.verified ? "gold" : "error"
    );
  };

  const createPlugin = async () => {
    const data = await exec("create", createForm as unknown as Record<string, unknown>);
    if (data?.created) {
      addTerminalLine?.(`Plugin scaffold created: ${createForm.name}`, "gold");
      setShowCreate(false);
      setCreateForm({ name: "", description: "", plugin_type: "ayah", author: "" });
      loadPlugins();
    }
  };

  const installed = plugins.filter(p => p.active);
  const available = plugins.filter(p => !p.active);

  return (
    <div className="page-wrapper">
      <div className="page-header">
        <div>
          <h2 className="page-title">Plugin System</h2>
          <p className="page-description">وَحْي (Wahy) — Extensibility</p>
        </div>
      </div>

      <div className="quran-quote">
        "And We have revealed to you the Book as clarification for all things" — Quran 16:89
      </div>

      <div className="tab-bar">
        {[
          { id: "installed", label: `Active (${installed.length})` },
          { id: "available", label: `Available (${available.length})` },
          { id: "hooks", label: "Hooks" },
          { id: "create", label: "Create" },
        ].map(tab => (
          <div key={tab.id} className={`tab ${activeTab === tab.id ? "active" : ""}`}
            onClick={() => setActiveTab(tab.id)}>
            {tab.label}
          </div>
        ))}
      </div>

      <div className="page-body">
        {activeTab === "installed" && (
          <>
            {installed.length === 0 && (
              <div className="empty-state">
                <div className="empty-arabic">وحي</div>
                <div className="empty-text">No active plugins</div>
                <div className="empty-sub">Activate plugins from the Available tab</div>
              </div>
            )}
            {installed.map(plugin => (
              <PluginCard key={plugin.name} plugin={plugin}
                onActivate={activatePlugin} onDeactivate={deactivatePlugin}
                onReload={reloadPlugin} onVerify={verifyPlugin} />
            ))}
          </>
        )}

        {activeTab === "available" && (
          <>
            {available.length === 0 && (
              <div className="empty-state">
                <div className="empty-arabic">وحي</div>
                <div className="empty-text">All plugins are active</div>
              </div>
            )}
            {available.map(plugin => (
              <PluginCard key={plugin.name} plugin={plugin}
                onActivate={activatePlugin} onDeactivate={deactivatePlugin}
                onReload={reloadPlugin} onVerify={verifyPlugin} />
            ))}
          </>
        )}

        {activeTab === "hooks" && (
          <>
            <div className="mb-3">
              <button className="btn-secondary btn-sm" onClick={loadHooks}>Refresh</button>
            </div>
            {hooks.length === 0 && (
              <div className="empty-state">
                <div className="empty-arabic">ربط</div>
                <div className="empty-text">No hooks registered</div>
                <div className="empty-sub">Plugins register hooks when activated</div>
              </div>
            )}
            <div className="card">
              <div className="text-2xs font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-widest mb-3">
                Event Hooks · خطافات
              </div>
              {hooks.map((hook, i) => (
                <div key={i} className="flex items-center gap-2 px-2 py-1.5 rounded mb-1 bg-gray-50 dark:bg-zinc-800/50 border border-gray-100 dark:border-zinc-700/50">
                  <span className="text-2xs font-mono text-blue-500 dark:text-blue-400 w-40 shrink-0">{hook.event}</span>
                  <span className="text-2xs text-gray-900 dark:text-gray-100">{hook.plugin}</span>
                  <span className="ml-auto text-micro font-mono text-gray-400 dark:text-gray-500">
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
              <div className="form-panel-title">Create Plugin Scaffold · إنشاء</div>
              <div className="form-group">
                <label className="form-label">Plugin Name</label>
                <input className="form-input" value={createForm.name}
                  onChange={e => setCreateForm({ ...createForm, name: e.target.value })}
                  placeholder="my_custom_plugin" />
              </div>
              <div className="form-group">
                <label className="form-label">Description</label>
                <input className="form-input" value={createForm.description}
                  onChange={e => setCreateForm({ ...createForm, description: e.target.value })}
                  placeholder="What does this plugin do?" />
              </div>
              <div className="form-group">
                <label className="form-label">Plugin Type</label>
                <div className="grid grid-cols-2 gap-2">
                  {Object.entries(TYPE_LABELS).map(([type, label]) => {
                    const ts = TYPE_STYLES[type] || TYPE_STYLES.ayah;
                    return (
                      <button key={type}
                        className={`p-2 rounded-lg border text-center text-xs font-medium transition-colors cursor-pointer
                          ${createForm.plugin_type === type
                            ? `${ts.bg} ${ts.border} ${ts.text}`
                            : "bg-gray-50 dark:bg-zinc-800 border-gray-200 dark:border-zinc-700 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-zinc-700"
                          }`}
                        onClick={() => setCreateForm({ ...createForm, plugin_type: type })}>
                        {label}
                      </button>
                    );
                  })}
                </div>
              </div>
              <div className="form-group">
                <label className="form-label">Author</label>
                <input className="form-input" value={createForm.author}
                  onChange={e => setCreateForm({ ...createForm, author: e.target.value })}
                  placeholder="Your name" />
              </div>
              <button className="btn-gold w-full py-2.5"
                onClick={createPlugin}
                disabled={!createForm.name || !createForm.description}>
                Create Plugin Scaffold
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
                    <span className={`w-2 h-2 rounded-full ${ts.bg} border ${ts.border}`} />
                    <span className={`text-xs ${ts.text}`}>{label}</span>
                    <span className="text-2xs text-gray-400 dark:text-gray-500">
                      {type === "ayah" ? "— Add new tool capabilities" :
                       type === "bab" ? "— New communication channels" :
                       type === "hafiz" ? "— Custom memory backends" :
                       type === "ruh" ? "— AI model providers" :
                       "— Request/response transforms"}
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

function PluginCard({ plugin, onActivate, onDeactivate, onReload, onVerify }: PluginCardProps) {
  const [expanded, setExpanded] = useState<boolean>(false);
  const ts = TYPE_STYLES[plugin.plugin_type] || { text: "text-gray-500", bg: "bg-gray-500/10", border: "border-gray-500/30", borderL: "border-l-gray-400" };
  const trust = (plugin.trust_level && TRUST_STYLES[plugin.trust_level]) || { text: "text-gray-500", bg: "bg-gray-500/10" };

  return (
    <div className={`memory-item border-l-4 ${ts.borderL} cursor-pointer`}
      onClick={() => setExpanded(!expanded)}>
      <div className="flex items-center gap-1.5 mb-1.5">
        <span className={`text-micro font-mono px-1.5 py-0.5 rounded ${ts.bg} ${ts.text} border ${ts.border} uppercase`}>
          {TYPE_LABELS[plugin.plugin_type] || plugin.plugin_type}
        </span>
        {plugin.trust_level && (
          <span className={`text-micro font-mono px-1.5 py-0.5 rounded ${trust.bg} ${trust.text}`}>
            {plugin.trust_level}
          </span>
        )}
        <span className={`ml-auto text-micro font-mono ${plugin.active ? "text-emerald-500" : "text-gray-400 dark:text-gray-500"}`}>
          {plugin.active ? "ACTIVE" : "INACTIVE"}
        </span>
      </div>

      <div className="text-sm text-gray-900 dark:text-gray-100 font-medium mt-1.5">
        {plugin.name}
        <span className="text-2xs text-gray-400 dark:text-gray-500 font-normal ml-2">v{plugin.version}</span>
      </div>

      {plugin.description && (
        <div className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{plugin.description}</div>
      )}

      {plugin.quranic_reference && (
        <div className="text-2xs text-mizan-gold italic mt-1">{plugin.quranic_reference}</div>
      )}

      {expanded && (
        <div className="detail-panel mt-2">
          {plugin.author && (
            <div className="text-2xs text-gray-500 dark:text-gray-400 mb-1">Author: {plugin.author}</div>
          )}
          {(plugin.permissions?.length ?? 0) > 0 && (
            <div className="text-2xs text-gray-500 dark:text-gray-400 mb-1">Permissions: {plugin.permissions!.join(", ")}</div>
          )}
          {plugin.checksum && (
            <div className="text-micro font-mono text-gray-400 dark:text-gray-500 mb-2">SHA-256: {plugin.checksum.slice(0, 16)}...</div>
          )}
          <div className="flex gap-2 mt-2">
            {plugin.active ? (
              <>
                <button className="btn-secondary btn-sm" onClick={e => { e.stopPropagation(); onDeactivate(plugin.name); }}>Deactivate</button>
                <button className="btn-secondary btn-sm" onClick={e => { e.stopPropagation(); onReload(plugin.name); }}>Reload</button>
              </>
            ) : (
              <button className="btn-gold btn-sm" onClick={e => { e.stopPropagation(); onActivate(plugin.name); }}>Activate</button>
            )}
            <button className="btn-secondary btn-sm" onClick={e => { e.stopPropagation(); onVerify(plugin.name); }}>Verify</button>
          </div>
        </div>
      )}
    </div>
  );
}

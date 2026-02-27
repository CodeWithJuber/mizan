/**
 * Wahy Plugin System Page (وحي — Revelation/Inspiration)
 * "And We have revealed to you the Book as clarification for all things" — Quran 16:89
 */

import { useState, useEffect, useCallback } from "react";
import { PageProps, Plugin, PluginType, TrustLevel, PluginHook } from "../types";

const TYPE_COLORS: Record<string, string> = {
  ayah: "#c9a227",
  bab: "#3b82f6",
  hafiz: "#10b981",
  ruh: "#a855f7",
  muaddib: "#f59e0b",
};

const TYPE_LABELS: Record<string, string> = {
  ayah: "آية · Tool",
  bab: "باب · Channel",
  hafiz: "حافظ · Memory",
  ruh: "روح · Provider",
  muaddib: "مؤدب · Middleware",
};

const TRUST_COLORS: Record<string, string> = {
  ammara: "#ef4444",
  lawwama: "#f59e0b",
  mutmainna: "#10b981",
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
    <>
      <div className="flex items-center justify-between px-5 py-3 border-b border-gray-200 dark:border-zinc-800">
        <h2 className="page-title">Plugin System · وَحْي (Wahy)</h2>
      </div>
      <div className="px-4 pb-2 pt-1 text-xs text-gray-500 dark:text-gray-400 italic">
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

      <div className="flex-1 overflow-auto p-4">

        {/* ===== INSTALLED PLUGINS ===== */}
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

        {/* ===== AVAILABLE PLUGINS ===== */}
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

        {/* ===== HOOKS ===== */}
        {activeTab === "hooks" && (
          <>
            <div className="mb-3">
              <button className="btn-secondary" onClick={loadHooks}>Refresh</button>
            </div>
            {hooks.length === 0 && (
              <div className="empty-state">
                <div className="empty-arabic">ربط</div>
                <div className="empty-text">No hooks registered</div>
                <div className="empty-sub">Plugins register hooks when activated</div>
              </div>
            )}
            <div className="card">
              <div className="text-[10px] tracking-widest text-gray-500 dark:text-gray-400 uppercase mb-3">
                Event Hooks · خطافات
              </div>
              {hooks.map((hook, i) => (
                <div key={i} className="flex items-center gap-2 px-2 py-1.5 rounded mb-1 bg-gray-50 dark:bg-zinc-800/50 border border-gray-200 dark:border-zinc-800">
                  <span className="text-[10px] font-mono text-blue-500 w-40">{hook.event}</span>
                  <span className="text-[10px] text-gray-900 dark:text-gray-100">{hook.plugin}</span>
                  <span className="ml-auto text-[9px] font-mono text-gray-500 dark:text-gray-400">
                    priority: {hook.priority}
                  </span>
                </div>
              ))}
            </div>
          </>
        )}

        {/* ===== CREATE PLUGIN ===== */}
        {activeTab === "create" && (
          <div className="max-w-[600px]">
            <div className="card border-mizan-gold">
              <div className="text-sm text-mizan-gold mb-3 font-semibold">
                Create Plugin Scaffold · إنشاء
              </div>
              <div className="space-y-1.5 mb-4">
                <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Plugin Name</label>
                <input className="input w-full text-sm" value={createForm.name}
                  onChange={e => setCreateForm({ ...createForm, name: e.target.value })}
                  placeholder="my_custom_plugin" />
              </div>
              <div className="space-y-1.5 mb-4">
                <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Description</label>
                <input className="input w-full text-sm" value={createForm.description}
                  onChange={e => setCreateForm({ ...createForm, description: e.target.value })}
                  placeholder="What does this plugin do?" />
              </div>
              <div className="space-y-1.5 mb-4">
                <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Plugin Type</label>
                <div className="flex gap-1.5 flex-wrap">
                  {Object.entries(TYPE_LABELS).map(([type, label]) => (
                    <button key={type}
                      className={`${createForm.plugin_type === type ? "btn-primary" : "btn-secondary"} flex-[1_0_30%] justify-center py-2`}
                      onClick={() => setCreateForm({ ...createForm, plugin_type: type })}>
                      <span className="text-[10px]">{label}</span>
                    </button>
                  ))}
                </div>
              </div>
              <div className="space-y-1.5 mb-4">
                <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Author</label>
                <input className="input w-full text-sm" value={createForm.author}
                  onChange={e => setCreateForm({ ...createForm, author: e.target.value })}
                  placeholder="Your name" />
              </div>
              <button className="btn-primary w-full justify-center py-3"
                onClick={createPlugin}
                disabled={!createForm.name || !createForm.description}>
                Create Plugin Scaffold
              </button>
            </div>

            <div className="card mt-4">
              <div className="text-xs text-gray-500 dark:text-gray-400 tracking-wide uppercase mb-2">
                Plugin Types
              </div>
              {Object.entries(TYPE_LABELS).map(([type, label]) => (
                <div key={type} className="flex items-center gap-2 py-1">
                  <span className="w-2 h-2 rounded-full"
                    style={{ background: TYPE_COLORS[type] }} />
                  <span className="text-xs text-gray-900 dark:text-gray-100">{label}</span>
                  <span className="text-[10px] text-gray-500 dark:text-gray-400">
                    {type === "ayah" ? "— Add new tool capabilities" :
                     type === "bab" ? "— New communication channels" :
                     type === "hafiz" ? "— Custom memory backends" :
                     type === "ruh" ? "— AI model providers" :
                     "— Request/response transforms"}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </>
  );
}

function PluginCard({ plugin, onActivate, onDeactivate, onReload, onVerify }: PluginCardProps) {
  const [expanded, setExpanded] = useState<boolean>(false);

  return (
    <div className="card mb-3 cursor-pointer"
      style={{ borderLeft: `3px solid ${TYPE_COLORS[plugin.plugin_type] || "#6b7280"}` }}
      onClick={() => setExpanded(!expanded)}>
      <div className="flex items-center gap-2">
        <span className="text-[9px] font-mono px-1.5 rounded uppercase"
          style={{
            background: `${TYPE_COLORS[plugin.plugin_type]}20`,
            color: TYPE_COLORS[plugin.plugin_type],
            border: `1px solid ${TYPE_COLORS[plugin.plugin_type]}30`,
          }}>
          {TYPE_LABELS[plugin.plugin_type] || plugin.plugin_type}
        </span>
        {plugin.trust_level && (
          <span className="text-[9px] font-mono px-1.5 rounded"
            style={{
              background: `${TRUST_COLORS[plugin.trust_level]}20`,
              color: TRUST_COLORS[plugin.trust_level],
            }}>
            {plugin.trust_level}
          </span>
        )}
        <span className={`ml-auto text-[9px] font-mono ${plugin.active ? "text-emerald-500" : "text-gray-500 dark:text-gray-400"}`}>
          {plugin.active ? "ACTIVE" : "INACTIVE"}
        </span>
      </div>

      <div className="text-xs text-gray-900 dark:text-gray-100 font-medium mt-1.5">
        {plugin.name}
        <span className="text-[10px] text-gray-500 dark:text-gray-400 font-normal ml-2">
          v{plugin.version}
        </span>
      </div>

      {plugin.description && (
        <div className="text-xs text-gray-600 dark:text-gray-300 mt-0.5">
          {plugin.description}
        </div>
      )}

      {plugin.quranic_reference && (
        <div className="text-[10px] text-mizan-gold italic mt-1">
          {plugin.quranic_reference}
        </div>
      )}

      {expanded && (
        <div className="mt-2 p-2 bg-gray-50 dark:bg-zinc-800/50 rounded border border-gray-200 dark:border-zinc-800">
          {plugin.author && (
            <div className="text-[10px] text-gray-500 dark:text-gray-400 mb-1">
              Author: {plugin.author}
            </div>
          )}
          {(plugin.permissions?.length ?? 0) > 0 && (
            <div className="text-[10px] text-gray-500 dark:text-gray-400 mb-1">
              Permissions: {plugin.permissions!.join(", ")}
            </div>
          )}
          {plugin.checksum && (
            <div className="text-[9px] font-mono text-gray-500 dark:text-gray-400 mb-1.5">
              SHA-256: {plugin.checksum.slice(0, 16)}...
            </div>
          )}
          <div className="flex gap-1.5 mt-1.5">
            {plugin.active ? (
              <>
                <button className="btn-secondary text-[10px] px-2 py-0.5"
                  onClick={e => { e.stopPropagation(); onDeactivate(plugin.name); }}>
                  Deactivate
                </button>
                <button className="btn-secondary text-[10px] px-2 py-0.5"
                  onClick={e => { e.stopPropagation(); onReload(plugin.name); }}>
                  Reload
                </button>
              </>
            ) : (
              <button className="btn-primary text-[10px] px-2 py-0.5"
                onClick={e => { e.stopPropagation(); onActivate(plugin.name); }}>
                Activate
              </button>
            )}
            <button className="btn-secondary text-[10px] px-2 py-0.5"
              onClick={e => { e.stopPropagation(); onVerify(plugin.name); }}>
              Verify
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

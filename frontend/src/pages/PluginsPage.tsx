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
      <div className="panel-header">
        <div className="panel-title">Plugin System · وَحْي (Wahy)</div>
      </div>
      <div style={{ padding: "4px 16px 8px", fontSize: 11, color: "var(--text-muted)", fontStyle: "italic" }}>
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

      <div style={{ flex: 1, overflow: "auto", padding: 16 }}>

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
            <div style={{ marginBottom: 12 }}>
              <button className="btn" onClick={loadHooks}>Refresh</button>
            </div>
            {hooks.length === 0 && (
              <div className="empty-state">
                <div className="empty-arabic">ربط</div>
                <div className="empty-text">No hooks registered</div>
                <div className="empty-sub">Plugins register hooks when activated</div>
              </div>
            )}
            <div style={{ padding: 16, background: "linear-gradient(135deg, rgba(15,32,48,0.9) 0%, rgba(10,21,32,0.9) 100%)",
              border: "1px solid var(--border)", borderRadius: 10 }}>
              <div style={{ fontFamily: "var(--font-display)", fontSize: 10, letterSpacing: "0.2em",
                color: "var(--text-muted)", textTransform: "uppercase", marginBottom: 12 }}>
                Event Hooks · خطافات
              </div>
              {hooks.map((hook, i) => (
                <div key={i} style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 8px",
                  borderRadius: 4, marginBottom: 4,
                  background: "rgba(3,6,8,0.4)", border: "1px solid var(--border)" }}>
                  <span style={{ fontSize: 10, fontFamily: "var(--font-mono)", color: "var(--sapphire)",
                    width: 160 }}>{hook.event}</span>
                  <span style={{ fontSize: 10, color: "var(--text-primary)" }}>{hook.plugin}</span>
                  <span style={{ marginLeft: "auto", fontSize: 9, fontFamily: "var(--font-mono)",
                    color: "var(--text-muted)" }}>
                    priority: {hook.priority}
                  </span>
                </div>
              ))}
            </div>
          </>
        )}

        {/* ===== CREATE PLUGIN ===== */}
        {activeTab === "create" && (
          <div style={{ maxWidth: 600 }}>
            <div style={{ padding: 16, background: "rgba(15,32,48,0.9)",
              border: "1px solid var(--gold)", borderRadius: 10 }}>
              <div style={{ fontFamily: "var(--font-display)", fontSize: 13, color: "var(--gold)", marginBottom: 12 }}>
                Create Plugin Scaffold · إنشاء
              </div>
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
                <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                  {Object.entries(TYPE_LABELS).map(([type, label]) => (
                    <button key={type}
                      className={`btn ${createForm.plugin_type === type ? "primary" : ""}`}
                      style={{ flex: "1 0 30%", justifyContent: "center", padding: "8px" }}
                      onClick={() => setCreateForm({ ...createForm, plugin_type: type })}>
                      <span style={{ fontSize: 10 }}>{label}</span>
                    </button>
                  ))}
                </div>
              </div>
              <div className="form-group">
                <label className="form-label">Author</label>
                <input className="form-input" value={createForm.author}
                  onChange={e => setCreateForm({ ...createForm, author: e.target.value })}
                  placeholder="Your name" />
              </div>
              <button className="btn primary" style={{ width: "100%", justifyContent: "center", padding: 12 }}
                onClick={createPlugin}
                disabled={!createForm.name || !createForm.description}>
                Create Plugin Scaffold
              </button>
            </div>

            <div style={{ marginTop: 16, padding: 16, background: "rgba(3,6,8,0.5)",
              border: "1px solid var(--border)", borderRadius: 8 }}>
              <div style={{ fontFamily: "var(--font-display)", fontSize: 11, color: "var(--text-muted)",
                letterSpacing: "0.1em", marginBottom: 8, textTransform: "uppercase" }}>
                Plugin Types
              </div>
              {Object.entries(TYPE_LABELS).map(([type, label]) => (
                <div key={type} style={{ display: "flex", alignItems: "center", gap: 8, padding: "4px 0" }}>
                  <span style={{ width: 8, height: 8, borderRadius: "50%",
                    background: TYPE_COLORS[type] }} />
                  <span style={{ fontSize: 11, color: "var(--text-primary)" }}>{label}</span>
                  <span style={{ fontSize: 10, color: "var(--text-muted)" }}>
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
    <div className="memory-item" style={{
      borderLeft: `3px solid ${TYPE_COLORS[plugin.plugin_type] || "var(--text-muted)"}`,
      cursor: "pointer" }}
      onClick={() => setExpanded(!expanded)}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span style={{ fontSize: 9, fontFamily: "var(--font-mono)", padding: "1px 6px",
          borderRadius: 3, background: `${TYPE_COLORS[plugin.plugin_type]}20`,
          color: TYPE_COLORS[plugin.plugin_type],
          border: `1px solid ${TYPE_COLORS[plugin.plugin_type]}30`,
          textTransform: "uppercase" }}>
          {TYPE_LABELS[plugin.plugin_type] || plugin.plugin_type}
        </span>
        {plugin.trust_level && (
          <span style={{ fontSize: 9, fontFamily: "var(--font-mono)", padding: "1px 6px",
            borderRadius: 3, background: `${TRUST_COLORS[plugin.trust_level]}20`,
            color: TRUST_COLORS[plugin.trust_level] }}>
            {plugin.trust_level}
          </span>
        )}
        <span style={{ marginLeft: "auto", fontSize: 9, fontFamily: "var(--font-mono)",
          color: plugin.active ? "var(--emerald)" : "var(--text-muted)" }}>
          {plugin.active ? "ACTIVE" : "INACTIVE"}
        </span>
      </div>

      <div style={{ fontSize: 12, color: "var(--text-primary)", fontWeight: 500, marginTop: 6 }}>
        {plugin.name}
        <span style={{ fontSize: 10, color: "var(--text-muted)", fontWeight: 400, marginLeft: 8 }}>
          v{plugin.version}
        </span>
      </div>

      {plugin.description && (
        <div style={{ fontSize: 11, color: "var(--text-secondary)", marginTop: 2 }}>
          {plugin.description}
        </div>
      )}

      {plugin.quranic_reference && (
        <div style={{ fontSize: 10, color: "var(--gold)", fontStyle: "italic", marginTop: 4 }}>
          {plugin.quranic_reference}
        </div>
      )}

      {expanded && (
        <div style={{ marginTop: 8, padding: 8, background: "rgba(3,6,8,0.5)",
          borderRadius: 4, border: "1px solid var(--border)" }}>
          {plugin.author && (
            <div style={{ fontSize: 10, color: "var(--text-muted)", marginBottom: 4 }}>
              Author: {plugin.author}
            </div>
          )}
          {(plugin.permissions?.length ?? 0) > 0 && (
            <div style={{ fontSize: 10, color: "var(--text-muted)", marginBottom: 4 }}>
              Permissions: {plugin.permissions!.join(", ")}
            </div>
          )}
          {plugin.checksum && (
            <div style={{ fontSize: 9, fontFamily: "var(--font-mono)", color: "var(--text-muted)", marginBottom: 6 }}>
              SHA-256: {plugin.checksum.slice(0, 16)}...
            </div>
          )}
          <div style={{ display: "flex", gap: 6, marginTop: 6 }}>
            {plugin.active ? (
              <>
                <button className="btn" style={{ fontSize: 10, padding: "3px 8px" }}
                  onClick={e => { e.stopPropagation(); onDeactivate(plugin.name); }}>
                  Deactivate
                </button>
                <button className="btn" style={{ fontSize: 10, padding: "3px 8px" }}
                  onClick={e => { e.stopPropagation(); onReload(plugin.name); }}>
                  Reload
                </button>
              </>
            ) : (
              <button className="btn primary" style={{ fontSize: 10, padding: "3px 8px" }}
                onClick={e => { e.stopPropagation(); onActivate(plugin.name); }}>
                Activate
              </button>
            )}
            <button className="btn" style={{ fontSize: 10, padding: "3px 8px" }}
              onClick={e => { e.stopPropagation(); onVerify(plugin.name); }}>
              Verify
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

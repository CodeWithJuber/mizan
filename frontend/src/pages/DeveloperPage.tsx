/**
 * Developer & Extensibility Page
 * Shows all extensibility points: plugins, events, hooks, middleware.
 * Designed for both technical and non-technical users.
 */

import { useState, useEffect } from "react";
import type { ApiClient } from "../types";

interface PluginInfo {
  name: string;
  version: string;
  description: string;
  author: string;
  enabled: boolean;
  loaded: boolean;
  permissions: string[];
  tags: string[];
}

interface EventHandler {
  pattern: string;
  source: string;
  priority: number;
  once: boolean;
}

interface HookEntry {
  hook: string;
  source: string;
  priority: number;
}

interface EventHistoryItem {
  name: string;
  data: Record<string, unknown>;
  source: string;
  timestamp: string;
}

interface PluginTool {
  name: string;
  plugin: string;
  schema: Record<string, unknown>;
}

interface VersionInfo {
  version: string;
  updates_available: number;
  latest_commit: string | null;
  can_check: boolean;
}

export default function DeveloperPage({ api }: { api: ApiClient }) {
  const [activeTab, setActiveTab] = useState<"system" | "plugins" | "events" | "hooks" | "guide">("system");
  const [plugins, setPlugins] = useState<PluginInfo[]>([]);
  const [events, setEvents] = useState<Record<string, string>>({});
  const [eventHandlers, setEventHandlers] = useState<EventHandler[]>([]);
  const [eventHistory, setEventHistory] = useState<EventHistoryItem[]>([]);
  const [hooks, setHooks] = useState<Record<string, string>>({});
  const [registeredHooks, setRegisteredHooks] = useState<HookEntry[]>([]);
  const [pluginTools, setPluginTools] = useState<PluginTool[]>([]);
  const [loading, setLoading] = useState(false);
  const [versionInfo, setVersionInfo] = useState<VersionInfo | null>(null);
  const [checkingUpdate, setCheckingUpdate] = useState(false);

  const fetchAll = async () => {
    setLoading(true);
    try {
      const [pluginsRes, eventsRes, hooksRes, toolsRes] = await Promise.all([
        api.get("/plugins"),
        api.get("/events"),
        api.get("/hooks"),
        api.get("/plugins/tools"),
      ]);
      setPlugins((pluginsRes as { plugins: PluginInfo[] }).plugins || []);
      const evData = eventsRes as { standard_events: Record<string, string>; handlers: EventHandler[]; history: EventHistoryItem[] };
      setEvents(evData.standard_events || {});
      setEventHandlers(evData.handlers || []);
      setEventHistory(evData.history || []);
      const hkData = hooksRes as { standard_hooks: Record<string, string>; registered: HookEntry[] };
      setHooks(hkData.standard_hooks || {});
      setRegisteredHooks(hkData.registered || []);
      setPluginTools((toolsRes as { tools: PluginTool[] }).tools || []);
    } catch { /* ignore */ }
    setLoading(false);
  };

  const fetchVersion = async () => {
    try {
      const data = await api.get("/version") as VersionInfo;
      setVersionInfo(data);
    } catch { /* ignore */ }
  };

  const checkForUpdates = async () => {
    setCheckingUpdate(true);
    try {
      const data = await api.get("/version") as VersionInfo;
      setVersionInfo(data);
    } catch { /* ignore */ }
    setCheckingUpdate(false);
  };

  useEffect(() => { fetchAll(); fetchVersion(); }, []);

  const handlePluginAction = async (name: string, action: "load" | "unload" | "reload") => {
    try {
      await api.post(`/plugins/${name}/${action}`);
      await fetchAll();
    } catch { /* ignore */ }
  };

  const tabs = [
    { id: "system" as const, label: "System" },
    { id: "plugins" as const, label: "Plugins" },
    { id: "events" as const, label: "Events" },
    { id: "hooks" as const, label: "Hooks" },
    { id: "guide" as const, label: "Developer Guide" },
  ];

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* Header */}
      <div className="px-5 py-3 border-b border-gray-200 dark:border-zinc-800">
        <h2 className="page-title">Developer</h2>
        <p className="page-description">Extend MIZAN with plugins, events, and hooks — no core code changes needed</p>
      </div>

      {/* Tabs */}
      <div className="tab-bar">
        {tabs.map((tab) => (
          <div
            key={tab.id}
            className={`tab ${activeTab === tab.id ? "active" : ""}`}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
          </div>
        ))}
      </div>

      <div className="flex-1 overflow-y-auto p-5 space-y-5">
        {/* System Tab */}
        {activeTab === "system" && (
          <div className="space-y-5">
            {/* Version Card */}
            <div className="card">
              <div className="flex items-start justify-between">
                <div>
                  <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-1">MIZAN</h3>
                  <div className="flex items-center gap-3">
                    <span className="text-3xl font-bold text-mizan-gold">
                      v{versionInfo?.version || "..."}
                    </span>
                    {versionInfo?.updates_available ? (
                      <span className="badge badge-warning">
                        {versionInfo.updates_available} update{versionInfo.updates_available !== 1 ? "s" : ""} available
                      </span>
                    ) : versionInfo ? (
                      <span className="badge badge-success">Up to date</span>
                    ) : null}
                  </div>
                </div>
                <button
                  onClick={checkForUpdates}
                  disabled={checkingUpdate}
                  className="btn-secondary text-sm flex items-center gap-2"
                >
                  {checkingUpdate ? (
                    <>
                      <svg className="animate-spin w-4 h-4" viewBox="0 0 24 24" fill="none">
                        <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" className="opacity-25"/>
                        <path d="M4 12a8 8 0 018-8" stroke="currentColor" strokeWidth="3" strokeLinecap="round" className="opacity-75"/>
                      </svg>
                      Checking...
                    </>
                  ) : "Check for Updates"}
                </button>
              </div>

              {versionInfo?.updates_available ? (
                <div className="mt-4 p-3 bg-amber-50 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/20 rounded-lg">
                  <p className="text-sm font-medium text-amber-800 dark:text-amber-300 mb-1">
                    New updates are available!
                  </p>
                  {versionInfo.latest_commit && (
                    <p className="text-xs text-amber-700 dark:text-amber-400 mb-2">
                      Latest: {versionInfo.latest_commit}
                    </p>
                  )}
                  <p className="text-xs text-amber-600 dark:text-amber-400">
                    Run <code className="code">./update.sh</code> or <code className="code">make update</code> to update
                  </p>
                </div>
              ) : null}
            </div>

            {/* Quick Info Cards */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div className="card text-center py-4">
                <div className="text-2xl font-bold text-gray-900 dark:text-gray-100">{versionInfo?.version?.split(".")[0] || "3"}</div>
                <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">Major Version</div>
              </div>
              <div className="card text-center py-4">
                <div className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                  {versionInfo?.can_check ? (
                    <span className="text-emerald-500">Git</span>
                  ) : (
                    <span className="text-gray-400">-</span>
                  )}
                </div>
                <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">Install Method</div>
              </div>
              <div className="card text-center py-4">
                <div className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                  {versionInfo?.updates_available || 0}
                </div>
                <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">Pending Updates</div>
              </div>
            </div>

            {/* How to Update */}
            <div className="card">
              <h3 className="text-base font-semibold text-gray-900 dark:text-gray-100 mb-3">How to Update</h3>
              <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
                MIZAN has a built-in one-command updater. Choose any of these:
              </p>
              <div className="space-y-2">
                <div className="flex items-center gap-3 p-2.5 bg-gray-50 dark:bg-zinc-800 rounded-lg border border-gray-200 dark:border-zinc-700">
                  <code className="text-sm font-mono text-mizan-gold flex-1">./update.sh</code>
                  <span className="text-xs text-gray-500 dark:text-gray-400">Direct command</span>
                </div>
                <div className="flex items-center gap-3 p-2.5 bg-gray-50 dark:bg-zinc-800 rounded-lg border border-gray-200 dark:border-zinc-700">
                  <code className="text-sm font-mono text-mizan-gold flex-1">make update</code>
                  <span className="text-xs text-gray-500 dark:text-gray-400">Via Makefile</span>
                </div>
                <div className="flex items-center gap-3 p-2.5 bg-gray-50 dark:bg-zinc-800 rounded-lg border border-gray-200 dark:border-zinc-700">
                  <code className="text-sm font-mono text-mizan-gold flex-1">./start.sh update</code>
                  <span className="text-xs text-gray-500 dark:text-gray-400">Via start script</span>
                </div>
              </div>
              <p className="text-xs text-gray-400 dark:text-gray-500 mt-3">
                The updater automatically stops services, pulls code, rebuilds everything, and restarts.
              </p>
            </div>

            {/* Check Only */}
            <div className="card">
              <h3 className="text-base font-semibold text-gray-900 dark:text-gray-100 mb-2">Check Without Installing</h3>
              <div className="flex items-center gap-3 p-2.5 bg-gray-50 dark:bg-zinc-800 rounded-lg border border-gray-200 dark:border-zinc-700">
                <code className="text-sm font-mono text-mizan-gold flex-1">./update.sh --check</code>
                <span className="text-xs text-gray-500 dark:text-gray-400">See if updates exist</span>
              </div>
            </div>
          </div>
        )}

        {/* Plugins Tab */}
        {activeTab === "plugins" && (
          <div className="space-y-4">
            <div className="flex justify-between items-center">
              <h2 className="text-base font-semibold text-gray-900 dark:text-gray-100">Installed Plugins</h2>
              <button onClick={fetchAll} className="text-sm text-mizan-gold hover:text-mizan-gold-light transition-colors">
                {loading ? "Refreshing..." : "Refresh"}
              </button>
            </div>

            {plugins.length === 0 ? (
              <div className="card text-center py-10">
                <h3 className="text-base font-semibold text-gray-900 dark:text-gray-100 mb-2">No Plugins Yet</h3>
                <p className="text-sm text-gray-500 dark:text-gray-400 max-w-md mx-auto">
                  Create a folder in <code className="code">plugins/</code> with
                  a <code className="code">plugin.json</code> and
                  <code className="code">main.py</code> to get started.
                </p>
              </div>
            ) : (
              <div className="grid gap-3">
                {plugins.map((p) => (
                  <div key={p.name} className={`card ${
                    p.loaded ? "border-emerald-200 dark:border-emerald-500/20" : ""
                  }`}>
                    <div className="flex items-start justify-between">
                      <div>
                        <div className="flex items-center gap-2">
                          <h3 className="font-semibold text-gray-900 dark:text-gray-100">{p.name}</h3>
                          <span className="text-xs text-gray-500 dark:text-gray-400">v{p.version}</span>
                          {p.loaded && (
                            <span className="badge badge-success">Active</span>
                          )}
                        </div>
                        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">{p.description}</p>
                        {p.author && <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">by {p.author}</p>}
                        {p.tags.length > 0 && (
                          <div className="flex gap-1 mt-2">
                            {p.tags.map((t) => (
                              <span key={t} className="tool-tag">{t}</span>
                            ))}
                          </div>
                        )}
                      </div>
                      <div className="flex gap-2">
                        {p.loaded ? (
                          <>
                            <button onClick={() => handlePluginAction(p.name, "reload")}
                              className="btn text-xs">
                              Reload
                            </button>
                            <button onClick={() => handlePluginAction(p.name, "unload")}
                              className="btn danger text-xs">
                              Unload
                            </button>
                          </>
                        ) : (
                          <button onClick={() => handlePluginAction(p.name, "load")}
                            className="btn primary text-xs">
                            Load
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Plugin Tools */}
            {pluginTools.length > 0 && (
              <div className="mt-6">
                <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3">Tools from Plugins</h3>
                <div className="grid gap-2">
                  {pluginTools.map((t) => (
                    <div key={t.name} className="card">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-mizan-gold text-sm">{t.name}</span>
                        <span className="text-xs text-gray-500 dark:text-gray-400">from {t.plugin}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Events Tab */}
        {activeTab === "events" && (
          <div className="space-y-5">
            <div>
              <h2 className="text-base font-semibold text-gray-900 dark:text-gray-100 mb-2">Event Bus</h2>
              <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
                Events let different parts of MIZAN communicate without knowing about each other.
                Plugins can listen to any event and react to it.
              </p>
            </div>

            <div>
              <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-2">Active Listeners ({eventHandlers.length})</h3>
              {eventHandlers.length > 0 ? (
                <div className="grid gap-2">
                  {eventHandlers.map((h, i) => (
                    <div key={i} className="card flex items-center justify-between py-3">
                      <div className="flex items-center gap-3">
                        <span className="font-mono text-cyan-600 dark:text-cyan-400 text-sm">{h.pattern}</span>
                        {h.source && <span className="text-xs text-gray-500 dark:text-gray-400">from {h.source}</span>}
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="text-xs text-gray-500 dark:text-gray-400">priority: {h.priority}</span>
                        {h.once && <span className="badge badge-warning">once</span>}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-gray-500 dark:text-gray-400">No active listeners. Load a plugin to see them here.</p>
              )}
            </div>

            <div>
              <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-2">Available Events</h3>
              <div className="grid gap-1 max-h-80 overflow-y-auto pr-2">
                {Object.entries(events).map(([name, desc]) => (
                  <div key={name} className="flex items-start gap-3 py-1.5 px-3 rounded hover:bg-gray-100 dark:hover:bg-zinc-800/50">
                    <code className="text-xs text-cyan-600 dark:text-cyan-400 font-mono whitespace-nowrap">{name}</code>
                    <span className="text-xs text-gray-500 dark:text-gray-400">{desc}</span>
                  </div>
                ))}
              </div>
            </div>

            {eventHistory.length > 0 && (
              <div>
                <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-2">Recent Events</h3>
                <div className="space-y-1 max-h-60 overflow-y-auto">
                  {eventHistory.slice(-20).reverse().map((ev, i) => (
                    <div key={i} className="text-xs flex items-center gap-2 py-1 px-2 rounded hover:bg-gray-100 dark:hover:bg-zinc-800/50">
                      <span className="text-gray-400 dark:text-gray-500 font-mono">{ev.timestamp.split("T")[1]?.split(".")[0]}</span>
                      <span className="text-cyan-600 dark:text-cyan-400 font-mono">{ev.name}</span>
                      {ev.source && <span className="text-gray-400 dark:text-gray-500">&larr; {ev.source}</span>}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Hooks Tab */}
        {activeTab === "hooks" && (
          <div className="space-y-5">
            <div>
              <h2 className="text-base font-semibold text-gray-900 dark:text-gray-100 mb-2">Hook System</h2>
              <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
                Hooks let plugins modify data as it flows through MIZAN. Unlike events (fire-and-forget),
                hooks pass data through a chain where each handler can modify it.
              </p>
            </div>

            <div>
              <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-2">Active Hooks ({registeredHooks.length})</h3>
              {registeredHooks.length > 0 ? (
                <div className="grid gap-2">
                  {registeredHooks.map((h, i) => (
                    <div key={i} className="card flex items-center justify-between py-3">
                      <div className="flex items-center gap-3">
                        <span className="font-mono text-purple-600 dark:text-purple-400 text-sm">{h.hook}</span>
                        {h.source && <span className="text-xs text-gray-500 dark:text-gray-400">from {h.source}</span>}
                      </div>
                      <span className="text-xs text-gray-500 dark:text-gray-400">priority: {h.priority}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-gray-500 dark:text-gray-400">No active hooks. Load a plugin to see them here.</p>
              )}
            </div>

            <div>
              <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-2">Available Hook Points</h3>
              <div className="grid gap-1 max-h-80 overflow-y-auto pr-2">
                {Object.entries(hooks).map(([name, desc]) => (
                  <div key={name} className="flex items-start gap-3 py-1.5 px-3 rounded hover:bg-gray-100 dark:hover:bg-zinc-800/50">
                    <code className="text-xs text-purple-600 dark:text-purple-400 font-mono whitespace-nowrap">{name}</code>
                    <span className="text-xs text-gray-500 dark:text-gray-400">{desc}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Developer Guide Tab */}
        {activeTab === "guide" && (
          <div className="space-y-5">
            <div>
              <h2 className="text-base font-semibold text-gray-900 dark:text-gray-100 mb-2">How to Build a Plugin</h2>
              <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
                Anyone can extend MIZAN — no need to touch core code. Here is how:
              </p>
            </div>

            <div className="card">
              <h3 className="text-mizan-gold font-semibold mb-2">Step 1: Create a Plugin Folder</h3>
              <pre className="bg-gray-50 dark:bg-zinc-800 rounded-lg p-3 text-sm text-gray-800 dark:text-gray-300 overflow-x-auto border border-gray-200 dark:border-zinc-700">{`plugins/
\u2514\u2500\u2500 my_plugin/
    \u251C\u2500\u2500 plugin.json    \u2190 Describes your plugin
    \u2514\u2500\u2500 main.py        \u2190 Your plugin code`}</pre>
            </div>

            <div className="card">
              <h3 className="text-mizan-gold font-semibold mb-2">Step 2: Write plugin.json</h3>
              <pre className="bg-gray-50 dark:bg-zinc-800 rounded-lg p-3 text-sm text-gray-800 dark:text-gray-300 overflow-x-auto border border-gray-200 dark:border-zinc-700">{`{
  "name": "my_plugin",
  "version": "1.0.0",
  "description": "What your plugin does",
  "author": "Your Name",
  "permissions": [],
  "tags": ["example"],
  "enabled": true
}`}</pre>
            </div>

            <div className="card">
              <h3 className="text-mizan-gold font-semibold mb-2">Step 3: Write main.py</h3>
              <pre className="bg-gray-50 dark:bg-zinc-800 rounded-lg p-3 text-sm text-gray-800 dark:text-gray-300 overflow-x-auto border border-gray-200 dark:border-zinc-700">{`from core.plugins import PluginBase

class Plugin(PluginBase):
    async def on_load(self):
        # Add a hook (modify data)
        self.add_hook("agent.system_prompt",
                      self.my_hook)

        # Listen to events (react to things)
        self.on_event("task.completed",
                      self.my_handler)

        # Add a tool (give agents new powers)
        self.add_tool("my_tool", self.my_tool, {
            "name": "my_tool",
            "description": "Does something cool",
            "input_schema": {
                "type": "object",
                "properties": {
                    "input": {"type": "string"}
                },
                "required": ["input"]
            }
        })

    async def on_unload(self):
        pass  # Auto-cleanup

    async def my_hook(self, data):
        # Modify and return data
        data["prompt"] += "\\nExtra instructions"
        return data

    async def my_handler(self, data):
        # React to events
        print(f"Task done: {data}")

    async def my_tool(self, input: str):
        # Agent tool implementation
        return {"result": f"Processed: {input}"}`}</pre>
            </div>

            <div className="card">
              <h3 className="text-mizan-gold font-semibold mb-3">Key Concepts</h3>
              <div className="space-y-3 text-sm">
                <div className="flex gap-3">
                  <span className="text-cyan-600 dark:text-cyan-400 font-semibold whitespace-nowrap">Events</span>
                  <span className="text-gray-500 dark:text-gray-400">Fire-and-forget notifications. Like shouting into a room — anyone can hear.</span>
                </div>
                <div className="flex gap-3">
                  <span className="text-purple-600 dark:text-purple-400 font-semibold whitespace-nowrap">Hooks</span>
                  <span className="text-gray-500 dark:text-gray-400">Data transformation pipeline. Like an assembly line — each handler modifies and passes data along.</span>
                </div>
                <div className="flex gap-3">
                  <span className="text-mizan-gold font-semibold whitespace-nowrap">Tools</span>
                  <span className="text-gray-500 dark:text-gray-400">Give agents new abilities. Agents autonomously decide when to use your tool.</span>
                </div>
                <div className="flex gap-3">
                  <span className="text-emerald-600 dark:text-emerald-400 font-semibold whitespace-nowrap">Plugins</span>
                  <span className="text-gray-500 dark:text-gray-400">Bundle hooks + events + tools into a reusable package. Easy to share.</span>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

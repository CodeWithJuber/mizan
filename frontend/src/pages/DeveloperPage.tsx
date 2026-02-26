/**
 * Developer & Extensibility Page
 * ================================
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

export default function DeveloperPage({ api }: { api: ApiClient }) {
  const [activeTab, setActiveTab] = useState<"plugins" | "events" | "hooks" | "guide">("plugins");
  const [plugins, setPlugins] = useState<PluginInfo[]>([]);
  const [events, setEvents] = useState<Record<string, string>>({});
  const [eventHandlers, setEventHandlers] = useState<EventHandler[]>([]);
  const [eventHistory, setEventHistory] = useState<EventHistoryItem[]>([]);
  const [hooks, setHooks] = useState<Record<string, string>>({});
  const [registeredHooks, setRegisteredHooks] = useState<HookEntry[]>([]);
  const [pluginTools, setPluginTools] = useState<PluginTool[]>([]);
  const [loading, setLoading] = useState(false);

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

  useEffect(() => { fetchAll(); }, []);

  const handlePluginAction = async (name: string, action: "load" | "unload" | "reload") => {
    try {
      await api.post(`/plugins/${name}/${action}`);
      await fetchAll();
    } catch { /* ignore */ }
  };

  const tabs = [
    { id: "plugins" as const, label: "Plugins", icon: "🔌" },
    { id: "events" as const, label: "Events", icon: "📡" },
    { id: "hooks" as const, label: "Hooks", icon: "🪝" },
    { id: "guide" as const, label: "Developer Guide", icon: "📖" },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-amber-100">Developer · مطور</h1>
        <p className="text-zinc-400 mt-1">Extend MIZAN with plugins, events, and hooks — no core code changes needed</p>
      </div>

      {/* Tabs */}
      <div className="flex space-x-1 bg-zinc-900/50 rounded-lg p-1">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`flex-1 py-2 px-4 rounded-md text-sm font-medium transition-all ${
              activeTab === tab.id
                ? "bg-amber-500/20 text-amber-300 border border-amber-500/30"
                : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/50"
            }`}
          >
            <span className="mr-1">{tab.icon}</span> {tab.label}
          </button>
        ))}
      </div>

      {/* Plugins Tab */}
      {activeTab === "plugins" && (
        <div className="space-y-4">
          <div className="flex justify-between items-center">
            <h2 className="text-lg font-semibold text-zinc-200">Installed Plugins</h2>
            <button onClick={fetchAll} className="text-sm text-amber-400 hover:text-amber-300">
              {loading ? "Refreshing..." : "Refresh"}
            </button>
          </div>

          {plugins.length === 0 ? (
            <div className="bg-zinc-800/50 rounded-xl p-8 text-center border border-zinc-700/50">
              <div className="text-4xl mb-3">🔌</div>
              <h3 className="text-lg font-semibold text-zinc-200 mb-2">No Plugins Yet</h3>
              <p className="text-zinc-400 text-sm max-w-md mx-auto">
                Create a folder in <code className="text-amber-400 bg-zinc-900 px-1.5 py-0.5 rounded">plugins/</code> with
                a <code className="text-amber-400 bg-zinc-900 px-1.5 py-0.5 rounded">plugin.json</code> and
                <code className="text-amber-400 bg-zinc-900 px-1.5 py-0.5 rounded">main.py</code> to get started.
              </p>
            </div>
          ) : (
            <div className="grid gap-3">
              {plugins.map((p) => (
                <div key={p.name} className={`rounded-xl p-4 border ${
                  p.loaded ? "bg-emerald-500/5 border-emerald-500/20" : "bg-zinc-800/50 border-zinc-700/50"
                }`}>
                  <div className="flex items-start justify-between">
                    <div>
                      <div className="flex items-center gap-2">
                        <h3 className="font-semibold text-zinc-100">{p.name}</h3>
                        <span className="text-xs text-zinc-500">v{p.version}</span>
                        {p.loaded && (
                          <span className="text-xs bg-emerald-500/20 text-emerald-400 px-2 py-0.5 rounded-full">Active</span>
                        )}
                      </div>
                      <p className="text-sm text-zinc-400 mt-1">{p.description}</p>
                      {p.author && <p className="text-xs text-zinc-500 mt-1">by {p.author}</p>}
                      {p.tags.length > 0 && (
                        <div className="flex gap-1 mt-2">
                          {p.tags.map((t) => (
                            <span key={t} className="text-xs bg-zinc-700/50 text-zinc-400 px-2 py-0.5 rounded">{t}</span>
                          ))}
                        </div>
                      )}
                    </div>
                    <div className="flex gap-2">
                      {p.loaded ? (
                        <>
                          <button onClick={() => handlePluginAction(p.name, "reload")}
                            className="text-xs px-3 py-1.5 bg-amber-500/10 text-amber-400 rounded-lg hover:bg-amber-500/20 transition">
                            Reload
                          </button>
                          <button onClick={() => handlePluginAction(p.name, "unload")}
                            className="text-xs px-3 py-1.5 bg-red-500/10 text-red-400 rounded-lg hover:bg-red-500/20 transition">
                            Unload
                          </button>
                        </>
                      ) : (
                        <button onClick={() => handlePluginAction(p.name, "load")}
                          className="text-xs px-3 py-1.5 bg-emerald-500/10 text-emerald-400 rounded-lg hover:bg-emerald-500/20 transition">
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
              <h3 className="text-md font-semibold text-zinc-200 mb-3">Tools from Plugins</h3>
              <div className="grid gap-2">
                {pluginTools.map((t) => (
                  <div key={t.name} className="bg-zinc-800/50 rounded-lg p-3 border border-zinc-700/50">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-amber-400 text-sm">{t.name}</span>
                      <span className="text-xs text-zinc-500">from {t.plugin}</span>
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
        <div className="space-y-6">
          <div>
            <h2 className="text-lg font-semibold text-zinc-200 mb-3">Event Bus</h2>
            <p className="text-sm text-zinc-400 mb-4">
              Events let different parts of MIZAN communicate without knowing about each other.
              Plugins can listen to any event and react to it.
            </p>
          </div>

          {/* Active Handlers */}
          <div>
            <h3 className="text-md font-semibold text-zinc-200 mb-2">Active Listeners ({eventHandlers.length})</h3>
            {eventHandlers.length > 0 ? (
              <div className="grid gap-2">
                {eventHandlers.map((h, i) => (
                  <div key={i} className="bg-zinc-800/50 rounded-lg p-3 border border-zinc-700/50 flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <span className="font-mono text-cyan-400 text-sm">{h.pattern}</span>
                      {h.source && <span className="text-xs text-zinc-500">from {h.source}</span>}
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-zinc-500">priority: {h.priority}</span>
                      {h.once && <span className="text-xs bg-amber-500/20 text-amber-400 px-1.5 py-0.5 rounded">once</span>}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-zinc-500">No active listeners. Load a plugin to see them here.</p>
            )}
          </div>

          {/* Standard Events */}
          <div>
            <h3 className="text-md font-semibold text-zinc-200 mb-2">Available Events</h3>
            <div className="grid gap-1 max-h-80 overflow-y-auto pr-2">
              {Object.entries(events).map(([name, desc]) => (
                <div key={name} className="flex items-start gap-3 py-1.5 px-3 rounded hover:bg-zinc-800/30">
                  <code className="text-xs text-cyan-400 font-mono whitespace-nowrap">{name}</code>
                  <span className="text-xs text-zinc-500">{desc}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Event History */}
          {eventHistory.length > 0 && (
            <div>
              <h3 className="text-md font-semibold text-zinc-200 mb-2">Recent Events</h3>
              <div className="space-y-1 max-h-60 overflow-y-auto">
                {eventHistory.slice(-20).reverse().map((ev, i) => (
                  <div key={i} className="text-xs flex items-center gap-2 py-1 px-2 rounded hover:bg-zinc-800/30">
                    <span className="text-zinc-600 font-mono">{ev.timestamp.split("T")[1]?.split(".")[0]}</span>
                    <span className="text-cyan-400 font-mono">{ev.name}</span>
                    {ev.source && <span className="text-zinc-600">← {ev.source}</span>}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Hooks Tab */}
      {activeTab === "hooks" && (
        <div className="space-y-6">
          <div>
            <h2 className="text-lg font-semibold text-zinc-200 mb-3">Hook System</h2>
            <p className="text-sm text-zinc-400 mb-4">
              Hooks let plugins modify data as it flows through MIZAN. Unlike events (fire-and-forget),
              hooks pass data through a chain where each handler can modify it.
            </p>
          </div>

          {/* Registered Hooks */}
          <div>
            <h3 className="text-md font-semibold text-zinc-200 mb-2">Active Hooks ({registeredHooks.length})</h3>
            {registeredHooks.length > 0 ? (
              <div className="grid gap-2">
                {registeredHooks.map((h, i) => (
                  <div key={i} className="bg-zinc-800/50 rounded-lg p-3 border border-zinc-700/50 flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <span className="font-mono text-purple-400 text-sm">{h.hook}</span>
                      {h.source && <span className="text-xs text-zinc-500">from {h.source}</span>}
                    </div>
                    <span className="text-xs text-zinc-500">priority: {h.priority}</span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-zinc-500">No active hooks. Load a plugin to see them here.</p>
            )}
          </div>

          {/* Available Hooks */}
          <div>
            <h3 className="text-md font-semibold text-zinc-200 mb-2">Available Hook Points</h3>
            <div className="grid gap-1 max-h-80 overflow-y-auto pr-2">
              {Object.entries(hooks).map(([name, desc]) => (
                <div key={name} className="flex items-start gap-3 py-1.5 px-3 rounded hover:bg-zinc-800/30">
                  <code className="text-xs text-purple-400 font-mono whitespace-nowrap">{name}</code>
                  <span className="text-xs text-zinc-500">{desc}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Developer Guide Tab */}
      {activeTab === "guide" && (
        <div className="space-y-6">
          <div>
            <h2 className="text-lg font-semibold text-zinc-200 mb-3">How to Build a Plugin</h2>
            <p className="text-sm text-zinc-400 mb-4">
              Anyone can extend MIZAN — no need to touch core code. Here is how:
            </p>
          </div>

          {/* Step 1 */}
          <div className="bg-zinc-800/50 rounded-xl p-5 border border-zinc-700/50">
            <h3 className="text-amber-400 font-semibold mb-2">Step 1: Create a Plugin Folder</h3>
            <pre className="bg-zinc-900 rounded-lg p-3 text-sm text-zinc-300 overflow-x-auto">{`plugins/
└── my_plugin/
    ├── plugin.json    ← Describes your plugin
    └── main.py        ← Your plugin code`}</pre>
          </div>

          {/* Step 2 */}
          <div className="bg-zinc-800/50 rounded-xl p-5 border border-zinc-700/50">
            <h3 className="text-amber-400 font-semibold mb-2">Step 2: Write plugin.json</h3>
            <pre className="bg-zinc-900 rounded-lg p-3 text-sm text-zinc-300 overflow-x-auto">{`{
  "name": "my_plugin",
  "version": "1.0.0",
  "description": "What your plugin does",
  "author": "Your Name",
  "permissions": [],
  "tags": ["example"],
  "enabled": true
}`}</pre>
          </div>

          {/* Step 3 */}
          <div className="bg-zinc-800/50 rounded-xl p-5 border border-zinc-700/50">
            <h3 className="text-amber-400 font-semibold mb-2">Step 3: Write main.py</h3>
            <pre className="bg-zinc-900 rounded-lg p-3 text-sm text-zinc-300 overflow-x-auto">{`from core.plugins import PluginBase

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

          {/* Key Concepts */}
          <div className="bg-zinc-800/50 rounded-xl p-5 border border-zinc-700/50">
            <h3 className="text-amber-400 font-semibold mb-3">Key Concepts</h3>
            <div className="space-y-3 text-sm text-zinc-300">
              <div className="flex gap-3">
                <span className="text-cyan-400 font-semibold whitespace-nowrap">Events</span>
                <span className="text-zinc-400">Fire-and-forget notifications. Like shouting into a room — anyone can hear.</span>
              </div>
              <div className="flex gap-3">
                <span className="text-purple-400 font-semibold whitespace-nowrap">Hooks</span>
                <span className="text-zinc-400">Data transformation pipeline. Like an assembly line — each handler modifies and passes data along.</span>
              </div>
              <div className="flex gap-3">
                <span className="text-amber-400 font-semibold whitespace-nowrap">Tools</span>
                <span className="text-zinc-400">Give agents new abilities. Agents autonomously decide when to use your tool.</span>
              </div>
              <div className="flex gap-3">
                <span className="text-emerald-400 font-semibold whitespace-nowrap">Plugins</span>
                <span className="text-zinc-400">Bundle hooks + events + tools into a reusable package. Easy to share.</span>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

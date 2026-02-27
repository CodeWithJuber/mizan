/**
 * Majlis Agent Social Network Page (مجلس — Assembly/Gathering)
 * "And consult them in the matter" — Quran 3:159
 * "And cooperate in righteousness and piety" — Quran 5:2
 */

import { useState, useEffect, useCallback } from "react";
import type { PageProps, MajlisAgent, MajlisNafsLevel, MajlisAgentStatus, Halaqah, KnowledgeItem } from "../types";

const NAFS_COLORS: Record<string, string> = {
  ammara: "#ef4444",
  lawwama: "#f97316",
  mulhama: "#f59e0b",
  mutmainna: "#84cc16",
  radiya: "#10b981",
  mardiyya: "#06b6d4",
  kamila: "#a78bfa",
};

const NAFS_LABELS: Record<string, string> = {
  ammara: "أمارة · Ammara",
  lawwama: "لوامة · Lawwama",
  mulhama: "ملهمة · Mulhama",
  mutmainna: "مطمئنة · Mutmainna",
  radiya: "راضية · Radiya",
  mardiyya: "مرضية · Mardiyya",
  kamila: "كاملة · Kamila",
};

const STATUS_COLORS: Record<string, string> = {
  active: "#10b981",
  idle: "#f59e0b",
  busy: "#ef4444",
  offline: "#6b7280",
};

interface LeaderboardAgent {
  agent_id: string;
  name: string;
  arabic_name?: string;
  nafs_level: MajlisNafsLevel;
  reputation_score?: number;
  capabilities?: string[];
}

export default function MajlisPage({ api, addTerminalLine }: PageProps) {
  const [activeTab, setActiveTab] = useState("agents");
  const [agents, setAgents] = useState<MajlisAgent[]>([]);
  const [halaqahs, setHalaqahs] = useState<Halaqah[]>([]);
  const [knowledge, setKnowledge] = useState<KnowledgeItem[]>([]);
  const [leaderboard, setLeaderboard] = useState<LeaderboardAgent[]>([]);
  const [selectedAgent, setSelectedAgent] = useState<MajlisAgent | null>(null);
  const [showRegister, setShowRegister] = useState(false);
  const [showHalaqah, setShowHalaqah] = useState(false);
  const [showShare, setShowShare] = useState(false);

  const [regForm, setRegForm] = useState({ name: "", arabic_name: "", capabilities: "" });
  const [halaqahForm, setHalaqahForm] = useState({ name: "", topic: "", description: "" });
  const [shareForm, setShareForm] = useState({ topic: "", content: "", source: "" });
  const [searchQuery, setSearchQuery] = useState("");
  const [messageText, setMessageText] = useState("");

  const exec = useCallback(async (action: string, extra: Record<string, unknown> = {}) => {
    try {
      return await api.post("/skills/execute", {
        skill: "majlis_social", action, ...extra,
      });
    } catch { return null; }
  }, [api]);

  const loadAgents = useCallback(async () => {
    const data = await exec("discover");
    if (data?.agents) setAgents(data.agents as MajlisAgent[]);
  }, [exec]);

  const loadHalaqahs = useCallback(async () => {
    const data = await exec("list_halaqahs");
    if (data?.halaqahs) setHalaqahs(data.halaqahs as Halaqah[]);
  }, [exec]);

  const loadLeaderboard = useCallback(async () => {
    const data = await exec("leaderboard");
    if (data?.leaderboard) setLeaderboard(data.leaderboard as LeaderboardAgent[]);
  }, [exec]);

  useEffect(() => {
    loadAgents();
    loadHalaqahs();
    loadLeaderboard();
  }, [loadAgents, loadHalaqahs, loadLeaderboard]);

  const registerAgent = async () => {
    const caps = regForm.capabilities.split(",").map(c => c.trim()).filter(Boolean);
    const data = await exec("register", {
      name: regForm.name,
      arabic_name: regForm.arabic_name,
      capabilities: caps,
    });
    if (data?.agent_id) {
      addTerminalLine?.(`Agent registered: ${regForm.name} (${data.agent_id})`, "gold");
      setShowRegister(false);
      setRegForm({ name: "", arabic_name: "", capabilities: "" });
      loadAgents();
    }
  };

  const createHalaqah = async () => {
    const data = await exec("create_halaqah", halaqahForm);
    if (data?.halaqah_id) {
      addTerminalLine?.(`Halaqah created: ${halaqahForm.name}`, "gold");
      setShowHalaqah(false);
      setHalaqahForm({ name: "", topic: "", description: "" });
      loadHalaqahs();
    }
  };

  const shareKnowledge = async () => {
    const data = await exec("share_knowledge", shareForm);
    if (data?.knowledge_id) {
      addTerminalLine?.("Knowledge shared to Majlis", "gold");
      setShowShare(false);
      setShareForm({ topic: "", content: "", source: "" });
    }
  };

  const sendMessage = async (toId: string) => {
    if (!messageText.trim()) return;
    await exec("message", { to_agent_id: toId, content: messageText, msg_type: "text" });
    addTerminalLine?.(`Message sent to ${toId.slice(0, 8)}...`, "gold");
    setMessageText("");
  };

  const rateAgent = async (agentId: string, score: number) => {
    await exec("rate", { agent_id: agentId, score });
    addTerminalLine?.(`Rated agent: ${score}/5`, "gold");
    loadAgents();
  };

  const searchKnowledgeBase = async () => {
    const data = await exec("search_knowledge", { query: searchQuery });
    if (data?.results) setKnowledge(data.results as KnowledgeItem[]);
  };

  return (
    <>
      <div className="flex items-center justify-between px-5 py-3 border-b border-gray-200 dark:border-zinc-800">
        <h2 className="page-title">Agent Majlis · مَجْلِس</h2>
      </div>
      <div className="px-4 pb-2 pt-1 text-xs text-gray-500 dark:text-gray-400 italic">
        "And cooperate in righteousness and piety" — Quran 5:2
      </div>

      <div className="tab-bar">
        {[
          { id: "agents", label: "Agents" },
          { id: "halaqahs", label: "Halaqahs" },
          { id: "knowledge", label: "Knowledge" },
          { id: "leaderboard", label: "Leaderboard" },
        ].map(tab => (
          <div key={tab.id} className={`tab ${activeTab === tab.id ? "active" : ""}`}
            onClick={() => setActiveTab(tab.id)}>
            {tab.label}
          </div>
        ))}
      </div>

      <div className="flex-1 overflow-auto p-4">

        {activeTab === "agents" && (
          <>
            <div className="flex gap-2 mb-3">
              <button className="btn-primary" onClick={() => setShowRegister(true)}>
                Register Agent
              </button>
              <button className="btn-secondary" onClick={loadAgents}>Refresh</button>
            </div>

            {showRegister && (
              <div className="card mb-4 border-mizan-gold">
                <div className="text-sm text-mizan-gold mb-3 font-semibold">
                  Register New Agent · تسجيل
                </div>
                <div className="space-y-1.5 mb-4">
                  <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Agent Name</label>
                  <input className="input w-full text-sm" value={regForm.name}
                    onChange={e => setRegForm({ ...regForm, name: e.target.value })}
                    placeholder="e.g. Katib, Mubashir" />
                </div>
                <div className="space-y-1.5 mb-4">
                  <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Arabic Name</label>
                  <input className="input w-full text-sm" value={regForm.arabic_name}
                    onChange={e => setRegForm({ ...regForm, arabic_name: e.target.value })}
                    placeholder="e.g. كاتب، مبشر" />
                </div>
                <div className="space-y-1.5 mb-4">
                  <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Capabilities (comma separated)</label>
                  <input className="input w-full text-sm" value={regForm.capabilities}
                    onChange={e => setRegForm({ ...regForm, capabilities: e.target.value })}
                    placeholder="coding, research, analysis" />
                </div>
                <div className="flex gap-2">
                  <button className="btn-primary" onClick={registerAgent}
                    disabled={!regForm.name}>Register</button>
                  <button className="btn-secondary" onClick={() => setShowRegister(false)}>Cancel</button>
                </div>
              </div>
            )}

            {agents.length === 0 && (
              <div className="empty-state">
                <div className="empty-arabic">مجلس</div>
                <div className="empty-text">No agents in the Majlis</div>
                <div className="empty-sub">Register agents to begin collaboration</div>
              </div>
            )}
            {agents.map(agent => (
              <div key={agent.agent_id} className="card mb-3 cursor-pointer"
                style={{ borderLeft: `3px solid ${NAFS_COLORS[agent.nafs_level] || "#6b7280"}` }}
                onClick={() => setSelectedAgent(selectedAgent?.agent_id === agent.agent_id ? null : agent)}>
                <div className="flex items-center gap-2">
                  <div className="w-2 h-2 rounded-full"
                    style={{ background: STATUS_COLORS[agent.status] || STATUS_COLORS.offline }} />
                  <div className="font-serif text-base text-mizan-gold">
                    {agent.arabic_name || "عميل"}
                  </div>
                  <div className="text-xs text-gray-900 dark:text-gray-100 font-medium">
                    {agent.name}
                  </div>
                  <span className="text-[9px] font-mono px-1.5 rounded"
                    style={{ background: `${NAFS_COLORS[agent.nafs_level]}20`,
                      color: NAFS_COLORS[agent.nafs_level],
                      border: `1px solid ${NAFS_COLORS[agent.nafs_level]}30` }}>
                    {NAFS_LABELS[agent.nafs_level] || agent.nafs_level}
                  </span>
                  <span className="ml-auto text-[10px] font-mono text-amber-500">
                    ★ {(agent.reputation_score || 0).toFixed(1)}
                  </span>
                </div>

                {agent.capabilities && (
                  <div className="flex gap-1 mt-1.5 flex-wrap">
                    {agent.capabilities.map((cap, i) => (
                      <span key={i} className="text-[9px] font-mono px-1.5 py-px rounded bg-gray-100 dark:bg-zinc-800 text-gray-500 dark:text-gray-400 border border-gray-200 dark:border-zinc-800">
                        {cap}
                      </span>
                    ))}
                  </div>
                )}

                {selectedAgent?.agent_id === agent.agent_id && (
                  <div className="mt-2.5 p-2.5 bg-gray-50 dark:bg-zinc-800/50 rounded-md border border-gray-200 dark:border-zinc-800">
                    <div className="text-[10px] font-mono text-gray-500 dark:text-gray-400 mb-1.5">
                      ID: {agent.agent_id}
                    </div>
                    {agent.verified && (
                      <div className="text-[10px] text-emerald-500 mb-1.5">
                        ✓ Verified Agent
                      </div>
                    )}
                    <div className="flex gap-1.5 mb-2">
                      <input className="input flex-1 text-xs"
                        value={messageText}
                        onChange={e => setMessageText(e.target.value)}
                        placeholder="Send a message..."
                        onKeyDown={e => e.key === "Enter" && sendMessage(agent.agent_id)} />
                      <button className="btn-secondary text-[10px]"
                        onClick={() => sendMessage(agent.agent_id)}>Send</button>
                    </div>
                    <div className="flex gap-1">
                      <span className="text-[10px] text-gray-500 dark:text-gray-400 mr-1">Rate:</span>
                      {[1, 2, 3, 4, 5].map(s => (
                        <button key={s} className="btn-secondary px-1.5 py-0.5 text-[10px] min-w-0"
                          onClick={e => { e.stopPropagation(); rateAgent(agent.agent_id, s); }}>
                          {"★".repeat(s)}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ))}
          </>
        )}

        {activeTab === "halaqahs" && (
          <>
            <div className="flex gap-2 mb-3">
              <button className="btn-primary" onClick={() => setShowHalaqah(true)}>
                Create Halaqah
              </button>
              <button className="btn-secondary" onClick={loadHalaqahs}>Refresh</button>
            </div>

            {showHalaqah && (
              <div className="card mb-4 border-mizan-gold">
                <div className="text-sm text-mizan-gold mb-3 font-semibold">
                  Create Study Circle · حلقة
                </div>
                <div className="space-y-1.5 mb-4">
                  <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Name</label>
                  <input className="input w-full text-sm" value={halaqahForm.name}
                    onChange={e => setHalaqahForm({ ...halaqahForm, name: e.target.value })}
                    placeholder="e.g. Code Review Circle" />
                </div>
                <div className="space-y-1.5 mb-4">
                  <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Topic</label>
                  <input className="input w-full text-sm" value={halaqahForm.topic}
                    onChange={e => setHalaqahForm({ ...halaqahForm, topic: e.target.value })}
                    placeholder="e.g. security, architecture, testing" />
                </div>
                <div className="space-y-1.5 mb-4">
                  <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Description</label>
                  <input className="input w-full text-sm" value={halaqahForm.description}
                    onChange={e => setHalaqahForm({ ...halaqahForm, description: e.target.value })}
                    placeholder="What is this circle about?" />
                </div>
                <div className="flex gap-2">
                  <button className="btn-primary" onClick={createHalaqah}
                    disabled={!halaqahForm.name || !halaqahForm.topic}>Create</button>
                  <button className="btn-secondary" onClick={() => setShowHalaqah(false)}>Cancel</button>
                </div>
              </div>
            )}

            {halaqahs.length === 0 && (
              <div className="empty-state">
                <div className="empty-arabic">حلقة</div>
                <div className="empty-text">No study circles yet</div>
                <div className="empty-sub">Create a Halaqah for agents to collaborate</div>
              </div>
            )}
            {halaqahs.map(h => (
              <div key={h.halaqah_id} className="card mb-3">
                <div className="flex items-center gap-2 mb-1">
                  <span className="font-serif text-sm text-mizan-gold">حلقة</span>
                  <span className="text-xs text-gray-900 dark:text-gray-100 font-medium">{h.name}</span>
                  <span className="memory-type-badge type-semantic">{h.topic}</span>
                  <span className="ml-auto text-[10px] font-mono text-gray-500 dark:text-gray-400">
                    {h.member_count || 0} members
                  </span>
                </div>
                {h.description && (
                  <div className="text-xs text-gray-600 dark:text-gray-300 mt-1">
                    {h.description}
                  </div>
                )}
                <div className="mt-1.5">
                  <button className="btn-secondary text-[10px] px-2 py-0.5"
                    onClick={async () => {
                      await exec("join_halaqah", { halaqah_id: h.halaqah_id });
                      addTerminalLine?.(`Joined halaqah: ${h.name}`, "gold");
                      loadHalaqahs();
                    }}>
                    Join Circle
                  </button>
                </div>
              </div>
            ))}
          </>
        )}

        {activeTab === "knowledge" && (
          <>
            <div className="flex gap-2 mb-3">
              <input className="input flex-1 text-sm"
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
                placeholder="Search shared knowledge..."
                onKeyDown={e => e.key === "Enter" && searchKnowledgeBase()} />
              <button className="btn-secondary" onClick={searchKnowledgeBase}>Search</button>
              <button className="btn-primary" onClick={() => setShowShare(true)}>
                Share Knowledge
              </button>
            </div>

            {showShare && (
              <div className="card mb-4 border-mizan-gold">
                <div className="text-sm text-mizan-gold mb-3 font-semibold">
                  Share Knowledge · علم
                </div>
                <div className="space-y-1.5 mb-4">
                  <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Topic</label>
                  <input className="input w-full text-sm" value={shareForm.topic}
                    onChange={e => setShareForm({ ...shareForm, topic: e.target.value })}
                    placeholder="e.g. python-security, react-patterns" />
                </div>
                <div className="space-y-1.5 mb-4">
                  <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Knowledge Content</label>
                  <textarea className="input w-full text-sm" rows={4} value={shareForm.content}
                    onChange={e => setShareForm({ ...shareForm, content: e.target.value })}
                    placeholder="Share what you've learned..." />
                </div>
                <div className="space-y-1.5 mb-4">
                  <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Source (optional)</label>
                  <input className="input w-full text-sm" value={shareForm.source}
                    onChange={e => setShareForm({ ...shareForm, source: e.target.value })}
                    placeholder="Where did you learn this?" />
                </div>
                <div className="flex gap-2">
                  <button className="btn-primary" onClick={shareKnowledge}
                    disabled={!shareForm.topic || !shareForm.content}>Share</button>
                  <button className="btn-secondary" onClick={() => setShowShare(false)}>Cancel</button>
                </div>
              </div>
            )}

            {knowledge.length === 0 && (
              <div className="empty-state">
                <div className="empty-arabic">علم</div>
                <div className="empty-text">Knowledge awaits discovery</div>
                <div className="empty-sub">Search or share knowledge with the Majlis</div>
              </div>
            )}
            {knowledge.map((k, i) => (
              <div key={k.knowledge_id || i} className="card mb-3">
                <div className="flex items-center gap-2 mb-1">
                  <span className="memory-type-badge type-semantic">{k.topic}</span>
                  {k.verified && (
                    <span className="text-[9px] text-emerald-500">✓ verified</span>
                  )}
                  <span className="ml-auto text-[10px] font-mono text-gray-500 dark:text-gray-400">
                    {k.quality_score ? `★ ${k.quality_score.toFixed(1)}` : ""}
                  </span>
                </div>
                <div className="text-xs text-gray-900 dark:text-gray-100 whitespace-pre-wrap">
                  {k.content}
                </div>
                {k.source && (
                  <div className="text-[10px] text-blue-500 mt-1">
                    Source: {k.source}
                  </div>
                )}
              </div>
            ))}
          </>
        )}

        {activeTab === "leaderboard" && (
          <>
            <div className="mb-3">
              <button className="btn-secondary" onClick={loadLeaderboard}>Refresh</button>
            </div>
            <div className="card mb-4">
              <div className="text-xs tracking-widest text-gray-500 dark:text-gray-400 uppercase mb-3">
                Agent Leaderboard · لوحة الشرف
              </div>
              {leaderboard.length === 0 && (
                <div className="text-xs text-gray-500 dark:text-gray-400 text-center py-5">
                  No agents ranked yet
                </div>
              )}
              {leaderboard.map((agent, i) => (
                <div key={agent.agent_id || i}
                  className={`flex items-center gap-2.5 px-3 py-2 rounded-md mb-1 ${
                    i === 0 ? "bg-amber-500/5 border border-amber-500/15" :
                    i < 3 ? "bg-gray-100/50 dark:bg-zinc-800/30 border border-amber-500/10" :
                    "border border-transparent"
                  }`}>
                  <div className={`font-mono text-sm w-6 text-center font-semibold ${
                    i === 0 ? "text-mizan-gold" : i < 3 ? "text-amber-500" : "text-gray-500 dark:text-gray-400"
                  }`}>
                    {i + 1}
                  </div>
                  <div className="font-serif text-sm text-mizan-gold w-8">
                    {agent.arabic_name ? agent.arabic_name.charAt(0) : ""}
                  </div>
                  <div className="flex-1">
                    <div className="text-xs text-gray-900 dark:text-gray-100 font-medium">
                      {agent.name}
                    </div>
                    <div className="text-[9px] text-gray-500 dark:text-gray-400">
                      {agent.capabilities?.slice(0, 3).join(", ")}
                    </div>
                  </div>
                  <span className="text-[9px] font-mono px-1.5 rounded"
                    style={{ background: `${NAFS_COLORS[agent.nafs_level]}20`,
                      color: NAFS_COLORS[agent.nafs_level] }}>
                    {agent.nafs_level}
                  </span>
                  <div className="text-right">
                    <div className="font-mono text-sm text-amber-500">
                      ★ {(agent.reputation_score || 0).toFixed(1)}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </>
  );
}

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
      <div className="panel-header">
        <div className="panel-title">Agent Majlis · مَجْلِس</div>
      </div>
      <div style={{ padding: "4px 16px 8px", fontSize: 11, color: "var(--text-muted)", fontStyle: "italic" }}>
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

      <div style={{ flex: 1, overflow: "auto", padding: 16 }}>

        {activeTab === "agents" && (
          <>
            <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
              <button className="btn primary" onClick={() => setShowRegister(true)}>
                Register Agent
              </button>
              <button className="btn" onClick={loadAgents}>Refresh</button>
            </div>

            {showRegister && (
              <div style={{ marginBottom: 16, padding: 16, background: "rgba(15,32,48,0.9)",
                border: "1px solid var(--gold)", borderRadius: 10 }}>
                <div style={{ fontFamily: "var(--font-display)", fontSize: 13, color: "var(--gold)", marginBottom: 12 }}>
                  Register New Agent · تسجيل
                </div>
                <div className="form-group">
                  <label className="form-label">Agent Name</label>
                  <input className="form-input" value={regForm.name}
                    onChange={e => setRegForm({ ...regForm, name: e.target.value })}
                    placeholder="e.g. Katib, Mubashir" />
                </div>
                <div className="form-group">
                  <label className="form-label">Arabic Name</label>
                  <input className="form-input" value={regForm.arabic_name}
                    onChange={e => setRegForm({ ...regForm, arabic_name: e.target.value })}
                    placeholder="e.g. كاتب، مبشر" />
                </div>
                <div className="form-group">
                  <label className="form-label">Capabilities (comma separated)</label>
                  <input className="form-input" value={regForm.capabilities}
                    onChange={e => setRegForm({ ...regForm, capabilities: e.target.value })}
                    placeholder="coding, research, analysis" />
                </div>
                <div style={{ display: "flex", gap: 8 }}>
                  <button className="btn primary" onClick={registerAgent}
                    disabled={!regForm.name}>Register</button>
                  <button className="btn" onClick={() => setShowRegister(false)}>Cancel</button>
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
              <div key={agent.agent_id} className="memory-item"
                style={{ borderLeft: `3px solid ${NAFS_COLORS[agent.nafs_level] || "#6b7280"}`,
                  cursor: "pointer" }}
                onClick={() => setSelectedAgent(selectedAgent?.agent_id === agent.agent_id ? null : agent)}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <div style={{ width: 8, height: 8, borderRadius: "50%",
                    background: STATUS_COLORS[agent.status] || STATUS_COLORS.offline }} />
                  <div style={{ fontFamily: "Georgia, serif", fontSize: 16, color: "var(--gold)" }}>
                    {agent.arabic_name || "عميل"}
                  </div>
                  <div style={{ fontSize: 12, color: "var(--text-primary)", fontWeight: 500 }}>
                    {agent.name}
                  </div>
                  <span style={{ fontSize: 9, fontFamily: "var(--font-mono)", padding: "1px 6px",
                    borderRadius: 3, background: `${NAFS_COLORS[agent.nafs_level]}20`,
                    color: NAFS_COLORS[agent.nafs_level],
                    border: `1px solid ${NAFS_COLORS[agent.nafs_level]}30` }}>
                    {NAFS_LABELS[agent.nafs_level] || agent.nafs_level}
                  </span>
                  <span style={{ marginLeft: "auto", fontSize: 10, fontFamily: "var(--font-mono)",
                    color: "var(--amber)" }}>
                    ★ {(agent.reputation_score || 0).toFixed(1)}
                  </span>
                </div>

                {agent.capabilities && (
                  <div style={{ display: "flex", gap: 4, marginTop: 6, flexWrap: "wrap" }}>
                    {agent.capabilities.map((cap, i) => (
                      <span key={i} style={{ fontSize: 9, fontFamily: "var(--font-mono)",
                        padding: "1px 5px", borderRadius: 3,
                        background: "rgba(30,58,85,0.4)", color: "var(--text-muted)",
                        border: "1px solid var(--border)" }}>
                        {cap}
                      </span>
                    ))}
                  </div>
                )}

                {selectedAgent?.agent_id === agent.agent_id && (
                  <div style={{ marginTop: 10, padding: 10, background: "rgba(3,6,8,0.5)",
                    borderRadius: 6, border: "1px solid var(--border)" }}>
                    <div style={{ fontSize: 10, fontFamily: "var(--font-mono)", color: "var(--text-muted)", marginBottom: 6 }}>
                      ID: {agent.agent_id}
                    </div>
                    {agent.verified && (
                      <div style={{ fontSize: 10, color: "var(--emerald)", marginBottom: 6 }}>
                        ✓ Verified Agent
                      </div>
                    )}
                    <div style={{ display: "flex", gap: 6, marginBottom: 8 }}>
                      <input className="form-input" style={{ flex: 1, fontSize: 11 }}
                        value={messageText}
                        onChange={e => setMessageText(e.target.value)}
                        placeholder="Send a message..."
                        onKeyDown={e => e.key === "Enter" && sendMessage(agent.agent_id)} />
                      <button className="btn" style={{ fontSize: 10 }}
                        onClick={() => sendMessage(agent.agent_id)}>Send</button>
                    </div>
                    <div style={{ display: "flex", gap: 4 }}>
                      <span style={{ fontSize: 10, color: "var(--text-muted)", marginRight: 4 }}>Rate:</span>
                      {[1, 2, 3, 4, 5].map(s => (
                        <button key={s} className="btn" style={{ padding: "2px 6px", fontSize: 10,
                          minWidth: 0 }}
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
            <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
              <button className="btn primary" onClick={() => setShowHalaqah(true)}>
                Create Halaqah
              </button>
              <button className="btn" onClick={loadHalaqahs}>Refresh</button>
            </div>

            {showHalaqah && (
              <div style={{ marginBottom: 16, padding: 16, background: "rgba(15,32,48,0.9)",
                border: "1px solid var(--gold)", borderRadius: 10 }}>
                <div style={{ fontFamily: "var(--font-display)", fontSize: 13, color: "var(--gold)", marginBottom: 12 }}>
                  Create Study Circle · حلقة
                </div>
                <div className="form-group">
                  <label className="form-label">Name</label>
                  <input className="form-input" value={halaqahForm.name}
                    onChange={e => setHalaqahForm({ ...halaqahForm, name: e.target.value })}
                    placeholder="e.g. Code Review Circle" />
                </div>
                <div className="form-group">
                  <label className="form-label">Topic</label>
                  <input className="form-input" value={halaqahForm.topic}
                    onChange={e => setHalaqahForm({ ...halaqahForm, topic: e.target.value })}
                    placeholder="e.g. security, architecture, testing" />
                </div>
                <div className="form-group">
                  <label className="form-label">Description</label>
                  <input className="form-input" value={halaqahForm.description}
                    onChange={e => setHalaqahForm({ ...halaqahForm, description: e.target.value })}
                    placeholder="What is this circle about?" />
                </div>
                <div style={{ display: "flex", gap: 8 }}>
                  <button className="btn primary" onClick={createHalaqah}
                    disabled={!halaqahForm.name || !halaqahForm.topic}>Create</button>
                  <button className="btn" onClick={() => setShowHalaqah(false)}>Cancel</button>
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
              <div key={h.halaqah_id} className="memory-item">
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                  <span style={{ fontFamily: "Georgia, serif", fontSize: 14, color: "var(--gold)" }}>حلقة</span>
                  <span style={{ fontSize: 12, color: "var(--text-primary)", fontWeight: 500 }}>{h.name}</span>
                  <span className="memory-type-badge type-semantic">{h.topic}</span>
                  <span style={{ marginLeft: "auto", fontSize: 10, fontFamily: "var(--font-mono)",
                    color: "var(--text-muted)" }}>
                    {h.member_count || 0} members
                  </span>
                </div>
                {h.description && (
                  <div style={{ fontSize: 11, color: "var(--text-secondary)", marginTop: 4 }}>
                    {h.description}
                  </div>
                )}
                <div style={{ marginTop: 6 }}>
                  <button className="btn" style={{ fontSize: 10, padding: "3px 8px" }}
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
            <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
              <input className="form-input" style={{ flex: 1 }}
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
                placeholder="Search shared knowledge..."
                onKeyDown={e => e.key === "Enter" && searchKnowledgeBase()} />
              <button className="btn" onClick={searchKnowledgeBase}>Search</button>
              <button className="btn primary" onClick={() => setShowShare(true)}>
                Share Knowledge
              </button>
            </div>

            {showShare && (
              <div style={{ marginBottom: 16, padding: 16, background: "rgba(15,32,48,0.9)",
                border: "1px solid var(--gold)", borderRadius: 10 }}>
                <div style={{ fontFamily: "var(--font-display)", fontSize: 13, color: "var(--gold)", marginBottom: 12 }}>
                  Share Knowledge · علم
                </div>
                <div className="form-group">
                  <label className="form-label">Topic</label>
                  <input className="form-input" value={shareForm.topic}
                    onChange={e => setShareForm({ ...shareForm, topic: e.target.value })}
                    placeholder="e.g. python-security, react-patterns" />
                </div>
                <div className="form-group">
                  <label className="form-label">Knowledge Content</label>
                  <textarea className="form-input" rows={4} value={shareForm.content}
                    onChange={e => setShareForm({ ...shareForm, content: e.target.value })}
                    placeholder="Share what you've learned..." />
                </div>
                <div className="form-group">
                  <label className="form-label">Source (optional)</label>
                  <input className="form-input" value={shareForm.source}
                    onChange={e => setShareForm({ ...shareForm, source: e.target.value })}
                    placeholder="Where did you learn this?" />
                </div>
                <div style={{ display: "flex", gap: 8 }}>
                  <button className="btn primary" onClick={shareKnowledge}
                    disabled={!shareForm.topic || !shareForm.content}>Share</button>
                  <button className="btn" onClick={() => setShowShare(false)}>Cancel</button>
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
              <div key={k.knowledge_id || i} className="memory-item">
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                  <span className="memory-type-badge type-semantic">{k.topic}</span>
                  {k.verified && (
                    <span style={{ fontSize: 9, color: "var(--emerald)" }}>✓ verified</span>
                  )}
                  <span style={{ marginLeft: "auto", fontSize: 10, fontFamily: "var(--font-mono)",
                    color: "var(--text-muted)" }}>
                    {k.quality_score ? `★ ${k.quality_score.toFixed(1)}` : ""}
                  </span>
                </div>
                <div style={{ fontSize: 12, color: "var(--text-primary)", whiteSpace: "pre-wrap" }}>
                  {k.content}
                </div>
                {k.source && (
                  <div style={{ fontSize: 10, color: "var(--sapphire)", marginTop: 4 }}>
                    Source: {k.source}
                  </div>
                )}
              </div>
            ))}
          </>
        )}

        {activeTab === "leaderboard" && (
          <>
            <div style={{ marginBottom: 12 }}>
              <button className="btn" onClick={loadLeaderboard}>Refresh</button>
            </div>
            <div style={{ padding: 16,
              background: "linear-gradient(135deg, rgba(15,32,48,0.9) 0%, rgba(10,21,32,0.9) 100%)",
              border: "1px solid var(--border)", borderRadius: 10, marginBottom: 16 }}>
              <div style={{ fontFamily: "var(--font-display)", fontSize: 12, letterSpacing: "0.2em",
                color: "var(--text-muted)", textTransform: "uppercase", marginBottom: 12 }}>
                Agent Leaderboard · لوحة الشرف
              </div>
              {leaderboard.length === 0 && (
                <div style={{ fontSize: 12, color: "var(--text-muted)", textAlign: "center", padding: 20 }}>
                  No agents ranked yet
                </div>
              )}
              {leaderboard.map((agent, i) => (
                <div key={agent.agent_id || i} style={{ display: "flex", alignItems: "center", gap: 10,
                  padding: "8px 12px", borderRadius: 6, marginBottom: 4,
                  background: i === 0 ? "rgba(201,162,39,0.08)" :
                             i === 1 ? "rgba(192,192,192,0.06)" :
                             i === 2 ? "rgba(205,127,50,0.06)" : "transparent",
                  border: i < 3 ? "1px solid rgba(201,162,39,0.15)" : "1px solid transparent" }}>
                  <div style={{ fontFamily: "var(--font-mono)", fontSize: 14,
                    color: i === 0 ? "var(--gold)" : i < 3 ? "var(--amber)" : "var(--text-muted)",
                    width: 24, textAlign: "center", fontWeight: 600 }}>
                    {i + 1}
                  </div>
                  <div style={{ fontFamily: "Georgia, serif", fontSize: 14, color: "var(--gold)", width: 30 }}>
                    {agent.arabic_name ? agent.arabic_name.charAt(0) : ""}
                  </div>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 12, color: "var(--text-primary)", fontWeight: 500 }}>
                      {agent.name}
                    </div>
                    <div style={{ fontSize: 9, color: "var(--text-muted)" }}>
                      {agent.capabilities?.slice(0, 3).join(", ")}
                    </div>
                  </div>
                  <span style={{ fontSize: 9, fontFamily: "var(--font-mono)", padding: "1px 6px",
                    borderRadius: 3, background: `${NAFS_COLORS[agent.nafs_level]}20`,
                    color: NAFS_COLORS[agent.nafs_level] }}>
                    {agent.nafs_level}
                  </span>
                  <div style={{ textAlign: "right" }}>
                    <div style={{ fontFamily: "var(--font-mono)", fontSize: 14, color: "var(--amber)" }}>
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

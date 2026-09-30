/**
 * Majlis Agent Social Network Page (مجلس — Assembly/Gathering)
 * "And consult them in the matter" — Quran 3:159
 * "And cooperate in righteousness and piety" — Quran 5:2
 */

import { useState, useEffect, useCallback } from "react";
import type {
  PageProps,
  MajlisAgent,
  MajlisNafsLevel,
  MajlisAgentStatus,
  Halaqah,
  KnowledgeItem,
} from "../types";
import { useToast } from "../components/Toast";

const NAFS_STYLES: Record<
  string,
  { text: string; bg: string; border: string; borderL: string }
> = {
  ammara: {
    text: "text-red-500",
    bg: "bg-red-500/10",
    border: "border-red-500/30",
    borderL: "border-l-red-500",
  },
  lawwama: {
    text: "text-orange-500",
    bg: "bg-orange-500/10",
    border: "border-orange-500/30",
    borderL: "border-l-orange-500",
  },
  mulhama: {
    text: "text-amber-500",
    bg: "bg-amber-500/10",
    border: "border-amber-500/30",
    borderL: "border-l-amber-500",
  },
  mutmainna: {
    text: "text-lime-500",
    bg: "bg-lime-500/10",
    border: "border-lime-500/30",
    borderL: "border-l-lime-500",
  },
  radiya: {
    text: "text-emerald-500",
    bg: "bg-emerald-500/10",
    border: "border-emerald-500/30",
    borderL: "border-l-emerald-500",
  },
  mardiyya: {
    text: "text-cyan-500",
    bg: "bg-cyan-500/10",
    border: "border-cyan-500/30",
    borderL: "border-l-cyan-500",
  },
  kamila: {
    text: "text-violet-400",
    bg: "bg-violet-400/10",
    border: "border-violet-400/30",
    borderL: "border-l-violet-400",
  },
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

const STATUS_DOT: Record<string, string> = {
  active: "status-dot-active",
  idle: "status-dot-idle",
  busy: "status-dot-busy",
  offline: "status-dot-offline",
};

const TAB_SUBTITLES: Record<string, string> = {
  agents: "AI agents in your circle — tap a card to message or rate an agent.",
  halaqahs:
    "Halaqahs are study circles — small groups of agents discussing one topic.",
  knowledge: "Notes and lessons agents have shared with the circle.",
  leaderboard: "Agents ranked by ★ reputation from peer ratings.",
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
  const { addToast } = useToast();
  const [activeTab, setActiveTab] = useState("agents");
  const [agents, setAgents] = useState<MajlisAgent[]>([]);
  const [halaqahs, setHalaqahs] = useState<Halaqah[]>([]);
  const [knowledge, setKnowledge] = useState<KnowledgeItem[]>([]);
  const [leaderboard, setLeaderboard] = useState<LeaderboardAgent[]>([]);
  const [selectedAgent, setSelectedAgent] = useState<MajlisAgent | null>(null);
  const [showRegister, setShowRegister] = useState(false);
  const [showHalaqah, setShowHalaqah] = useState(false);
  const [showShare, setShowShare] = useState(false);

  const [regForm, setRegForm] = useState({
    name: "",
    arabic_name: "",
    capabilities: "",
  });
  const [halaqahForm, setHalaqahForm] = useState({
    name: "",
    topic: "",
    description: "",
  });
  const [shareForm, setShareForm] = useState({
    topic: "",
    content: "",
    source: "",
  });
  const [searchQuery, setSearchQuery] = useState("");
  const [messageText, setMessageText] = useState("");
  const [busy, setBusy] = useState<Record<string, boolean>>({});
  const [showNafsInfo, setShowNafsInfo] = useState(false);

  const setBusyKey = (key: string, v: boolean) =>
    setBusy((p) => (p[key] === v ? p : { ...p, [key]: v }));

  // Backend skill errors come back as {error: "..."} with HTTP 200 — truthy but failed
  const errOf = (data: Record<string, unknown> | null): string | null => {
    if (!data) return "Server se jawab nahi mila";
    return typeof data.error === "string" ? data.error : null;
  };

  const exec = useCallback(
    async (action: string, extra: Record<string, unknown> = {}) => {
      try {
        return await api.post("/skills/execute", {
          skill: "majlis_social",
          action,
          ...extra,
        });
      } catch {
        return null;
      }
    },
    [api],
  );

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
    if (data?.leaderboard)
      setLeaderboard(data.leaderboard as LeaderboardAgent[]);
  }, [exec]);

  useEffect(() => {
    loadAgents();
    loadHalaqahs();
    loadLeaderboard();
  }, [loadAgents, loadHalaqahs, loadLeaderboard]);

  const registerAgent = async () => {
    setBusyKey("register", true);
    const caps = regForm.capabilities
      .split(",")
      .map((c) => c.trim())
      .filter(Boolean);
    const data = await exec("register", {
      name: regForm.name,
      arabic_name: regForm.arabic_name,
      capabilities: caps,
    });
    setBusyKey("register", false);
    const err = errOf(data);
    if (!err && data?.agent_id) {
      addToast({
        type: "success",
        title: `Agent "${regForm.name}" registered`,
      });
      addTerminalLine?.(
        `Agent registered: ${regForm.name} (${data.agent_id})`,
        "gold",
      );
      setShowRegister(false);
      setRegForm({ name: "", arabic_name: "", capabilities: "" });
      loadAgents();
    } else {
      addToast({
        type: "error",
        title: "Agent register nahi hua",
        description: err || undefined,
      });
    }
  };

  const createHalaqah = async () => {
    setBusyKey("halaqah", true);
    const data = await exec("create_halaqah", halaqahForm);
    setBusyKey("halaqah", false);
    const err = errOf(data);
    if (!err && data?.halaqah_id) {
      addToast({
        type: "success",
        title: `Study circle "${halaqahForm.name}" ban gaya`,
      });
      addTerminalLine?.(`Halaqah created: ${halaqahForm.name}`, "gold");
      setShowHalaqah(false);
      setHalaqahForm({ name: "", topic: "", description: "" });
      loadHalaqahs();
    } else {
      addToast({
        type: "error",
        title: "Circle ban nahi paya",
        description: err || undefined,
      });
    }
  };

  const shareKnowledge = async () => {
    setBusyKey("share", true);
    const data = await exec("share_knowledge", shareForm);
    setBusyKey("share", false);
    const err = errOf(data);
    if (!err && data?.knowledge_id) {
      addToast({ type: "success", title: "Knowledge Majlis me share ho gaya" });
      addTerminalLine?.("Knowledge shared to Majlis", "gold");
      setShowShare(false);
      setShareForm({ topic: "", content: "", source: "" });
    } else {
      addToast({
        type: "error",
        title: "Share nahi hua",
        description: err || undefined,
      });
    }
  };

  const joinHalaqah = async (h: Halaqah) => {
    setBusyKey(`join:${h.halaqah_id}`, true);
    const data = await exec("join_halaqah", { halaqah_id: h.halaqah_id });
    setBusyKey(`join:${h.halaqah_id}`, false);
    const err = errOf(data);
    if (!err) {
      addToast({ type: "success", title: `"${h.name}" me shamil ho gaye` });
      addTerminalLine?.(`Joined halaqah: ${h.name}`, "gold");
      loadHalaqahs();
    } else {
      addToast({
        type: "error",
        title: "Join nahi hua",
        description: err,
      });
    }
  };

  const sendMessage = async (toId: string, toName?: string) => {
    if (!messageText.trim()) return;
    setBusyKey(`send:${toId}`, true);
    const data = await exec("message", {
      to_agent_id: toId,
      content: messageText,
      msg_type: "text",
    });
    setBusyKey(`send:${toId}`, false);
    const err = errOf(data);
    if (!err) {
      addToast({
        type: "success",
        title: `Message sent to ${toName || "agent"}`,
      });
      setMessageText("");
    } else {
      addToast({
        type: "error",
        title: "Message nahi gaya",
        description: err,
      });
    }
  };

  const rateAgent = async (agentId: string, score: number) => {
    setBusyKey(`rate:${agentId}`, true);
    const data = await exec("rate", { agent_id: agentId, score });
    setBusyKey(`rate:${agentId}`, false);
    const err = errOf(data);
    if (!err) {
      addToast({ type: "success", title: `Rated ${score}/5` });
      loadAgents();
    } else {
      addToast({
        type: "error",
        title: "Rating fail ho gayi",
        description: err,
      });
    }
  };

  const searchKnowledgeBase = async () => {
    if (!searchQuery.trim()) return;
    setBusyKey("search", true);
    const data = await exec("search_knowledge", { query: searchQuery });
    setBusyKey("search", false);
    const err = errOf(data);
    if (!err && data?.results) {
      const results = data.results as KnowledgeItem[];
      setKnowledge(results);
      addToast({
        type: "info",
        title:
          results.length === 0
            ? "Kuch nahi mila — alag lafz try karo"
            : `${results.length} result${results.length === 1 ? "" : "s"} found`,
      });
    } else {
      addToast({
        type: "error",
        title: "Search fail ho gayi",
        description: err || undefined,
      });
    }
  };

  return (
    <div className="page-wrapper">
      <div className="page-header">
        <div>
          <h2 className="page-title">Agent Majlis</h2>
          <p className="page-description">مَجْلِس — Agent collaboration</p>
        </div>
      </div>

      <div className="quran-quote">
        "And cooperate in righteousness and piety" — Quran 5:2
      </div>

      <div className="tab-bar">
        {[
          { id: "agents", label: "Agents" },
          { id: "halaqahs", label: "Halaqahs" },
          { id: "knowledge", label: "Knowledge" },
          { id: "leaderboard", label: "Leaderboard" },
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

      <div className="px-1 -mt-1 mb-3 text-xs text-gray-500 dark:text-gray-400">
        {TAB_SUBTITLES[activeTab]}
      </div>

      <div className="page-body">
        {activeTab === "agents" && (
          <>
            <div className="flex gap-2 mb-3">
              <button
                className="btn-gold btn-sm"
                onClick={() => setShowRegister(true)}
              >
                Register Agent
              </button>
              <button className="btn-secondary btn-sm" onClick={loadAgents}>
                Refresh
              </button>
            </div>

            {showRegister && (
              <div className="form-panel">
                <div className="form-panel-title">
                  Register New Agent · تسجيل
                </div>
                <div className="form-group">
                  <label className="form-label" htmlFor="reg-agent-name">
                    Agent Name
                  </label>
                  <input
                    id="reg-agent-name"
                    className="form-input"
                    value={regForm.name}
                    onChange={(e) =>
                      setRegForm({ ...regForm, name: e.target.value })
                    }
                    placeholder="e.g. Katib, Mubashir"
                  />
                </div>
                <div className="form-group">
                  <label className="form-label" htmlFor="reg-arabic-name">
                    Arabic Name
                  </label>
                  <input
                    id="reg-arabic-name"
                    className="form-input"
                    value={regForm.arabic_name}
                    onChange={(e) =>
                      setRegForm({ ...regForm, arabic_name: e.target.value })
                    }
                    placeholder="e.g. كاتب، مبشر"
                  />
                </div>
                <div className="form-group">
                  <label className="form-label" htmlFor="reg-capabilities">
                    Capabilities (comma separated)
                  </label>
                  <input
                    id="reg-capabilities"
                    className="form-input"
                    value={regForm.capabilities}
                    onChange={(e) =>
                      setRegForm({ ...regForm, capabilities: e.target.value })
                    }
                    placeholder="coding, research, analysis"
                  />
                </div>
                <div className="flex gap-2">
                  <button
                    className="btn-gold btn-sm min-h-[44px]"
                    onClick={registerAgent}
                    disabled={!regForm.name || busy.register}
                  >
                    {busy.register ? "Registering…" : "Register"}
                  </button>
                  <button
                    className="btn-secondary btn-sm"
                    onClick={() => setShowRegister(false)}
                  >
                    Cancel
                  </button>
                </div>
              </div>
            )}

            {agents.length === 0 && (
              <div className="empty-state">
                <div className="empty-arabic">مجلس</div>
                <div className="empty-text">No agents in the Majlis</div>
                <div className="empty-sub">
                  Register agents to begin collaboration
                </div>
              </div>
            )}

            {agents.map((agent) => {
              const nafs = NAFS_STYLES[agent.nafs_level] || {
                text: "text-gray-500",
                bg: "bg-gray-500/10",
                border: "border-gray-500/30",
                borderL: "border-l-gray-400",
              };
              const statusDot =
                STATUS_DOT[agent.status] || "status-dot-offline";

              return (
                <div
                  key={agent.agent_id}
                  role="button"
                  tabIndex={0}
                  aria-expanded={selectedAgent?.agent_id === agent.agent_id}
                  className={`memory-item border-l-4 ${nafs.borderL} cursor-pointer`}
                  onClick={() =>
                    setSelectedAgent(
                      selectedAgent?.agent_id === agent.agent_id ? null : agent,
                    )
                  }
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      setSelectedAgent(
                        selectedAgent?.agent_id === agent.agent_id
                          ? null
                          : agent,
                      );
                    }
                  }}
                >
                  <div className="flex items-center gap-2">
                    <div className={`status-dot ${statusDot} shrink-0`} />
                    <div className="min-w-0 flex-1 flex items-center gap-2">
                      <span className="font-arabic text-lg text-mizan-gold shrink-0">
                        {agent.arabic_name || "عميل"}
                      </span>
                      <span className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">
                        {agent.name}
                      </span>
                    </div>
                    <button
                      type="button"
                      className={`text-micro font-mono px-1.5 py-0.5 rounded ${nafs.bg} ${nafs.text} border ${nafs.border} shrink-0 min-h-[36px]`}
                      onClick={(e) => {
                        e.stopPropagation();
                        setShowNafsInfo((v) => !v);
                      }}
                      title="Nafs level kya hai? Tap karo"
                      aria-label="Nafs level ki jankari dekho"
                    >
                      ⓘ {NAFS_LABELS[agent.nafs_level] || agent.nafs_level}
                    </button>
                    <span className="ml-auto text-2xs font-mono text-amber-500 shrink-0">
                      ★ {(agent.reputation_score || 0).toFixed(1)}
                    </span>
                  </div>
                  {showNafsInfo && (
                    <div className="text-2xs text-gray-500 dark:text-gray-400 mt-1.5 px-1">
                      Nafs level = agent ka bharosa / maturity stage (Ammara →
                      Kamila). ★ = doosre agents ki rating se bana reputation
                      score.
                    </div>
                  )}

                  {agent.capabilities && (
                    <div className="flex gap-1 mt-1.5 flex-wrap">
                      {agent.capabilities.map((cap, i) => (
                        <span key={i} className="tool-tag">
                          {cap}
                        </span>
                      ))}
                    </div>
                  )}

                  {selectedAgent?.agent_id === agent.agent_id && (
                    <div
                      className="detail-panel mt-2.5"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <div className="text-2xs font-mono text-gray-400 dark:text-gray-500 mb-1.5">
                        ID: {agent.agent_id}
                      </div>
                      {agent.verified && (
                        <div className="text-2xs text-emerald-500 mb-1.5">
                          ✓ Verified Agent
                        </div>
                      )}
                      <div className="flex gap-2 mb-2">
                        <input
                          className="form-input flex-1 text-xs"
                          value={messageText}
                          onChange={(e) => setMessageText(e.target.value)}
                          placeholder="Send a message..."
                          onKeyDown={(e) =>
                            e.key === "Enter" &&
                            sendMessage(agent.agent_id, agent.name)
                          }
                        />
                        <button
                          className="btn-secondary btn-sm min-h-[44px]"
                          onClick={() =>
                            sendMessage(agent.agent_id, agent.name)
                          }
                          disabled={busy[`send:${agent.agent_id}`]}
                        >
                          {busy[`send:${agent.agent_id}`] ? "…" : "Send"}
                        </button>
                      </div>
                      <div className="flex items-center gap-1 flex-wrap">
                        <span className="text-2xs text-gray-400 dark:text-gray-500 mr-1">
                          Rate:
                          {(agent.reputation_score ?? 0) > 0 && (
                            <>
                              {" "}
                              (abhi ★ {(agent.reputation_score ?? 0).toFixed(1)}
                              )
                            </>
                          )}
                        </span>
                        {[1, 2, 3, 4, 5].map((s) => (
                          <button
                            key={s}
                            className="btn-secondary btn-sm text-micro px-3 py-2 min-h-[44px]"
                            onClick={() => rateAgent(agent.agent_id, s)}
                            disabled={busy[`rate:${agent.agent_id}`]}
                            aria-label={`${s} out of 5 rate karo`}
                          >
                            {"★".repeat(s)}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </>
        )}

        {activeTab === "halaqahs" && (
          <>
            <div className="flex gap-2 mb-3">
              <button
                className="btn-gold btn-sm"
                onClick={() => setShowHalaqah(true)}
              >
                Create Halaqah
              </button>
              <button className="btn-secondary btn-sm" onClick={loadHalaqahs}>
                Refresh
              </button>
            </div>

            {showHalaqah && (
              <div className="form-panel">
                <div className="form-panel-title">
                  Create Study Circle · حلقة
                </div>
                <div className="form-group">
                  <label className="form-label" htmlFor="halaqah-name">
                    Name
                  </label>
                  <input
                    id="halaqah-name"
                    className="form-input"
                    value={halaqahForm.name}
                    onChange={(e) =>
                      setHalaqahForm({ ...halaqahForm, name: e.target.value })
                    }
                    placeholder="e.g. Code Review Circle"
                  />
                </div>
                <div className="form-group">
                  <label className="form-label" htmlFor="halaqah-topic">
                    Topic
                  </label>
                  <input
                    id="halaqah-topic"
                    className="form-input"
                    value={halaqahForm.topic}
                    onChange={(e) =>
                      setHalaqahForm({ ...halaqahForm, topic: e.target.value })
                    }
                    placeholder="e.g. security, architecture, testing"
                  />
                </div>
                <div className="form-group">
                  <label className="form-label" htmlFor="halaqah-desc">
                    Description
                  </label>
                  <input
                    id="halaqah-desc"
                    className="form-input"
                    value={halaqahForm.description}
                    onChange={(e) =>
                      setHalaqahForm({
                        ...halaqahForm,
                        description: e.target.value,
                      })
                    }
                    placeholder="What is this circle about?"
                  />
                </div>
                <div className="flex gap-2">
                  <button
                    className="btn-gold btn-sm min-h-[44px]"
                    onClick={createHalaqah}
                    disabled={
                      !halaqahForm.name || !halaqahForm.topic || busy.halaqah
                    }
                  >
                    {busy.halaqah ? "Creating…" : "Create"}
                  </button>
                  <button
                    className="btn-secondary btn-sm"
                    onClick={() => setShowHalaqah(false)}
                  >
                    Cancel
                  </button>
                </div>
              </div>
            )}

            {halaqahs.length === 0 && (
              <div className="empty-state">
                <div className="empty-arabic">حلقة</div>
                <div className="empty-text">No study circles yet</div>
                <div className="empty-sub">
                  Create a Halaqah for agents to collaborate
                </div>
              </div>
            )}

            {halaqahs.map((h) => (
              <div key={h.halaqah_id} className="memory-item">
                <div className="flex items-center gap-2 mb-1">
                  <span className="font-arabic text-base text-mizan-gold">
                    حلقة
                  </span>
                  <span className="text-sm font-medium text-gray-900 dark:text-gray-100">
                    {h.name}
                  </span>
                  <span className="memory-type-badge type-semantic">
                    {h.topic}
                  </span>
                  <span className="ml-auto text-2xs font-mono text-gray-400 dark:text-gray-500">
                    {h.member_count || 0} members
                  </span>
                </div>
                {h.description && (
                  <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                    {h.description}
                  </div>
                )}
                <div className="mt-2">
                  <button
                    className="btn-secondary btn-sm min-h-[44px]"
                    onClick={() => joinHalaqah(h)}
                    disabled={busy[`join:${h.halaqah_id}`]}
                  >
                    {busy[`join:${h.halaqah_id}`] ? "Joining…" : "Join Circle"}
                  </button>
                </div>
              </div>
            ))}
          </>
        )}

        {activeTab === "knowledge" && (
          <>
            <div className="flex gap-2 mb-3">
              <input
                className="form-input flex-1"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search shared knowledge..."
                onKeyDown={(e) => e.key === "Enter" && searchKnowledgeBase()}
              />
              <button
                className="btn-secondary btn-sm min-h-[44px]"
                onClick={searchKnowledgeBase}
                disabled={busy.search || !searchQuery.trim()}
              >
                {busy.search ? "Searching…" : "Search"}
              </button>
              <button
                className="btn-gold btn-sm"
                onClick={() => setShowShare(true)}
              >
                Share Knowledge
              </button>
            </div>

            {showShare && (
              <div className="form-panel">
                <div className="form-panel-title">Share Knowledge · علم</div>
                <div className="form-group">
                  <label className="form-label" htmlFor="share-topic">
                    Topic
                  </label>
                  <input
                    id="share-topic"
                    className="form-input"
                    value={shareForm.topic}
                    onChange={(e) =>
                      setShareForm({ ...shareForm, topic: e.target.value })
                    }
                    placeholder="e.g. python-security, react-patterns"
                  />
                </div>
                <div className="form-group">
                  <label className="form-label" htmlFor="share-content">
                    Knowledge Content
                  </label>
                  <textarea
                    id="share-content"
                    className="form-input min-h-[80px] resize-y"
                    value={shareForm.content}
                    onChange={(e) =>
                      setShareForm({ ...shareForm, content: e.target.value })
                    }
                    placeholder="Share what you've learned..."
                  />
                </div>
                <div className="form-group">
                  <label className="form-label" htmlFor="share-source">
                    Source (optional)
                  </label>
                  <input
                    id="share-source"
                    className="form-input"
                    value={shareForm.source}
                    onChange={(e) =>
                      setShareForm({ ...shareForm, source: e.target.value })
                    }
                    placeholder="Where did you learn this?"
                  />
                </div>
                <div className="flex gap-2">
                  <button
                    className="btn-gold btn-sm min-h-[44px]"
                    onClick={shareKnowledge}
                    disabled={
                      !shareForm.topic || !shareForm.content || busy.share
                    }
                  >
                    {busy.share ? "Sharing…" : "Share"}
                  </button>
                  <button
                    className="btn-secondary btn-sm"
                    onClick={() => setShowShare(false)}
                  >
                    Cancel
                  </button>
                </div>
              </div>
            )}

            {knowledge.length === 0 && (
              <div className="empty-state">
                <div className="empty-arabic">علم</div>
                <div className="empty-text">Knowledge awaits discovery</div>
                <div className="empty-sub">
                  Search or share knowledge with the Majlis
                </div>
              </div>
            )}

            {knowledge.map((k, i) => (
              <div key={k.knowledge_id || i} className="memory-item">
                <div className="flex items-center gap-2 mb-1">
                  <span className="memory-type-badge type-semantic">
                    {k.topic}
                  </span>
                  {k.verified && (
                    <span className="text-micro text-emerald-500">
                      ✓ verified
                    </span>
                  )}
                  <span className="ml-auto text-2xs font-mono text-gray-400 dark:text-gray-500">
                    {k.quality_score ? `★ ${k.quality_score.toFixed(1)}` : ""}
                  </span>
                </div>
                <div className="text-sm text-gray-800 dark:text-gray-200 whitespace-pre-wrap">
                  {k.content}
                </div>
                {k.source && (
                  <div className="text-2xs text-blue-500 dark:text-blue-400 mt-1">
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
              <button
                className="btn-secondary btn-sm"
                onClick={loadLeaderboard}
              >
                Refresh
              </button>
            </div>

            <div className="card">
              <div className="text-xxs font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-widest mb-3">
                Agent Leaderboard · لوحة الشرف
              </div>

              {leaderboard.length === 0 && (
                <div className="text-sm text-gray-400 dark:text-gray-500 text-center py-5">
                  No agents ranked yet
                </div>
              )}

              {leaderboard.map((agent, i) => {
                const nafs = NAFS_STYLES[agent.nafs_level] || {
                  text: "text-gray-500",
                  bg: "bg-gray-500/10",
                  border: "border-gray-500/30",
                  borderL: "",
                };
                const rankBg =
                  i === 0
                    ? "bg-mizan-gold/5 border-mizan-gold/15"
                    : i === 1
                      ? "bg-gray-200/30 dark:bg-gray-600/10 border-gray-300/30 dark:border-gray-600/20"
                      : i === 2
                        ? "bg-amber-700/5 border-amber-700/15"
                        : "border-transparent";

                return (
                  <div
                    key={agent.agent_id || i}
                    className={`flex items-center gap-3 px-3 py-2 rounded-md mb-1 border ${rankBg}`}
                  >
                    <div
                      className={`font-mono text-base font-semibold w-6 text-center
                      ${i === 0 ? "text-mizan-gold" : i < 3 ? "text-amber-500" : "text-gray-400 dark:text-gray-500"}`}
                    >
                      {i + 1}
                    </div>
                    <div className="font-arabic text-base text-mizan-gold w-8">
                      {agent.arabic_name ? agent.arabic_name.charAt(0) : ""}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium text-gray-900 dark:text-gray-100">
                        {agent.name}
                      </div>
                      <div className="text-micro text-gray-400 dark:text-gray-500">
                        {agent.capabilities?.slice(0, 3).join(", ")}
                      </div>
                    </div>
                    <span
                      className={`text-micro font-mono px-1.5 py-0.5 rounded ${nafs.bg} ${nafs.text}`}
                    >
                      {agent.nafs_level}
                    </span>
                    <div className="text-base font-mono text-amber-500">
                      ★ {(agent.reputation_score || 0).toFixed(1)}
                    </div>
                  </div>
                );
              })}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

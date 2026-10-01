/**
 * Skills Page (Hikmah - حِكْمَة - Wisdom)
 * Skills management and MizanHub browser
 */

import { useState, useEffect, useCallback } from "react";
import { PageProps, Skill } from "../types";
import { SkeletonCard } from "../components/Skeleton";
import { useToast } from "../components/Toast";

/** Readable names for agent-type slugs shown under "Best For". */
const AGENT_TYPE_LABELS: Record<string, string> = {
  browser: "Browser",
  mubashir: "Mubashir",
  research: "Research",
  general: "General",
  code: "Code",
  katib: "Katib",
  communication: "Communication",
};

const BUILTIN_SKILLS: Skill[] = [
  {
    name: "web_browse",
    display: "Web Browse",
    arabic: "تصفح",
    description:
      "Browse websites and extract content. Supports fetching pages, following links, and extracting structured data from HTML.",
    category: "Research",
    installed: true,
    version: "1.0.0",
    permissions: ["network_access"],
  },
  {
    name: "data_analysis",
    display: "Data Analysis",
    arabic: "تحليل",
    description:
      "Analyze CSV, JSON, and structured data. Compute statistics, generate summaries, and detect patterns in datasets.",
    category: "Analysis",
    installed: true,
    version: "1.0.0",
    permissions: ["file_read"],
  },
  {
    name: "code_exec",
    display: "Code Execution",
    arabic: "تنفيذ",
    description:
      "Execute Python code in a sandboxed environment. Run scripts, install packages, and process data safely.",
    category: "Development",
    installed: true,
    version: "1.0.0",
    permissions: ["sandbox_exec"],
  },
  {
    name: "file_manager",
    display: "File Manager",
    arabic: "ملفات",
    description:
      "Read, write, list, and manage files on the system. Supports creating directories and file operations.",
    category: "System",
    installed: true,
    version: "1.0.0",
    permissions: ["file_read", "file_write"],
  },
  {
    name: "calendar",
    display: "Calendar",
    arabic: "تقويم",
    description:
      "Schedule and manage events, reminders, and appointments. Integrates with external calendar services.",
    category: "Productivity",
    installed: false,
    version: "1.0.0",
    permissions: ["calendar_access"],
  },
];

const CATEGORY_STYLES: Record<
  string,
  { text: string; bg: string; border: string }
> = {
  Research: {
    text: "text-blue-500",
    bg: "bg-blue-500/10",
    border: "border-blue-500/30",
  },
  Analysis: {
    text: "text-amber-500",
    bg: "bg-amber-500/10",
    border: "border-amber-500/30",
  },
  Development: {
    text: "text-emerald-500",
    bg: "bg-emerald-500/10",
    border: "border-emerald-500/30",
  },
  System: {
    text: "text-red-500",
    bg: "bg-red-500/10",
    border: "border-red-500/30",
  },
  Productivity: {
    text: "text-violet-500",
    bg: "bg-violet-500/10",
    border: "border-violet-500/30",
  },
};

const SKILL_AGENT_AFFINITY: Record<string, { types: string[]; note: string }> =
  {
    web_browse: {
      types: ["browser", "mubashir"],
      note: "Primary skill for Browser agents — enables web scraping, page navigation, and content extraction.",
    },
    data_analysis: {
      types: ["research", "general"],
      note: "Used by Research and General agents to analyze structured data and generate insights.",
    },
    code_exec: {
      types: ["code", "katib"],
      note: "Core skill for Code agents — provides sandboxed Python execution.",
    },
    file_manager: {
      types: ["general", "code"],
      note: "Available to General and Code agents for reading and writing files.",
    },
    calendar: {
      types: ["general", "communication"],
      note: "Useful for General and Communication agents to manage schedules.",
    },
    kitab_notebook: {
      types: ["code", "research"],
      note: "Interactive notebook execution for Code and Research agents.",
    },
    raqib_scanner: {
      types: ["code", "general"],
      note: "Security scanning for Code agents to detect vulnerabilities.",
    },
    sahab_cloud: {
      types: ["general", "code"],
      note: "Cloud integration (GitHub, Docker) for General and Code agents.",
    },
    majlis_social: {
      types: ["communication"],
      note: "Agent social network for Communication agents.",
    },
  };

const PERMISSION_LABELS: Record<string, string> = {
  network_access: "Internet Access",
  file_read: "Read Files",
  file_write: "Write Files",
  sandbox_exec: "Code Sandbox",
  calendar_access: "Calendar",
  shell_git: "Git Commands",
  shell_docker: "Docker",
  agent_manage: "Manage Agents",
  plugin_manage: "Manage Plugins",
};

export default function SkillsPage({ api, addTerminalLine }: PageProps) {
  const { addToast } = useToast();
  const [skills, setSkills] = useState<Skill[]>(BUILTIN_SKILLS);
  const [activeTab, setActiveTab] = useState<string>("installed");
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(true);
  const [expandedSkill, setExpandedSkill] = useState<string | null>(null);
  const [pendingSkill, setPendingSkill] = useState<string | null>(null);

  const loadSkills = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.get("/skills");
      if ((data.skills as Skill[] | undefined)?.length) {
        setSkills(data.skills as Skill[]);
      }
    } catch (err) {
      console.error("Failed to fetch skills, using defaults:", err);
    } finally {
      setLoading(false);
    }
  }, [api]);

  useEffect(() => {
    loadSkills();
  }, [loadSkills]);

  const installSkill = async (skillName: string) => {
    setPendingSkill(skillName);
    try {
      await api.post("/skills/install", { name: skillName });
      addToast({
        type: "success",
        title: "Added — find it under Added",
      });
      addTerminalLine?.(`Skill added: ${skillName}`, "gold");
      setSkills((prev) =>
        prev.map((s) => (s.name === skillName ? { ...s, installed: true } : s)),
      );
    } catch (e) {
      addToast({
        type: "error",
        title: (e as Error).message || "Add nahi ho paya",
      });
      addTerminalLine?.(`Failed to add skill: ${skillName}`, "error");
    } finally {
      setPendingSkill(null);
    }
  };

  const uninstallSkill = async (skillName: string) => {
    if (!window.confirm(`"${skillName}" skill remove kar dun?`)) return;
    setPendingSkill(skillName);
    try {
      await api.post("/skills/uninstall", { name: skillName });
      addToast({ type: "success", title: "Skill remove ho gaya" });
      addTerminalLine?.(`Skill removed: ${skillName}`, "gold");
      setSkills((prev) =>
        prev.map((s) =>
          s.name === skillName ? { ...s, installed: false } : s,
        ),
      );
    } catch (e) {
      addToast({
        type: "error",
        title: (e as Error).message || "Remove nahi ho paya",
      });
      addTerminalLine?.(`Failed to remove skill: ${skillName}`, "error");
    } finally {
      setPendingSkill(null);
    }
  };

  const filteredSkills = skills.filter((s) => {
    const matchesSearch =
      !searchQuery ||
      s.display.toLowerCase().includes(searchQuery.toLowerCase()) ||
      s.description.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesTab =
      activeTab === "all" ||
      (activeTab === "installed" && s.installed) ||
      (activeTab === "available" && !s.installed);
    return matchesSearch && matchesTab;
  });

  return (
    <div className="page-wrapper">
      <div className="page-header">
        <div>
          <h2 className="page-title">Skills</h2>
          <p className="page-description">
            حِكْمَة (Hikmah) — Capabilities management
          </p>
        </div>
        <input
          className="form-input w-full sm:w-48"
          placeholder="Search skills..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
        />
      </div>

      <div className="quran-quote">
        "He gives wisdom (Hikmah) to whom He wills, and whoever has been given
        wisdom has certainly been given much good" — Quran 2:269
      </div>

      <div className="tab-bar">
        {[
          { id: "installed", label: "Added" },
          { id: "available", label: "Available" },
          { id: "all", label: "All Skills" },
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

      {loading && (
        <div className="p-5" aria-live="polite">
          <div className="card-grid">
            <SkeletonCard count={4} />
          </div>
        </div>
      )}

      <div className="flex-1 overflow-y-auto p-5">
        <div className="card-grid">
          {filteredSkills.map((skill) => {
            const cat = CATEGORY_STYLES[skill.category] || {
              text: "text-mizan-gold",
              bg: "bg-mizan-gold/10",
              border: "border-mizan-gold/30",
            };
            const isExpanded = expandedSkill === skill.name;
            const affinity = SKILL_AGENT_AFFINITY[skill.name];

            return (
              <div
                key={skill.name}
                role="button"
                tabIndex={0}
                aria-expanded={isExpanded}
                className={`card cursor-pointer transition-all ${skill.installed ? cat.border : ""} ${isExpanded ? "ring-2 ring-mizan-gold/30" : ""}`}
                onClick={() => setExpandedSkill(isExpanded ? null : skill.name)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    setExpandedSkill(isExpanded ? null : skill.name);
                  }
                }}
              >
                <div className="flex items-start gap-3 mb-2.5">
                  <div
                    className={`w-9 h-9 rounded-lg ${cat.bg} border ${cat.border} flex items-center justify-center font-arabic text-sm ${cat.text} shrink-0`}
                  >
                    {skill.arabic}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                      {skill.display}
                    </div>
                    <div className="text-xs text-gray-500 dark:text-gray-400 mt-0.5 leading-snug">
                      {isExpanded
                        ? skill.description
                        : skill.description.split(".")[0] + "."}
                    </div>
                  </div>
                  <svg
                    viewBox="0 0 20 20"
                    fill="currentColor"
                    aria-hidden="true"
                    className={`w-4 h-4 text-gray-400 shrink-0 transition-transform ${isExpanded ? "rotate-180" : ""}`}
                  >
                    <path
                      fillRule="evenodd"
                      d="M5.23 7.21a.75.75 0 011.06.02L10 11.168l3.71-3.938a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z"
                      clipRule="evenodd"
                    />
                  </svg>
                </div>

                <div className="flex items-center gap-1.5 mb-2.5">
                  <span
                    className={`text-micro font-mono px-1.5 py-0.5 rounded ${cat.bg} border ${cat.border} ${cat.text} uppercase tracking-wider`}
                  >
                    {skill.category}
                  </span>
                  <span className="text-micro font-mono text-gray-400 dark:text-gray-500">
                    v{skill.version}
                  </span>
                  {skill.installed && (
                    <span className="ml-auto text-micro font-mono text-emerald-500">
                      INSTALLED
                    </span>
                  )}
                </div>

                {/* Collapsed: show permission tags */}
                {!isExpanded && (
                  <div className="flex flex-wrap gap-1 mb-3">
                    {(skill.permissions || []).map((perm) => (
                      <span key={perm} className="tool-tag">
                        {PERMISSION_LABELS[perm] || perm}
                      </span>
                    ))}
                  </div>
                )}

                {/* Expanded detail section */}
                {isExpanded && (
                  <div className="mb-3 space-y-3">
                    {/* Permissions with readable labels */}
                    <div>
                      <div className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-1.5">
                        Required Permissions
                      </div>
                      <div className="flex flex-wrap gap-1">
                        {(skill.permissions || []).map((perm) => (
                          <span
                            key={perm}
                            className={`text-xs px-2 py-1 rounded-lg ${cat.bg} border ${cat.border} ${cat.text}`}
                          >
                            {PERMISSION_LABELS[perm] || perm}
                          </span>
                        ))}
                      </div>
                    </div>

                    {/* Agent affinity */}
                    {affinity && (
                      <div>
                        <div className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-1.5">
                          Best For
                        </div>
                        <p className="text-xs text-gray-600 dark:text-gray-300 leading-relaxed">
                          {affinity.note}
                        </p>
                        <div className="flex flex-wrap gap-1 mt-1.5">
                          {affinity.types.map((type) => (
                            <span
                              key={type}
                              className="text-xs px-1.5 py-0.5 bg-mizan-gold/10 border border-mizan-gold/20 rounded text-mizan-gold font-mono"
                            >
                              {AGENT_TYPE_LABELS[type] || type}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}

                <button
                  className={`w-full ${skill.installed ? "btn-danger" : "btn-gold"} btn-sm min-h-[44px]`}
                  disabled={pendingSkill === skill.name}
                  onClick={(e) => {
                    e.stopPropagation();
                    skill.installed
                      ? uninstallSkill(skill.name)
                      : installSkill(skill.name);
                  }}
                >
                  {pendingSkill === skill.name
                    ? skill.installed
                      ? "Removing…"
                      : "Adding…"
                    : skill.installed
                      ? "Remove"
                      : "Add"}
                </button>
              </div>
            );
          })}

          {filteredSkills.length === 0 && (
            <div className="empty-state col-span-full">
              <div className="empty-arabic">حكمة</div>
              <div className="empty-text">No skills in this view yet</div>
              <div className="empty-sub">
                {searchQuery
                  ? "Try a different search"
                  : "Nayi skills install karke yahan dekho"}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

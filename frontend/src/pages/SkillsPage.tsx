/**
 * Skills Page (Hikmah - حِكْمَة - Wisdom)
 * Skills management and MizanHub browser
 */

import { useState, useEffect, useCallback } from "react";
import { PageProps, Skill } from "../types";

const BUILTIN_SKILLS: Skill[] = [
  {
    name: "web_browse",
    display: "Web Browse",
    arabic: "تصفح",
    description: "Browse websites and extract content",
    category: "Research",
    installed: true,
    version: "1.0.0",
    permissions: ["network_access"],
  },
  {
    name: "data_analysis",
    display: "Data Analysis",
    arabic: "تحليل",
    description: "Analyze CSV, JSON, and structured data",
    category: "Analysis",
    installed: true,
    version: "1.0.0",
    permissions: ["file_read"],
  },
  {
    name: "code_exec",
    display: "Code Execution",
    arabic: "تنفيذ",
    description: "Execute code in sandboxed environment",
    category: "Development",
    installed: true,
    version: "1.0.0",
    permissions: ["sandbox_exec"],
  },
  {
    name: "file_manager",
    display: "File Manager",
    arabic: "ملفات",
    description: "Read, write, and manage files",
    category: "System",
    installed: true,
    version: "1.0.0",
    permissions: ["file_read", "file_write"],
  },
  {
    name: "calendar",
    display: "Calendar",
    arabic: "تقويم",
    description: "Schedule and manage events",
    category: "Productivity",
    installed: false,
    version: "1.0.0",
    permissions: ["calendar_access"],
  },
];

const CATEGORY_COLORS: Record<string, string> = {
  Research: "#3b82f6",
  Analysis: "#f59e0b",
  Development: "#10b981",
  System: "#ef4444",
  Productivity: "#8b5cf6",
};

export default function SkillsPage({ api, addTerminalLine }: PageProps) {
  const [skills, setSkills] = useState<Skill[]>(BUILTIN_SKILLS);
  const [activeTab, setActiveTab] = useState<string>("installed");
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(true);

  const loadSkills = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.get("/skills");
      if ((data.skills as Skill[] | undefined)?.length) {
        setSkills(data.skills as Skill[]);
      }
    } catch (err) {
      console.error("Failed to fetch skills, using defaults:", err);
      // Use defaults (BUILTIN_SKILLS already set)
    } finally {
      setLoading(false);
    }
  }, [api]);

  useEffect(() => {
    loadSkills();
  }, [loadSkills]);

  const installSkill = async (skillName: string) => {
    try {
      await api.post("/skills/install", { name: skillName });
      addTerminalLine?.(`Skill installed: ${skillName}`, "gold");
      setSkills((prev) =>
        prev.map((s) => (s.name === skillName ? { ...s, installed: true } : s)),
      );
    } catch {
      addTerminalLine?.(`Failed to install skill: ${skillName}`, "error");
    }
  };

  const uninstallSkill = async (skillName: string) => {
    try {
      await api.post("/skills/uninstall", { name: skillName });
      addTerminalLine?.(`Skill uninstalled: ${skillName}`, "gold");
      setSkills((prev) =>
        prev.map((s) => (s.name === skillName ? { ...s, installed: false } : s)),
      );
    } catch {
      addTerminalLine?.(`Failed to uninstall skill: ${skillName}`, "error");
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
    <>
      <div className="flex items-center justify-between px-5 py-3 border-b border-gray-200 dark:border-zinc-800">
        <h2 className="page-title">Skills · حِكْمَة (Hikmah)</h2>
        <div className="flex gap-2">
          <input
            className="input w-[200px] text-sm px-2.5 py-1.5"
            placeholder="Search skills..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>
      </div>

      <div className="px-4 pb-2 pt-1 text-xs text-gray-500 dark:text-gray-400 italic">
        "He gives wisdom (Hikmah) to whom He wills, and whoever has been given wisdom has
        certainly been given much good" — Quran 2:269
      </div>

      {/* Tabs */}
      <div className="tab-bar">
        {[
          { id: "installed", label: "Installed" },
          { id: "available", label: "Available" },
          { id: "all", label: "All Skills" },
        ].map((tab) => (
          <div
            key={tab.id}
            className={`tab ${activeTab === tab.id ? "active" : ""}`}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
          </div>
        ))}
      </div>

      {loading && (
        <div className="p-4 text-xs text-gray-500 dark:text-gray-400 font-mono">
          Loading skills...
        </div>
      )}

      <div className="grid grid-cols-[repeat(auto-fill,minmax(300px,1fr))] gap-3 p-4 overflow-auto flex-1">
        {filteredSkills.map((skill) => {
          const catColor = CATEGORY_COLORS[skill.category] || "#c9a227";

          return (
            <div
              key={skill.name}
              className="card relative"
              style={{ borderColor: skill.installed ? `${catColor}40` : undefined }}
            >
              <div className="flex items-start gap-3 mb-2.5">
                <div
                  className="w-9 h-9 rounded-lg flex items-center justify-center font-serif text-sm shrink-0"
                  style={{
                    background: `${catColor}15`,
                    border: `1px solid ${catColor}30`,
                    color: catColor,
                  }}
                >
                  {skill.arabic}
                </div>
                <div className="flex-1">
                  <div className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                    {skill.display}
                  </div>
                  <div className="text-xs text-gray-500 dark:text-gray-400 mt-0.5 leading-snug">
                    {skill.description}
                  </div>
                </div>
              </div>

              <div className="flex items-center gap-1.5 mb-2.5">
                <span
                  className="text-[9px] font-mono px-1.5 rounded uppercase tracking-wide"
                  style={{
                    background: `${catColor}15`,
                    border: `1px solid ${catColor}30`,
                    color: catColor,
                  }}
                >
                  {skill.category}
                </span>
                <span className="text-[9px] font-mono text-gray-500 dark:text-gray-400">
                  v{skill.version}
                </span>
                {skill.installed && (
                  <span className="ml-auto text-[9px] font-mono text-emerald-500">
                    INSTALLED
                  </span>
                )}
              </div>

              <div className="flex flex-wrap gap-1 mb-2.5">
                {(skill.permissions || []).map((perm) => (
                  <span key={perm} className="tool-tag">
                    {perm}
                  </span>
                ))}
              </div>

              <button
                className={`${skill.installed ? "btn-danger" : "btn-primary"} w-full justify-center text-[10px]`}
                onClick={() =>
                  skill.installed
                    ? uninstallSkill(skill.name)
                    : installSkill(skill.name)
                }
              >
                {skill.installed ? "Uninstall" : "Install"}
              </button>
            </div>
          );
        })}

        {filteredSkills.length === 0 && (
          <div className="empty-state col-span-full">
            <div className="empty-arabic">حكمة</div>
            <div className="empty-text">No skills found</div>
            <div className="empty-sub">Search or browse the MizanHub registry</div>
          </div>
        )}
      </div>
    </>
  );
}

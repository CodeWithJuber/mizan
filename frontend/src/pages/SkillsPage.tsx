/**
 * Skills Page (Hikmah - حِكْمَة - Wisdom)
 * Skills management and MizanHub browser
 */

import { useState, useEffect, useCallback } from "react";
import { PageProps, Skill } from "../types";

const BUILTIN_SKILLS: Skill[] = [
  { name: "web_browse", display: "Web Browse", arabic: "تصفح", description: "Browse websites and extract content", category: "Research", installed: true, version: "1.0.0", permissions: ["network_access"] },
  { name: "data_analysis", display: "Data Analysis", arabic: "تحليل", description: "Analyze CSV, JSON, and structured data", category: "Analysis", installed: true, version: "1.0.0", permissions: ["file_read"] },
  { name: "code_exec", display: "Code Execution", arabic: "تنفيذ", description: "Execute code in sandboxed environment", category: "Development", installed: true, version: "1.0.0", permissions: ["sandbox_exec"] },
  { name: "file_manager", display: "File Manager", arabic: "ملفات", description: "Read, write, and manage files", category: "System", installed: true, version: "1.0.0", permissions: ["file_read", "file_write"] },
  { name: "calendar", display: "Calendar", arabic: "تقويم", description: "Schedule and manage events", category: "Productivity", installed: false, version: "1.0.0", permissions: ["calendar_access"] },
];

const CATEGORY_STYLES: Record<string, { text: string; bg: string; border: string }> = {
  Research: { text: "text-blue-500", bg: "bg-blue-500/10", border: "border-blue-500/30" },
  Analysis: { text: "text-amber-500", bg: "bg-amber-500/10", border: "border-amber-500/30" },
  Development: { text: "text-emerald-500", bg: "bg-emerald-500/10", border: "border-emerald-500/30" },
  System: { text: "text-red-500", bg: "bg-red-500/10", border: "border-red-500/30" },
  Productivity: { text: "text-violet-500", bg: "bg-violet-500/10", border: "border-violet-500/30" },
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
    <div className="page-wrapper">
      <div className="page-header">
        <div>
          <h2 className="page-title">Skills</h2>
          <p className="page-description">حِكْمَة (Hikmah) — Capabilities management</p>
        </div>
        <input
          className="form-input w-48"
          placeholder="Search skills..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
        />
      </div>

      <div className="quran-quote">
        "He gives wisdom (Hikmah) to whom He wills, and whoever has been given wisdom has
        certainly been given much good" — Quran 2:269
      </div>

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

      {loading && <div className="loading-text">Loading skills...</div>}

      <div className="flex-1 overflow-y-auto p-5">
        <div className="card-grid">
          {filteredSkills.map((skill) => {
            const cat = CATEGORY_STYLES[skill.category] || { text: "text-mizan-gold", bg: "bg-mizan-gold/10", border: "border-mizan-gold/30" };

            return (
              <div key={skill.name} className={`card ${skill.installed ? cat.border : ""}`}>
                <div className="flex items-start gap-3 mb-2.5">
                  <div className={`w-9 h-9 rounded-lg ${cat.bg} border ${cat.border} flex items-center justify-center font-arabic text-sm ${cat.text} shrink-0`}>
                    {skill.arabic}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                      {skill.display}
                    </div>
                    <div className="text-xs text-gray-500 dark:text-gray-400 mt-0.5 leading-snug">
                      {skill.description}
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-1.5 mb-2.5">
                  <span className={`text-micro font-mono px-1.5 py-0.5 rounded ${cat.bg} border ${cat.border} ${cat.text} uppercase tracking-wider`}>
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

                <div className="flex flex-wrap gap-1 mb-3">
                  {(skill.permissions || []).map((perm) => (
                    <span key={perm} className="tool-tag">{perm}</span>
                  ))}
                </div>

                <button
                  className={`w-full ${skill.installed ? "btn-danger" : "btn-gold"} btn-sm`}
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
      </div>
    </div>
  );
}

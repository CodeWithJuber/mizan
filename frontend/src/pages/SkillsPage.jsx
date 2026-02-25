/**
 * Skills Page (Hikmah - حِكْمَة - Wisdom)
 * Skills management and MizanHub browser
 */

import { useState, useEffect, useCallback } from "react";

const BUILTIN_SKILLS = [
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

const CATEGORY_COLORS = {
  Research: "#3b82f6",
  Analysis: "#f59e0b",
  Development: "#10b981",
  System: "#ef4444",
  Productivity: "#8b5cf6",
};

export default function SkillsPage({ api, addTerminalLine }) {
  const [skills, setSkills] = useState(BUILTIN_SKILLS);
  const [activeTab, setActiveTab] = useState("installed");
  const [searchQuery, setSearchQuery] = useState("");

  const loadSkills = useCallback(async () => {
    try {
      const data = await api.get("/skills");
      if (data.skills?.length) {
        setSkills(data.skills);
      }
    } catch {
      // Use defaults
    }
  }, [api]);

  useEffect(() => {
    loadSkills();
  }, [loadSkills]);

  const installSkill = async (skillName) => {
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

  const uninstallSkill = async (skillName) => {
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
      <div className="panel-header">
        <div className="panel-title">Skills · حِكْمَة (Hikmah)</div>
        <div style={{ display: "flex", gap: 8 }}>
          <input
            className="form-input"
            style={{ width: 200, padding: "5px 10px" }}
            placeholder="Search skills..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>
      </div>

      <div
        style={{
          padding: "4px 16px 8px",
          fontSize: 11,
          color: "var(--text-muted)",
          fontStyle: "italic",
        }}
      >
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

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))",
          gap: 12,
          padding: 16,
          overflow: "auto",
          flex: 1,
        }}
      >
        {filteredSkills.map((skill) => {
          const catColor = CATEGORY_COLORS[skill.category] || "#c9a227";

          return (
            <div
              key={skill.name}
              style={{
                background:
                  "linear-gradient(135deg, rgba(15,32,48,0.9) 0%, rgba(10,21,32,0.9) 100%)",
                border: `1px solid ${skill.installed ? catColor + "40" : "var(--border)"}`,
                borderRadius: 10,
                padding: 16,
                position: "relative",
              }}
            >
              <div
                style={{
                  display: "flex",
                  alignItems: "flex-start",
                  gap: 12,
                  marginBottom: 10,
                }}
              >
                <div
                  style={{
                    width: 36,
                    height: 36,
                    borderRadius: 8,
                    background: `${catColor}15`,
                    border: `1px solid ${catColor}30`,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontFamily: "Georgia, serif",
                    fontSize: 14,
                    color: catColor,
                    flexShrink: 0,
                  }}
                >
                  {skill.arabic}
                </div>
                <div style={{ flex: 1 }}>
                  <div
                    style={{
                      fontFamily: "var(--font-display)",
                      fontSize: 13,
                      color: "var(--text-primary)",
                      fontWeight: 600,
                    }}
                  >
                    {skill.display}
                  </div>
                  <div
                    style={{
                      fontSize: 11,
                      color: "var(--text-muted)",
                      marginTop: 2,
                      lineHeight: 1.4,
                    }}
                  >
                    {skill.description}
                  </div>
                </div>
              </div>

              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 6,
                  marginBottom: 10,
                }}
              >
                <span
                  style={{
                    fontSize: 9,
                    fontFamily: "var(--font-mono)",
                    padding: "1px 6px",
                    borderRadius: 3,
                    background: `${catColor}15`,
                    border: `1px solid ${catColor}30`,
                    color: catColor,
                    textTransform: "uppercase",
                    letterSpacing: "0.1em",
                  }}
                >
                  {skill.category}
                </span>
                <span
                  style={{
                    fontSize: 9,
                    fontFamily: "var(--font-mono)",
                    color: "var(--text-muted)",
                  }}
                >
                  v{skill.version}
                </span>
                {skill.installed && (
                  <span
                    style={{
                      marginLeft: "auto",
                      fontSize: 9,
                      fontFamily: "var(--font-mono)",
                      color: "var(--emerald)",
                    }}
                  >
                    INSTALLED
                  </span>
                )}
              </div>

              {/* Permissions */}
              <div
                style={{
                  display: "flex",
                  flexWrap: "wrap",
                  gap: 4,
                  marginBottom: 10,
                }}
              >
                {(skill.permissions || []).map((perm) => (
                  <span key={perm} className="tool-tag">
                    {perm}
                  </span>
                ))}
              </div>

              <button
                className={`btn ${skill.installed ? "danger" : "primary"}`}
                style={{ width: "100%", justifyContent: "center", fontSize: 10 }}
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
          <div className="empty-state" style={{ gridColumn: "1/-1" }}>
            <div className="empty-arabic">حكمة</div>
            <div className="empty-text">No skills found</div>
            <div className="empty-sub">Search or browse the MizanHub registry</div>
          </div>
        )}
      </div>
    </>
  );
}

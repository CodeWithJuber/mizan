import { useState, useCallback } from "react";
import type { Agent } from "../types";
import { Icons } from "./Icons";
import { NAFS_LEVELS } from "./AgentCard";

interface NavItem {
  id: string;
  label: string;
  icon: React.ReactNode;
  desc: string;
}

interface NavSection {
  label: string;
  items: NavItem[];
}

interface SidebarProps {
  navSections: NavSection[];
  activeTab: string;
  setActiveTab: (tab: string) => void;
  selectedAgent: Agent | null;
}

export function Sidebar({
  navSections,
  activeTab,
  setActiveTab,
  selectedAgent,
}: SidebarProps) {
  const [collapsed, setCollapsed] = useState(() => {
    return localStorage.getItem("mizan_sidebar_collapsed") === "true";
  });

  const toggleCollapsed = useCallback(() => {
    setCollapsed((prev) => {
      const next = !prev;
      localStorage.setItem("mizan_sidebar_collapsed", String(next));
      return next;
    });
  }, []);

  return (
    <nav
      className={`${collapsed ? "w-16" : "w-64"} shrink-0 bg-white/60 dark:bg-mizan-dark/40 backdrop-blur-md border-r border-white/50 dark:border-white/5 flex flex-col overflow-y-auto z-sticky shadow-[4px_0_24px_rgba(0,0,0,0.02)] pt-2 relative transition-[width] duration-200 hidden md:flex`}
      role="navigation"
      aria-label="Main navigation"
    >
      {/* Collapse toggle */}
      <button
        onClick={toggleCollapsed}
        className="absolute top-3 right-2 p-1 rounded-md text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-zinc-800 transition-colors focus-ring cursor-pointer z-10"
        aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
      >
        <svg
          viewBox="0 0 20 20"
          fill="currentColor"
          className={`w-4 h-4 transition-transform ${collapsed ? "rotate-180" : ""}`}
          aria-hidden="true"
        >
          <path
            fillRule="evenodd"
            d="M12.79 5.23a.75.75 0 01-.02 1.06L8.832 10l3.938 3.71a.75.75 0 11-1.04 1.08l-4.5-4.25a.75.75 0 010-1.08l4.5-4.25a.75.75 0 011.06.02z"
            clipRule="evenodd"
          />
        </svg>
      </button>

      <div className="flex-1 py-2">
        {navSections.map((section) => (
          <div key={section.label} className="px-2 mb-1" role="group" aria-label={section.label}>
            {!collapsed && (
              <h3 className="text-sm font-semibold uppercase tracking-widest text-gray-400 dark:text-gray-500 px-3 py-2">
                {section.label}
              </h3>
            )}
            {collapsed && <div className="h-2" />}
            {section.items.map((item) => {
              const isActive = activeTab === item.id;
              return (
                <button
                  key={item.id}
                  className={`w-full flex items-center ${collapsed ? "justify-center" : "gap-3"} ${collapsed ? "px-0 py-2.5" : "px-3 py-2.5"} rounded-xl text-left transition-all duration-200 mb-0.5 focus-ring cursor-pointer ${
                    isActive
                      ? "bg-mizan-gold/10 text-mizan-gold border-l-2 border-mizan-gold"
                      : "text-gray-600 dark:text-gray-400 hover:bg-white/60 dark:hover:bg-mizan-dark-surface/50 hover:text-gray-900 dark:hover:text-gray-200 border-l-2 border-transparent"
                  }`}
                  onClick={() => setActiveTab(item.id)}
                  title={collapsed ? item.label : item.desc}
                  aria-current={isActive ? "page" : undefined}
                >
                  <span className="shrink-0">{item.icon}</span>
                  {!collapsed && (
                    <span className="text-sm truncate">{item.label}</span>
                  )}
                </button>
              );
            })}
          </div>
        ))}
      </div>

      {/* Active agent footer */}
      {selectedAgent && !collapsed && (
        <div className="px-4 py-4 border-t border-white/50 dark:border-white/10 mt-auto bg-gradient-to-t from-white/40 dark:from-mizan-dark-surface/40 to-transparent transition-all">
          <div className="text-xs uppercase tracking-widest text-mizan-gold/80 font-semibold mb-2 flex items-center gap-2">
            <Icons.Agent /> Active Agent
          </div>
          <div
            className="flex items-center gap-3 bg-white/50 dark:bg-mizan-dark-surface/50 p-2.5 rounded-xl border border-white/50 dark:border-white/5 shadow-sm hover:shadow hover:-translate-y-0.5 transition-all group cursor-pointer"
            onClick={() => setActiveTab("agents")}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                setActiveTab("agents");
              }
            }}
          >
            <div className="w-8 h-8 rounded-full bg-gradient-to-br from-mizan-gold to-orange-400 border-2 border-white dark:border-mizan-dark-surface shadow-sm flex items-center justify-center text-white text-xs font-bold group-hover:scale-105 transition-transform">
              {selectedAgent.name[0]?.toUpperCase()}
            </div>
            <div className="min-w-0 flex-1">
              <div className="text-sm font-semibold text-gray-900 dark:text-gray-100 truncate group-hover:text-mizan-gold transition-colors">
                {selectedAgent.name}
              </div>
              <div className="text-xs text-gray-500 dark:text-gray-400 font-mono truncate">
                Level {selectedAgent.nafs_level} —{" "}
                {NAFS_LEVELS[selectedAgent.nafs_level]?.latin}
              </div>
            </div>
          </div>
        </div>
      )}
    </nav>
  );
}

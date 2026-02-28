import type { Agent } from "../types";

export const NAFS_LEVELS: Record<
  number,
  { latin: string; color: string; desc: string }
> = {
  1: { latin: "Ammara", color: "#ef4444", desc: "Raw potential" },
  2: { latin: "Lawwama", color: "#f97316", desc: "Self-correcting" },
  3: { latin: "Mulhama", color: "#f59e0b", desc: "Inspired" },
  4: { latin: "Mutmainna", color: "#84cc16", desc: "Tranquil" },
  5: { latin: "Radiya", color: "#10b981", desc: "Content" },
  6: { latin: "Mardiyya", color: "#06b6d4", desc: "Pleasing" },
  7: { latin: "Kamila", color: "#a78bfa", desc: "Perfected" },
};

const STATE_COLORS: Record<string, string> = {
  resting: "bg-gray-100 dark:bg-zinc-700/30 text-gray-500 dark:text-gray-400",
  thinking: "bg-blue-100 dark:bg-blue-500/15 text-blue-600 dark:text-blue-400",
  acting:
    "bg-amber-100 dark:bg-amber-500/15 text-amber-600 dark:text-amber-400",
  learning:
    "bg-emerald-100 dark:bg-emerald-500/15 text-emerald-600 dark:text-emerald-400",
  error: "bg-red-100 dark:bg-red-500/15 text-red-600 dark:text-red-400",
};

interface AgentCardProps {
  agent: Agent;
  selected: boolean;
  onClick: () => void;
}

export function AgentCard({ agent, selected, onClick }: AgentCardProps) {
  const nafs = NAFS_LEVELS[agent.nafs_level] || NAFS_LEVELS[1];

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      onClick();
    }
  };

  return (
    <div
      className={`card-hover cursor-pointer ${selected ? "ring-2 ring-mizan-gold/40 border-mizan-gold/30" : ""}`}
      onClick={onClick}
      onKeyDown={handleKeyDown}
      role="button"
      tabIndex={0}
      aria-selected={selected}
      aria-label={`Agent ${agent.name}, ${nafs.desc}, ${agent.state}`}
    >
      <div className="flex items-start gap-3 mb-3">
        <div className="w-10 h-10 rounded-full bg-gray-100 dark:bg-zinc-800 border border-gray-200 dark:border-zinc-700 flex items-center justify-center text-mizan-gold font-semibold text-sm shrink-0">
          {agent.name[0]?.toUpperCase() || "A"}
        </div>
        <div className="flex-1 min-w-0">
          <div className="font-semibold text-sm text-gray-900 dark:text-gray-100 truncate">
            {agent.name}
          </div>
          <div className="text-xs text-gray-500 dark:text-gray-400 font-mono uppercase tracking-wide">
            {agent.role}
          </div>
        </div>
        <span
          className={`text-xs px-2 py-0.5 rounded-full font-medium ${STATE_COLORS[agent.state] || STATE_COLORS.resting}`}
        >
          {agent.state}
        </span>
      </div>

      <div className="flex items-center gap-2 mb-2">
        <span
          className="text-xs text-gray-500 dark:text-gray-400 min-w-[60px]"
          title={`Trust tier ${agent.nafs_level}/7`}
        >
          Level {agent.nafs_level}
        </span>
        <div className="flex-1 h-1.5 bg-gray-200 dark:bg-zinc-700 rounded-full overflow-hidden">
          <div
            className="h-full rounded-full transition-all"
            style={{
              width: `${(agent.nafs_level / 7) * 100}%`,
              background: nafs.color,
            }}
          />
        </div>
        <span className="text-xs text-gray-400 dark:text-gray-500 italic whitespace-nowrap">
          {nafs.desc}
        </span>
      </div>

      {/* Ruh energy bar */}
      {agent.ruh_energy != null && (
        <div className="flex items-center gap-2 mb-3">
          <span
            className="text-xs text-gray-500 dark:text-gray-400 min-w-[60px]"
            title={`Ruh energy: ${(agent.ruh_energy * 100).toFixed(0)}%`}
          >
            Ruh
          </span>
          <div className="flex-1 h-1 bg-gray-200 dark:bg-zinc-700 rounded-full overflow-hidden">
            <div
              className="h-full rounded-full transition-all"
              style={{
                width: `${agent.ruh_energy * 100}%`,
                background:
                  agent.ruh_energy > 0.6
                    ? "#10b981"
                    : agent.ruh_energy > 0.3
                      ? "#f59e0b"
                      : "#ef4444",
              }}
            />
          </div>
          <span className="text-xs text-gray-400 dark:text-gray-500 font-mono tabular-nums whitespace-nowrap">
            {(agent.ruh_energy * 100).toFixed(0)}%
          </span>
        </div>
      )}

      <div className="grid grid-cols-3 gap-2">
        {[
          {
            label: "Tasks",
            value: agent.total_tasks,
            color: undefined as boolean | undefined,
          },
          {
            label: "Success",
            value: `${(agent.success_rate * 100).toFixed(0)}%`,
            color: agent.success_rate > 0.7,
          },
          {
            label: "Wisdom",
            value: agent.hikmah_count,
            color: undefined as boolean | undefined,
          },
        ].map((s) => (
          <div
            key={s.label}
            className="text-center py-1.5 px-1 bg-gray-50 dark:bg-zinc-800/50 rounded border border-gray-100 dark:border-zinc-700/50"
          >
            <span
              className={`block font-mono text-sm ${s.color === false ? "text-red-500" : s.color ? "text-emerald-600 dark:text-emerald-400" : "text-gray-900 dark:text-gray-100"}`}
            >
              {s.value}
            </span>
            <span className="block text-xs text-gray-400 dark:text-gray-500 uppercase tracking-wider">
              {s.label}
            </span>
          </div>
        ))}
      </div>

      {(agent.tools || []).length > 0 && (
        <div className="flex flex-wrap gap-1 mt-2">
          {(agent.tools || []).slice(0, 4).map((t) => (
            <span key={t} className="tool-tag">
              {t}
            </span>
          ))}
          {(agent.tools || []).length > 4 && (
            <span className="text-xs px-1.5 py-0.5 bg-gray-100 dark:bg-zinc-800 rounded text-gray-400 font-mono">
              +{(agent.tools || []).length - 4}
            </span>
          )}
        </div>
      )}

      {agent.model && (
        <div className="mt-2 flex items-center gap-1.5">
          <span className="text-xs px-2 py-0.5 bg-purple-50 dark:bg-purple-500/10 border border-purple-200 dark:border-purple-500/20 rounded text-purple-600 dark:text-purple-400 font-mono truncate">
            {agent.model}
          </span>
        </div>
      )}
    </div>
  );
}

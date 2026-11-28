import { ShieldCheck, Star, TriangleAlert } from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import type { Agent, AgentMartaba } from "../types";
import { AGENT_AVATAR_MAX, agentSettingsFrom, agentTools, textLength } from "../utils/agentSettings.ts";

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
  resting: "bg-gray-100 dark:bg-zinc-700/30 text-muted-foreground",
  thinking: "bg-blue-100 dark:bg-blue-500/15 text-blue-600 dark:text-blue-400",
  acting:
    "bg-amber-100 dark:bg-amber-500/15 text-amber-600 dark:text-amber-400",
  learning:
    "bg-emerald-100 dark:bg-emerald-500/15 text-emerald-600 dark:text-emerald-400",
  error: "bg-red-100 dark:bg-red-500/15 text-red-600 dark:text-red-400",
};

/** The agent's own avatar (an emoji or a few letters), else its initial. */
export function AgentAvatar({ agent, className }: { agent: Pick<Agent, "name" | "settings">; className?: string }) {
  // A longer avatar (an image link from another client) shows as the initial here.
  const saved = agentSettingsFrom(agent.settings).avatar;
  const avatar = saved && textLength(saved) <= AGENT_AVATAR_MAX ? saved : null;
  return (
    <span
      aria-hidden="true"
      className={cn(
        "flex shrink-0 items-center justify-center overflow-hidden rounded-full border border-border bg-muted font-semibold text-brand",
        className,
      )}
    >
      {avatar ?? (agent.name[0]?.toUpperCase() || "A")}
    </span>
  );
}

/** The record behind an agent's Martaba stage, in words (report only: it limits nothing). */
export function martabaRecord(martaba: AgentMartaba): string {
  const counted = martaba.counted
    ? `${martaba.verified} of ${martaba.counted} checked runs verified`
    : "No checked runs yet";
  const next = martaba.stage < 7 ? `; ${martaba.to_next} more in a row for stage ${martaba.stage + 1}` : "";
  return `${counted}${next}. Shown only: it never limits what the agent may do.`;
}

interface AgentCardProps {
  agent: Agent;
  selected: boolean;
  onClick: () => void;
}

export function AgentCard({ agent, selected, onClick }: AgentCardProps) {
  const nafs = NAFS_LEVELS[agent.nafs_level] || NAFS_LEVELS[1];
  const tools = agentTools(agent);

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
      aria-pressed={selected}
      aria-label={`Agent ${agent.name}, ${nafs.desc}, ${agent.state}`}
    >
      <div className="flex items-start gap-3 mb-3">
        <AgentAvatar agent={agent} className="size-10 text-sm" />
        <div className="flex-1 min-w-0">
          <div className="font-semibold text-sm text-foreground truncate">
            {agent.name}
          </div>
          <div className="text-xs text-muted-foreground font-mono uppercase tracking-wide">
            {agent.role}
          </div>
          {(agent.is_default || agent.shared !== undefined || agent.martaba) && (
            <div className="mt-1 flex flex-wrap gap-1">
              {agent.is_default && (
                <Badge>
                  <Star /> Default
                </Badge>
              )}
              {agent.shared !== undefined && (
                <Badge variant="outline" title={agent.shared ? "Everyone on this server can chat with it" : "Only you can see it"}>
                  {agent.shared ? "Shared" : "Private"}
                </Badge>
              )}
              {agent.martaba && (
                <Badge variant="secondary" title={martabaRecord(agent.martaba)} data-testid="martaba-stage">
                  <ShieldCheck /> Stage {agent.martaba.stage}/7 · {agent.martaba.name}
                </Badge>
              )}
            </div>
          )}
        </div>
        <span
          className={`text-xs px-2 py-0.5 rounded-full font-medium ${STATE_COLORS[agent.state] || STATE_COLORS.resting}`}
        >
          {agent.state}
        </span>
      </div>

      <div className="flex items-center gap-2 mb-2">
        <span
          className="text-xs text-muted-foreground min-w-[60px]"
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
        <span className="text-xs text-muted-foreground/80 italic whitespace-nowrap">
          {nafs.desc}
        </span>
      </div>

      {/* Internal Ruh workload counter — backend sends 0-100 already. */}
      {agent.ruh_energy != null && (
        <div className="flex items-center gap-2 mb-3">
          <span
            className="text-xs text-muted-foreground min-w-[60px]"
            title="Internal task/idle counter; not training progress, CPU usage, or capability."
          >
            Ruh workload
          </span>
          <div className="flex-1 h-1 bg-gray-200 dark:bg-zinc-700 rounded-full overflow-hidden">
            <div
              className="h-full rounded-full transition-all"
              style={{
                width: `${Math.min(100, agent.ruh_energy)}%`,
                background:
                  agent.ruh_energy > 60
                    ? "#10b981"
                    : agent.ruh_energy > 30
                      ? "#f59e0b"
                      : "#ef4444",
              }}
            />
          </div>
          <span className="text-xs text-muted-foreground/80 font-mono tabular-nums whitespace-nowrap">
            {agent.ruh_energy.toFixed(0)}/100
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
            className="text-center py-1.5 px-1 bg-muted/50 rounded border border-border/60"
          >
            <span
              className={`block font-mono text-sm ${s.color === false ? "text-red-500" : s.color ? "text-emerald-600 dark:text-emerald-400" : "text-foreground"}`}
            >
              {s.value}
            </span>
            <span className="block text-xs text-muted-foreground/80 uppercase tracking-wider">
              {s.label}
            </span>
          </div>
        ))}
      </div>

      {tools.length > 0 && (
        <div className="flex flex-wrap gap-1 mt-2" title={tools.join(", ")}>
          {tools.slice(0, 4).map((t) => (
            <span key={t} className="tool-tag">
              {t}
            </span>
          ))}
          {tools.length > 4 && (
            <span className="text-xs px-1.5 py-0.5 bg-muted rounded text-muted-foreground font-mono">
              +{tools.length - 4}
            </span>
          )}
        </div>
      )}

      {agent.model && (
        <div className="mt-2 flex items-center gap-1.5">
          <span className="text-xs px-2 py-0.5 bg-muted border border-border rounded text-muted-foreground font-mono truncate">
            {agent.model}
          </span>
        </div>
      )}

      {agent.martaba && (
        <p className="mt-2 text-xs text-muted-foreground" data-testid="martaba-record">
          {martabaRecord(agent.martaba)}
        </p>
      )}

      {agent.provider_warning && (
        <p className="mt-2 flex items-start gap-1.5 rounded-md border border-warning/40 bg-warning/10 px-2 py-1.5 text-xs text-foreground">
          <TriangleAlert className="mt-0.5 size-3.5 shrink-0 text-warning" />
          <span className="min-w-0 wrap-break-word">{agent.provider_warning}</span>
        </p>
      )}
    </div>
  );
}

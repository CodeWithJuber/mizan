/**
 * ModeSwitcher — agent mode selector for the chat input area.
 *
 * Modes: "single" (default ReAct agent path) | "deep_research"
 * (planner → workers → aggregator → verifier pipeline).
 *
 * deep_research requires explicit per-request confirmation: the checkbox
 * below sets `confirmed=true` in the request body, otherwise the backend
 * rejects with 409. Live progress/cost arrives on the chat WebSocket as:
 *   {"type":"mode_progress","run_id":...,"stage":...,"detail":...,
 *    "cost_so_far":...,"tokens_so_far":...}
 */

export type AgentMode = "single" | "deep_research";

interface ModeSwitcherProps {
  mode: AgentMode;
  confirmed: boolean;
  onModeChange: (mode: AgentMode) => void;
  onConfirmedChange: (confirmed: boolean) => void;
  disabled?: boolean;
}

export default function ModeSwitcher({
  mode,
  confirmed,
  onModeChange,
  onConfirmedChange,
  disabled = false,
}: ModeSwitcherProps) {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-1 rounded-lg border border-border bg-surface p-1 text-sm">
        <button
          type="button"
          disabled={disabled}
          onClick={() => onModeChange("single")}
          className={`flex-1 rounded-md px-3 py-1.5 font-medium transition-colors ${
            mode === "single"
              ? "bg-primary text-white"
              : "text-secondary hover:text-primary"
          }`}
          aria-pressed={mode === "single"}
        >
          Single
        </button>
        <button
          type="button"
          disabled={disabled}
          onClick={() => onModeChange("deep_research")}
          className={`flex-1 rounded-md px-3 py-1.5 font-medium transition-colors ${
            mode === "deep_research"
              ? "bg-primary text-white"
              : "text-secondary hover:text-primary"
          }`}
          aria-pressed={mode === "deep_research"}
        >
          Deep research
        </button>
      </div>

      {mode === "deep_research" && (
        <label className="flex cursor-pointer items-start gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-secondary">
          <input
            type="checkbox"
            checked={confirmed}
            disabled={disabled}
            onChange={(e) => onConfirmedChange(e.target.checked)}
            className="mt-0.5 accent-amber-500"
          />
          <span>
            Deep research runs a multi-step pipeline (planner → workers →
            aggregator → verifier) that consumes extra model budget. I confirm
            this request.
          </span>
        </label>
      )}
    </div>
  );
}

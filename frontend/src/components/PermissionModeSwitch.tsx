/** Izn mode for the next chat request: how much the agent may do without asking. */
import { PERMISSION_MODES, type PermissionMode } from "../utils/agentActivity";

export const PERMISSION_LABELS: Record<PermissionMode, { title: string; hint: string }> = {
  auto_edits: { title: "Auto edits", hint: "Edits project files; asks before running commands or external actions" },
  ask: { title: "Ask first", hint: "Asks before every change or command" },
  plan: { title: "Plan", hint: "Read-only: investigates and proposes a plan" },
  auto: { title: "Full auto", hint: "Runs every permitted tool without asking" },
};

export const STORAGE_KEY = "mizan_permission_mode";

export function savePermissionMode(mode: PermissionMode) {
  try {
    localStorage.setItem(STORAGE_KEY, mode);
  } catch {
    // per-viewer convenience only
  }
}

export function loadPermissionMode(): PermissionMode {
  try {
    const saved = localStorage.getItem(STORAGE_KEY) as PermissionMode | null;
    return saved && PERMISSION_MODES.includes(saved) ? saved : "auto_edits";
  } catch {
    return "auto_edits";
  }
}

export default function PermissionModeSwitch({
  mode, onChange, disabled = false,
}: { mode: PermissionMode; onChange: (mode: PermissionMode) => void; disabled?: boolean }) {
  return (
    <label className="flex items-center gap-2 text-xs text-muted-foreground" title={PERMISSION_LABELS[mode].hint}>
      <span className="font-medium">Mode</span>
      <select
        className="rounded-md border border-border bg-card px-2 py-1 text-xs focus-ring"
        value={mode}
        disabled={disabled}
        onChange={(event) => {
          const next = event.target.value as PermissionMode;
          try { localStorage.setItem(STORAGE_KEY, next); } catch { /* per-viewer convenience only */ }
          onChange(next);
        }}
        aria-label="Agent permission mode"
      >
        {PERMISSION_MODES.map((value) => (
          <option key={value} value={value}>{PERMISSION_LABELS[value].title}</option>
        ))}
      </select>
    </label>
  );
}

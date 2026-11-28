/** Izn mode for the next chat request: how much the agent may do without asking. */
import { PERMISSION_MODES, type PermissionMode } from "../utils/agentActivity";
import {
  loadPermissionMode as loadMode, PERMISSION_STORAGE_KEY, rememberPermissionMode,
} from "../utils/permissionMode";

export const PERMISSION_LABELS: Record<PermissionMode, { title: string; hint: string }> = {
  auto_edits: { title: "Auto edits", hint: "Edits project files; asks before running commands or external actions" },
  ask: { title: "Ask first", hint: "Asks before every change or command" },
  plan: { title: "Plan", hint: "Read-only: investigates and proposes a plan" },
  auto: { title: "Full auto", hint: "Runs every permitted tool without asking" },
};

export const STORAGE_KEY = PERMISSION_STORAGE_KEY;

export function savePermissionMode(mode: PermissionMode) {
  rememberPermissionMode(mode);
}

/** The saved choice, else the server's default (when given), else "auto". */
export function loadPermissionMode(serverDefault?: unknown): PermissionMode {
  return loadMode(serverDefault);
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
          rememberPermissionMode(next);
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

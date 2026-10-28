/** Administrator view of every operator setting, editable and saved in one batch. */
import { useEffect, useMemo, useState } from "react";
import { RotateCcw, Search } from "lucide-react";
import { config } from "../config";
import { authFetch } from "../utils/authFetch";
import { PasswordInput } from "./PasswordInput";
import {
  isOn,
  pendingChanges,
  type RuntimeSetting,
} from "../utils/runtimeSettings";

interface View {
  groups: string[];
  settings: RuntimeSetting[];
  restart_required: string[];
  notes?: string[];
}

const field =
  "w-full px-3 py-2 rounded-lg border border-border bg-background text-sm focus-ring";
const APPLY_LABEL = {
  live: "Applies immediately",
  provider: "Switches the model now",
  restart: "Needs a backend restart",
} as const;

async function request(init?: RequestInit): Promise<View> {
  const response = await authFetch(`${config.API_URL}/settings/runtime`, init);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = body.detail;
    const error = new Error(
      typeof detail === "string" ? detail : detail?.message ?? `Request failed (${response.status})`,
    ) as Error & { fields?: Record<string, string> };
    if (detail && typeof detail === "object" && detail.errors) error.fields = detail.errors;
    throw error;
  }
  return body as View;
}

export default function RuntimeSettingsPanel() {
  const [view, setView] = useState<View | null>(null);
  const [error, setError] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [notes, setNotes] = useState<string[]>([]);
  const [edits, setEdits] = useState<Record<string, string | boolean | null>>({});
  const [group, setGroup] = useState("Model");
  const [query, setQuery] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    request().then(setView).catch((e) => setError((e as Error).message));
  }, []);

  const changes = useMemo(() => (view ? pendingChanges(view.settings, edits) : {}), [view, edits]);
  const changeCount = Object.keys(changes).length;
  const visible = useMemo(() => {
    if (!view) return [];
    const needle = query.trim().toLowerCase();
    return view.settings.filter((item) =>
      needle
        ? `${item.label} ${item.key} ${item.description}`.toLowerCase().includes(needle)
        : item.group === group,
    );
  }, [view, group, query]);

  const save = async () => {
    setSaving(true);
    setError("");
    setFieldErrors({});
    setNotes([]);
    try {
      const next = await request({
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ values: changes }),
      });
      setView(next);
      setEdits({});
      setNotes(next.notes?.length ? next.notes : ["Saved."]);
    } catch (e) {
      const failure = e as Error & { fields?: Record<string, string> };
      setError(failure.message);
      setFieldErrors(failure.fields ?? {});
    } finally {
      setSaving(false);
    }
  };

  if (error && !view) {
    return <p role="alert" className="text-sm text-red-600">{error === "Administrator role required" ? "Only administrators can change system settings." : error}</p>;
  }
  if (!view) return <p className="text-sm text-gray-500">Loading settings…</p>;

  return (
    <div className="space-y-4 pb-20">
      <div>
        <h3 className="text-lg font-semibold text-foreground">System settings</h3>
        <p className="text-sm text-muted-foreground">
          Every server setting in one place. Saved values are stored on the server (keys encrypted) and override its .env.
        </p>
      </div>
      {view.restart_required.length > 0 && (
        <p role="status" className="text-sm rounded-lg p-3 bg-amber-50 text-amber-800 dark:bg-amber-500/10 dark:text-amber-300">
          Restart the backend to apply: {view.restart_required.join(", ")}
        </p>
      )}
      <div className="flex flex-wrap gap-2 items-center">
        <div className="relative w-full sm:w-64">
          <Search className="w-4 h-4 absolute left-3 top-2.5 text-gray-400" aria-hidden />
          <input aria-label="Search settings" className={`${field} pl-9`} placeholder="Search settings" value={query} onChange={(e) => setQuery(e.target.value)} />
        </div>
        {!query && view.groups.map((name) => (
          <button
            key={name}
            className={`px-3 py-1.5 text-xs rounded-full border ${group === name ? "border-amber-500 bg-amber-50 text-amber-800 dark:bg-amber-500/10 dark:text-amber-300" : "border-border text-muted-foreground"}`}
            aria-pressed={group === name}
            onClick={() => setGroup(name)}
          >
            {name}
          </button>
        ))}
      </div>
      <div className="space-y-3">
        {visible.map((item) => {
          const edited = item.key in edits;
          const value = edited ? edits[item.key] : item.value;
          const inputId = `setting-${item.key}`;
          return (
            <div key={item.key} className="card">
              <div className="flex flex-wrap items-start gap-2 justify-between">
                <div className="min-w-0">
                  <label htmlFor={inputId} className="font-medium text-sm text-foreground">{item.label}</label>
                  <p className="text-2xs font-mono text-gray-400">{item.key}</p>
                </div>
                <div className="flex flex-wrap gap-1 text-2xs">
                  <span className={`px-2 py-0.5 rounded-full ${item.source === "admin" ? "bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-300" : "bg-gray-100 text-gray-600 dark:bg-zinc-800 dark:text-gray-400"}`}>
                    {item.source === "admin" ? "Set here" : item.source === "environment" ? "From server .env" : "Default"}
                  </span>
                  <span className={`px-2 py-0.5 rounded-full ${item.restart_pending ? "bg-amber-100 text-amber-800" : "bg-gray-100 text-gray-600 dark:bg-zinc-800 dark:text-gray-400"}`}>
                    {item.restart_pending ? "Restart pending" : APPLY_LABEL[item.apply]}
                  </span>
                </div>
              </div>
              {item.description && <p className="text-xs text-muted-foreground mt-1">{item.description}</p>}
              <div className="mt-2 flex items-center gap-2">
                <div className="flex-1 min-w-0">
                  {item.kind === "bool" ? (
                    <label className="inline-flex items-center gap-2 text-sm">
                      <input id={inputId} type="checkbox" className="w-4 h-4 accent-amber-600" checked={value === null ? isOn(item.default) : typeof value === "boolean" ? value : isOn(String(value ?? ""))} onChange={(e) => setEdits({ ...edits, [item.key]: e.target.checked })} />
                      {(value === null ? isOn(item.default) : typeof value === "boolean" ? value : isOn(String(value ?? ""))) ? "On" : "Off"}
                    </label>
                  ) : item.kind === "choice" ? (
                    <select id={inputId} className={field} value={String(value ?? item.default)} onChange={(e) => setEdits({ ...edits, [item.key]: e.target.value })}>
                      {item.choices.map((choice) => <option key={choice} value={choice}>{choice}</option>)}
                    </select>
                  ) : item.kind === "secret" ? (
                    <PasswordInput
                      id={inputId}
                      value={typeof value === "string" ? value : ""}
                      onChange={(text) => setEdits({ ...edits, [item.key]: text })}
                      placeholder={item.is_set ? "Saved — type to replace" : "Not set"}
                      className={field}
                    />
                  ) : (
                    <input
                      id={inputId}
                      type={item.kind === "int" || item.kind === "float" ? "number" : "text"}
                      step={item.kind === "float" ? "any" : undefined}
                      min={item.minimum ?? undefined}
                      max={item.maximum ?? undefined}
                      className={`${field} ${item.kind === "text" || item.kind === "url" ? "font-mono" : ""}`}
                      value={value === null ? "" : String(value ?? "")}
                      placeholder={item.default ? `Default: ${item.default}` : ""}
                      onChange={(e) => setEdits({ ...edits, [item.key]: e.target.value })}
                    />
                  )}
                </div>
                {(item.source === "admin" || edited) && (
                  <button
                    className="p-2 rounded-lg border border-border hover:bg-gray-100 dark:hover:bg-zinc-800"
                    title={item.source === "admin" ? "Use the server's own value" : "Undo"}
                    aria-label={`Reset ${item.label}`}
                    onClick={() => {
                      const { [item.key]: _dropped, ...rest } = edits;
                      setEdits(item.source === "admin" && !(edited && edits[item.key] === null) ? { ...rest, [item.key]: null } : rest);
                    }}
                  >
                    <RotateCcw className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>
              {edited && edits[item.key] === null && <p className="text-2xs text-amber-700 mt-1">Will reset to the server's own value.</p>}
              {fieldErrors[item.key] && <p role="alert" className="text-xs text-red-600 mt-1">{fieldErrors[item.key]}</p>}
            </div>
          );
        })}
        {visible.length === 0 && <p className="text-sm text-gray-500">No settings match.</p>}
      </div>
      <div className="sticky bottom-0 -mx-4 md:-mx-8 px-4 md:px-8 py-3 bg-white/95 dark:bg-zinc-950/95 border-t border-border flex flex-wrap items-center gap-2">
        <span className="text-sm text-muted-foreground mr-auto" role="status">
          {error ? <span className="text-red-600">{error}</span> : notes.length ? notes.join(" ") : changeCount ? `${changeCount} unsaved change${changeCount > 1 ? "s" : ""}` : "No unsaved changes"}
        </span>
        <button className="px-3 py-1.5 text-sm rounded-lg border border-border disabled:opacity-40" disabled={!changeCount || saving} onClick={() => { setEdits({}); setFieldErrors({}); }}>
          Discard
        </button>
        <button className="px-3 py-1.5 text-sm rounded-lg bg-amber-600 text-white disabled:opacity-40" disabled={!changeCount || saving} onClick={() => void save()}>
          {saving ? "Saving…" : "Save changes"}
        </button>
      </div>
    </div>
  );
}

/**
 * The connector form, for adding (Custom, or prefilled from a preset or the
 * registry) and for editing. Remote servers speak streamable HTTP or the
 * older SSE; local ones are a command (stdio).
 */
import { useState, type FormEvent } from "react";
import { ExternalLink } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";
import { KeyValueEditor } from "./KeyValueEditor";
import { type Draft, type DraftErrors, isRemote, stdioUnavailable, validateDraft } from "./logic";
import { OfficialBadge } from "./parts";
import type { Capabilities, Transport } from "./types";

export const SELECT_CLASS =
  "h-8 w-full min-w-0 rounded-lg border border-input bg-background px-2 text-sm outline-none transition-colors focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-input/30";

interface Props {
  draft: Draft;
  onChange: (draft: Draft) => void;
  mode: "create" | "edit";
  capabilities: Capabilities;
  busy: boolean;
  submitLabel: string;
  /** Called with a draft that passed validation. */
  onSubmit: () => void;
  onCancel?: () => void;
  cancelLabel?: string;
  /** Edit: the server holds an OAuth client secret already. */
  savedClientSecret?: boolean;
  idPrefix: string;
}

const AUTH_HINT = {
  oauth: "Signs in with OAuth: after adding, press Connect and a sign-in window opens.",
  headers: "Needs an API key in a header: fill it in below.",
  none: "No sign-in needed.",
} as const;

const ORDER: (keyof DraftErrors)[] = ["name", "url", "command", "headers", "env", "oauth", "timeouts"];

export function ConnectorForm({
  draft, onChange, mode, capabilities, busy, submitLabel, onSubmit, onCancel, cancelLabel = "Cancel",
  savedClientSecret = false, idPrefix,
}: Props) {
  const [submitted, setSubmitted] = useState(false);
  const [advancedOpen, setAdvancedOpen] = useState(() =>
    Boolean(draft.oauth.client_id || draft.timeouts.connect_s || draft.timeouts.call_s));
  const errors = submitted ? validateDraft(draft, mode === "create") : {};
  const remote = isRemote(draft.transport);
  const stdioBlocked = stdioUnavailable(capabilities);
  const stdioDisabled = Boolean(stdioBlocked) && !(mode === "edit" && draft.transport === "stdio");
  const id = (name: string) => `${idPrefix}-${name}`;
  const described = (name: keyof DraftErrors, hint?: string) => {
    const ids = [errors[name] ? id(`${name}-error`) : "", hint ? id(`${name}-hint`) : ""].filter(Boolean).join(" ");
    return { "aria-invalid": errors[name] ? true : undefined, "aria-describedby": ids || undefined };
  };
  const set = (change: Partial<Draft>) => onChange({ ...draft, ...change });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setSubmitted(true);
    const found = validateDraft(draft, mode === "create");
    const first = ORDER.find((name) => found[name]);
    if (first) {
      if (first === "oauth" || first === "timeouts") setAdvancedOpen(true);
      const target = first === "headers" || first === "env" ? `${first}-error` : first === "oauth" ? "oauth-client" : first;
      // After the errors render: focus the field, or bring a list's message into view.
      requestAnimationFrame(() => {
        const element = document.getElementById(id(target));
        if (element instanceof HTMLInputElement) element.focus();
        else element?.scrollIntoView({ block: "center" });
      });
      return;
    }
    onSubmit();
  };

  return (
    <form className="space-y-5" onSubmit={submit} noValidate aria-label={mode === "create" ? "New connector" : "Edit connector"}>
      {draft.origin && (
        <div className="space-y-1 rounded-lg border bg-muted/40 p-3 text-sm">
          <p className="flex flex-wrap items-center gap-2">
            <span className="text-muted-foreground">From</span>
            <span className="font-medium">{draft.origin.label}</span>
            {draft.origin.official && <OfficialBadge />}
            {draft.origin.docs_url && (
              <a className="inline-flex items-center gap-1 text-xs text-brand underline-offset-4 hover:underline" href={draft.origin.docs_url} target="_blank" rel="noopener noreferrer">
                Documentation <ExternalLink className="size-3" aria-hidden />
              </a>
            )}
          </p>
          {draft.origin.auth && <p className="text-xs text-muted-foreground">{AUTH_HINT[draft.origin.auth]}</p>}
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor={id("name")}>Name</Label>
          <Input id={id("name")} maxLength={60} autoComplete="off" placeholder="GitHub" value={draft.name}
            onChange={(event) => set({ name: event.target.value })} {...described("name")} />
          {errors.name && <p id={id("name-error")} className="text-xs text-destructive">{errors.name}</p>}
        </div>
        <div className="space-y-1.5">
          <Label htmlFor={id("transport")}>Type</Label>
          <select id={id("transport")} className={SELECT_CLASS} value={draft.transport}
            aria-describedby={stdioDisabled ? id("transport-hint") : undefined}
            onChange={(event) => set({ transport: event.target.value as Transport })}>
            <option value="http">Remote · streamable HTTP</option>
            <option value="sse">Remote · server-sent events (SSE)</option>
            <option value="stdio" disabled={stdioDisabled}>Local command (stdio)</option>
          </select>
          {stdioDisabled && <p id={id("transport-hint")} className="text-xs text-muted-foreground">{stdioBlocked}</p>}
        </div>
      </div>

      {remote ? (
        <div className="space-y-1.5">
          <Label htmlFor={id("url")}>Server URL</Label>
          <Input id={id("url")} type="url" inputMode="url" autoComplete="off" spellCheck={false} className="font-mono"
            placeholder={draft.transport === "sse" ? "https://example.com/sse" : "https://example.com/mcp"}
            value={draft.url} onChange={(event) => set({ url: event.target.value })} {...described("url", "hint")} />
          {errors.url && <p id={id("url-error")} className="text-xs text-destructive">{errors.url}</p>}
          <p id={id("url-hint")} className="text-xs text-muted-foreground">
            Servers that use OAuth open a sign-in window when you connect.
          </p>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-3">
          <div className="space-y-1.5">
            <Label htmlFor={id("command")}>Command</Label>
            <Input id={id("command")} autoComplete="off" spellCheck={false} className="font-mono" placeholder="npx"
              value={draft.command} onChange={(event) => set({ command: event.target.value })} {...described("command")} />
            {errors.command && <p id={id("command-error")} className="text-xs text-destructive">{errors.command}</p>}
          </div>
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor={id("args")}>Arguments</Label>
            <Input id={id("args")} autoComplete="off" spellCheck={false} className="font-mono"
              placeholder="-y @modelcontextprotocol/server-everything" value={draft.args}
              aria-describedby={id("args-hint")} onChange={(event) => set({ args: event.target.value })} />
          </div>
          <p id={id("args-hint")} className="text-xs text-muted-foreground sm:col-span-3">
            Quote an argument that has spaces. {capabilities.host_stdio
              ? "Local servers you add run as a process on the MIZAN server."
              : "Local servers run in the isolated sandbox runner, which only reaches the package registries."}
          </p>
        </div>
      )}

      {remote ? (
        <KeyValueEditor kind="headers" idPrefix={id("headers")} rows={draft.headers} error={errors.headers}
          onChange={(headers) => set({ headers })} />
      ) : (
        <KeyValueEditor kind="env" idPrefix={id("env")} rows={draft.env} error={errors.env}
          onChange={(env) => set({ env })} />
      )}

      <details className="group rounded-lg border" open={advancedOpen}
        onToggle={(event) => setAdvancedOpen(event.currentTarget.open)}>
        <summary className="cursor-pointer select-none rounded-lg px-3 py-2 text-sm font-medium hover:bg-muted">
          Advanced{remote ? ": OAuth client and timeouts" : ": timeouts"}
        </summary>
        <div className="space-y-4 border-t p-3">
          {remote && (
            <fieldset className="space-y-3">
              <legend className="text-sm font-medium">OAuth client</legend>
              <p className="text-xs text-muted-foreground">
                Only for a server that does not register clients by itself: enter the client its provider gave you.
              </p>
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <Label htmlFor={id("oauth-client")}>Client ID</Label>
                  <Input id={id("oauth-client")} autoComplete="off" spellCheck={false} className="font-mono"
                    value={draft.oauth.client_id} {...described("oauth")}
                    onChange={(event) => set({ oauth: { ...draft.oauth, client_id: event.target.value } })} />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor={id("oauth-secret")}>Client secret</Label>
                  <Input id={id("oauth-secret")} type="password" autoComplete="off"
                    placeholder={savedClientSecret ? "Leave empty to keep it as it is" : "Optional"}
                    value={draft.oauth.client_secret}
                    onChange={(event) => set({ oauth: { ...draft.oauth, client_secret: event.target.value } })} />
                </div>
                <div className="space-y-1.5 sm:col-span-2">
                  <Label htmlFor={id("oauth-scopes")}>Scopes</Label>
                  <Input id={id("oauth-scopes")} autoComplete="off" spellCheck={false} className="font-mono"
                    placeholder="repo read:user" value={draft.oauth.scopes}
                    onChange={(event) => set({ oauth: { ...draft.oauth, scopes: event.target.value } })} />
                </div>
              </div>
              {errors.oauth && <p id={id("oauth-error")} className="text-xs text-destructive">{errors.oauth}</p>}
            </fieldset>
          )}
          <fieldset className="space-y-3">
            <legend className="text-sm font-medium">Timeouts</legend>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor={id("timeouts")}>Connect (seconds)</Label>
                <Input id={id("timeouts")} type="number" inputMode="numeric" min={1} max={3600} placeholder="Server default"
                  value={draft.timeouts.connect_s} {...described("timeouts")}
                  onChange={(event) => set({ timeouts: { ...draft.timeouts, connect_s: event.target.value } })} />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor={id("timeouts-call")}>Each tool call (seconds)</Label>
                <Input id={id("timeouts-call")} type="number" inputMode="numeric" min={1} max={3600} placeholder="Server default"
                  value={draft.timeouts.call_s}
                  onChange={(event) => set({ timeouts: { ...draft.timeouts, call_s: event.target.value } })} />
              </div>
            </div>
            {errors.timeouts && <p id={id("timeouts-error")} className="text-xs text-destructive">{errors.timeouts}</p>}
          </fieldset>
        </div>
      </details>

      <div className={cn("flex flex-wrap gap-2", mode === "edit" && "justify-end")}>
        {onCancel && mode === "edit" && <Button type="button" variant="ghost" onClick={onCancel}>{cancelLabel}</Button>}
        <Button type="submit" disabled={busy}>{busy ? "Saving…" : submitLabel}</Button>
        {onCancel && mode === "create" && <Button type="button" variant="ghost" onClick={onCancel}>{cancelLabel}</Button>}
      </div>
    </form>
  );
}

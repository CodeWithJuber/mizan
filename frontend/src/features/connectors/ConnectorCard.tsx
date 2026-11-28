/** One connector: live status, how it signs in, its actions, and what it offers. */
import { useId, useState } from "react";
import {
  Activity, ChevronRight, CircleAlert, ExternalLink, KeyRound, LoaderCircle, Pencil, PlugZap, RefreshCw, ScrollText,
  Trash2, Unplug,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";
import type { ConnectorActions } from "./api";
import { authSummary, endpoint, TRANSPORT_LABEL } from "./logic";
import { StatusPill, ToneBadge } from "./parts";
import { ToolsPanel } from "./ToolsPanel";
import type { Connector } from "./types";

export type Busy = "connect" | "test" | "disconnect" | "signout" | "enable" | "delete";

interface Props {
  connector: Connector;
  actions: ConnectorActions;
  now: number;
  busy?: Busy;
  /** A sign-in or connection is being waited for. */
  waiting: boolean;
  /** The browser blocked the sign-in window: the link to open by hand. */
  signInUrl?: string;
  onConnect: (connector: Connector, intent: "connect" | "signin") => void;
  onStopWaiting: (connector: Connector) => void;
  onTest: (connector: Connector) => void;
  onDisconnect: (connector: Connector) => void;
  onSignOut: (connector: Connector) => void;
  onToggle: (connector: Connector, enabled: boolean) => void;
  onEdit: (connector: Connector) => void;
  onLogs: (connector: Connector) => void;
  onDelete: (connector: Connector) => void;
}

export function ConnectorCard({
  connector, actions, now, busy, waiting, signInUrl,
  onConnect, onStopWaiting, onTest, onDisconnect, onSignOut, onToggle, onEdit, onLogs, onDelete,
}: Props) {
  const uid = useId();
  const titleId = `${uid}-title`;
  const panelId = `${uid}-tools`;
  const { status, counts, enabled, name } = connector;
  const [open, setOpen] = useState(counts.held > 0);
  const auth = authSummary(connector, now);
  const live = status === "connected" || status === "connecting";
  const showTools = connector.tools.length > 0 || status === "connected";

  return (
    <article aria-labelledby={titleId} className={cn("rounded-xl border bg-card text-card-foreground", !enabled && "opacity-80")}>
      <div className="flex items-start gap-3 p-4">
        <div className="min-w-0 flex-1 space-y-1.5">
          <div className="flex flex-wrap items-center gap-2">
            <h3 id={titleId} className="break-words font-semibold">{name}</h3>
            <StatusPill status={status} />
            <ToneBadge tone="muted">{TRANSPORT_LABEL[connector.transport]}</ToneBadge>
            {connector.transport === "stdio" && connector.runtime && (
              <ToneBadge tone="muted">{connector.runtime === "host" ? "Runs on the server" : "Runs in the sandbox"}</ToneBadge>
            )}
          </div>
          <p className="break-all font-mono text-xs text-muted-foreground">{endpoint(connector)}</p>
          {connector.last_error && status !== "connected" && (
            <p className="flex items-start gap-1.5 break-words text-xs text-destructive">
              <CircleAlert className="mt-px size-3.5 shrink-0" aria-hidden />
              <span className="min-w-0">{connector.last_error}</span>
            </p>
          )}
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
            <KeyRound className="size-3.5 shrink-0" aria-hidden />
            <span className="min-w-0 break-words">{auth.text}</span>
            {auth.action === "signin" && (
              <Button size="xs" variant="outline" disabled={!enabled || busy === "connect" || waiting}
                onClick={() => onConnect(connector, "signin")} aria-label={`Sign in to ${name}`}>
                Sign in
              </Button>
            )}
            {auth.action === "signout" && (
              <Button size="xs" variant="ghost" disabled={busy === "signout"} onClick={() => onSignOut(connector)}
                aria-label={`Sign out of ${name}`}>
                Sign out
              </Button>
            )}
          </div>
          {waiting && (
            <output className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              <LoaderCircle className="size-3.5 animate-spin text-brand" aria-hidden />
              {auth.action === "signin" || connector.auth.type === "oauth"
                ? "Waiting for you to finish signing in…"
                : "Waiting for it to connect…"}
              <Button size="xs" variant="ghost" onClick={() => onStopWaiting(connector)}>Stop waiting</Button>
            </output>
          )}
          {signInUrl && (
            <p className="text-xs">
              Your browser blocked the sign-in window.{" "}
              <a href={signInUrl} target="_blank" rel="noopener noreferrer"
                className="inline-flex items-center gap-1 font-medium text-brand underline underline-offset-4">
                Open the sign-in page <ExternalLink className="size-3" aria-hidden />
              </a>
            </p>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-2 pt-0.5">
          <span className="hidden text-xs text-muted-foreground sm:inline" aria-hidden>{enabled ? "On" : "Off"}</span>
          <Switch
            checked={enabled}
            disabled={busy === "enable"}
            aria-label={`Use ${name}`}
            onCheckedChange={(checked) => onToggle(connector, checked)}
          />
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2 border-t px-4 py-3">
        <Button size="sm" disabled={!enabled || busy === "connect" || waiting} onClick={() => onConnect(connector, "connect")}
          aria-label={`${status === "connected" ? "Reconnect" : "Connect"} ${name}`}>
          {busy === "connect" ? <LoaderCircle className="animate-spin" aria-hidden />
            : status === "connected" ? <RefreshCw aria-hidden /> : <PlugZap aria-hidden />}
          {status === "connected" ? "Reconnect" : "Connect"}
        </Button>
        <Button size="sm" variant="outline" disabled={!enabled || busy === "test"} onClick={() => onTest(connector)} aria-label={`Test ${name}`}>
          {busy === "test" ? <LoaderCircle className="animate-spin" aria-hidden /> : <Activity aria-hidden />} Test
        </Button>
        {live && (
          <Button size="sm" variant="outline" disabled={busy === "disconnect"} onClick={() => onDisconnect(connector)} aria-label={`Disconnect ${name}`}>
            <Unplug aria-hidden /> Disconnect
          </Button>
        )}
        <Button size="sm" variant="outline" onClick={() => onEdit(connector)} aria-label={`Edit ${name}`}>
          <Pencil aria-hidden /> Edit
        </Button>
        <Button size="sm" variant="ghost" onClick={() => onLogs(connector)} aria-label={`Logs of ${name}`}>
          <ScrollText aria-hidden /> Logs
        </Button>
        <Button size="icon-sm" variant="ghost" className="ml-auto text-destructive hover:bg-destructive/10 hover:text-destructive"
          disabled={busy === "delete"} onClick={() => onDelete(connector)} aria-label={`Delete ${name}`}>
          <Trash2 />
        </Button>
      </div>

      {connector.instructions && (
        <details className="border-t px-4 py-2.5 text-sm">
          <summary className="cursor-pointer select-none text-muted-foreground hover:text-foreground">Instructions from the server</summary>
          <p className="mt-2 whitespace-pre-wrap break-words text-xs">{connector.instructions}</p>
          <p className="mt-1 text-xs text-muted-foreground">MIZAN reads these as information about the server, never as orders.</p>
        </details>
      )}

      {showTools && (
        <div className="border-t">
          <button
            type="button"
            aria-expanded={open}
            aria-controls={panelId}
            onClick={() => setOpen((value) => !value)}
            className="flex w-full flex-wrap items-center gap-2 rounded-b-xl px-4 py-2.5 text-left text-sm outline-none hover:bg-muted/50 focus-visible:ring-3 focus-visible:ring-ring/50"
          >
            <ChevronRight className={cn("size-4 shrink-0 text-muted-foreground transition-transform", open && "rotate-90")} aria-hidden />
            <span className="font-medium">Tools, resources and prompts</span>
            <span className="text-xs text-muted-foreground">{counts.enabled} of {counts.total} tools usable</span>
            {counts.held > 0 && <ToneBadge tone="warning">{counts.held} held</ToneBadge>}
            {counts.new > 0 && <ToneBadge tone="info">{counts.new} new</ToneBadge>}
          </button>
          {open && (
            <div id={panelId} className="px-4 pb-4">
              <ToolsPanel connector={connector} actions={actions} />
            </div>
          )}
        </div>
      )}
    </article>
  );
}

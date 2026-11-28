/**
 * Connectors (Wasl - وَصْل - connection): MCP servers the agent can use.
 * Add one from a preset, the official MCP Registry or by hand; connect and
 * sign in; test it; choose per tool whether the agent may call it, must ask
 * first, or never may. Tools whose description changed or that instruct the
 * AI are held by Amanah until the person trusts them.
 */
import { useEffect, useRef, useState } from "react";
import { Plug, PlugZap, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { confirmDialog } from "@/components/ui/confirm";
import { addToast } from "../components/Toast";
import { AddConnector } from "../features/connectors/AddConnector";
import { type Busy, ConnectorCard } from "../features/connectors/ConnectorCard";
import { EditSheet } from "../features/connectors/EditSheet";
import { LogsDialog } from "../features/connectors/LogsDialog";
import { notFound, useConnectorActions, useConnectorList } from "../features/connectors/api";
import {
  closeSignInWindow, openSignInWindow, pollOAuth, readConnectorPhase, readOAuthStatus, sendSignInWindow, type PollEnd,
} from "../features/connectors/oauth";
import { Dot, useNow } from "../features/connectors/parts";
import type { Capabilities, Connector } from "../features/connectors/types";

const message = (problem: unknown) => (problem instanceof Error ? problem.message : undefined);

function CapabilityBadges({ capabilities }: { capabilities: Capabilities }) {
  const runner = !capabilities.sandbox_stdio
    ? { tone: "muted" as const, text: "No sandbox runner" }
    : capabilities.runner_available === false
      ? { tone: "warning" as const, text: "Sandbox runner offline" }
      : { tone: "success" as const, text: capabilities.runner_available ? "Sandbox runner available" : "Sandbox runner enabled" };
  return (
    <ul className="flex flex-wrap gap-2" aria-label="What this MIZAN can run">
      <li className="inline-flex h-6 items-center gap-1.5 rounded-full border px-2.5 text-xs">
        <Dot tone="success" /> Remote servers
      </li>
      <li className="inline-flex h-6 items-center gap-1.5 rounded-full border px-2.5 text-xs"
        title="Local (stdio) servers run in an isolated container whose only network is the package registries.">
        <Dot tone={runner.tone} /> {runner.text}
      </li>
      {capabilities.host_stdio && (
        <li className="inline-flex h-6 items-center gap-1.5 rounded-full border px-2.5 text-xs"
          title="As an administrator, local servers you add run as a process on the MIZAN server.">
          <Dot tone="info" /> Local servers on this server
        </li>
      )}
    </ul>
  );
}

const EMPTY_CAPS: Capabilities = { sandbox_stdio: false, host_stdio: false, runner_available: null };

export default function ConnectorsPage() {
  const { data, isLoading, error, refetch } = useConnectorList();
  const actions = useConnectorActions();
  const now = useNow();
  const [adding, setAdding] = useState<boolean | null>(null);
  const [editing, setEditing] = useState<Connector | null>(null);
  const [logsFor, setLogsFor] = useState<Connector | null>(null);
  const [busy, setBusy] = useState<Record<string, Busy | undefined>>({});
  const [waiting, setWaiting] = useState<Record<string, boolean>>({});
  const [signInUrls, setSignInUrls] = useState<Record<string, string | undefined>>({});
  const polls = useRef(new Map<string, () => void>());

  useEffect(() => {
    const running = polls.current;
    return () => running.forEach((stop) => stop());
  }, []);

  const connectors = data?.connectors ?? [];
  const capabilities = data?.capabilities ?? EMPTY_CAPS;
  // With nothing added yet the add panel is open; after that it opens on request.
  const showAdd = adding ?? (data !== undefined && connectors.length === 0);

  const mark = (id: string, value: Busy | undefined) => setBusy((current) => ({ ...current, [id]: value }));
  const setWait = (id: string, value: boolean) => setWaiting((current) => ({ ...current, [id]: value }));
  const setLink = (id: string, url: string | undefined) => setSignInUrls((current) => ({ ...current, [id]: url }));

  const announce = (connector: Connector, end: PollEnd, signIn: boolean) => {
    if (end.outcome === "connected") {
      addToast({ type: "success", title: `${connector.name} connected` });
    } else if (end.outcome === "error") {
      addToast({ type: "error", title: `Could not connect ${connector.name}`, description: end.error });
    } else if (end.outcome === "auth_required") {
      addToast({
        type: "warning",
        title: `${connector.name} still needs you to sign in`,
        description: end.error ?? "The sign-in did not finish. Press Sign in to try again.",
      });
    } else {
      addToast({
        type: "warning",
        title: `Stopped waiting for ${connector.name}`,
        description: signIn
          ? "The sign-in took longer than five minutes. Press Sign in to try again."
          : "It has not connected yet. Its logs may say why.",
      });
    }
  };

  /** Ask every 2 s how the sign-in (or the connection) is going, until it ends. */
  const watch = (connector: Connector, signIn: boolean, popup: Window | null) => {
    polls.current.get(connector.id)?.();
    setWait(connector.id, true);
    // A sign-in asks /oauth/status; an older server without it, or a plain connection, reads the connector.
    let fallback = !signIn;
    const stop = pollOAuth({
      check: async () => {
        if (!fallback) {
          try {
            return readOAuthStatus(await actions.oauthStatus(connector));
          } catch (problem) {
            if (!notFound(problem)) throw problem;
            fallback = true;
          }
        }
        const current = await actions.get(connector.id);
        return readConnectorPhase(current.status, current.last_error, signIn);
      },
      onEnd: (end) => {
        polls.current.delete(connector.id);
        closeSignInWindow(popup);
        setWait(connector.id, false);
        if (end.outcome === "connected") setLink(connector.id, undefined);
        void actions.refresh();
        announce(connector, end, signIn);
      },
    });
    polls.current.set(connector.id, () => {
      stop();
      setWait(connector.id, false);
    });
  };

  const stopWaiting = (connector: Connector) => {
    polls.current.get(connector.id)?.();
    polls.current.delete(connector.id);
    void actions.refresh();
  };

  const connect = (connector: Connector, intent: "connect" | "signin") => {
    // The window opens here, inside the click: a window opened after the server answers is blocked by Safari and others.
    const expectsSignIn = intent === "signin" || connector.status === "auth_required"
      || (connector.auth.type === "oauth" && !connector.auth.signed_in);
    const popup = expectsSignIn ? openSignInWindow(`mizan-sign-in-${connector.id}`) : null;
    mark(connector.id, "connect");
    setLink(connector.id, undefined);
    void (async () => {
      try {
        const result = await actions.connect(connector);
        if (result.status === "authorization_required" && result.authorizationUrl) {
          const url = result.authorizationUrl;
          // No window opened in the click (the server asked for a sign-in we did not expect): try one now.
          const signInWindow = popup ?? openSignInWindow(`mizan-sign-in-${connector.id}`);
          if (sendSignInWindow(signInWindow, url)) {
            addToast({ type: "info", title: `Sign in to ${connector.name} in the new window`, description: "This page updates when you are done." });
          } else {
            closeSignInWindow(signInWindow);
            setLink(connector.id, url);
            addToast({
              type: "warning",
              title: "Your browser blocked the sign-in window",
              description: `Open the sign-in page for ${connector.name} to continue.`,
              action: { label: "Open sign-in page", onClick: () => globalThis.open(url, "_blank", "noopener,noreferrer") },
            });
          }
          watch(connector, true, signInWindow);
        } else if (result.status === "connected") {
          closeSignInWindow(popup);
          addToast({ type: "success", title: `${connector.name} connected` });
        } else {
          closeSignInWindow(popup);
          watch(connector, false, null);
        }
      } catch (problem) {
        closeSignInWindow(popup);
        addToast({ type: "error", title: `Could not connect ${connector.name}`, description: message(problem) });
        void actions.refresh();
      } finally {
        mark(connector.id, undefined);
      }
    })();
  };

  const run = async (connector: Connector, kind: Busy, work: () => Promise<void>, failure: string) => {
    mark(connector.id, kind);
    try {
      await work();
    } catch (problem) {
      addToast({ type: "error", title: failure, description: message(problem) });
    } finally {
      mark(connector.id, undefined);
    }
  };

  const test = (connector: Connector) => void run(connector, "test", async () => {
    const result = await actions.test(connector);
    if (result.ok) {
      const parts = [
        result.latency_ms != null ? `${Math.round(result.latency_ms)} ms` : "",
        result.tools != null ? `${result.tools} tool${result.tools === 1 ? "" : "s"}` : "",
      ].filter(Boolean);
      addToast({ type: "success", title: `${connector.name} answered`, ...(parts.length ? { description: parts.join(" · ") } : {}) });
    } else {
      addToast({ type: "error", title: `${connector.name} did not answer`, description: result.error });
    }
  }, `Could not test ${connector.name}`);

  const disconnect = (connector: Connector) => void run(connector, "disconnect", async () => {
    stopWaiting(connector);
    await actions.disconnect(connector);
    addToast({ type: "info", title: `${connector.name} disconnected` });
  }, `Could not disconnect ${connector.name}`);

  const signOut = async (connector: Connector) => {
    const confirmed = await confirmDialog({
      title: `Sign out of ${connector.name}?`,
      description: "MIZAN forgets its sign-in, and the agent can't use this connector until you sign in again.",
      confirmLabel: "Sign out",
    });
    if (!confirmed) return;
    await run(connector, "signout", async () => {
      await actions.signOut(connector);
      addToast({ type: "info", title: `Signed out of ${connector.name}` });
    }, `Could not sign out of ${connector.name}`);
  };

  const toggle = (connector: Connector, enabled: boolean) => void run(connector, "enable", async () => {
    await actions.update(connector, { enabled });
    if (!enabled) stopWaiting(connector);
  }, `Could not ${enabled ? "enable" : "disable"} ${connector.name}`);

  const remove = async (connector: Connector) => {
    const confirmed = await confirmDialog({
      title: `Delete ${connector.name}?`,
      description: "Its saved headers, variables and sign-in are deleted too. The agent loses its tools at once.",
      confirmLabel: "Delete",
      destructive: true,
    });
    if (!confirmed) return;
    stopWaiting(connector);
    await run(connector, "delete", async () => {
      await actions.remove(connector);
      addToast({ type: "success", title: `${connector.name} deleted` });
    }, `Could not delete ${connector.name}`);
  };

  const created = (connector: Connector) => {
    setAdding(false);
    addToast({
      type: "success",
      title: `${connector.name} added`,
      description: "Connect it to load its tools.",
      action: { label: "Connect", onClick: () => connect(connector, "connect") },
    });
  };

  return (
    <div className="page-wrapper">
      <div className="page-body">
        <div className="mx-auto w-full max-w-5xl min-w-0 space-y-6">
          <header className="space-y-3">
            <div className="flex flex-wrap items-start gap-3">
              <div className="min-w-0 flex-1">
                <h2 className="page-title flex items-center gap-2">
                  <Plug className="size-6 text-brand" aria-hidden /> Connectors
                </h2>
                <p className="page-description">
                  MCP servers whose tools your agent can use: GitHub, Notion, databases, search and more. Their tools
                  still pass permission checks and your approval mode.
                </p>
              </div>
              {!showAdd && (
                <Button onClick={() => setAdding(true)}>
                  <Plus aria-hidden /> Add connector
                </Button>
              )}
            </div>
            {data && <CapabilityBadges capabilities={capabilities} />}
          </header>

          {showAdd && data && (
            <AddConnector
              capabilities={capabilities}
              onCreated={created}
              focusOnOpen={adding === true}
              {...(connectors.length ? { onClose: () => setAdding(false) } : {})}
            />
          )}

          <section aria-labelledby="my-connectors" className="space-y-3">
            <h3 id="my-connectors" className="text-sm font-medium text-muted-foreground">
              Your connectors{connectors.length ? ` (${connectors.length})` : ""}
            </h3>
            {isLoading ? (
              <p className="text-sm text-muted-foreground">Loading…</p>
            ) : error ? (
              <div role="alert" className="flex flex-wrap items-center gap-2 rounded-xl border border-destructive/30 bg-destructive/5 p-4 text-sm">
                <span className="text-destructive">Connectors are unavailable: {error.message}</span>
                <Button size="sm" variant="outline" onClick={() => void refetch()}>Try again</Button>
              </div>
            ) : connectors.length === 0 ? (
              <div className="rounded-xl border border-dashed p-8 text-center">
                <PlugZap className="mx-auto size-8 text-brand" aria-hidden />
                <p className="mt-2 font-medium">No connectors yet</p>
                <p className="text-sm text-muted-foreground">Add one above: a preset is the quickest start.</p>
              </div>
            ) : (
              <div className="space-y-3">
                {connectors.map((connector) => (
                  <ConnectorCard
                    key={connector.id}
                    connector={connector}
                    actions={actions}
                    now={now}
                    busy={busy[connector.id]}
                    waiting={Boolean(waiting[connector.id])}
                    signInUrl={signInUrls[connector.id]}
                    onConnect={connect}
                    onStopWaiting={stopWaiting}
                    onTest={test}
                    onDisconnect={disconnect}
                    onSignOut={(item) => void signOut(item)}
                    onToggle={toggle}
                    onEdit={setEditing}
                    onLogs={setLogsFor}
                    onDelete={(item) => void remove(item)}
                  />
                ))}
              </div>
            )}
          </section>
        </div>
      </div>

      {editing && (
        <EditSheet
          connector={connectors.find((item) => item.id === editing.id) ?? editing}
          capabilities={capabilities}
          actions={actions}
          onClose={() => setEditing(null)}
          onReconnect={(connector) => connect(connector, "connect")}
        />
      )}
      {logsFor && <LogsDialog connector={logsFor} onClose={() => setLogsFor(null)} />}
    </div>
  );
}

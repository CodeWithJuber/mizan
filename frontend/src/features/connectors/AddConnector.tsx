/**
 * Add a connector: a ready preset, a server from the official MCP Registry,
 * or one typed by hand. Choosing a preset or a registry entry fills the
 * Custom form so the person sees and can change everything before adding.
 */
import { useEffect, useRef, useState, type FormEvent } from "react";
import { ExternalLink, LoaderCircle, Search, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { addToast } from "../../components/Toast";
import { useConnectorActions, usePresets, useRegistry } from "./api";
import { ConnectorForm } from "./ConnectorForm";
import {
  type Draft, createBody, draftFromPackage, draftFromPreset, draftFromRemote, emptyDraft, packagePlan, remoteTransport,
  stdioUnavailable, TRANSPORT_LABEL,
} from "./logic";
import { OfficialBadge, ToneBadge } from "./parts";
import type { Capabilities, Connector, Preset, RegistryServer } from "./types";

const AUTH_LABEL: Record<Preset["auth"], string> = { oauth: "OAuth sign-in", headers: "API key", none: "No sign-in" };

function ExternalLinkText({ href, children, label }: { href: string; children: string; label: string }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      aria-label={label}
      className="inline-flex items-center gap-1 rounded text-xs text-muted-foreground underline-offset-4 hover:text-foreground hover:underline focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
    >
      {children} <ExternalLink className="size-3" aria-hidden />
    </a>
  );
}

function PresetGallery({ capabilities, onPick }: { capabilities: Capabilities; onPick: (preset: Preset) => void }) {
  const { data, isLoading, error, refetch } = usePresets();
  const stdioBlocked = stdioUnavailable(capabilities);
  if (isLoading) return <p className="text-sm text-muted-foreground">Loading presets…</p>;
  if (error) {
    return (
      <p className="text-sm text-destructive">
        Could not load presets: {error.message}{" "}
        <Button size="xs" variant="outline" onClick={() => void refetch()}>Try again</Button>
      </p>
    );
  }
  if (!data?.length) {
    return <p className="text-sm text-muted-foreground">This MIZAN has no presets. Search the registry, or add a server by hand under Custom.</p>;
  }
  return (
    <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3" aria-label="Presets">
      {data.map((preset) => {
        const blocked = preset.transport === "stdio" ? stdioBlocked : null;
        return (
          <li key={preset.id} className="flex flex-col gap-2 rounded-xl border bg-background p-4">
            <div className="flex items-start gap-2">
              <h4 className="min-w-0 flex-1 break-words font-medium">{preset.name}</h4>
              {preset.official && <OfficialBadge />}
            </div>
            <p className="flex flex-wrap gap-1.5">
              <ToneBadge tone="muted">{AUTH_LABEL[preset.auth]}</ToneBadge>
              <ToneBadge tone="muted">{TRANSPORT_LABEL[preset.transport]}</ToneBadge>
            </p>
            {preset.description && <p className="line-clamp-3 flex-1 text-xs text-muted-foreground">{preset.description}</p>}
            <div className="mt-auto flex flex-wrap items-center gap-3">
              <Button size="sm" disabled={Boolean(blocked)} aria-label={`Set up ${preset.name}`} onClick={() => onPick(preset)}>
                Set up
              </Button>
              {preset.docs_url && <ExternalLinkText href={preset.docs_url} label={`Docs for ${preset.name}`}>Docs</ExternalLinkText>}
            </div>
            {blocked && <p className="text-xs text-muted-foreground">{blocked}</p>}
          </li>
        );
      })}
    </ul>
  );
}

function RegistryCard({ server, stdioBlocked, onPick }: {
  server: RegistryServer; stdioBlocked: string | null; onPick: (draft: Draft) => void;
}) {
  const title = server.title || server.name;
  const packages = server.packages.slice(0, 3).map((pkg) => {
    const plan = packagePlan(pkg);
    const reason = !plan.ok ? plan.reason : stdioBlocked;
    return { pkg, reason };
  });
  const reasons = [...new Set(packages.flatMap(({ reason }) => (reason ? [reason] : [])))];
  return (
    <li className="flex flex-col gap-2 rounded-xl border bg-background p-4">
      <div className="flex items-start gap-2">
        <div className="min-w-0 flex-1">
          <h4 className="break-words font-medium">{title}</h4>
          <p className="break-all font-mono text-xs text-muted-foreground">
            {server.name}{server.version && ` · v${server.version}`}
          </p>
        </div>
        {server.official && <OfficialBadge />}
      </div>
      {server.description && <p className="line-clamp-3 text-xs text-muted-foreground">{server.description}</p>}
      <div className="mt-auto flex flex-wrap items-center gap-2">
        {server.remotes.slice(0, 2).map((remote) => (
          <Button key={remote.url} size="sm" onClick={() => onPick(draftFromRemote(server, remote))}
            aria-label={`Add ${title} as a remote server (${remoteTransport(remote) === "sse" ? "SSE" : "HTTP"})`}>
            Add remote ({remoteTransport(remote) === "sse" ? "SSE" : "HTTP"})
          </Button>
        ))}
        {packages.map(({ pkg, reason }) => (
          <Button key={`${pkg.registry}:${pkg.identifier}`} size="sm" variant="outline"
            disabled={Boolean(reason)} title={reason ?? undefined}
            aria-label={`Add ${title} as a local server (${pkg.registry || "package"})`}
            onClick={() => {
              const draft = draftFromPackage(server, pkg);
              if (draft) onPick(draft);
            }}>
            Add local ({pkg.registry || "package"})
          </Button>
        ))}
        {server.repository && <ExternalLinkText href={server.repository} label={`Source of ${title}`}>Source</ExternalLinkText>}
      </div>
      {reasons.map((reason) => <p key={reason} className="text-xs text-muted-foreground">{reason}</p>)}
      {server.remotes.length === 0 && server.packages.length === 0 && (
        <p className="text-xs text-muted-foreground">The registry lists no way to run this server.</p>
      )}
    </li>
  );
}

function RegistrySearch({ capabilities, onPick }: { capabilities: Capabilities; onPick: (draft: Draft) => void }) {
  const [text, setText] = useState("");
  const [search, setSearch] = useState("");
  const { data, error, isFetching, isLoading, hasNextPage, fetchNextPage, isFetchingNextPage } = useRegistry(search);
  const servers = data?.pages.flatMap((page) => page.servers) ?? [];
  const stdioBlocked = stdioUnavailable(capabilities);
  const submit = (event: FormEvent) => {
    event.preventDefault();
    setSearch(text.trim());
  };
  return (
    <div className="space-y-3">
      <form aria-label="Search the MCP Registry" className="flex gap-2" onSubmit={submit}>
        <Input
          aria-label="Search the MCP Registry"
          placeholder="Search MCP servers (github, notion, postgres…)"
          value={text}
          onChange={(event) => setText(event.target.value)}
        />
        <Button type="submit" disabled={isFetching && !isFetchingNextPage}>
          {isFetching && !isFetchingNextPage ? <LoaderCircle className="animate-spin" aria-hidden /> : <Search aria-hidden />}
          Search
        </Button>
      </form>
      <p className="text-xs text-muted-foreground">
        From the official MCP Registry. Official marks servers published by the service they connect to.
      </p>
      {error && <p className="text-sm text-destructive">The registry is unavailable right now: {error.message}</p>}
      {isLoading && <p className="text-sm text-muted-foreground">Searching…</p>}
      {!isLoading && !error && servers.length === 0 && (
        <p className="text-sm text-muted-foreground">No servers found{search ? ` for “${search}”` : ""}.</p>
      )}
      {servers.length > 0 && (
        <ul className="grid gap-3 md:grid-cols-2" aria-label="Registry results">
          {servers.map((server) => (
            <RegistryCard key={`${server.name}@${server.version}`} server={server} stdioBlocked={stdioBlocked} onPick={onPick} />
          ))}
        </ul>
      )}
      {hasNextPage && (
        <Button variant="outline" disabled={isFetchingNextPage} onClick={() => void fetchNextPage()}>
          {isFetchingNextPage ? "Loading…" : "Load more"}
        </Button>
      )}
    </div>
  );
}

interface Props {
  capabilities: Capabilities;
  onCreated: (connector: Connector) => void;
  onClose?: () => void;
  /** Move focus to the panel when it opens (the person pressed Add connector). */
  focusOnOpen?: boolean;
}

export function AddConnector({ capabilities, onCreated, onClose, focusOnOpen = false }: Props) {
  const actions = useConnectorActions();
  const [tab, setTab] = useState<string>("presets");
  const [draft, setDraft] = useState<Draft>(() => emptyDraft());
  const [formKey, setFormKey] = useState(0);
  const [busy, setBusy] = useState(false);
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    if (focusOnOpen) heading.current?.focus();
  }, [focusOnOpen]);

  const fill = (next: Draft) => {
    setDraft(next);
    setFormKey((key) => key + 1);
    setTab("custom");
  };

  const add = async () => {
    setBusy(true);
    try {
      const created = await actions.create(createBody(draft));
      setDraft(emptyDraft());
      setFormKey((key) => key + 1);
      setTab("presets");
      onCreated(created);
    } catch (problem) {
      addToast({ type: "error", title: "Could not add the connector", description: problem instanceof Error ? problem.message : undefined });
    } finally {
      setBusy(false);
    }
  };

  return (
    <section aria-labelledby="add-connector-title" className="space-y-4 rounded-xl border bg-card p-4 sm:p-5">
      <div className="flex items-start gap-2">
        <div className="min-w-0 flex-1">
          <h3 id="add-connector-title" ref={heading} tabIndex={-1} className="font-semibold outline-none">Add a connector</h3>
          <p className="text-sm text-muted-foreground">Start from a preset, find a server in the MCP Registry, or enter one yourself.</p>
        </div>
        {onClose && (
          <Button variant="ghost" size="icon-sm" aria-label="Close add connector" onClick={onClose}>
            <X />
          </Button>
        )}
      </div>
      <Tabs value={tab} onValueChange={(value) => setTab(String(value))} className="gap-4">
        <TabsList aria-label="Ways to add a connector" className="max-w-full overflow-x-auto">
          <TabsTrigger value="presets">Presets</TabsTrigger>
          <TabsTrigger value="registry">Registry</TabsTrigger>
          <TabsTrigger value="custom">Custom</TabsTrigger>
        </TabsList>
        <TabsContent value="presets">
          <PresetGallery capabilities={capabilities} onPick={(preset) => fill(draftFromPreset(preset))} />
        </TabsContent>
        <TabsContent value="registry">
          <RegistrySearch capabilities={capabilities} onPick={fill} />
        </TabsContent>
        <TabsContent value="custom">
          <ConnectorForm
            key={formKey}
            idPrefix="add"
            mode="create"
            draft={draft}
            onChange={setDraft}
            capabilities={capabilities}
            busy={busy}
            submitLabel="Add connector"
            onSubmit={() => void add()}
            onCancel={() => {
              setDraft(emptyDraft());
              setFormKey((key) => key + 1);
            }}
            cancelLabel="Clear"
          />
        </TabsContent>
      </Tabs>
    </section>
  );
}

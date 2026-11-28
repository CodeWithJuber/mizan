/**
 * Pure helpers behind the connectors page: argument lines, the add/edit form
 * (a draft), the header/environment key-value editor and the requests built
 * from it. No React here, so every rule is tested in logic.spec.ts.
 */
import type {
  Capabilities, Connector, ConnectorStatus, Preset, RegistryField, RegistryPackage, RegistryRemote, RegistryServer,
  Transport,
} from "./types";

// ----- Argument lines ---------------------------------------------------

/**
 * Split an argument line the way a shell would for plain quoting:
 * whitespace separates, '…' and "…" group (and may sit inside a word:
 * --flag="a b"), a backslash escapes a space, quote or backslash.
 */
export function splitArgs(line: string): string[] {
  const args: string[] = [];
  let current = "";
  let inToken = false;
  let quote: '"' | "'" | null = null;
  const escapable = (ch: string | undefined) => ch !== undefined && /[\s"'\\]/.test(ch);
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (quote) {
      if (ch === quote) quote = null;
      else if (ch === "\\" && quote === '"' && (line[i + 1] === '"' || line[i + 1] === "\\")) current += line[++i];
      else current += ch;
    } else if (/\s/.test(ch)) {
      if (inToken) args.push(current);
      current = "";
      inToken = false;
    } else if (ch === '"' || ch === "'") {
      quote = ch;
      inToken = true;
    } else if (ch === "\\" && escapable(line[i + 1])) {
      current += line[++i];
      inToken = true;
    } else {
      current += ch;
      inToken = true;
    }
  }
  if (inToken) args.push(current);
  return args;
}

/** The inverse of splitArgs: quote only the arguments that need it. */
export function joinArgs(args: string[]): string {
  return args
    .map((arg) => (arg === "" || /[\s"'\\]/.test(arg) ? `"${arg.replace(/(["\\])/g, "\\$1")}"` : arg))
    .join(" ");
}

// ----- Headers and environment variables ---------------------------------

export interface KeyValueRow {
  /** Stable React key. */
  id: string;
  key: string;
  value: string;
  secret: boolean;
  description?: string;
  required?: boolean;
  /** Already saved on the server: its value is never shown or sent back, only replaced or deleted. */
  saved?: boolean;
  mode?: "keep" | "replace" | "delete";
}

let rowSequence = 0;

export function newRow(partial: Partial<KeyValueRow> = {}): KeyValueRow {
  rowSequence += 1;
  return { id: `kv-${rowSequence}`, key: "", value: "", secret: true, ...partial };
}

/** Rows for names a server already holds (edit form). */
export function savedRows(names: string[]): KeyValueRow[] {
  return names.map((key) => newRow({ key, saved: true, mode: "keep", secret: true }));
}

function fieldRows(fields: RegistryField[]): KeyValueRow[] {
  return fields
    .filter((field) => field.name)
    .map((field) => newRow({
      key: field.name, secret: field.secret, required: field.required,
      ...(field.description ? { description: field.description } : {}),
    }));
}

/** POST body: the keyed rows that have a value. */
export function buildSecretMap(rows: KeyValueRow[]): Record<string, string> {
  const map: Record<string, string> = {};
  for (const row of rows) {
    const key = row.key.trim();
    if (!key || row.saved || row.value === "") continue;
    map[key] = row.value;
  }
  return map;
}

/**
 * PATCH body for headers or env, merged per key on the server: a value sets
 * or replaces that key, null deletes it, a key left out is kept as it is.
 * Undefined when nothing changes.
 */
export function buildSecretPatch(rows: KeyValueRow[]): Record<string, string | null> | undefined {
  const patch: Record<string, string | null> = {};
  for (const row of rows) {
    if (!row.saved) continue;
    if (row.mode === "delete") patch[row.key] = null;
    else if (row.mode === "replace" && row.value !== "") patch[row.key] = row.value;
  }
  for (const row of rows) {
    const key = row.key.trim();
    if (row.saved || !key || row.value === "") continue;
    patch[key] = row.value;
  }
  return Object.keys(patch).length ? patch : undefined;
}

const HEADER_NAME = /^[A-Za-z0-9-]{1,100}$/;
const ENV_NAME = /^[A-Za-z_][A-Za-z0-9_]{0,100}$/;

// ----- The add / edit form -------------------------------------------------

export interface Draft {
  name: string;
  transport: Transport;
  url: string;
  command: string;
  args: string;
  source: string;
  headers: KeyValueRow[];
  env: KeyValueRow[];
  oauth: { client_id: string; client_secret: string; scopes: string };
  timeouts: { connect_s: string; call_s: string };
  /** Where this draft came from, shown above the form. */
  origin?: { label: string; docs_url?: string; auth?: Preset["auth"]; official?: boolean };
}

export const emptyDraft = (transport: Transport = "http"): Draft => ({
  name: "", transport, url: "", command: "", args: "", source: "",
  headers: [], env: [],
  oauth: { client_id: "", client_secret: "", scopes: "" },
  timeouts: { connect_s: "", call_s: "" },
});

export const isRemote = (transport: Transport) => transport !== "stdio";

const shortName = (server: RegistryServer) => (server.title || server.name).split("/").pop() || server.name;

export function draftFromPreset(preset: Preset): Draft {
  return {
    ...emptyDraft(preset.transport),
    name: preset.name,
    url: preset.url ?? "",
    command: preset.command ?? "",
    args: joinArgs(preset.args ?? []),
    source: `preset:${preset.id}`,
    headers: preset.auth === "headers" && preset.header_name
      ? [newRow({ key: preset.header_name, secret: true, required: true, ...(preset.header_hint ? { description: preset.header_hint } : {}) })]
      : [],
    origin: { label: preset.name, docs_url: preset.docs_url, auth: preset.auth, official: preset.official },
  };
}

/** The registry's remote types: streamable HTTP, or the older server-sent events. */
export const remoteTransport = (remote: RegistryRemote): Transport => (remote.type === "sse" ? "sse" : "http");

export function draftFromRemote(server: RegistryServer, remote: RegistryRemote): Draft {
  return {
    ...emptyDraft(remoteTransport(remote)),
    name: shortName(server),
    url: remote.url,
    source: server.name,
    headers: fieldRows(remote.headers),
    origin: { label: server.title || server.name, ...(server.repository ? { docs_url: server.repository } : {}), official: server.official },
  };
}

export type PackagePlan =
  | { ok: true; runtime: string; command: string; args: string[]; env: RegistryField[] }
  | { ok: false; reason: string };

const REGISTRY_LABEL: Record<string, string> = { npm: "npm", pypi: "PyPI", oci: "Container image", nuget: "NuGet", mcpb: "MCP bundle" };

/**
 * How to run a registry package: the server's own `install` plan when it sends
 * one, else (older servers) npx for npm and uvx for PyPI only.
 */
export function packagePlan(pkg: RegistryPackage): PackagePlan {
  const label = REGISTRY_LABEL[pkg.registry] ?? (pkg.registry || "This kind of");
  if (pkg.install) {
    if (pkg.install.supported === false || !pkg.install.command) {
      return { ok: false, reason: pkg.install.reason || `${label} packages can't run here yet.` };
    }
    return {
      ok: true,
      runtime: pkg.install.runtime || pkg.registry,
      command: pkg.install.command,
      args: pkg.install.args,
      env: pkg.install.env_vars.length ? pkg.install.env_vars : pkg.env,
    };
  }
  if (!pkg.identifier) return { ok: false, reason: "The registry entry names no package." };
  if (pkg.registry === "npm") {
    return { ok: true, runtime: "node", command: "npx", args: ["-y", pkg.version ? `${pkg.identifier}@${pkg.version}` : pkg.identifier], env: pkg.env };
  }
  if (pkg.registry === "pypi") {
    return { ok: true, runtime: "python", command: "uvx", args: [pkg.version ? `${pkg.identifier}@${pkg.version}` : pkg.identifier], env: pkg.env };
  }
  return { ok: false, reason: `${label} packages can't run here yet.` };
}

export function draftFromPackage(server: RegistryServer, pkg: RegistryPackage): Draft | null {
  const plan = packagePlan(pkg);
  if (!plan.ok) return null;
  return {
    ...emptyDraft("stdio"),
    name: shortName(server),
    command: plan.command,
    args: joinArgs(plan.args),
    source: server.name,
    env: fieldRows(plan.env),
    origin: { label: server.title || server.name, ...(server.repository ? { docs_url: server.repository } : {}), official: server.official },
  };
}

/** Why local (stdio) servers cannot be added here, or null when they can. */
export function stdioUnavailable(caps: Capabilities): string | null {
  if (caps.host_stdio) return null;
  if (!caps.sandbox_stdio) return "Local servers can't run on this MIZAN: the sandbox runner is not enabled.";
  if (caps.runner_available === false) return "The sandbox runner is not answering right now, so local servers can't start.";
  return null;
}

export function draftFromConnector(connector: Connector): Draft {
  return {
    ...emptyDraft(connector.transport),
    name: connector.name,
    url: connector.url,
    command: connector.command,
    args: joinArgs(connector.args),
    source: connector.source,
    headers: savedRows(connector.header_names),
    env: savedRows(connector.env_names),
    oauth: { client_id: connector.auth.client_id ?? "", client_secret: "", scopes: connector.auth.scopes.join(" ") },
    timeouts: {
      connect_s: connector.timeouts.connect_s == null ? "" : String(connector.timeouts.connect_s),
      call_s: connector.timeouts.call_s == null ? "" : String(connector.timeouts.call_s),
    },
  };
}

export type DraftErrors = Partial<Record<"name" | "url" | "command" | "headers" | "env" | "timeouts" | "oauth", string>>;

function rowErrors(rows: KeyValueRow[], kind: "headers" | "env", creating: boolean): string | undefined {
  const seen = new Set<string>();
  const pattern = kind === "headers" ? HEADER_NAME : ENV_NAME;
  for (const row of rows) {
    if (row.saved && row.mode === "delete") continue;
    const key = row.key.trim();
    if (!key) {
      if (row.value) return "Every value needs a name.";
      continue;
    }
    if (!pattern.test(key)) {
      return kind === "headers"
        ? `“${key}” is not a valid header name (letters, digits and hyphens).`
        : `“${key}” is not a valid variable name (letters, digits and _, not starting with a digit).`;
    }
    const folded = kind === "headers" ? key.toLowerCase() : key;
    if (seen.has(folded)) return `“${key}” is listed twice.`;
    seen.add(folded);
    if (kind === "headers" && /[\r\n]/.test(row.value)) return `The value of “${key}” must be one line.`;
    if (creating && row.required && !row.value) return `“${key}” is required.`;
  }
  return undefined;
}

const seconds = (value: string): number | null | "bad" => {
  if (!value.trim()) return null;
  const n = Number(value);
  return Number.isFinite(n) && n > 0 && n <= 3600 ? n : "bad";
};

export function validateDraft(draft: Draft, creating: boolean): DraftErrors {
  const errors: DraftErrors = {};
  if (!draft.name.trim()) errors.name = "Give the connector a name.";
  if (isRemote(draft.transport)) {
    const url = draft.url.trim();
    if (!url) errors.url = "Enter the server's address.";
    else if (!/^https:\/\/[^\s/]+/i.test(url)) errors.url = "Use an https:// address.";
    const headers = rowErrors(draft.headers, "headers", creating);
    if (headers) errors.headers = headers;
  } else {
    if (!draft.command.trim()) errors.command = "Enter the command that starts the server.";
    const env = rowErrors(draft.env, "env", creating);
    if (env) errors.env = env;
  }
  if (seconds(draft.timeouts.connect_s) === "bad" || seconds(draft.timeouts.call_s) === "bad") {
    errors.timeouts = "Timeouts are seconds between 1 and 3600.";
  }
  if (draft.oauth.client_secret && !draft.oauth.client_id.trim()) errors.oauth = "A client secret needs its client ID.";
  return errors;
}

const scopeList = (value: string) => value.split(/[\s,]+/).filter(Boolean);

function timeoutBody(draft: Draft): { connect_s?: number; call_s?: number } | undefined {
  const connect = seconds(draft.timeouts.connect_s);
  const call = seconds(draft.timeouts.call_s);
  const body = {
    ...(typeof connect === "number" ? { connect_s: connect } : {}),
    ...(typeof call === "number" ? { call_s: call } : {}),
  };
  return Object.keys(body).length ? body : undefined;
}

/** POST /api/connectors */
export function createBody(draft: Draft): Record<string, unknown> {
  const body: Record<string, unknown> = { name: draft.name.trim(), transport: draft.transport, source: draft.source };
  if (isRemote(draft.transport)) {
    body.url = draft.url.trim();
    body.headers = buildSecretMap(draft.headers);
    const clientId = draft.oauth.client_id.trim();
    if (clientId) {
      body.oauth = {
        client_id: clientId,
        ...(draft.oauth.client_secret ? { client_secret: draft.oauth.client_secret } : {}),
        ...(scopeList(draft.oauth.scopes).length ? { scopes: scopeList(draft.oauth.scopes) } : {}),
      };
    }
  } else {
    body.command = draft.command.trim();
    body.args = splitArgs(draft.args);
    body.env = buildSecretMap(draft.env);
  }
  const timeouts = timeoutBody(draft);
  if (timeouts) body.timeouts = timeouts;
  return body;
}

const sameList = (a: string[], b: string[]) => a.length === b.length && a.every((item, index) => item === b[index]);

/** PATCH /api/connectors/{id}: only what changed ({} when nothing did). */
export function patchBody(draft: Draft, connector: Connector): Record<string, unknown> {
  const body: Record<string, unknown> = {};
  const name = draft.name.trim();
  if (name !== connector.name) body.name = name;
  if (draft.transport !== connector.transport) body.transport = draft.transport;
  if (isRemote(draft.transport)) {
    const url = draft.url.trim();
    if (url !== connector.url || body.transport) body.url = url;
    const headers = buildSecretPatch(draft.headers);
    if (headers) body.headers = headers;
    const clientId = draft.oauth.client_id.trim();
    const scopes = scopeList(draft.oauth.scopes);
    const before = connector.auth;
    if (!clientId && before.client_id) {
      body.oauth = null;
    } else if (clientId && (clientId !== before.client_id || draft.oauth.client_secret || !sameList(scopes, before.scopes))) {
      body.oauth = {
        client_id: clientId,
        scopes,
        ...(draft.oauth.client_secret ? { client_secret: draft.oauth.client_secret } : {}),
      };
    }
  } else {
    const command = draft.command.trim();
    if (command !== connector.command || body.transport) body.command = command;
    const args = splitArgs(draft.args);
    if (!sameList(args, connector.args) || body.transport) body.args = args;
    const env = buildSecretPatch(draft.env);
    if (env) body.env = env;
  }
  const connect = seconds(draft.timeouts.connect_s);
  const call = seconds(draft.timeouts.call_s);
  if (connect !== "bad" && call !== "bad" && (connect !== connector.timeouts.connect_s || call !== connector.timeouts.call_s)) {
    body.timeouts = { connect_s: connect, call_s: call };
  }
  return body;
}

// ----- Presentation --------------------------------------------------------

export type Tone = "success" | "warning" | "destructive" | "info" | "muted";

export const STATUS_META: Record<ConnectorStatus, { label: string; tone: Tone }> = {
  connected: { label: "Connected", tone: "success" },
  connecting: { label: "Connecting…", tone: "info" },
  disconnected: { label: "Not connected", tone: "muted" },
  error: { label: "Error", tone: "destructive" },
  auth_required: { label: "Sign-in needed", tone: "warning" },
  disabled: { label: "Disabled", tone: "muted" },
};

export const TRANSPORT_LABEL: Record<Transport, string> = {
  http: "Remote · HTTP",
  sse: "Remote · SSE",
  stdio: "Local",
};

const UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ["day", 86_400_000], ["hour", 3_600_000], ["minute", 60_000],
];

/** "in 3 hours" / "2 days ago"; null for a missing or unreadable date. */
export function relativeTime(iso: string | null, now: number): string | null {
  if (!iso) return null;
  const at = Date.parse(iso);
  if (Number.isNaN(at)) return null;
  const delta = at - now;
  const format = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
  for (const [unit, ms] of UNITS) {
    if (Math.abs(delta) >= ms) return format.format(Math.round(delta / ms), unit);
  }
  return delta >= 0 ? "in under a minute" : "just now";
}

/** The auth line under a connector's name. */
export function authSummary(connector: Connector, now: number): { text: string; action: "signin" | "signout" | null } {
  const { auth } = connector;
  if (auth.type === "oauth") {
    if (!auth.signed_in) return { text: "Not signed in", action: "signin" };
    const expiry = relativeTime(auth.expires_at, now);
    const expired = auth.expires_at ? Date.parse(auth.expires_at) <= now : false;
    if (expired) return { text: `Sign-in expired ${expiry}; it renews on the next use when it can`, action: "signin" };
    return { text: expiry ? `Signed in · expires ${expiry}` : "Signed in", action: "signout" };
  }
  if (auth.type === "headers") {
    const names = connector.header_names;
    return { text: names.length ? `Headers: ${names.join(", ")}` : "Uses headers", action: null };
  }
  if (connector.transport === "stdio" && connector.env_names.length) {
    return { text: `Environment: ${connector.env_names.join(", ")}`, action: null };
  }
  return { text: connector.status === "auth_required" ? "Needs sign-in" : "No sign-in", action: connector.status === "auth_required" ? "signin" : null };
}

/** "ls -la" style endpoint line. */
export const endpoint = (connector: Connector) =>
  isRemote(connector.transport) ? connector.url : [connector.command, joinArgs(connector.args)].filter(Boolean).join(" ");

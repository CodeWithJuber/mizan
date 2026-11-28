/**
 * Connectors (Wasl - وَصْل - connection): the shapes GET /api/connectors and
 * the registry return, read defensively so an older server (no `auth`,
 * `counts`, `policy`, …) still renders.
 */

export type ConnectorStatus = "connected" | "connecting" | "disconnected" | "error" | "auth_required" | "disabled";
export type Transport = "http" | "sse" | "stdio";
export type ToolPolicy = "allow" | "ask" | "never";
export type HeldReason = "new" | "changed" | "poisoned";
export type AuthType = "none" | "oauth" | "headers";

export interface ToolSnapshot {
  description: string;
  input_schema: unknown;
  annotations: unknown;
}

export interface ConnectorTool {
  name: string;
  exposed: string;
  description: string;
  read_only: boolean;
  destructive: boolean;
  enabled: boolean;
  /** Amanah holds a tool the agent may not call until the person trusts it. */
  held: boolean;
  held_reason: HeldReason | null;
  /** Appeared since the person last looked. */
  new: boolean;
  policy: ToolPolicy;
  input_schema: unknown;
  annotations: unknown;
  /** What the person accepted before a change (only for changed tools). */
  previous: ToolSnapshot | null;
  /** Excerpts Amanah found aimed at the AI (older servers). */
  amanah: string[];
}

export interface ConnectorAuth {
  type: AuthType;
  signed_in: boolean;
  expires_at: string | null;
  client_id: string | null;
  scopes: string[];
}

export interface ConnectorTimeouts {
  connect_s: number | null;
  call_s: number | null;
}

export interface ToolCounts {
  total: number;
  enabled: number;
  held: number;
  new: number;
}

export interface Connector {
  id: string;
  name: string;
  slug: string;
  transport: Transport;
  url: string;
  command: string;
  args: string[];
  runtime: string;
  enabled: boolean;
  status: ConnectorStatus;
  last_error: string | null;
  source: string;
  header_names: string[];
  env_names: string[];
  auth: ConnectorAuth;
  timeouts: ConnectorTimeouts;
  instructions: string | null;
  counts: ToolCounts;
  tools: ConnectorTool[];
}

export interface Capabilities {
  /** Local (stdio) servers can run in the isolated sandbox runner. */
  sandbox_stdio: boolean;
  /** Local servers may run as a process on the MIZAN server (administrators). */
  host_stdio: boolean;
  /** The sandbox runner answers right now (null: the server did not say). */
  runner_available: boolean | null;
}

export interface Preset {
  id: string;
  name: string;
  description: string;
  transport: Transport;
  url?: string;
  command?: string;
  args?: string[];
  auth: "oauth" | "headers" | "none";
  header_name?: string;
  header_hint?: string;
  docs_url: string;
  official: boolean;
}

export interface RegistryField {
  name: string;
  description: string;
  required: boolean;
  secret: boolean;
}

export interface RegistryInstall {
  runtime: string;
  command: string;
  args: string[];
  env_vars: RegistryField[];
  supported?: boolean;
  reason?: string;
}

export interface RegistryPackage {
  registry: string;
  identifier: string;
  version: string;
  runtime: string;
  env: RegistryField[];
  install?: RegistryInstall;
}

export interface RegistryRemote {
  type: string;
  url: string;
  headers: RegistryField[];
}

export interface RegistryServer {
  name: string;
  title: string;
  description: string;
  version: string;
  repository: string;
  official: boolean;
  remotes: RegistryRemote[];
  packages: RegistryPackage[];
}

export interface ConnectorResource {
  uri: string;
  name: string;
  description: string;
  mime_type: string;
}

export interface PromptArgument {
  name: string;
  description: string;
  required: boolean;
}

export interface ConnectorPrompt {
  name: string;
  description: string;
  arguments: PromptArgument[];
}

export interface TestResult {
  ok: boolean;
  latency_ms: number | null;
  tools: number | null;
  error?: string;
}

type Raw = Record<string, unknown>;

const record = (value: unknown): Raw => (value && typeof value === "object" && !Array.isArray(value) ? value as Raw : {});
const text = (value: unknown, fallback = ""): string => (typeof value === "string" ? value : fallback);
const flag = (value: unknown): boolean => value === true;
const count = (value: unknown): number | null => (typeof value === "number" && Number.isFinite(value) ? value : null);
const strings = (value: unknown): string[] => (Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : []);
const list = (value: unknown): Raw[] => (Array.isArray(value) ? value.map(record) : []);

const STATUSES: ConnectorStatus[] = ["connected", "connecting", "disconnected", "error", "auth_required", "disabled"];
const TRANSPORTS: Transport[] = ["http", "sse", "stdio"];
const POLICIES: ToolPolicy[] = ["allow", "ask", "never"];
const REASONS: HeldReason[] = ["new", "changed", "poisoned"];

function pick<T extends string>(value: unknown, allowed: readonly T[], fallback: T): T {
  return allowed.includes(value as T) ? value as T : fallback;
}

export function normalizeTool(raw: unknown): ConnectorTool {
  const tool = record(raw);
  const enabled = tool.enabled !== false;
  // Older servers: `held` was the reason itself ("changed" | "flagged").
  const legacyHeld = typeof tool.held === "string" ? tool.held : "";
  const held = tool.held === true || Boolean(legacyHeld);
  const reason = REASONS.includes(tool.held_reason as HeldReason)
    ? tool.held_reason as HeldReason
    : legacyHeld === "flagged" ? "poisoned" : legacyHeld === "changed" ? "changed" : null;
  const previous = tool.previous && typeof tool.previous === "object" ? record(tool.previous) : null;
  return {
    name: text(tool.name),
    exposed: text(tool.exposed),
    description: text(tool.description),
    read_only: flag(tool.read_only),
    destructive: flag(tool.destructive),
    enabled,
    held,
    held_reason: held ? reason : null,
    new: flag(tool.new),
    policy: pick(tool.policy, POLICIES, enabled ? "allow" : "never"),
    input_schema: tool.input_schema ?? null,
    annotations: tool.annotations ?? null,
    previous: previous
      ? { description: text(previous.description), input_schema: previous.input_schema ?? null, annotations: previous.annotations ?? null }
      : null,
    amanah: strings(tool.amanah),
  };
}

/** Tools the agent may call: enabled, not held, policy other than never. */
export function usableTools(tools: ConnectorTool[]): number {
  return tools.filter((tool) => tool.enabled && !tool.held && tool.policy !== "never").length;
}

export function normalizeConnector(raw: unknown): Connector {
  const server = record(raw);
  const tools = list(server.tools).map(normalizeTool);
  const headerNames = strings(server.header_names);
  const envNames = strings(server.env_names);
  const enabled = server.enabled !== false;
  const rawStatus = text(server.status);
  const status = STATUSES.includes(rawStatus as ConnectorStatus)
    ? rawStatus as ConnectorStatus
    : !enabled ? "disabled" : "disconnected";
  const auth = record(server.auth);
  const oauthConnected = flag(server.oauth_connected);
  const authType = pick<AuthType>(auth.type, ["none", "oauth", "headers"], oauthConnected ? "oauth" : headerNames.length ? "headers" : "none");
  const timeouts = record(server.timeouts);
  const counts = record(server.counts);
  return {
    id: text(server.id),
    name: text(server.name, "Connector"),
    slug: text(server.slug),
    transport: pick(server.transport, TRANSPORTS, "http"),
    url: text(server.url),
    command: text(server.command),
    args: strings(server.args),
    runtime: text(server.runtime),
    enabled,
    status,
    last_error: text(server.last_error) || null,
    source: text(server.source),
    header_names: headerNames,
    env_names: envNames,
    auth: {
      type: authType,
      signed_in: "signed_in" in auth ? flag(auth.signed_in) : oauthConnected,
      expires_at: text(auth.expires_at) || null,
      client_id: text(auth.client_id) || null,
      scopes: strings(auth.scopes),
    },
    timeouts: { connect_s: count(timeouts.connect_s), call_s: count(timeouts.call_s) },
    instructions: text(server.instructions) || null,
    counts: {
      total: count(counts.total) ?? tools.length,
      // Held tools are not usable, so they never count as enabled.
      enabled: count(counts.enabled) ?? usableTools(tools),
      held: count(counts.held) ?? tools.filter((tool) => tool.held).length,
      new: count(counts.new) ?? tools.filter((tool) => tool.new).length,
    },
    tools,
  };
}

export function normalizeCapabilities(raw: unknown): Capabilities {
  const caps = record(raw);
  return {
    sandbox_stdio: flag(caps.sandbox_stdio),
    host_stdio: flag(caps.host_stdio),
    runner_available: typeof caps.runner_available === "boolean" ? caps.runner_available : null,
  };
}

function field(raw: Raw): RegistryField {
  return { name: text(raw.name), description: text(raw.description), required: flag(raw.required), secret: flag(raw.secret) };
}

export function normalizeRegistryServer(raw: unknown): RegistryServer {
  const server = record(raw);
  return {
    name: text(server.name),
    title: text(server.title) || text(server.name),
    description: text(server.description),
    version: text(server.version),
    repository: text(server.repository),
    official: flag(server.official),
    remotes: list(server.remotes).map((remote) => ({
      type: text(remote.type),
      url: text(remote.url),
      headers: list(remote.headers).map(field),
    })),
    packages: list(server.packages).map((pkg) => {
      const install = pkg.install && typeof pkg.install === "object" ? record(pkg.install) : null;
      return {
        registry: text(pkg.registry),
        identifier: text(pkg.identifier),
        version: text(pkg.version),
        runtime: text(pkg.runtime),
        env: list(pkg.env).map(field),
        ...(install
          ? {
              install: {
                runtime: text(install.runtime),
                command: text(install.command),
                args: strings(install.args),
                env_vars: list(install.env_vars).map(field),
                ...(typeof install.supported === "boolean" ? { supported: install.supported } : {}),
                ...(text(install.reason) ? { reason: text(install.reason) } : {}),
              },
            }
          : {}),
      };
    }),
  };
}

export function normalizePreset(raw: unknown): Preset {
  const preset = record(raw);
  return {
    id: text(preset.id),
    name: text(preset.name),
    description: text(preset.description),
    transport: pick(preset.transport, TRANSPORTS, "http"),
    ...(text(preset.url) ? { url: text(preset.url) } : {}),
    ...(text(preset.command) ? { command: text(preset.command) } : {}),
    ...(Array.isArray(preset.args) ? { args: strings(preset.args) } : {}),
    auth: pick(preset.auth, ["oauth", "headers", "none"] as const, "none"),
    ...(text(preset.header_name) ? { header_name: text(preset.header_name) } : {}),
    ...(text(preset.header_hint) ? { header_hint: text(preset.header_hint) } : {}),
    docs_url: text(preset.docs_url),
    official: flag(preset.official),
  };
}

export function normalizeTest(raw: unknown): TestResult {
  const result = record(raw);
  return {
    ok: flag(result.ok),
    latency_ms: count(result.latency_ms),
    tools: count(result.tools) ?? (Array.isArray(result.tools) ? result.tools.length : null),
    ...(text(result.error) ? { error: text(result.error) } : {}),
  };
}

export function normalizeResources(raw: unknown): ConnectorResource[] {
  return list(record(raw).resources).map((item) => ({
    uri: text(item.uri),
    name: text(item.name) || text(item.uri),
    description: text(item.description),
    mime_type: text(item.mime_type) || text(item.mimeType),
  }));
}

export function normalizePrompts(raw: unknown): ConnectorPrompt[] {
  return list(record(raw).prompts).map((item) => ({
    name: text(item.name),
    description: text(item.description),
    arguments: list(item.arguments).map((arg) => ({
      name: text(arg.name),
      description: text(arg.description),
      required: flag(arg.required),
    })),
  }));
}

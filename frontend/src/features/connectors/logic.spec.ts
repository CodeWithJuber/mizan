import { describe, expect, it } from "vitest";
import {
  authSummary, buildSecretMap, buildSecretPatch, createBody, draftFromConnector, draftFromPackage, draftFromPreset,
  draftFromRemote, emptyDraft, joinArgs, newRow, packagePlan, patchBody, savedRows, splitArgs, stdioUnavailable,
  validateDraft,
} from "./logic";
import { normalizeConnector, normalizeRegistryServer, type RegistryPackage } from "./types";

describe("splitArgs", () => {
  it("splits on whitespace and keeps quoted groups", () => {
    expect(splitArgs("-y  @scope/pkg@1.2.3")).toEqual(["-y", "@scope/pkg@1.2.3"]);
    expect(splitArgs(`--name "two words" 'single quoted'`)).toEqual(["--name", "two words", "single quoted"]);
  });

  it("joins quotes inside a word, as a shell does", () => {
    expect(splitArgs(`--flag="a b" x'y z'`)).toEqual(["--flag=a b", "xy z"]);
  });

  it("keeps an empty quoted argument and escaped characters", () => {
    expect(splitArgs(`a "" b`)).toEqual(["a", "", "b"]);
    expect(splitArgs(String.raw`one\ arg "say \"hi\""`)).toEqual(["one arg", `say "hi"`]);
  });

  it("leaves other backslashes alone (paths)", () => {
    expect(splitArgs(String.raw`C:\tools\server.exe`)).toEqual([String.raw`C:\tools\server.exe`]);
  });

  it("reads an unterminated quote to the end and an empty line as nothing", () => {
    expect(splitArgs(`run "open`)).toEqual(["run", "open"]);
    expect(splitArgs("   ")).toEqual([]);
  });

  it("round-trips through joinArgs", () => {
    const args = ["-y", "pkg", "two words", "", `quote"d`, String.raw`back\slash`];
    expect(splitArgs(joinArgs(args))).toEqual(args);
    expect(joinArgs(["-y", "pkg"])).toBe("-y pkg");
  });
});

describe("headers and environment: the key-value payloads", () => {
  it("a new connector sends the keyed rows that have a value", () => {
    const rows = [newRow({ key: " Authorization ", value: "Bearer x" }), newRow({ key: "Empty", value: "" }), newRow({ key: "", value: "" })];
    expect(buildSecretMap(rows)).toEqual({ Authorization: "Bearer x" });
  });

  it("an edit sends null to delete, a value to replace, and leaves kept keys out", () => {
    const [keep, replace, remove] = savedRows(["KEEP", "REPLACE", "DELETE"]);
    const rows = [
      keep,
      { ...replace, mode: "replace" as const, value: "new-secret" },
      { ...remove, mode: "delete" as const },
      newRow({ key: "ADDED", value: "1" }),
    ];
    expect(buildSecretPatch(rows)).toEqual({ REPLACE: "new-secret", DELETE: null, ADDED: "1" });
  });

  it("a replace left empty keeps the saved value; no change gives undefined", () => {
    const [saved] = savedRows(["TOKEN"]);
    expect(buildSecretPatch([{ ...saved, mode: "replace", value: "" }])).toBeUndefined();
    expect(buildSecretPatch(savedRows(["A", "B"]))).toBeUndefined();
  });

  it("a deleted key added again under the same name gets the new value", () => {
    const [saved] = savedRows(["TOKEN"]);
    expect(buildSecretPatch([{ ...saved, mode: "delete" }, newRow({ key: "TOKEN", value: "fresh" })])).toEqual({ TOKEN: "fresh" });
  });
});

const pkg = (partial: Partial<RegistryPackage>): RegistryPackage => ({
  registry: "npm", identifier: "@acme/mcp", version: "1.0.0", runtime: "", env: [], ...partial,
});

const server = normalizeRegistryServer({
  name: "io.github.acme/mcp", title: "Acme", version: "1.0.0", official: true, repository: "https://github.com/acme/mcp",
  remotes: [{ type: "sse", url: "https://acme.example/sse", headers: [{ name: "X-Api-Key", required: true, secret: true, description: "Your key" }] }],
  packages: [],
});

describe("registry entries become a form", () => {
  it("uses the server's install plan as given", () => {
    const plan = packagePlan(pkg({
      registry: "pypi",
      install: {
        runtime: "python", command: "uvx", args: ["--from", "acme-mcp==1.0.0", "acme-mcp"],
        env_vars: [{ name: "ACME_TOKEN", required: true, secret: true, description: "Token" }],
      },
    }));
    expect(plan).toEqual({
      ok: true, runtime: "python", command: "uvx", args: ["--from", "acme-mcp==1.0.0", "acme-mcp"],
      env: [{ name: "ACME_TOKEN", required: true, secret: true, description: "Token" }],
    });
  });

  it("refuses a package the server says it cannot run, with its reason", () => {
    expect(packagePlan(pkg({ registry: "oci", install: { runtime: "docker", command: "", args: [], env_vars: [], supported: false, reason: "Containers can't run in the sandbox." } })))
      .toEqual({ ok: false, reason: "Containers can't run in the sandbox." });
    expect(packagePlan(pkg({ install: { runtime: "", command: "", args: [], env_vars: [], supported: false } })))
      .toEqual({ ok: false, reason: "npm packages can't run here yet." });
  });

  it("falls back for an older server: npx for npm, uvx for PyPI, nothing for others", () => {
    expect(packagePlan(pkg({}))).toMatchObject({ ok: true, command: "npx", args: ["-y", "@acme/mcp@1.0.0"] });
    expect(packagePlan(pkg({ registry: "pypi", identifier: "acme-mcp", version: "" }))).toMatchObject({ ok: true, command: "uvx", args: ["acme-mcp"] });
    expect(packagePlan(pkg({ registry: "oci", identifier: "ghcr.io/acme/mcp" }))).toEqual({ ok: false, reason: "Container image packages can't run here yet." });
  });

  it("fills a local draft with the command and the package's variables", () => {
    const draft = draftFromPackage(server, pkg({ env: [{ name: "ACME_TOKEN", required: true, secret: true, description: "Token" }] }));
    expect(draft).toMatchObject({ name: "Acme", transport: "stdio", command: "npx", args: "-y @acme/mcp@1.0.0", source: "io.github.acme/mcp" });
    expect(draft?.env.map(({ key, required, secret }) => ({ key, required, secret }))).toEqual([{ key: "ACME_TOKEN", required: true, secret: true }]);
    expect(draftFromPackage(server, pkg({ registry: "nuget" }))).toBeNull();
  });

  it("keeps an SSE remote as SSE (not forced to HTTP)", () => {
    const draft = draftFromRemote(server, server.remotes[0]);
    expect(draft.transport).toBe("sse");
    expect(draft.url).toBe("https://acme.example/sse");
    expect(draft.headers[0]).toMatchObject({ key: "X-Api-Key", required: true, description: "Your key" });
    expect(draft.origin).toMatchObject({ official: true });
  });

  it("a preset asking for a header prefills it", () => {
    const draft = draftFromPreset({
      id: "github", name: "GitHub", description: "", transport: "http", url: "https://api.example/mcp",
      auth: "headers", header_name: "Authorization", header_hint: "Bearer <token>", docs_url: "https://docs.example", official: true,
    });
    expect(draft).toMatchObject({ name: "GitHub", url: "https://api.example/mcp", source: "preset:github" });
    expect(draft.headers[0]).toMatchObject({ key: "Authorization", description: "Bearer <token>", required: true });
  });
});

describe("where local servers may run", () => {
  it("says why a local server cannot be added", () => {
    expect(stdioUnavailable({ host_stdio: true, sandbox_stdio: false, runner_available: null })).toBeNull();
    expect(stdioUnavailable({ host_stdio: false, sandbox_stdio: true, runner_available: true })).toBeNull();
    expect(stdioUnavailable({ host_stdio: false, sandbox_stdio: false, runner_available: null })).toMatch(/not enabled/);
    expect(stdioUnavailable({ host_stdio: false, sandbox_stdio: true, runner_available: false })).toMatch(/not answering/);
  });
});

const existing = normalizeConnector({
  id: "c1", name: "Docs", transport: "http", url: "https://docs.example/mcp", status: "connected", enabled: true,
  header_names: ["Authorization"], env_names: [],
  auth: { type: "headers", signed_in: false, expires_at: null, client_id: null, scopes: [] },
  timeouts: { connect_s: 30, call_s: null }, tools: [],
});

describe("the form's requests", () => {
  it("creates with headers and an OAuth client when given", () => {
    const draft = {
      ...emptyDraft("http"), name: " Docs ", url: "https://docs.example/mcp ",
      headers: [newRow({ key: "Authorization", value: "Bearer t" })],
      oauth: { client_id: "abc", client_secret: "", scopes: "read, write" },
      timeouts: { connect_s: "15", call_s: "" },
    };
    expect(createBody(draft)).toEqual({
      name: "Docs", transport: "http", source: "", url: "https://docs.example/mcp", headers: { Authorization: "Bearer t" },
      oauth: { client_id: "abc", scopes: ["read", "write"] }, timeouts: { connect_s: 15 },
    });
  });

  it("an edit with nothing changed sends nothing", () => {
    expect(patchBody(draftFromConnector(existing), existing)).toEqual({});
  });

  it("an edit sends only what changed, secrets merged per key", () => {
    const draft = draftFromConnector(existing);
    draft.name = "Docs search";
    draft.headers = [{ ...draft.headers[0], mode: "delete" }];
    draft.timeouts = { connect_s: "", call_s: "60" };
    expect(patchBody(draft, existing)).toEqual({
      name: "Docs search", headers: { Authorization: null }, timeouts: { connect_s: null, call_s: 60 },
    });
  });

  it("validation names the field at fault", () => {
    expect(validateDraft({ ...emptyDraft("http"), name: "x", url: "http://plain.example" }, true)).toEqual({ url: "Use an https:// address." });
    const required = { ...emptyDraft("stdio"), name: "x", command: "npx", env: [newRow({ key: "TOKEN", required: true })] };
    expect(validateDraft(required, true).env).toBe("“TOKEN” is required.");
    expect(validateDraft({ ...required, env: [newRow({ key: "1BAD", value: "v" })] }, true).env).toMatch(/not a valid variable name/);
    expect(validateDraft({ ...emptyDraft("http"), name: "x", url: "https://a.example", headers: [newRow({ key: "A", value: "1" }), newRow({ key: "a", value: "2" })] }, true).headers)
      .toBe("“a” is listed twice.");
  });
});

describe("reading an older server", () => {
  it("does not count held tools as enabled, and reads the old held reasons", () => {
    const connector = normalizeConnector({
      id: "c2", name: "Old", transport: "stdio", command: "npx", args: ["-y", "x"], status: "new", oauth_connected: false,
      tools: [
        { name: "a", enabled: true },
        { name: "b", enabled: true, held: "flagged", amanah: ["ignore previous instructions"] },
        { name: "c", enabled: true, held: "changed" },
        { name: "d", enabled: false },
      ],
    });
    expect(connector.status).toBe("disconnected");
    expect(connector.counts).toEqual({ total: 4, enabled: 1, held: 2, new: 0 });
    expect(connector.tools[1]).toMatchObject({ held: true, held_reason: "poisoned", amanah: ["ignore previous instructions"] });
    expect(connector.tools[2]).toMatchObject({ held: true, held_reason: "changed" });
    expect(connector.tools[3].policy).toBe("never");
    expect(connector.auth).toEqual({ type: "none", signed_in: false, expires_at: null, client_id: null, scopes: [] });
  });

  it("an OAuth connection of an older server reads as signed in", () => {
    const connector = normalizeConnector({ id: "c3", name: "OAuth", transport: "http", url: "https://x.example", oauth_connected: true });
    expect(connector.auth).toMatchObject({ type: "oauth", signed_in: true });
    expect(authSummary(connector, Date.now())).toEqual({ text: "Signed in", action: "signout" });
  });

  it("says when the sign-in expires", () => {
    const now = Date.parse("2026-11-28T12:00:00Z");
    const connector = normalizeConnector({
      id: "c4", name: "Linear", transport: "http", url: "https://x.example",
      auth: { type: "oauth", signed_in: true, expires_at: "2026-11-28T15:00:00Z", client_id: null, scopes: [] },
    });
    expect(authSummary(connector, now)).toEqual({ text: "Signed in · expires in 3 hours", action: "signout" });
    expect(authSummary({ ...connector, auth: { ...connector.auth, signed_in: false } }, now).action).toBe("signin");
  });
});

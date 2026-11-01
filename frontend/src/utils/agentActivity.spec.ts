import { describe, expect, it } from "vitest";
import { allowedLabel, reduceActivity, emptyActivity } from "./agentActivity";

describe("allowedLabel", () => {
  it("names a tool the person allowed", () => {
    expect(allowedLabel("workspace_edit")).toBe("Edit files");
    expect(allowedLabel("workspace_run")).toBe("Run commands");
  });

  it("names one action of an action tool", () => {
    expect(allowedLabel("workspace_git:commit")).toBe("Git commit");
    expect(allowedLabel("workspace_sandbox:start")).toBe("Sandbox start");
  });

  it("names a connector tool by its server and tool", () => {
    expect(allowedLabel("mcp__github__create_issue")).toBe("github · create_issue");
  });
});

describe("approval preview", () => {
  it("keeps the new-file and truncated flags of an edit prompt", () => {
    const state = reduceActivity(emptyActivity(), {
      type: "approval_request",
      approval_id: "a1",
      tool: "workspace_write",
      preview: { path: "src/App.tsx", diff: "+x", truncated: true, new_file: true },
    });
    expect(state.approvals[0].preview).toEqual({ path: "src/App.tsx", diff: "+x", truncated: true, newFile: true });
  });

  it("drops a preview without a diff", () => {
    const state = reduceActivity(emptyActivity(), {
      type: "approval_request", approval_id: "a2", tool: "workspace_write", preview: { path: "a" },
    });
    expect(state.approvals[0].preview).toBeUndefined();
  });
});

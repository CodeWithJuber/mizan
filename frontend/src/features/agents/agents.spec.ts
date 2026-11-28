import { describe, expect, it } from "vitest";
import type { Agent } from "../../types";
import { pickSelectedAgent } from "./agents";

const agent = (id: string, extra: Partial<Agent> = {}): Agent => ({
  id, name: id, role: "wakil", state: "resting", nafs_level: 1, total_tasks: 0, success_rate: 0, hikmah_count: 0, tools: [], ...extra,
});

describe("which agent answers", () => {
  const list = [agent("a"), agent("b", { is_default: true }), agent("c")];

  it("is the person's pick while it still exists", () => {
    expect(pickSelectedAgent(list, "c")?.id).toBe("c");
  });

  it("is the person's default agent when nothing (or a deleted agent) was picked", () => {
    expect(pickSelectedAgent(list, null)?.id).toBe("b");
    expect(pickSelectedAgent(list, "gone")?.id).toBe("b");
  });

  it("is the first agent on a server that names no default", () => {
    expect(pickSelectedAgent([agent("a"), agent("c")], null)?.id).toBe("a");
    expect(pickSelectedAgent([], "a")).toBeNull();
    expect(pickSelectedAgent(undefined, null)).toBeNull();
  });
});

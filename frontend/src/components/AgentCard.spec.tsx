import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import type { Agent, AgentMartaba } from "../types";
import { AgentCard, martabaRecord } from "./AgentCard";

const MARTABA: AgentMartaba = {
  stage: 2,
  name: "Assist",
  verified: 23,
  counted: 24,
  pass_rate: 0.958,
  consecutive: 3,
  failures: 0,
  to_next: 17,
  reason: "recorded",
  report_only: true,
};

function agent(extra: Partial<Agent> = {}): Agent {
  return {
    id: "a1",
    name: "Katib",
    role: "katib",
    state: "resting",
    nafs_level: 2,
    total_tasks: 24,
    success_rate: 0.95,
    hikmah_count: 1,
    tools: [],
    ...extra,
  } as Agent;
}

afterEach(cleanup);

describe("AgentCard Martaba stage", () => {
  it("shows the stage badge and the record behind it", () => {
    render(<AgentCard agent={agent({ martaba: MARTABA })} selected={false} onClick={() => undefined} />);
    expect(screen.getByTestId("martaba-stage").textContent).toContain("Stage 2/7 · Assist");
    const record = screen.getByTestId("martaba-record").textContent ?? "";
    expect(record).toContain("23 of 24 checked runs verified");
    expect(record).toContain("17 more in a row for stage 3");
    expect(record).toContain("never limits");
  });

  it("shows nothing for a server that sends no stage", () => {
    render(<AgentCard agent={agent()} selected={false} onClick={() => undefined} />);
    expect(screen.queryByTestId("martaba-stage")).toBeNull();
    expect(screen.queryByTestId("martaba-record")).toBeNull();
  });

  it("words a fresh agent and the top stage plainly", () => {
    expect(martabaRecord({ ...MARTABA, stage: 1, verified: 0, counted: 0, to_next: 20 })).toBe(
      "No checked runs yet; 20 more in a row for stage 2. Shown only: it never limits what the agent may do.",
    );
    expect(martabaRecord({ ...MARTABA, stage: 7, to_next: 0 })).not.toContain("stage 8");
  });
});

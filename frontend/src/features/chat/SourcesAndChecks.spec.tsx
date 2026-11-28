import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { SourcesAndChecks } from "./SourcesAndChecks";
import type { MessageUsageMeta } from "../../types";

const isnad = {
  counts: { sahih: 2, hasan: 1, daif: 1, mawdu: 0 },
  claims: 4,
  supported: 0.75,
  ledger: [
    { text: "Sabr is patience in hardship.", kind: "sentence", grade: "sahih", support: ["Lane's Lexicon"] },
    { text: "A loop prints three numbers.", kind: "sentence", grade: "daif", support: [] },
  ],
};

describe("SourcesAndChecks", () => {
  afterEach(cleanup);

  it("shows nothing when there is nothing to show", () => {
    const { container } = render(<SourcesAndChecks meta={{} as MessageUsageMeta} />);
    expect(container.innerHTML).toBe("");
  });

  it("folds the Isnad grades and usage into one row that opens the details", () => {
    const meta = { model: "m-1", input_tokens: 812, output_tokens: 96, isnad } as unknown as MessageUsageMeta;
    render(<SourcesAndChecks meta={meta} />);
    const row = screen.getByRole("button", { expanded: false });
    expect(row.textContent).toContain("2 verified · 1 supported · 1 model's words only");
    expect(row.textContent).toContain("m-1");
    expect(screen.queryByText("Sources — what supports each claim")).toBeNull();
    fireEvent.click(row);
    expect(screen.getByText("Sources — what supports each claim")).toBeTruthy();
    expect(screen.queryByText("Raw metadata (debug)")).toBeNull();
  });

  it("notes drift from the project's goal only when the alarm is on, and stops nothing", () => {
    const niyyah = {
      scope: "project", goal: "A todo list app", goal_source: "stated", work: 2, drift: 1, cusum: 1.3,
      alarm: true, off_goal: ["workspace_write billing/invoice.py"],
    };
    render(<SourcesAndChecks meta={{ niyyah } as unknown as MessageUsageMeta} />);
    const row = screen.getByRole("button", { expanded: false });
    expect(row.textContent).toContain("Off the project's goal?");
    fireEvent.click(row);
    expect(screen.getByText(/the goal you set: “A todo list app”/)).toBeTruthy();
    expect(screen.getByText("workspace_write billing/invoice.py")).toBeTruthy();
    cleanup();
    const { container } = render(
      <SourcesAndChecks meta={{ niyyah: { ...niyyah, alarm: false } } as unknown as MessageUsageMeta} />,
    );
    expect(container.innerHTML).toBe("");
  });

  it("shows the raw metadata only in debug mode", () => {
    render(<SourcesAndChecks meta={{ model: "m-1" } as MessageUsageMeta} debug />);
    fireEvent.click(screen.getByRole("button"));
    expect(screen.getByText("Raw metadata (debug)")).toBeTruthy();
  });
});

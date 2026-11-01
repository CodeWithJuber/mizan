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
    expect(row.textContent).toContain("2 sahih · 1 hasan · 1 da'if");
    expect(row.textContent).toContain("m-1");
    expect(screen.queryByText("Isnad — what supports each claim")).toBeNull();
    fireEvent.click(row);
    expect(screen.getByText("Isnad — what supports each claim")).toBeTruthy();
    expect(screen.queryByText("Raw metadata (debug)")).toBeNull();
  });

  it("shows the raw metadata only in debug mode", () => {
    render(<SourcesAndChecks meta={{ model: "m-1" } as MessageUsageMeta} debug />);
    fireEvent.click(screen.getByRole("button"));
    expect(screen.getByText("Raw metadata (debug)")).toBeTruthy();
  });
});

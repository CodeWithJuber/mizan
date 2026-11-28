import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { ElicitationPrompt } from "./ElicitationPrompt";

const request = {
  id: "e1",
  server: "github",
  message: "Which repository should I use?",
  schema: {
    type: "object",
    properties: { repo: { type: "string", title: "Repository" }, private: { type: "boolean", title: "Private" } },
    required: ["repo"],
  },
};

describe("ElicitationPrompt", () => {
  afterEach(cleanup);

  it("asks for the fields, checks required ones, and sends the answer", async () => {
    const onAnswer = vi.fn();
    render(<ul><ElicitationPrompt request={request} onAnswer={onAnswer} /></ul>);
    expect(screen.getByText("github asks you")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByText("Required.")).toBeTruthy();
    expect(onAnswer).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText(/Repository/), { target: { value: "acme/site" } });
    fireEvent.click(screen.getByRole("switch", { name: "Private" }));
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(onAnswer).toHaveBeenCalledWith("e1", "accept", { repo: "acme/site", private: true });
  });

  it("declines without content", () => {
    const onAnswer = vi.fn();
    render(<ul><ElicitationPrompt request={request} onAnswer={onAnswer} /></ul>);
    fireEvent.click(screen.getByRole("button", { name: "Decline" }));
    expect(onAnswer).toHaveBeenCalledWith("e1", "decline", undefined);
  });

  it("answers an unsupported schema as raw JSON", () => {
    const onAnswer = vi.fn();
    const raw = { ...request, schema: { type: "object", properties: { tags: { type: "array" } } } };
    render(<ul><ElicitationPrompt request={raw} onAnswer={onAnswer} /></ul>);
    fireEvent.change(screen.getByLabelText("Answer as JSON"), { target: { value: '{"tags": ["a"]}' } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(onAnswer).toHaveBeenCalledWith("e1", "accept", { tags: ["a"] });
  });

  it("shows only the outcome once answered", () => {
    render(<ul><ElicitationPrompt request={{ ...request, decision: "decline" }} /></ul>);
    expect(screen.getByText("github's question declined")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Send" })).toBeNull();
  });
});

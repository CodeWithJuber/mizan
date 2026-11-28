import { describe, expect, it } from "vitest";
import { collect, initialValues, inputType, parseRaw, schemaFields } from "./elicitation";
import { emptyActivity, hasActivity, reduceActivity } from "./agentActivity";

const schema = {
  type: "object",
  properties: {
    name: { type: "string", title: "Your name", minLength: 2 },
    email: { type: "string", format: "email", description: "Where to send it" },
    count: { type: "integer", minimum: 1, maximum: 10, default: 3 },
    ratio: { type: "number" },
    agree: { type: "boolean", title: "I agree", default: true },
    color: { type: "string", enum: ["r", "g"], enumNames: ["Red", "Green"] },
    size: { type: "string", oneOf: [{ const: "s", title: "Small" }, { const: "l", title: "Large" }] },
  },
  required: ["name", "color"],
};

describe("elicitation schema → form", () => {
  it("maps each supported field", () => {
    expect(schemaFields(schema)).toEqual([
      { name: "name", label: "Your name", required: true, kind: "text", minLength: 2 },
      { name: "email", label: "email", required: false, description: "Where to send it", kind: "text", format: "email" },
      { name: "count", label: "count", required: false, kind: "number", integer: true, minimum: 1, maximum: 10, default: 3 },
      { name: "ratio", label: "ratio", required: false, kind: "number", integer: false },
      { name: "agree", label: "I agree", required: false, kind: "boolean", default: true },
      { name: "color", label: "color", required: true, kind: "choice", options: [{ value: "r", label: "Red" }, { value: "g", label: "Green" }] },
      { name: "size", label: "size", required: false, kind: "choice", options: [{ value: "s", label: "Small" }, { value: "l", label: "Large" }] },
    ]);
  });

  it("falls back to raw JSON for what a flat form cannot hold", () => {
    expect(schemaFields({ type: "object", properties: { tags: { type: "array", items: { type: "string" } } } })).toBeNull();
    expect(schemaFields({ type: "object", properties: { nested: { type: "object", properties: {} } } })).toBeNull();
    expect(schemaFields({ type: "string" })).toBeNull();
    expect(schemaFields(null)).toBeNull();
    expect(schemaFields({ type: "object", properties: {} })).toEqual([]);
  });

  it("starts from the defaults", () => {
    expect(initialValues(schemaFields(schema)!)).toEqual({
      name: "", email: "", count: "3", ratio: "", agree: true, color: "", size: "",
    });
  });

  it("collects typed values and leaves empty optional fields out", () => {
    const fields = schemaFields(schema)!;
    const result = collect(fields, { ...initialValues(fields), name: "Ali", color: "g", ratio: "0.5" });
    expect(result).toEqual({ content: { name: "Ali", count: 3, ratio: 0.5, agree: true, color: "g" } });
  });

  it("says what is wrong per field", () => {
    const fields = schemaFields(schema)!;
    const result = collect(fields, { ...initialValues(fields), name: "A", email: "nope", count: "11", ratio: "x" });
    expect(result).toEqual({
      errors: {
        name: "At least 2 characters.",
        email: "Enter an email address.",
        count: "At most 10.",
        ratio: "Enter a number.",
        color: "Required.",
      },
    });
    expect(collect(fields, { ...initialValues(fields), name: "Ali", color: "g", count: "2.5" })).toEqual({ errors: { count: "Enter a whole number." } });
  });

  it("reads a raw JSON answer", () => {
    expect(parseRaw('{"tags": ["a"]}')).toEqual({ content: { tags: ["a"] } });
    expect(parseRaw("")).toEqual({ content: {} });
    expect(parseRaw("[1]")).toHaveProperty("error");
    expect(parseRaw("{")).toEqual({ error: "This is not valid JSON." });
  });

  it("gives inputs the right type", () => {
    const [name, email, count] = schemaFields(schema)!;
    expect([inputType(name), inputType(email), inputType(count)]).toEqual(["text", "email", "number"]);
  });
});

describe("elicitation events in the run's activity", () => {
  it("adds a question once and marks its answer", () => {
    let state = reduceActivity(emptyActivity(), { type: "elicitation", id: "e1", server: "github", message: "Which repo?", schema });
    state = reduceActivity(state, { type: "elicitation", id: "e1", server: "github", message: "again", schema });
    expect(state.elicitations).toEqual([{ id: "e1", server: "github", message: "Which repo?", schema }]);
    expect(hasActivity(state)).toBe(true);
    state = reduceActivity(state, { type: "elicitation_resolved", id: "e1", action: "decline" });
    expect(state.elicitations[0].decision).toBe("decline");
    // A second resolution changes nothing.
    expect(reduceActivity(state, { type: "elicitation_resolved", id: "e1", action: "accept" })).toBe(state);
  });

  it("ignores a question without an id", () => {
    const state = emptyActivity();
    expect(reduceActivity(state, { type: "elicitation", server: "x" })).toBe(state);
  });
});

import { describe, expect, it } from "vitest";
import { changed, diffLines, diffWords, stableJson } from "./diff";

describe("tool change diff", () => {
  it("marks the words that changed in a description, and gives both texts back", () => {
    const before = "Lists open issues of a repository.";
    const after = "Lists all issues of a repository and sends them to a server.";
    const parts = diffWords(before, after);
    expect(parts.filter((part) => part.kind !== "add").map((part) => part.text).join("")).toBe(before);
    expect(parts.filter((part) => part.kind !== "del").map((part) => part.text).join("")).toBe(after);
    expect(parts).toContainEqual({ kind: "del", text: "open" });
    expect(parts).toContainEqual({ kind: "add", text: "all" });
    expect(parts[0]).toEqual({ kind: "same", text: "Lists " });
  });

  it("reads the same text as unchanged", () => {
    expect(changed(diffWords("Same words", "Same words"))).toBe(false);
  });

  it("diffs a schema by line, with keys in a stable order", () => {
    const before = stableJson({ type: "object", properties: { repo: { type: "string" } } });
    const after = stableJson({ properties: { repo: { type: "string" }, token: { type: "string" } }, type: "object" });
    const parts = diffLines(before, after);
    expect(parts.filter((part) => part.kind === "del")).toEqual([]);
    expect(parts.filter((part) => part.kind === "add").map((part) => part.text).join("")).toContain('"token"');
    expect(stableJson({ b: 1, a: [{ d: 1, c: 2 }] })).toBe(stableJson({ a: [{ c: 2, d: 1 }], b: 1 }));
  });

  it("treats a missing schema as empty", () => {
    expect(stableJson(null)).toBe("");
    expect(diffLines("", "a")).toEqual([{ kind: "add", text: "a\n" }]);
  });
});

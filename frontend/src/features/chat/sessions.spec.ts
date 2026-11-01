import { describe, expect, it } from "vitest";
import { chatTitle, groupChats, type ChatSessionRow } from "./sessions";

const row = (id: string, last: string): ChatSessionRow => ({
  session_id: id,
  started_at: last,
  last_message_at: last,
  message_count: 2,
});

describe("chatTitle", () => {
  it("prefers the title the person gave, then the first message", () => {
    expect(chatTitle({ title: " Fiqh of travel ", first_message: "hello" })).toBe("Fiqh of travel");
    expect(chatTitle({ title: "  ", first_message: "Which ayah…" })).toBe("Which ayah…");
    expect(chatTitle({ title: null })).toBe("New chat");
    expect(chatTitle(undefined)).toBe("New chat");
  });
});

describe("groupChats", () => {
  const now = new Date(2026, 9, 28, 15, 0, 0);
  const at = (days: number, hour = 10) => new Date(2026, 9, 28 - days, hour).toISOString();

  it("puts each chat under the day of its last message, newest groups first", () => {
    const groups = groupChats(
      [row("a", at(0)), row("b", at(1)), row("c", at(3)), row("d", at(20)), row("e", at(90))],
      now,
    );
    expect(groups.map((group) => [group.label, group.rows.map((r) => r.session_id)])).toEqual([
      ["Today", ["a"]],
      ["Yesterday", ["b"]],
      ["Previous 7 days", ["c"]],
      ["Previous 30 days", ["d"]],
      ["Older", ["e"]],
    ]);
  });

  it("keeps the order it was given inside a group and leaves out empty groups", () => {
    const groups = groupChats([row("x", at(0, 14)), row("y", at(0, 9))], now);
    expect(groups).toHaveLength(1);
    expect(groups[0].rows.map((r) => r.session_id)).toEqual(["x", "y"]);
  });

  it("puts an unreadable date under Older", () => {
    expect(groupChats([row("z", "not a date")], now)[0].label).toBe("Older");
  });
});

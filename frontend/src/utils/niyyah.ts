/** Niyyah: how a run's work stood against its project's or watcher's goal. Only a note. */

export interface NiyyahNote {
  scope: "project" | "watcher";
  goal: string;
  goal_source: "stated" | "first_request" | "task";
  work: number;
  drift: number;
  cusum: number;
  alarm: boolean;
  off_goal: string[];
}

const record = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

export function isNiyyah(value: unknown): value is NiyyahNote {
  return record(value) && typeof value.goal === "string" && typeof value.alarm === "boolean"
    && typeof value.drift === "number";
}

/** The chip under the answer: shown only when the drift alarm is on. */
export function niyyahHeadline(note: NiyyahNote): string {
  return note.scope === "watcher" ? "Off the watcher's goal?" : "Off the project's goal?";
}

/** Where the goal came from, in words. */
export function goalSource(note: NiyyahNote): string {
  if (note.goal_source === "stated") return "the goal you set";
  if (note.goal_source === "task") return "the watcher's task (no goal set)";
  return "this chat's first request (no goal set)";
}

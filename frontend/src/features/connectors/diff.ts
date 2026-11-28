/**
 * A small diff for "this tool changed since you accepted it": words for the
 * description, lines for its input schema (JSON with sorted keys, so moving a
 * key is not a change). Longest common subsequence; no library.
 */

export interface DiffPart {
  kind: "same" | "add" | "del";
  text: string;
}

/** Cells of the LCS table we are willing to fill (≈ 1500 × 1500 tokens). */
const BUDGET = 2_250_000;

export function diffSequence(before: string[], after: string[]): DiffPart[] {
  // Trim the common start and end: most changes are small.
  let start = 0;
  while (start < before.length && start < after.length && before[start] === after[start]) start++;
  let endA = before.length;
  let endB = after.length;
  while (endA > start && endB > start && before[endA - 1] === after[endB - 1]) {
    endA--;
    endB--;
  }
  const head = before.slice(0, start).map((text): DiffPart => ({ kind: "same", text }));
  const tail = before.slice(endA).map((text): DiffPart => ({ kind: "same", text }));
  const a = before.slice(start, endA);
  const b = after.slice(start, endB);
  let middle: DiffPart[];
  if (a.length * b.length > BUDGET) {
    middle = [...a.map((text): DiffPart => ({ kind: "del", text })), ...b.map((text): DiffPart => ({ kind: "add", text }))];
  } else {
    const width = b.length + 1;
    const table = new Uint32Array((a.length + 1) * width);
    for (let i = a.length - 1; i >= 0; i--) {
      for (let j = b.length - 1; j >= 0; j--) {
        table[i * width + j] = a[i] === b[j]
          ? table[(i + 1) * width + j + 1] + 1
          : Math.max(table[(i + 1) * width + j], table[i * width + j + 1]);
      }
    }
    middle = [];
    let i = 0;
    let j = 0;
    while (i < a.length && j < b.length) {
      if (a[i] === b[j]) {
        middle.push({ kind: "same", text: a[i] });
        i++;
        j++;
      } else if (table[(i + 1) * width + j] >= table[i * width + j + 1]) {
        middle.push({ kind: "del", text: a[i++] });
      } else {
        middle.push({ kind: "add", text: b[j++] });
      }
    }
    while (i < a.length) middle.push({ kind: "del", text: a[i++] });
    while (j < b.length) middle.push({ kind: "add", text: b[j++] });
  }
  return merge([...head, ...middle, ...tail]);
}

/** Join neighbouring parts of one kind ("a", " ", "b" → "a b"). */
function merge(parts: DiffPart[]): DiffPart[] {
  const out: DiffPart[] = [];
  for (const part of parts) {
    const last = out[out.length - 1];
    if (last && last.kind === part.kind) last.text += part.text;
    else out.push({ ...part });
  }
  return out;
}

/** Words and the spaces between them, so the joined parts give the text back. */
export const words = (text: string) => text.split(/(\s+)/).filter((token) => token !== "");

export function diffWords(before: string, after: string): DiffPart[] {
  return diffSequence(words(before), words(after));
}

/** Lines (each with its newline) so merged parts read as blocks. */
export function diffLines(before: string, after: string): DiffPart[] {
  const lines = (text: string) => (text ? text.split("\n").map((line) => `${line}\n`) : []);
  return diffSequence(lines(before), lines(after));
}

function sortKeys(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(sortKeys);
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.keys(value as Record<string, unknown>).sort().map((key) => [key, sortKeys((value as Record<string, unknown>)[key])]),
    );
  }
  return value;
}

/** Pretty JSON with keys in order; "" for null/undefined. */
export function stableJson(value: unknown): string {
  if (value === null || value === undefined) return "";
  try {
    return JSON.stringify(sortKeys(value), null, 2);
  } catch {
    return String(value);
  }
}

export const changed = (parts: DiffPart[]) => parts.some((part) => part.kind !== "same");

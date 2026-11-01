/** Mahw: what MIZAN removed when you deleted a chat or forgot notes, and what it checked. */

export interface MahwReceipt {
  kind: "chat" | "notes";
  removed: Record<string, number>;
  checked: number;
  traces: number;
  traces_by_store?: Record<string, number>;
  kept?: string[];
  outside?: string[];
}

const record = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

export function isReceipt(value: unknown): value is MahwReceipt {
  return record(value) && record(value.removed) && typeof value.checked === "number" && typeof value.traces === "number";
}

/** "messages 12 · summary 1 · notes 2" in the order the server listed them. */
export function removedLine(receipt: MahwReceipt): string {
  return Object.entries(receipt.removed)
    .filter(([, count]) => count > 0)
    .map(([store, count]) => `${store} ${count}`)
    .join(" · ");
}

/** One plain sentence about the check that followed the erasure. */
export function checkLine(receipt: MahwReceipt): string {
  if (receipt.traces === 0)
    return `Checked ${receipt.checked} times across your stores: nothing of it is left.`;
  const where = Object.keys(receipt.traces_by_store ?? {}).join(", ");
  const copies = receipt.traces === 1 ? "1 copy remains" : `${receipt.traces} copies remain`;
  return `Checked ${receipt.checked} times: ${copies}${where ? ` in ${where}` : ""}, saved separately. Forget them in your Daftar.`;
}

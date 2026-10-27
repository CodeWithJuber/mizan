/**
 * Daftar: everything MIZAN keeps about you in one list, each entry with where
 * it came from and when it was made and last used. Notes and preferences can
 * be edited and forgotten one by one or by topic (after a preview); the whole
 * ledger exports as Markdown or JSON, and a JSON export imports elsewhere.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import type { ApiClient } from "../types";
import { config } from "../config";
import { authFetch } from "../utils/authFetch";
import { useToast } from "./Toast";
import { checkLine, isReceipt } from "../utils/mahw.ts";
import { KINDS, expiryIn, isLedger, provenance, type DaftarEntry, type EntryKind, type Ledger } from "../utils/daftar.ts";

const KIND_BADGE: Record<EntryKind, { label: string; style: string }> = {
  note: { label: "Note", style: "badge-info" },
  preference: { label: "Preference", style: "badge-gold" },
  summary: { label: "Chat summary", style: "badge-success" },
  learned: { label: "Learned", style: "badge-warning" },
};

export default function DaftarPanel({ api }: { api: ApiClient }) {
  const { addToast } = useToast();
  const [ledger, setLedger] = useState<Ledger>({ entries: [], counts: {} });
  const [kind, setKind] = useState<EntryKind | "">("");
  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState<{ id: string; text: string } | null>(null);
  const [draft, setDraft] = useState({ content: "", tags: "", days: 0 });
  const [topic, setTopic] = useState("");
  const [preview, setPreview] = useState<DaftarEntry[] | null>(null);
  const [busy, setBusy] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    try {
      const params = new URLSearchParams({ query, kind });
      const data = await api.get(`/daftar?${params.toString()}`);
      if (isLedger(data)) setLedger(data);
    } catch {
      addToast({ type: "error", title: "Your ledger could not be loaded" });
    }
  }, [api, query, kind, addToast]);

  useEffect(() => {
    load();
  }, [load]);

  const act = async (action: () => Promise<unknown>, done: string) => {
    setBusy(true);
    try {
      const result = await action();
      // Forgetting notes returns Mahw's receipt: what was removed and checked.
      const receipt = (result as { receipt?: unknown } | undefined)?.receipt;
      addToast(
        isReceipt(receipt)
          ? { type: receipt.traces ? "warning" : "success", title: done, description: checkLine(receipt) }
          : { type: "success", title: done },
      );
      await load();
    } catch (error) {
      addToast({ type: "error", title: "That did not work", description: (error as Error).message });
    } finally {
      setBusy(false);
    }
  };

  const addNote = () =>
    act(async () => {
      await api.post("/daftar", {
        content: draft.content.trim(),
        tags: draft.tags.split(",").map((t) => t.trim()).filter(Boolean),
        expires: expiryIn(draft.days),
      });
      setDraft({ content: "", tags: "", days: 0 });
    }, "MIZAN will remember this");

  const saveEdit = () =>
    editing &&
    act(async () => {
      await api.patch(`/daftar/${encodeURIComponent(editing.id)}`, { content: editing.text.trim() });
      setEditing(null);
    }, "Updated");

  const forgetOne = (entry: DaftarEntry) =>
    act(() => api.post("/daftar/forget", { ids: [entry.id] }), "Forgotten");

  const previewTopic = async () => {
    if (!topic.trim()) return;
    const data = await api.post("/daftar/forget", { topic: topic.trim() });
    setPreview((data.preview as DaftarEntry[]) ?? []);
  };

  const forgetTopic = () =>
    act(async () => {
      const result = await api.post("/daftar/forget", { topic: topic.trim(), confirm: true });
      setPreview(null);
      setTopic("");
      return result;
    }, `Forgot everything about "${topic.trim()}"`);

  const download = async (format: "md" | "json") => {
    const response = await authFetch(`${config.API_URL}/daftar/export?format=${format}`);
    if (!response.ok) {
      addToast({ type: "error", title: "Export failed" });
      return;
    }
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement("a");
    link.href = url;
    link.download = `mizan-daftar.${format}`;
    link.click();
    URL.revokeObjectURL(url);
  };

  const importFile = (file: File | undefined) =>
    file &&
    act(async () => {
      const data = JSON.parse(await file.text());
      const result = await api.post("/daftar/import", data);
      const imported = result.imported as Record<string, number> | undefined;
      if (imported?.skipped) {
        addToast({ type: "info", title: `${imported.skipped} entries were skipped (empty, invalid or carrying instructions)` });
      }
    }, "Imported");

  return (
    <section className="mx-5 mt-3 space-y-3" aria-label="Daftar: what MIZAN keeps about you">
      <div className="card space-y-3">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="text-xxs font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-widest">
              Daftar · دفتر
            </div>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
              Everything MIZAN keeps about you, with where it came from. Change or forget anything; take it with you.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button className="btn-secondary btn-sm" onClick={() => download("md")}>Export Markdown</button>
            <button className="btn-secondary btn-sm" onClick={() => download("json")}>Export JSON</button>
            <button className="btn-secondary btn-sm" onClick={() => fileInput.current?.click()} disabled={busy}>
              Import
            </button>
            <input
              ref={fileInput}
              type="file"
              accept="application/json,.json"
              className="hidden"
              onChange={(event) => {
                importFile(event.target.files?.[0]);
                event.target.value = "";
              }}
            />
          </div>
        </div>

        <div className="flex flex-wrap gap-1" role="tablist" aria-label="Kinds">
          {KINDS.map((item) => {
            const count = item.key ? ledger.counts[item.key] ?? 0 : Object.values(ledger.counts).reduce((a, b) => a + (b ?? 0), 0);
            return (
              <button
                key={item.key || "all"}
                role="tab"
                aria-selected={kind === item.key}
                className={`px-3 py-1.5 text-xs font-medium rounded-lg border transition-colors ${
                  kind === item.key
                    ? "bg-mizan-gold/10 text-mizan-gold border-mizan-gold/20"
                    : "text-gray-500 dark:text-gray-400 border-transparent hover:bg-gray-100 dark:hover:bg-zinc-800"
                }`}
                onClick={() => setKind(item.key)}
              >
                {item.label} {count > 0 && <span className="font-mono">{count}</span>}
              </button>
            );
          })}
          <span className="flex-1" />
          <input
            className="input text-sm py-1.5 w-full sm:w-56"
            placeholder="Search your ledger…"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            aria-label="Search your ledger"
          />
        </div>

        <div className="rounded-lg border border-gray-200 dark:border-zinc-700 p-3 space-y-2">
          <textarea
            className="input w-full h-16 resize-none text-sm"
            placeholder="Something MIZAN should remember about you…"
            value={draft.content}
            onChange={(event) => setDraft({ ...draft, content: event.target.value })}
          />
          <div className="flex flex-wrap items-center gap-2">
            <input
              className="input text-sm py-1.5 w-full sm:w-44"
              placeholder="Tags (comma-separated)"
              value={draft.tags}
              onChange={(event) => setDraft({ ...draft, tags: event.target.value })}
            />
            <label className="text-xs text-gray-500 dark:text-gray-400 flex items-center gap-1">
              Forget after
              <select
                className="input text-sm py-1"
                value={draft.days}
                onChange={(event) => setDraft({ ...draft, days: Number(event.target.value) })}
              >
                <option value={0}>never</option>
                <option value={1}>1 day</option>
                <option value={7}>1 week</option>
                <option value={30}>1 month</option>
                <option value={365}>1 year</option>
              </select>
            </label>
            <span className="flex-1" />
            <button className="btn-gold btn-sm" disabled={busy || !draft.content.trim()} onClick={addNote}>
              Remember this
            </button>
          </div>
        </div>
      </div>

      <ul className="space-y-2">
        {ledger.entries.length === 0 && (
          <li className="text-sm text-gray-400 dark:text-gray-500 text-center py-6">
            {query ? "Nothing about that." : "MIZAN keeps nothing about you yet."}
          </li>
        )}
        {ledger.entries.map((entry) => (
          <li key={entry.id} className="card space-y-1.5">
            <div className="flex flex-wrap items-center gap-2">
              <span className={KIND_BADGE[entry.kind].style}>{KIND_BADGE[entry.kind].label}</span>
              {entry.key && <span className="font-mono text-xs text-gray-500">{entry.key}</span>}
              {entry.tags?.map((tag) => (
                <span key={tag} className="text-micro font-mono px-1.5 py-0.5 rounded bg-gray-100 dark:bg-zinc-800 text-gray-500">
                  {tag}
                </span>
              ))}
            </div>
            {editing?.id === entry.id ? (
              <div className="space-y-2">
                <textarea
                  className="input w-full h-20 resize-none text-sm"
                  value={editing.text}
                  onChange={(event) => setEditing({ id: entry.id, text: event.target.value })}
                  aria-label="Edit entry"
                />
                <div className="flex gap-2">
                  <button className="btn-gold btn-sm" disabled={busy || !editing.text.trim()} onClick={saveEdit}>
                    Save
                  </button>
                  <button className="btn-secondary btn-sm" onClick={() => setEditing(null)}>
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <p className="text-sm text-gray-900 dark:text-gray-100 whitespace-pre-wrap wrap-break-word line-clamp-6">
                {entry.content}
              </p>
            )}
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-micro text-gray-400 dark:text-gray-500">{provenance(entry)}</span>
              <span className="flex-1" />
              {entry.editable && editing?.id !== entry.id && (
                <>
                  <button className="btn-ghost btn-sm" onClick={() => setEditing({ id: entry.id, text: entry.content })}>
                    Edit
                  </button>
                  <button className="btn-ghost btn-sm" disabled={busy} onClick={() => forgetOne(entry)}>
                    Forget
                  </button>
                </>
              )}
              {entry.kind === "learned" && <span className="text-micro text-gray-400">Manage in Majlis → Learning</span>}
            </div>
          </li>
        ))}
      </ul>

      <div className="card space-y-2">
        <div className="text-xxs font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-widest">
          Forget a topic
        </div>
        <div className="flex flex-wrap gap-2">
          <input
            className="input text-sm py-1.5 flex-1 min-w-0"
            placeholder="For example: my old job"
            value={topic}
            onChange={(event) => {
              setTopic(event.target.value);
              setPreview(null);
            }}
          />
          <button className="btn-secondary btn-sm" disabled={!topic.trim()} onClick={previewTopic}>
            Show what would go
          </button>
        </div>
        {preview && (
          <div className="space-y-2">
            {preview.length === 0 ? (
              <p className="text-sm text-gray-400">No notes or preferences about that.</p>
            ) : (
              <>
                <ul className="text-sm list-disc pl-5 text-gray-700 dark:text-gray-300">
                  {preview.map((entry) => (
                    <li key={entry.id} className="wrap-break-word">
                      {entry.key ? `${entry.key}: ` : ""}
                      {entry.content.slice(0, 160)}
                    </li>
                  ))}
                </ul>
                <button className="btn-danger btn-sm" disabled={busy} onClick={forgetTopic}>
                  Forget these {preview.length}
                </button>
              </>
            )}
          </div>
        )}
      </div>
    </section>
  );
}

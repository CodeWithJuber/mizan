/**
 * ArtifactsPanel.tsx — slide-over panel listing the session's artifacts.
 *
 * Each artifact card has:
 *  - Preview/Code toggle (Sandpack preview vs editor for code; locked-down
 *    iframe vs raw source for HTML/markdown — see ArtifactPreview.tsx).
 *  - Version dropdown (v1, v2, …) with per-version preview; "Restore" appends
 *    the old content as a NEW version (non-destructive, no confirm needed).
 *
 * Artifacts arrive over the chat WebSocket as {"type": "artifact", ...}
 * (handled in App.tsx); the panel lazily loads version history from
 * GET /api/artifacts/{id}/versions and can also backfill the session list
 * from GET /api/artifacts/?session_id=… (e.g. after a page reload).
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { ArtifactPreview } from "./ArtifactPreview.tsx";
import { useToast } from "./Toast.tsx";
import { config } from "../config.ts";
import { authFetch } from "../utils/authFetch.ts";
import type { Artifact, ArtifactKind, ArtifactVersion } from "../types.ts";

interface ArtifactsPanelProps {
  artifacts: Artifact[]; // WS-arrived, newest last
  sessionId: string;
  onClose: () => void;
}

const KIND_LABEL: Record<ArtifactKind, string> = {
  code: "Code",
  html: "HTML",
  markdown: "Docs",
};

const KIND_BADGE: Record<ArtifactKind, string> = {
  code: "bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-300",
  html: "bg-orange-100 text-orange-700 dark:bg-orange-500/15 dark:text-orange-300",
  markdown:
    "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300",
};

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await authFetch(`${config.API_URL}/artifacts${path}`, init);
  if (!res.ok)
    throw new Error(`artifacts API ${res.status}: ${await res.text()}`);
  return (await res.json()) as T;
}

export function ArtifactsPanel({
  artifacts,
  sessionId,
  onClose,
}: ArtifactsPanelProps) {
  const { addToast } = useToast();
  const [listed, setListed] = useState<Artifact[]>([]);
  const [versions, setVersions] = useState<Record<string, ArtifactVersion[]>>(
    {},
  );
  const [loadingVersions, setLoadingVersions] = useState<
    Record<string, boolean>
  >({});
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [view, setView] = useState<Record<string, "preview" | "code">>({});
  const [selectedVersion, setSelectedVersion] = useState<
    Record<string, number>
  >({});
  const [restoring, setRestoring] = useState(false);

  // Merge WS artifacts with the server-side session list (dedup by id).
  const all = [
    ...listed,
    ...artifacts.filter((a) => !listed.some((l) => l.id === a.id)),
  ];

  useEffect(() => {
    let cancelled = false;
    api<Array<Omit<Artifact, "versions">>>(
      `/?session_id=${encodeURIComponent(sessionId)}`,
    )
      .then((items) => {
        if (cancelled) return;
        setListed(items.map((a) => ({ ...a, versions: [] })));
        if (items.length > 0)
          setExpandedId((prev) => prev ?? items[items.length - 1].id);
      })
      .catch(() => {
        /* panel still shows WS-arrived artifacts */
      });
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  const cancelledRef = useRef(false);
  useEffect(() => {
    cancelledRef.current = false;
    return () => {
      cancelledRef.current = true;
    };
  }, []);

  const ensureVersions = useCallback(
    async (artifact: Artifact) => {
      if (versions[artifact.id]) return;
      setLoadingVersions((p) => ({ ...p, [artifact.id]: true }));
      try {
        // Seed v1 from the WS payload when present so the panel works offline.
        const seeded: ArtifactVersion[] = artifact.versions ?? [];
        const fetched = await api<ArtifactVersion[]>(
          `/${artifact.id}/versions`,
        );
        const merged = fetched.length > 0 ? fetched : seeded;
        if (!cancelledRef.current) {
          setVersions((p) => ({ ...p, [artifact.id]: merged }));
          if (merged.length > 0) {
            setSelectedVersion((p) => ({
              ...p,
              [artifact.id]: merged[merged.length - 1].version,
            }));
          }
        }
      } catch {
        if (!cancelledRef.current && artifact.versions?.length) {
          setVersions((p) => ({ ...p, [artifact.id]: artifact.versions }));
          setSelectedVersion((p) => ({
            ...p,
            [artifact.id]: artifact.versions[0].version,
          }));
        }
      } finally {
        setLoadingVersions((p) => ({ ...p, [artifact.id]: false }));
      }
    },
    [versions],
  );

  const toggleExpand = (artifact: Artifact) => {
    const next = expandedId === artifact.id ? null : artifact.id;
    setExpandedId(next);
    if (next) void ensureVersions(artifact);
  };

  const handleRestore = async (artifact: Artifact) => {
    const vers = versions[artifact.id] ?? [];
    const sel = selectedVersion[artifact.id] ?? vers[vers.length - 1]?.version;
    const target = vers.find((v) => v.version === sel);
    if (!target) return;
    setRestoring(true);
    try {
      const res = await api<{ id: string; version: number }>(
        `/${artifact.id}/versions`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ content: target.content }),
        },
      );
      const refreshed = await api<ArtifactVersion[]>(
        `/${artifact.id}/versions`,
      );
      setVersions((p) => ({ ...p, [artifact.id]: refreshed }));
      setSelectedVersion((p) => ({ ...p, [artifact.id]: res.version }));
      addToast({
        type: "success",
        title: `Restored v${sel} as v${res.version}`,
        description: artifact.title,
      });
    } catch {
      addToast({ type: "error", title: "Restore failed — dobara try karo" });
    } finally {
      setRestoring(false);
    }
  };

  const currentContent = (artifact: Artifact): ArtifactVersion | undefined => {
    const vers = versions[artifact.id] ?? artifact.versions ?? [];
    const sel = selectedVersion[artifact.id];
    return vers.find((v) => v.version === sel) ?? vers[vers.length - 1];
  };

  return (
    <div className="fixed inset-y-0 right-0 w-full sm:w-[520px] bg-white dark:bg-zinc-900 border-l border-gray-200 dark:border-zinc-700 shadow-2xl z-50 flex flex-col animate-slide-in-right">
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 dark:border-zinc-700">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
            Artifacts
          </h2>
          <span className="text-[11px] px-1.5 py-0.5 rounded-full bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300 font-mono">
            {all.length}
          </span>
        </div>
        <button
          onClick={onClose}
          className="p-2 rounded-lg text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-zinc-800 transition-colors"
          title="Close artifacts"
        >
          <svg viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4">
            <path d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z" />
          </svg>
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-3">
        {all.length === 0 && (
          <div className="text-center text-sm text-gray-400 dark:text-gray-500 py-12">
            No artifacts yet.
            <br />
            <span className="text-xs">
              Jab agent code/HTML/docs banayega, woh yahan aayega.
            </span>
          </div>
        )}
        {all.map((artifact) => {
          const expanded = expandedId === artifact.id;
          const vers = versions[artifact.id] ?? artifact.versions ?? [];
          const cur = currentContent(artifact);
          const v = view[artifact.id] ?? "preview";
          return (
            <div
              key={artifact.id}
              className="border border-gray-200 dark:border-zinc-700 rounded-xl overflow-hidden bg-white dark:bg-zinc-900"
            >
              <button
                onClick={() => toggleExpand(artifact)}
                className="w-full flex items-center gap-2 px-3 py-2.5 text-left hover:bg-gray-50 dark:hover:bg-zinc-800/60 transition-colors"
              >
                <svg
                  viewBox="0 0 20 20"
                  fill="currentColor"
                  className={`w-3.5 h-3.5 text-gray-400 transition-transform ${expanded ? "rotate-90" : ""}`}
                >
                  <path
                    fillRule="evenodd"
                    d="M7.21 14.77a.75.75 0 01.02-1.06L11.168 10 7.23 6.29a.75.75 0 111.04-1.08l4.5 4.25a.75.75 0 010 1.08l-4.5 4.25a.75.75 0 01-1.06-.02z"
                    clipRule="evenodd"
                  />
                </svg>
                <span className="min-w-0 flex-1 text-sm font-medium text-gray-800 dark:text-gray-200 truncate">
                  {artifact.title}
                </span>
                <span
                  className={`text-[10px] px-1.5 py-0.5 rounded-full font-semibold ${KIND_BADGE[artifact.kind] ?? KIND_BADGE.markdown}`}
                >
                  {KIND_LABEL[artifact.kind] ?? artifact.kind}
                </span>
                {vers.length > 0 && (
                  <span className="text-[10px] font-mono text-gray-400">
                    v{vers[vers.length - 1].version}
                  </span>
                )}
              </button>

              {expanded && (
                <div className="px-3 pb-3">
                  <div className="flex items-center gap-2 mb-2 flex-wrap">
                    <div className="flex rounded-lg overflow-hidden border border-gray-200 dark:border-zinc-700 text-xs">
                      {(["preview", "code"] as const).map((mode) => (
                        <button
                          key={mode}
                          onClick={() =>
                            setView((p) => ({ ...p, [artifact.id]: mode }))
                          }
                          className={`px-2.5 py-1 capitalize transition-colors ${
                            v === mode
                              ? "bg-amber-500 text-white"
                              : "text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-zinc-800"
                          }`}
                        >
                          {mode}
                        </button>
                      ))}
                    </div>
                    {vers.length > 1 && (
                      <>
                        <select
                          value={
                            selectedVersion[artifact.id] ??
                            vers[vers.length - 1]?.version ??
                            1
                          }
                          onChange={(e) =>
                            setSelectedVersion((p) => ({
                              ...p,
                              [artifact.id]: Number(e.target.value),
                            }))
                          }
                          className="text-xs rounded-lg border border-gray-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 px-2 py-1 text-gray-700 dark:text-gray-300"
                          title="Version history"
                        >
                          {vers.map((ver) => (
                            <option key={ver.version} value={ver.version}>
                              v{ver.version}
                              {ver.created_at
                                ? ` — ${new Date(ver.created_at).toLocaleString()}`
                                : ""}
                            </option>
                          ))}
                        </select>
                        <button
                          onClick={() => void handleRestore(artifact)}
                          disabled={restoring}
                          className="text-xs px-2.5 py-1 rounded-lg border border-gray-200 dark:border-zinc-700 text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-zinc-800 disabled:opacity-50 transition-colors"
                          title="Restore this version as a new version (non-destructive)"
                        >
                          {restoring ? "Restoring…" : "Restore"}
                        </button>
                      </>
                    )}
                    {loadingVersions[artifact.id] && (
                      <span className="text-[11px] text-gray-400">
                        Loading versions…
                      </span>
                    )}
                  </div>
                  {cur ? (
                    <ArtifactPreview
                      kind={artifact.kind}
                      language={artifact.language}
                      content={cur.content}
                      view={v}
                      title={`${artifact.title} — v${cur.version}`}
                    />
                  ) : (
                    <div className="text-xs text-gray-400 py-6 text-center">
                      No content loaded.
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

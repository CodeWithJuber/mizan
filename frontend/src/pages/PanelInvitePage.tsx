/**
 * The human panel, answered alone (/panel/<code>): a person the administrator
 * invited answers the AGI test's text items with no account. The code in the
 * link is the only credential; the first answer to an item is final and no
 * verdict is shown, so the panel measures what people do on a first try.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { config } from "../config";
import { useTheme } from "../hooks/useTheme";
import { inviteCode } from "../utils/imtihan.ts";

interface PanelTask {
  id: string;
  faculty: string;
  prompt: string;
  history: { role: string; content: string }[];
}

interface InviteView {
  person: string;
  expires: number;
  faculties: { key: string; name: string }[];
  tasks: PanelTask[];
  answered: string[];
}

export default function PanelInvitePage() {
  useTheme();
  const code = inviteCode(window.location.pathname) ?? "";
  const url = `${config.API_URL}/public/panel/${code}`;
  const [view, setView] = useState<InviteView | null>(null);
  const [error, setError] = useState("");
  const [faculty, setFaculty] = useState("");
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const response = await fetch(url);
      if (!response.ok) throw new Error(response.status === 404 ? "expired" : response.statusText);
      const body = (await response.json()) as InviteView;
      setView(body);
      setFaculty((current) => current || body.faculties[0]?.key || "");
    } catch (exc) {
      setError(
        exc instanceof Error && exc.message === "expired"
          ? "This link is not valid or has expired. Ask the person who sent it for a new one."
          : "The items could not be loaded; try again in a minute.",
      );
    }
  }, [url]);

  useEffect(() => {
    document.title = "MIZAN · Human panel";
    void load();
  }, [load]);

  const done = useMemo(() => new Set(view?.answered ?? []), [view]);
  const shown = (view?.tasks ?? []).filter((task) => task.faculty === faculty);
  const filled = Object.entries(answers).filter(([id, text]) => text.trim() && !done.has(id));

  const submit = async () => {
    if (filled.length === 0) return;
    setBusy(true);
    setError("");
    try {
      const response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ answers: Object.fromEntries(filled) }),
      });
      if (!response.ok) throw new Error(response.statusText);
      const body = (await response.json()) as { answered: string[] };
      setView((current) => (current ? { ...current, answered: body.answered } : current));
      setAnswers({});
    } catch {
      setError("The answers could not be saved; try again.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-mizan-dark text-gray-900 dark:text-gray-100">
      <main className="max-w-3xl mx-auto px-4 py-8 space-y-5">
        <header className="space-y-2">
          <div className="text-sm text-amber-700 dark:text-amber-400">ميزان MIZAN · Human panel</div>
          <h1 className="text-2xl font-semibold">Answer as yourself</h1>
          <p className="text-sm text-gray-600 dark:text-gray-400">
            These are the same items MIZAN and a base AI model answer. Please answer each one on your own, without
            asking an AI or searching. Your first answer to an item is kept and is final; you will not be told whether
            it was right. You can stop at any time and come back with the same link.
            {view && ` You answer as ${view.person}; nothing else about you is kept.`}
          </p>
        </header>

        {error && <div className="card p-4 text-sm text-red-600 dark:text-red-400">{error}</div>}
        {!view && !error && <div className="card p-4 text-sm text-gray-500">Loading…</div>}

        {view && (
          <>
            <div className="flex flex-wrap items-center gap-3 text-sm">
              <select className="input" value={faculty} onChange={(event) => setFaculty(event.target.value)}>
                {view.faculties.map((entry) => {
                  const items = view.tasks.filter((task) => task.faculty === entry.key);
                  const answered = items.filter((task) => done.has(task.id)).length;
                  return (
                    <option key={entry.key} value={entry.key}>
                      {entry.name} ({answered}/{items.length})
                    </option>
                  );
                })}
              </select>
              <span className="text-gray-500">
                {done.size} of {view.tasks.length} answered
              </span>
            </div>
            <ol className="space-y-4">
              {shown.map((task) => (
                <li key={task.id} className="card p-4 space-y-2">
                  {task.history.length > 0 && (
                    <div className="space-y-1 text-xs text-gray-500">
                      {task.history.map((turn, index) => (
                        <div key={index}>
                          <span className="font-medium">{turn.role === "user" ? "You said" : "Reply"}:</span>{" "}
                          {turn.content}
                        </div>
                      ))}
                    </div>
                  )}
                  <div dir="auto" className="text-sm whitespace-pre-wrap wrap-break-word max-h-72 overflow-auto">
                    {task.prompt}
                  </div>
                  {done.has(task.id) ? (
                    <div className="text-xs text-gray-500">Answered</div>
                  ) : (
                    <textarea
                      dir="auto"
                      className="input w-full text-sm"
                      rows={2}
                      value={answers[task.id] ?? ""}
                      onChange={(event) => setAnswers({ ...answers, [task.id]: event.target.value })}
                      aria-label={`Answer to ${task.id}`}
                    />
                  )}
                </li>
              ))}
            </ol>
            <button type="button" className="btn-primary" disabled={busy || filled.length === 0} onClick={submit}>
              {busy ? "Saving…" : `Save ${filled.length} answer${filled.length === 1 ? "" : "s"}`}
            </button>
          </>
        )}
      </main>
    </div>
  );
}

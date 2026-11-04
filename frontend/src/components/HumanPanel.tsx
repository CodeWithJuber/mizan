/**
 * The human panel (imtihan/quwa.py): people answer the AGI test's text items
 * themselves, under a pseudonym, and are scored by the same rules as MIZAN.
 * The faculty profile then reads each arm as the share of panel members it
 * outperforms, as Google DeepMind's cognitive framework measures it.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import type { ApiClient } from "../types";
import { pct } from "../utils/imtihan.ts";
import { confirmDialog } from "./ui/confirm";

interface PanelTask {
  id: string;
  block: string;
  faculty: string;
  prompt: string;
  history: { role: string; content: string }[];
}

interface PanelView {
  faculties: { key: string; name: string }[];
  tasks: PanelTask[];
  people: { person: string; answered: number; faculties: Record<string, number> }[];
}

const PSEUDONYM = /^[A-Za-z0-9_.-]{1,40}$/;

interface Invite {
  id: string;
  person: string;
  created: number;
  expires: number;
  active: boolean;
  answered: number;
}

/** Links people open to answer alone, with no account (``/panel/<code>``). */
function PanelInvites({ api, total }: { api: ApiClient; total: number }) {
  const [invites, setInvites] = useState<Invite[]>([]);
  const [person, setPerson] = useState("");
  const [link, setLink] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const data = (await api.get("/imtihan/panel/invites")) as unknown as { invites: Invite[] };
      setInvites(data.invites);
    } catch {
      setError("Invite links could not be loaded");
    }
  }, [api]);

  useEffect(() => {
    void load();
  }, [load]);

  const named = person === "" || PSEUDONYM.test(person);

  const make = async () => {
    setError("");
    try {
      const made = (await api.post("/imtihan/panel/invites", person ? { person } : {})) as unknown as {
        path: string;
      };
      setLink(`${window.location.origin}${made.path}`);
      setPerson("");
      await load();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "The link could not be made");
    }
  };

  const revoke = async (id: string) => {
    const ok = await confirmDialog({
      title: "Revoke this invite?",
      description: "The link stops working at once. Answers already given are kept.",
      confirmLabel: "Revoke",
      destructive: true,
    });
    if (!ok) return;
    await api.del(`/imtihan/panel/invites/${encodeURIComponent(id)}`);
    await load();
  };

  return (
    <div className="space-y-2 border-t border-border/60 pt-3">
      <h4 className="font-medium text-sm">Invite links</h4>
      <p className="text-xs text-gray-500">
        Send a person a link to answer on their own phone or computer, with no account. Each link is for one pseudonym
        and lasts 14 days; their first answer to an item is final and they are not told whether it was right.
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <input
          className="input"
          placeholder="Pseudonym (optional)"
          value={person}
          onChange={(event) => setPerson(event.target.value.trim())}
          aria-invalid={!named}
        />
        <button type="button" className="btn-primary" disabled={!named} onClick={make}>
          Make a link
        </button>
        {error && <span className="text-xs text-red-500">{error}</span>}
      </div>
      {link && (
        <div className="text-xs space-y-1">
          <div className="text-gray-500">Copy it now: it is shown only once.</div>
          <code className="block break-all bg-muted rounded p-2">{link}</code>
        </div>
      )}
      {invites.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-xs min-w-[420px]">
            <thead>
              <tr className="text-gray-500 text-left">
                <th className="font-normal pb-1">Person</th>
                <th className="font-normal pb-1 text-right">Answered</th>
                <th className="font-normal pb-1 pl-3">Until</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {invites.map((entry) => (
                <tr key={entry.id} className="border-t border-border/60">
                  <td className="py-1.5">{entry.person}</td>
                  <td className="py-1.5 text-right tabular-nums">
                    {entry.answered}/{total}
                  </td>
                  <td className="py-1.5 pl-3 text-gray-500">
                    {entry.active ? new Date(entry.expires * 1000).toLocaleDateString() : "closed"}
                  </td>
                  <td className="py-1.5 text-right">
                    {entry.active && (
                      <button type="button" className="underline" onClick={() => revoke(entry.id)}>
                        Close
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default function HumanPanel({ api, onChange }: { api: ApiClient; onChange?: () => void }) {
  const [view, setView] = useState<PanelView | null>(null);
  const [error, setError] = useState("");
  const [person, setPerson] = useState("");
  const [faculty, setFaculty] = useState("");
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [scored, setScored] = useState<Record<string, { pass: boolean; detail: string }>>({});
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const data = (await api.get("/imtihan/panel")) as unknown as PanelView;
      setView(data);
      setFaculty((current) => current || data.faculties[0]?.key || "");
    } catch {
      setError("The human panel is for administrators.");
    }
  }, [api]);

  useEffect(() => {
    void load();
  }, [load]);

  const shown = useMemo(() => (view?.tasks ?? []).filter((task) => task.faculty === faculty), [view, faculty]);
  const filled = Object.entries(answers).filter(([, text]) => text.trim());
  const named = PSEUDONYM.test(person);

  const submit = async () => {
    if (!named || filled.length === 0) return;
    setBusy(true);
    setError("");
    try {
      const result = (await api.post("/imtihan/panel", {
        person,
        answers: Object.fromEntries(filled),
      })) as { scored: { task_id: string; pass: boolean; detail: string }[] };
      setScored((before) => ({
        ...before,
        ...Object.fromEntries(result.scored.map((entry) => [entry.task_id, entry])),
      }));
      setAnswers({});
      await load();
      onChange?.();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "The answers could not be saved");
    } finally {
      setBusy(false);
    }
  };

  const erase = async (who: string) => {
    const ok = await confirmDialog({
      title: `Erase ${who}'s answers?`,
      description: "All of this person's answers are deleted from the panel. This cannot be undone.",
      confirmLabel: "Erase",
      destructive: true,
    });
    if (!ok) return;
    await api.del(`/imtihan/panel/${encodeURIComponent(who)}`);
    await load();
    onChange?.();
  };

  if (!view) return <div className="card p-4 text-sm text-gray-500">{error || "Loading…"}</div>;
  const names = Object.fromEntries(view.faculties.map((entry) => [entry.key, entry.name]));

  return (
    <div className="card p-4 space-y-3">
      <h3 className="font-semibold text-sm">Human panel</h3>
      <p className="text-xs text-gray-500">
        Ask each person to answer on their own, without asking an AI, as the items are given to the base model and
        MIZAN. Use a pseudonym (letters, digits, <code>-_.</code>), never a name: only the pseudonym and the answers
        are kept. Each answer is scored by the item's own rule, and the faculty profile then shows the share of the
        panel each arm outperforms.
      </p>
      <div className="grid gap-2 sm:grid-cols-2">
        <input
          className="input"
          placeholder="Pseudonym (for example p01)"
          value={person}
          onChange={(event) => setPerson(event.target.value.trim())}
          aria-invalid={person !== "" && !named}
        />
        <select className="input" value={faculty} onChange={(event) => setFaculty(event.target.value)}>
          {view.faculties.map((entry) => (
            <option key={entry.key} value={entry.key}>
              {entry.name} ({view.tasks.filter((task) => task.faculty === entry.key).length} items)
            </option>
          ))}
        </select>
      </div>
      <ol className="space-y-4">
        {shown.map((task) => (
          <li key={task.id} className="border-t border-border/60 pt-3 space-y-2">
            {task.history.length > 0 && (
              <div className="space-y-1 text-xs">
                {task.history.map((turn, index) => (
                  <div key={index} className="text-gray-500">
                    <span className="font-medium">{turn.role === "user" ? "You said" : "Reply"}:</span> {turn.content}
                  </div>
                ))}
              </div>
            )}
            <div dir="auto" className="text-sm whitespace-pre-wrap wrap-break-word max-h-64 overflow-auto">
              {task.prompt}
            </div>
            <textarea
              dir="auto"
              className="input w-full text-sm"
              rows={task.prompt.length > 400 ? 3 : 2}
              value={answers[task.id] ?? ""}
              onChange={(event) => setAnswers({ ...answers, [task.id]: event.target.value })}
              aria-label={`Answer to ${task.id}`}
            />
            {scored[task.id] && (
              <div
                className={`text-xs ${scored[task.id].pass ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400"}`}
              >
                {scored[task.id].pass ? "✓" : "✗"} {scored[task.id].detail}
              </div>
            )}
          </li>
        ))}
      </ol>
      <div className="flex flex-wrap items-center gap-3">
        <button type="button" className="btn-primary" disabled={busy || !named || filled.length === 0} onClick={submit}>
          {busy ? "Scoring…" : `Score ${filled.length} answer${filled.length === 1 ? "" : "s"}`}
        </button>
        {!named && person !== "" && <span className="text-xs text-red-500">Letters, digits and -_. only</span>}
        {error && <span className="text-xs text-red-500">{error}</span>}
      </div>
      <PanelInvites api={api} total={view.tasks.length} />
      {view.people.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-xs min-w-[480px]">
            <thead>
              <tr className="text-gray-500 text-left">
                <th className="font-normal pb-1">Person</th>
                <th className="font-normal pb-1 text-right">Answered</th>
                <th className="font-normal pb-1 pl-3">Pass rate by faculty</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {view.people.map((entry) => (
                <tr key={entry.person} className="border-t border-border/60">
                  <td className="py-1.5">{entry.person}</td>
                  <td className="py-1.5 text-right tabular-nums">{entry.answered}</td>
                  <td className="py-1.5 pl-3 text-gray-500">
                    {Object.entries(entry.faculties)
                      .map(([key, rate]) => `${names[key] ?? key} ${pct(rate)}`)
                      .join(" · ")}
                  </td>
                  <td className="py-1.5 text-right">
                    <button type="button" className="underline" onClick={() => erase(entry.person)}>
                      Erase
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

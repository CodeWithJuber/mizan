/**
 * Muraqabah: watchers that work for you and judge when to interrupt.
 * Your place sets the prayer times; nothing is delivered from 5 minutes
 * before each adhan until 20 after (Jumu'ah: 30 before Dhuhr to 60 after).
 * "Useful" and "Not now" on each notice teach MIZAN when to interrupt you.
 */

import { useCallback, useEffect, useState } from "react";
import type { ApiClient } from "../types";
import { useToast } from "../components/Toast";
import { confirmDialog } from "../components/ui/confirm";
import {
  PRAYERS,
  STATUS_LABELS,
  localTime,
  triggerFrom,
  usefulShare,
  type Overview,
  type TriggerForm,
} from "../utils/muraqabah.ts";

interface Notice {
  id: string;
  kind: string;
  text: string;
  status: string;
  created: string;
}

const TASKS = [
  { key: "ayah_of_the_day", label: "Ayah of the day, with the Hijri date" },
  { key: "remind", label: "A reminder (your words)" },
  { key: "ask", label: "Ask MIZAN each time (for example \"today's hadith from Riyad as-Salihin\")" },
];

export default function WatchersPage({ api }: { api: ApiClient }) {
  const { addToast } = useToast();
  const [data, setData] = useState<Overview | null>(null);
  const [notices, setNotices] = useState<Notice[]>([]);
  const [city, setCity] = useState("");
  const [busy, setBusy] = useState(false);
  const [title, setTitle] = useState("");
  const [taskKind, setTaskKind] = useState("ayah_of_the_day");
  const [taskText, setTaskText] = useState("");
  const [always, setAlways] = useState(false);
  const [form, setForm] = useState<TriggerForm>({
    kind: "prayer", time: "08:00", prayer: "fajr", offset: 20, days: "13, 14, 15", url: "", hours: 6,
  });

  const load = useCallback(async () => {
    try {
      setData((await api.get("/muraqabah")) as unknown as Overview);
      setNotices(((await api.get("/muraqabah/notices")).notices as Notice[]) ?? []);
    } catch {
      addToast({ type: "error", title: "Watchers could not be loaded" });
    }
  }, [api, addToast]);

  useEffect(() => {
    load();
  }, [load]);

  const act = async (action: () => Promise<unknown>, done: string) => {
    setBusy(true);
    try {
      await action();
      if (done) addToast({ type: "success", title: done });
      await load();
    } catch (error) {
      addToast({ type: "error", title: "That did not work", description: (error as Error).message });
    } finally {
      setBusy(false);
    }
  };

  const savePlace = (changes: Record<string, unknown>) =>
    act(() => api.put("/muraqabah/place", changes), "Saved");

  const addWatcher = () => {
    const task = taskKind === "ayah_of_the_day" ? "ayah_of_the_day" : taskKind === "remind" ? `remind:${taskText.trim()}` : taskText.trim();
    const name = title.trim() || (taskKind === "ayah_of_the_day" ? "Ayah of the day" : taskText.trim().slice(0, 60));
    return act(async () => {
      await api.post("/muraqabah/watchers", { title: name, trigger: triggerFrom(form), task, priority: always ? "always" : "judge" });
      setTitle("");
      setTaskText("");
    }, "Watcher saved");
  };

  const place = data?.place ?? null;
  const tz = place?.tz;

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      <div className="px-5 py-3 border-b border-border">
        <h2 className="page-title">Watchers · مراقبة</h2>
        <p className="page-description">
          Things MIZAN does for you on a schedule, quiet during salah, learning when to interrupt you
        </p>
      </div>

      <div className="flex-1 overflow-y-auto p-4 sm:p-5 space-y-4">
        <section className="card space-y-3" aria-label="Your place and today's prayer times">
          <div className="flex flex-wrap items-end gap-2">
            <div className="flex-1 min-w-[12rem]">
              <div className="text-xxs font-semibold text-muted-foreground/80 uppercase tracking-widest mb-1">
                Your place
              </div>
              <p className="text-sm text-foreground">
                {place ? `${place.label} · ${place.tz}` : "Not set: prayer-time watchers and quiet windows need it."}
              </p>
            </div>
            <input
              className="input text-sm py-1.5 w-full sm:w-48"
              placeholder="City, e.g. Karachi"
              value={city}
              onChange={(event) => setCity(event.target.value)}
              onKeyDown={(event) => event.key === "Enter" && city.trim() && savePlace({ city: city.trim() })}
            />
            <button className="btn-secondary btn-sm" disabled={busy || !city.trim()} onClick={() => savePlace({ city: city.trim() })}>
              Set city
            </button>
          </div>

          {place && (
            <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
              <label className="flex items-center gap-1">
                Method
                <select className="input text-xs py-1" value={place.method} onChange={(event) => savePlace({ method: event.target.value })}>
                  {data?.methods.map((method) => (
                    <option key={method} value={method}>
                      {method.replace(/_/g, " ").toLowerCase()}
                    </option>
                  ))}
                </select>
              </label>
              <label className="flex items-center gap-1">
                <input type="checkbox" checked={place.hanafi} onChange={(event) => savePlace({ hanafi: event.target.checked })} />
                Hanafi Asr
              </label>
              <label className="flex items-center gap-1">
                <input type="checkbox" checked={place.quiet} onChange={(event) => savePlace({ quiet: event.target.checked })} />
                Quiet during salah
              </label>
              <label className="flex items-center gap-1">
                Notices a day
                <input
                  type="number"
                  min={0}
                  max={50}
                  className="input text-xs py-1 w-16"
                  defaultValue={place.budget}
                  onBlur={(event) => Number(event.target.value) !== place.budget && savePlace({ budget: Number(event.target.value) })}
                />
              </label>
              <label className="flex items-center gap-1">
                Digest at
                <input
                  type="time"
                  className="input text-xs py-1"
                  defaultValue={place.digest}
                  onBlur={(event) => event.target.value && event.target.value !== place.digest && savePlace({ digest: event.target.value })}
                />
              </label>
            </div>
          )}

          {data?.today && (
            <div>
              <div className="flex flex-wrap gap-2">
                {Object.entries(data.today.times).map(([name, value]) => (
                  <div key={name} className="rounded-lg border border-border px-3 py-1.5 text-center min-w-[4.5rem]">
                    <div className="text-micro uppercase tracking-wide text-gray-400">{name}</div>
                    <div className="font-mono text-sm text-foreground">{value}</div>
                  </div>
                ))}
              </div>
              <p className="text-micro text-muted-foreground mt-2">
                {data.today.quiet_now ? "🕌 Quiet now: notices wait until salah ends. " : ""}
                Quiet: {data.today.quiet.map((w) => `${w.prayer === "jumuah" ? "Jumu'ah" : w.prayer} ${w.from}–${w.to}`).join(" · ")}
                {" · "}Delivered today: {data.delivered_today} of {data.budget}
              </p>
            </div>
          )}
        </section>

        <section className="card space-y-3" aria-label="New watcher">
          <div className="text-xxs font-semibold text-muted-foreground/80 uppercase tracking-widest">New watcher</div>
          <p className="text-xs text-muted-foreground">
            Or just ask in chat: “Har subah Fajr ke baad ek ayat aur Hijri date bhejo”.
          </p>
          <div className="grid gap-2 sm:grid-cols-2">
            <label className="text-xs text-muted-foreground space-y-1">
              <span>When</span>
              <select className="input text-sm w-full" value={form.kind} onChange={(event) => setForm({ ...form, kind: event.target.value as TriggerForm["kind"] })}>
                <option value="prayer">Around a prayer</option>
                <option value="daily">Every day at a time</option>
                <option value="hijri">On Hijri days of the month</option>
                <option value="page">When a page changes</option>
              </select>
            </label>
            {form.kind === "prayer" && (
              <div className="flex items-end gap-2 text-xs">
                <input
                  type="number"
                  className="input text-sm w-20"
                  value={Math.abs(form.offset)}
                  onChange={(event) => setForm({ ...form, offset: Math.sign(form.offset || 1) * Number(event.target.value) })}
                  aria-label="Minutes"
                />
                <select className="input text-sm" value={form.offset < 0 ? "before" : "after"} onChange={(event) => setForm({ ...form, offset: (event.target.value === "before" ? -1 : 1) * Math.abs(form.offset) })} aria-label="Before or after">
                  <option value="after">min after</option>
                  <option value="before">min before</option>
                </select>
                <select className="input text-sm" value={form.prayer} onChange={(event) => setForm({ ...form, prayer: event.target.value })} aria-label="Prayer">
                  {PRAYERS.map((prayer) => (
                    <option key={prayer} value={prayer}>
                      {prayer[0].toUpperCase() + prayer.slice(1)}
                    </option>
                  ))}
                </select>
              </div>
            )}
            {(form.kind === "daily" || form.kind === "hijri") && (
              <div className="flex items-end gap-2">
                {form.kind === "hijri" && (
                  <input className="input text-sm flex-1" value={form.days} onChange={(event) => setForm({ ...form, days: event.target.value })} aria-label="Hijri days" placeholder="13, 14, 15" />
                )}
                <input type="time" className="input text-sm" value={form.time} onChange={(event) => setForm({ ...form, time: event.target.value })} aria-label="Time" />
              </div>
            )}
            {form.kind === "page" && (
              <input className="input text-sm" placeholder="https://your-masjid.example/timetable" value={form.url} onChange={(event) => setForm({ ...form, url: event.target.value })} aria-label="Page address" />
            )}
          </div>
          {form.kind !== "page" && (
            <div className="space-y-2">
              <select className="input text-sm w-full" value={taskKind} onChange={(event) => setTaskKind(event.target.value)} aria-label="What to do">
                {TASKS.map((task) => (
                  <option key={task.key} value={task.key}>
                    {task.label}
                  </option>
                ))}
              </select>
              {taskKind !== "ayah_of_the_day" && (
                <input className="input text-sm w-full" placeholder={taskKind === "remind" ? "Pray witr" : "What MIZAN should do each time"} value={taskText} onChange={(event) => setTaskText(event.target.value)} />
              )}
            </div>
          )}
          <div className="flex flex-wrap items-center gap-2">
            <input className="input text-sm py-1.5 flex-1 min-w-[10rem]" placeholder="Name (optional)" value={title} onChange={(event) => setTitle(event.target.value)} />
            <label className="text-xs text-muted-foreground flex items-center gap-1">
              <input type="checkbox" checked={always} onChange={(event) => setAlways(event.target.checked)} />
              Always deliver (still waits for salah)
            </label>
            <button
              className="btn-gold btn-sm"
              disabled={busy || (form.kind !== "page" && taskKind !== "ayah_of_the_day" && !taskText.trim()) || (form.kind === "page" && !form.url.trim())}
              onClick={addWatcher}
            >
              Save watcher
            </button>
          </div>
        </section>

        <section className="space-y-2" aria-label="Your watchers">
          {(data?.watchers ?? []).length === 0 && <p className="text-sm text-gray-400 text-center py-4">No watchers yet.</p>}
          {data?.watchers.map((watcher) => (
            <article key={watcher.id} className={`card space-y-1 ${watcher.enabled ? "" : "opacity-60"}`}>
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="font-medium text-sm text-foreground flex-1 min-w-0 wrap-break-word">{watcher.title}</h3>
                {watcher.priority === "always" && <span className="badge-gold">always</span>}
              </div>
              <p className="text-xs text-muted-foreground">
                {watcher.when} · next {localTime(watcher.next_due, tz)}
              </p>
              <div className="flex flex-wrap gap-2 pt-1">
                <button className="btn-ghost btn-sm" disabled={busy} onClick={() => act(() => api.post(`/muraqabah/watchers/${watcher.id}/run`), "Ran now")}>
                  Run now
                </button>
                <button className="btn-ghost btn-sm" disabled={busy} onClick={() => act(() => api.patch(`/muraqabah/watchers/${watcher.id}`, { enabled: !watcher.enabled }), "")}>
                  {watcher.enabled ? "Pause" : "Resume"}
                </button>
                <button className="btn-danger btn-sm" disabled={busy} onClick={async () => {
                    const ok = await confirmDialog({
                      title: "Remove this watcher?",
                      description: "It stops running and its schedule is deleted. This cannot be undone.",
                      confirmLabel: "Remove",
                      destructive: true,
                    });
                    if (ok) act(() => api.del(`/muraqabah/watchers/${watcher.id}`), "Removed");
                  }}>
                  Remove
                </button>
              </div>
            </article>
          ))}
        </section>

        <section className="card space-y-2" aria-label="Recent notices">
          <div className="text-xxs font-semibold text-muted-foreground/80 uppercase tracking-widest">Recent notices</div>
          {data && (
            <p className="text-micro text-muted-foreground">
              Useful so far:{" "}
              {Object.entries(data.attention)
                .filter(([, counts]) => counts.useful + counts.not_now > 3)
                .map(([kind, counts]) => `${kind} ${usefulShare(counts)}%`)
                .join(" · ") || "MIZAN is still learning"}
            </p>
          )}
          {notices.length === 0 && <p className="text-sm text-gray-400">Nothing yet.</p>}
          <ul className="divide-y divide-gray-200/60 dark:divide-gray-700/60">
            {notices.map((notice) => (
              <li key={notice.id} className="py-2 space-y-1">
                <p className="text-sm text-foreground/90 whitespace-pre-wrap wrap-break-word line-clamp-4">
                  {notice.text.replace(/\*\*/g, "")}
                </p>
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-micro text-gray-400">
                    {STATUS_LABELS[notice.status] ?? notice.status} · {localTime(notice.created, tz)}
                  </span>
                  <span className="flex-1" />
                  {!["opened", "dismissed"].includes(notice.status) && (
                    <>
                      <button className="btn-ghost btn-sm" onClick={() => act(() => api.post(`/muraqabah/notices/${notice.id}/feedback`, { useful: true }), "")}>
                        Useful
                      </button>
                      <button className="btn-ghost btn-sm" onClick={() => act(() => api.post(`/muraqabah/notices/${notice.id}/feedback`, { useful: false }), "")}>
                        Not now
                      </button>
                    </>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  );
}

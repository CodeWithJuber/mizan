/**
 * Iqtisad: what your model calls cost today and this month, against your
 * spending limits. Every paid call is checked before it is sent, so a limit
 * here is a hard stop, not a warning. You can lower your own limits;
 * administrators also see every user's spend and can set their limits.
 */

import { useCallback, useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { ApiClient } from "../types";
import { useToast } from "./Toast";
import {
  dailySeries,
  isSummary,
  parseLimit,
  renewal,
  share,
  usd,
  type Period,
  type SpendSummary,
  type SpendUser,
} from "../utils/iqtisad.ts";

const PERIOD_LABEL: Record<Period, string> = { day: "Today", month: "This month" };

function Meter({ period, summary }: { period: Period; summary: SpendSummary }) {
  const spent = summary.spent_usd[period];
  const limit = summary.limits_usd[period];
  const used = share(spent, limit);
  const full = used !== null && used >= 1;
  return (
    <div className="card p-4 space-y-2">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-xs font-medium text-muted-foreground">
          {PERIOD_LABEL[period]}
        </span>
        <span className="text-xs text-muted-foreground">
          renews {renewal(summary.renews_at[period])}
        </span>
      </div>
      <div className="text-2xl font-semibold text-foreground tabular-nums">
        {usd(spent)}
        <span className="text-sm font-normal text-muted-foreground">
          {limit === null ? " · no limit" : ` of ${usd(limit)}`}
        </span>
      </div>
      {used !== null && (
        <div
          className="h-2 rounded-full bg-muted overflow-hidden"
          role="meter"
          aria-valuemin={0}
          aria-valuemax={limit ?? 0}
          aria-valuenow={spent}
          aria-label={`${PERIOD_LABEL[period]} spend`}
        >
          <div
            className={`h-full rounded-full ${full ? "bg-red-500" : "bg-[var(--spend-bar)]"}`}
            style={{ width: `${Math.max(2, used * 100)}%` }}
          />
        </div>
      )}
      {full && (
        <p className="text-xs text-red-600 dark:text-red-400">
          Used up: MIZAN sends nothing more to a paid model until it renews. Its own tools still work.
        </p>
      )}
    </div>
  );
}

function OwnLimits({ summary, onSave }: { summary: SpendSummary; onSave: (day: number | null, month: number | null) => Promise<void> }) {
  const [day, setDay] = useState(summary.own_limits_usd.day?.toString() ?? "");
  const [month, setMonth] = useState(summary.own_limits_usd.month?.toString() ?? "");
  const [busy, setBusy] = useState(false);
  const dayValue = parseLimit(day);
  const monthValue = parseLimit(month);
  const valid = dayValue !== undefined && monthValue !== undefined;
  return (
    <form
      className="card p-4 space-y-3"
      onSubmit={async (event) => {
        event.preventDefault();
        if (!valid) return;
        setBusy(true);
        try {
          await onSave(dayValue, monthValue);
        } finally {
          setBusy(false);
        }
      }}
    >
      <div>
        <h4 className="text-sm font-semibold text-foreground">Your own limits</h4>
        <p className="text-xs text-muted-foreground">
          They can only make your budget smaller. Leave a box empty for no limit of your own.
        </p>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {(
          [
            ["Daily (USD)", day, setDay, dayValue],
            ["Monthly (USD)", month, setMonth, monthValue],
          ] as const
        ).map(([label, value, set, parsed]) => (
          <label key={label} className="text-xs text-muted-foreground space-y-1">
            <span>{label}</span>
            <input
              className="input w-full"
              inputMode="decimal"
              value={value}
              onChange={(event) => set(event.target.value)}
              aria-invalid={parsed === undefined}
              placeholder="No limit"
            />
          </label>
        ))}
      </div>
      {!valid && <p className="text-xs text-red-600 dark:text-red-400">Use a number of 0 or more.</p>}
      <button className="btn-gold btn-sm min-h-[36px]" disabled={!valid || busy}>
        {busy ? "Saving…" : "Save my limits"}
      </button>
    </form>
  );
}

function AllUsers({ api, users, month, reload }: { api: ApiClient; users: SpendUser[]; month: string; reload: () => void }) {
  const { addToast } = useToast();
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState({ day: "", month: "" });
  if (!users.length) return null;
  return (
    <div className="card p-4 space-y-2 overflow-x-auto">
      <h4 className="text-sm font-semibold text-foreground">Every user, {month}</h4>
      <table className="w-full text-xs">
        <thead className="text-left text-muted-foreground">
          <tr>
            <th className="py-1 pr-2 font-medium">User</th>
            <th className="py-1 pr-2 font-medium text-right">Spent</th>
            <th className="py-1 pr-2 font-medium text-right">Calls</th>
            <th className="py-1 pr-2 font-medium">Limits (day / month)</th>
            <th className="py-1" />
          </tr>
        </thead>
        <tbody>
          {users.map((row) => (
            <tr key={row.owner_id || "system"} className="border-t border-border/60">
              <td className="py-1.5 pr-2 text-foreground/90">{row.username || row.owner_id}</td>
              <td className="py-1.5 pr-2 text-right tabular-nums">{usd(row.cost_usd)}</td>
              <td className="py-1.5 pr-2 text-right tabular-nums">{row.calls}</td>
              <td className="py-1.5 pr-2">
                {editing === row.owner_id ? (
                  <span className="flex gap-1">
                    <input className="input w-16 py-0.5" inputMode="decimal" value={draft.day} placeholder="day"
                      onChange={(event) => setDraft({ ...draft, day: event.target.value })} />
                    <input className="input w-16 py-0.5" inputMode="decimal" value={draft.month} placeholder="month"
                      onChange={(event) => setDraft({ ...draft, month: event.target.value })} />
                  </span>
                ) : (
                  `${usd(row.limits_usd.day)} / ${usd(row.limits_usd.month)}`
                )}
              </td>
              <td className="py-1.5 text-right">
                {row.owner_id && editing !== row.owner_id && (
                  <button className="btn-secondary btn-sm" onClick={() => {
                    setEditing(row.owner_id);
                    setDraft({ day: row.limits_usd.day?.toString() ?? "", month: row.limits_usd.month?.toString() ?? "" });
                  }}>
                    Set
                  </button>
                )}
                {editing === row.owner_id && (
                  <button className="btn-gold btn-sm" onClick={async () => {
                    const day = parseLimit(draft.day);
                    const monthly = parseLimit(draft.month);
                    if (day === undefined || monthly === undefined) {
                      addToast({ type: "error", title: "Use a number of 0 or more" });
                      return;
                    }
                    try {
                      await api.put(`/iqtisad/limits/${encodeURIComponent(row.owner_id)}`, { daily_usd: day, monthly_usd: monthly });
                      setEditing(null);
                      reload();
                    } catch (error) {
                      addToast({ type: "error", title: "Limits not saved", description: (error as Error).message });
                    }
                  }}>
                    Save
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="text-2xs text-muted-foreground">
        A limit set here replaces the server default for that user, even for an administrator. Empty boxes return them to the default.
      </p>
    </div>
  );
}

export default function SpendingPanel({ api }: { api: ApiClient }) {
  const { addToast } = useToast();
  const [summary, setSummary] = useState<SpendSummary | null>(null);
  const [users, setUsers] = useState<{ month: string; users: SpendUser[] } | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const data = await api.get("/iqtisad");
      if (isSummary(data)) setSummary(data);
      setError("");
    } catch (failure) {
      setError((failure as Error).message || "Spending could not be loaded");
    }
    try {
      const everyone = await api.get("/iqtisad/all");
      if (Array.isArray(everyone.users)) setUsers(everyone as unknown as { month: string; users: SpendUser[] });
    } catch {
      setUsers(null); // not an administrator
    }
  }, [api]);

  useEffect(() => {
    load();
  }, [load]);

  if (error) return <p className="text-sm text-red-600 dark:text-red-400">{error}</p>;
  if (!summary) return <p className="text-sm text-gray-500">Loading spending…</p>;

  const series = dailySeries(summary.history, summary.day);
  return (
    <div className="space-y-4 iqtisad-viz">
      <style>{`
.iqtisad-viz { --spend-bar: #2a78d6; --spend-grid: #e5e4e0; }
.dark .iqtisad-viz { --spend-bar: #3987e5; --spend-grid: #3f3f46; }
`}</style>
      <div>
        <h3 className="text-lg font-semibold text-foreground">Spending</h3>
        <p className="text-sm text-muted-foreground">
          Every paid model call is checked against your limits before it is sent, and its answer
          length is capped to what is left, so no call can overspend. Prices are the providers'
          list prices unless the provider reports the cost itself.
        </p>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <Meter period="day" summary={summary} />
        <Meter period="month" summary={summary} />
      </div>
      <div className="card p-4">
        <h4 className="text-sm font-semibold text-foreground mb-2">Last 30 days</h4>
        <div className="h-48" role="img" aria-label="Model spend per day for the last 30 days">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={series} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
              <CartesianGrid stroke="var(--spend-grid)" vertical={false} />
              <XAxis dataKey="day" tickFormatter={(day: string) => day.slice(8)} tick={{ fontSize: 10 }} stroke="currentColor" opacity={0.6} interval="preserveStartEnd" />
              <YAxis tickFormatter={(value: number) => usd(value)} tick={{ fontSize: 10 }} stroke="currentColor" opacity={0.6} width={56} />
              <Tooltip
                formatter={(value) => [usd(Number(value)), "Spent"]}
                labelFormatter={(day) => `${day}`}
                cursor={{ fillOpacity: 0.08 }}
              />
              <Bar dataKey="cost_usd" fill="var(--spend-bar)" radius={[4, 4, 0, 0]} maxBarSize={18} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
      {summary.by_model.length > 0 && (
        <div className="card p-4 overflow-x-auto">
          <h4 className="text-sm font-semibold text-foreground mb-2">By model, {summary.month}</h4>
          <table className="w-full text-xs">
            <tbody>
              {summary.by_model.map((row) => (
                <tr key={row.model} className="border-t first:border-t-0 border-border/60">
                  <td className="py-1.5 pr-2 font-mono text-foreground/90 break-all">{row.model}</td>
                  <td className="py-1.5 pr-2 text-right tabular-nums">{usd(row.cost_usd)}</td>
                  <td className="py-1.5 text-right text-muted-foreground whitespace-nowrap">
                    {row.calls} calls{row.estimated_calls ? `, ${row.estimated_calls} priced from the list` : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <OwnLimits
        key={`${summary.own_limits_usd.day}-${summary.own_limits_usd.month}`}
        summary={summary}
        onSave={async (day, month) => {
          try {
            const data = await api.put("/iqtisad/limits", { daily_usd: day, monthly_usd: month });
            if (isSummary(data)) setSummary(data);
            addToast({ type: "success", title: "Your limits are saved" });
          } catch (failure) {
            addToast({ type: "error", title: "Limits not saved", description: (failure as Error).message });
          }
        }}
      />
      {users && <AllUsers api={api} users={users.users} month={users.month} reload={load} />}
    </div>
  );
}

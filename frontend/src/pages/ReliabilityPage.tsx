/**
 * MIZAN's public reliability page (/reliability), readable without signing in:
 * the published AGI-test results (aggregates only), their history, and the
 * signed daily roots of MIZAN's action receipts with the key to check them.
 */
import { useEffect, useMemo, useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { config } from "../config";
import { Legend2, ReportSummary, VIZ_STYLE } from "../components/ReportSummary";
import { useTheme } from "../hooks/useTheme";
import { historySeries, isPublicView, short, type PublicView } from "../utils/reliability.ts";

export default function ReliabilityPage() {
  useTheme();
  const [view, setView] = useState<PublicView | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    document.title = "MIZAN · Reliability";
    fetch(`${config.API_URL}/public/reliability`)
      .then((response) => (response.ok ? response.json() : Promise.reject(new Error(response.statusText))))
      .then((body) => (isPublicView(body) ? setView(body) : setError("The page could not be read")))
      .catch(() => setError("The results could not be loaded; try again in a minute"));
  }, []);

  const series = useMemo(() => (view ? historySeries(view.history) : []), [view]);
  const latest = view?.latest;

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-mizan-dark text-gray-900 dark:text-gray-100">
      <style>{VIZ_STYLE}</style>
      <main className="imtihan-viz max-w-5xl mx-auto px-4 py-8 space-y-6">
        <header className="space-y-2">
          <a href="/" className="text-sm text-amber-700 dark:text-amber-400">
            ميزان MIZAN
          </a>{" "}
          <a href="/api/docs" className="text-sm text-amber-700 dark:text-amber-400 ml-3">
            API docs
          </a>
          <h1 className="text-2xl font-semibold">How reliable is MIZAN?</h1>
          <p className="text-sm text-gray-600 dark:text-gray-400 max-w-3xl">
            Every task goes to the base model alone and to MIZAN, and each answer is scored by rule, not by another
            model. The scores below are aggregates with 95% Wilson intervals; no prompt or answer is published. Each
            published result's hash is written into MIZAN's signed action receipts (Sakk), so it cannot be changed
            later without that showing.
          </p>
        </header>

        {error && <div className="card p-4 text-sm text-red-600 dark:text-red-400">{error}</div>}
        {!view && !error && <div className="card p-4 text-sm text-gray-500">Loading…</div>}
        {view && !latest && (
          <div className="card p-4 text-sm text-gray-500">No results have been published yet.</div>
        )}

        {latest && (
          <section className="space-y-3">
            <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 text-sm">
              <h2 className="text-lg font-semibold">Latest result</h2>
              <span className="text-gray-500">
                run {new Date(latest.created_at * 1000).toLocaleDateString()} · {latest.blocks.length} blocks ·{" "}
                {latest.repeats ?? 1} attempt(s) per task
              </span>
              <span className="text-xs text-gray-500" title={latest.report_sha256}>
                report SHA-256 {short(latest.report_sha256)}
              </span>
            </div>
            <ReportSummary report={latest.report} model={latest.model} />
          </section>
        )}

        {series.length > 1 && (
          <section className="card p-4">
            <div className="flex flex-wrap items-center gap-2 mb-3">
              <h2 className="font-semibold text-sm">Over time</h2>
              <div className="ml-auto">
                <Legend2 />
              </div>
            </div>
            <div className="h-56">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={series} margin={{ top: 8, right: 16, bottom: 0, left: -8 }}>
                  <CartesianGrid stroke="var(--viz-grid)" vertical={false} />
                  <XAxis dataKey="date" tick={{ fontSize: 11 }} stroke="currentColor" opacity={0.6} />
                  <YAxis domain={[0, 100]} unit="%" tick={{ fontSize: 11 }} stroke="currentColor" opacity={0.6} />
                  <Tooltip formatter={(value) => `${value}%`} />
                  <Line type="monotone" dataKey="base" name="Base model" stroke="var(--viz-base)" strokeWidth={2} dot={{ r: 4 }} />
                  <Line type="monotone" dataKey="mizan" name="MIZAN" stroke="var(--viz-mizan)" strokeWidth={2} dot={{ r: 4 }} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </section>
        )}

        {view && (
          <section className="card p-4 space-y-3">
            <h2 className="font-semibold text-sm">Signed action receipts (Sakk)</h2>
            <p className="text-xs text-gray-600 dark:text-gray-400">
              Every action MIZAN takes or holds is a receipt chained to the one before it. Once a day MIZAN signs the
              Merkle root of every chain's latest receipt with this Ed25519 key. Any user can export their chain in
              Settings → Receipts and check it, offline, with <code>scripts/verify_sakk.py</code>.
            </p>
            <div className="text-xs break-all">
              <span className="text-gray-500">Public key </span>
              <code>{view.sakk.public_key}</code>
            </div>
            {view.sakk.roots.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full text-xs min-w-[420px]">
                  <thead>
                    <tr className="text-gray-500 text-left">
                      <th className="font-normal pb-1">Day (UTC)</th>
                      <th className="font-normal pb-1">Root</th>
                      <th className="font-normal pb-1 text-right">Chains</th>
                    </tr>
                  </thead>
                  <tbody>
                    {view.sakk.roots.map((root) => (
                      <tr key={root.day} className="border-t border-gray-100 dark:border-zinc-800">
                        <td className="py-1 pr-3 tabular-nums">{root.day}</td>
                        <td className="py-1 pr-3 font-mono" title={`${root.root}\nsignature ${root.signature}`}>
                          {short(root.root, 16)}
                        </td>
                        <td className="py-1 text-right tabular-nums">{root.leaves}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="text-xs text-gray-500">The first root is signed within the hour.</p>
            )}
          </section>
        )}
      </main>
    </div>
  );
}

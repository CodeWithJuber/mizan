/**
 * ComparePanel — parallel-model compare UI.
 *
 * POST /api/compare {prompt, models: [...up to 4]} → blind-labeled A/B/C/D
 * responses (model mapping is NOT revealed). POST /api/compare/{id}/reveal
 * {choice} or {judge: true} → reveals the mapping; judge mode returns
 * rubric scores plus a merged answer split into CONSENSUS vs CONTESTED.
 */

import { useState } from "react";
import { config } from "../config";

const LABELS = ["A", "B", "C", "D"] as const;

interface BlindResult {
  label: string;
  response: string;
}

interface JudgeData {
  scores: Record<string, Record<string, number>>;
  consensus: string[];
  contested: string[];
  winner: string | null;
  reason: string;
}

function authHeaders(): Record<string, string> {
  const token = localStorage.getItem("mizan_token") || "";
  const h: Record<string, string> = { "Content-Type": "application/json" };
  if (token) h["Authorization"] = `Bearer ${token}`;
  return h;
}

export default function ComparePanel() {
  const [prompt, setPrompt] = useState("");
  const [modelInputs, setModelInputs] = useState(["", ""]);
  const [compareId, setCompareId] = useState<string | null>(null);
  const [results, setResults] = useState<BlindResult[]>([]);
  const [mapping, setMapping] = useState<Record<string, string> | null>(null);
  const [choice, setChoice] = useState<string | null>(null);
  const [judge, setJudge] = useState<JudgeData | null>(null);
  const [merged, setMerged] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const models = modelInputs.map((m) => m.trim()).filter(Boolean);

  function setModel(i: number, v: string) {
    const next = [...modelInputs];
    next[i] = v;
    setModelInputs(next);
  }

  async function runCompare() {
    setError(null);
    setMapping(null);
    setJudge(null);
    setMerged(null);
    if (models.length < 2) {
      setError("Enter at least 2 model ids (max 4).");
      return;
    }
    setBusy(true);
    try {
      const res = await fetch(`${config.API_URL}/compare`, {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify({ prompt, models: models.slice(0, 4) }),
      });
      if (!res.ok) throw new Error(`compare failed: ${res.status}`);
      const data = await res.json();
      setCompareId(data.compare_id);
      setResults(data.results ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function reveal(withJudge: boolean) {
    if (!compareId) return;
    setError(null);
    setBusy(true);
    try {
      const res = await fetch(`${config.API_URL}/compare/${compareId}/reveal`, {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify(withJudge ? { judge: true } : { choice }),
      });
      if (!res.ok) throw new Error(`reveal failed: ${res.status}`);
      const data = await res.json();
      setMapping(data.mapping ?? null);
      if (data.judge) setJudge(data.judge);
      if (data.merged_answer) setMerged(data.merged_answer);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-4 rounded-xl border border-border bg-surface p-4">
      <h2 className="text-base font-semibold text-primary">Compare models</h2>

      <textarea
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
        placeholder="Prompt to send to every model…"
        rows={3}
        className="w-full rounded-lg border border-border bg-background p-2 text-sm text-primary"
      />

      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {modelInputs.map((m, i) => (
          <input
            key={i}
            value={m}
            onChange={(e) => setModel(i, e.target.value)}
            placeholder={`Model ${LABELS[i]} id (e.g. anthropic/claude-sonnet-4-20250514)`}
            className="rounded-lg border border-border bg-background p-2 text-sm text-primary"
          />
        ))}
      </div>
      {modelInputs.length < 4 && (
        <button
          type="button"
          onClick={() => setModelInputs([...modelInputs, ""])}
          className="self-start text-xs text-secondary underline"
        >
          + add model (up to 4)
        </button>
      )}

      <button
        type="button"
        disabled={busy || !prompt.trim()}
        onClick={runCompare}
        className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
      >
        {busy ? "Running…" : "Compare (blind)"}
      </button>

      {error && <p className="text-xs text-red-500">{error}</p>}

      {results.length > 0 && (
        <>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            {results.map((r) => (
              <div
                key={r.label}
                className="rounded-lg border border-border bg-background p-3"
              >
                <div className="mb-1 flex items-center justify-between">
                  <span className="font-mono text-sm font-bold text-primary">
                    {r.label}
                    {mapping && (
                      <span className="ml-2 text-xs font-normal text-secondary">
                        {mapping[r.label]}
                      </span>
                    )}
                  </span>
                  <button
                    type="button"
                    onClick={() => setChoice(r.label)}
                    className={`rounded px-2 py-0.5 text-xs ${
                      choice === r.label
                        ? "bg-primary text-white"
                        : "border border-border text-secondary"
                    }`}
                  >
                    Pick
                  </button>
                </div>
                <p className="whitespace-pre-wrap text-sm text-primary">
                  {r.response}
                </p>
              </div>
            ))}
          </div>

          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              disabled={busy}
              onClick={() => reveal(false)}
              className="rounded-lg border border-border px-4 py-2 text-sm text-primary"
            >
              Reveal mapping{choice ? ` (my pick: ${choice})` : ""}
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() => reveal(true)}
              className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white"
            >
              Judge + merge
            </button>
          </div>
        </>
      )}

      {judge && (
        <div className="rounded-lg border border-border bg-background p-3 text-sm">
          <h3 className="mb-2 font-semibold text-primary">
            Judge scores{judge.winner ? ` — winner: ${judge.winner}` : ""}
          </h3>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-left text-secondary">
                  <th className="p-1">Label</th>
                  <th className="p-1">Accuracy</th>
                  <th className="p-1">Relevance</th>
                  <th className="p-1">Clarity</th>
                  <th className="p-1">Honesty</th>
                  <th className="p-1">Total</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(judge.scores).map(([label, s]) => (
                  <tr key={label} className="text-primary">
                    <td className="p-1 font-mono font-bold">{label}</td>
                    <td className="p-1">{s.factual_accuracy}</td>
                    <td className="p-1">{s.relevance_completeness}</td>
                    <td className="p-1">{s.clarity_concision}</td>
                    <td className="p-1">{s.safety_honesty}</td>
                    <td className="p-1 font-bold">{s.total}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {judge.reason && (
            <p className="mt-2 text-xs text-secondary">{judge.reason}</p>
          )}
        </div>
      )}

      {merged && (
        <div className="rounded-lg border border-border bg-background p-3">
          <h3 className="mb-2 text-sm font-semibold text-primary">
            Merged answer
          </h3>
          <p className="whitespace-pre-wrap text-sm text-primary">{merged}</p>
        </div>
      )}
    </div>
  );
}

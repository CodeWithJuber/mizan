import { useCallback, useEffect, useState } from "react";
import { config } from "../../config";
import { authFetch } from "../../utils/authFetch";

interface Candidate {
  id: number;
  prompt: string;
  response: string;
  model: string;
  provider: string;
  content_hash: string;
  review_status: string;
  review_evidence: string | null;
  quality_score: number;
}

function ReviewCandidate({ candidate, refresh }: { candidate: Candidate; refresh: () => void }) {
  const [evidence, setEvidence] = useState(candidate.review_evidence ?? "");
  const [score, setScore] = useState(String(candidate.quality_score));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const review = async (accepted: boolean) => {
    setBusy(true);
    setError("");
    try {
      const response = await authFetch(`${config.API_URL}/learner/review/${candidate.id}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          expected_hash: candidate.content_hash, accepted, evidence,
          quality_score: Number(score),
        }),
      });
      if (!response.ok) throw new Error("The review was not saved. Refresh and check your evidence and score.");
      refresh();
    } catch {
      setError("The review was not saved. Refresh and check your evidence and score.");
    } finally {
      setBusy(false);
    }
  };
  const valid = evidence.trim().length > 0 && score.trim() !== "" && Number.isFinite(Number(score))
    && Number(score) >= 0 && Number(score) <= 1;
  return (
    <details className="rounded border border-gray-200 dark:border-zinc-700 p-3">
      <summary className="cursor-pointer text-sm">
        {candidate.prompt.slice(0, 100)} · {candidate.review_status}
      </summary>
      <p className="mt-2 text-xs text-gray-500">Model-authored · {candidate.provider} / {candidate.model}</p>
      <h4 className="mt-3 text-xs font-semibold">Your request</h4>
      <pre className="max-h-36 overflow-auto whitespace-pre-wrap wrap-break-word text-xs">{candidate.prompt}</pre>
      <h4 className="mt-3 text-xs font-semibold">Captured response</h4>
      <pre className="max-h-64 overflow-auto whitespace-pre-wrap wrap-break-word text-xs">{candidate.response}</pre>
      <label className="block mt-3 text-xs">
        Review evidence or reason
        <textarea value={evidence} maxLength={4000} rows={2} disabled={busy}
          onChange={(event) => setEvidence(event.target.value)}
          className="block mt-1 w-full rounded border border-gray-300 dark:border-zinc-700 bg-transparent p-2" />
      </label>
      <label className="block mt-2 text-xs">
        Quality score (0–1; export requires at least 0.8)
        <input type="number" min="0" max="1" step="0.05" value={score} disabled={busy}
          onChange={(event) => setScore(event.target.value)}
          className="ml-2 w-20 rounded border border-gray-300 dark:border-zinc-700 bg-transparent p-1" />
      </label>
      <div className="flex gap-2 mt-3">
        <button type="button" disabled={busy || !valid} onClick={() => void review(true)}
          className="btn-primary text-xs disabled:opacity-50">Accept candidate</button>
        <button type="button" disabled={busy || !valid} onClick={() => void review(false)}
          className="btn-secondary text-xs disabled:opacity-50">Reject candidate</button>
      </div>
      {error && <p role="alert" className="mt-2 text-xs text-red-600">{error}</p>}
    </details>
  );
}

export function LearningReviewPanel() {
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [exporting, setExporting] = useState(false);
  const refresh = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    try {
      const response = await authFetch(`${config.API_URL}/learner/recent?limit=20`, { signal });
      if (!response.ok) throw new Error("Candidates unavailable");
      const data = await response.json() as { interactions: Candidate[] };
      if (!signal?.aborted) { setCandidates(data.interactions); setError(""); }
    } catch {
      if (!signal?.aborted) setError("Candidates are temporarily unavailable.");
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    void refresh(controller.signal);
    return () => controller.abort();
  }, [refresh]);

  const download = async () => {
    setExporting(true);
    try {
      const response = await authFetch(`${config.API_URL}/learner/export`, { method: "POST" });
      if (!response.ok) throw new Error("Export unavailable");
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = url;
      link.download = "mizan-reviewed-candidates.jsonl";
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      setError("");
    } catch {
      setError("Export is temporarily unavailable.");
    } finally { setExporting(false); }
  };

  return (
    <section className="card">
      <h3 className="text-sm font-semibold">Your captured learning candidates</h3>
      <p className="my-2 text-xs text-gray-500">
        Completed chat responses are captured privately for review. Reviewing a response does not
        train weights or establish that it is true. Exports retain model authorship and are not original training data.
      </p>
      <div className="flex gap-2 mb-3">
        <button type="button" disabled={loading} onClick={() => void refresh()}
          className="btn-secondary text-xs">Refresh</button>
        <button type="button" disabled={exporting} onClick={() => void download()}
          className="btn-secondary text-xs">{exporting ? "Exporting…" : "Export reviewed candidates"}</button>
      </div>
      {error && <p role="alert" className="mb-2 text-xs text-red-600">{error}</p>}
      {loading && candidates.length === 0 ? <p className="text-xs">Loading candidates…</p>
        : candidates.length === 0 ? <p className="text-xs">No chat responses captured for this account yet.</p>
          : <div className="space-y-2">{candidates.map((candidate) => (
            <ReviewCandidate key={`${candidate.id}-${candidate.review_status}-${candidate.quality_score}`}
              candidate={candidate} refresh={() => void refresh()} />
          ))}</div>}
    </section>
  );
}

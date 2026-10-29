import { useCallback, useEffect, useRef, useState } from "react";
import type { ApiClient } from "../../types";

interface LearningBundle {
  bundle_id: string;
  state: string;
}

interface LearningState {
  configured: boolean;
  status?: string;
  error?: string;
  reason?: string;
  initialized?: boolean;
  policy_ready?: boolean;
  policy_reason?: string;
  capacity?: { admitted: boolean; available_bytes?: number | null; required_bytes?: number; reason?: string };
  busy?: boolean;
  generation: number;
  active?: { sha256?: string; checkpoint_sha256?: string } | null;
  previous?: unknown;
  bundles?: LearningBundle[];
  last_run?: { status?: string; stage?: string; bundle_id?: string } | null;
  service_busy: boolean;
  service_job?: { state: string; bundle_id: string } | null;
  automation_active: boolean;
  automation_configured: boolean;
}

export function OwnedLearningPanel({ api }: { api: ApiClient }) {
  const [state, setState] = useState<LearningState | null>(null);
  const [bundle, setBundle] = useState("");
  const [error, setError] = useState("");
  const [loadError, setLoadError] = useState("");
  const [current, setCurrent] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const requestId = useRef(0);
  const mounted = useRef(true);
  const refresh = useCallback(async () => {
    const request = ++requestId.current;
    try {
      const value = await api.get("/owned/learning") as unknown as LearningState;
      if (!mounted.current || request !== requestId.current) return;
      setState(value);
      setLoadError("");
      setCurrent(true);
      setBundle((old) => (value.bundles ?? []).some((row) => row.bundle_id === old && row.state === "ready")
        ? old : (value.bundles ?? []).find((row) => row.state === "ready")?.bundle_id ?? "");
    } catch {
      if (!mounted.current || request !== requestId.current) return;
      setLoadError("Could not load learning status. Refresh to reconnect.");
      setCurrent(false);
    }
  }, [api]);
  useEffect(() => {
    mounted.current = true;
    void refresh();
    const timer = setInterval(() => void refresh(), 10_000);
    return () => { mounted.current = false; requestId.current++; clearInterval(timer); };
  }, [refresh]);

  const act = async (operation: "run" | "rollback") => {
    if (!state || !current) return;
    setSubmitting(true);
    setError("");
    try {
      await api.post(`/owned/learning/${operation}`, operation === "run"
        ? { bundle_id: bundle } : { expected_generation: state.generation });
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "The action was not applied. Refresh and try again.");
    } finally { setSubmitting(false); }
  };

  const ready = state?.bundles?.filter((row) => row.state === "ready") ?? [];
  const busy = submitting || state?.service_busy || state?.busy;
  const digest = state?.active?.sha256 ?? state?.active?.checkpoint_sha256;
  return (
    <section className="card space-y-4">
      <div>
        <h3 className="text-sm font-semibold">Own-model learning</h3>
        <p className="mt-1 text-xs text-muted-foreground">
          Train the Mizan reply model on approved original-source data, evaluate it,
          and activate only candidates that pass the configured checks. This is a
          separate model from Ruh; their checkpoints cannot be interchanged.
        </p>
      </div>
      {!state && !loadError && <p className="text-sm">Loading learning status…</p>}
      {state && <>
        <dl className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-sm">
          <div><dt className="text-xs text-gray-500">Setup</dt><dd>{state.configured ? state.status ?? "Configured" : "Not configured"}</dd></div>
          <div><dt className="text-xs text-gray-500">Automatic cycles</dt><dd>{state.automation_active ? "Watching for approved bundles" : state.automation_configured ? "Not running" : "Disabled"}</dd></div>
          <div><dt className="text-xs text-gray-500">Active checkpoint</dt><dd>{state.active ? `Generation ${state.generation}` : "None"}</dd></div>
        </dl>
        {digest && <p className="break-all font-mono text-xs text-gray-500">Checkpoint: {digest}</p>}
        {!state.configured && <p className="text-sm">
          A private learning directory, admission policy and approved data bundle
          must be configured before training can start. Captured chat replies are
          not automatically accepted as original training data.
        </p>}
        {state.error && <p role="alert" className="text-sm text-red-600">{state.error}</p>}
        {state.status === "invalid" && <p role="alert" className="text-sm text-red-600">
          Learning state could not be verified: {state.reason ?? "refresh required"}
        </p>}
        {state.configured && state.policy_ready === false && <p className="text-sm">
          Admission policy is not ready: {state.policy_reason ?? "configure and validate the learning policy"}
        </p>}
        {state.capacity?.admitted === false && <p role="status" className="text-sm">
          Training is paused because sufficient server memory has not been confirmed.
          {typeof state.capacity.available_bytes === "number" && typeof state.capacity.required_bytes === "number"
            ? ` Available: ${(state.capacity.available_bytes / 1024 ** 3).toFixed(1)} GiB; required by the worker policy and API reserve: ${(state.capacity.required_bytes / 1024 ** 3).toFixed(1)} GiB.`
            : " A bounded memory budget is required before a worker can start."}
        </p>}
        {state.service_job && <p className="text-sm break-all">
          Worker: {state.service_job.state} · {state.service_job.bundle_id}
        </p>}
        {state.last_run && <p className="text-sm break-all">
          Last candidate: {state.last_run.status ?? "Recorded"}
          {state.last_run.stage ? ` · ${state.last_run.stage}` : ""}
          {state.last_run.bundle_id ? ` · ${state.last_run.bundle_id}` : ""}
        </p>}
        <label className="block text-xs">
          Approved data bundle
          <select value={bundle} onChange={(event) => setBundle(event.target.value)}
            disabled={busy || ready.length === 0}
            className="mt-1 block w-full rounded border border-input bg-card p-2 min-h-[44px]">
            {ready.length === 0 && <option value="">No approved, unprocessed bundles</option>}
            {ready.map((row) => <option key={row.bundle_id} value={row.bundle_id}>{row.bundle_id}</option>)}
          </select>
        </label>
        <div className="flex flex-wrap gap-2">
          <button type="button" onClick={() => void act("run")}
            disabled={busy || !current || !state.configured || !state.policy_ready || !bundle || state.capacity?.admitted === false || state.status === "unavailable" || state.status === "invalid"}
            className="btn-primary min-h-[44px] text-xs disabled:opacity-50">Run validated cycle</button>
          <button type="button" onClick={() => void act("rollback")}
            disabled={busy || !current || !state.active || state.status === "unavailable" || state.status === "invalid"}
            className="btn-secondary min-h-[44px] text-xs disabled:opacity-50">
            {state.previous ? "Restore previous checkpoint" : "Deactivate first checkpoint"}
          </button>
          <button type="button" onClick={() => void refresh()} disabled={submitting}
            className="btn-secondary min-h-[44px] text-xs">Refresh</button>
        </div>
        <p className="text-xs text-muted-foreground">
          A completed worker can still produce a rejected candidate. Passing development
          checks does not establish general conversation readiness. Accepted checkpoints
          are available to the mizan-owned provider; actual use appears in each reply's
          model details. No paid GPU service is started here.
        </p>
      </>}
      {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
      {loadError && <p role="alert" className="text-sm text-red-600">{loadError}</p>}
    </section>
  );
}

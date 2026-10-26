import { useEffect, useState } from "react";
import { phaseLabel, type ChatRecoveryState } from "../utils/chatRecovery.ts";

export function ChatRunStatus({ progress, recovery, onRefresh, storageUnavailable }: {
  progress: { startedAt: number; phase?: string } | null;
  recovery: ChatRecoveryState | null;
  onRefresh: () => void;
  storageUnavailable?: boolean;
}) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!progress) return;
    setNow(Date.now());
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [progress?.startedAt]);
  if (!progress && !recovery && !storageUnavailable) return null;
  const blocked = recovery && ["checking", "active", "unknown"].includes(recovery.state);
  return <div role="status" className="mx-4 mt-3 rounded-xl border border-amber-200 dark:border-amber-500/30 bg-amber-50/70 dark:bg-amber-500/5 p-3 text-sm">
    {storageUnavailable && <p role="alert" className="mb-2 text-xs text-amber-800 dark:text-amber-200">
      Your browser could not save all received text for local recovery. Copy any important text before reloading or leaving this conversation.
    </p>}
    {progress ? <>
      <p>{phaseLabel(progress.phase)} · {Math.max(0, Math.floor((now - progress.startedAt) / 1000))}s since send</p>
      <p className="mt-1 text-xs text-gray-500">Elapsed time is measured in this browser. No completion estimate is available.</p>
    </> : recovery && <>
      <p>{recovery.state === "checking" ? "Checking the saved reply and server run…"
        : recovery.state === "active" ? `${phaseLabel(recovery.request?.phase)}. The server still has an active run.`
          : recovery.state === "unknown" ? "The previous request's outcome is not confirmed."
            : recovery.state === "terminal" ? recovery.historySaved === false
              ? "The local run ended, but its reply was not saved. The provider may still finish; this request will not be resent automatically."
              : "The previous local run has ended. Saved messages are refreshed."
              : "No active run was found. You can send a new message."}</p>
      {recovery.state === "active" && recovery.request?.elapsed_ms != null && <p className="mt-1 text-xs text-gray-500">
        Server elapsed time at the last check: {Math.floor(recovery.request.elapsed_ms / 1000)}s.
      </p>}
      {blocked && <p className="mt-1 text-xs text-gray-500">
        {recovery.message ?? "Received text remains in this conversation; local recovery copies depend on available browser storage. Sending is paused until this run is confirmed ended. The message will not be resent automatically."}
      </p>}
      {recovery.state === "unknown" && <p className="mt-1 text-xs text-gray-500">
        A refresh may not resolve this outcome. You can use New chat to continue;
        saved history is retained. Copy any text you need if local recovery storage is unavailable.
        Nothing is copied or resent automatically.
      </p>}
      {blocked && <button type="button" onClick={onRefresh} disabled={recovery.state === "checking"}
        className="mt-2 min-h-[44px] rounded-lg border border-amber-400/50 px-3 py-2 text-xs font-medium disabled:opacity-50">
        Refresh run status
      </button>}
    </>}
  </div>;
}

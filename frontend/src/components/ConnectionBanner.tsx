interface ConnectionBannerProps {
  status: string;
  attempts: number;
}

export function ConnectionBanner({ status, attempts }: ConnectionBannerProps) {
  if (status === "connected") return null;
  if (status === "connecting" || (status === "reconnecting" && attempts < 5))
    return null;

  return (
    <div
      role="alert"
      aria-live="polite"
      className="bg-amber-50 dark:bg-amber-500/5 border-b border-amber-200 dark:border-amber-500/20 px-4 py-2.5 flex items-center justify-between gap-3"
    >
      <div className="flex items-center gap-2 text-sm text-amber-800 dark:text-amber-300">
        <svg
          viewBox="0 0 20 20"
          fill="currentColor"
          className="w-4 h-4 shrink-0"
          aria-hidden="true"
        >
          <path
            fillRule="evenodd"
            d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.17 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495zM10 6a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 6zm0 9a1 1 0 100-2 1 1 0 000 2z"
            clipRule="evenodd"
          />
        </svg>
        <span>
          Cannot connect to backend. Make sure the server is running:{" "}
          <code className="code">mizan serve</code> or{" "}
          <code className="code">make dev</code>
        </span>
      </div>
      <button
        onClick={() => window.location.reload()}
        className="text-xs px-3 py-1 bg-amber-100 dark:bg-amber-500/10 hover:bg-amber-200 dark:hover:bg-amber-500/20 text-amber-800 dark:text-amber-300 rounded transition-colors shrink-0 focus-ring cursor-pointer"
      >
        Retry
      </button>
    </div>
  );
}

interface ConnectionBannerProps {
  status: string;
  attempts: number;
  /** Result of polling the public GET /api/health (unauthenticated). */
  backendUp: boolean | null;
  /** Jump to the Security tab so the user can log in. */
  onLogin: () => void;
}

export function ConnectionBanner({
  status,
  attempts,
  backendUp,
  onLogin,
}: ConnectionBannerProps) {
  if (status === "connected") return null;
  if (status === "connecting" || (status === "reconnecting" && attempts < 5))
    return null;

  // Login required: the WS handshake was rejected with 4401 (fail-closed
  // auth). The backend is fine — the user just needs to authenticate.
  // This must never read as "backend down".
  if (status === "auth_required") {
    return (
      <div
        role="alert"
        aria-live="polite"
        className="bg-sky-50 dark:bg-sky-500/5 border-b border-sky-200 dark:border-sky-500/20 px-4 py-2.5 flex items-center justify-between gap-3"
      >
        <div className="flex items-center gap-2 text-sm text-sky-800 dark:text-sky-300">
          <svg
            viewBox="0 0 20 20"
            fill="currentColor"
            className="w-4 h-4 shrink-0"
            aria-hidden="true"
          >
            <path
              fillRule="evenodd"
              d="M10 1a4.5 4.5 0 00-4.5 4.5V9H5a2 2 0 00-2 2v6a2 2 0 002 2h10a2 2 0 002-2v-6a2 2 0 00-2-2h-.5V5.5A4.5 4.5 0 0010 1zm3 5.5V9H7V5.5a3 3 0 016 0z"
              clipRule="evenodd"
            />
          </svg>
          <span>
            Login required — the server is up, but this session is not
            authenticated. Log in on the Security page to connect.
          </span>
        </div>
        <button
          onClick={onLogin}
          className="text-xs px-3 py-1 bg-sky-100 dark:bg-sky-500/10 hover:bg-sky-200 dark:hover:bg-sky-500/20 text-sky-800 dark:text-sky-300 rounded transition-colors shrink-0 focus-ring cursor-pointer"
        >
          Log in
        </button>
      </div>
    );
  }

  // Real backend outage (the public /api/health probe failed). Only this
  // state may claim "cannot connect to backend" — lā taqfu: never assert
  // an outage we have not verified.
  if (backendUp === false) {
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
            Cannot connect to backend. Ask the person who set up Mizan to start
            the server.
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

  return null;
}

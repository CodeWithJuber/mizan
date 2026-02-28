/**
 * Security Page — Authentication & Access Control
 * On localhost: auth is optional, shows simplified interface
 * On remote: full auth forms and token management
 */

import { useState, useEffect, useCallback } from "react";
import type { PageProps } from "../types";
import { SkeletonCard } from "../components/Skeleton";

interface AuditEvent {
  timestamp: string;
  type: string;
  severity: string;
  details: Record<string, unknown>;
}

interface AuditSummary {
  total_events: number;
  warnings: number;
  errors: number;
  recent: AuditEvent[];
}

const isLocalhost = () => {
  const host = window.location.hostname;
  return (
    host === "localhost" ||
    host === "127.0.0.1" ||
    host === "0.0.0.0" ||
    host === "::1"
  );
};

export default function SecurityPage({ api, addTerminalLine }: PageProps) {
  const [activeTab, setActiveTab] = useState("overview");
  const [token, setToken] = useState(
    () => localStorage.getItem("mizan_token") || "",
  );
  const [loginForm, setLoginForm] = useState({ username: "", password: "" });
  const [registerForm, setRegisterForm] = useState({
    username: "",
    password: "",
    confirm: "",
  });
  const [showAuthForms, setShowAuthForms] = useState(false);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<{
    type: "success" | "error";
    text: string;
  } | null>(null);
  const [auditData, setAuditData] = useState<AuditSummary | null>(null);
  const [auditLoading, setAuditLoading] = useState(false);
  const local = isLocalhost();

  const loadAudit = useCallback(async () => {
    setAuditLoading(true);
    try {
      const data = await api.get("/security/audit");
      setAuditData(data as unknown as AuditSummary);
    } catch (err) {
      console.error("Failed to fetch audit logs:", err);
      // Fallback: empty audit data (may fail due to auth requirements)
      setAuditData({ total_events: 0, warnings: 0, errors: 0, recent: [] });
    } finally {
      setAuditLoading(false);
    }
  }, [api]);

  useEffect(() => {
    if (activeTab === "audit") {
      loadAudit();
    }
  }, [activeTab, loadAudit]);

  const login = async () => {
    setLoading(true);
    setMessage(null);
    try {
      const data = (await api.post("/auth/login", loginForm)) as {
        access_token?: string;
        error?: string;
      };
      if (data.access_token) {
        localStorage.setItem("mizan_token", data.access_token);
        setToken(data.access_token);
        setMessage({ type: "success", text: "Logged in successfully" });
        addTerminalLine?.("Authenticated", "gold");
      } else {
        setMessage({ type: "error", text: data.error || "Login failed" });
      }
    } catch {
      setMessage({ type: "error", text: "Login request failed" });
    }
    setLoading(false);
  };

  const register = async () => {
    if (registerForm.password !== registerForm.confirm) {
      setMessage({ type: "error", text: "Passwords do not match" });
      return;
    }
    setLoading(true);
    setMessage(null);
    try {
      const data = (await api.post("/auth/register", {
        username: registerForm.username,
        password: registerForm.password,
      })) as { access_token?: string; error?: string };
      if (data.access_token) {
        localStorage.setItem("mizan_token", data.access_token);
        setToken(data.access_token);
        setMessage({ type: "success", text: "Account created and logged in" });
        addTerminalLine?.("Account created", "gold");
      } else {
        setMessage({
          type: "error",
          text: data.error || "Registration failed",
        });
      }
    } catch {
      setMessage({ type: "error", text: "Registration request failed" });
    }
    setLoading(false);
  };

  const logout = () => {
    localStorage.removeItem("mizan_token");
    setToken("");
    setMessage({ type: "success", text: "Logged out" });
    addTerminalLine?.("Logged out", "info");
  };

  return (
    <div className="page-wrapper">
      {/* Header */}
      <div className="page-header">
        <div>
          <h2 className="page-title">Security</h2>
          <p className="page-description">
            Authentication, access control, and security settings
          </p>
        </div>
      </div>

      {/* Tabs */}
      <div className="tab-bar">
        {[
          { id: "overview", label: "Overview" },
          { id: "auth", label: "Authentication" },
          { id: "tokens", label: "Tokens" },
          { id: "audit", label: "Audit Log" },
        ].map((tab) => (
          <button
            key={tab.id}
            className={`tab ${activeTab === tab.id ? "active" : ""}`}
            onClick={() => setActiveTab(tab.id)}
            aria-selected={activeTab === tab.id}
            role="tab"
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div className="page-body">
        {/* Localhost Banner */}
        {local && (
          <div className="bg-emerald-50 dark:bg-emerald-500/5 border border-emerald-200 dark:border-emerald-500/20 rounded-lg p-4 flex items-start gap-3">
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              className="w-5 h-5 text-emerald-600 dark:text-emerald-400 shrink-0 mt-0.5"
            >
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
              <path d="M9 12l2 2 4-4" />
            </svg>
            <div>
              <p className="text-sm font-medium text-emerald-800 dark:text-emerald-300">
                Running on localhost — authentication is optional
              </p>
              <p className="text-xs text-emerald-600 dark:text-emerald-400/70 mt-1">
                You&apos;re running MIZAN locally. No login is required. All
                features are available without authentication. If you deploy to
                a server, enable authentication to protect your instance.
              </p>
            </div>
          </div>
        )}

        {/* Message */}
        {message && (
          <div
            className={`rounded-lg px-4 py-3 text-sm ${
              message.type === "success"
                ? "bg-emerald-50 dark:bg-emerald-500/5 border border-emerald-200 dark:border-emerald-500/20 text-emerald-800 dark:text-emerald-300"
                : "bg-red-50 dark:bg-red-500/5 border border-red-200 dark:border-red-500/20 text-red-800 dark:text-red-300"
            }`}
          >
            {message.text}
          </div>
        )}

        {/* Overview Tab */}
        {activeTab === "overview" && (
          <div className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div className="card text-center">
                <div className="text-2xl font-mono text-emerald-600 dark:text-emerald-400 mb-1">
                  {token ? "Yes" : "No"}
                </div>
                <div className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                  Authenticated
                </div>
              </div>
              <div className="card text-center">
                <div className="text-2xl font-mono text-gray-900 dark:text-gray-100 mb-1">
                  {local ? "Local" : "Remote"}
                </div>
                <div className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                  Access Mode
                </div>
              </div>
              <div className="card text-center">
                <div className="text-2xl font-mono text-mizan-gold mb-1">
                  {local ? "Open" : token ? "Protected" : "Unprotected"}
                </div>
                <div className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                  Status
                </div>
              </div>
            </div>

            <div className="card">
              <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3">
                Security Checklist
              </h3>
              <div className="space-y-2">
                {[
                  { label: "Backend running", ok: true, info: false },
                  {
                    label: "HTTPS enabled",
                    ok: !local && window.location.protocol === "https:",
                    info: false,
                  },
                  {
                    label: "Authentication configured",
                    ok: !!token,
                    info: false,
                  },
                  { label: "Running on localhost", ok: local, info: true },
                ].map((item) => (
                  <div
                    key={item.label}
                    className="flex items-center gap-2.5 py-1"
                  >
                    <div
                      className={`w-5 h-5 rounded-full flex items-center justify-center text-xs ${
                        item.info
                          ? "bg-blue-100 dark:bg-blue-500/10 text-blue-600 dark:text-blue-400"
                          : item.ok
                            ? "bg-emerald-100 dark:bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                            : "bg-gray-100 dark:bg-zinc-800 text-gray-400 dark:text-gray-500"
                      }`}
                    >
                      {item.info ? "i" : item.ok ? "\u2713" : "\u2013"}
                    </div>
                    <span className="text-sm text-gray-700 dark:text-gray-300">
                      {item.label}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Auth Tab */}
        {activeTab === "auth" && (
          <div className="space-y-4 max-w-md">
            {token ? (
              <div className="card">
                <div className="flex items-center gap-3 mb-3">
                  <div className="w-10 h-10 rounded-full bg-emerald-100 dark:bg-emerald-500/10 flex items-center justify-center text-emerald-600 dark:text-emerald-400">
                    <svg
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="1.5"
                      className="w-5 h-5"
                    >
                      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
                      <path d="M9 12l2 2 4-4" />
                    </svg>
                  </div>
                  <div>
                    <div className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                      Authenticated
                    </div>
                    <div className="text-xs text-gray-500 dark:text-gray-400">
                      Your session is active
                    </div>
                  </div>
                </div>
                <button className="btn-danger text-sm w-full" onClick={logout}>
                  Logout
                </button>
              </div>
            ) : (
              <>
                {local && !showAuthForms && (
                  <div className="card text-center py-8">
                    <div className="text-sm text-gray-600 dark:text-gray-400 mb-3">
                      Authentication is optional on localhost
                    </div>
                    <button
                      className="btn-secondary text-sm"
                      onClick={() => setShowAuthForms(true)}
                    >
                      Set up authentication anyway
                    </button>
                  </div>
                )}

                {(!local || showAuthForms) && (
                  <div className="space-y-4">
                    {/* Login */}
                    <div className="card">
                      <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-4">
                        Login
                      </h3>
                      <div className="space-y-3">
                        <div>
                          <label className="form-label">Username</label>
                          <input
                            className="form-input"
                            placeholder="Enter username"
                            value={loginForm.username}
                            onChange={(e) =>
                              setLoginForm({
                                ...loginForm,
                                username: e.target.value,
                              })
                            }
                          />
                        </div>
                        <div>
                          <label className="form-label">Password</label>
                          <input
                            className="form-input"
                            type="password"
                            placeholder="Enter password"
                            value={loginForm.password}
                            onChange={(e) =>
                              setLoginForm({
                                ...loginForm,
                                password: e.target.value,
                              })
                            }
                          />
                        </div>
                        <button
                          className="btn-gold text-sm w-full"
                          onClick={login}
                          disabled={
                            loading ||
                            !loginForm.username ||
                            !loginForm.password
                          }
                        >
                          {loading ? "Logging in..." : "Login"}
                        </button>
                      </div>
                    </div>

                    {/* Register */}
                    <div className="card">
                      <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-4">
                        Create Account
                      </h3>
                      <div className="space-y-3">
                        <div>
                          <label className="form-label">Username</label>
                          <input
                            className="form-input"
                            placeholder="Choose a username"
                            value={registerForm.username}
                            onChange={(e) =>
                              setRegisterForm({
                                ...registerForm,
                                username: e.target.value,
                              })
                            }
                          />
                        </div>
                        <div>
                          <label className="form-label">Password</label>
                          <input
                            className="form-input"
                            type="password"
                            placeholder="Choose a password"
                            value={registerForm.password}
                            onChange={(e) =>
                              setRegisterForm({
                                ...registerForm,
                                password: e.target.value,
                              })
                            }
                          />
                        </div>
                        <div>
                          <label className="form-label">Confirm Password</label>
                          <input
                            className="form-input"
                            type="password"
                            placeholder="Re-enter password"
                            value={registerForm.confirm}
                            onChange={(e) =>
                              setRegisterForm({
                                ...registerForm,
                                confirm: e.target.value,
                              })
                            }
                          />
                        </div>
                        <button
                          className="btn-secondary text-sm w-full"
                          onClick={register}
                          disabled={
                            loading ||
                            !registerForm.username ||
                            !registerForm.password ||
                            !registerForm.confirm
                          }
                        >
                          {loading ? "Creating..." : "Create Account"}
                        </button>
                      </div>
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        )}

        {/* Tokens Tab */}
        {activeTab === "tokens" && (
          <div className="space-y-4 max-w-lg">
            <div className="card">
              <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3">
                Current Token
              </h3>
              {token ? (
                <>
                  <div className="bg-gray-50 dark:bg-zinc-800 rounded-lg p-3 font-mono text-xs text-gray-600 dark:text-gray-400 break-all mb-3 border border-gray-200 dark:border-zinc-700">
                    {token.substring(0, 20)}...
                    {token.substring(token.length - 10)}
                  </div>
                  <div className="flex gap-2">
                    <button
                      className="btn-secondary text-xs"
                      onClick={() => {
                        navigator.clipboard.writeText(token);
                        setMessage({
                          type: "success",
                          text: "Token copied to clipboard",
                        });
                      }}
                    >
                      Copy Token
                    </button>
                    <button className="btn-danger text-xs" onClick={logout}>
                      Revoke
                    </button>
                  </div>
                </>
              ) : (
                <div className="text-sm text-gray-500 dark:text-gray-400">
                  No active token.{" "}
                  {local
                    ? "Authentication is optional on localhost."
                    : "Login to get a token."}
                </div>
              )}
            </div>

            <div className="card">
              <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3">
                Manual Token
              </h3>
              <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">
                Paste a token from another session or API call.
              </p>
              <div className="flex gap-2">
                <input
                  className="form-input flex-1"
                  type="password"
                  placeholder="Paste token here..."
                  onChange={(e) => {
                    const val = e.target.value.trim();
                    if (val) {
                      localStorage.setItem("mizan_token", val);
                      setToken(val);
                      setMessage({ type: "success", text: "Token saved" });
                    }
                  }}
                />
              </div>
            </div>
          </div>
        )}

        {/* Audit Tab */}
        {activeTab === "audit" && (
          <div className="space-y-4">
            {auditLoading && (
              <div aria-live="polite">
                <SkeletonCard count={3} />
              </div>
            )}

            {!auditLoading && auditData && (
              <>
                {/* Summary Cards */}
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <div className="card text-center">
                    <div className="text-2xl font-mono text-gray-900 dark:text-gray-100 mb-1">
                      {auditData.total_events}
                    </div>
                    <div className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                      Total Events
                    </div>
                  </div>
                  <div className="card text-center">
                    <div className="text-2xl font-mono text-amber-600 dark:text-amber-400 mb-1">
                      {auditData.warnings}
                    </div>
                    <div className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                      Warnings
                    </div>
                  </div>
                  <div className="card text-center">
                    <div className="text-2xl font-mono text-red-600 dark:text-red-400 mb-1">
                      {auditData.errors}
                    </div>
                    <div className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                      Errors
                    </div>
                  </div>
                </div>

                {/* Recent Events */}
                <div className="card">
                  <div className="flex items-center justify-between mb-3">
                    <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                      Recent Audit Events
                    </h3>
                    <button
                      className="text-sm text-mizan-gold hover:text-mizan-gold-light transition-colors"
                      onClick={loadAudit}
                    >
                      Refresh
                    </button>
                  </div>

                  {auditData.recent.length === 0 ? (
                    <div className="text-sm text-gray-500 dark:text-gray-400 text-center py-6">
                      No audit events recorded yet.
                    </div>
                  ) : (
                    <div className="space-y-1 max-h-96 overflow-y-auto">
                      {[...auditData.recent].reverse().map((event, i) => (
                        <div
                          key={i}
                          className="flex items-start gap-3 py-2 px-3 rounded hover:bg-gray-100 dark:hover:bg-zinc-800/50 text-xs"
                        >
                          <span
                            className={`inline-block w-2 h-2 rounded-full mt-1 shrink-0 ${
                              event.severity === "error" ||
                              event.severity === "critical"
                                ? "bg-red-500"
                                : event.severity === "warning"
                                  ? "bg-amber-500"
                                  : "bg-emerald-500"
                            }`}
                          />
                          <span className="text-gray-400 dark:text-gray-500 font-mono whitespace-nowrap">
                            {event.timestamp.split("T")[1]?.split(".")[0] ||
                              event.timestamp}
                          </span>
                          <span className="font-mono text-gray-700 dark:text-gray-300 whitespace-nowrap">
                            {event.type}
                          </span>
                          <span className="text-gray-500 dark:text-gray-400 truncate">
                            {typeof event.details === "object"
                              ? Object.entries(event.details)
                                  .map(([k, v]) => `${k}: ${v}`)
                                  .join(", ")
                              : String(event.details)}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

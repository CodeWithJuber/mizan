/**
 * Security Page (Wali - وَلِيّ - Guardian)
 * Security dashboard with audit log, permissions, and auth management
 */

import { useState, useEffect, useCallback } from "react";
import type { PageProps } from "../types";

interface AuditEvent {
  severity?: string;
  event_type: string;
  timestamp: string;
  details?: string | Record<string, unknown>;
}

interface Permission {
  key: string;
  tool_name: string;
  agent_id?: string;
}

const SEVERITY_COLORS: Record<string, string> = {
  info: "var(--sapphire)",
  warning: "var(--amber)",
  error: "var(--ruby)",
  critical: "#dc2626",
};

export default function SecurityPage({ api, addTerminalLine }: PageProps) {
  const [activeTab, setActiveTab] = useState("overview");
  const [auditLog, setAuditLog] = useState<AuditEvent[]>([]);
  const [permissions, setPendingApprovals] = useState<Permission[]>([]);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [loginForm, setLoginForm] = useState({ username: "", password: "" });
  const [loginError, setLoginError] = useState("");

  useEffect(() => {
    const token = localStorage.getItem("mizan_token");
    setIsAuthenticated(!!token);
  }, []);

  const loadAudit = useCallback(async () => {
    try {
      const data = await api.get("/security/audit");
      setAuditLog((data.recent_events as AuditEvent[]) || []);
    } catch {
      // Not authenticated or endpoint not available
    }
  }, [api]);

  const loadPermissions = useCallback(async () => {
    try {
      const data = await api.get("/security/permissions");
      setPendingApprovals((data.pending_approvals as Permission[]) || []);
    } catch {}
  }, [api]);

  useEffect(() => {
    if (isAuthenticated) {
      loadAudit();
      loadPermissions();
    }
  }, [isAuthenticated, loadAudit, loadPermissions]);

  const handleLogin = async () => {
    setLoginError("");
    try {
      const data = await api.post("/auth/login", loginForm);
      if (data.token) {
        localStorage.setItem("mizan_token", data.token as string);
        localStorage.setItem("mizan_user", JSON.stringify(data));
        setIsAuthenticated(true);
        addTerminalLine?.(`Authenticated as ${data.username}`, "gold");
      } else {
        setLoginError("Invalid credentials");
      }
    } catch {
      setLoginError("Authentication failed");
    }
  };

  const handleRegister = async () => {
    setLoginError("");
    try {
      const data = await api.post("/auth/register", loginForm);
      if (data.token) {
        localStorage.setItem("mizan_token", data.token as string);
        localStorage.setItem("mizan_user", JSON.stringify(data));
        setIsAuthenticated(true);
        addTerminalLine?.(`Registered and authenticated as ${data.username}`, "gold");
      } else {
        setLoginError((data.detail as string) || "Registration failed");
      }
    } catch {
      setLoginError("Registration failed");
    }
  };

  const handleLogout = () => {
    localStorage.removeItem("mizan_token");
    localStorage.removeItem("mizan_user");
    setIsAuthenticated(false);
    addTerminalLine?.("Logged out", "info");
  };

  // Login panel
  if (!isAuthenticated) {
    return (
      <>
        <div className="panel-header">
          <div className="panel-title">Security · وَلِيّ (Wali Guardian)</div>
        </div>
        <div
          style={{
            flex: 1,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <div
            style={{
              background:
                "linear-gradient(135deg, rgba(15,32,48,0.9) 0%, rgba(10,21,32,0.9) 100%)",
              border: "1px solid rgba(201,162,39,0.3)",
              borderRadius: 12,
              padding: 32,
              width: 380,
            }}
          >
            <div
              style={{
                textAlign: "center",
                marginBottom: 24,
              }}
            >
              <div
                style={{
                  fontFamily: "Georgia, serif",
                  fontSize: 36,
                  color: "var(--gold)",
                  marginBottom: 8,
                }}
              >
                ولي
              </div>
              <div
                style={{
                  fontFamily: "var(--font-display)",
                  fontSize: 12,
                  letterSpacing: "0.15em",
                  color: "var(--text-muted)",
                  textTransform: "uppercase",
                }}
              >
                Wali Authentication
              </div>
              <div
                style={{
                  fontSize: 11,
                  color: "var(--text-muted)",
                  fontStyle: "italic",
                  marginTop: 6,
                }}
              >
                "And Allah is sufficient as a Guardian (Wali)" — 4:45
              </div>
            </div>

            <div className="form-group">
              <label className="form-label">Username</label>
              <input
                className="form-input"
                placeholder="Enter username..."
                value={loginForm.username}
                onChange={(e) =>
                  setLoginForm({ ...loginForm, username: e.target.value })
                }
                onKeyDown={(e) => e.key === "Enter" && handleLogin()}
              />
            </div>

            <div className="form-group">
              <label className="form-label">Password</label>
              <input
                className="form-input"
                type="password"
                placeholder="Enter password..."
                value={loginForm.password}
                onChange={(e) =>
                  setLoginForm({ ...loginForm, password: e.target.value })
                }
                onKeyDown={(e) => e.key === "Enter" && handleLogin()}
              />
            </div>

            {loginError && (
              <div
                style={{
                  fontSize: 11,
                  color: "var(--ruby)",
                  marginBottom: 12,
                  padding: "6px 10px",
                  background: "rgba(239,68,68,0.1)",
                  borderRadius: 4,
                  border: "1px solid rgba(239,68,68,0.2)",
                }}
              >
                {loginError}
              </div>
            )}

            <div style={{ display: "flex", gap: 8 }}>
              <button
                className="btn primary"
                style={{ flex: 1, justifyContent: "center" }}
                onClick={handleLogin}
                disabled={!loginForm.username || !loginForm.password}
              >
                Login
              </button>
              <button
                className="btn"
                style={{ flex: 1, justifyContent: "center" }}
                onClick={handleRegister}
                disabled={!loginForm.username || !loginForm.password}
              >
                Register
              </button>
            </div>
          </div>
        </div>
      </>
    );
  }

  return (
    <>
      <div className="panel-header">
        <div className="panel-title">Security · وَلِيّ (Wali Guardian)</div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <div
            style={{
              fontSize: 10,
              fontFamily: "var(--font-mono)",
              color: "var(--emerald)",
              display: "flex",
              alignItems: "center",
              gap: 4,
            }}
          >
            <div
              style={{
                width: 6,
                height: 6,
                borderRadius: "50%",
                background: "var(--emerald)",
              }}
            />
            Wali Active
          </div>
          <button className="btn" style={{ fontSize: 10 }} onClick={handleLogout}>
            Logout
          </button>
        </div>
      </div>

      <div className="tab-bar">
        {[
          { id: "overview", label: "Overview" },
          { id: "audit", label: "Audit Log" },
          { id: "permissions", label: "Permissions" },
        ].map((tab) => (
          <div
            key={tab.id}
            className={`tab ${activeTab === tab.id ? "active" : ""}`}
            onClick={() => {
              setActiveTab(tab.id);
              if (tab.id === "audit") loadAudit();
              if (tab.id === "permissions") loadPermissions();
            }}
          >
            {tab.label}
          </div>
        ))}
      </div>

      <div style={{ flex: 1, overflow: "auto", padding: 16 }}>
        {activeTab === "overview" && (
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))",
              gap: 12,
            }}
          >
            {[
              {
                label: "Auth System",
                value: "JWT + API Keys",
                arabic: "توثيق",
                color: "var(--emerald)",
                status: "Active",
              },
              {
                label: "Rate Limiting",
                value: "Token Bucket",
                arabic: "حد",
                color: "var(--sapphire)",
                status: "Active",
              },
              {
                label: "Input Validation",
                value: "Pydantic + Wali",
                arabic: "تحقق",
                color: "var(--gold)",
                status: "Active",
              },
              {
                label: "Tool Permissions",
                value: "Izn System",
                arabic: "إذن",
                color: "var(--amber)",
                status: "Active",
              },
              {
                label: "File Sandbox",
                value: "Path Restriction",
                arabic: "صندوق",
                color: "var(--ruby)",
                status: "Active",
              },
              {
                label: "SSRF Prevention",
                value: "URL Validation",
                arabic: "حماية",
                color: "#8b5cf6",
                status: "Active",
              },
            ].map((item) => (
              <div
                key={item.label}
                style={{
                  background:
                    "linear-gradient(135deg, rgba(15,32,48,0.9) 0%, rgba(10,21,32,0.9) 100%)",
                  border: "1px solid var(--border)",
                  borderRadius: 10,
                  padding: 16,
                  borderLeft: `3px solid ${item.color}`,
                }}
              >
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    marginBottom: 8,
                  }}
                >
                  <div
                    style={{
                      fontFamily: "Georgia, serif",
                      fontSize: 16,
                      color: item.color,
                    }}
                  >
                    {item.arabic}
                  </div>
                  <div
                    style={{
                      fontSize: 9,
                      fontFamily: "var(--font-mono)",
                      color: "var(--emerald)",
                      padding: "1px 6px",
                      borderRadius: 3,
                      background: "rgba(16,185,129,0.1)",
                      border: "1px solid rgba(16,185,129,0.2)",
                    }}
                  >
                    {item.status}
                  </div>
                </div>
                <div
                  style={{
                    fontFamily: "var(--font-display)",
                    fontSize: 12,
                    color: "var(--text-primary)",
                    marginBottom: 4,
                  }}
                >
                  {item.label}
                </div>
                <div
                  style={{
                    fontSize: 10,
                    color: "var(--text-muted)",
                    fontFamily: "var(--font-mono)",
                  }}
                >
                  {item.value}
                </div>
              </div>
            ))}
          </div>
        )}

        {activeTab === "audit" && (
          <div>
            {auditLog.length === 0 && (
              <div className="empty-state">
                <div className="empty-arabic">شاهد</div>
                <div className="empty-text">No audit events</div>
                <div className="empty-sub">Security events will appear here</div>
              </div>
            )}
            {auditLog.map((event, i) => (
              <div key={i} className="memory-item">
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                  }}
                >
                  <span
                    style={{
                      fontSize: 9,
                      fontFamily: "var(--font-mono)",
                      padding: "1px 6px",
                      borderRadius: 3,
                      background: `${SEVERITY_COLORS[event.severity || ""] || "var(--text-muted)"}15`,
                      color: SEVERITY_COLORS[event.severity || ""] || "var(--text-muted)",
                      border: `1px solid ${SEVERITY_COLORS[event.severity || ""] || "var(--text-muted)"}30`,
                      textTransform: "uppercase",
                    }}
                  >
                    {event.severity || "info"}
                  </span>
                  <span
                    style={{
                      fontFamily: "var(--font-mono)",
                      fontSize: 11,
                      color: "var(--text-primary)",
                    }}
                  >
                    {event.event_type}
                  </span>
                  <span
                    style={{
                      marginLeft: "auto",
                      fontSize: 10,
                      color: "var(--text-muted)",
                      fontFamily: "var(--font-mono)",
                    }}
                  >
                    {event.timestamp}
                  </span>
                </div>
                {event.details && (
                  <div
                    style={{
                      fontSize: 11,
                      color: "var(--text-secondary)",
                      marginTop: 4,
                      fontFamily: "var(--font-mono)",
                    }}
                  >
                    {typeof event.details === "string"
                      ? event.details
                      : JSON.stringify(event.details)}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        {activeTab === "permissions" && (
          <div>
            {permissions.length === 0 && (
              <div className="empty-state">
                <div className="empty-arabic">إذن</div>
                <div className="empty-text">No pending approvals</div>
                <div className="empty-sub">
                  Tool permission requests will appear here
                </div>
              </div>
            )}
            {permissions.map((perm, i) => (
              <div key={i} className="memory-item">
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                  }}
                >
                  <span className="memory-type-badge type-semantic">
                    {perm.tool_name}
                  </span>
                  <span
                    style={{
                      fontSize: 11,
                      color: "var(--text-primary)",
                    }}
                  >
                    Agent: {perm.agent_id?.substring(0, 8)}
                  </span>
                  <div
                    style={{ marginLeft: "auto", display: "flex", gap: 6 }}
                  >
                    <button
                      className="btn primary"
                      style={{ fontSize: 10, padding: "3px 10px" }}
                      onClick={async () => {
                        await api.post("/security/permissions/approve", {
                          key: perm.key,
                        });
                        loadPermissions();
                      }}
                    >
                      Approve
                    </button>
                    <button
                      className="btn danger"
                      style={{ fontSize: 10, padding: "3px 10px" }}
                      onClick={async () => {
                        await api.post("/security/permissions/deny", {
                          key: perm.key,
                        });
                        loadPermissions();
                      }}
                    >
                      Deny
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </>
  );
}

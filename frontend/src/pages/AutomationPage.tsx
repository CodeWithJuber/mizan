/**
 * Automation Page (Qadr - قَدَر - Predestination/Scheduling)
 * Task scheduling, webhooks, and proactive automation
 */

import { useState, useEffect, useCallback } from "react";
import type { PageProps, ScheduledJob, Webhook } from "../types";

export default function AutomationPage({ api, addTerminalLine }: PageProps) {
  const [activeTab, setActiveTab] = useState("jobs");
  const [jobs, setJobs] = useState<ScheduledJob[]>([]);
  const [webhooks, setWebhooks] = useState<Webhook[]>([]);
  const [showAddJob, setShowAddJob] = useState(false);
  const [showAddWebhook, setShowAddWebhook] = useState(false);
  const [newJob, setNewJob] = useState({
    name: "",
    cron: "0 9 * * *",
    task: "",
    agent_id: "",
  });
  const [newWebhook, setNewWebhook] = useState({
    name: "",
    task_template: "",
    agent_id: "",
  });
  const [loading, setLoading] = useState(true);

  const loadJobs = useCallback(async () => {
    try {
      const data = await api.get("/automation/jobs");
      setJobs((data.jobs as ScheduledJob[]) || []);
    } catch (err) {
      console.error("Failed to fetch jobs:", err);
    }
  }, [api]);

  const loadWebhooks = useCallback(async () => {
    try {
      const data = await api.get("/automation/webhooks");
      setWebhooks((data.webhooks as Webhook[]) || []);
    } catch (err) {
      console.error("Failed to fetch webhooks:", err);
    }
  }, [api]);

  useEffect(() => {
    setLoading(true);
    Promise.all([loadJobs(), loadWebhooks()]).finally(() => setLoading(false));
  }, [loadJobs, loadWebhooks]);

  const addJob = async () => {
    try {
      await api.post("/automation/jobs", newJob);
      addTerminalLine?.(`Job created: ${newJob.name}`, "gold");
      setShowAddJob(false);
      setNewJob({ name: "", cron: "0 9 * * *", task: "", agent_id: "" });
      loadJobs();
    } catch {
      addTerminalLine?.("Failed to create job", "error");
    }
  };

  const removeJob = async (jobId: string) => {
    try {
      await api.del(`/automation/jobs/${jobId}`);
      addTerminalLine?.("Job removed", "gold");
      loadJobs();
    } catch (err) {
      console.error("Failed to remove job:", err);
      addTerminalLine?.("Failed to remove job", "error");
    }
  };

  const addWebhookHandler = async () => {
    try {
      await api.post("/automation/webhooks", newWebhook);
      addTerminalLine?.(`Webhook created: ${newWebhook.name}`, "gold");
      setShowAddWebhook(false);
      setNewWebhook({ name: "", task_template: "", agent_id: "" });
      loadWebhooks();
    } catch {
      addTerminalLine?.("Failed to create webhook", "error");
    }
  };

  const CRON_PRESETS = [
    { label: "Every minute", cron: "* * * * *" },
    { label: "Every hour", cron: "0 * * * *" },
    { label: "Daily 9 AM", cron: "0 9 * * *" },
    { label: "Weekly Monday", cron: "0 9 * * 1" },
    { label: "Monthly 1st", cron: "0 9 1 * *" },
  ];

  return (
    <>
      <div className="panel-header">
        <div className="panel-title">Automation · قَدَر (Qadr)</div>
        <div style={{ display: "flex", gap: 8 }}>
          <button
            className="btn primary"
            onClick={() => setShowAddJob(true)}
            style={{ fontSize: 10 }}
          >
            + Add Job
          </button>
          <button
            className="btn"
            onClick={() => setShowAddWebhook(true)}
            style={{ fontSize: 10 }}
          >
            + Add Webhook
          </button>
        </div>
      </div>

      <div
        style={{
          padding: "4px 16px 8px",
          fontSize: 11,
          color: "var(--text-muted)",
          fontStyle: "italic",
        }}
      >
        "Indeed, all things We created with predestination (Qadr)" — Quran 54:49
      </div>

      <div className="tab-bar">
        {[
          { id: "jobs", label: "Scheduled Jobs" },
          { id: "webhooks", label: "Webhooks" },
        ].map((tab) => (
          <div
            key={tab.id}
            className={`tab ${activeTab === tab.id ? "active" : ""}`}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
          </div>
        ))}
      </div>

      {loading && (
        <div style={{ padding: 16, fontSize: 12, color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
          Loading automation data...
        </div>
      )}

      <div style={{ flex: 1, overflow: "auto", padding: 16 }}>
        {activeTab === "jobs" && (
          <>
            {jobs.length === 0 && (
              <div className="empty-state">
                <div className="empty-arabic">قدر</div>
                <div className="empty-text">No scheduled jobs</div>
                <div className="empty-sub">Create cron-like schedules for automated tasks</div>
              </div>
            )}
            {jobs.map((job) => (
              <div key={job.id} className="memory-item">
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 10,
                    marginBottom: 8,
                  }}
                >
                  <div
                    style={{
                      width: 32,
                      height: 32,
                      borderRadius: "50%",
                      background: job.enabled
                        ? "rgba(16,185,129,0.15)"
                        : "rgba(74,104,128,0.2)",
                      border: `1px solid ${job.enabled ? "rgba(16,185,129,0.3)" : "rgba(74,104,128,0.3)"}`,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      fontSize: 14,
                    }}
                  >
                    {job.enabled ? "⏱" : "⏸"}
                  </div>
                  <div style={{ flex: 1 }}>
                    <div
                      style={{
                        fontFamily: "var(--font-display)",
                        fontSize: 12,
                        color: "var(--text-primary)",
                        fontWeight: 600,
                      }}
                    >
                      {job.name}
                    </div>
                    <div
                      style={{
                        fontFamily: "var(--font-mono)",
                        fontSize: 10,
                        color: "var(--gold)",
                      }}
                    >
                      {job.cron}
                    </div>
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <div
                      style={{
                        fontSize: 10,
                        fontFamily: "var(--font-mono)",
                        color: "var(--text-muted)",
                      }}
                    >
                      Runs: {job.run_count}
                    </div>
                    <div
                      style={{
                        fontSize: 10,
                        fontFamily: "var(--font-mono)",
                        color: "var(--text-muted)",
                      }}
                    >
                      Next: {job.next_run ? new Date(job.next_run).toLocaleString() : "—"}
                    </div>
                  </div>
                  <button
                    className="btn danger"
                    style={{ padding: "4px 8px", fontSize: 10 }}
                    onClick={() => removeJob(job.id)}
                  >
                    Remove
                  </button>
                </div>
                <div
                  style={{
                    fontSize: 11,
                    color: "var(--text-secondary)",
                    padding: "6px 10px",
                    background: "rgba(6,12,16,0.5)",
                    borderRadius: 4,
                    fontFamily: "var(--font-mono)",
                  }}
                >
                  Task: {job.task}
                </div>
              </div>
            ))}
          </>
        )}

        {activeTab === "webhooks" && (
          <>
            {webhooks.length === 0 && (
              <div className="empty-state">
                <div className="empty-arabic">خطاف</div>
                <div className="empty-text">No webhooks configured</div>
                <div className="empty-sub">Create webhook endpoints for event-driven automation</div>
              </div>
            )}
            {webhooks.map((wh) => (
              <div key={wh.id} className="memory-item">
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 10,
                  }}
                >
                  <div
                    style={{
                      width: 32,
                      height: 32,
                      borderRadius: "50%",
                      background: "rgba(59,130,246,0.15)",
                      border: "1px solid rgba(59,130,246,0.3)",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      fontSize: 14,
                    }}
                  >
                    🔗
                  </div>
                  <div style={{ flex: 1 }}>
                    <div
                      style={{
                        fontFamily: "var(--font-display)",
                        fontSize: 12,
                        color: "var(--text-primary)",
                      }}
                    >
                      {wh.name}
                    </div>
                    <div
                      style={{
                        fontFamily: "var(--font-mono)",
                        fontSize: 10,
                        color: "var(--sapphire)",
                      }}
                    >
                      {wh.path}
                    </div>
                  </div>
                  <div
                    style={{
                      fontSize: 10,
                      fontFamily: "var(--font-mono)",
                      color: "var(--text-muted)",
                    }}
                  >
                    Triggered: {wh.trigger_count}x
                  </div>
                </div>
              </div>
            ))}
          </>
        )}
      </div>

      {showAddJob && (
        <div className="modal-overlay" onClick={() => setShowAddJob(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-title">
              <span
                style={{ fontFamily: "Georgia", fontSize: 22, color: "var(--gold)" }}
              >
                قدر
              </span>
              Schedule New Job
            </div>

            <div className="form-group">
              <label className="form-label">Job Name</label>
              <input
                className="form-input"
                placeholder="e.g., Morning Briefing"
                value={newJob.name}
                onChange={(e) => setNewJob({ ...newJob, name: e.target.value })}
              />
            </div>

            <div className="form-group">
              <label className="form-label">Cron Schedule</label>
              <input
                className="form-input"
                placeholder="0 9 * * *"
                value={newJob.cron}
                onChange={(e) => setNewJob({ ...newJob, cron: e.target.value })}
              />
              <div
                style={{
                  display: "flex",
                  gap: 4,
                  marginTop: 6,
                  flexWrap: "wrap",
                }}
              >
                {CRON_PRESETS.map((preset) => (
                  <button
                    key={preset.cron}
                    className="btn"
                    style={{ fontSize: 9, padding: "2px 8px" }}
                    onClick={() => setNewJob({ ...newJob, cron: preset.cron })}
                  >
                    {preset.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="form-group">
              <label className="form-label">Task Description</label>
              <textarea
                className="form-input"
                style={{ minHeight: 60, resize: "vertical" }}
                placeholder="What should the agent do?"
                value={newJob.task}
                onChange={(e) => setNewJob({ ...newJob, task: e.target.value })}
              />
            </div>

            <div className="modal-footer">
              <button className="btn" onClick={() => setShowAddJob(false)}>
                Cancel
              </button>
              <button
                className="btn primary"
                onClick={addJob}
                disabled={!newJob.name || !newJob.task}
              >
                Create Job
              </button>
            </div>
          </div>
        </div>
      )}

      {showAddWebhook && (
        <div className="modal-overlay" onClick={() => setShowAddWebhook(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-title">
              <span
                style={{ fontFamily: "Georgia", fontSize: 22, color: "var(--gold)" }}
              >
                خطاف
              </span>
              Create Webhook
            </div>

            <div className="form-group">
              <label className="form-label">Webhook Name</label>
              <input
                className="form-input"
                placeholder="e.g., GitHub Push Handler"
                value={newWebhook.name}
                onChange={(e) =>
                  setNewWebhook({ ...newWebhook, name: e.target.value })
                }
              />
            </div>

            <div className="form-group">
              <label className="form-label">Task Template</label>
              <textarea
                className="form-input"
                style={{ minHeight: 60, resize: "vertical" }}
                placeholder='e.g., Process push event from {repo} by {sender}'
                value={newWebhook.task_template}
                onChange={(e) =>
                  setNewWebhook({ ...newWebhook, task_template: e.target.value })
                }
              />
              <div
                style={{
                  fontSize: 10,
                  color: "var(--text-muted)",
                  marginTop: 4,
                }}
              >
                Use {"{key}"} placeholders for webhook payload values
              </div>
            </div>

            <div className="modal-footer">
              <button className="btn" onClick={() => setShowAddWebhook(false)}>
                Cancel
              </button>
              <button
                className="btn primary"
                onClick={addWebhookHandler}
                disabled={!newWebhook.name || !newWebhook.task_template}
              >
                Create Webhook
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

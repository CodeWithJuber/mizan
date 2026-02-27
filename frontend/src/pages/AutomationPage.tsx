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
  const [newJob, setNewJob] = useState({ name: "", cron: "0 9 * * *", task: "", agent_id: "" });
  const [newWebhook, setNewWebhook] = useState({ name: "", task_template: "", agent_id: "" });
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
    <div className="page-wrapper">
      <div className="page-header">
        <div>
          <h2 className="page-title">Automation</h2>
          <p className="page-description">قَدَر (Qadr) — Scheduling and webhooks</p>
        </div>
        <div className="flex gap-2">
          <button className="btn-gold btn-sm" onClick={() => setShowAddJob(true)}>
            + Add Job
          </button>
          <button className="btn-secondary btn-sm" onClick={() => setShowAddWebhook(true)}>
            + Add Webhook
          </button>
        </div>
      </div>

      <div className="quran-quote">
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

      {loading && <div className="loading-text">Loading automation data...</div>}

      <div className="page-body">
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
                <div className="flex items-center gap-3 mb-2">
                  <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm
                    ${job.enabled
                      ? "bg-emerald-500/15 border border-emerald-500/30"
                      : "bg-gray-200 dark:bg-zinc-700 border border-gray-300 dark:border-zinc-600"
                    }`}
                  >
                    {job.enabled ? "⏱" : "⏸"}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                      {job.name}
                    </div>
                    <div className="text-2xs font-mono text-mizan-gold">
                      {job.cron}
                    </div>
                  </div>
                  <div className="text-right shrink-0">
                    <div className="text-2xs font-mono text-gray-400 dark:text-gray-500">
                      Runs: {job.run_count}
                    </div>
                    <div className="text-2xs font-mono text-gray-400 dark:text-gray-500">
                      Next: {job.next_run ? new Date(job.next_run).toLocaleString() : "—"}
                    </div>
                  </div>
                  <button className="btn-danger btn-sm" onClick={() => removeJob(job.id)}>
                    Remove
                  </button>
                </div>
                <div className="detail-panel font-mono text-xs text-gray-600 dark:text-gray-400">
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
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-full bg-blue-500/15 border border-blue-500/30 flex items-center justify-center text-sm">
                    🔗
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                      {wh.name}
                    </div>
                    <div className="text-2xs font-mono text-blue-500 dark:text-blue-400">
                      {wh.path}
                    </div>
                  </div>
                  <div className="text-2xs font-mono text-gray-400 dark:text-gray-500">
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
              <span className="font-arabic text-2xl text-mizan-gold">قدر</span>
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
              <div className="flex gap-1 mt-2 flex-wrap">
                {CRON_PRESETS.map((preset) => (
                  <button
                    key={preset.cron}
                    className="btn-secondary btn-sm text-micro"
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
                className="form-input min-h-[60px] resize-y"
                placeholder="What should the agent do?"
                value={newJob.task}
                onChange={(e) => setNewJob({ ...newJob, task: e.target.value })}
              />
            </div>

            <div className="modal-footer">
              <button className="btn-secondary" onClick={() => setShowAddJob(false)}>Cancel</button>
              <button className="btn-gold" onClick={addJob} disabled={!newJob.name || !newJob.task}>
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
              <span className="font-arabic text-2xl text-mizan-gold">خطاف</span>
              Create Webhook
            </div>

            <div className="form-group">
              <label className="form-label">Webhook Name</label>
              <input
                className="form-input"
                placeholder="e.g., GitHub Push Handler"
                value={newWebhook.name}
                onChange={(e) => setNewWebhook({ ...newWebhook, name: e.target.value })}
              />
            </div>

            <div className="form-group">
              <label className="form-label">Task Template</label>
              <textarea
                className="form-input min-h-[60px] resize-y"
                placeholder='e.g., Process push event from {repo} by {sender}'
                value={newWebhook.task_template}
                onChange={(e) => setNewWebhook({ ...newWebhook, task_template: e.target.value })}
              />
              <div className="text-2xs text-gray-400 dark:text-gray-500 mt-1">
                Use {"{key}"} placeholders for webhook payload values
              </div>
            </div>

            <div className="modal-footer">
              <button className="btn-secondary" onClick={() => setShowAddWebhook(false)}>Cancel</button>
              <button
                className="btn-gold"
                onClick={addWebhookHandler}
                disabled={!newWebhook.name || !newWebhook.task_template}
              >
                Create Webhook
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

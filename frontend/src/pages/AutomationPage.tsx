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
      <div className="flex items-center justify-between px-5 py-3 border-b border-gray-200 dark:border-zinc-800">
        <h2 className="page-title">Automation · قَدَر (Qadr)</h2>
        <div className="flex gap-2">
          <button
            className="btn-primary text-[10px]"
            onClick={() => setShowAddJob(true)}
          >
            + Add Job
          </button>
          <button
            className="btn-secondary text-[10px]"
            onClick={() => setShowAddWebhook(true)}
          >
            + Add Webhook
          </button>
        </div>
      </div>

      <div className="px-4 pb-2 pt-1 text-xs text-gray-500 dark:text-gray-400 italic">
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
        <div className="p-4 text-xs text-gray-500 dark:text-gray-400 font-mono">
          Loading automation data...
        </div>
      )}

      <div className="flex-1 overflow-auto p-4">
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
              <div key={job.id} className="card mb-3">
                <div className="flex items-center gap-2.5 mb-2">
                  <div
                    className={`w-8 h-8 rounded-full flex items-center justify-center text-sm ${
                      job.enabled
                        ? "bg-emerald-500/15 border border-emerald-500/30"
                        : "bg-gray-500/20 border border-gray-500/30"
                    }`}
                  >
                    {job.enabled ? "⏱" : "⏸"}
                  </div>
                  <div className="flex-1">
                    <div className="text-xs font-semibold text-gray-900 dark:text-gray-100">
                      {job.name}
                    </div>
                    <div className="font-mono text-[10px] text-mizan-gold">
                      {job.cron}
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-[10px] font-mono text-gray-500 dark:text-gray-400">
                      Runs: {job.run_count}
                    </div>
                    <div className="text-[10px] font-mono text-gray-500 dark:text-gray-400">
                      Next: {job.next_run ? new Date(job.next_run).toLocaleString() : "—"}
                    </div>
                  </div>
                  <button
                    className="btn-danger px-2 py-1 text-[10px]"
                    onClick={() => removeJob(job.id)}
                  >
                    Remove
                  </button>
                </div>
                <div className="text-xs text-gray-600 dark:text-gray-300 px-2.5 py-1.5 bg-gray-100 dark:bg-zinc-800/50 rounded font-mono">
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
              <div key={wh.id} className="card mb-3">
                <div className="flex items-center gap-2.5">
                  <div className="w-8 h-8 rounded-full bg-blue-500/15 border border-blue-500/30 flex items-center justify-center text-sm">
                    🔗
                  </div>
                  <div className="flex-1">
                    <div className="text-xs text-gray-900 dark:text-gray-100">
                      {wh.name}
                    </div>
                    <div className="font-mono text-[10px] text-blue-500">
                      {wh.path}
                    </div>
                  </div>
                  <div className="text-[10px] font-mono text-gray-500 dark:text-gray-400">
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
              <span className="font-serif text-[22px] text-mizan-gold">
                قدر
              </span>
              Schedule New Job
            </div>

            <div className="space-y-1.5 mb-4">
              <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Job Name</label>
              <input
                className="input w-full text-sm"
                placeholder="e.g., Morning Briefing"
                value={newJob.name}
                onChange={(e) => setNewJob({ ...newJob, name: e.target.value })}
              />
            </div>

            <div className="space-y-1.5 mb-4">
              <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Cron Schedule</label>
              <input
                className="input w-full text-sm"
                placeholder="0 9 * * *"
                value={newJob.cron}
                onChange={(e) => setNewJob({ ...newJob, cron: e.target.value })}
              />
              <div className="flex gap-1 mt-1.5 flex-wrap">
                {CRON_PRESETS.map((preset) => (
                  <button
                    key={preset.cron}
                    className="btn-secondary text-[9px] px-2 py-0.5"
                    onClick={() => setNewJob({ ...newJob, cron: preset.cron })}
                  >
                    {preset.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="space-y-1.5 mb-4">
              <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Task Description</label>
              <textarea
                className="input w-full text-sm min-h-[60px] resize-y"
                placeholder="What should the agent do?"
                value={newJob.task}
                onChange={(e) => setNewJob({ ...newJob, task: e.target.value })}
              />
            </div>

            <div className="modal-footer">
              <button className="btn-secondary" onClick={() => setShowAddJob(false)}>
                Cancel
              </button>
              <button
                className="btn-primary"
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
              <span className="font-serif text-[22px] text-mizan-gold">
                خطاف
              </span>
              Create Webhook
            </div>

            <div className="space-y-1.5 mb-4">
              <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Webhook Name</label>
              <input
                className="input w-full text-sm"
                placeholder="e.g., GitHub Push Handler"
                value={newWebhook.name}
                onChange={(e) =>
                  setNewWebhook({ ...newWebhook, name: e.target.value })
                }
              />
            </div>

            <div className="space-y-1.5 mb-4">
              <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Task Template</label>
              <textarea
                className="input w-full text-sm min-h-[60px] resize-y"
                placeholder='e.g., Process push event from {repo} by {sender}'
                value={newWebhook.task_template}
                onChange={(e) =>
                  setNewWebhook({ ...newWebhook, task_template: e.target.value })
                }
              />
              <div className="text-[10px] text-gray-500 dark:text-gray-400 mt-1">
                Use {"{key}"} placeholders for webhook payload values
              </div>
            </div>

            <div className="modal-footer">
              <button className="btn-secondary" onClick={() => setShowAddWebhook(false)}>
                Cancel
              </button>
              <button
                className="btn-primary"
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

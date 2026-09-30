/**
 * Automation Page (Qadr - قَدَر - Predestination/Scheduling)
 * Task scheduling, webhooks, and proactive automation
 */

import { useState, useEffect, useCallback } from "react";
import type { PageProps, ScheduledJob, Webhook } from "../types";
import { SkeletonCard } from "../components/Skeleton";
import { useToast } from "../components/Toast";

const WEEKDAYS = [
  "Sunday",
  "Monday",
  "Tuesday",
  "Wednesday",
  "Thursday",
  "Friday",
  "Saturday",
];

/** Inline validation for the 5-field cron format. Returns an error string or null. */
function validateCron(cron: string): string | null {
  const parts = cron.trim().split(/\s+/);
  if (parts.length !== 5)
    return "5 hisse likho: minute hour day month weekday (jaise 0 9 * * *)";
  const ranges: [number, number][] = [
    [0, 59],
    [0, 23],
    [1, 31],
    [1, 12],
    [0, 7],
  ];
  const names = ["minute", "hour", "day", "month", "weekday"];
  for (let i = 0; i < 5; i++) {
    for (const token of parts[i].split(",")) {
      const m = token.match(/^\*(\/(\d+))?$|^(\d+)(?:-(\d+))?(\/(\d+))?$/);
      if (!m) return `"${parts[i]}" samajh nahi aaya (${names[i]} me)`;
      const nums = [m[2], m[3], m[4], m[6]]
        .filter(Boolean)
        .map((n) => parseInt(n as string, 10));
      const [lo, hi] = ranges[i];
      for (const n of nums) {
        if (n < lo || n > hi)
          return `${names[i]} ${lo}–${hi} ke beech hona chahiye`;
      }
    }
  }
  return null;
}

function formatTime12h(h: string, mi: string): string {
  const hh = parseInt(h, 10);
  const mm = mi.padStart(2, "0");
  if (Number.isNaN(hh)) return `${h}:${mm}`;
  const suffix = hh >= 12 ? "PM" : "AM";
  const h12 = hh % 12 === 0 ? 12 : hh % 12;
  return `${h12}:${mm} ${suffix}`;
}

/** Plain-English preview for common cron patterns. */
function describeCron(cron: string): string {
  if (validateCron(cron)) return "Custom schedule";
  const [mi, h, dom, mon, dow] = cron.trim().split(/\s+/);
  if (mi === "*" && h === "*" && dom === "*" && mon === "*" && dow === "*")
    return "Runs every minute";
  if (mi === "0" && h === "*" && dom === "*" && mon === "*" && dow === "*")
    return "Runs every hour";
  if (dom === "*" && mon === "*" && dow === "*")
    return `Runs every day at ${formatTime12h(h, mi)}`;
  if (dom === "*" && mon === "*" && dow !== "*") {
    const d = parseInt(dow, 10);
    const day = Number.isNaN(d) ? dow : WEEKDAYS[d % 7];
    return `Runs every week on ${day} at ${formatTime12h(h, mi)}`;
  }
  if (mon === "*" && dow === "*")
    return `Runs every month on day ${dom} at ${formatTime12h(h, mi)}`;
  return "Custom schedule";
}

const CRON_PRESETS = [
  { label: "Every day", cron: "0 9 * * *" },
  { label: "Every week", cron: "0 9 * * 1" },
  { label: "Every hour", cron: "0 * * * *" },
  { label: "Custom…", cron: "custom" },
];

export default function AutomationPage({ api, addTerminalLine }: PageProps) {
  const { addToast } = useToast();
  const [activeTab, setActiveTab] = useState("jobs");
  const [jobs, setJobs] = useState<ScheduledJob[]>([]);
  const [webhooks, setWebhooks] = useState<Webhook[]>([]);
  const [agents, setAgents] = useState<{ id: string; name: string }[]>([]);
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
  const [loadError, setLoadError] = useState(false);
  const [cronIsCustom, setCronIsCustom] = useState(false);
  const [cronError, setCronError] = useState<string | null>(null);

  const loadJobs = useCallback(async () => {
    try {
      const data = await api.get("/automation/jobs");
      setJobs((data.jobs as ScheduledJob[]) || []);
      return true;
    } catch {
      return false;
    }
  }, [api]);

  const loadWebhooks = useCallback(async () => {
    try {
      const data = await api.get("/automation/webhooks");
      setWebhooks((data.webhooks as Webhook[]) || []);
      return true;
    } catch {
      return false;
    }
  }, [api]);

  const loadAgents = useCallback(async () => {
    try {
      const data = await api.get("/api/agents");
      if (Array.isArray(data.agents)) {
        setAgents(
          data.agents.map(
            (a: { id: string; name?: string }) =>
              ({ id: a.id, name: a.name || a.id }) as {
                id: string;
                name: string;
              },
          ),
        );
      }
    } catch {
      // Optional — modals fall back to a free-text agent input.
    }
  }, [api]);

  useEffect(() => {
    setLoading(true);
    setLoadError(false);
    Promise.all([loadJobs(), loadWebhooks(), loadAgents()]).then(
      ([jobsOk, whOk]) => {
        if (!jobsOk && !whOk) setLoadError(true);
        setLoading(false);
      },
    );
  }, [loadJobs, loadWebhooks, loadAgents]);

  const resetJobForm = () => {
    setNewJob({ name: "", cron: "0 9 * * *", task: "", agent_id: "" });
    setCronIsCustom(false);
    setCronError(null);
  };

  const addJob = async () => {
    const err = validateCron(newJob.cron);
    setCronError(err);
    if (err) return;
    try {
      await api.post("/automation/jobs", newJob);
      addToast({ type: "success", title: "Job ban gaya" });
      addTerminalLine?.(`Job created: ${newJob.name}`, "gold");
      setShowAddJob(false);
      resetJobForm();
      loadJobs();
    } catch (e) {
      addToast({
        type: "error",
        title: (e as Error).message || "Job ban nahi paya",
      });
      addTerminalLine?.("Failed to create job", "error");
    }
  };

  const removeJob = async (jobId: string) => {
    if (!window.confirm("Ye scheduled job delete kar dun?")) return;
    try {
      await api.del(`/automation/jobs/${jobId}`);
      addToast({ type: "success", title: "Job delete ho gaya" });
      addTerminalLine?.("Job removed", "gold");
      loadJobs();
    } catch (e) {
      addToast({
        type: "error",
        title: (e as Error).message || "Job delete nahi ho paya",
      });
      addTerminalLine?.("Failed to remove job", "error");
    }
  };

  const addWebhookHandler = async () => {
    try {
      await api.post("/automation/webhooks", newWebhook);
      addToast({ type: "success", title: "Webhook ban gaya" });
      addTerminalLine?.(`Webhook created: ${newWebhook.name}`, "gold");
      setShowAddWebhook(false);
      setNewWebhook({ name: "", task_template: "", agent_id: "" });
      loadWebhooks();
    } catch (e) {
      addToast({
        type: "error",
        title: (e as Error).message || "Webhook ban nahi paya",
      });
      addTerminalLine?.("Failed to create webhook", "error");
    }
  };

  const copyWebhookUrl = async (path: string) => {
    try {
      await navigator.clipboard.writeText(path);
      addToast({ type: "success", title: "Copied" });
    } catch {
      addToast({ type: "error", title: "Copy nahi ho paya" });
    }
  };

  const openAddJob = () => {
    resetJobForm();
    setShowAddJob(true);
  };

  return (
    <div className="page-wrapper">
      <div className="page-header">
        <div>
          <h2 className="page-title">Automation</h2>
          <p className="page-description">
            قَدَر (Qadr) — Scheduling and webhooks
          </p>
        </div>
        <div className="flex gap-2 flex-wrap">
          <button className="btn-gold btn-sm min-h-[44px]" onClick={openAddJob}>
            + Add Job
          </button>
          <button
            className="btn-secondary btn-sm min-h-[44px]"
            onClick={() => setShowAddWebhook(true)}
          >
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

      {loading && (
        <div className="p-5" aria-live="polite">
          <SkeletonCard count={2} />
        </div>
      )}

      <div className="page-body">
        {!loading && loadError && (
          <div className="empty-state">
            <div className="empty-arabic">قدر</div>
            <div className="empty-text">Load nahi ho paya</div>
            <div className="empty-sub">
              Automation data fetch fail ho gaya — connection check karo
            </div>
            <button
              className="btn-gold btn-sm min-h-[44px] mt-3"
              onClick={() => {
                setLoading(true);
                setLoadError(false);
                Promise.all([loadJobs(), loadWebhooks()]).then(
                  ([jobsOk, whOk]) => {
                    if (!jobsOk && !whOk) setLoadError(true);
                    setLoading(false);
                  },
                );
              }}
            >
              Dobara try karo
            </button>
          </div>
        )}
        {!loadError && activeTab === "jobs" && (
          <>
            {jobs.length === 0 && (
              <div className="empty-state">
                <div className="empty-arabic">قدر</div>
                <div className="empty-text">No scheduled jobs</div>
                <div className="empty-sub">
                  Run things automatically on a schedule
                </div>
              </div>
            )}
            {jobs.map((job) => (
              <div key={job.id} className="memory-item">
                <div className="flex flex-col gap-2 sm:flex-row sm:items-center mb-2">
                  <div className="flex items-center gap-3 flex-1 min-w-0">
                    <div
                      className={`w-8 h-8 rounded-full flex items-center justify-center text-sm shrink-0
                      ${
                        job.enabled
                          ? "bg-emerald-500/15 border border-emerald-500/30"
                          : "bg-gray-200 dark:bg-zinc-700 border border-gray-300 dark:border-zinc-600"
                      }`}
                    >
                      {job.enabled ? "⏱" : "⏸"}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-semibold text-gray-900 dark:text-gray-100 truncate">
                        {job.name}
                      </div>
                      <div className="text-2xs font-mono text-mizan-gold truncate">
                        {job.cron}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <div className="text-left sm:text-right">
                      <div className="text-2xs font-mono text-gray-400 dark:text-gray-500">
                        Runs: {job.run_count}
                      </div>
                      <div className="text-2xs font-mono text-gray-400 dark:text-gray-500">
                        Next:{" "}
                        {job.next_run
                          ? new Date(job.next_run).toLocaleString()
                          : "Not scheduled yet."}
                      </div>
                    </div>
                    <button
                      className="btn-danger btn-sm min-h-[44px]"
                      onClick={() => removeJob(job.id)}
                    >
                      Remove
                    </button>
                  </div>
                </div>
                <div className="detail-panel font-mono text-xs text-gray-600 dark:text-gray-400 break-words">
                  Task: {job.task}
                </div>
              </div>
            ))}
          </>
        )}

        {!loadError && activeTab === "webhooks" && (
          <>
            {webhooks.length === 0 && (
              <div className="empty-state">
                <div className="empty-arabic">خطاف</div>
                <div className="empty-text">No webhooks configured</div>
                <div className="empty-sub">
                  Create webhook endpoints for event-driven automation
                </div>
              </div>
            )}
            {webhooks.map((wh) => (
              <div key={wh.id} className="memory-item">
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-full bg-blue-500/15 border border-blue-500/30 flex items-center justify-center text-sm shrink-0">
                    🔗
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-semibold text-gray-900 dark:text-gray-100 truncate">
                      {wh.name}
                    </div>
                    <div className="text-2xs font-mono text-blue-500 dark:text-blue-400 break-all">
                      {wh.path}
                    </div>
                  </div>
                  <div className="text-2xs font-mono text-gray-400 dark:text-gray-500 shrink-0">
                    Triggered: {wh.trigger_count}x
                  </div>
                  <button
                    className="btn-secondary btn-sm min-h-[44px] shrink-0"
                    onClick={() => copyWebhookUrl(wh.path)}
                  >
                    Copy URL
                  </button>
                </div>
              </div>
            ))}
          </>
        )}
      </div>

      {showAddJob && (
        <div className="modal-overlay" onClick={() => setShowAddJob(false)}>
          <div
            className="modal"
            role="dialog"
            aria-modal="true"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-title">
              <span className="font-arabic text-2xl text-mizan-gold">قدر</span>
              Schedule New Job
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="job-name">
                Job Name
              </label>
              <input
                id="job-name"
                className="form-input"
                placeholder="e.g., Morning Briefing"
                value={newJob.name}
                onChange={(e) => setNewJob({ ...newJob, name: e.target.value })}
              />
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="job-cron">
                How often?
              </label>
              <div className="flex gap-2 flex-wrap">
                {CRON_PRESETS.map((preset) => {
                  const isActive =
                    preset.cron === "custom"
                      ? cronIsCustom
                      : !cronIsCustom && newJob.cron === preset.cron;
                  return (
                    <button
                      key={preset.label}
                      className={`btn-sm min-h-[44px] px-3 rounded-lg border text-xs font-medium ${
                        isActive ? "btn-gold" : "btn-secondary"
                      }`}
                      onClick={() => {
                        if (preset.cron === "custom") {
                          setCronIsCustom(true);
                        } else {
                          setCronIsCustom(false);
                          setCronError(null);
                          setNewJob({ ...newJob, cron: preset.cron });
                        }
                      }}
                    >
                      {preset.label}
                    </button>
                  );
                })}
              </div>
              {!cronIsCustom && (
                <div className="text-xs text-gray-500 dark:text-gray-400 mt-1.5">
                  {describeCron(newJob.cron)}{" "}
                  <span className="font-mono">({newJob.cron})</span>
                </div>
              )}
              {cronIsCustom && (
                <>
                  <input
                    id="job-cron"
                    className="form-input mt-2 font-mono"
                    placeholder="0 9 * * *"
                    value={newJob.cron}
                    onChange={(e) => {
                      const v = e.target.value;
                      setNewJob({ ...newJob, cron: v });
                      setCronError(validateCron(v));
                    }}
                  />
                  <div className="text-2xs text-gray-400 dark:text-gray-500 mt-1">
                    minute hour day month weekday — * ka matlab "har"
                  </div>
                  {cronError ? (
                    <div className="text-xs text-red-500 dark:text-red-400 mt-1">
                      {cronError}
                    </div>
                  ) : (
                    <div className="text-xs text-emerald-600 dark:text-emerald-400 mt-1">
                      {describeCron(newJob.cron)}
                    </div>
                  )}
                </>
              )}
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="job-task">
                Task Description
              </label>
              <textarea
                id="job-task"
                className="form-input min-h-[60px] resize-y"
                placeholder="What should the agent do?"
                value={newJob.task}
                onChange={(e) => setNewJob({ ...newJob, task: e.target.value })}
              />
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="job-agent">
                Agent{" "}
                <span className="font-normal text-gray-400">(optional)</span>
              </label>
              {agents.length > 0 ? (
                <select
                  id="job-agent"
                  className="form-select"
                  value={newJob.agent_id}
                  onChange={(e) =>
                    setNewJob({ ...newJob, agent_id: e.target.value })
                  }
                >
                  <option value="">Any available agent</option>
                  {agents.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.name}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  id="job-agent"
                  className="form-input"
                  placeholder="Agent ID (optional)"
                  value={newJob.agent_id}
                  onChange={(e) =>
                    setNewJob({ ...newJob, agent_id: e.target.value })
                  }
                />
              )}
            </div>

            <div className="modal-footer">
              <button
                className="btn-secondary min-h-[44px]"
                onClick={() => setShowAddJob(false)}
              >
                Cancel
              </button>
              <button
                className="btn-gold min-h-[44px]"
                onClick={addJob}
                disabled={!newJob.name || !newJob.task || !!cronError}
              >
                Create Job
              </button>
            </div>
          </div>
        </div>
      )}

      {showAddWebhook && (
        <div className="modal-overlay" onClick={() => setShowAddWebhook(false)}>
          <div
            className="modal"
            role="dialog"
            aria-modal="true"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-title">
              <span className="font-arabic text-2xl text-mizan-gold">خطاف</span>
              Create Webhook
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="webhook-name">
                Webhook Name
              </label>
              <input
                id="webhook-name"
                className="form-input"
                placeholder="e.g., GitHub Push Handler"
                value={newWebhook.name}
                onChange={(e) =>
                  setNewWebhook({ ...newWebhook, name: e.target.value })
                }
              />
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="webhook-task">
                Task Template
              </label>
              <textarea
                id="webhook-task"
                className="form-input min-h-[60px] resize-y"
                placeholder="e.g., Process push event from {repo} by {sender}"
                value={newWebhook.task_template}
                onChange={(e) =>
                  setNewWebhook({
                    ...newWebhook,
                    task_template: e.target.value,
                  })
                }
              />
              <div className="text-2xs text-gray-400 dark:text-gray-500 mt-1">
                Use {"{key}"} placeholders for webhook payload values
              </div>
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="webhook-agent">
                Agent{" "}
                <span className="font-normal text-gray-400">(optional)</span>
              </label>
              {agents.length > 0 ? (
                <select
                  id="webhook-agent"
                  className="form-select"
                  value={newWebhook.agent_id}
                  onChange={(e) =>
                    setNewWebhook({ ...newWebhook, agent_id: e.target.value })
                  }
                >
                  <option value="">Any available agent</option>
                  {agents.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.name}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  id="webhook-agent"
                  className="form-input"
                  placeholder="Agent ID (optional)"
                  value={newWebhook.agent_id}
                  onChange={(e) =>
                    setNewWebhook({ ...newWebhook, agent_id: e.target.value })
                  }
                />
              )}
            </div>

            <div className="modal-footer">
              <button
                className="btn-secondary min-h-[44px]"
                onClick={() => setShowAddWebhook(false)}
              >
                Cancel
              </button>
              <button
                className="btn-gold min-h-[44px]"
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

/**
 * Agent Skills (SKILL.md) — the open format shared with other agent products.
 * Bundled skills ship with MIZAN; users install from GitHub or an archive,
 * or write their own. Activate one in chat with /skill-name.
 */
import { useCallback, useEffect, useState } from "react";
import { BookOpen, Download, Pencil, Sparkles, Trash2, Upload } from "lucide-react";
import type { ApiClient } from "../types";
import { useToast } from "./Toast";
import { authFetch } from "../utils/authFetch";
import { Markdown } from "./Markdown";
import { confirmDialog } from "@/components/ui/confirm";

interface AgentSkill {
  name: string;
  description: string;
  scope: "bundled" | "user" | "project";
  directory: string;
  license: string;
  compatibility: string;
  metadata: Record<string, string>;
  files: string[];
  diagnostics: string[];
  enabled: boolean;
  /** Amanah holds a skill whose instructions try to override the AI until you trust it. */
  held?: boolean;
  amanah?: string[];
}

const SCOPE_BADGE: Record<string, string> = { bundled: "badge-gold", user: "badge-success", project: "badge-info" };

export default function AgentSkillsPanel({ api }: { api: ApiClient }) {
  const { addToast } = useToast();
  const [skills, setSkills] = useState<AgentSkill[]>([]);
  const [loading, setLoading] = useState(true);
  const [viewing, setViewing] = useState<{ skill: AgentSkill; body: string } | null>(null);
  const [githubUrl, setGithubUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [editor, setEditor] = useState<{ name: string; description: string; body: string; overwrite: boolean } | null>(null);

  const load = useCallback(async () => {
    try {
      const data = await api.get("/agent-skills");
      setSkills((data.skills as AgentSkill[]) ?? []);
    } catch (error) {
      addToast({ type: "error", title: "Skills unavailable", description: (error as Error).message });
    } finally {
      setLoading(false);
    }
  }, [api, addToast]);

  useEffect(() => { void load(); }, [load]);

  const view = async (skill: AgentSkill) => {
    try {
      const data = await api.get(`/agent-skills/${encodeURIComponent(skill.name)}`);
      setViewing({ skill, body: String(data.body ?? "") });
    } catch (error) {
      addToast({ type: "error", title: "Could not open skill", description: (error as Error).message });
    }
  };

  const toggle = async (skill: AgentSkill) => {
    try {
      await api.post(`/agent-skills/${encodeURIComponent(skill.name)}/enabled`, { enabled: !skill.enabled });
      setSkills((list) => list.map((s) => s.name === skill.name ? { ...s, enabled: !s.enabled } : s));
    } catch (error) {
      addToast({ type: "error", title: "Update failed", description: (error as Error).message });
    }
  };

  const trust = async (skill: AgentSkill) => {
    try {
      await api.post(`/agent-skills/${encodeURIComponent(skill.name)}/trust`, {});
      setSkills((list) => list.map((s) => s.name === skill.name ? { ...s, held: false } : s));
      addToast({ type: "success", title: `${skill.name} is available to the agent` });
    } catch (error) {
      addToast({ type: "error", title: "Could not trust the skill", description: (error as Error).message });
    }
  };

  const remove = async (skill: AgentSkill) => {
    if (!(await confirmDialog({ title: `Remove the skill ${skill.name}?`, confirmLabel: "Remove", destructive: true }))) return;
    try {
      await api.del(`/agent-skills/${encodeURIComponent(skill.name)}`);
      await load();
    } catch (error) {
      addToast({ type: "error", title: "Remove failed", description: (error as Error).message });
    }
  };

  const installGithub = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    try {
      const data = await api.post("/agent-skills/install", { url: githubUrl.trim() });
      const names = ((data.installed as { name: string }[]) ?? []).map((s) => s.name).join(", ");
      addToast({ type: "success", title: "Skills installed", description: names });
      setGithubUrl("");
      await load();
    } catch (error) {
      addToast({ type: "error", title: "Install failed", description: (error as Error).message });
    } finally {
      setBusy(false);
    }
  };

  const upload = async (file: File | undefined) => {
    if (!file) return;
    setBusy(true);
    try {
      const form = new FormData();
      form.append("archive", file);
      const response = await authFetch(`${api.API_URL}/agent-skills/upload`, { method: "POST", body: form });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : `Upload failed (${response.status})`);
      addToast({ type: "success", title: "Skills installed" });
      await load();
    } catch (error) {
      addToast({ type: "error", title: "Upload failed", description: (error as Error).message });
    } finally {
      setBusy(false);
    }
  };

  const save = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!editor) return;
    setBusy(true);
    try {
      await api.post("/agent-skills", editor);
      addToast({ type: "success", title: `Skill ${editor.name} saved`, description: `Use it in chat with /${editor.name}` });
      setEditor(null);
      await load();
    } catch (error) {
      addToast({ type: "error", title: "Save failed", description: (error as Error).message });
    } finally {
      setBusy(false);
    }
  };

  const edit = async (skill: AgentSkill) => {
    const data = await api.get(`/agent-skills/${encodeURIComponent(skill.name)}`);
    setEditor({ name: skill.name, description: skill.description, body: String(data.body ?? ""), overwrite: true });
  };

  return (
    <div className="p-5 space-y-5">
      <div className="card space-y-3">
        <p className="text-sm text-muted-foreground">
          Skills are folders of instructions (<code>SKILL.md</code>) the agent loads when a task matches,
          the same open format used by other coding agents. Type <code>/skill-name</code> in chat to use one directly.
        </p>
        <form className="flex flex-col sm:flex-row gap-2" onSubmit={installGithub}>
          <input className="input flex-1 font-mono" placeholder="https://github.com/owner/repo/tree/main/skills/pdf" value={githubUrl} onChange={(e) => setGithubUrl(e.target.value)} required />
          <button className="btn-gold inline-flex items-center gap-1" disabled={busy}><Download className="w-4 h-4" /> Install from GitHub</button>
        </form>
        <div className="flex flex-wrap gap-2">
          <label className="btn-secondary btn-sm inline-flex items-center gap-1 cursor-pointer">
            <Upload className="w-3.5 h-3.5" /> Upload .zip / .tar.gz
            <input type="file" accept=".zip,.tar.gz,.tgz,application/zip,application/gzip" className="hidden" onChange={(e) => upload(e.target.files?.[0])} />
          </label>
          <button className="btn-secondary btn-sm inline-flex items-center gap-1" onClick={() => setEditor({ name: "", description: "", body: "# Instructions\n\n1. ", overwrite: false })}>
            <Pencil className="w-3.5 h-3.5" /> Write a skill
          </button>
        </div>
      </div>

      {editor && (
        <form className="card space-y-3" onSubmit={save}>
          <div className="grid gap-3 sm:grid-cols-3">
            <label className="space-y-1">
              <span className="text-sm font-medium">Name</span>
              <input className="input w-full font-mono" required pattern="[a-z0-9]+(-[a-z0-9]+)*" maxLength={64} disabled={editor.overwrite} value={editor.name} onChange={(e) => setEditor({ ...editor, name: e.target.value })} placeholder="my-skill" />
            </label>
            <label className="space-y-1 sm:col-span-2">
              <span className="text-sm font-medium">When to use it (description)</span>
              <input className="input w-full" required maxLength={1024} value={editor.description} onChange={(e) => setEditor({ ...editor, description: e.target.value })} placeholder="What it does and when the agent should use it" />
            </label>
          </div>
          <label className="block space-y-1">
            <span className="text-sm font-medium">Instructions (Markdown)</span>
            <textarea className="input w-full font-mono min-h-48" value={editor.body} onChange={(e) => setEditor({ ...editor, body: e.target.value })} />
          </label>
          <div className="flex gap-2">
            <button className="btn-gold" disabled={busy}>Save skill</button>
            <button type="button" className="btn-ghost" onClick={() => setEditor(null)}>Cancel</button>
          </div>
        </form>
      )}

      {loading && <p className="text-sm text-gray-500">Loading skills…</p>}
      <div className="card-grid">
        {skills.map((skill) => (
          <article key={skill.name} className={`card space-y-2 ${skill.enabled ? "" : "opacity-60"}`}>
            <div className="flex items-start gap-2">
              <Sparkles className="w-4 h-4 mt-1 text-mizan-gold shrink-0" />
              <div className="flex-1 min-w-0">
                <h3 className="font-semibold font-mono break-all">{skill.name}</h3>
                <div className="flex gap-1 flex-wrap mt-1">
                  <span className={SCOPE_BADGE[skill.scope] ?? "badge-info"}>{skill.scope}</span>
                  {skill.license && <span className="badge-info">{skill.license}</span>}
                  {skill.files.length > 0 && <span className="badge-info">{skill.files.length} files</span>}
                  {skill.held && <span className="badge-warning">held</span>}
                </div>
              </div>
            </div>
            <p className="text-sm text-muted-foreground line-clamp-4">{skill.description}</p>
            {skill.diagnostics.length > 0 && <p className="text-xs text-amber-600">⚠ {skill.diagnostics.join("; ")}</p>}
            {skill.held && (
              <div className="rounded-md bg-amber-50 dark:bg-amber-950/30 p-2 text-xs text-amber-800 dark:text-amber-300">
                <p>Amanah: this skill contains instructions aimed at overriding the AI, so the agent cannot use it until you check it. A later change holds it again.</p>
                {skill.amanah?.map((excerpt) => <p key={excerpt} className="mt-0.5 font-mono break-all">“{excerpt}”</p>)}
                <button className="btn-secondary btn-sm mt-1" onClick={() => trust(skill)}>Trust as it is now</button>
              </div>
            )}
            <div className="flex flex-wrap gap-2 pt-1">
              <button className="btn-secondary btn-sm inline-flex items-center gap-1" onClick={() => view(skill)}><BookOpen className="w-3.5 h-3.5" /> View</button>
              <button className="btn-ghost btn-sm" onClick={() => toggle(skill)}>{skill.enabled ? "Disable" : "Enable"}</button>
              {skill.scope === "user" && (
                <>
                  <button className="btn-ghost btn-sm" onClick={() => edit(skill)} aria-label={`Edit ${skill.name}`}><Pencil className="w-3.5 h-3.5" /></button>
                  <button className="btn-danger btn-sm" onClick={() => remove(skill)} aria-label={`Remove ${skill.name}`}><Trash2 className="w-3.5 h-3.5" /></button>
                </>
              )}
            </div>
          </article>
        ))}
      </div>

      {viewing && (
        <div className="modal-overlay" role="dialog" aria-modal="true" aria-label={viewing.skill.name} onClick={() => setViewing(null)}>
          <div className="modal max-w-3xl w-full max-h-[85vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-lg font-semibold font-mono">{viewing.skill.name}</h2>
              <button className="btn-ghost btn-sm" onClick={() => setViewing(null)} aria-label="Close">✕</button>
            </div>
            <p className="text-sm text-muted-foreground mb-3">{viewing.skill.description}</p>
            <div className="prose dark:prose-invert max-w-none text-sm"><Markdown content={viewing.body} /></div>
            {viewing.skill.files.length > 0 && (
              <div className="mt-4">
                <p className="text-xs font-medium text-gray-500">Bundled files</p>
                <ul className="text-xs font-mono">{viewing.skill.files.map((f) => <li key={f}>{f}</li>)}</ul>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

/** Memory: the person's Daftar ledger, what MIZAN may learn, chat memory and stored knowledge records. */
import { useEffect, useState } from "react";
import { Brain, Plus, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import DaftarPanel from "../components/DaftarPanel";
import { ConversationMemorySummary } from "../components/ConversationMemorySummary";
import { LearningConsent } from "../components/LearningConsent";
import { ReaderLessons } from "../components/ReaderLessons";
import { addToast } from "../components/Toast";
import { confirmDialog } from "@/components/ui/confirm";
import { useApi } from "../hooks/useApi";
import type { Memory } from "../types";

const TYPES = [
  { key: "all", label: "All" },
  { key: "semantic", label: "Knowledge" },
  { key: "episodic", label: "Events" },
  { key: "procedural", label: "How-to" },
] as const;

const EMPTY = { content: "", memory_type: "semantic", importance: 0.7, tags: "" };

export default function MemoryPage() {
  const api = useApi();
  const [memories, setMemories] = useState<Memory[]>([]);
  const [query, setQuery] = useState("");
  const [type, setType] = useState("all");
  const [adding, setAdding] = useState(false);
  const [draft, setDraft] = useState(EMPTY);
  const [loadError, setLoadError] = useState("");

  const load = async (search = query, filter = type) => {
    const typed: Record<string, string> = filter !== "all" ? { memory_type: filter } : {};
    try {
      const data = search.trim()
        ? await api.post("/memory/query", { query: search, limit: 30, ...typed })
        : await api.get(`/memory/list?${new URLSearchParams({ limit: "30", ...typed }).toString()}`);
      setMemories(Array.isArray(data.results) ? (data.results as Memory[]) : []);
      setLoadError("");
    } catch (error) {
      setLoadError((error as Error).message);
    }
  };

  useEffect(() => {
    void load("", "all");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const save = async () => {
    try {
      await api.post("/memory/store", {
        content: draft.content,
        memory_type: draft.memory_type,
        importance: draft.importance,
        tags: draft.tags.split(",").map((tag) => tag.trim()).filter(Boolean),
      });
    } catch (error) {
      addToast({
        type: "error",
        title: "Memory not saved",
        description: `${(error as Error).message}. Your text is still in the form.`,
      });
      return;
    }
    setDraft(EMPTY);
    setAdding(false);
    void load("", type);
    addToast({ type: "success", title: "Memory saved" });
  };

  const consolidate = async () => {
    const confirmed = await confirmDialog({
      title: "Consolidate memory?",
      description: "MIZAN links related records and deletes weak and old ones. Deleted records cannot be restored.",
      confirmLabel: "Consolidate",
      destructive: true,
    });
    if (!confirmed) return;
    try {
      await api.post("/memory/consolidate");
      addToast({ type: "success", title: "Memory consolidated" });
      void load("", type);
    } catch (error) {
      addToast({ type: "error", title: "Memory not consolidated", description: (error as Error).message });
    }
  };

  return (
    <div className="page-body">
      <DaftarPanel api={api} />
      <LearningConsent />
      <ReaderLessons />
      <ConversationMemorySummary />

      <section className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="mr-auto text-base font-semibold">Knowledge records</h2>
          <form
            className="flex items-center gap-2"
            onSubmit={(event) => {
              event.preventDefault();
              void load(query, type);
            }}
          >
            <Input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search memories…"
              aria-label="Search memories"
              className="w-full sm:w-56"
            />
            <Button type="submit" variant="outline" size="icon" aria-label="Search"><Search /></Button>
          </form>
          <Button
            variant="outline"
            onClick={() => void consolidate()}
          >
            Consolidate
          </Button>
          <Button onClick={() => setAdding((value) => !value)}><Plus /> Add</Button>
        </div>

        {adding && (
          <div className="card space-y-3">
            <textarea
              className="form-input h-20 resize-none"
              placeholder="What should MIZAN remember?"
              value={draft.content}
              onChange={(event) => setDraft({ ...draft, content: event.target.value })}
            />
            <div className="flex flex-wrap items-center gap-2">
              <select
                className="form-select w-auto"
                value={draft.memory_type}
                onChange={(event) => setDraft({ ...draft, memory_type: event.target.value })}
                aria-label="Kind of memory"
              >
                <option value="semantic">Knowledge / fact</option>
                <option value="episodic">Experience / event</option>
                <option value="procedural">How-to / process</option>
              </select>
              <Input
                className="w-48"
                placeholder="Tags (comma-separated)"
                value={draft.tags}
                onChange={(event) => setDraft({ ...draft, tags: event.target.value })}
              />
              <div className="ml-auto flex gap-2">
                <Button variant="outline" onClick={() => setAdding(false)}>Cancel</Button>
                <Button disabled={!draft.content.trim()} onClick={() => void save()}>Save memory</Button>
              </div>
            </div>
          </div>
        )}

        <div className="flex flex-wrap gap-1">
          {TYPES.map((tab) => (
            <Button
              key={tab.key}
              size="sm"
              variant={type === tab.key ? "secondary" : "ghost"}
              onClick={() => {
                setType(tab.key);
                void load(query, tab.key);
              }}
            >
              {tab.label}
            </Button>
          ))}
        </div>

        {loadError ? (
          <div role="alert" className="empty-state">
            <Brain className="size-8 text-muted-foreground" />
            <p className="empty-text mt-3">Could not load knowledge records</p>
            <p className="empty-sub">{loadError}. Check that the server is running, then try again.</p>
            <Button variant="outline" className="mt-3" onClick={() => void load(query, type)}>Try again</Button>
          </div>
        ) : memories.length === 0 ? (
          <div className="empty-state">
            <Brain className="size-8 text-muted-foreground" />
            <p className="empty-text mt-3">No knowledge records stored yet</p>
            <p className="empty-sub">
              Add one here, or keep chatting — conversations are remembered separately in your chat memory.
            </p>
          </div>
        ) : (
          <div className="space-y-2">
            {memories.map((memory) => (
              <div key={memory.id} className="card p-4">
                <div className="mb-2 flex items-center gap-2 text-xs text-muted-foreground">
                  <span className="badge badge-gold">
                    {memory.type === "semantic" ? "knowledge" : memory.type === "procedural" ? "how-to" : memory.type}
                  </span>
                  <span className="font-mono">{memory.agent_id ? `Agent ${memory.agent_id.substring(0, 8)}` : "System"}</span>
                  <span className="ml-auto">Importance {(memory.importance * 100).toFixed(0)}%</span>
                </div>
                <div className="text-sm leading-relaxed" dir="auto">
                  {typeof memory.content === "string" ? memory.content : JSON.stringify(memory.content)}
                </div>
                {(memory.tags?.length ?? 0) > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1">
                    {memory.tags!.map((tag) => <span key={tag} className="tool-tag">{tag}</span>)}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

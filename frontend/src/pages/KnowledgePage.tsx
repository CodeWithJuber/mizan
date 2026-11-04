/** Knowledge: feed MIZAN web pages, YouTube videos and PDFs. */
import { useEffect, useState } from "react";
import { FileUp, Link2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { config } from "../config";
import { authFetch } from "../utils/authFetch";

interface Source {
  title: string;
  type: string;
  chunks: number;
  last_updated: string;
}

export default function KnowledgePage() {
  const [url, setUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [sources, setSources] = useState<Source[]>([]);
  const [result, setResult] = useState<string | null>(null);

  const [sourcesError, setSourcesError] = useState("");
  const loadSources = async () => {
    try {
      const res = await authFetch(`${config.API_URL}/knowledge/sources`);
      if (!res.ok) throw new Error(`the server answered ${res.status}`);
      const data = await res.json();
      setSources(data.sources || []);
      setSourcesError("");
    } catch (error) {
      setSourcesError((error as Error).message);
    }
  };
  useEffect(() => {
    void loadSources();
  }, []);

  const ingest = async () => {
    if (!url.trim()) return;
    setLoading(true);
    setResult(null);
    try {
      const res = await authFetch(`${config.API_URL}/knowledge/ingest`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source: url.trim() }),
      });
      const data = await res.json();
      if (res.ok) {
        setResult(`Ingested "${data.title}" — ${data.chunks_stored} chunks stored (${data.char_count?.toLocaleString()} chars)`);
        setUrl("");
        void loadSources();
      } else {
        setResult(`Error: ${data.detail || "Failed to ingest"}`);
      }
    } catch (error) {
      setResult(`Error: ${error instanceof Error ? error.message : "Network error"}`);
    } finally {
      setLoading(false);
    }
  };

  const upload = async (file: File) => {
    setLoading(true);
    setResult(null);
    try {
      const form = new FormData();
      form.append("file", file);
      const res = await authFetch(`${config.API_URL}/knowledge/upload`, { method: "POST", body: form });
      const data = await res.json();
      if (res.ok) {
        setResult(`Uploaded "${data.title}" — ${data.page_count} pages, ${data.chunks_stored} chunks stored`);
        void loadSources();
      } else {
        setResult(`Error: ${data.detail || "Upload failed"}`);
      }
    } catch (error) {
      setResult(`Error: ${error instanceof Error ? error.message : "Network error"}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="page-body">
      <div className="grid gap-4 lg:grid-cols-2">
        <section className="card space-y-3">
          <h2 className="flex items-center gap-2 font-semibold"><Link2 className="size-4 text-brand" /> From a link</h2>
          <p className="text-sm text-muted-foreground">A web page or a YouTube link; its text is stored as knowledge.</p>
          <form
            className="flex gap-2"
            onSubmit={(event) => {
              event.preventDefault();
              if (!loading) void ingest();
            }}
          >
            <Input
              placeholder="https://example.com or a YouTube link"
              value={url}
              onChange={(event) => setUrl(event.target.value)}
              disabled={loading}
              aria-label="Link to ingest"
            />
            <Button type="submit" disabled={loading || !url.trim()}>{loading ? "Ingesting…" : "Ingest"}</Button>
          </form>
        </section>
        <section className="card space-y-3">
          <h2 className="flex items-center gap-2 font-semibold"><FileUp className="size-4 text-brand" /> Upload a PDF</h2>
          <p className="text-sm text-muted-foreground">Its text is extracted into knowledge (up to 20 MB).</p>
          <label
            className={`flex cursor-pointer items-center justify-center rounded-xl border-2 border-dashed p-5 text-sm text-muted-foreground transition-colors hover:border-ring/60 hover:bg-muted/40 ${loading ? "pointer-events-none opacity-50" : ""}`}
          >
            <input
              type="file"
              accept=".pdf"
              className="hidden"
              disabled={loading}
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) void upload(file);
                event.target.value = "";
              }}
            />
            {loading ? "Uploading…" : "Choose a PDF"}
          </label>
        </section>
      </div>
      {result && (
        <div
          role="status"
          className={`rounded-lg border px-3 py-2 text-sm ${result.startsWith("Error") ? "border-destructive/30 bg-destructive/8 text-destructive" : "border-success/30 bg-success/8 text-success"}`}
        >
          {result}
        </div>
      )}
      <section className="card space-y-3">
        <h2 className="font-semibold">Sources ({sources.length})</h2>
        {sourcesError ? (
          <p role="alert" className="text-sm text-muted-foreground">
            Could not load your sources: {sourcesError}.{" "}
            <button type="button" className="rounded underline focus-ring" onClick={() => void loadSources()}>
              Try again
            </button>
          </p>
        ) : sources.length === 0 ? (
          <p className="text-sm text-muted-foreground">Nothing ingested yet. Add a link or a PDF above.</p>
        ) : (
          <ul className="divide-y">
            {sources.map((source, index) => (
              <li key={index} className="flex items-center gap-3 py-2">
                <span className="badge badge-gold">{source.type}</span>
                <span className="min-w-0 flex-1 truncate text-sm">{source.title}</span>
                <span className="shrink-0 text-xs text-muted-foreground">{source.chunks} chunks</span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

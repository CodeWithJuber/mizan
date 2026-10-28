/**
 * Ta'lim (Developer → Teach MIZAN): an administrator adds examples to MIZAN's
 * understanding (what a message asks, its yes/no facets, its language), typed
 * in or imported from a Hugging Face dataset. A batch is kept only if it does
 * not make MIZAN worse at what it already knew; every batch is listed with
 * that verdict and can be undone.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import type { ApiClient } from "../types";
import { useToast } from "./Toast";
import {
  isTalimView,
  parseExamples,
  parseLabelMap,
  percent,
  verdict,
  type TalimReport,
  type TalimView,
} from "../utils/talim.ts";

const MODEL_HELP: Record<string, string> = {
  qasd: "What a message asks for (intent)",
  lughah: "Which language a message is in",
};

function modelHelp(name: string): string {
  if (MODEL_HELP[name]) return MODEL_HELP[name];
  return name.startsWith("qasd.") ? `Yes/no: is the message about "${name.slice(5)}"?` : name;
}

function Report({ report }: { report: TalimReport }) {
  const changed = Object.entries(report.changed_classes);
  return (
    <div className="text-xs text-gray-600 dark:text-gray-300 space-y-1">
      <p className={report.kept ? "text-green-700 dark:text-green-400" : "text-red-600 dark:text-red-400"}>
        {verdict(report)}
      </p>
      <p>
        {report.examples} examples; {report.seeds_scored} known examples re-read by leave-one-out.
      </p>
      {changed.length > 0 && (
        <ul className="list-disc pl-4">
          {changed.slice(0, 8).map(([label, entry]) => (
            <li key={label}>
              {label}: {percent(entry.before)} → {percent(entry.after)} ({entry.n})
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function TalimPanel({ api }: { api: ApiClient }) {
  const { addToast } = useToast();
  const [view, setView] = useState<TalimView | null>(null);
  const [error, setError] = useState("");
  const [model, setModel] = useState("qasd");
  const [lines, setLines] = useState("");
  const [languageName, setLanguageName] = useState("");
  const [source, setSource] = useState("");
  const [licence, setLicence] = useState("");
  const [busy, setBusy] = useState(false);
  const [last, setLast] = useState<TalimReport | null>(null);
  const [dataset, setDataset] = useState("");
  const [config, setConfig] = useState("default");
  const [split, setSplit] = useState("train");
  const [textColumn, setTextColumn] = useState("text");
  const [labelColumn, setLabelColumn] = useState("label");
  const [labelMap, setLabelMap] = useState("");
  const [limit, setLimit] = useState("500");

  const load = useCallback(async () => {
    try {
      const data = await api.get("/api/tadbir/talim");
      if (isTalimView(data)) {
        setView(data);
        setError("");
      }
    } catch {
      setError("Teaching is for administrators, or MIZAN could not be reached.");
    }
  }, [api]);

  useEffect(() => {
    void load();
  }, [load]);

  const labels = useMemo(() => view?.models[model] ?? [], [view, model]);
  const parsed = useMemo(() => parseExamples(lines, labels, model === "lughah"), [lines, labels, model]);

  const finish = async (result: Record<string, unknown>) => {
    const report = result as unknown as TalimReport;
    setLast(report);
    addToast({
      type: report.kept ? "success" : "info",
      title: report.kept ? "Kept: MIZAN learned the batch" : "Refused: the batch made MIZAN worse",
    });
    await load();
  };

  const teach = async () => {
    if (!parsed.examples.length || parsed.errors.length) return;
    setBusy(true);
    try {
      await finish(
        await api.post("/api/tadbir/talim", {
          model,
          examples: parsed.examples,
          source: source || "typed by an administrator",
          licence,
          language_name: languageName,
        }),
      );
      setLines("");
    } catch {
      addToast({ type: "error", title: "MIZAN could not take this batch; check the labels." });
    } finally {
      setBusy(false);
    }
  };

  const importRows = async () => {
    if (!dataset.trim()) return;
    setBusy(true);
    try {
      await finish(
        await api.post("/api/tadbir/talim/import", {
          model,
          dataset: dataset.trim(),
          config,
          split,
          text_column: textColumn,
          label_column: labelColumn,
          label_map: parseLabelMap(labelMap),
          limit: Math.max(1, Math.min(5000, Number(limit) || 500)),
          licence,
          language_name: languageName,
        }),
      );
    } catch {
      addToast({ type: "error", title: "The import failed: check the dataset, columns and labels." });
    } finally {
      setBusy(false);
    }
  };

  const undo = async (id: string) => {
    try {
      await api.del(`/api/tadbir/talim/${id}`);
      addToast({ type: "success", title: "Batch undone" });
      await load();
    } catch {
      addToast({ type: "error", title: "Could not undo that batch." });
    }
  };

  if (error) return <p className="text-sm text-gray-500 dark:text-gray-400">{error}</p>;
  if (!view) return <p className="text-sm text-gray-500 dark:text-gray-400">Loading…</p>;

  return (
    <div className="space-y-5">
      <div className="card p-4 space-y-2">
        <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Teach MIZAN</h3>
        <p className="text-xs text-gray-500 dark:text-gray-400">
          Add examples to how MIZAN understands messages. A batch is refitted with what MIZAN already
          knew and kept only if it does not make it worse there (leave-one-out before and after, paired
          bootstrap, refused at P(worse) ≥ 0.95).{" "}
          {!view.enabled && "Teaching is off on this server (MIZAN_TALIM=off): batches are kept but set aside."}
        </p>
        <label className="block text-xs font-medium text-gray-600 dark:text-gray-300">
          Model
          <select
            className="input mt-1 w-full"
            value={model}
            onChange={(event) => setModel(event.target.value)}
          >
            {Object.keys(view.models).map((name) => (
              <option key={name} value={name}>
                {name} — {modelHelp(name)}
              </option>
            ))}
          </select>
        </label>
        <p className="text-xs text-gray-500 dark:text-gray-400 break-words">
          Labels: {labels.join(", ") || "—"}
          {model === "lughah" && " · a new language code (for example ta) adds that language"}
        </p>
      </div>

      <div className="card p-4 space-y-3">
        <h4 className="text-sm font-medium text-gray-900 dark:text-gray-100">Type examples</h4>
        <textarea
          className="input w-full font-mono text-xs"
          rows={8}
          placeholder={"compute | 2 ki power 10 kitna hai\nconverse | Assalamu alaikum, kaise ho?"}
          value={lines}
          onChange={(event) => setLines(event.target.value)}
          aria-label="Examples, one per line: label | text"
        />
        {parsed.errors.length > 0 && (
          <ul className="text-xs text-red-600 dark:text-red-400 list-disc pl-4">
            {parsed.errors.slice(0, 5).map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        )}
        <div className="grid gap-2 sm:grid-cols-3">
          <input className="input" placeholder="Source (optional)" value={source} onChange={(e) => setSource(e.target.value)} />
          <input className="input" placeholder="Licence (optional)" value={licence} onChange={(e) => setLicence(e.target.value)} />
          {model === "lughah" && (
            <input
              className="input"
              placeholder="New language's name (Tamil)"
              value={languageName}
              onChange={(e) => setLanguageName(e.target.value)}
            />
          )}
        </div>
        <button
          className="btn-primary"
          disabled={busy || !parsed.examples.length || parsed.errors.length > 0}
          onClick={() => void teach()}
        >
          {busy ? "Judging…" : `Teach ${parsed.examples.length || ""} example(s)`}
        </button>
      </div>

      <div className="card p-4 space-y-3">
        <h4 className="text-sm font-medium text-gray-900 dark:text-gray-100">Import from Hugging Face</h4>
        <div className="grid gap-2 sm:grid-cols-2">
          <input className="input" placeholder="Dataset (owner/name)" value={dataset} onChange={(e) => setDataset(e.target.value)} />
          <input className="input" placeholder="Config" value={config} onChange={(e) => setConfig(e.target.value)} />
          <input className="input" placeholder="Split" value={split} onChange={(e) => setSplit(e.target.value)} />
          <input className="input" placeholder="Rows (1-5000)" value={limit} onChange={(e) => setLimit(e.target.value)} />
          <input className="input" placeholder="Text column" value={textColumn} onChange={(e) => setTextColumn(e.target.value)} />
          <input className="input" placeholder="Label column" value={labelColumn} onChange={(e) => setLabelColumn(e.target.value)} />
        </div>
        <textarea
          className="input w-full font-mono text-xs"
          rows={3}
          placeholder={"Label map, one per line (dataset label = MIZAN label):\ngreeting = converse"}
          value={labelMap}
          onChange={(event) => setLabelMap(event.target.value)}
          aria-label="Label map"
        />
        <button className="btn-secondary" disabled={busy || !dataset.trim()} onClick={() => void importRows()}>
          {busy ? "Importing…" : "Import and judge"}
        </button>
      </div>

      {last && (
        <div className="card p-4">
          <h4 className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-2">Last batch</h4>
          <Report report={last} />
        </div>
      )}

      <div className="card p-4 space-y-3">
        <h4 className="text-sm font-medium text-gray-900 dark:text-gray-100">
          Batches ({view.batches.length})
          {Object.keys(view.languages).length > 0 &&
            ` · languages taught: ${Object.entries(view.languages)
              .map(([code, name]) => `${name} (${code})`)
              .join(", ")}`}
        </h4>
        {view.batches.length === 0 && (
          <p className="text-xs text-gray-500 dark:text-gray-400">Nothing taught yet.</p>
        )}
        <ul className="space-y-3">
          {view.batches.map((batch) => (
            <li key={batch.id} className="border-t border-gray-100 dark:border-zinc-800 pt-3 space-y-1">
              <div className="flex flex-wrap items-baseline justify-between gap-2 text-xs">
                <span className="font-medium text-gray-800 dark:text-gray-200">
                  {batch.model} · {batch.size} examples · {batch.status}
                </span>
                <span className="text-gray-500 dark:text-gray-400">
                  {new Date(batch.created * 1000).toLocaleString()} · {batch.by}
                </span>
              </div>
              <p className="text-xs text-gray-500 dark:text-gray-400 break-words">
                {batch.source}
                {batch.licence && ` · ${batch.licence}`}
              </p>
              <Report report={batch.report} />
              {batch.status === "kept" && (
                <button className="btn-secondary btn-sm" onClick={() => void undo(batch.id)}>
                  Undo
                </button>
              )}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

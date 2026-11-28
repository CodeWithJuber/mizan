/** Before/after of a tool that changed since the person accepted it: its description by word, its schema by line. */
import { cn } from "@/lib/utils";
import { changed, diffLines, diffWords, stableJson, type DiffPart } from "./diff";
import type { ConnectorTool } from "./types";

function Words({ parts }: { parts: DiffPart[] }) {
  return (
    <p className="whitespace-pre-wrap break-words rounded-md border bg-background p-2 text-xs leading-relaxed">
      {parts.map((part, index) =>
        part.kind === "same" ? (
          <span key={index}>{part.text}</span>
        ) : part.kind === "del" ? (
          <del key={index} className="rounded-sm bg-destructive/12 text-destructive decoration-destructive/60">
            <span className="sr-only">removed: </span>{part.text}
          </del>
        ) : (
          <ins key={index} className="rounded-sm bg-success/15 text-foreground no-underline">
            <span className="sr-only">added: </span>{part.text}
          </ins>
        ))}
    </p>
  );
}

function Lines({ parts }: { parts: DiffPart[] }) {
  const lines = parts.flatMap((part) =>
    part.text.replace(/\n$/, "").split("\n").map((text) => ({ kind: part.kind, text })));
  return (
    <pre className="max-h-72 overflow-auto rounded-md border bg-background py-1 font-mono text-xs">
      {lines.map((line, index) => (
        <div
          key={index}
          className={cn(
            "whitespace-pre px-2",
            line.kind === "add" && "bg-success/15",
            line.kind === "del" && "bg-destructive/12 text-destructive",
          )}
        >
          <span aria-hidden className="mr-2 select-none text-muted-foreground">
            {line.kind === "add" ? "+" : line.kind === "del" ? "−" : " "}
          </span>
          <span className="sr-only">{line.kind === "add" ? "added: " : line.kind === "del" ? "removed: " : ""}</span>
          {line.text || " "}
        </div>
      ))}
    </pre>
  );
}

function hintChanges(before: unknown, tool: ConnectorTool): string[] {
  if (!before || typeof before !== "object") return [];
  const old = before as Record<string, unknown>;
  const notes: string[] = [];
  if (typeof old.readOnlyHint === "boolean" && old.readOnlyHint !== tool.read_only) {
    notes.push(tool.read_only ? "Now says it only reads." : "No longer says it only reads.");
  }
  if (typeof old.destructiveHint === "boolean" && old.destructiveHint !== tool.destructive) {
    notes.push(tool.destructive ? "Now says it may delete or overwrite." : "No longer says it may delete or overwrite.");
  }
  return notes;
}

export function ToolChange({ tool }: { tool: ConnectorTool }) {
  const before = tool.previous;
  if (!before) return null;
  const description = diffWords(before.description, tool.description);
  const schema = diffLines(stableJson(before.input_schema), stableJson(tool.input_schema));
  // Annotations are compared only when the server sends both; otherwise the read-only/destructive hints are.
  const annotations = before.annotations != null && tool.annotations != null
    ? diffLines(stableJson(before.annotations), stableJson(tool.annotations))
    : [];
  const hints = hintChanges(before.annotations, tool);
  const any = changed(description) || changed(schema) || changed(annotations) || hints.length > 0;
  return (
    <div className="space-y-2">
      <p className="text-xs font-medium">What changed</p>
      {!any && <p className="text-xs text-muted-foreground">The server reports a change, but the description and inputs read the same.</p>}
      {changed(description) && (
        <div className="space-y-1">
          <p className="text-xs text-muted-foreground">Description</p>
          <Words parts={description} />
        </div>
      )}
      {changed(schema) && (
        <div className="space-y-1">
          <p className="text-xs text-muted-foreground">Inputs (JSON schema)</p>
          <Lines parts={schema} />
        </div>
      )}
      {hints.length > 0 && (
        <ul className="list-disc space-y-0.5 pl-5 text-xs">
          {hints.map((hint) => <li key={hint}>{hint}</li>)}
        </ul>
      )}
      {changed(annotations) && (
        <div className="space-y-1">
          <p className="text-xs text-muted-foreground">Annotations</p>
          <Lines parts={annotations} />
        </div>
      )}
    </div>
  );
}

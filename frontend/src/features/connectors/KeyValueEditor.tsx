/**
 * Headers (remote servers) or environment variables (local ones). A value
 * saved on the server is write-only: the page shows its name, and it can be
 * replaced or deleted, never read back.
 */
import { Eye, EyeOff, Plus, RotateCcw, Trash2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { type KeyValueRow, newRow } from "./logic";

interface Props {
  kind: "headers" | "env";
  rows: KeyValueRow[];
  onChange: (rows: KeyValueRow[]) => void;
  error?: string;
  idPrefix: string;
}

export function KeyValueEditor({ kind, rows, onChange, error, idPrefix }: Props) {
  const noun = kind === "headers" ? "header" : "variable";
  const set = (id: string, change: Partial<KeyValueRow>) => onChange(rows.map((row) => (row.id === id ? { ...row, ...change } : row)));
  const remove = (id: string) => onChange(rows.filter((row) => row.id !== id));
  const errorId = `${idPrefix}-error`;
  return (
    <fieldset className="space-y-2" aria-describedby={error ? errorId : undefined}>
      <legend className="text-sm font-medium">
        {kind === "headers" ? "Headers" : "Environment variables"}
        <span className="ml-1.5 text-xs font-normal text-muted-foreground">stored encrypted, never shown again</span>
      </legend>
      {rows.length === 0 && (
        <p className="text-xs text-muted-foreground">
          {kind === "headers" ? "None. Add one for an API key, for example Authorization." : "None. Add one for an API key the server reads."}
        </p>
      )}
      <ul className="space-y-2">
        {rows.map((row, index) => {
          const keyId = `${idPrefix}-${row.id}-key`;
          const valueId = `${idPrefix}-${row.id}-value`;
          if (row.saved) {
            const deleting = row.mode === "delete";
            const replacing = row.mode === "replace";
            return (
              <li key={row.id} className="rounded-lg border bg-muted/40 p-2">
                <div className="flex flex-wrap items-center gap-2">
                  <code className={cn("min-w-0 break-all font-mono text-xs font-medium", deleting && "text-muted-foreground line-through")}>{row.key}</code>
                  <span className="text-xs text-muted-foreground">
                    {deleting ? "will be deleted when you save" : replacing ? "new value:" : "saved · hidden"}
                  </span>
                  <span className="ml-auto flex gap-1">
                    {row.mode === "keep" ? (
                      <>
                        <Button type="button" size="xs" variant="outline" aria-label={`Replace ${row.key}`} onClick={() => set(row.id, { mode: "replace", value: "" })}>
                          Replace
                        </Button>
                        <Button type="button" size="xs" variant="ghost" aria-label={`Delete ${row.key}`} onClick={() => set(row.id, { mode: "delete", value: "" })}>
                          <Trash2 /> Delete
                        </Button>
                      </>
                    ) : (
                      <Button type="button" size="xs" variant="ghost" onClick={() => set(row.id, { mode: "keep", value: "" })}>
                        <RotateCcw /> {deleting ? "Undo" : "Keep the saved value"}
                      </Button>
                    )}
                  </span>
                </div>
                {replacing && (
                  <Input
                    className="mt-2 font-mono"
                    type="password"
                    autoComplete="off"
                    aria-label={`New value for ${row.key}`}
                    placeholder="New value"
                    value={row.value}
                    onChange={(event) => set(row.id, { value: event.target.value })}
                  />
                )}
              </li>
            );
          }
          return (
            <li key={row.id} className="space-y-1">
              <div className="flex flex-col gap-2 sm:flex-row sm:items-start">
                <label htmlFor={keyId} className="sr-only">{`${noun === "header" ? "Header" : "Variable"} ${index + 1} name`}</label>
                <Input
                  id={keyId}
                  className="font-mono sm:w-2/5"
                  placeholder={kind === "headers" ? "Authorization" : "API_KEY"}
                  autoComplete="off"
                  spellCheck={false}
                  value={row.key}
                  onChange={(event) => set(row.id, { key: event.target.value })}
                />
                <div className="flex min-w-0 flex-1 gap-1">
                  <label htmlFor={valueId} className="sr-only">{`Value of ${row.key || `${noun} ${index + 1}`}${row.required ? " (required)" : ""}`}</label>
                  <Input
                    id={valueId}
                    className="font-mono"
                    type={row.secret ? "password" : "text"}
                    autoComplete="off"
                    spellCheck={false}
                    placeholder={row.required ? "Value (required)" : "Value"}
                    aria-required={row.required || undefined}
                    value={row.value}
                    onChange={(event) => set(row.id, { value: event.target.value })}
                  />
                  <Button
                    type="button"
                    size="icon"
                    variant="ghost"
                    aria-label={row.secret ? `Show the value of ${row.key || `${noun} ${index + 1}`}` : `Hide the value of ${row.key || `${noun} ${index + 1}`}`}
                    aria-pressed={!row.secret}
                    onClick={() => set(row.id, { secret: !row.secret })}
                  >
                    {row.secret ? <Eye /> : <EyeOff />}
                  </Button>
                  <Button type="button" size="icon" variant="ghost" aria-label={`Remove ${row.key || `${noun} ${index + 1}`}`} onClick={() => remove(row.id)}>
                    <X />
                  </Button>
                </div>
              </div>
              {row.description && <p className="text-xs text-muted-foreground">{row.description}</p>}
            </li>
          );
        })}
      </ul>
      {error && <p id={errorId} className="text-xs text-destructive">{error}</p>}
      <Button type="button" size="sm" variant="outline" onClick={() => onChange([...rows, newRow({ secret: true })])}>
        <Plus /> Add {noun}
      </Button>
    </fieldset>
  );
}

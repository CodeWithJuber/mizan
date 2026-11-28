/**
 * A connector asks the person for a few values while a reply runs (MCP
 * elicitation). Shown in the run timeline beside approval prompts: the form
 * built from its schema (or raw JSON), and Send / Decline / Cancel.
 *
 * MIZAN's own question before an action it would otherwise guess (Tabayyun,
 * kind "question") uses the same card: one field, prefilled with the value it
 * would have guessed, and the answer is read as the person's own words.
 */
import { useId, useState, type FormEvent } from "react";
import { MessageSquareText } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import type { ElicitationRequest } from "../../utils/agentActivity";
import {
  type ElicitationAction, type ElicitField, type ElicitValues, collect, initialValues, inputType, parseRaw, schemaFields,
} from "../../utils/elicitation";

const DECIDED: Record<string, string> = {
  accept: "answered",
  decline: "declined",
  cancel: "cancelled",
  expired: "expired before the answer arrived",
};

const SELECT =
  "h-8 w-full rounded-lg border border-input bg-background px-2 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30";

function Field({ field, value, error, onChange, id }: {
  field: ElicitField; value: string | boolean; error?: string; onChange: (value: string | boolean) => void; id: string;
}) {
  const hint = [field.description ? `${id}-hint` : "", error ? `${id}-error` : ""].filter(Boolean).join(" ") || undefined;
  const label = (
    <Label htmlFor={id} id={`${id}-label`}>
      {field.label}
      {field.required && <span className="text-muted-foreground"> (required)</span>}
    </Label>
  );
  return (
    <div className="space-y-1">
      {field.kind === "boolean" ? (
        <div className="flex items-center gap-2">
          <Switch id={id} checked={value === true} onCheckedChange={(checked) => onChange(checked)}
            aria-labelledby={`${id}-label`} aria-describedby={hint} />
          {label}
        </div>
      ) : (
        <>
          {label}
          {field.kind === "choice" ? (
            <select id={id} className={SELECT} value={String(value)} aria-describedby={hint} aria-invalid={error ? true : undefined}
              onChange={(event) => onChange(event.target.value)}>
              {!field.required || !value ? <option value="">Choose…</option> : null}
              {field.options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
          ) : (
            <Input
              id={id}
              type={inputType(field)}
              value={String(value)}
              aria-describedby={hint}
              aria-invalid={error ? true : undefined}
              {...(field.kind === "number"
                ? { step: field.integer ? 1 : "any", ...(field.minimum !== undefined ? { min: field.minimum } : {}), ...(field.maximum !== undefined ? { max: field.maximum } : {}) }
                : field.kind === "text" && field.maxLength !== undefined ? { maxLength: field.maxLength } : {})}
              onChange={(event) => onChange(event.target.value)}
            />
          )}
        </>
      )}
      {field.description && <p id={`${id}-hint`} className="text-xs text-muted-foreground">{field.description}</p>}
      {error && <p id={`${id}-error`} className="text-xs text-destructive">{error}</p>}
    </div>
  );
}

export function ElicitationPrompt({ request, onAnswer }: {
  request: ElicitationRequest;
  onAnswer?: (id: string, action: ElicitationAction, content?: Record<string, unknown>) => Promise<void> | void;
}) {
  const uid = useId();
  const [fields] = useState(() => schemaFields(request.schema));
  const [values, setValues] = useState<ElicitValues>(() => (fields ? initialValues(fields) : {}));
  const [raw, setRaw] = useState("{}");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  const asking = request.kind === "question";
  if (request.decision) {
    return (
      <li className="flex items-center gap-2 px-1.5 text-xs text-muted-foreground">
        <MessageSquareText className="size-3.5" aria-hidden />
        {asking ? "MIZAN's question before acting" : `${request.server}'s question`} {DECIDED[request.decision] ?? request.decision}
      </li>
    );
  }

  const answer = async (action: ElicitationAction, content?: Record<string, unknown>) => {
    if (!onAnswer) return;
    setBusy(true);
    try {
      await onAnswer(request.id, action, content);
    } finally {
      setBusy(false);
    }
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (fields) {
      const result = collect(fields, values);
      if ("errors" in result) {
        setErrors(result.errors);
        return;
      }
      setErrors({});
      void answer("accept", result.content);
    } else {
      const result = parseRaw(raw);
      if ("error" in result) {
        setErrors({ raw: result.error });
        return;
      }
      setErrors({});
      void answer("accept", result.content);
    }
  };

  const titleId = `${uid}-title`;
  return (
    <li className="rounded-lg border border-primary/50 bg-primary/8 p-3">
      <form aria-labelledby={titleId} onSubmit={submit} className="flex items-start gap-2" noValidate>
        <MessageSquareText className="mt-0.5 size-4 shrink-0 text-brand" aria-hidden />
        <div className="min-w-0 flex-1 space-y-2">
          <p id={titleId} className="text-sm font-medium">{asking ? "MIZAN asks before acting" : `${request.server} asks you`}</p>
          {request.message && <p className="whitespace-pre-wrap break-words text-sm">{request.message}</p>}
          <p className="text-xs text-muted-foreground">
            {asking
              ? `Nothing runs until you answer. Your answer is read as your own words${request.tool ? ` for ${request.tool}` : ""}; Decline and it does not run.`
              : `Your answer goes to ${request.server} only. Never give it a password here.`}
          </p>
          {fields ? (
            fields.length > 0 && (
              <div className="space-y-3">
                {fields.map((field) => (
                  <Field
                    key={field.name}
                    id={`${uid}-${field.name}`}
                    field={field}
                    value={values[field.name] ?? ""}
                    error={errors[field.name]}
                    onChange={(value) => setValues((current) => ({ ...current, [field.name]: value }))}
                  />
                ))}
              </div>
            )
          ) : (
            <div className="space-y-1">
              <Label htmlFor={`${uid}-raw`}>Answer as JSON</Label>
              <Textarea id={`${uid}-raw`} className="font-mono text-xs" value={raw} spellCheck={false}
                aria-describedby={`${uid}-raw-hint`} aria-invalid={errors.raw ? true : undefined}
                onChange={(event) => setRaw(event.target.value)} />
              <p id={`${uid}-raw-hint`} className="text-xs text-muted-foreground">
                The form for this question can't be shown here, so answer with a JSON object.
              </p>
              <details>
                <summary className="cursor-pointer text-xs text-muted-foreground">What it asks for</summary>
                <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap break-words font-mono text-xs">
                  {JSON.stringify(request.schema, null, 2)}
                </pre>
              </details>
              {errors.raw && <p className="text-xs text-destructive">{errors.raw}</p>}
            </div>
          )}
          {onAnswer && (
            <div className="flex flex-wrap gap-2 pt-1">
              <Button size="sm" type="submit" disabled={busy}>Send</Button>
              <Button size="sm" type="button" variant="outline" disabled={busy} onClick={() => void answer("decline")}>Decline</Button>
              <Button size="sm" type="button" variant="ghost" disabled={busy} onClick={() => void answer("cancel")}>Cancel</Button>
            </div>
          )}
        </div>
      </form>
    </li>
  );
}

/**
 * MCP elicitation: a connector asks the person for a few values mid-run. Its
 * requested schema is a flat object of strings, numbers, booleans and
 * choices; that becomes a small form. Anything else (arrays, nested objects)
 * is answered as raw JSON instead.
 */

export type ElicitationAction = "accept" | "decline" | "cancel";

interface Common {
  name: string;
  label: string;
  description?: string;
  required: boolean;
}

export type ElicitField =
  | (Common & { kind: "text"; format?: "email" | "uri" | "date" | "date-time"; minLength?: number; maxLength?: number; default?: string })
  | (Common & { kind: "number"; integer: boolean; minimum?: number; maximum?: number; default?: number })
  | (Common & { kind: "boolean"; default?: boolean })
  | (Common & { kind: "choice"; options: { value: string; label: string }[]; default?: string });

export type ElicitValues = Record<string, string | boolean>;

type Raw = Record<string, unknown>;
const record = (value: unknown): Raw | null => (value && typeof value === "object" && !Array.isArray(value) ? value as Raw : null);
const num = (value: unknown) => (typeof value === "number" && Number.isFinite(value) ? value : undefined);
const str = (value: unknown) => (typeof value === "string" && value ? value : undefined);
const FORMATS = ["email", "uri", "date", "date-time"] as const;

function choices(property: Raw): { value: string; label: string }[] | null {
  if (Array.isArray(property.enum)) {
    if (!property.enum.every((item) => typeof item === "string")) return null;
    const names = Array.isArray(property.enumNames) ? property.enumNames : [];
    return (property.enum as string[]).map((value, index) => ({ value, label: typeof names[index] === "string" ? names[index] : value }));
  }
  const options = Array.isArray(property.oneOf) ? property.oneOf : Array.isArray(property.anyOf) ? property.anyOf : null;
  if (!options) return null;
  const mapped = options.map((option) => {
    const item = record(option);
    return item && typeof item.const === "string" ? { value: item.const, label: str(item.title) ?? item.const } : null;
  });
  return mapped.every(Boolean) ? mapped as { value: string; label: string }[] : null;
}

/** The form for a requested schema, or null when it is not a flat object of supported fields. */
export function schemaFields(schema: unknown): ElicitField[] | null {
  const root = record(schema);
  if (!root) return null;
  if (root.type !== undefined && root.type !== "object") return null;
  const properties = record(root.properties);
  if (!properties) return null;
  const required = new Set(Array.isArray(root.required) ? root.required.filter((item): item is string => typeof item === "string") : []);
  const fields: ElicitField[] = [];
  for (const [name, value] of Object.entries(properties)) {
    const property = record(value);
    if (!property) return null;
    const common: Common = {
      name,
      label: str(property.title) ?? name,
      required: required.has(name),
      ...(str(property.description) ? { description: str(property.description) } : {}),
    };
    const options = choices(property);
    if (options && (property.type === undefined || property.type === "string")) {
      fields.push({ ...common, kind: "choice", options, ...(str(property.default) ? { default: str(property.default) } : {}) });
    } else if (property.type === "string") {
      const format = FORMATS.find((item) => item === property.format);
      fields.push({
        ...common,
        kind: "text",
        ...(format ? { format } : {}),
        ...(num(property.minLength) !== undefined ? { minLength: num(property.minLength) } : {}),
        ...(num(property.maxLength) !== undefined ? { maxLength: num(property.maxLength) } : {}),
        ...(typeof property.default === "string" ? { default: property.default } : {}),
      });
    } else if (property.type === "number" || property.type === "integer") {
      fields.push({
        ...common,
        kind: "number",
        integer: property.type === "integer",
        ...(num(property.minimum) !== undefined ? { minimum: num(property.minimum) } : {}),
        ...(num(property.maximum) !== undefined ? { maximum: num(property.maximum) } : {}),
        ...(num(property.default) !== undefined ? { default: num(property.default) } : {}),
      });
    } else if (property.type === "boolean") {
      fields.push({ ...common, kind: "boolean", ...(typeof property.default === "boolean" ? { default: property.default } : {}) });
    } else {
      return null;
    }
  }
  return fields;
}

export function initialValues(fields: ElicitField[]): ElicitValues {
  const values: ElicitValues = {};
  for (const field of fields) {
    if (field.kind === "boolean") values[field.name] = field.default ?? false;
    else if (field.kind === "number") values[field.name] = field.default === undefined ? "" : String(field.default);
    else values[field.name] = field.default ?? "";
  }
  return values;
}

export type Collected = { content: Record<string, unknown> } | { errors: Record<string, string> };

/** The answer to send, or what is wrong with it per field. Empty optional fields are left out. */
export function collect(fields: ElicitField[], values: ElicitValues): Collected {
  const content: Record<string, unknown> = {};
  const errors: Record<string, string> = {};
  for (const field of fields) {
    const value = values[field.name];
    if (field.kind === "boolean") {
      content[field.name] = value === true;
      continue;
    }
    const text = typeof value === "string" ? value : "";
    if (!text.trim()) {
      if (field.required) errors[field.name] = "Required.";
      continue;
    }
    if (field.kind === "number") {
      const n = Number(text);
      if (!Number.isFinite(n)) errors[field.name] = "Enter a number.";
      else if (field.integer && !Number.isInteger(n)) errors[field.name] = "Enter a whole number.";
      else if (field.minimum !== undefined && n < field.minimum) errors[field.name] = `At least ${field.minimum}.`;
      else if (field.maximum !== undefined && n > field.maximum) errors[field.name] = `At most ${field.maximum}.`;
      else content[field.name] = n;
    } else if (field.kind === "choice") {
      if (field.options.some((option) => option.value === text)) content[field.name] = text;
      else errors[field.name] = "Choose one of the options.";
    } else {
      if (field.minLength !== undefined && text.length < field.minLength) errors[field.name] = `At least ${field.minLength} characters.`;
      else if (field.maxLength !== undefined && text.length > field.maxLength) errors[field.name] = `At most ${field.maxLength} characters.`;
      else if (field.format === "email" && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(text)) errors[field.name] = "Enter an email address.";
      else if (field.format === "uri" && !/^[a-z][a-z0-9+.-]*:\S+$/i.test(text)) errors[field.name] = "Enter a full address, such as https://example.com.";
      else content[field.name] = text;
    }
  }
  return Object.keys(errors).length ? { errors } : { content };
}

/** The raw-JSON answer: an object, or why it is not one. */
export function parseRaw(text: string): { content: Record<string, unknown> } | { error: string } {
  if (!text.trim()) return { content: {} };
  try {
    const value: unknown = JSON.parse(text);
    const object = record(value);
    return object ? { content: object } : { error: "The answer must be a JSON object, such as {\"name\": \"value\"}." };
  } catch {
    return { error: "This is not valid JSON." };
  }
}

/** HTML input type for a text field's format. */
export function inputType(field: ElicitField): string {
  if (field.kind === "number") return "number";
  if (field.kind !== "text") return "text";
  return field.format === "email" ? "email" : field.format === "uri" ? "url" : field.format === "date" ? "date"
    : field.format === "date-time" ? "datetime-local" : "text";
}

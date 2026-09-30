/**
 * agentDisplay.ts — resolve a chat message's sender label (pure functions).
 *
 * The backend sends `agent_id` (a UUID) on chat messages. The sender label
 * must never show a raw UUID/hex id — it resolves through the loaded agents
 * list and falls back to a human label.
 */

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
// Bare hex ids (e.g. 24-char mongo-style, 32/40/64-char hashes).
const HEX_ID_RE = /^[0-9a-f]{24,64}$/i;

/** True when the string looks like a raw machine id, not a display name. */
export function looksLikeRawId(value: string): boolean {
  const v = value.trim();
  if (!v) return false;
  return UUID_RE.test(v) || HEX_ID_RE.test(v);
}

export interface NamedAgent {
  id: string;
  name: string;
}

/**
 * Resolve the sender label for a chat message.
 *  - agent id found in the loaded agents list -> the agent's display name
 *  - agent id is UUID/hex-like but unknown        -> selected agent name, else "Assistant"
 *  - agent value is already a display name        -> shown as-is
 *  - no agent value                               -> selected agent name, else "MIZAN"
 */
export function resolveAgentName(
  agentId: string | undefined | null,
  agents?: NamedAgent[],
  selectedAgentName?: string | null,
): string {
  const selected =
    selectedAgentName && !looksLikeRawId(selectedAgentName)
      ? selectedAgentName
      : null;
  if (!agentId || !agentId.trim()) return selected ?? "MIZAN";
  const id = agentId.trim();
  const match = agents?.find((a) => a.id === id);
  if (match?.name) return match.name;
  if (looksLikeRawId(id)) return selected ?? "Assistant";
  return id;
}

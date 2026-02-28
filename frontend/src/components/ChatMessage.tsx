import { useState, useMemo } from "react";
import type {
  ChatMessage as ChatMessageType,
  CognitiveMetadata,
  PerceptionResult,
} from "../types";
import { Markdown } from "./Markdown";

type ContentBlock =
  | { type: "text"; content: string }
  | { type: "tool"; name: string; result: string; isError: boolean }
  | { type: "error"; content: string };

function parseChatContent(text: string): ContentBlock[] {
  const blocks: ContentBlock[] = [];
  const pattern =
    /\[Tool:\s*(\w+)\]\s*→\s*([\s\S]*?)(?=\n\[Tool:|\n\[Error:|\n\n|$)|\[Error:\s*([\s\S]*?)\]/g;
  const matches = [...text.matchAll(pattern)];

  if (matches.length === 0) {
    const trimmed = text.trim();
    if (trimmed) blocks.push({ type: "text", content: trimmed });
    return blocks;
  }

  let lastIndex = 0;
  for (const match of matches) {
    if (match.index !== undefined && match.index > lastIndex) {
      const preceding = text.slice(lastIndex, match.index).trim();
      if (preceding) blocks.push({ type: "text", content: preceding });
    }
    if (match[0].startsWith("[Tool:")) {
      const result = (match[2] || "").trim();
      blocks.push({
        type: "tool",
        name: match[1],
        result,
        isError:
          result.toLowerCase().includes('"error"') ||
          result.startsWith('{"error'),
      });
    } else if (match[0].startsWith("[Error:")) {
      blocks.push({ type: "error", content: (match[3] || "").trim() });
    }
    lastIndex = (match.index || 0) + match[0].length;
  }

  if (lastIndex < text.length) {
    const trailing = text.slice(lastIndex).trim();
    if (trailing) blocks.push({ type: "text", content: trailing });
  }
  return blocks;
}

export function TypingIndicator() {
  return (
    <span className="inline-flex gap-1 items-center py-1">
      <span className="w-1.5 h-1.5 rounded-full bg-gray-400 dark:bg-gray-500 animate-bounce" style={{ animationDelay: "0ms" }} />
      <span className="w-1.5 h-1.5 rounded-full bg-gray-400 dark:bg-gray-500 animate-bounce" style={{ animationDelay: "150ms" }} />
      <span className="w-1.5 h-1.5 rounded-full bg-gray-400 dark:bg-gray-500 animate-bounce" style={{ animationDelay: "300ms" }} />
    </span>
  );
}

export function ChatMessageContent({ content }: { content: string }) {
  const [expandedTools, setExpandedTools] = useState<Set<number>>(new Set());
  const blocks = useMemo(() => parseChatContent(content), [content]);

  const toggleTool = (idx: number) => {
    setExpandedTools((prev) => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx);
      else next.add(idx);
      return next;
    });
  };

  if (blocks.length === 1 && blocks[0].type === "text") {
    return <Markdown content={blocks[0].content} />;
  }

  return (
    <div className="space-y-2">
      {blocks.map((block, idx) => {
        if (block.type === "text") {
          return <Markdown key={idx} content={block.content} />;
        }

        if (block.type === "error") {
          return (
            <div
              key={idx}
              className="flex items-start gap-2 px-3 py-2.5 rounded-lg bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20"
              role="alert"
            >
              <svg
                viewBox="0 0 20 20"
                fill="currentColor"
                className="w-4 h-4 text-red-500 shrink-0 mt-0.5"
                aria-hidden="true"
              >
                <path
                  fillRule="evenodd"
                  d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-8-5a.75.75 0 01.75.75v4.5a.75.75 0 01-1.5 0v-4.5A.75.75 0 0110 5zm0 10a1 1 0 100-2 1 1 0 000 2z"
                  clipRule="evenodd"
                />
              </svg>
              <div className="text-xs text-red-700 dark:text-red-300 font-mono leading-relaxed break-all">
                {block.content}
              </div>
            </div>
          );
        }

        if (block.type === "tool") {
          const isExpanded = expandedTools.has(idx);
          const truncated =
            block.result.length > 120
              ? block.result.slice(0, 120) + "..."
              : block.result;

          return (
            <div
              key={idx}
              className={`rounded-lg border transition-colors ${
                block.isError
                  ? "bg-red-50/50 dark:bg-red-500/5 border-red-200/60 dark:border-red-500/15"
                  : "bg-gray-50 dark:bg-zinc-800/50 border-gray-200/60 dark:border-zinc-700/50"
              }`}
            >
              <button
                className="w-full flex items-center gap-2 px-3 py-2 text-left cursor-pointer focus-ring rounded-lg"
                onClick={() => toggleTool(idx)}
                aria-expanded={isExpanded}
                aria-label={`Tool: ${block.name}${block.isError ? " (failed)" : ""}`}
              >
                <div
                  className={`flex items-center gap-1.5 px-2 py-0.5 rounded-md text-xs font-mono font-medium ${
                    block.isError
                      ? "bg-red-100 dark:bg-red-500/15 text-red-600 dark:text-red-400"
                      : "bg-blue-100 dark:bg-blue-500/15 text-blue-600 dark:text-blue-400"
                  }`}
                >
                  <svg
                    viewBox="0 0 20 20"
                    fill="currentColor"
                    className="w-3 h-3"
                    aria-hidden="true"
                  >
                    <path
                      fillRule="evenodd"
                      d="M14.5 10a4.5 4.5 0 004.284-5.882c-.105-.324-.51-.391-.752-.15L15.34 6.66a.454.454 0 01-.493.101 3.046 3.046 0 01-1.609-1.61.454.454 0 01.101-.492l2.692-2.692c.24-.241.174-.647-.15-.752a4.5 4.5 0 00-5.873 4.575c.055.873-.128 1.808-.8 2.368l-7.482 6.19a1.879 1.879 0 102.7 2.618l6.337-7.326c.523-.603 1.398-.773 2.24-.738z"
                      clipRule="evenodd"
                    />
                  </svg>
                  {block.name}
                </div>
                {block.isError && (
                  <span className="text-xs text-red-500 font-medium">
                    failed
                  </span>
                )}
                <svg
                  viewBox="0 0 20 20"
                  fill="currentColor"
                  className={`w-3.5 h-3.5 ml-auto text-gray-400 transition-transform ${isExpanded ? "rotate-180" : ""}`}
                  aria-hidden="true"
                >
                  <path
                    fillRule="evenodd"
                    d="M5.23 7.21a.75.75 0 011.06.02L10 11.168l3.71-3.938a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z"
                    clipRule="evenodd"
                  />
                </svg>
              </button>
              {isExpanded ? (
                <div className="px-3 pb-2">
                  <pre className="text-xs font-mono text-gray-600 dark:text-gray-400 bg-gray-100 dark:bg-zinc-900 rounded p-2 overflow-x-auto max-h-48 overflow-y-auto whitespace-pre-wrap break-all leading-relaxed">
                    {block.result}
                  </pre>
                </div>
              ) : block.result ? (
                <div className="px-3 pb-2">
                  <div className="text-xs font-mono text-gray-400 dark:text-gray-500 truncate">
                    {truncated}
                  </div>
                </div>
              ) : null}
            </div>
          );
        }
        return null;
      })}
    </div>
  );
}

// ===== Qalb state → color mapping =====
const QALB_COLORS: Record<string, string> = {
  neutral: "bg-gray-100 dark:bg-zinc-700/40 text-gray-600 dark:text-gray-300",
  positive:
    "bg-emerald-100 dark:bg-emerald-500/15 text-emerald-700 dark:text-emerald-400",
  frustrated: "bg-red-100 dark:bg-red-500/15 text-red-700 dark:text-red-400",
  anxious:
    "bg-amber-100 dark:bg-amber-500/15 text-amber-700 dark:text-amber-400",
  confused:
    "bg-purple-100 dark:bg-purple-500/15 text-purple-700 dark:text-purple-400",
  determined:
    "bg-blue-100 dark:bg-blue-500/15 text-blue-700 dark:text-blue-400",
  fatigued: "bg-gray-100 dark:bg-zinc-700/40 text-gray-500 dark:text-gray-400",
};

const YAQIN_LABELS: Record<string, string> = {
  ilm_al_yaqin: "'ilm",
  ayn_al_yaqin: "'ayn",
  haqq_al_yaqin: "haqq",
};

const LUBB_COLORS: Record<string, string> = {
  confident:
    "bg-emerald-100 dark:bg-emerald-500/15 text-emerald-700 dark:text-emerald-400",
  hedged:
    "bg-amber-100 dark:bg-amber-500/15 text-amber-700 dark:text-amber-400",
  uncertain: "bg-red-100 dark:bg-red-500/15 text-red-700 dark:text-red-400",
};

function CognitiveBar({ cognitive }: { cognitive: CognitiveMetadata }) {
  const [expanded, setExpanded] = useState(false);

  const hasPills =
    cognitive.qalb ||
    cognitive.yaqin ||
    cognitive.lubb ||
    cognitive.ruh_energy != null ||
    cognitive.nafs_level != null ||
    (cognitive.lawwama && cognitive.lawwama.repair_level > 0);

  if (!hasPills) return null;

  return (
    <div className="mt-1.5 animate-fade-in">
      <button
        onClick={() => setExpanded((prev) => !prev)}
        className="flex flex-wrap items-center gap-1.5 cursor-pointer group"
        aria-expanded={expanded}
        aria-label="Cognitive metadata"
      >
        {/* Qalb state pill */}
        {cognitive.qalb && (
          <span
            className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium ${QALB_COLORS[cognitive.qalb.state] || QALB_COLORS.neutral}`}
            title={`Qalb: ${cognitive.qalb.state} (${(cognitive.qalb.confidence * 100).toFixed(0)}%)`}
          >
            <span className="opacity-60">Qalb</span>
            {cognitive.qalb.state}
          </span>
        )}

        {/* Yaqin level pill */}
        {cognitive.yaqin && (
          <span
            className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-sky-100 dark:bg-sky-500/15 text-sky-700 dark:text-sky-400"
            title={`Yaqin: ${cognitive.yaqin.level} (${(cognitive.yaqin.confidence * 100).toFixed(0)}%)`}
          >
            <span className="opacity-60">Yaqin</span>
            {YAQIN_LABELS[cognitive.yaqin.level] || cognitive.yaqin.level}
            <span className="w-8 h-1 rounded-full bg-sky-200 dark:bg-sky-800 overflow-hidden inline-block align-middle">
              <span
                className="block h-full rounded-full bg-sky-500 dark:bg-sky-400"
                style={{ width: `${cognitive.yaqin.confidence * 100}%` }}
              />
            </span>
          </span>
        )}

        {/* Lubb quality pill */}
        {cognitive.lubb && (
          <span
            className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium ${LUBB_COLORS[cognitive.lubb.quality] || LUBB_COLORS.uncertain}`}
            title={`Lubb: ${cognitive.lubb.quality} (coherence ${(cognitive.lubb.coherence_score * 100).toFixed(0)}%)`}
          >
            <span className="opacity-60">Lubb</span>
            {cognitive.lubb.quality}
          </span>
        )}

        {/* Ruh energy pill */}
        {cognitive.ruh_energy != null && (
          <span
            className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-indigo-100 dark:bg-indigo-500/15 text-indigo-700 dark:text-indigo-400"
            title={`Ruh energy: ${(cognitive.ruh_energy * 100).toFixed(0)}%`}
          >
            <span className="opacity-60">Ruh</span>
            {(cognitive.ruh_energy * 100).toFixed(0)}%
          </span>
        )}

        {/* Nafs level pill */}
        {cognitive.nafs_level != null && (
          <span
            className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-mizan-gold/10 text-mizan-gold-text dark:text-mizan-gold border border-mizan-gold/20"
            title={`Nafs: Level ${cognitive.nafs_level} — ${cognitive.nafs_name || ""}`}
          >
            N{cognitive.nafs_level}
            {cognitive.nafs_name && (
              <span className="opacity-70">{cognitive.nafs_name}</span>
            )}
          </span>
        )}

        {/* Lawwama repair pill (only when active) */}
        {cognitive.lawwama && cognitive.lawwama.repair_level > 0 && (
          <span
            className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-orange-100 dark:bg-orange-500/15 text-orange-700 dark:text-orange-400"
            title={`Lawwama: L${cognitive.lawwama.repair_level} repair, health ${(cognitive.lawwama.health * 100).toFixed(0)}%`}
          >
            <span className="opacity-60">Heal</span>L
            {cognitive.lawwama.repair_level}
          </span>
        )}

        {/* Expand chevron */}
        <svg
          viewBox="0 0 20 20"
          fill="currentColor"
          className={`w-3 h-3 text-gray-400 transition-transform ${expanded ? "rotate-180" : ""}`}
          aria-hidden="true"
        >
          <path
            fillRule="evenodd"
            d="M5.23 7.21a.75.75 0 011.06.02L10 11.168l3.71-3.938a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z"
            clipRule="evenodd"
          />
        </svg>
      </button>

      {/* Expanded details */}
      {expanded && (
        <div className="mt-1.5 p-2.5 rounded-lg bg-gray-50/80 dark:bg-zinc-800/50 border border-gray-200/60 dark:border-zinc-700/40 text-xs space-y-1.5 animate-fade-in">
          {cognitive.cognitive_method && (
            <div className="text-gray-500 dark:text-gray-400">
              <span className="font-medium text-gray-700 dark:text-gray-300">
                Method:
              </span>{" "}
              {cognitive.cognitive_method}
            </div>
          )}
          {cognitive.mizan_label && (
            <div className="text-gray-500 dark:text-gray-400">
              <span className="font-medium text-gray-700 dark:text-gray-300">
                Mizan:
              </span>{" "}
              {cognitive.mizan_label}
            </div>
          )}
          {cognitive.qalb?.signals && cognitive.qalb.signals.length > 0 && (
            <div className="text-gray-500 dark:text-gray-400">
              <span className="font-medium text-gray-700 dark:text-gray-300">
                Signals:
              </span>{" "}
              {cognitive.qalb.signals.join(", ")}
            </div>
          )}
          {cognitive.yaqin?.evidence && cognitive.yaqin.evidence.length > 0 && (
            <div className="text-gray-500 dark:text-gray-400">
              <span className="font-medium text-gray-700 dark:text-gray-300">
                Evidence:
              </span>{" "}
              {cognitive.yaqin.evidence.join(", ")}
            </div>
          )}
          {cognitive.lubb?.bias_flags &&
            cognitive.lubb.bias_flags.length > 0 && (
              <div className="text-orange-600 dark:text-orange-400">
                <span className="font-medium">Bias flags:</span>{" "}
                {cognitive.lubb.bias_flags.join(", ")}
              </div>
            )}
          {cognitive.lawwama && (
            <div className="text-gray-500 dark:text-gray-400">
              <span className="font-medium text-gray-700 dark:text-gray-300">
                Health:
              </span>{" "}
              {(cognitive.lawwama.health * 100).toFixed(0)}% | Hallucination:{" "}
              {(cognitive.lawwama.hallucination_score * 100).toFixed(0)}% |
              Errors: {cognitive.lawwama.errors}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

const PERCEPTION_CATEGORY_COLORS: Record<string, string> = {
  text: "bg-blue-100 dark:bg-blue-500/15 text-blue-700 dark:text-blue-400",
  diagram: "bg-purple-100 dark:bg-purple-500/15 text-purple-700 dark:text-purple-400",
  screenshot: "bg-cyan-100 dark:bg-cyan-500/15 text-cyan-700 dark:text-cyan-400",
  photo: "bg-emerald-100 dark:bg-emerald-500/15 text-emerald-700 dark:text-emerald-400",
  document: "bg-amber-100 dark:bg-amber-500/15 text-amber-700 dark:text-amber-400",
};

function PerceptionCard({ perception }: { perception: PerceptionResult }) {
  const [expanded, setExpanded] = useState(false);
  const basirah = perception.perception?.basirah;
  const nutq = perception.perception?.nutq;

  return (
    <div className="mt-2 animate-fade-in">
      <button
        onClick={() => setExpanded((prev) => !prev)}
        className="flex flex-wrap items-center gap-1.5 cursor-pointer group"
        aria-expanded={expanded}
        aria-label="Perception results"
      >
        {/* Vision pill */}
        {basirah && (
          <span
            className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium ${PERCEPTION_CATEGORY_COLORS[basirah.category] || PERCEPTION_CATEGORY_COLORS.text}`}
            title={`Basirah: ${basirah.category} (${(basirah.confidence * 100).toFixed(0)}%)`}
          >
            <svg viewBox="0 0 20 20" fill="currentColor" className="w-3 h-3" aria-hidden="true">
              <path d="M10 12.5a2.5 2.5 0 100-5 2.5 2.5 0 000 5z" />
              <path fillRule="evenodd" d="M.664 10.59a1.651 1.651 0 010-1.186A10.004 10.004 0 0110 3c4.257 0 7.893 2.66 9.336 6.41.147.381.146.804 0 1.186A10.004 10.004 0 0110 17c-4.257 0-7.893-2.66-9.336-6.41zM14 10a4 4 0 11-8 0 4 4 0 018 0z" clipRule="evenodd" />
            </svg>
            {basirah.category}
          </span>
        )}

        {/* Audio pill */}
        {nutq && (
          <span
            className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-indigo-100 dark:bg-indigo-500/15 text-indigo-700 dark:text-indigo-400"
            title={`Nutq: ${nutq.intent} (${nutq.language})`}
          >
            <svg viewBox="0 0 20 20" fill="currentColor" className="w-3 h-3" aria-hidden="true">
              <path d="M7 4a3 3 0 016 0v6a3 3 0 11-6 0V4z" />
              <path d="M5.5 9.643a.75.75 0 00-1.5 0V10c0 3.06 2.29 5.585 5.25 5.954V17.5h-1.5a.75.75 0 000 1.5h4.5a.75.75 0 000-1.5h-1.5v-1.546A6.001 6.001 0 0016 10v-.357a.75.75 0 00-1.5 0V10a4.5 4.5 0 01-9 0v-.357z" />
            </svg>
            {nutq.intent}
          </span>
        )}

        {/* Key terms pills */}
        {perception.key_terms?.slice(0, 3).map((term, i) => (
          <span
            key={i}
            className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium bg-amber-50 dark:bg-amber-500/10 text-amber-700 dark:text-amber-400 border border-amber-200/40 dark:border-amber-500/15"
          >
            {term}
          </span>
        ))}

        <svg
          viewBox="0 0 20 20"
          fill="currentColor"
          className={`w-3 h-3 text-gray-400 transition-transform ${expanded ? "rotate-180" : ""}`}
          aria-hidden="true"
        >
          <path fillRule="evenodd" d="M5.23 7.21a.75.75 0 011.06.02L10 11.168l3.71-3.938a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z" clipRule="evenodd" />
        </svg>
      </button>

      {expanded && (
        <div className="mt-1.5 p-2.5 rounded-lg bg-gray-50/80 dark:bg-zinc-800/50 border border-gray-200/60 dark:border-zinc-700/40 text-xs space-y-2 animate-fade-in">
          {basirah && (
            <div className="space-y-1">
              <div className="font-medium text-gray-700 dark:text-gray-300">Vision (Basirah)</div>
              <p className="text-gray-500 dark:text-gray-400">{basirah.description}</p>
              <div className="flex items-center gap-2">
                <span className="text-gray-400 w-16">Confidence</span>
                <div className="flex-1 h-1.5 rounded-full bg-gray-200 dark:bg-zinc-700 overflow-hidden">
                  <div className="h-full rounded-full bg-amber-500" style={{ width: `${(basirah.confidence * 100).toFixed(0)}%` }} />
                </div>
                <span className="font-mono text-gray-400 w-8 text-right">{(basirah.confidence * 100).toFixed(0)}%</span>
              </div>
              {basirah.extracted_text && (
                <div className="text-gray-500 dark:text-gray-400">
                  <span className="font-medium text-gray-700 dark:text-gray-300">Text: </span>
                  {basirah.extracted_text.substring(0, 200)}
                  {basirah.extracted_text.length > 200 && "..."}
                </div>
              )}
              {basirah.key_elements?.length > 0 && (
                <div className="flex flex-wrap gap-1">
                  {basirah.key_elements.map((el, i) => (
                    <span key={i} className="px-1.5 py-0.5 rounded bg-gray-100 dark:bg-zinc-700 text-gray-600 dark:text-gray-400 text-[10px]">
                      {el}
                    </span>
                  ))}
                </div>
              )}
            </div>
          )}
          {nutq && (
            <div className="space-y-1">
              <div className="font-medium text-gray-700 dark:text-gray-300">Voice (Nutq)</div>
              <p className="text-gray-500 dark:text-gray-400">{nutq.text}</p>
              <div className="text-gray-500 dark:text-gray-400">
                <span className="font-medium text-gray-700 dark:text-gray-300">Intent: </span>{nutq.intent}
                {" · "}
                <span className="font-medium text-gray-700 dark:text-gray-300">Lang: </span>{nutq.language}
              </div>
            </div>
          )}
          {perception.zahir && (
            <div className="text-gray-500 dark:text-gray-400">
              <span className="font-medium text-gray-700 dark:text-gray-300">Zahir: </span>{perception.zahir}
            </div>
          )}
          {perception.batin && (
            <div className="text-gray-500 dark:text-gray-400">
              <span className="font-medium text-gray-700 dark:text-gray-300">Batin: </span>{perception.batin}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

interface ChatMessageBubbleProps {
  msg: ChatMessageType;
  selectedAgent?: { name: string } | null;
}

export function ChatMessageBubble({
  msg,
  selectedAgent,
}: ChatMessageBubbleProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(msg.content).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  if (msg.role === "system") {
    return (
      <div className="chat-message-row">
        <div className="chat-message-container flex justify-center">
          <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-amber-50/80 dark:bg-amber-500/5 border border-amber-200/40 dark:border-amber-500/10 text-xs text-amber-700 dark:text-amber-300/80">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="w-3 h-3" aria-hidden="true">
              <path d="M7 9l3 3-3 3M13 15h4" />
              <rect x="3" y="4" width="18" height="16" rx="2" />
            </svg>
            <span>{msg.content}</span>
          </div>
        </div>
      </div>
    );
  }

  if (msg.role === "user") {
    return (
      <div className="chat-message-row">
        <div className="chat-message-container flex justify-end">
          <div className="max-w-[80%] lg:max-w-[70%]">
            <div className="px-4 py-3 rounded-2xl rounded-br-md text-sm leading-relaxed bg-blue-600 text-white shadow-sm">
              {msg.content}
            </div>
            <div className="text-[10px] text-gray-400 dark:text-gray-500 mt-1 text-right font-mono px-1">
              {msg.ts}
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Assistant message — full-width like ChatGPT/Claude
  return (
    <div className="chat-message-row group/msg">
      <div className="chat-message-container">
        <div className="flex gap-3.5">
          {/* Avatar */}
          <div className="w-7 h-7 rounded-full shrink-0 flex items-center justify-center mt-0.5 bg-gradient-to-br from-amber-400 to-amber-600 shadow-sm">
            <svg viewBox="0 0 20 20" fill="white" className="w-3.5 h-3.5">
              <path d="M10 1a.75.75 0 01.75.75v1.5a.75.75 0 01-1.5 0v-1.5A.75.75 0 0110 1zM10 7a3 3 0 100 6 3 3 0 000-6z" />
            </svg>
          </div>

          {/* Body */}
          <div className="min-w-0 flex-1 overflow-hidden">
            {/* Header */}
            <div className="flex items-center gap-2 mb-1">
              <span className="text-[13px] font-semibold text-gray-900 dark:text-gray-100">
                {msg.agent || selectedAgent?.name || "MIZAN"}
              </span>
              {msg.model && (
                <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-gray-100 dark:bg-zinc-800 text-gray-500 dark:text-gray-400">
                  {msg.model}
                </span>
              )}
            </div>

            {/* Content */}
            <div className="prose">
              <ChatMessageContent content={msg.content} />
            </div>

            {/* Cognitive bar */}
            {msg.cognitive && <CognitiveBar cognitive={msg.cognitive} />}

            {/* Perception card */}
            {msg.perception && <PerceptionCard perception={msg.perception} />}

            {/* Action buttons — hover reveal */}
            <div className="flex items-center gap-1 mt-2 opacity-0 group-hover/msg:opacity-100 transition-opacity duration-200">
              <button
                onClick={handleCopy}
                className="p-1.5 rounded-md text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-zinc-800 transition-colors"
                title="Copy"
              >
                {copied ? (
                  <svg viewBox="0 0 20 20" fill="currentColor" className="w-3.5 h-3.5 text-green-500">
                    <path fillRule="evenodd" d="M16.704 4.153a.75.75 0 01.143 1.052l-8 10.5a.75.75 0 01-1.127.075l-4.5-4.5a.75.75 0 011.06-1.06l3.894 3.893 7.48-9.817a.75.75 0 011.05-.143z" clipRule="evenodd" />
                  </svg>
                ) : (
                  <svg viewBox="0 0 20 20" fill="currentColor" className="w-3.5 h-3.5">
                    <path d="M7 3.5A1.5 1.5 0 018.5 2h3.879a1.5 1.5 0 011.06.44l3.122 3.12A1.5 1.5 0 0117 6.622V12.5a1.5 1.5 0 01-1.5 1.5h-1v-3.379a3 3 0 00-.879-2.121L10.5 5.379A3 3 0 008.379 4.5H7v-1z" />
                    <path d="M4.5 6A1.5 1.5 0 003 7.5v9A1.5 1.5 0 004.5 18h7a1.5 1.5 0 001.5-1.5v-5.879a1.5 1.5 0 00-.44-1.06L9.44 6.439A1.5 1.5 0 008.378 6H4.5z" />
                  </svg>
                )}
              </button>
              <span className="text-[10px] text-gray-400 dark:text-gray-500 font-mono ml-1">
                {msg.ts}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

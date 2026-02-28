import { useState, useMemo } from "react";
import type {
  ChatMessage as ChatMessageType,
  CognitiveMetadata,
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

interface ChatMessageBubbleProps {
  msg: ChatMessageType;
  selectedAgent?: { name: string } | null;
}

export function ChatMessageBubble({
  msg,
  selectedAgent,
}: ChatMessageBubbleProps) {
  return (
    <div
      className={`flex gap-4 ${
        msg.role === "user"
          ? "flex-row-reverse"
          : msg.role === "system"
            ? "justify-center"
            : ""
      } animate-fade-in`}
    >
      {msg.role === "system" ? (
        <div className="max-w-[85%] w-full">
          <div
            className="px-4 py-3 rounded-lg text-sm leading-relaxed italic
            bg-amber-50/60 dark:bg-amber-500/5 border border-amber-200/60 dark:border-amber-500/15
            text-amber-900 dark:text-amber-200/90"
            style={{
              fontFamily:
                "'SF Mono', 'Fira Code', 'Cascadia Code', 'Consolas', monospace",
            }}
          >
            <div className="flex items-center gap-2 mb-1.5 not-italic">
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.5"
                className="w-3.5 h-3.5 text-amber-500 dark:text-amber-400"
                aria-hidden="true"
              >
                <path d="M7 9l3 3-3 3M13 15h4" />
                <rect x="3" y="4" width="18" height="16" rx="2" />
              </svg>
              <span className="text-xs font-semibold uppercase tracking-wider text-amber-600 dark:text-amber-400">
                System
              </span>
            </div>
            <div className="whitespace-pre-wrap">{msg.content}</div>
          </div>
          <div className="text-xs text-amber-400 dark:text-amber-500/60 mt-1 px-1 font-mono text-center">
            {msg.ts}
          </div>
        </div>
      ) : (
        <>
          <div
            className={`w-8 h-8 rounded-full shrink-0 flex items-center justify-center text-xs font-medium ${
              msg.role === "user"
                ? "bg-blue-100 dark:bg-blue-500/15 text-blue-600 dark:text-blue-400 border border-blue-200 dark:border-blue-500/30"
                : "bg-gray-100 dark:bg-zinc-800 text-mizan-gold border border-gray-200 dark:border-zinc-700"
            }`}
          >
            {msg.role === "user"
              ? "You"
              : selectedAgent?.name?.[0] || msg.agent?.[0] || "AI"}
          </div>
          <div
            className={msg.role === "assistant" ? "max-w-[85%]" : "max-w-[75%]"}
          >
            {msg.role === "assistant" ? (
              <div className="prose px-5 py-3.5 rounded-2xl text-sm leading-relaxed bg-white/80 dark:bg-mizan-dark-surface/80 backdrop-blur-md border border-white/50 dark:border-white/5 text-gray-800 dark:text-gray-200 rounded-tl-sm shadow-sm transition-all hover:shadow-md">
                <ChatMessageContent content={msg.content} />
              </div>
            ) : (
              <div className="px-5 py-3.5 rounded-2xl text-sm leading-relaxed bg-gradient-to-br from-blue-500 to-blue-600 border border-blue-400/50 text-white rounded-tr-sm shadow-md">
                {msg.content}
              </div>
            )}
            {msg.role === "assistant" && msg.cognitive && (
              <CognitiveBar cognitive={msg.cognitive} />
            )}
            <div className="text-xs text-gray-400 dark:text-gray-500 mt-1 px-1 font-mono opacity-0 group-hover:opacity-100 transition-opacity">
              {msg.role === "assistant" ? msg.agent : "You"} &middot; {msg.ts}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

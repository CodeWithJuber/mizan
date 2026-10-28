import {
  useState,
  useMemo,
  useEffect,
  isValidElement,
  cloneElement,
  memo,
} from "react";
import type { ReactNode } from "react";
import type {
  ChatMessage as ChatMessageType,
  CognitiveMetadata,
  PerceptionResult,
} from "../types";
import { Markdown, type Components } from "./Markdown";
import {
  Check, Copy, GitCompareArrows, Pencil, RotateCcw, Scale, Volume2, VolumeX,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { addToast } from "./Toast";
import { convertCopyFormat, type CopyFormatId } from "../utils/copyFormat";
import { speakable } from "../utils/voice.ts";
import { resolveAgentName, type NamedAgent } from "../utils/agentDisplay";
import { HeldActions } from "./HeldActions";
import { ChatImages } from "./ChatImages";
import { SourcesAndChecks } from "../features/chat/SourcesAndChecks";
import { RunTimeline } from "../features/chat/RunTimeline";
import type { ThinkingTrace } from "../types/ruh";
// MORPH-FEAT: Arabic word tap-to-explore
import { useMorphology } from "../hooks/useMorphology";
import { VerifiedBadge } from "./ruh/VerifiedBadge";
import type { AnalyzeWordResponse } from "../types/morphology";

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


// ===== MORPH-FEAT: Arabic word tap-to-explore (start) =====
// Splits text into Arabic / non-Arabic runs. Matches the contract regex
// /[\u0600-\u06FF]+/g. The non-global TEST_RE avoids lastIndex state bugs.
const ARABIC_RUN_RE = /([\u0600-\u06FF]+)/g;
const ARABIC_TEST_RE = /^[\u0600-\u06FF]+$/;

function ArabicWord({
  word,
  onExplore,
}: {
  word: string;
  onExplore?: (word: string) => void;
}) {
  const [open, setOpen] = useState(false);
  return (
    <span className="relative inline-block">
      <button
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-label={`Explore Arabic word ${word}`}
        className="underline decoration-dotted decoration-mizan-gold/60 underline-offset-2 cursor-pointer focus-ring rounded-sm"
      >
        {word}
      </button>
      {open && (
        <WordTapPopover
          word={word}
          onExplore={onExplore}
          onClose={() => setOpen(false)}
        />
      )}
    </span>
  );
}

function WordTapPopover({
  word,
  onExplore,
  onClose,
}: {
  word: string;
  onExplore?: (word: string) => void;
  onClose: () => void;
}) {
  const morph = useMorphology();
  const [data, setData] = useState<AnalyzeWordResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    morph
      .analyzeWord(word)
      .then((res) => {
        if (!cancelled) setData(res);
      })
      .catch((err) => {
        if (!cancelled)
          setError(err instanceof Error ? err.message : "Lookup failed");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [word, morph]);

  return (
    <span
      className="absolute z-30 bottom-full left-1/2 -translate-x-1/2 mb-2 w-64 max-w-[78vw] p-3 rounded-xl bg-white dark:bg-zinc-900 border border-gray-200 dark:border-zinc-700 shadow-xl text-left animate-fade-in"
      role="dialog"
      aria-label={`Preview of ${word}`}
    >
      <button
        onClick={onClose}
        aria-label="Close preview"
        className="absolute top-1 right-1 w-8 h-8 flex items-center justify-center rounded-full text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 cursor-pointer focus-ring"
      >
        <svg
          viewBox="0 0 20 20"
          fill="currentColor"
          className="w-4 h-4"
          aria-hidden="true"
        >
          <path d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z" />
        </svg>
      </button>
      {loading && (
        <span className="text-xs text-gray-400">
          Looking up &ldquo;{word}&rdquo;&hellip;
        </span>
      )}
      {error && !loading && (
        <span className="text-xs text-red-600 dark:text-red-400">{error}</span>
      )}
      {data && !loading && (
        <span className="block">
          <span
            dir="rtl"
            lang="ar"
            className="block text-lg font-bold text-gray-900 dark:text-gray-100 pr-6"
          >
            {data.word}
          </span>
          <span className="mt-1 flex items-center gap-2">
            <span
              dir="rtl"
              lang="ar"
              className="text-base font-semibold text-mizan-gold-text dark:text-mizan-gold"
            >
              {data.root || "\u2014"}
            </span>
            <VerifiedBadge level={data.provenance} source={data.source} />
          </span>
          {onExplore && (
            <button
              onClick={() => onExplore(word)}
              className="mt-2 w-full min-h-[44px] px-3 text-sm font-medium rounded-lg bg-mizan-gold/15 text-mizan-gold-text dark:text-mizan-gold hover:bg-mizan-gold/25 transition-colors cursor-pointer focus-ring"
            >
              Explore root
            </button>
          )}
        </span>
      )}
    </span>
  );
}

/**
 * Recursively walks rendered Markdown children and wraps Arabic runs in
 * <ArabicWord> tap targets. Skips <code> elements (code stays untappable).
 */
function linkifyArabic(
  node: ReactNode,
  onExplore: ((word: string) => void) | undefined,
  keyPrefix: string,
): ReactNode {
  if (typeof node === "string") {
    const parts = node.split(ARABIC_RUN_RE);
    if (parts.length === 1) return node;
    return parts.map((part, i) =>
      ARABIC_TEST_RE.test(part) ? (
        <ArabicWord
          key={`${keyPrefix}-${i}`}
          word={part}
          onExplore={onExplore}
        />
      ) : (
        <span key={`${keyPrefix}-${i}`}>{part}</span>
      ),
    );
  }
  if (Array.isArray(node)) {
    return node.map((child, i) =>
      linkifyArabic(child, onExplore, `${keyPrefix}.${i}`),
    );
  }
  if (isValidElement<{ children?: ReactNode }>(node)) {
    if (node.type === "code") return node; // never linkify code
    return cloneElement(node, {
      key: node.key ?? keyPrefix,
      children: linkifyArabic(node.props.children, onExplore, `${keyPrefix}.c`),
    });
  }
  return node;
}
// ===== MORPH-FEAT: Arabic word tap-to-explore (end) =====

export function ChatMessageContent({
  content,
  onExploreWord,
  streaming = false,
}: {
  content: string;
  onExploreWord?: (word: string) => void;
  streaming?: boolean;
}) {
  const [expandedTools, setExpandedTools] = useState<Set<number>>(new Set());
  const blocks = useMemo(() => parseChatContent(content), [content]);
  // MORPH-FEAT: element overrides that linkify Arabic words in
  // paragraphs. Memoized so the memoized <Markdown> keeps its memo.
  const arabicComponents = useMemo(() => {
    const p = ({ children }: { children?: ReactNode }) => (
      <p dir="auto">{linkifyArabic(children, onExploreWord, "p")}</p>
    );
    return { p } as unknown as Partial<Components>;
  }, [onExploreWord]);

  const toggleTool = (idx: number) => {
    setExpandedTools((prev) => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx);
      else next.add(idx);
      return next;
    });
  };

  if (blocks.length === 1 && blocks[0].type === "text") {
    return (
      <Markdown content={blocks[0].content} components={arabicComponents} streaming={streaming} />
    );
  }

  return (
    <div className="space-y-2">
      {blocks.map((block, idx) => {
        if (block.type === "text") {
          return (
            <Markdown
              key={idx}
              content={block.content}
              components={arabicComponents}
              streaming={streaming}
            />
          );
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

const PERCEPTION_CATEGORY_COLORS: Record<string, string> = {
  text: "bg-blue-100 dark:bg-blue-500/15 text-blue-700 dark:text-blue-400",
  diagram:
    "bg-purple-100 dark:bg-purple-500/15 text-purple-700 dark:text-purple-400",
  screenshot:
    "bg-cyan-100 dark:bg-cyan-500/15 text-cyan-700 dark:text-cyan-400",
  photo:
    "bg-emerald-100 dark:bg-emerald-500/15 text-emerald-700 dark:text-emerald-400",
  document:
    "bg-amber-100 dark:bg-amber-500/15 text-amber-700 dark:text-amber-400",
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
            <svg
              viewBox="0 0 20 20"
              fill="currentColor"
              className="w-3 h-3"
              aria-hidden="true"
            >
              <path d="M10 12.5a2.5 2.5 0 100-5 2.5 2.5 0 000 5z" />
              <path
                fillRule="evenodd"
                d="M.664 10.59a1.651 1.651 0 010-1.186A10.004 10.004 0 0110 3c4.257 0 7.893 2.66 9.336 6.41.147.381.146.804 0 1.186A10.004 10.004 0 0110 17c-4.257 0-7.893-2.66-9.336-6.41zM14 10a4 4 0 11-8 0 4 4 0 018 0z"
                clipRule="evenodd"
              />
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
            <svg
              viewBox="0 0 20 20"
              fill="currentColor"
              className="w-3 h-3"
              aria-hidden="true"
            >
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
          <path
            fillRule="evenodd"
            d="M5.23 7.21a.75.75 0 011.06.02L10 11.168l3.71-3.938a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z"
            clipRule="evenodd"
          />
        </svg>
      </button>

      {expanded && (
        <div className="mt-1.5 p-2.5 rounded-lg bg-gray-50/80 dark:bg-zinc-800/50 border border-gray-200/60 dark:border-zinc-700/40 text-xs space-y-2 animate-fade-in">
          {basirah && (
            <div className="space-y-1">
              <div className="font-medium text-gray-700 dark:text-gray-300">
                Vision (Basirah)
              </div>
              <p className="text-gray-500 dark:text-gray-400">
                {basirah.description}
              </p>
              <div className="flex items-center gap-2">
                <span className="text-gray-400 w-16">Confidence</span>
                <div className="flex-1 h-1.5 rounded-full bg-gray-200 dark:bg-zinc-700 overflow-hidden">
                  <div
                    className="h-full rounded-full bg-amber-500"
                    style={{
                      width: `${(basirah.confidence * 100).toFixed(0)}%`,
                    }}
                  />
                </div>
                <span className="font-mono text-gray-400 w-8 text-right">
                  {(basirah.confidence * 100).toFixed(0)}%
                </span>
              </div>
              {basirah.extracted_text && (
                <div className="text-gray-500 dark:text-gray-400">
                  <span className="font-medium text-gray-700 dark:text-gray-300">
                    Text:{" "}
                  </span>
                  {basirah.extracted_text.substring(0, 200)}
                  {basirah.extracted_text.length > 200 && "..."}
                </div>
              )}
              {basirah.key_elements?.length > 0 && (
                <div className="flex flex-wrap gap-1">
                  {basirah.key_elements.map((el, i) => (
                    <span
                      key={i}
                      className="px-1.5 py-0.5 rounded bg-gray-100 dark:bg-zinc-700 text-gray-600 dark:text-gray-400 text-[10px]"
                    >
                      {el}
                    </span>
                  ))}
                </div>
              )}
            </div>
          )}
          {nutq && (
            <div className="space-y-1">
              <div className="font-medium text-gray-700 dark:text-gray-300">
                Voice (Nutq)
              </div>
              <p className="text-gray-500 dark:text-gray-400">{nutq.text}</p>
              <div className="text-gray-500 dark:text-gray-400">
                <span className="font-medium text-gray-700 dark:text-gray-300">
                  Intent:{" "}
                </span>
                {nutq.intent}
                {" · "}
                <span className="font-medium text-gray-700 dark:text-gray-300">
                  Lang:{" "}
                </span>
                {nutq.language}
              </div>
            </div>
          )}
          {perception.zahir && (
            <div className="text-gray-500 dark:text-gray-400">
              <span className="font-medium text-gray-700 dark:text-gray-300">
                Zahir:{" "}
              </span>
              {perception.zahir}
            </div>
          )}
          {perception.batin && (
            <div className="text-gray-500 dark:text-gray-400">
              <span className="font-medium text-gray-700 dark:text-gray-300">
                Batin:{" "}
              </span>
              {perception.batin}
            </div>
          )}
        </div>
      )}
    </div>
  );
}


const COPY_FORMATS: { id: CopyFormatId; label: string; hint: string }[] = [
  { id: "markdown", label: "Copy", hint: "as written" },
  { id: "plain", label: "Copy plain text", hint: "no formatting" },
  { id: "whatsapp", label: "Copy for WhatsApp", hint: "*bold* style" },
];

/** An icon button with a tooltip and an accessible name. */
export function IconAction({
  label,
  onClick,
  children,
  pressed,
}: {
  label: string;
  onClick: () => void;
  children: ReactNode;
  pressed?: boolean;
}) {
  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label={label}
            aria-pressed={pressed}
            onClick={onClick}
            className="text-muted-foreground hover:text-foreground"
          />
        }
      >
        {children}
      </TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  );
}

function copyText(text: string, label: string, done: () => void) {
  navigator.clipboard.writeText(text).then(
    () => {
      done();
      addToast({ type: "success", title: "Copied", description: label === "Copy" ? undefined : label });
    },
    () => addToast({ type: "error", title: "Copy failed — clipboard unavailable" }),
  );
}

function CopyMenu({ content }: { content: string }) {
  const [copied, setCopied] = useState(false);
  const done = () => {
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };
  return (
    <DropdownMenu>
      <Tooltip>
        <TooltipTrigger
          render={
            <DropdownMenuTrigger
              render={
                <Button variant="ghost" size="icon-sm" aria-label="Copy options" className="text-muted-foreground hover:text-foreground" />
              }
            />
          }
        >
          {copied ? <Check className="text-success" /> : <Copy />}
        </TooltipTrigger>
        <TooltipContent>Copy</TooltipContent>
      </Tooltip>
      <DropdownMenuContent className="w-52" side="top">
        {COPY_FORMATS.map((format) => (
          <DropdownMenuItem key={format.id} onClick={() => copyText(convertCopyFormat(content, format.id), format.label, done)}>
            <span className="flex-1">{format.label}</span>
            <span className="text-xs text-muted-foreground">{format.hint}</span>
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function ReadAloud({ content }: { content: string }) {
  const [speaking, setSpeaking] = useState(false);
  if (typeof window === "undefined" || !("speechSynthesis" in window) || !content.trim()) return null;
  const toggle = () => {
    const voice = window.speechSynthesis;
    voice.cancel();
    if (speaking) {
      setSpeaking(false);
      return;
    }
    const utterance = new SpeechSynthesisUtterance(convertCopyFormat(speakable(content), "plain"));
    utterance.onend = () => setSpeaking(false);
    utterance.onerror = () => setSpeaking(false);
    voice.speak(utterance);
    setSpeaking(true);
  };
  return (
    <IconAction
      label={speaking ? "Stop reading aloud" : "Read aloud (Quran text is not read by the voice)"}
      onClick={toggle}
      pressed={speaking}
    >
      {speaking ? <VolumeX className="text-brand" /> : <Volume2 />}
    </IconAction>
  );
}

export function MizanMark({ className = "" }: { className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={`inline-flex size-7 shrink-0 items-center justify-center rounded-full bg-primary/15 text-brand ${className}`}
    >
      <Scale className="size-4" />
    </span>
  );
}

interface ChatMessageBubbleProps {
  msg: ChatMessageType;
  /** The chatting agent's name, used when a message does not name its own. */
  agentName?: string;
  // Loaded agents list — used to resolve a raw agent_id into a display name.
  agents?: NamedAgent[];
  // Forwarded to ChatMessageContent; opens the root explorer.
  onExploreWord?: (word: string) => void;
  // Optional in-message CTA button (e.g. "Open providers").
  onNavigateTab?: (tab: string) => void;
  /** Debug mode: raw metadata and heuristic diagnostics under answers. */
  debug?: boolean;
  /** Ask again (the last answer only). */
  onRetry?: () => void;
  /** Put a sent message back in the message box. */
  onEdit?: (text: string) => void;
  /** Debug mode: compare this message with the base model alone. */
  onCompare?: (text: string) => void;
  /** The thinking steps of this answer, shown with its tools in the run summary. */
  trace?: ThinkingTrace;
}

export const ChatMessageBubble = memo(function ChatMessageBubble({
  msg,
  agentName,
  agents,
  onExploreWord,
  onNavigateTab,
  debug = false,
  onRetry,
  onEdit,
  onCompare,
  trace,
}: ChatMessageBubbleProps) {
  const cta = (msg as ChatMessageType & { cta?: { label: string; tab: string } }).cta;

  if (msg.role === "system") {
    return (
      <div className="chat-message-row">
        <div className="chat-message-container flex justify-center">
          <div className="inline-flex max-w-full items-center gap-2 rounded-full border bg-muted/60 px-4 py-1.5 text-xs text-muted-foreground">
            <span className="break-words">{msg.content}</span>
          </div>
        </div>
      </div>
    );
  }

  if (msg.role === "user") {
    return (
      <div className="chat-message-row group/msg">
        <div className="chat-message-container flex flex-col items-end">
          <div
            dir="auto"
            className="max-w-[85%] whitespace-pre-wrap break-words rounded-2xl rounded-br-md bg-muted px-4 py-2.5 text-[15px] leading-relaxed text-foreground"
          >
            {msg.content}
          </div>
          <ChatImages images={msg.images} />
          {msg.notStarted && (
            <p className="mt-1 text-xs text-amber-800 dark:text-warning">
              Not started — no model execution was started for this message.
            </p>
          )}
          <div className="mt-1 flex items-center gap-0.5 opacity-100 transition-opacity md:opacity-0 md:group-hover/msg:opacity-100 md:focus-within:opacity-100">
            <span className="mr-1 font-mono text-[11px] text-muted-foreground">{msg.ts}</span>
            <CopyMenu content={msg.content} />
            {onEdit && (
              <IconAction label="Edit and send again" onClick={() => onEdit(msg.content)}>
                <Pencil />
              </IconAction>
            )}
            {onCompare && (
              <IconAction label="Compare with the base model" onClick={() => onCompare(msg.content)}>
                <GitCompareArrows />
              </IconAction>
            )}
          </div>
        </div>
      </div>
    );
  }

  // Assistant message — full width, no bubble.
  return (
    <div className="chat-message-row group/msg">
      <div className="chat-message-container">
        <div className="flex gap-3">
          <MizanMark className="mt-0.5" />
          <div className="min-w-0 flex-1">
            <div className="mb-1 flex h-7 items-center gap-2">
              <span className="text-sm font-medium text-foreground">
                {resolveAgentName(msg.agent, agents, agentName)}
              </span>
            </div>
            <RunTimeline activity={msg.activity} trace={trace} />
            {msg.content.trim() && (
              <ChatMessageContent content={msg.content} onExploreWord={onExploreWord} />
            )}
            {msg.error && (
              <p role="alert" className="mt-2 break-words rounded-lg border border-destructive/30 bg-destructive/8 px-3 py-2 text-sm text-destructive">
                {msg.error.message}
              </p>
            )}
            {msg.perception && <PerceptionCard perception={msg.perception} />}
            {/* Pictures MIZAN made for this answer (Shahid's screenshot) */}
            <ChatImages images={msg.images} align="start" />
            {msg.stopped && (
              <p role="status" className="mt-2 text-xs text-muted-foreground">
                Stopped · {msg.content.length ? "received text kept" : "no answer received"}
              </p>
            )}
            {msg.interrupted && (
              <p role="status" className="mt-2 text-xs text-muted-foreground">
                Interrupted · {msg.content.trim() ? "partial response saved" : "no answer received"}
              </p>
            )}
            {msg.held && <HeldActions items={msg.held} />}
            <SourcesAndChecks meta={msg.meta} cognitive={msg.cognitive} debug={debug} />
            {cta && (
              <Button className="mt-2" onClick={() => onNavigateTab?.(cta.tab)}>
                {cta.label}
              </Button>
            )}
            <div className="mt-1 flex items-center gap-0.5 opacity-100 transition-opacity md:opacity-0 md:group-hover/msg:opacity-100 md:focus-within:opacity-100">
              {msg.content.trim() && <CopyMenu content={msg.content} />}
              <ReadAloud content={msg.content} />
              {onRetry && (
                <IconAction label="Ask again" onClick={onRetry}>
                  <RotateCcw />
                </IconAction>
              )}
              <span className="ml-1 font-mono text-[11px] text-muted-foreground">{msg.ts}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
});

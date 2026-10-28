/**
 * Everything MIZAN knows about where an answer came from, in one quiet row
 * under it: the Isnad grades of its claims, what the Truth Gate (Sidq)
 * corrected, which sources were asked (Ahl al-Dhikr), what was recalled from
 * other chats, any injected instruction Amanah ignored, and the model's
 * usage. One click opens the details; nothing is hidden, only folded.
 */
import { useState } from "react";
import { BookOpen, ChevronRight, History, Scale, ShieldAlert } from "lucide-react";
import { cn } from "@/lib/utils";
import type { CognitiveMetadata, MessageUsageMeta } from "../../types";
import { amanahHeadline, isAmanah, kindLabels } from "../../utils/amanah.ts";
import { GRADES, headline as isnadHeadline, isIsnad, segments } from "../../utils/isnad.ts";
import { isSidq, sidqHeadline, sidqLines } from "../../utils/sidq.ts";
import { ahlHeadline, ahlLines, isAhl } from "../../utils/ahl.ts";
import { recalledHeadline, recalledLines } from "../../utils/recalled.ts";
import { cognitiveMetrics, fmtCost, fmtTokens, usageMetrics } from "../../utils/responseMetrics.ts";
import IsnadView from "../../components/IsnadView";

interface Props {
  meta?: MessageUsageMeta;
  cognitive?: CognitiveMetadata;
  /** Debug mode shows the raw metadata and the heuristic diagnostics too. */
  debug?: boolean;
}

function Chip({ children, tone }: { children: React.ReactNode; tone?: "warning" }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 whitespace-nowrap",
        tone === "warning" ? "text-amber-800 dark:text-warning" : "text-muted-foreground",
      )}
    >
      {children}
    </span>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-1">
      <h4 className="text-xs font-medium text-foreground">{title}</h4>
      {children}
    </section>
  );
}

export function SourcesAndChecks({ meta, cognitive, debug = false }: Props) {
  const [open, setOpen] = useState(false);
  const recalled = recalledLines(meta?.recalled);
  const isnad = isIsnad(meta?.isnad) && meta.isnad.claims ? meta.isnad : null;
  const sidq = isSidq(meta?.sidq) ? meta.sidq : null;
  const ahl = isAhl(meta?.ahl) ? meta.ahl : null;
  const amanah = isAmanah(meta?.amanah) ? meta.amanah : null;
  const usage = usageMetrics(meta);
  const diagnostics = debug && cognitive ? cognitiveMetrics(cognitive) : null;
  const tokens = [
    meta?.input_tokens ? `${fmtTokens(meta.input_tokens)} in` : "",
    meta?.output_tokens ? `${fmtTokens(meta.output_tokens)} out` : "",
  ].filter(Boolean).join(" / ");
  const cost = meta?.cost_usd != null && Number.isFinite(meta.cost_usd) && meta.cost_usd >= 0
    ? fmtCost(meta.cost_usd, meta.cost_estimated) : "";

  if (!isnad && !sidq && !ahl && !amanah && !recalled.length && !usage.parts.length && !diagnostics) return null;

  return (
    <div className="mt-2 text-xs">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className="group/sources -ml-1 flex max-w-full flex-wrap items-center gap-x-3 gap-y-1 rounded-md px-1 py-0.5 text-left hover:bg-muted/60"
        title={open ? "Hide sources and checks" : "Show sources and checks"}
      >
        {isnad && (
          <Chip>
            <span className="inline-flex h-1.5 w-12 overflow-hidden rounded-full bg-muted" aria-hidden>
              {segments(isnad).map((bar, index) => (
                <span
                  key={bar.grade}
                  style={{ width: `${bar.share * 100}%`, background: GRADES[bar.grade].color, marginLeft: index ? 1 : 0 }}
                />
              ))}
            </span>
            <span>{isnadHeadline(isnad)}</span>
          </Chip>
        )}
        {sidq && (
          <Chip>
            <Scale className="size-3" />
            {sidqHeadline(sidq).replace(/^Truth Gate: /, "")}
          </Chip>
        )}
        {ahl && (
          <Chip>
            <BookOpen className="size-3" />
            {ahlHeadline(ahl).replace(/^Sources asked: /, "sources: ").replace(/ — .*$/, "")}
          </Chip>
        )}
        {recalled.length > 0 && (
          <Chip>
            <History className="size-3" />
            {recalled.length} recalled
          </Chip>
        )}
        {amanah && (
          <Chip tone="warning">
            <ShieldAlert className="size-3" />
            {amanah.ignored === 1 ? "1 injected instruction ignored" : `${amanah.ignored} injected instructions ignored`}
          </Chip>
        )}
        {(meta?.model || tokens || cost) && (
          <Chip>
            <span className="font-mono">{[meta?.model, tokens, cost].filter(Boolean).join(" · ")}</span>
          </Chip>
        )}
        {!isnad && !sidq && !ahl && !amanah && !recalled.length && !meta?.model && !tokens && !cost && (
          <Chip>Details</Chip>
        )}
        <ChevronRight className={cn("size-3 text-muted-foreground transition-transform", open && "rotate-90")} />
      </button>

      {open && (
        <div className="mt-2 space-y-3 rounded-lg border bg-card p-3 leading-relaxed text-muted-foreground">
          {isnad && (
            <Section title="Isnad — what supports each claim">
              <IsnadView isnad={isnad} compact />
            </Section>
          )}
          {sidq && (
            <Section title={sidqHeadline(sidq)}>
              <p>
                Before showing this answer MIZAN checked what it could prove: arithmetic, quoted Quran and hadith text,
                actions claimed without a receipt, and links.
              </p>
              <ul className="space-y-0.5 font-mono text-[11px]">
                {sidqLines(sidq).map((line) => <li key={line} className="break-words">{line}</li>)}
              </ul>
            </Section>
          )}
          {ahl && (
            <Section title={ahlHeadline(ahl)}>
              <p>
                This answer was in the language model's own words, so MIZAN asked its sources about each claim: what it
                settled before, then Wikipedia and a web search. What a source settled is kept for next time.
              </p>
              <ul className="space-y-0.5 font-mono text-[11px]">
                {ahlLines(ahl).map((line) => (
                  <li key={line.text} className="break-words">
                    {line.url ? (
                      <a href={line.url} target="_blank" rel="noreferrer noopener" className="underline">{line.text}</a>
                    ) : line.text}
                  </li>
                ))}
              </ul>
            </Section>
          )}
          {recalled.length > 0 && (
            <Section title={recalledHeadline(recalled)}>
              <p>
                The model was shown these words you wrote in other chats, as your statements, not as facts. Turn this
                off with the chat preference cross_chat_recall: off, or delete a chat to forget it.
              </p>
              <ul className="space-y-0.5 text-[11px]">
                {recalled.map((line) => (
                  <li key={`${line.session_id}-${line.created_at}`} className="break-words">
                    <span className="font-mono">{line.created_at.slice(0, 10)}</span> “{line.content}”
                  </li>
                ))}
              </ul>
            </Section>
          )}
          {amanah && (
            <Section title={amanahHeadline(amanah)}>
              <p>
                The text {kindLabels(amanah).join("; ")}. MIZAN removed it before the model read anything, and it chose
                no action{amanah.hidden ? "; some of it was hidden from view" : ""}.
              </p>
              {amanah.examples.length > 0 && (
                <ul className="space-y-0.5 font-mono text-[11px]">
                  {amanah.examples.map((example) => <li key={example} className="break-words">“{example}”</li>)}
                </ul>
              )}
            </Section>
          )}
          {usage.parts.length > 0 && (
            <Section title="Model and usage">
              <p className="font-mono text-[11px]">{usage.parts.join(" · ")}</p>
              {usage.explanations.map((text) => <p key={text}>{text}</p>)}
            </Section>
          )}
          {diagnostics && (diagnostics.pills.length > 0 || diagnostics.details.length > 0) && (
            <Section title="Heuristic diagnostics (debug)">
              <p>Internal estimates and counters. They do not measure answer accuracy.</p>
              <dl className="space-y-1">
                {[...new Map([...diagnostics.pills, ...diagnostics.details].map((m) => [m.key, m])).values()].map((metric) => (
                  <div key={metric.key}>
                    <dt className="inline font-medium text-foreground">{metric.label}:</dt>{" "}
                    <dd className="inline">{metric.value}</dd>
                  </div>
                ))}
              </dl>
            </Section>
          )}
          {debug && meta && (
            <Section title="Raw metadata (debug)">
              <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-all rounded-md border bg-muted/40 p-2 font-mono text-[10px]">
                {JSON.stringify(meta, null, 2)}
              </pre>
            </Section>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * What MIZAN learned from its own verified work: which agent it gives each
 * kind of work to, the wording it now understands without the model, the
 * programs and repair lessons it keeps, and (for admins) the instruction
 * versions and models it chose for code work.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import type { ApiClient } from "../types";
import { useToast } from "./Toast";
import { confirmDialog } from "./ui/confirm";
import { NOTE_LABELS, ago, mergeNotes, type LearningNote } from "../utils/sijill.ts";
import {
  learnedCount,
  percent,
  shareText,
  topFamilies,
  workRows,
  WORK_LABELS,
  type RoutingRow,
  type TeacherFamily,
  type WorkRow,
} from "../utils/tadbirLearning.ts";

interface Wording {
  examples: number;
  by_intent: Record<string, number>;
}

interface Programs {
  programs: number;
  reuses: number;
  items: { request: string; language: string; runs: number; reliability: number }[];
}

interface Answers {
  answers: number;
  reuses: number;
  items: {
    request: string;
    language: string;
    kept: string;
    reused: number;
    sources: string[];
    next_check_days: number;
  }[];
}

interface Lessons {
  lessons: number;
  items: { kind: string; signature: string; usefulness: number }[];
}

/** Sullam: whether sharing the work among agents beats a vote at the same budget. */
interface LadderRow {
  intent: string;
  default: string;
  verdict: string;
  /** 0-3: beats one answer, a vote at the same budget, pass@n at the same budget. */
  level: number;
  questions: number;
  n_b?: number | null;
  y?: number | null;
  tests?: Record<string, { reference: number | null; cleared: boolean; indeterminate: boolean }>;
}

/** Islah, Itqan and Athar: lessons from corrections, earned skills, replayed runs. */
interface Corrections {
  lessons: number;
  active: number;
  candidate: number;
  quarantined: number;
  items: { id: string; status: string; corrected: string; confidence: number }[];
}

interface EarnedSkills {
  counting: number;
  proposed: { name: string; terms: string[] }[];
  removed: number;
  threshold: number;
}

interface Replay {
  enabled: boolean;
  thresholds: Record<string, number>;
  families: { tools: string[]; requests: number; agreed: number; lower_bound: number; replayed: number }[];
}

const share = (value?: number | null) => (typeof value === "number" ? percent(value) : "—");

function ShapesCard({ ladder, corrections, earned, replay }: {
  ladder: LadderRow[];
  corrections: Corrections | null;
  earned: EarnedSkills | null;
  replay: Replay | null;
}) {
  const measured = ladder.filter((row) => row.questions > 0);
  return (
    <div className="card">
      <div className="text-xxs font-semibold text-muted-foreground/80 uppercase tracking-widest mb-1">
        Corrections, earned skills and replays · إصلاح · إتقان · أثر
      </div>
      <p className="text-xs text-muted-foreground mb-3">
        MIZAN learns a lesson only when two independent kinds of correction agree (your correction, an undo, a
        check that failed before it passed), proposes a skill only from work it verified three times (it waits
        for your trust in Skills), and repeats a verified run with no model call only once the evidence clears
        its bar.
      </p>
      <ul className="space-y-1 text-sm mb-3">
        <li className="text-foreground">
          Lessons: {corrections ? `${corrections.active} in use · ${corrections.candidate} waiting for a second time · ${corrections.quarantined} set aside` : "—"}
        </li>
        <li className="text-foreground">
          Earned skills: {earned ? `${earned.proposed.length} proposed · ${earned.counting} kinds of work being counted (needs ${earned.threshold} verified runs)` : "—"}
        </li>
        <li className="text-foreground">
          Replays: {replay ? `${replay.families.reduce((sum, family) => sum + family.replayed, 0)} answered without the model · ${replay.families.length} forms learned${replay.enabled ? "" : " (turned off)"}` : "—"}
        </li>
      </ul>
      {corrections && corrections.items.some((item) => item.status === "active") && (
        <ul className="divide-y divide-border mb-3">
          {corrections.items.filter((item) => item.status === "active").map((item) => (
            <li key={item.id} className="py-1.5 text-xs text-muted-foreground">{item.corrected}</li>
          ))}
        </ul>
      )}
      <div className="text-xs font-medium text-foreground mb-1">Sharing the work (Majlis) against a vote at the same budget</div>
      {measured.length > 0 ? (
        <ul className="divide-y divide-border" data-testid="ladder">
          {measured.map((row) => (
            <li key={row.intent} className="py-1.5 flex flex-wrap items-center gap-x-3 text-xs">
              <span className="min-w-0 flex-1 font-mono text-foreground">{row.intent}</span>
              <span className="text-muted-foreground">{row.verdict}</span>
              <span className="font-mono text-muted-foreground">
                level {row.level} of 3 · {row.questions} questions · n_B {row.n_b ?? "—"} · right {share(row.y)} vs vote {share(row.tests?.["2"]?.reference)}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-xs text-muted-foreground">
          Not measured yet: Majlis stays the default for every kind of work. The AGI test measures it (more repeats
          let it judge the vote). This is reported only and never changes a run.
        </p>
      )}
    </div>
  );
}

interface HarnessRow {
  task: string;
  incumbent: string;
  incumbent_success: number;
  incumbent_trials: number;
  failures_since_renewal: number;
  challenger?: {
    id: string;
    success: number;
    trials: number;
    p_better: number;
    /** Paired e-values (Tajdid): promoted when "better" reaches the threshold. */
    evidence?: { wins: number; losses: number; ties: number; better: number; worse: number; threshold: number };
  };
}

interface Harness {
  evolution: boolean;
  instructions: HarnessRow[];
  models: string[];
  routing: { task: string; model: string; success: number; evidence: number }[];
}

interface TeacherCalls {
  days: number;
  requests: number;
  zero_call: number;
  zero_call_share: number | null;
  interval: [number, number] | null;
  by_family: TeacherFamily[];
  lisan_tasks: Record<string, number>;
}

/** How often MIZAN answered with no hosted-model call (docs/teacher-calls.md). */
function OnItsOwn({ api }: { api: ApiClient }) {
  const [data, setData] = useState<TeacherCalls | null>(null);

  useEffect(() => {
    api
      .get("/tadbir/teacher-calls?days=30")
      .then((value) => setData(value as unknown as TeacherCalls))
      .catch(() => setData(null));
  }, [api]);

  if (!data) return null;
  const families = topFamilies(data.by_family ?? []);
  const tasks = Object.entries(data.lisan_tasks ?? {}).slice(0, 6);
  return (
    <div className="card">
      <div className="text-xxs font-semibold text-muted-foreground/80 uppercase tracking-widest mb-1">
        On its own · بنفسه
      </div>
      <p className="text-xs text-muted-foreground mb-2">
        Your answers in the last {data.days} days that needed no hosted-model call, with a 95% interval. The goal is
        for this to rise as MIZAN keeps what it verified.
      </p>
      <div className="text-2xl font-semibold text-brand tabular-nums">
        {shareText(data.zero_call_share, data.interval)}
      </div>
      <div className="text-xs text-muted-foreground mb-3">
        {data.zero_call} of {data.requests} answers
      </div>
      {families.length > 0 && (
        <ul className="divide-y divide-border text-sm">
          {families.map((row) => (
            <li key={`${row.family}-${row.language}`} className="py-1.5 flex items-center gap-2">
              <span className="min-w-0 flex-1 truncate">
                {row.label} <span className="text-muted-foreground">· {row.language}</span>
              </span>
              <span className="shrink-0 text-xs text-muted-foreground tabular-nums">{row.requests}</span>
              <span className="shrink-0 w-28 text-right text-xs tabular-nums">
                {shareText(row.zero_call_share, row.interval)}
              </span>
            </li>
          ))}
        </ul>
      )}
      {tasks.length > 0 && (
        <p className="text-xs text-muted-foreground mt-3">
          Still asked of the model: {tasks.map(([task, count]) => `${task} ${count}`).join(", ")}
        </p>
      )}
    </div>
  );
}

/** What MIZAN learns from your work, as it happens (polled every few seconds). */
function LiveLearning({ api }: { api: ApiClient }) {
  const [notes, setNotes] = useState<LearningNote[]>([]);
  const last = useRef(0);
  const [, setTick] = useState(0);

  useEffect(() => {
    let stopped = false;
    const poll = async () => {
      try {
        const data = (await api.get(`/tadbir/learning/live?after=${last.current}`)) as unknown as {
          notes: LearningNote[];
          last: number;
        };
        if (stopped) return;
        last.current = data.last ?? last.current;
        if (data.notes?.length) setNotes((previous) => mergeNotes(previous, data.notes));
        setTick((tick) => tick + 1); // refresh the "ago" times
      } catch {
        // the feed is best effort; the next poll tries again
      }
    };
    poll();
    const timer = window.setInterval(poll, 4000);
    return () => {
      stopped = true;
      window.clearInterval(timer);
    };
  }, [api]);

  return (
    <div className="card">
      <div className="flex items-center gap-2 mb-1">
        <span className="relative flex h-2 w-2" aria-hidden="true">
          <span className="absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-60 motion-safe:animate-ping" />
          <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
        </span>
        <div className="text-xxs font-semibold text-muted-foreground/80 uppercase tracking-widest">
          Learning now · سجل
        </div>
      </div>
      <p className="text-xs text-muted-foreground mb-2">
        Each step MIZAN learns from verified work, the moment it happens. No weights change: this is learning by
        evidence.
      </p>
      {notes.length === 0 ? (
        <div className="text-sm text-muted-foreground/80 text-center py-3">
          Nothing yet. Ask MIZAN to compute, run code, quote a source or play a game, and watch here.
        </div>
      ) : (
        <ul className="divide-y divide-gray-200/60 dark:divide-gray-700/60 max-h-72 overflow-y-auto">
          {notes.map((note) => (
            <li key={note.seq} className="py-1.5 flex items-start gap-2 text-sm">
              <span className="shrink-0 text-micro font-mono px-1.5 py-0.5 rounded bg-muted text-foreground/75">
                {NOTE_LABELS[note.kind] ?? note.kind}
              </span>
              <span className="min-w-0 flex-1 wrap-break-word text-foreground/90">{note.summary}</span>
              <span className="shrink-0 text-micro text-gray-400 tabular-nums">{ago(note.at)}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function TadbirLearning({ api }: { api: ApiClient }) {
  const { addToast } = useToast();
  const [rows, setRows] = useState<WorkRow[]>([]);
  const [wording, setWording] = useState<Wording | null>(null);
  const [programs, setPrograms] = useState<Programs | null>(null);
  const [lessons, setLessons] = useState<Lessons | null>(null);
  const [answers, setAnswers] = useState<Answers | null>(null);
  const [harness, setHarness] = useState<Harness | null>(null);
  const [ladder, setLadder] = useState<LadderRow[]>([]);
  const [corrections, setCorrections] = useState<Corrections | null>(null);
  const [earned, setEarned] = useState<EarnedSkills | null>(null);
  const [replay, setReplay] = useState<Replay | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const data = await api.get("/tadbir/learning");
      setRows(workRows((data.routing as RoutingRow[]) ?? []));
      setWording((data.wording as Wording) ?? null);
      setAnswers((data.answers as Answers) ?? null);
      setLadder((data.ladder as LadderRow[]) ?? []);
      setCorrections((data.lessons as Corrections) ?? null);
      setEarned((data.earned_skills as EarnedSkills) ?? null);
      setReplay((data.replay as Replay) ?? null);
      setPrograms((await api.get("/tadbir/programs")) as unknown as Programs);
      setLessons((await api.get("/tadbir/lessons")) as unknown as Lessons);
      setError("");
    } catch {
      setError("MIZAN's learning could not be loaded");
    }
    try {
      // Admins only; everyone else simply does not see this card.
      setHarness((await api.get("/tadbir/harness")) as unknown as Harness);
    } catch {
      setHarness(null);
    }
  }, [api]);

  useEffect(() => {
    load();
  }, [load]);

  const run = async (action: () => Promise<unknown>, done: string, failed: string) => {
    setBusy(true);
    try {
      await action();
      addToast({ type: "success", title: done });
      await load();
    } catch {
      addToast({ type: "error", title: failed });
    } finally {
      setBusy(false);
    }
  };

  const forget = async () => {
    const ok = await confirmDialog({
      title: "Forget the wording MIZAN learned from you?",
      description: "MIZAN will read your requests from scratch again. This cannot be undone.",
      confirmLabel: "Forget wording",
      destructive: true,
    });
    if (!ok) return;
    setBusy(true);
    try {
      await api.del("/tadbir/learning/wording");
      addToast({ type: "success", title: "MIZAN forgot the wording it learned from you" });
      await load();
    } catch {
      addToast({ type: "error", title: "Could not forget the learned wording" });
    } finally {
      setBusy(false);
    }
  };

  const forgetAnswers = async () => {
    const ok = await confirmDialog({
      title: "Forget the answers MIZAN kept?",
      description: "Those questions will be sent to the language model again. This cannot be undone.",
      confirmLabel: "Forget answers",
      destructive: true,
    });
    if (!ok) return;
    setBusy(true);
    try {
      await api.del("/tadbir/answers");
      addToast({ type: "success", title: "MIZAN forgot the answers it kept for you" });
      await load();
    } catch {
      addToast({ type: "error", title: "Could not forget the kept answers" });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-3">
      {error && <div className="text-sm text-red-500">{error}</div>}

      <LiveLearning api={api} />

      <OnItsOwn api={api} />

      <div className="card">
        <div className="text-xxs font-semibold text-muted-foreground/80 uppercase tracking-widest mb-1">
          Who does which work · مَن يعمل ماذا
        </div>
        <p className="text-xs text-muted-foreground mb-3">
          MIZAN gives each part of a request to an agent and runs independent parts side by side.
          Every result it verifies, or fails to verify, moves these estimates.
        </p>
        {rows.length === 0 && (
          <div className="text-sm text-muted-foreground/80 text-center py-4">No agents yet</div>
        )}
        <ul className="divide-y divide-gray-200/60 dark:divide-gray-700/60">
          {rows.map((row) => (
            <li key={row.intent} className="py-2 flex flex-wrap items-center gap-x-3 gap-y-1">
              <span className="text-sm font-medium text-foreground min-w-[10rem]">
                {row.label}
              </span>
              <span className="text-sm text-mizan-gold font-semibold">{row.leader}</span>
              <span className="text-micro font-mono text-muted-foreground">
                {percent(row.estimate)} expected to verify
              </span>
              <span className="text-micro text-muted-foreground/80">
                {row.evidence > 0 ? learnedCount(row.evidence) : "prior only"}
              </span>
              {row.others.length > 0 && (
                <span className="text-micro text-muted-foreground/80 basis-full">
                  Also able: {row.others.map((o) => `${o.agent} ${percent(o.estimate)}`).join(" · ")}
                </span>
              )}
            </li>
          ))}
        </ul>
      </div>

      <div className="card">
        <div className="text-xxs font-semibold text-muted-foreground/80 uppercase tracking-widest mb-1">
          Wording MIZAN learned from you · تعلّم
        </div>
        <p className="text-xs text-muted-foreground mb-3">
          When the language model maps an unusual request and MIZAN verifies the result, MIZAN keeps that
          wording. Similar requests are then understood without the model. This stays private to your account.
        </p>
        <div className="flex flex-wrap items-center gap-3">
          <span className="text-sm text-foreground">
            {wording ? `${wording.examples} learned` : "—"}
          </span>
          {wording &&
            Object.entries(wording.by_intent).map(([intent, count]) => (
              <span
                key={intent}
                className="text-micro font-mono px-1.5 py-0.5 rounded bg-mizan-gold/10 text-mizan-gold"
              >
                {WORK_LABELS[intent] ?? intent}: {count}
              </span>
            ))}
          <span className="flex-1" />
          <button className="btn-secondary btn-sm" onClick={load}>
            Refresh
          </button>
          <button
            className="btn-secondary btn-sm"
            onClick={forget}
            disabled={busy || !wording?.examples}
          >
            Forget my wording
          </button>
        </div>
        <p className="text-micro text-muted-foreground/80 mt-3">
          This is MIZAN's own understanding, not model training. Training the own model's weights still needs an
          approved data bundle (Ruh Model → Own learning).
        </p>
      </div>

      <div className="card">
        <div className="text-xxs font-semibold text-muted-foreground/80 uppercase tracking-widest mb-1">
          Programs MIZAN keeps · حفظ
        </div>
        <p className="text-xs text-muted-foreground mb-3">
          A program MIZAN verified for you is kept. The same request, with the same numbers, re-runs it in the
          sandbox with no model call, and the output must match what was verified. A program whose output
          changes is distrusted and written again.
        </p>
        {programs && programs.items.length > 0 ? (
          <ul className="divide-y divide-gray-200/60 dark:divide-gray-700/60 mb-3">
            {programs.items.map((item, index) => (
              <li key={index} className="py-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
                <span className="min-w-0 flex-1 truncate text-foreground">{item.request}</span>
                <span className="text-micro font-mono text-muted-foreground">{item.language}</span>
                <span className="text-micro font-mono text-muted-foreground">
                  {item.runs} run{item.runs === 1 ? "" : "s"} · {percent(item.reliability)} reliable
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <div className="text-sm text-muted-foreground/80 mb-3">No programs kept yet</div>
        )}
        <button
          className="btn-secondary btn-sm"
          disabled={busy || !programs?.programs}
          onClick={async () => {
            const ok = await confirmDialog({
              title: "Forget the programs MIZAN kept?",
              description: "Verified programs are deleted and MIZAN must write them again. This cannot be undone.",
              confirmLabel: "Forget programs",
              destructive: true,
            });
            if (!ok) return;
            setBusy(true);
            try {
              await api.del("/tadbir/programs");
              addToast({ type: "success", title: "MIZAN forgot the programs it kept for you" });
              await load();
            } catch {
              addToast({ type: "error", title: "Could not forget the kept programs" });
            } finally {
              setBusy(false);
            }
          }}
        >
          Forget my programs
        </button>
      </div>

      <div className="card">
        <div className="text-xxs font-semibold text-muted-foreground/80 uppercase tracking-widest mb-1">
          Answers MIZAN learned from sources · تلقّي
        </div>
        <p className="text-xs text-muted-foreground mb-3">
          When the language model answers a question about the world and a source confirms every claim, MIZAN
          keeps the answer with its sources. The same question, opening a chat, is then answered with no model
          call. The claims are checked against the sources again on a schedule that lengthens each time they
          hold; an answer a source contradicts is dropped.
        </p>
        {answers && answers.items.length > 0 ? (
          <ul className="divide-y divide-border mb-3">
            {answers.items.map((item, index) => (
              <li key={index} className="py-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
                <span className="min-w-0 flex-1 truncate text-foreground">{item.request}</span>
                <span className="text-xs text-muted-foreground">{item.sources.join(", ")}</span>
                <span className="text-xs text-muted-foreground">
                  given again {item.reused}× · next check in {item.next_check_days} d
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground mb-3">No answers kept yet.</p>
        )}
        <div className="flex items-center gap-3">
          <span className="text-sm text-foreground">
            {answers ? `${answers.answers} kept · ${answers.reuses} given without the model` : "—"}
          </span>
          <span className="flex-1" />
          <button
            className="btn-secondary btn-sm"
            onClick={forgetAnswers}
            disabled={busy || !answers?.answers}
          >
            Forget these answers
          </button>
        </div>
      </div>

      <ShapesCard ladder={ladder} corrections={corrections} earned={earned} replay={replay} />

      <div className="card">
        <div className="text-xxs font-semibold text-muted-foreground/80 uppercase tracking-widest mb-1">
          Lessons from repairs · تجربة
        </div>
        <p className="text-xs text-muted-foreground mb-3">
          When a program failed in the sandbox and a repair then verified, MIZAN keeps the error (without your
          names or values) and the change that fixed it. Similar work later is written with that lesson in view.
          Lessons that stop helping are dropped.
        </p>
        {lessons && lessons.items.length > 0 ? (
          <ul className="divide-y divide-gray-200/60 dark:divide-gray-700/60 mb-3">
            {lessons.items.map((item, index) => (
              <li key={index} className="py-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
                <span className="min-w-0 flex-1 truncate font-mono text-xs text-foreground">
                  {item.signature}
                </span>
                <span className="text-micro font-mono text-muted-foreground">
                  {percent(item.usefulness)} useful
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <div className="text-sm text-muted-foreground/80 mb-3">No lessons yet</div>
        )}
        <button
          className="btn-secondary btn-sm"
          disabled={busy || !lessons?.lessons}
          onClick={async () => {
            const ok = await confirmDialog({
              title: "Forget MIZAN's repair lessons?",
              description: "Lessons learned from past fixes are deleted. This cannot be undone.",
              confirmLabel: "Forget lessons",
              destructive: true,
            });
            if (ok) await run(() => api.del("/tadbir/lessons"), "MIZAN forgot its repair lessons", "Could not forget the lessons");
          }}
        >
          Forget my lessons
        </button>
      </div>

      {harness && (
        <div className="card">
          <div className="text-xxs font-semibold text-muted-foreground/80 uppercase tracking-widest mb-1">
            Instructions MIZAN renewed · تجديد
          </div>
          <p className="text-xs text-muted-foreground mb-3">
            After repeated failures the model rewrites one of MIZAN&apos;s code instructions. The new version gets
            part of the work and replaces the old one only when MIZAN&apos;s checks show it is better (95%), or is
            retired. Shared by all users; only error kinds are stored.
            {!harness.evolution && " Renewal is off (System settings)."}
          </p>
          <ul className="divide-y divide-gray-200/60 dark:divide-gray-700/60 mb-3">
            {harness.instructions.map((row) => (
              <li key={row.task} className="py-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
                <span className="font-mono text-xs text-foreground min-w-[10rem]">{row.task}</span>
                <span className="text-micro font-mono text-muted-foreground">
                  {row.incumbent} ·{" "}
                  {row.incumbent_trials > 0
                    ? `${percent(row.incumbent_success)} verified over ${row.incumbent_trials}`
                    : "no results yet"}
                </span>
                {row.challenger ? (
                  <span className="text-micro font-mono text-mizan-gold">
                    trying {row.challenger.id}: {percent(row.challenger.success)} over {row.challenger.trials} ·{" "}
                    {row.challenger.evidence
                      ? `evidence ${row.challenger.evidence.better.toFixed(1)} of ${row.challenger.evidence.threshold} needed (${row.challenger.evidence.wins} won, ${row.challenger.evidence.losses} lost)`
                      : `P(better) ${percent(row.challenger.p_better)}`}
                  </span>
                ) : (
                  <span className="text-micro text-muted-foreground/80">
                    {row.failures_since_renewal} failures since renewal
                  </span>
                )}
                <span className="flex-1" />
                {(row.incumbent !== "base" || row.challenger) && (
                  <button
                    className="btn-secondary btn-sm"
                    disabled={busy}
                    onClick={async () => {
                      const ok = await confirmDialog({
                        title: "Reset this instruction?",
                        description: "The renewed instruction is dropped and MIZAN goes back to its built-in one.",
                        confirmLabel: "Reset",
                        destructive: true,
                      });
                      if (!ok) return;
                      await run(
                        () => api.del(`/tadbir/harness/${row.task}`),
                        "Back to MIZAN's built-in instruction",
                        "Could not reset the instruction",
                      );
                    }}
                  >
                    Reset
                  </button>
                )}
              </li>
            ))}
          </ul>
          {harness.models.length > 0 && (
            <>
              <div className="text-xxs font-semibold text-muted-foreground/80 uppercase tracking-widest mb-1">
                Models for code work · وزن
              </div>
              <ul className="text-micro font-mono text-muted-foreground space-y-0.5">
                {harness.routing
                  .filter((row) => row.evidence > 0)
                  .map((row) => (
                    <li key={`${row.task}-${row.model}`}>
                      {row.task} · {row.model}: {percent(row.success)} verified
                    </li>
                  ))}
              </ul>
            </>
          )}
        </div>
      )}
    </div>
  );
}

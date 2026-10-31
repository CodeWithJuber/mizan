/**
 * The person's lessons (docs/tadrib.md): their own messages MIZAN's language
 * reader learned from while it worked, or holds out as test. Each can be
 * taken back; the server then rebuilds every model without it.
 */
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { confirmDialog } from "@/components/ui/confirm";
import { config } from "../config";
import { authFetch } from "../utils/authFetch";

interface Lesson {
  digest: string;
  language: string;
  text: string;
  created: string;
  status: "learned" | "held_out";
  consolidated: boolean;
}

const PAGE = 20;

const LANGUAGES: Record<string, string> = {
  en: "English",
  hi: "Hindi",
  ur: "Urdu",
  ar: "Arabic",
  "hi-latn": "Roman Hindi/Urdu",
};

async function fetchLessons(from: number, signal?: AbortSignal): Promise<{ lessons: Lesson[]; total: number }> {
  const response = await authFetch(`${config.API_URL}/tadrib/lessons?limit=${PAGE}&offset=${from}`, { signal });
  if (!response.ok) throw new Error("unavailable");
  return (await response.json()) as { lessons: Lesson[]; total: number };
}

export function ReaderLessons() {
  const [lessons, setLessons] = useState<Lesson[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [status, setStatus] = useState("");

  const show = (data: { lessons: Lesson[]; total: number }, from: number) => {
    setLessons(data.lessons);
    setTotal(data.total);
    setOffset(from);
  };

  const load = async (from: number) => {
    try {
      show(await fetchLessons(from), from);
    } catch {
      setStatus("Your lessons could not be loaded.");
    }
  };

  useEffect(() => {
    const controller = new AbortController();
    void (async () => {
      try {
        const data = await fetchLessons(0, controller.signal);
        if (!controller.signal.aborted) show(data, 0);
      } catch {
        // No lessons to show (none yet, or the server has no reader): nothing is drawn.
      }
    })();
    return () => controller.abort();
  }, []);

  const takeBack = async (lesson: Lesson) => {
    const ok = await confirmDialog({
      title: "Take this lesson back?",
      description: "It is deleted, and every version of MIZAN's reader that learned it is rebuilt without it.",
      confirmLabel: "Take back",
      destructive: true,
    });
    if (!ok) return;
    try {
      const response = await authFetch(`${config.API_URL}/tadrib/lessons/${lesson.digest}`, { method: "DELETE" });
      if (!response.ok) throw new Error("not removed");
      setStatus("Taken back. The reader no longer holds it.");
      void load(lessons.length === 1 && offset > 0 ? offset - PAGE : offset);
    } catch {
      setStatus("Could not take it back. Try again.");
    }
  };

  if (total === 0 && !status) return null;

  return (
    <section aria-labelledby="reader-lessons" className="mx-5 mt-3 rounded-lg border bg-card p-4 text-sm">
      <h3 id="reader-lessons" className="font-semibold">What MIZAN's reader learned from you</h3>
      <p className="mt-0.5 text-xs text-muted-foreground">
        With training on, each of your messages teaches MIZAN's own language reader within seconds, where it and
        Lughah read the same language. One in five is kept as a test and never learned.
      </p>
      <ul className="mt-3 divide-y">
        {lessons.map((lesson) => (
          <li key={lesson.digest} className="flex items-start justify-between gap-3 py-2">
            <div className="min-w-0">
              <p className="break-words">{lesson.text}</p>
              <p className="mt-0.5 text-xs text-muted-foreground">
                {LANGUAGES[lesson.language] ?? lesson.language} ·{" "}
                {lesson.status === "held_out" ? "kept as a test" : lesson.consolidated ? "learned, kept by a night" : "learned"} ·{" "}
                {lesson.created ? new Date(lesson.created).toLocaleString() : ""}
              </p>
            </div>
            <Button variant="outline" size="sm" onClick={() => void takeBack(lesson)}>
              Take back
            </Button>
          </li>
        ))}
      </ul>
      {total > PAGE && (
        <div className="mt-2 flex items-center gap-2 text-xs text-muted-foreground">
          <Button variant="ghost" size="sm" disabled={offset === 0} onClick={() => void load(Math.max(0, offset - PAGE))}>
            Newer
          </Button>
          <span>
            {offset + 1}–{Math.min(offset + PAGE, total)} of {total}
          </span>
          <Button variant="ghost" size="sm" disabled={offset + PAGE >= total} onClick={() => void load(offset + PAGE)}>
            Older
          </Button>
        </div>
      )}
      {status && <output aria-live="polite" className="mt-3 block text-xs text-muted-foreground">{status}</output>}
    </section>
  );
}

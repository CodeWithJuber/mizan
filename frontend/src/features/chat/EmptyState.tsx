/** A new chat: a greeting and a few things MIZAN does well, one tap away. */
import { BookOpen, Code2, ScrollText, Sunrise } from "lucide-react";
import { Link } from "react-router-dom";
import { useChatActions } from "./ChatProvider";

const SUGGESTIONS = [
  {
    icon: BookOpen,
    title: "Find an ayah",
    prompt: "Which ayah talks about patience in hardship? Quote it with a translation.",
  },
  {
    icon: ScrollText,
    title: "Check a hadith",
    prompt: "Is this hadith in Bukhari or Muslim: \"Actions are judged by intentions\"?",
  },
  {
    icon: Code2,
    title: "Build a small app",
    prompt: "Build me a simple to-do web app with add, done and delete.",
  },
  {
    icon: Sunrise,
    title: "Plan around salah",
    prompt: "Help me plan tomorrow around the five prayers in my city.",
  },
];

export function EmptyState() {
  const { setInput, focusComposer } = useChatActions();
  return (
    <div className="flex min-h-full flex-col items-center justify-center px-4 py-10">
      <div className="mb-8 text-center">
        <div className="mx-auto mb-4 font-arabic text-5xl leading-none text-brand" aria-hidden="true">ميزان</div>
        <h1 className="text-2xl font-semibold tracking-tight">Assalamu alaikum</h1>
        <p className="mt-1.5 text-sm text-muted-foreground">
          Ask anything. MIZAN checks Quran and hadith text against the sources and shows how sure each answer is.
        </p>
      </div>
      <div className="grid w-full max-w-2xl grid-cols-1 gap-2.5 sm:grid-cols-2">
        {SUGGESTIONS.map(({ icon: Icon, title, prompt }) => (
          <button
            key={title}
            type="button"
            onClick={() => {
              setInput(prompt);
              focusComposer();
            }}
            className="group flex items-start gap-3 rounded-xl border bg-card p-3.5 text-left transition-colors hover:border-ring/60 hover:bg-accent/50 focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
          >
            <Icon className="mt-0.5 size-4 shrink-0 text-brand" />
            <span className="min-w-0">
              <span className="block text-sm font-medium">{title}</span>
              <span className="mt-0.5 line-clamp-2 block text-xs text-muted-foreground">{prompt}</span>
            </span>
          </button>
        ))}
      </div>
      <p className="mt-6 max-w-2xl text-center text-xs text-balance text-muted-foreground">
        MIZAN learns from your chats to help you, and lists all it keeps in your Daftar. Your words train no model
        unless you allow it.{" "}
        <Link to="/library/memory" className="font-medium text-brand underline-offset-4 hover:underline">
          Choose in Memory
        </Link>
      </p>
    </div>
  );
}

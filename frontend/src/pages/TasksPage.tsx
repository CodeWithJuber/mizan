/** Tasks: give the selected agent a background job and watch its output. */
import { useState } from "react";
import { Play } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useTerminal, addTerminalLine } from "../realtime/terminal";
import { sendSocket, useSocketStatus } from "../realtime/socket";
import { useSelectedAgent } from "../features/agents/agents";
import { addToast } from "../components/Toast";

const TONE: Record<string, string> = {
  error: "text-red-400",
  warn: "text-amber-300",
  info: "text-sky-300",
  gold: "text-amber-300",
};

export default function TasksPage() {
  const lines = useTerminal((state) => state.lines);
  const status = useSocketStatus((state) => state.status);
  const agent = useSelectedAgent();
  const [task, setTask] = useState("");

  const run = () => {
    if (!task.trim()) return;
    if (!sendSocket({ type: "task", task, agent_id: agent?.id })) {
      addToast({ type: "warning", title: "Not connected", description: "Tasks run over the live connection; wait for it to reconnect." });
      return;
    }
    addTerminalLine(`$ ${task}`, "gold");
    setTask("");
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3 p-4 sm:p-6">
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl border bg-neutral-950 text-neutral-200">
        <div className="flex items-center gap-2 border-b border-white/10 px-4 py-2.5 text-xs text-neutral-400">
          <span className="font-mono">mizan ~ %</span>
          <span className="ml-auto">Agent: {agent?.name ?? "none"} · {status === "connected" ? "connected" : status}</span>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-4 font-mono text-xs leading-relaxed" role="log" aria-live="polite">
          {lines.map((line, index) => (
            <div key={index} className={TONE[line.type] ?? "text-emerald-300"}>
              {line.type === "gold" && <span className="font-semibold">{"> "}</span>}
              {line.text}
            </div>
          ))}
        </div>
        <form
          className="flex items-center gap-2 border-t border-white/10 p-2"
          onSubmit={(event) => {
            event.preventDefault();
            run();
          }}
        >
          <Input
            value={task}
            onChange={(event) => setTask(event.target.value)}
            placeholder="A task for the agent (e.g. search for the latest AI papers)"
            aria-label="Task for the agent"
            className="border-white/10 bg-transparent font-mono text-xs text-neutral-100 placeholder:text-neutral-500"
          />
          <Button type="submit" size="sm" disabled={!task.trim()}>
            <Play /> Run
          </Button>
        </form>
      </div>
    </div>
  );
}

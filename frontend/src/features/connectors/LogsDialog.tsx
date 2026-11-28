/** The latest lines a connector wrote (start-up, errors, stderr of a local server). */
import { Copy, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { addToast } from "../../components/Toast";
import { useLogs } from "./api";
import type { Connector } from "./types";

export function LogsDialog({ connector, onClose }: { connector: Connector; onClose: () => void }) {
  const { data: lines, error, isFetching, refetch } = useLogs(connector.id, true);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText((lines ?? []).join("\n"));
      addToast({ type: "success", title: "Logs copied" });
    } catch {
      addToast({ type: "error", title: "Could not copy", description: "Select the lines and copy them instead." });
    }
  };
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Logs · {connector.name}</DialogTitle>
          <DialogDescription>The latest lines from this connector, newest last. Secrets are never written here.</DialogDescription>
        </DialogHeader>
        {error ? (
          <p className="text-sm text-destructive">Could not load the logs: {error.message}</p>
        ) : !lines ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : lines.length === 0 ? (
          <p className="text-sm text-muted-foreground">Nothing logged yet. Connect or test it, then refresh.</p>
        ) : (
          <textarea
            readOnly
            wrap="off"
            aria-label={`Log lines of ${connector.name}`}
            value={lines.join("\n")}
            className="h-[55vh] w-full min-w-0 resize-none rounded-md border bg-muted/40 p-2 font-mono text-xs leading-relaxed outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
          />
        )}
        <DialogFooter>
          <Button variant="outline" disabled={isFetching} onClick={() => void refetch()}>
            <RefreshCw className={isFetching ? "animate-spin" : undefined} aria-hidden /> Refresh
          </Button>
          <Button variant="outline" disabled={!lines?.length} onClick={() => void copy()}>
            <Copy aria-hidden /> Copy
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

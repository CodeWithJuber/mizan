/** Cards under an answer for the artifacts saved with it; each opens the panel. */
import { FileCode } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useChatActions, useChatState } from "./ChatProvider";

export function MessageArtifacts({ ids }: { ids?: string[] }) {
  const { artifacts } = useChatState();
  const { setShowArtifacts } = useChatActions();
  if (!ids?.length) return null;
  return (
    <div className="mt-2 flex flex-wrap gap-2">
      {ids.map((id) => {
        const title = artifacts.find((artifact) => artifact.id === id)?.title ?? "Artifact";
        return (
          <Button key={id} variant="outline" size="sm" onClick={() => setShowArtifacts(true)}>
            <FileCode aria-hidden="true" />
            <span className="max-w-48 truncate">{title}</span>
            <span className="text-muted-foreground">· Open</span>
          </Button>
        );
      })}
    </div>
  );
}

/** Debug: one message to the base model alone and to MIZAN, with every step MIZAN took. */
import DebugCompare from "../components/DebugCompare";
import { useApi } from "../hooks/useApi";
import { useChatActions, useChatState } from "../features/chat/ChatProvider";

export default function DebugPage() {
  const api = useApi();
  const { debugPrompt } = useChatState();
  const { setDebugPrompt } = useChatActions();
  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        The same message to the model alone and to MIZAN, with every step MIZAN took.
      </p>
      <DebugCompare api={api} initialPrompt={debugPrompt} onPromptUsed={() => setDebugPrompt(undefined)} />
    </div>
  );
}

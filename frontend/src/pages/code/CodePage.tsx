/** Code: the coding workspace — files, editor, preview, terminal — on the chat's project. */
import { useCallback, useEffect, useRef } from "react";
import { useBlocker, useNavigate } from "react-router-dom";
import { CodingWorkspace } from "../../components/CodingWorkspace";
import { confirmDialog } from "../../components/ui/confirm";
import { useChatActions, useChatState } from "../../features/chat/ChatProvider";
import type { Artifact } from "../../types";

export default function CodePage() {
  const { sessionId, workspaceId, messages } = useChatState();
  const actions = useChatActions();
  const navigate = useNavigate();
  const dirty = useRef(false);
  const setDirty = useCallback((value: boolean) => {
    dirty.current = value;
  }, []);

  // Leaving with unsaved editor changes asks first.
  const blocker = useBlocker(({ currentLocation, nextLocation }) =>
    dirty.current && currentLocation.pathname !== nextLocation.pathname);
  useEffect(() => {
    if (blocker.state !== "blocked") return;
    void confirmDialog({
      title: "Leave the editor?",
      description: "Unsaved changes in the editor will be lost.",
      confirmLabel: "Leave",
      destructive: true,
    }).then((leave) => {
      if (leave) {
        dirty.current = false;
        blocker.proceed();
      } else blocker.reset();
    });
  }, [blocker]);

  return (
    <div className="page-wrapper">
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
        <CodingWorkspace
          sessionId={sessionId}
          selectedId={workspaceId}
          onSelect={actions.selectWorkspace}
          onDirtyChange={setDirty}
          onArtifact={(artifact) => {
            if (artifact.session_id !== sessionId) return;
            const full = {
              ...artifact,
              versions: artifact.versions ?? (typeof artifact.content === "string"
                ? [{
                    version: artifact.current_version ?? 1,
                    content: artifact.content,
                    created_at: artifact.created_at ?? new Date().toISOString(),
                  }]
                : []),
            } as Artifact;
            actions.addArtifact(full);
          }}
          onAskAgent={(content) => {
            dirty.current = false;
            navigate(messages.length ? `/chat/${encodeURIComponent(sessionId)}` : "/chat");
            actions.setInput(content);
            setTimeout(actions.focusComposer, 50);
          }}
        />
      </div>
    </div>
  );
}

/** Edit a connector in a side sheet: the same form as adding, with saved secrets write-only. */
import { useState } from "react";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { addToast } from "../../components/Toast";
import type { ConnectorActions } from "./api";
import { ConnectorForm } from "./ConnectorForm";
import { type Draft, draftFromConnector, patchBody } from "./logic";
import type { Capabilities, Connector } from "./types";

/** Changes that only take effect on a new connection. */
const RECONNECT_FIELDS = ["transport", "url", "command", "args", "headers", "env", "oauth", "timeouts"];

interface Props {
  connector: Connector;
  capabilities: Capabilities;
  actions: ConnectorActions;
  onClose: () => void;
  onReconnect: (connector: Connector) => void;
}

export function EditSheet({ connector, capabilities, actions, onClose, onReconnect }: Props) {
  const [draft, setDraft] = useState<Draft>(() => draftFromConnector(connector));
  const [busy, setBusy] = useState(false);

  const save = async () => {
    const body = patchBody(draft, connector);
    if (!Object.keys(body).length) {
      addToast({ type: "info", title: "Nothing changed" });
      onClose();
      return;
    }
    setBusy(true);
    try {
      const updated = await actions.update(connector, body);
      const live = connector.status === "connected" || connector.status === "connecting";
      const needsReconnect = live && RECONNECT_FIELDS.some((field) => field in body);
      addToast({
        type: "success",
        title: `${updated.name} saved`,
        ...(needsReconnect
          ? { description: "Reconnect to use the new settings.", action: { label: "Reconnect", onClick: () => onReconnect(updated) } }
          : {}),
      });
      onClose();
    } catch (problem) {
      addToast({ type: "error", title: "Could not save", description: problem instanceof Error ? problem.message : undefined });
    } finally {
      setBusy(false);
    }
  };

  return (
    <Sheet open onOpenChange={(open) => !open && onClose()}>
      <SheetContent side="right" className="gap-0 overflow-y-auto data-[side=right]:w-full data-[side=right]:sm:max-w-xl">
        <SheetHeader className="border-b pr-12">
          <SheetTitle>Edit {connector.name}</SheetTitle>
          <SheetDescription>
            Saved headers and variables show only their names: replace or delete them, they are never shown again.
          </SheetDescription>
        </SheetHeader>
        <div className="p-4">
          <ConnectorForm
            idPrefix={`edit-${connector.id}`}
            mode="edit"
            draft={draft}
            onChange={setDraft}
            capabilities={capabilities}
            busy={busy}
            submitLabel="Save changes"
            onSubmit={() => void save()}
            onCancel={onClose}
            savedClientSecret={Boolean(connector.auth.client_id)}
          />
        </div>
      </SheetContent>
    </Sheet>
  );
}

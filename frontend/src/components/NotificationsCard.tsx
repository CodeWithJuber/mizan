/**
 * Notifications on this device: MIZAN's watcher notices and held actions as
 * Web Push, even with the app closed. The lock screen shows only "MIZAN has a
 * new notice" unless you set the chat preference push_preview: on.
 */
import { useCallback, useEffect, useState } from "react";
import type { ApiClient } from "../types";
import { useToast } from "./Toast";
import { currentSubscription, keyBytes, pushState, registerWorker, type PushState } from "../utils/push.ts";

export function NotificationsCard({ api }: { api: ApiClient }) {
  const { addToast } = useToast();
  const [state, setState] = useState<PushState | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => setState(await pushState()), []);
  useEffect(() => {
    refresh();
  }, [refresh]);

  const turnOn = async () => {
    setBusy(true);
    try {
      if ((await Notification.requestPermission()) !== "granted") {
        await refresh();
        return;
      }
      const registration = (await registerWorker()) ?? (await navigator.serviceWorker.ready);
      const { public_key } = (await api.get("/bab/push/key")) as { public_key: string };
      const subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: keyBytes(public_key),
      });
      await api.post("/bab/push/subscription", subscription.toJSON() as Record<string, unknown>);
      addToast({ type: "success", title: "Notifications are on for this device" });
    } catch (error) {
      addToast({ type: "error", title: "Notifications not turned on", description: (error as Error).message });
    } finally {
      setBusy(false);
      await refresh();
    }
  };

  const turnOff = async () => {
    setBusy(true);
    try {
      const subscription = await currentSubscription();
      if (subscription) {
        await api.del(`/bab/push/subscription?endpoint=${encodeURIComponent(subscription.endpoint)}`).catch(() => undefined);
        await subscription.unsubscribe();
      }
    } finally {
      setBusy(false);
      await refresh();
    }
  };

  if (state === null) return null;
  return (
    <div className="card p-4 space-y-2">
      <div className="flex items-center justify-between gap-2">
        <div>
          <div className="text-sm font-medium text-gray-900 dark:text-gray-100">Notifications on this device</div>
          <p className="text-xs text-gray-500 dark:text-gray-400">
            {state === "unsupported" && "This browser cannot receive notifications. On iPhone, add MIZAN to the Home Screen first."}
            {state === "denied" && "Notifications are blocked for MIZAN in this browser's settings."}
            {state === "off" && "Get your watchers' notices and actions waiting for you, even with MIZAN closed."}
            {state === "on" && "On. The lock screen shows only “MIZAN has a new notice” unless you set push_preview: on."}
          </p>
        </div>
        {state === "off" && (
          <button className="btn-gold btn-sm min-h-[36px]" disabled={busy} onClick={turnOn}>
            Turn on
          </button>
        )}
        {state === "on" && (
          <span className="flex gap-2">
            <button
              className="btn-secondary btn-sm min-h-[36px]"
              disabled={busy}
              onClick={async () => {
                const sent = (await api.post("/bab/push/test")) as { sent?: number };
                addToast({ type: sent.sent ? "success" : "warning", title: sent.sent ? "Test notice sent" : "No device received it" });
              }}
            >
              Test
            </button>
            <button className="btn-secondary btn-sm min-h-[36px]" disabled={busy} onClick={turnOff}>
              Turn off
            </button>
          </span>
        )}
      </div>
    </div>
  );
}

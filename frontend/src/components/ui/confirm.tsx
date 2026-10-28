/**
 * A promise-based confirmation dialog that replaces `window.confirm`.
 *
 *   if (!(await confirmDialog({ title: "Delete this chat?", destructive: true }))) return;
 *
 * `<ConfirmHost />` is mounted once at the root; any code (hooks, plain
 * functions) may ask. Requests made while one is open wait their turn.
 */

import { useSyncExternalStore } from "react";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";

export interface ConfirmOptions {
  title: string;
  description?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  destructive?: boolean;
  /** Only an acknowledgement: one button, resolves true (replaces `alert`). */
  notice?: boolean;
}

interface Request extends ConfirmOptions {
  resolve: (ok: boolean) => void;
}

let queue: Request[] = [];
const listeners = new Set<() => void>();
const emit = () => listeners.forEach((listener) => listener());

export function confirmDialog(options: ConfirmOptions): Promise<boolean> {
  return new Promise((resolve) => {
    queue = [...queue, { ...options, resolve }];
    emit();
  });
}

/** `alert` replacement: shows the message and waits for OK. */
export function noticeDialog(title: string, description?: string): Promise<boolean> {
  return confirmDialog({ title, description, notice: true, confirmLabel: "OK" });
}

function settle(ok: boolean) {
  const [current, ...rest] = queue;
  if (!current) return;
  queue = rest;
  emit();
  current.resolve(ok);
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function ConfirmHost() {
  const current = useSyncExternalStore(subscribe, () => queue[0]);
  return (
    <AlertDialog open={Boolean(current)} onOpenChange={(open) => !open && settle(false)}>
      {current && (
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{current.title}</AlertDialogTitle>
            {current.description && (
              <AlertDialogDescription>{current.description}</AlertDialogDescription>
            )}
          </AlertDialogHeader>
          <AlertDialogFooter>
            {!current.notice && (
              <AlertDialogCancel>{current.cancelLabel ?? "Cancel"}</AlertDialogCancel>
            )}
            <AlertDialogAction
              variant={current.destructive ? "destructive" : "default"}
              onClick={() => settle(true)}
              autoFocus
            >
              {current.confirmLabel ?? (current.destructive ? "Delete" : "Continue")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      )}
    </AlertDialog>
  );
}

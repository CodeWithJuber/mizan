/**
 * Toasts for MIZAN, drawn by sonner. `useToast().addToast` keeps the shape
 * every page already calls, so no call site changes.
 */

import { Toaster, toast } from "sonner";
import { useTheme } from "../hooks/useTheme";

export interface ToastInput {
  type: "success" | "error" | "warning" | "info";
  title: string;
  description?: string;
}

export function addToast({ type, title, description }: ToastInput) {
  toast[type](title, { description });
}

const api = { addToast };

export function useToast() {
  return api;
}

/** Mount once near the root; children render unchanged. */
export function ToastProvider({ children }: { children?: React.ReactNode }) {
  const { isDark } = useTheme();
  return (
    <>
      {children}
      <Toaster
        theme={isDark ? "dark" : "light"}
        position="bottom-right"
        richColors
        closeButton
        duration={4500}
        toastOptions={{ className: "font-body" }}
      />
    </>
  );
}

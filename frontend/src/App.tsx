/**
 * MIZAN — the signed-in app: server-state cache, toasts, dialogs and the
 * router. Pages live under src/pages and src/features; the shell is src/app.
 */
import { QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "react-router-dom";
import { queryClient } from "./app/queryClient";
import { router } from "./app/router";
import { ToastProvider } from "./components/Toast";
import { ConfirmHost } from "./components/ui/confirm";

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <RouterProvider router={router} />
        <ConfirmHost />
      </ToastProvider>
    </QueryClientProvider>
  );
}

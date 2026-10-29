/** Signed-in layout: the sidebar, and the page beside it. */
import { Suspense } from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ChatProvider } from "../features/chat/ChatProvider";
import { useRealtimeSocket } from "../realtime/socket";
import { AppSidebar } from "./AppSidebar";
import { ErrorBoundary } from "./ErrorBoundary";
import { PageFallback } from "./PageFallback";

function readSidebarCookie(): boolean {
  return !document.cookie.split("; ").includes("sidebar_state=false");
}

function Realtime() {
  useRealtimeSocket();
  return null;
}

export function AppShell() {
  const { pathname } = useLocation();
  let setupDone = true;
  try {
    setupDone = Boolean(localStorage.getItem("mizan_setup_complete"));
  } catch {
    // Storage blocked: skip the first-run setup.
  }
  if (!setupDone) return <Navigate to="/welcome" replace />;
  return (
    <ChatProvider>
      <Realtime />
      <TooltipProvider delay={400}>
        <SidebarProvider defaultOpen={readSidebarCookie()} className="h-dvh min-h-0 overflow-hidden">
          <a
            href="#main"
            className="sr-only z-50 rounded-md bg-background px-3 py-2 focus:not-sr-only focus:absolute focus:left-2 focus:top-2"
          >
            Skip to content
          </a>
          <AppSidebar />
          <SidebarInset id="main" className="min-h-0 overflow-hidden">
            <ErrorBoundary resetKey={pathname}>
              <Suspense fallback={<PageFallback />}>
                <Outlet />
              </Suspense>
            </ErrorBoundary>
          </SidebarInset>
        </SidebarProvider>
      </TooltipProvider>
    </ChatProvider>
  );
}

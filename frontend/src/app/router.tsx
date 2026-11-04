/**
 * Every page has a URL. Pages load on demand; the chat, which nearly every
 * visit opens first, starts downloading as soon as the shell runs.
 */
import { lazy, Suspense, type ReactNode } from "react";
import { createBrowserRouter, Link, Navigate, Outlet, useNavigate } from "react-router-dom";
import { useApi } from "../hooks/useApi";
import { useSocketStatus } from "../realtime/socket";
import { addTerminalLine } from "../realtime/terminal";
import { AppShell } from "./AppShell";
import { RequireAdmin, RequireAuth } from "./RequireAuth";
import { useIsAdmin } from "./auth";
import { RouteError } from "./ErrorBoundary";
import { SectionLayout } from "./SectionLayout";
import { SettingsLayout } from "./SettingsLayout";
import { PageFallback } from "./PageFallback";
import { takeLegacyTab } from "./legacyTabs";
import type { DeveloperTab } from "../pages/DeveloperPage";
import type { SettingsSection } from "../pages/SettingsPage";

const chatPage = import("../features/chat/ChatPage");
const ChatPage = lazy(() => chatPage);
const LoginPage = lazy(() => import("../pages/LoginPage"));
const WelcomePage = lazy(() => import("../pages/WelcomePage"));
const CodePage = lazy(() => import("../pages/code/CodePage"));
const AgentsPage = lazy(() => import("../pages/AgentsPage"));
const MajlisPage = lazy(() => import("../pages/MajlisPage"));
const MemoryPage = lazy(() => import("../pages/MemoryPage"));
const KnowledgePage = lazy(() => import("../pages/KnowledgePage"));
const NotebookPage = lazy(() => import("../pages/NotebookPage"));
const WatchersPage = lazy(() => import("../pages/WatchersPage"));
const AutomationPage = lazy(() => import("../pages/AutomationPage"));
const TasksPage = lazy(() => import("../pages/TasksPage"));
const QueuePage = lazy(() => import("../pages/QueuePage"));
const SecurityPage = lazy(() => import("../pages/SecurityPage"));
const AppearancePage = lazy(() => import("../pages/AppearancePage"));
const ChannelsPage = lazy(() => import("../pages/ChannelsPage"));
const ConnectorsPage = lazy(() => import("../pages/ConnectorsPage"));
const SkillsPage = lazy(() => import("../pages/SkillsPage"));
const SpendingPanel = lazy(() => import("../components/SpendingPanel"));
const SakkPanel = lazy(() => import("../components/SakkPanel"));
const SettingsPage = lazy(() => import("../pages/SettingsPage"));
const ProvidersPage = lazy(() => import("../pages/ProvidersPage"));
const DeveloperPage = lazy(() => import("../pages/DeveloperPage"));
const DebugPage = lazy(() => import("../pages/DebugPage"));
const ComparePanel = lazy(() => import("../components/ComparePanel"));
const ScannerPage = lazy(() => import("../pages/ScannerPage"));
const RuhModelPage = lazy(() => import("../pages/RuhModelPage"));
const PerceptionPage = lazy(() => import("../pages/PerceptionPage"));
const PluginsPage = lazy(() => import("../pages/PluginsPage"));

/** Pages written before the router take `api` (and sometimes a log line). */
function WithApi({ page: Page }: { page: React.ComponentType<{ api: ReturnType<typeof useApi>; addTerminalLine?: typeof addTerminalLine }> }) {
  const api = useApi();
  return <Page api={api} addTerminalLine={addTerminalLine} />;
}

function Settings({ section }: { section: SettingsSection }) {
  const api = useApi();
  return <SettingsPage api={api} section={section} />;
}

function Developer({ tab }: { tab: DeveloperTab }) {
  const api = useApi();
  return <DeveloperPage api={api} tab={tab} />;
}

function Panel({ children }: { children: ReactNode }) {
  return <div className="page-body">{children}</div>;
}

function SpendingRoute() {
  const api = useApi();
  return <Panel><SpendingPanel api={api} /></Panel>;
}

function ReceiptsRoute() {
  const api = useApi();
  return <Panel><SakkPanel api={api} /></Panel>;
}

function Welcome() {
  const api = useApi();
  const status = useSocketStatus((state) => state.status);
  const navigate = useNavigate();
  const admin = useIsAdmin();
  // Leaving setup for a page counts as finishing it; otherwise the app shell
  // sends the person straight back here.
  const leave = (to: string) => {
    try {
      localStorage.setItem("mizan_setup_complete", "true");
    } catch {
      // Storage blocked: the app shell skips setup anyway.
    }
    navigate(to, { replace: true });
  };
  return (
    <Suspense fallback={<PageFallback />}>
      <WelcomePage
        api={api}
        wsStatus={status}
        onComplete={() => navigate("/chat", { replace: true })}
        onOpenSettings={admin ? () => leave("/settings/developer/providers") : undefined}
        onNavigate={leave}
      />
    </Suspense>
  );
}

/** "/" lands where an old visit left off, else in the chat. */
function Home() {
  return <Navigate to={takeLegacyTab() ?? "/chat"} replace />;
}

const page = (element: ReactNode) => ({ element });

export const router = createBrowserRouter([
  {
    path: "/login",
    errorElement: <RouteError />,
    element: (
      <Suspense fallback={<PageFallback />}>
        <LoginPage />
      </Suspense>
    ),
  },
  {
    path: "/welcome",
    errorElement: <RouteError />,
    element: <RequireAuth><Welcome /></RequireAuth>,
  },
  {
    path: "/",
    errorElement: <RouteError />,
    element: <RequireAuth><AppShell /></RequireAuth>,
    children: [
      { index: true, element: <Home /> },
      { path: "chat/:sessionId?", element: <ChatPage /> },
      { path: "code/:projectId?", element: <CodePage /> },
      {
        path: "agents",
        element: <SectionLayout title="Agents" tabs={[{ to: "/agents", label: "Your agents", end: true }, { to: "/agents/majlis", label: "Majlis" }]} />,
        children: [
          { index: true, element: <AgentsPage /> },
          { path: "majlis", ...page(<WithApi page={MajlisPage} />) },
        ],
      },
      {
        path: "library",
        element: (
          <SectionLayout
            title="Library"
            tabs={[
              { to: "/library/memory", label: "Memory" },
              { to: "/library/knowledge", label: "Knowledge" },
              { to: "/library/notebooks", label: "Notebooks" },
            ]}
          />
        ),
        children: [
          { index: true, element: <Navigate to="memory" replace /> },
          { path: "memory", element: <MemoryPage /> },
          { path: "knowledge", element: <KnowledgePage /> },
          { path: "notebooks", ...page(<WithApi page={NotebookPage} />) },
        ],
      },
      {
        path: "automations",
        element: (
          <SectionLayout
            title="Automations"
            tabs={[
              { to: "/automations/watchers", label: "Watchers" },
              { to: "/automations/schedules", label: "Schedules & webhooks" },
              { to: "/automations/tasks", label: "Tasks" },
              { to: "/automations/queue", label: "Queue" },
            ]}
          />
        ),
        children: [
          { index: true, element: <Navigate to="watchers" replace /> },
          { path: "watchers", ...page(<WithApi page={WatchersPage} />) },
          { path: "schedules", ...page(<WithApi page={AutomationPage} />) },
          { path: "tasks", element: <TasksPage /> },
          { path: "queue", element: <QueuePage /> },
        ],
      },
      {
        path: "settings",
        element: <SettingsLayout />,
        children: [
          { index: true, element: <Navigate to="account" replace /> },
          { path: "account", ...page(<WithApi page={SecurityPage} />) },
          { path: "appearance", element: <AppearancePage /> },
          { path: "channels", ...page(<WithApi page={ChannelsPage} />) },
          { path: "connectors", ...page(<WithApi page={ConnectorsPage} />) },
          { path: "skills", ...page(<WithApi page={SkillsPage} />) },
          { path: "spending", element: <SpendingRoute /> },
          { path: "receipts", element: <ReceiptsRoute /> },
          // Debug compare: administrators, and everyone when MIZAN_DEBUG_MODE=users.
          { path: "developer/debug", element: <Panel><DebugPage /></Panel> },
          {
            path: "developer",
            element: <RequireAdmin><SettingsOutlet /></RequireAdmin>,
            children: [
              { index: true, element: <Navigate to="system" replace /> },
              { path: "system", element: <Settings section="system" /> },
              { path: "providers", ...page(<WithApi page={ProvidersPage} />) },
              { path: "keys", element: <Settings section="providers" /> },
              { path: "bots", element: <Settings section="channels" /> },
              { path: "security", element: <Settings section="security" /> },
              { path: "vault", element: <Settings section="vault" /> },
              { path: "memory", element: <Settings section="memory" /> },
              { path: "about", element: <Developer tab="system" /> },
              { path: "compare", element: <Panel><ComparePanel /></Panel> },
              { path: "agi", element: <Developer tab="agi" /> },
              { path: "teach", element: <Developer tab="teach" /> },
              { path: "scanner", ...page(<WithApi page={ScannerPage} />) },
              { path: "ruh", ...page(<WithApi page={RuhModelPage} />) },
              { path: "perception", ...page(<WithApi page={PerceptionPage} />) },
              { path: "plugins", ...page(<WithApi page={PluginsPage} />) },
              { path: "events", element: <Developer tab="events" /> },
              { path: "hooks", element: <Developer tab="hooks" /> },
              { path: "guide", element: <Developer tab="guide" /> },
            ],
          },
        ],
      },
      { path: "*", element: <NotFound /> },
    ],
  },
]);


function SettingsOutlet() {
  return <Outlet />;
}

function NotFound() {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-3 p-8 text-center">
      <p className="font-arabic text-4xl text-brand">ميزان</p>
      <h1 className="text-lg font-semibold">This page does not exist</h1>
      <Link to="/chat" className="text-sm text-brand underline-offset-4 hover:underline">Back to chat</Link>
    </div>
  );
}

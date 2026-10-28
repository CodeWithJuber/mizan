/**
 * Settings: the person's own settings, and — for administrators — Developer:
 * the server, models, quality tools and extensions.
 */
import { Suspense } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { cn } from "@/lib/utils";
import { SidebarTrigger } from "@/components/ui/sidebar";
import { useIsAdmin } from "./auth";
import { useChatState } from "../features/chat/ChatProvider";
import { PageFallback } from "./PageFallback";

interface Item {
  to: string;
  label: string;
}

const USER: Item[] = [
  { to: "/settings/account", label: "Account" },
  { to: "/settings/appearance", label: "Appearance" },
  { to: "/settings/channels", label: "Channels" },
  { to: "/settings/connectors", label: "Connectors" },
  { to: "/settings/skills", label: "Skills" },
  { to: "/settings/spending", label: "Spending" },
  { to: "/settings/receipts", label: "Receipts" },
];

export const DEVELOPER_GROUPS: { label: string; items: Item[] }[] = [
  {
    label: "Server",
    items: [
      { to: "/settings/developer/system", label: "System settings" },
      { to: "/settings/developer/providers", label: "Models & providers" },
      { to: "/settings/developer/keys", label: "API keys" },
      { to: "/settings/developer/bots", label: "Bot tokens" },
      { to: "/settings/developer/security", label: "Server security" },
      { to: "/settings/developer/vault", label: "Secret vault" },
      { to: "/settings/developer/memory", label: "Memory upkeep" },
      { to: "/settings/developer/about", label: "Version & updates" },
    ],
  },
  {
    label: "Quality",
    items: [
      { to: "/settings/developer/debug", label: "Debug compare" },
      { to: "/settings/developer/compare", label: "Blind compare" },
      { to: "/settings/developer/agi", label: "AGI test" },
      { to: "/settings/developer/teach", label: "Teach MIZAN" },
      { to: "/settings/developer/scanner", label: "Scanner" },
    ],
  },
  {
    label: "Models & senses",
    items: [
      { to: "/settings/developer/ruh", label: "Ruh model" },
      { to: "/settings/developer/perception", label: "Perception" },
    ],
  },
  {
    label: "Extensions",
    items: [
      { to: "/settings/developer/plugins", label: "Plugins" },
      { to: "/settings/developer/events", label: "Events" },
      { to: "/settings/developer/hooks", label: "Hooks" },
      { to: "/settings/developer/guide", label: "Developer guide" },
    ],
  },
];

function Link({ item }: { item: Item }) {
  return (
    <NavLink
      to={item.to}
      className={({ isActive }) =>
        cn(
          "block whitespace-nowrap rounded-md px-2.5 py-1.5 text-sm transition-colors",
          isActive ? "bg-accent font-medium text-foreground" : "text-muted-foreground hover:bg-muted hover:text-foreground",
        )
      }
    >
      {item.label}
    </NavLink>
  );
}

export function SettingsLayout() {
  const admin = useIsAdmin();
  const { debugAllowed } = useChatState();
  const groups = admin
    ? DEVELOPER_GROUPS
    : debugAllowed
      ? [{ label: "Developer", items: [{ to: "/settings/developer/debug", label: "Debug compare" }] }]
      : [];
  return (
    <div className="flex min-h-0 flex-1 flex-col md:flex-row">
      <aside className="shrink-0 border-b md:w-60 md:border-b-0 md:border-r">
        <div className="flex items-center gap-2 px-4 pb-2 pt-3 md:pt-4">
          <SidebarTrigger className="-ml-1 md:hidden" />
          <h1 className="text-lg font-semibold tracking-tight">Settings</h1>
        </div>
        <nav aria-label="Settings" className="flex gap-1 overflow-x-auto px-3 pb-3 md:block md:space-y-4 md:overflow-y-auto md:pb-6">
          <div className="flex gap-1 md:block md:space-y-0.5">
            {USER.map((item) => <Link key={item.to} item={item} />)}
          </div>
          {groups.map((group) => (
            <div key={group.label} className="flex gap-1 md:block md:space-y-0.5">
              <p className="hidden px-2.5 pb-1 pt-2 text-xs font-medium uppercase tracking-wide text-muted-foreground md:block">
                {group.label === "Server" ? "Developer · Server" : group.label}
              </p>
              {group.items.map((item) => <Link key={item.to} item={item} />)}
            </div>
          ))}
        </nav>
      </aside>
      <div className="flex min-h-0 flex-1 flex-col overflow-y-auto">
        <Suspense fallback={<PageFallback />}>
          <Outlet />
        </Suspense>
      </div>
    </div>
  );
}

/** A section with a few pages (Library, Automations, Agents): title and tabs, then the page. */
import { Suspense } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { cn } from "@/lib/utils";
import { SidebarTrigger } from "@/components/ui/sidebar";
import { PageFallback } from "./PageFallback";

export interface SectionTab {
  to: string;
  label: string;
  end?: boolean;
}

export function SectionLayout({ title, tabs }: { title: string; tabs: SectionTab[] }) {
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <header className="shrink-0 border-b px-4 pt-3 sm:px-6">
        <div className="flex items-center gap-2">
          <SidebarTrigger className="-ml-1 md:hidden" />
          <h1 className="text-lg font-semibold tracking-tight sm:text-xl">{title}</h1>
        </div>
        <nav className="-mb-px mt-2 flex gap-1 overflow-x-auto" aria-label={`${title} pages`}>
          {tabs.map((tab) => (
            <NavLink
              key={tab.to}
              to={tab.to}
              end={tab.end}
              className={({ isActive }) =>
                cn(
                  "whitespace-nowrap border-b-2 px-3 py-2 text-sm transition-colors",
                  isActive
                    ? "border-primary font-medium text-foreground"
                    : "border-transparent text-muted-foreground hover:text-foreground",
                )
              }
            >
              {tab.label}
            </NavLink>
          ))}
        </nav>
      </header>
      <div className="flex min-h-0 flex-1 flex-col overflow-y-auto">
        <Suspense fallback={<PageFallback />}>
          <Outlet />
        </Suspense>
      </div>
    </div>
  );
}

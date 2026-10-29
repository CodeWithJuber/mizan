/**
 * The title row of a page, with the mobile menu button and page actions.
 * Inside a section (Agents, Library, Automations) the section already shows
 * the title and the menu button, so `sub` draws only the description and
 * actions.
 */
import type { ReactNode } from "react";
import { SidebarTrigger } from "@/components/ui/sidebar";

interface Props {
  title?: string;
  description?: string;
  actions?: ReactNode;
  sub?: boolean;
}

export function PageHeader({ title, description, actions, sub = false }: Props) {
  if (sub) {
    return (
      <div className="flex shrink-0 flex-wrap items-center gap-3 px-4 pt-4 sm:px-6">
        <div className="min-w-0 flex-1">
          {title && <h2 className="text-base font-semibold">{title}</h2>}
          {description && <p className="text-sm text-muted-foreground">{description}</p>}
        </div>
        {actions && <div className="flex items-center gap-2">{actions}</div>}
      </div>
    );
  }
  return (
    <header className="flex shrink-0 flex-wrap items-center gap-3 border-b px-4 py-3 sm:px-6 sm:py-4">
      <SidebarTrigger className="-ml-1 md:hidden" />
      <div className="min-w-0 flex-1">
        <h1 className="truncate text-lg font-semibold tracking-tight sm:text-xl">{title}</h1>
        {description && <p className="mt-0.5 text-sm text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </header>
  );
}

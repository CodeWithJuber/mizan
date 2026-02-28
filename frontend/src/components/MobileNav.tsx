import { Icons } from "./Icons";

interface MobileNavProps {
  activeTab: string;
  setActiveTab: (tab: string) => void;
}

const MOBILE_TABS = [
  { id: "chat", label: "Chat", icon: <Icons.Chat /> },
  { id: "agents", label: "Agents", icon: <Icons.Agent /> },
  { id: "memory", label: "Memory", icon: <Icons.Memory /> },
  { id: "settings", label: "Settings", icon: <Icons.Settings /> },
];

export function MobileNav({ activeTab, setActiveTab }: MobileNavProps) {
  return (
    <nav
      className="md:hidden fixed bottom-0 left-0 right-0 bg-white/90 dark:bg-mizan-dark/90 backdrop-blur-xl border-t border-gray-200 dark:border-white/10 z-sticky flex items-center justify-around px-2 py-1 safe-area-bottom"
      role="navigation"
      aria-label="Mobile navigation"
    >
      {MOBILE_TABS.map((tab) => {
        const isActive = activeTab === tab.id;
        return (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`flex flex-col items-center gap-0.5 px-3 py-2 rounded-lg min-w-[60px] transition-colors cursor-pointer focus-ring ${
              isActive
                ? "text-mizan-gold"
                : "text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300"
            }`}
            aria-current={isActive ? "page" : undefined}
            aria-label={tab.label}
          >
            <span className={isActive ? "scale-110" : ""}>{tab.icon}</span>
            <span className="text-[10px] font-medium">{tab.label}</span>
            {isActive && (
              <div className="absolute top-0 left-1/2 -translate-x-1/2 w-6 h-0.5 bg-mizan-gold rounded-full" />
            )}
          </button>
        );
      })}
    </nav>
  );
}

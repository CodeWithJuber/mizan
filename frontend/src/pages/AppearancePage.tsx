/** Appearance: light, dark, or follow the device. */
import { Monitor, Moon, Sun } from "lucide-react";
import { cn } from "@/lib/utils";
import { useTheme, type ThemeMode } from "../hooks/useTheme";
import { PageHeader } from "../app/PageHeader";

const MODES: { mode: ThemeMode; label: string; icon: typeof Sun }[] = [
  { mode: "light", label: "Light", icon: Sun },
  { mode: "dark", label: "Dark", icon: Moon },
  { mode: "system", label: "Same as device", icon: Monitor },
];

export default function AppearancePage() {
  const { theme, setTheme } = useTheme();
  return (
    <div className="page-wrapper">
      <PageHeader title="Appearance" description="How MIZAN looks on this device." />
      <div className="page-body">
        <div role="radiogroup" aria-label="Theme" className="grid max-w-xl grid-cols-3 gap-3">
          {MODES.map(({ mode, label, icon: Icon }) => (
            <button
              key={mode}
              type="button"
              role="radio"
              aria-checked={theme === mode}
              onClick={() => setTheme(mode)}
              className={cn(
                "flex flex-col items-center gap-2 rounded-xl border bg-card p-4 text-sm transition-colors hover:bg-muted/50 focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/50",
                theme === mode && "border-primary ring-2 ring-primary/30",
              )}
            >
              <Icon className="size-5 text-brand" />
              {label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

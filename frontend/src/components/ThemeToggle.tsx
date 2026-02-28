import { useTheme } from "../hooks/useTheme";
import { Icons } from "./Icons";

const modes = ["light", "dark", "system"] as const;

export function ThemeToggle() {
  const { theme, setTheme } = useTheme();

  const next = () => {
    const idx = modes.indexOf(theme);
    setTheme(modes[(idx + 1) % modes.length]);
  };

  const icon =
    theme === "light" ? (
      <Icons.Sun />
    ) : theme === "dark" ? (
      <Icons.Moon />
    ) : (
      <Icons.Monitor />
    );

  const label =
    theme === "light" ? "Light" : theme === "dark" ? "Dark" : "System";

  return (
    <button
      onClick={next}
      className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-zinc-800 transition-colors focus-ring cursor-pointer"
      aria-label={`Theme: ${label}. Click to change.`}
      title={`Theme: ${label}. Click to change.`}
    >
      {icon}
      <span className="text-xs hidden sm:inline">{label}</span>
    </button>
  );
}

/**
 * Theme Hook for MIZAN
 * Supports light, dark, and system (auto-detect) modes.
 * Persists choice in localStorage.
 */

import { useState, useEffect, useCallback } from "react";

export type ThemeMode = "light" | "dark" | "system";

export function useTheme() {
  const [theme, setThemeState] = useState<ThemeMode>(() => {
    const stored = localStorage.getItem("mizan_theme");
    if (stored === "light" || stored === "dark" || stored === "system") return stored;
    return "system";
  });

  const [isDark, setIsDark] = useState(() => {
    const stored = localStorage.getItem("mizan_theme");
    if (stored === "dark") return true;
    if (stored === "light") return false;
    return window.matchMedia("(prefers-color-scheme: dark)").matches;
  });

  const applyTheme = useCallback((mode: ThemeMode) => {
    let dark: boolean;
    if (mode === "system") {
      dark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    } else {
      dark = mode === "dark";
    }
    setIsDark(dark);
    if (dark) {
      document.documentElement.classList.add("dark");
    } else {
      document.documentElement.classList.remove("dark");
    }
  }, []);

  const setTheme = useCallback((mode: ThemeMode) => {
    setThemeState(mode);
    localStorage.setItem("mizan_theme", mode);
    applyTheme(mode);
  }, [applyTheme]);

  // Apply on mount
  useEffect(() => {
    applyTheme(theme);
  }, []);

  // Listen for system preference changes
  useEffect(() => {
    if (theme !== "system") return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const handler = (e: MediaQueryListEvent) => {
      setIsDark(e.matches);
      if (e.matches) {
        document.documentElement.classList.add("dark");
      } else {
        document.documentElement.classList.remove("dark");
      }
    };
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, [theme]);

  return { theme, setTheme, isDark };
}

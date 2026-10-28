/**
 * Theme for MIZAN: light, dark, or system (follows the device).
 * One shared store, so every component — editor, preview, toasts — changes
 * together when the person switches theme. Saved in localStorage.
 */

import { useSyncExternalStore } from "react";

export type ThemeMode = "light" | "dark" | "system";

const KEY = "mizan_theme";
const media = () => window.matchMedia("(prefers-color-scheme: dark)");

function readMode(): ThemeMode {
  try {
    const stored = localStorage.getItem(KEY);
    if (stored === "light" || stored === "dark" || stored === "system") return stored;
  } catch {
    // Storage blocked: follow the device.
  }
  return "system";
}

let mode: ThemeMode = readMode();
let dark = mode === "dark" || (mode === "system" && media().matches);
const listeners = new Set<() => void>();

function apply() {
  dark = mode === "dark" || (mode === "system" && media().matches);
  document.documentElement.classList.toggle("dark", dark);
  listeners.forEach((listener) => listener());
}

media().addEventListener("change", () => {
  if (mode === "system") apply();
});
apply();

export function setThemeMode(next: ThemeMode) {
  mode = next;
  try {
    localStorage.setItem(KEY, next);
  } catch {
    // The choice still applies for this visit.
  }
  apply();
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useTheme() {
  const theme = useSyncExternalStore(subscribe, () => mode);
  const isDark = useSyncExternalStore(subscribe, () => dark);
  return { theme, setTheme: setThemeMode, isDark };
}

/** The running log shown on the Tasks page (connection notes, task output). */
import { create } from "zustand";
import type { TerminalLine } from "../types";

interface TerminalState {
  lines: TerminalLine[];
  add: (text: string, type?: string) => void;
  clear: () => void;
}

export const useTerminal = create<TerminalState>((set) => ({
  lines: [
    { text: "MIZAN System Initializing...", type: "" },
    { text: "Connecting to backend...", type: "" },
  ],
  add: (text, type = "") =>
    set((state) => ({
      lines: [...state.lines.slice(-100), { text, type: type as TerminalLine["type"], ts: Date.now() }],
    })),
  clear: () => set({ lines: [] }),
}));

export const addTerminalLine = (text: string, type: string = "") => useTerminal.getState().add(text, type);

/**
 * The text of the reply that is streaming right now. Kept out of React state
 * so a chunk re-renders only the live message, not the page around it.
 */
import { create } from "zustand";

export const useLiveText = create<{ text: string }>(() => ({ text: "" }));

export const setLiveText = (text: string) => useLiveText.setState({ text });

/** What the shell needs about the chat without re-rendering on every change. */
export interface ChatSummary {
  sessionId: string;
  streaming: boolean;
  hasMessages: boolean;
}

export const useChatSummary = create<ChatSummary>(() => ({ sessionId: "", streaming: false, hasMessages: false }));

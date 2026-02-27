/**
 * MIZAN — Main Application
 * Clean, accessible UI with light/dark/system theme support.
 */

import { useState, useEffect, useRef, useCallback, Component } from "react";
import type { ErrorInfo, ReactNode } from "react";
import type { Agent, ChatMessage, TerminalLine, Memory, Integration, SystemStatus } from "./types";
import { config } from "./config";
import { useTheme } from "./hooks/useTheme";
import { useApi } from "./hooks/useApi";
import { ToastProvider, useToast } from "./components/Toast";

// ===== ERROR BOUNDARY =====
interface ErrorBoundaryProps {
  children: ReactNode;
}
interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error("ErrorBoundary caught an error:", error, errorInfo);
  }

  handleRetry = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex-1 flex items-center justify-center p-8 bg-gray-50 dark:bg-zinc-950">
          <div className="max-w-md w-full text-center space-y-6">
            <div className="mx-auto w-16 h-16 rounded-full bg-red-100 dark:bg-red-900/30 flex items-center justify-center">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="w-8 h-8 text-red-600 dark:text-red-400">
                <path d="M12 9v4m0 4h.01M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0z" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </div>
            <div>
              <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Something went wrong</h2>
              <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">
                An unexpected error occurred while rendering this page. You can try again or refresh the browser.
              </p>
              {this.state.error && (
                <p className="mt-3 text-xs font-mono text-gray-400 dark:text-gray-500 bg-gray-100 dark:bg-zinc-900 rounded-lg p-3 text-left break-all">
                  {this.state.error.message}
                </p>
              )}
            </div>
            <button
              onClick={this.handleRetry}
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg text-sm font-medium text-white bg-amber-600 hover:bg-amber-700 dark:bg-amber-500 dark:hover:bg-amber-600 transition-colors shadow-sm"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-4 h-4">
                <path d="M1 4v6h6M23 20v-6h-6" strokeLinecap="round" strokeLinejoin="round"/>
                <path d="M20.49 9A9 9 0 0 0 5.64 5.64L1 10m22 4-4.64 4.36A9 9 0 0 1 3.51 15" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
              Retry
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

import ChannelsPage from "./pages/ChannelsPage";
import SkillsPage from "./pages/SkillsPage";
import SecurityPage from "./pages/SecurityPage";
import AutomationPage from "./pages/AutomationPage";
import NotebookPage from "./pages/NotebookPage";
import ScannerPage from "./pages/ScannerPage";
import MajlisPage from "./pages/MajlisPage";
import PluginsPage from "./pages/PluginsPage";
import ProvidersPage from "./pages/ProvidersPage";
import DeveloperPage from "./pages/DeveloperPage";
import WelcomePage from "./pages/WelcomePage";
import SettingsPage from "./pages/SettingsPage";

// ===== ICONS (inline SVG) =====
const Icons = {
  Agent: () => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="w-5 h-5">
      <circle cx="12" cy="8" r="4"/>
      <path d="M4 20c0-4 3.58-7 8-7s8 3 8 7"/>
      <path d="M20 12h2M2 12h2M12 2v2M12 20v2"/>
    </svg>
  ),
  Brain: () => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="w-5 h-5">
      <path d="M12 5c-2.8 0-5 2.2-5 5 0 1.5.6 2.8 1.5 3.8C7.2 15 6 17 6 19h12c0-2 -1.2-4-2.5-5.2C16.4 12.8 17 11.5 17 10c0-2.8-2.2-5-5-5z"/>
      <path d="M9 10h6M10 13h4"/>
    </svg>
  ),
  Terminal: () => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="w-5 h-5">
      <rect x="3" y="4" width="18" height="16" rx="2"/>
      <path d="M7 9l3 3-3 3M13 15h4"/>
    </svg>
  ),
  Memory: () => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="w-5 h-5">
      <rect x="2" y="7" width="20" height="10" rx="2"/>
      <path d="M7 7V5M12 7V5M17 7V5M7 17v2M12 17v2M17 17v2"/>
      <circle cx="7" cy="12" r="1.5" fill="currentColor"/>
      <circle cx="12" cy="12" r="1.5" fill="currentColor"/>
      <circle cx="17" cy="12" r="1.5" fill="currentColor"/>
    </svg>
  ),
  Chat: () => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="w-5 h-5">
      <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/>
    </svg>
  ),
  Plus: () => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-4 h-4">
      <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
    </svg>
  ),
  Send: () => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-4 h-4">
      <line x1="22" y1="2" x2="11" y2="13"/>
      <polygon points="22 2 15 22 11 13 2 9 22 2"/>
    </svg>
  ),
  Trash: () => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="w-4 h-4">
      <polyline points="3 6 5 6 21 6"/>
      <path d="M19 6l-1 14H6L5 6M10 11v6M14 11v6M9 6V4h6v2"/>
    </svg>
  ),
  Globe: () => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="w-5 h-5">
      <circle cx="12" cy="12" r="10"/>
      <line x1="2" y1="12" x2="22" y2="12"/>
      <path d="M12 2a15.3 15.3 0 014 10 15.3 15.3 0 01-4 10 15.3 15.3 0 01-4-10 15.3 15.3 0 014-10z"/>
    </svg>
  ),
  Zap: () => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="w-5 h-5">
      <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
    </svg>
  ),
  Channel: () => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="w-5 h-5">
      <path d="M4 11a9 9 0 0 1 9 9M4 4a16 16 0 0 1 16 16"/>
      <circle cx="5" cy="19" r="2" fill="currentColor"/>
    </svg>
  ),
  Skill: () => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="w-5 h-5">
      <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>
    </svg>
  ),
  Shield: () => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="w-5 h-5">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
    </svg>
  ),
  Clock: () => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="w-5 h-5">
      <circle cx="12" cy="12" r="10"/>
      <polyline points="12 6 12 12 16 14"/>
    </svg>
  ),
  Notebook: () => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="w-5 h-5">
      <path d="M4 4h16v16H4z"/>
      <path d="M8 4v16M4 8h4M4 12h4M4 16h4"/>
      <path d="M11 8h6M11 12h4"/>
    </svg>
  ),
  Plugin: () => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="w-5 h-5">
      <path d="M12 2v4M12 18v4M2 12h4M18 12h4"/>
      <rect x="8" y="8" width="8" height="8" rx="1"/>
      <path d="M10 8V6a2 2 0 114 0v2M8 14h-2a2 2 0 100 4h2"/>
    </svg>
  ),
  Sun: () => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="w-5 h-5">
      <circle cx="12" cy="12" r="5"/>
      <line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/>
      <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/>
      <line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/>
      <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>
    </svg>
  ),
  Moon: () => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="w-5 h-5">
      <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
    </svg>
  ),
  Monitor: () => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="w-5 h-5">
      <rect x="2" y="3" width="20" height="14" rx="2"/>
      <line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/>
    </svg>
  ),
  Settings: () => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="w-5 h-5">
      <circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
    </svg>
  ),
};

// ===== NAFS LEVELS =====
const NAFS_LEVELS: Record<number, { latin: string; color: string; desc: string }> = {
  1: { latin: "Ammara", color: "#ef4444", desc: "Raw potential" },
  2: { latin: "Lawwama", color: "#f97316", desc: "Self-correcting" },
  3: { latin: "Mulhama", color: "#f59e0b", desc: "Inspired" },
  4: { latin: "Mutmainna", color: "#84cc16", desc: "Tranquil" },
  5: { latin: "Radiya", color: "#10b981", desc: "Content" },
  6: { latin: "Mardiyya", color: "#06b6d4", desc: "Pleasing" },
  7: { latin: "Kamila", color: "#a78bfa", desc: "Perfected" },
};

// ===== AGENT CARD =====
const AgentCard = ({ agent, selected, onClick }: { agent: Agent; selected: boolean; onClick: () => void }) => {
  const nafs = NAFS_LEVELS[agent.nafs_level] || NAFS_LEVELS[1];

  const stateColors: Record<string, string> = {
    resting: "bg-gray-100 dark:bg-zinc-700/30 text-gray-500 dark:text-gray-400",
    thinking: "bg-blue-100 dark:bg-blue-500/15 text-blue-600 dark:text-blue-400",
    acting: "bg-amber-100 dark:bg-amber-500/15 text-amber-600 dark:text-amber-400",
    learning: "bg-emerald-100 dark:bg-emerald-500/15 text-emerald-600 dark:text-emerald-400",
    error: "bg-red-100 dark:bg-red-500/15 text-red-600 dark:text-red-400",
  };

  return (
    <div
      className={`card-hover cursor-pointer ${selected ? "ring-2 ring-mizan-gold/40 border-mizan-gold/30" : ""}`}
      onClick={onClick}
    >
      <div className="flex items-start gap-3 mb-3">
        <div className="w-10 h-10 rounded-full bg-gray-100 dark:bg-zinc-800 border border-gray-200 dark:border-zinc-700 flex items-center justify-center text-mizan-gold font-semibold text-sm shrink-0">
          {agent.name[0]?.toUpperCase() || "A"}
        </div>
        <div className="flex-1 min-w-0">
          <div className="font-semibold text-sm text-gray-900 dark:text-gray-100 truncate">{agent.name}</div>
          <div className="text-xs text-gray-500 dark:text-gray-400 font-mono uppercase tracking-wide">{agent.role}</div>
        </div>
        <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${stateColors[agent.state] || stateColors.resting}`}>
          {agent.state}
        </span>
      </div>

      <div className="flex items-center gap-2 mb-3">
        <span className="text-xs text-gray-500 dark:text-gray-400 min-w-[60px]" title={`Trust tier ${agent.nafs_level}/7`}>
          Level {agent.nafs_level}
        </span>
        <div className="flex-1 h-1.5 bg-gray-200 dark:bg-zinc-700 rounded-full overflow-hidden">
          <div className="h-full rounded-full transition-all" style={{
            width: `${(agent.nafs_level / 7) * 100}%`,
            background: nafs.color,
          }}/>
        </div>
        <span className="text-xs text-gray-400 dark:text-gray-500 italic whitespace-nowrap">{nafs.desc}</span>
      </div>

      <div className="grid grid-cols-3 gap-2">
        {[
          { label: "Tasks", value: agent.total_tasks, color: undefined as boolean | undefined },
          { label: "Success", value: `${(agent.success_rate * 100).toFixed(0)}%`, color: agent.success_rate > 0.7 },
          { label: "Wisdom", value: agent.hikmah_count, color: undefined as boolean | undefined },
        ].map(s => (
          <div key={s.label} className="text-center py-1.5 px-1 bg-gray-50 dark:bg-zinc-800/50 rounded border border-gray-100 dark:border-zinc-700/50">
            <span className={`block font-mono text-sm ${s.color === false ? "text-red-500" : s.color ? "text-emerald-600 dark:text-emerald-400" : "text-gray-900 dark:text-gray-100"}`}>
              {s.value}
            </span>
            <span className="block text-xs text-gray-400 dark:text-gray-500 uppercase tracking-wider">{s.label}</span>
          </div>
        ))}
      </div>

      {(agent.tools || []).length > 0 && (
        <div className="flex flex-wrap gap-1 mt-2">
          {(agent.tools || []).slice(0, 4).map(t => (
            <span key={t} className="text-xs px-1.5 py-0.5 bg-gray-100 dark:bg-zinc-800 border border-gray-200 dark:border-zinc-700 rounded text-gray-500 dark:text-gray-400 font-mono">{t}</span>
          ))}
          {(agent.tools || []).length > 4 && (
            <span className="text-xs px-1.5 py-0.5 bg-gray-100 dark:bg-zinc-800 rounded text-gray-400 font-mono">+{(agent.tools || []).length - 4}</span>
          )}
        </div>
      )}
    </div>
  );
};

// ===== THEME TOGGLE =====
function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const modes = ["light", "dark", "system"] as const;
  const next = () => {
    const idx = modes.indexOf(theme);
    setTheme(modes[(idx + 1) % modes.length]);
  };
  const icon = theme === "light" ? <Icons.Sun /> : theme === "dark" ? <Icons.Moon /> : <Icons.Monitor />;
  const label = theme === "light" ? "Light" : theme === "dark" ? "Dark" : "System";

  return (
    <button
      onClick={next}
      className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-zinc-800 transition-colors"
      title={`Theme: ${label}. Click to change.`}
    >
      {icon}
      <span className="text-xs hidden sm:inline">{label}</span>
    </button>
  );
}

// ===== CONNECTION BANNER =====
function ConnectionBanner({ status, attempts }: { status: string; attempts: number }) {
  if (status === "connected") return null;
  if (status === "connecting" || (status === "reconnecting" && attempts < 5)) return null;

  return (
    <div className="bg-amber-50 dark:bg-amber-500/5 border-b border-amber-200 dark:border-amber-500/20 px-4 py-2.5 flex items-center justify-between gap-3">
      <div className="flex items-center gap-2 text-sm text-amber-800 dark:text-amber-300">
        <svg viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4 shrink-0">
          <path fillRule="evenodd" d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.17 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495zM10 6a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 6zm0 9a1 1 0 100-2 1 1 0 000 2z" clipRule="evenodd"/>
        </svg>
        <span>Cannot connect to backend. Make sure the server is running: <code className="code">mizan serve</code> or <code className="code">make dev</code></span>
      </div>
      <button
        onClick={() => window.location.reload()}
        className="text-xs px-3 py-1 bg-amber-100 dark:bg-amber-500/10 hover:bg-amber-200 dark:hover:bg-amber-500/20 text-amber-800 dark:text-amber-300 rounded transition-colors shrink-0"
      >
        Retry
      </button>
    </div>
  );
}

// ===== SIMPLE MARKDOWN TO HTML =====
function simpleMarkdown(text: string): string {
  let html = text
    // Escape HTML entities first
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    // Code blocks (``` ... ```)
    .replace(/```(\w*)\n([\s\S]*?)```/g, '<pre class="bg-gray-100 dark:bg-zinc-900 rounded p-2 my-2 overflow-x-auto text-xs"><code>$2</code></pre>')
    // Inline code
    .replace(/`([^`]+)`/g, '<code class="bg-gray-100 dark:bg-zinc-900 px-1 rounded text-xs">$1</code>')
    // Bold
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    // Italic
    .replace(/\*(.+?)\*/g, "<em>$1</em>")
    // Headers (only at line start)
    .replace(/^### (.+)$/gm, '<h4 class="font-semibold mt-2">$1</h4>')
    .replace(/^## (.+)$/gm, '<h3 class="font-semibold mt-2 text-base">$1</h3>')
    .replace(/^# (.+)$/gm, '<h2 class="font-bold mt-2 text-lg">$1</h2>')
    // Line breaks
    .replace(/\n/g, "<br/>");
  return html;
}

// ===== MAIN APP INNER =====
function AppInner() {
  const { addToast } = useToast();

  const [showWelcome, setShowWelcome] = useState(() => {
    return !localStorage.getItem("mizan_setup_complete");
  });

  const [activeTab, setActiveTab] = useState("chat");
  const [agents, setAgents] = useState<Agent[]>([]);
  const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [streamingText, setStreamingText] = useState("");
  const [ws, setWs] = useState<WebSocket | null>(null);
  const [wsStatus, setWsStatus] = useState<string>("connecting");
  const [reconnectAttempts, setReconnectAttempts] = useState(0);
  const [terminalLines, setTerminalLines] = useState<TerminalLine[]>([
    { text: "MIZAN System Initializing...", type: "" },
    { text: "Connecting to backend...", type: "" },
  ]);
  const [taskInput, setTaskInput] = useState("");
  const [sessionId] = useState(() => `session_${Date.now()}`);
  const [typingIndicator, setTypingIndicator] = useState(false);
  const [toolStatus, setToolStatus] = useState("");
  const [showCreateAgent, setShowCreateAgent] = useState(false);
  const [memories, setMemories] = useState<Memory[]>([]);
  const [memoryQuery, setMemoryQuery] = useState("");
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [integrations, setIntegrations] = useState<Integration[]>([]);
  const [newAgent, setNewAgent] = useState({ name: "", type: "general", model: "claude-opus-4-6" });
  const [appVersion, setAppVersion] = useState("...");
  const [showCommandMenu, setShowCommandMenu] = useState(false);
  const [commandMenuIndex, setCommandMenuIndex] = useState(0);

  const CHAT_COMMANDS = [
    { name: "/help", description: "Show available commands" },
    { name: "/status", description: "Show system status" },
    { name: "/new", description: "Start a new chat session" },
    { name: "/reset", description: "Reset agent state" },
    { name: "/model", description: "Switch AI model (e.g. /model claude-sonnet-4-6)" },
    { name: "/agents", description: "List available agents" },
    { name: "/compact", description: "Summarize older messages to save context" },
  ];

  const filteredCommands = CHAT_COMMANDS.filter(cmd =>
    input.startsWith("/") && cmd.name.startsWith(input.split(" ")[0].toLowerCase())
  );

  const api = useApi();
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const commandMenuRef = useRef<HTMLDivElement>(null);
  const clientId = useRef(`client_${Date.now()}`);

  const addTerminalLine = useCallback((text: string, type: string = "") => {
    setTerminalLines(prev => [...prev.slice(-100), { text, type: type as TerminalLine["type"], ts: Date.now() }]);
  }, []);

  // Connect WebSocket
  useEffect(() => {
    let socket: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let attempts = 0;

    const connect = () => {
      try {
        if (attempts > 0) {
          setWsStatus("reconnecting");
        }

        socket = new WebSocket(`${config.WS_URL}/${clientId.current}`);

        socket.onopen = () => {
          setWsStatus("connected");
          setWs(socket);
          attempts = 0;
          setReconnectAttempts(0);
          addTerminalLine("Connected to backend", "gold");
        };

        socket.onmessage = (event) => {
          const data = JSON.parse(event.data);
          handleWsMessage(data);
        };

        socket.onclose = () => {
          setWs(null);
          attempts++;
          setReconnectAttempts(attempts);
          if (attempts >= 5) {
            setWsStatus("disconnected");
          } else {
            setWsStatus("reconnecting");
          }
          addTerminalLine("Connection lost. Reconnecting...", "warn");
          const delay = Math.min(3000 * Math.pow(1.5, attempts - 1), 15000);
          reconnectTimer = setTimeout(connect, delay);
        };

        socket.onerror = () => {
          addTerminalLine("Connection error", "error");
        };
      } catch (e: unknown) {
        addTerminalLine(`Connection failed: ${(e as Error).message}`, "error");
        attempts++;
        reconnectTimer = setTimeout(connect, 5000);
      }
    };

    connect();

    return () => {
      if (reconnectTimer) clearTimeout(reconnectTimer);
      if (socket) socket.close();
    };
  }, []);

  const handleWsMessage = useCallback((data: Record<string, unknown>) => {
    switch (data.type) {
      case "connected":
        addTerminalLine(`${data.message} — ${data.agents} agents online`, "gold");
        loadAgents();
        loadStatus();
        break;
      case "stream":
      case "chat_stream":
        setTypingIndicator(false);
        setStreamingText(prev => prev + (data.chunk as string));
        break;
      case "response":
        setStreamingText("");
        setStreaming(false);
        setTypingIndicator(false);
        setToolStatus("");
        setMessages(prev => [...prev, {
          id: Date.now(),
          role: "assistant" as const,
          content: data.content as string,
          agent: data.agent as string,
          ts: new Date().toLocaleTimeString(),
        }]);
        addTerminalLine(`Response from ${data.agent}`, "info");
        break;
      case "chat_complete":
        setStreamingText("");
        setStreaming(false);
        setTypingIndicator(false);
        setToolStatus("");
        setMessages(prev => [...prev, {
          id: Date.now(),
          role: "assistant" as const,
          content: (data.response as string) || (data.content as string) || "",
          agent: data.agent as string,
          ts: new Date().toLocaleTimeString(),
        }]);
        addTerminalLine(`Response from ${data.agent}`, "info");
        break;
      case "typing":
        setTypingIndicator(true);
        break;
      case "tool_use":
        setToolStatus(`Agent is using ${data.tool_name as string}...`);
        addTerminalLine(`Tool: ${data.tool_name as string}`, "info");
        break;
      case "command_result": {
        setStreaming(false);
        setStreamingText("");
        setTypingIndicator(false);
        const cmdContent = (data.content as string) || (data.result as string) || "done";
        setMessages(prev => [...prev, {
          id: Date.now(),
          role: "system" as const,
          content: cmdContent,
          agent: "system",
          ts: new Date().toLocaleTimeString(),
        }]);
        addTerminalLine(`Command: ${cmdContent.substring(0, 60)}`, "gold");
        break;
      }
      case "error":
        setStreaming(false);
        setStreamingText("");
        setTypingIndicator(false);
        setToolStatus("");
        addTerminalLine(`Error: ${data.message as string}`, "error");
        break;
      case "task_stream":
        addTerminalLine(data.chunk as string, "");
        break;
      case "task_done":
        addTerminalLine("Task completed", "gold");
        loadAgents();
        break;
      case "agent_created":
        addTerminalLine(`Agent created: ${(data.agent as Record<string, unknown>).name}`, "gold");
        loadAgents();
        break;
    }
  }, [addTerminalLine]);

  const loadAgents = async () => {
    try {
      const res = await fetch(`${config.API_URL}/agents`);
      const data = await res.json();
      setAgents(data.agents || []);
      if (!selectedAgent && data.agents?.length > 0) {
        setSelectedAgent(data.agents[0]);
      }
    } catch (e: unknown) {
      addTerminalLine(`Failed to load agents: ${(e as Error).message}`, "error");
    }
  };

  const loadStatus = async () => {
    try {
      const res = await fetch(`${config.API_URL}/status`);
      const data = await res.json();
      setStatus(data);
    } catch { /* ignore */ }
  };

  const loadMemories = async (query: string = "") => {
    try {
      const res = await fetch(`${config.API_URL}/memory/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: query || "all", limit: 20 }),
      });
      const data = await res.json();
      setMemories(data.results || []);
    } catch { /* ignore */ }
  };

  const loadIntegrations = async () => {
    try {
      const res = await fetch(`${config.API_URL}/integrations`);
      const data = await res.json();
      setIntegrations(data.integrations || []);
    } catch { /* ignore */ }
  };

  useEffect(() => {
    loadAgents();
    // Fetch version from backend
    fetch(`${config.API_URL}/version`).then(r => r.json()).then(data => {
      if (data.version) setAppVersion(data.version);
    }).catch(() => {});
    const interval = setInterval(() => {
      loadAgents();
      loadStatus();
    }, 5000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (activeTab === "memory") loadMemories(memoryQuery);
    if (activeTab === "integrations") loadIntegrations();
  }, [activeTab]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingText]);

  const sendMessage = async () => {
    if (!input.trim() || streaming) return;
    const content = input;
    const userMsg: ChatMessage = { id: Date.now(), role: "user", content, ts: new Date().toLocaleTimeString() };
    setMessages(prev => [...prev, userMsg]);
    setStreaming(true);
    setStreamingText("");
    setTypingIndicator(true);
    setToolStatus("");
    setInput("");
    addTerminalLine(`> ${content.substring(0, 60)}...`, "info");

    // Prefer HTTP POST /api/chat (returns message_id, streams via WebSocket)
    // Fall back to WebSocket direct send if HTTP fails
    try {
      const res = await fetch(`${config.API_URL}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          content,
          agent_id: selectedAgent?.id,
        }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      // Response processing happens via chat_stream/chat_complete WebSocket events
    } catch {
      // Fallback: send via WebSocket directly
      if (ws) {
        ws.send(JSON.stringify({
          type: "chat",
          session_id: sessionId,
          content,
          agent_id: selectedAgent?.id,
        }));
      } else {
        setStreaming(false);
        setTypingIndicator(false);
        addTerminalLine("Not connected - cannot send message", "error");
      }
    }
  };

  const runTask = () => {
    if (!taskInput.trim() || !ws) return;
    addTerminalLine(`$ ${taskInput}`, "gold");
    ws.send(JSON.stringify({
      type: "task",
      task: taskInput,
      agent_id: selectedAgent?.id,
    }));
    setTaskInput("");
  };

  const createAgent = async () => {
    try {
      const res = await fetch(`${config.API_URL}/agents`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(newAgent),
      });
      await res.json();
      setShowCreateAgent(false);
      setNewAgent({ name: "", type: "general", model: "claude-opus-4-6" });
      loadAgents();
      addToast({ type: "success", title: "Agent created", description: `${newAgent.name} is ready` });
    } catch (e: unknown) {
      addToast({ type: "error", title: "Failed to create agent", description: (e as Error).message });
    }
  };

  const deleteAgent = async (agentId: string) => {
    if (!confirm("Delete this agent?")) return;
    try {
      await fetch(`${config.API_URL}/agents/${agentId}`, { method: "DELETE" });
      if (selectedAgent?.id === agentId) setSelectedAgent(null);
      loadAgents();
      addToast({ type: "success", title: "Agent deleted" });
    } catch { /* ignore */ }
  };

  // ===== WELCOME PAGE =====
  if (showWelcome) {
    return (
      <WelcomePage
        api={api}
        wsStatus={wsStatus}
        onComplete={() => setShowWelcome(false)}
      />
    );
  }

  // ===== NAVIGATION =====
  const navSections = [
    {
      label: "Main",
      items: [
        { id: "chat", label: "Chat", desc: "Talk to your AI", icon: <Icons.Chat /> },
        { id: "agents", label: "Agents", desc: "Your AI team", icon: <Icons.Agent /> },
        { id: "terminal", label: "Tasks", desc: "Run background jobs", icon: <Icons.Terminal /> },
      ],
    },
    {
      label: "Tools",
      items: [
        { id: "memory", label: "Memory", desc: "What your AI remembers", icon: <Icons.Memory /> },
        { id: "notebooks", label: "Notebooks", desc: "Code scratchpad", icon: <Icons.Notebook /> },
        { id: "skills", label: "Skills", desc: "AI abilities", icon: <Icons.Skill /> },
        { id: "plugins", label: "Plugins", desc: "Extend with add-ons", icon: <Icons.Plugin /> },
      ],
    },
    {
      label: "System",
      items: [
        { id: "providers", label: "Providers", desc: "AI model settings", icon: <Icons.Zap /> },
        { id: "channels", label: "Channels", desc: "Telegram, Discord, etc.", icon: <Icons.Channel /> },
        { id: "automation", label: "Automation", desc: "Scheduled tasks", icon: <Icons.Clock /> },
        { id: "security", label: "Security", desc: "Login & permissions", icon: <Icons.Shield /> },
        { id: "settings", label: "Settings", desc: "Configure MIZAN", icon: <Icons.Settings /> },
        { id: "developer", label: "Developer", desc: "Build extensions", icon: <Icons.Brain /> },
      ],
    },
  ];

  // ===== STATUS =====
  const statusDot = wsStatus === "connected"
    ? "bg-emerald-500"
    : wsStatus === "connecting" || wsStatus === "reconnecting"
    ? "bg-amber-500 animate-pulse"
    : "bg-red-500";

  const statusLabel = wsStatus === "connected"
    ? "Online"
    : wsStatus === "connecting"
    ? "Connecting..."
    : wsStatus === "reconnecting"
    ? "Reconnecting..."
    : "Offline";

  // ===== RENDER CONTENT =====
  const renderContent = () => {
    switch (activeTab) {
      case "agents":
        return (
          <div className="flex-1 flex flex-col overflow-hidden">
            <div className="flex items-center justify-between px-5 py-3 border-b border-gray-200 dark:border-zinc-800">
              <div>
                <h2 className="page-title">Agents</h2>
                <p className="page-description">Your AI team — create and manage intelligent agents</p>
              </div>
              <button className="btn-gold flex items-center gap-2" onClick={() => setShowCreateAgent(true)}>
                <Icons.Plus /> New Agent
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-4">
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {agents.map(agent => (
                  <div key={agent.id} className="relative">
                    <AgentCard
                      agent={agent}
                      selected={selectedAgent?.id === agent.id}
                      onClick={() => setSelectedAgent(agent)}
                    />
                    <button
                      className="absolute top-3 right-3 p-1.5 rounded-lg text-gray-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-500/10 transition-colors"
                      onClick={e => { e.stopPropagation(); deleteAgent(agent.id); }}
                      title="Delete agent"
                    >
                      <Icons.Trash />
                    </button>
                  </div>
                ))}
              </div>
              {agents.length === 0 && (
                <div className="flex-1 flex flex-col items-center justify-center py-20 text-gray-400 dark:text-gray-500">
                  <Icons.Agent />
                  <p className="mt-3 font-medium">No agents yet</p>
                  <p className="text-sm mt-1">Create your first agent to get started, or make sure the backend is running.</p>
                </div>
              )}
            </div>
          </div>
        );

      case "chat":
        return (
          <div className="flex-1 flex flex-col overflow-hidden">
            <div className="flex items-center gap-3 px-4 py-3 border-b border-gray-200 dark:border-zinc-800 bg-white dark:bg-zinc-900/50">
              <Icons.Chat />
              <span className="font-semibold text-sm text-gray-900 dark:text-gray-100">Chat</span>
              <select
                className="input text-sm py-1.5 px-3"
                value={selectedAgent?.id || ""}
                onChange={e => {
                  const agent = agents.find(a => a.id === e.target.value);
                  setSelectedAgent(agent || null);
                }}
              >
                <option value="">Select Agent</option>
                {agents.map(a => (
                  <option key={a.id} value={a.id}>{a.name} ({a.role})</option>
                ))}
              </select>
              {selectedAgent && (
                <span className="ml-auto text-xs text-gray-500 dark:text-gray-400">
                  Level {selectedAgent.nafs_level} — {NAFS_LEVELS[selectedAgent.nafs_level]?.latin}
                </span>
              )}
            </div>

            <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
              {messages.length === 0 && !streaming && (
                <div className="flex-1 flex flex-col items-center justify-center py-20 text-gray-400 dark:text-gray-500">
                  <Icons.Chat />
                  <p className="mt-3 font-medium">Start a conversation</p>
                  <p className="text-sm mt-1 text-center max-w-sm">Send a message below. Your AI is ready to help with anything.</p>
                </div>
              )}

              {messages.map(msg => (
                <div key={msg.id} className={`flex gap-3 ${
                  msg.role === "user" ? "flex-row-reverse" :
                  msg.role === "system" ? "justify-center" : ""
                }`}>
                  {msg.role === "system" ? (
                    <div className="max-w-[85%] w-full">
                      <div className="px-4 py-3 rounded-lg text-sm leading-relaxed italic
                        bg-amber-50/60 dark:bg-amber-500/5 border border-amber-200/60 dark:border-amber-500/15
                        text-amber-900 dark:text-amber-200/90"
                        style={{ fontFamily: "'SF Mono', 'Fira Code', 'Cascadia Code', 'Consolas', monospace" }}
                      >
                        <div className="flex items-center gap-2 mb-1.5 not-italic">
                          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="w-3.5 h-3.5 text-amber-500 dark:text-amber-400">
                            <path d="M7 9l3 3-3 3M13 15h4" /><rect x="3" y="4" width="18" height="16" rx="2"/>
                          </svg>
                          <span className="text-xs font-semibold uppercase tracking-wider text-amber-600 dark:text-amber-400">
                            System
                          </span>
                        </div>
                        <div className="whitespace-pre-wrap">{msg.content}</div>
                      </div>
                      <div className="text-xs text-amber-400 dark:text-amber-500/60 mt-1 px-1 font-mono text-center">
                        {msg.ts}
                      </div>
                    </div>
                  ) : (
                    <>
                      <div className={`w-8 h-8 rounded-full shrink-0 flex items-center justify-center text-xs font-medium ${
                        msg.role === "user"
                          ? "bg-blue-100 dark:bg-blue-500/15 text-blue-600 dark:text-blue-400 border border-blue-200 dark:border-blue-500/30"
                          : "bg-gray-100 dark:bg-zinc-800 text-mizan-gold border border-gray-200 dark:border-zinc-700"
                      }`}>
                        {msg.role === "user" ? "You" : (msg.agent?.[0] || "AI")}
                      </div>
                      <div className="max-w-[75%]">
                        {msg.role === "assistant" ? (
                          <div
                            className="px-4 py-2.5 rounded-xl text-sm leading-relaxed bg-white dark:bg-zinc-800 border border-gray-200 dark:border-zinc-700 text-gray-800 dark:text-gray-200 rounded-tl-sm"
                            dangerouslySetInnerHTML={{ __html: simpleMarkdown(msg.content) }}
                          />
                        ) : (
                          <div className="px-4 py-2.5 rounded-xl text-sm leading-relaxed bg-blue-50 dark:bg-blue-500/10 border border-blue-100 dark:border-blue-500/20 text-gray-900 dark:text-gray-100 rounded-tr-sm">
                            {msg.content}
                          </div>
                        )}
                        <div className="text-xs text-gray-400 dark:text-gray-500 mt-1 px-1 font-mono">
                          {msg.role === "assistant" ? msg.agent : "You"} &middot; {msg.ts}
                        </div>
                      </div>
                    </>
                  )}
                </div>
              ))}

              {/* Typing indicator - shown before first token arrives */}
              {streaming && !streamingText && typingIndicator && (
                <div className="flex gap-3">
                  <div className="w-8 h-8 rounded-full shrink-0 flex items-center justify-center text-xs bg-gray-100 dark:bg-zinc-800 text-mizan-gold border border-gray-200 dark:border-zinc-700">
                    {selectedAgent?.name?.[0] || "AI"}
                  </div>
                  <div className="max-w-[75%]">
                    <div className="bg-white dark:bg-zinc-800 border border-gray-200 dark:border-zinc-700 px-4 py-2.5 rounded-xl rounded-tl-sm text-sm leading-relaxed text-gray-400 dark:text-gray-500">
                      <span className="inline-flex gap-1 items-center">
                        <span className="w-1.5 h-1.5 rounded-full bg-gray-400 dark:bg-gray-500 animate-bounce" style={{ animationDelay: "0ms" }}/>
                        <span className="w-1.5 h-1.5 rounded-full bg-gray-400 dark:bg-gray-500 animate-bounce" style={{ animationDelay: "150ms" }}/>
                        <span className="w-1.5 h-1.5 rounded-full bg-gray-400 dark:bg-gray-500 animate-bounce" style={{ animationDelay: "300ms" }}/>
                      </span>
                    </div>
                  </div>
                </div>
              )}

              {/* Tool status indicator */}
              {streaming && toolStatus && (
                <div className="flex gap-3">
                  <div className="w-8 h-8 shrink-0"/>
                  <div className="text-xs text-gray-500 dark:text-gray-400 italic px-1">
                    {toolStatus}
                  </div>
                </div>
              )}

              {/* Streaming text with markdown and blinking cursor */}
              {streaming && streamingText && (
                <div className="flex gap-3">
                  <div className="w-8 h-8 rounded-full shrink-0 flex items-center justify-center text-xs bg-gray-100 dark:bg-zinc-800 text-mizan-gold border border-gray-200 dark:border-zinc-700">
                    {selectedAgent?.name?.[0] || "AI"}
                  </div>
                  <div className="max-w-[75%]">
                    <div className="bg-white dark:bg-zinc-800 border border-gray-200 dark:border-zinc-700 px-4 py-2.5 rounded-xl rounded-tl-sm text-sm leading-relaxed text-gray-800 dark:text-gray-200">
                      <span dangerouslySetInnerHTML={{ __html: simpleMarkdown(streamingText) }}/>
                      <span className="inline-block w-0.5 h-4 bg-mizan-gold ml-0.5 align-middle animate-pulse"/>
                    </div>
                  </div>
                </div>
              )}

              <div ref={messagesEndRef}/>
            </div>

            <div className="relative px-4 py-3 border-t border-gray-200 dark:border-zinc-800 bg-white dark:bg-zinc-900/50">
              {/* Command autocomplete dropdown */}
              {showCommandMenu && filteredCommands.length > 0 && (
                <div
                  ref={commandMenuRef}
                  className="absolute bottom-full left-4 right-4 mb-1 bg-white dark:bg-zinc-800 border border-gray-200 dark:border-zinc-700 rounded-lg shadow-lg overflow-hidden z-50"
                >
                  <div className="px-3 py-1.5 text-xs uppercase tracking-wider font-semibold text-gray-400 dark:text-gray-500 border-b border-gray-100 dark:border-zinc-700">
                    Commands
                  </div>
                  {filteredCommands.map((cmd, i) => (
                    <button
                      key={cmd.name}
                      className={`w-full text-left px-3 py-2 flex items-center gap-3 text-sm transition-colors ${
                        i === commandMenuIndex
                          ? "bg-amber-50 dark:bg-amber-500/10 text-amber-900 dark:text-amber-200"
                          : "text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-zinc-700/50"
                      }`}
                      onMouseEnter={() => setCommandMenuIndex(i)}
                      onClick={() => {
                        setInput(cmd.name + " ");
                        setShowCommandMenu(false);
                        setCommandMenuIndex(0);
                      }}
                    >
                      <span className="font-mono font-semibold text-amber-600 dark:text-amber-400 shrink-0">{cmd.name}</span>
                      <span className="text-gray-500 dark:text-gray-400 text-xs truncate">{cmd.description}</span>
                    </button>
                  ))}
                </div>
              )}
              <div className="flex gap-2 items-end">
                <textarea
                  className="input flex-1 resize-none min-h-[38px] max-h-[120px]"
                  placeholder="Type your message... (/ for commands, Enter to send)"
                  value={input}
                  onChange={e => {
                    const val = e.target.value;
                    setInput(val);
                    if (val.startsWith("/") && !val.includes(" ")) {
                      setShowCommandMenu(true);
                      setCommandMenuIndex(0);
                    } else {
                      setShowCommandMenu(false);
                    }
                  }}
                  onKeyDown={e => {
                    if (showCommandMenu && filteredCommands.length > 0) {
                      if (e.key === "ArrowDown") {
                        e.preventDefault();
                        setCommandMenuIndex(prev => (prev + 1) % filteredCommands.length);
                        return;
                      }
                      if (e.key === "ArrowUp") {
                        e.preventDefault();
                        setCommandMenuIndex(prev => (prev - 1 + filteredCommands.length) % filteredCommands.length);
                        return;
                      }
                      if (e.key === "Tab" || (e.key === "Enter" && !e.shiftKey)) {
                        e.preventDefault();
                        const selected = filteredCommands[commandMenuIndex];
                        if (selected) {
                          setInput(selected.name + " ");
                          setShowCommandMenu(false);
                          setCommandMenuIndex(0);
                        }
                        return;
                      }
                      if (e.key === "Escape") {
                        e.preventDefault();
                        setShowCommandMenu(false);
                        return;
                      }
                    }
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      sendMessage();
                    }
                  }}
                  onBlur={() => {
                    // Delay hiding so clicks on menu items register
                    setTimeout(() => setShowCommandMenu(false), 150);
                  }}
                  rows={1}
                />
                <button
                  className="w-10 h-10 rounded-lg bg-mizan-gold hover:bg-mizan-gold-light text-black flex items-center justify-center shrink-0 transition-colors disabled:opacity-40"
                  onClick={sendMessage}
                  disabled={streaming || !input.trim() || !ws}
                >
                  <Icons.Send />
                </button>
              </div>
            </div>
          </div>
        );

      case "terminal":
        return (
          <div className="flex-1 flex flex-col overflow-hidden p-4 gap-3">
            <div>
              <h2 className="page-title">Task Runner</h2>
              <p className="page-description">Execute tasks through your AI agents</p>
            </div>

            <div className="flex-1 bg-gray-900 dark:bg-black rounded-xl border border-gray-200 dark:border-zinc-800 overflow-hidden flex flex-col">
              <div className="flex items-center gap-2 px-4 py-2.5 bg-gray-800 dark:bg-zinc-900 border-b border-gray-700 dark:border-zinc-800">
                <div className="flex gap-1.5">
                  <div className="w-3 h-3 rounded-full bg-red-500"/>
                  <div className="w-3 h-3 rounded-full bg-amber-500"/>
                  <div className="w-3 h-3 rounded-full bg-emerald-500"/>
                </div>
                <span className="text-xs font-mono text-gray-400 ml-2">mizan ~ %</span>
                <span className="ml-auto text-xs text-gray-500">
                  Agent: {selectedAgent?.name || "None"}
                </span>
              </div>

              <div className="flex-1 overflow-y-auto p-4 font-mono text-xs leading-relaxed text-emerald-400 min-h-[120px] max-h-[400px]">
                {terminalLines.map((line, i) => (
                  <div key={i} className={`mb-0.5 ${
                    line.type === "error" ? "text-red-400" :
                    line.type === "warn" ? "text-amber-400" :
                    line.type === "info" ? "text-blue-400" :
                    line.type === "gold" ? "text-mizan-gold" : "text-emerald-400"
                  }`}>
                    {line.type === "gold" && <span className="text-mizan-gold font-semibold">{"> "}</span>}
                    {line.text}
                  </div>
                ))}
              </div>

              <div className="flex items-center border-t border-gray-700 dark:border-zinc-800 px-2 py-1">
                <span className="text-mizan-gold font-mono text-xs px-2 font-semibold">{">"}</span>
                <input
                  className="flex-1 bg-transparent border-none text-emerald-400 font-mono text-xs outline-none py-2 px-1"
                  placeholder="Enter task for agent... (e.g., 'search for latest AI papers')"
                  value={taskInput}
                  onChange={e => setTaskInput(e.target.value)}
                  onKeyDown={e => e.key === "Enter" && runTask()}
                />
                <button
                  className="text-xs px-3 py-1 bg-mizan-gold/20 hover:bg-mizan-gold/30 text-mizan-gold rounded transition-colors mr-1"
                  onClick={runTask}
                >
                  Run
                </button>
              </div>
            </div>
          </div>
        );

      case "memory":
        return (
          <div className="flex-1 flex flex-col overflow-hidden">
            <div className="flex items-center justify-between px-5 py-3 border-b border-gray-200 dark:border-zinc-800">
              <div>
                <h2 className="page-title">Memory</h2>
                <p className="page-description">What your AI remembers from past interactions</p>
              </div>
              <div className="flex items-center gap-2">
                <input
                  className="input text-sm py-1.5 w-48"
                  placeholder="Search memories..."
                  value={memoryQuery}
                  onChange={e => setMemoryQuery(e.target.value)}
                  onKeyDown={e => e.key === "Enter" && loadMemories(memoryQuery)}
                />
                <button className="btn-secondary text-sm" onClick={() => loadMemories(memoryQuery)}>Search</button>
                <button className="btn-secondary text-sm" onClick={async () => {
                  await fetch(`${config.API_URL}/memory/consolidate`, { method: "POST" });
                  addToast({ type: "success", title: "Memory consolidated" });
                  loadMemories();
                }}>Consolidate</button>
              </div>
            </div>

            <div className="flex-1 overflow-y-auto p-4 space-y-2">
              {memories.length === 0 && (
                <div className="flex flex-col items-center justify-center py-20 text-gray-400 dark:text-gray-500">
                  <Icons.Memory />
                  <p className="mt-3 font-medium">No memories yet</p>
                  <p className="text-sm mt-1">As you chat, your AI will remember important information.</p>
                </div>
              )}
              {memories.map(mem => (
                <div key={mem.id} className="card">
                  <div className="flex items-center gap-2 mb-2">
                    <span className={`badge ${
                      mem.type === "episodic" ? "badge-info" :
                      mem.type === "semantic" ? "badge-warning" : "badge-success"
                    }`}>{mem.type}</span>
                    <span className="text-xs font-mono text-gray-400 dark:text-gray-500">
                      {mem.agent_id ? `Agent: ${mem.agent_id.substring(0, 8)}` : "System"}
                    </span>
                    <span className="ml-auto text-xs text-gray-400 dark:text-gray-500">
                      Importance: {(mem.importance * 100).toFixed(0)}%
                    </span>
                  </div>
                  <div className="text-sm text-gray-700 dark:text-gray-300 leading-relaxed">
                    {typeof mem.content === "string" ? mem.content : JSON.stringify(mem.content)}
                  </div>
                  {(mem.tags?.length ?? 0) > 0 && (
                    <div className="flex flex-wrap gap-1 mt-2">
                      {mem.tags!.map(t => (
                        <span key={t} className="text-xs px-1.5 py-0.5 bg-gray-100 dark:bg-zinc-800 border border-gray-200 dark:border-zinc-700 rounded text-gray-500 dark:text-gray-400 font-mono">{t}</span>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        );

      case "channels":
        return <ChannelsPage api={api} addTerminalLine={addTerminalLine} />;
      case "skills":
        return <SkillsPage api={api} addTerminalLine={addTerminalLine} />;
      case "security":
        return <SecurityPage api={api} addTerminalLine={addTerminalLine} />;
      case "automation":
        return <AutomationPage api={api} addTerminalLine={addTerminalLine} />;
      case "notebooks":
        return <NotebookPage api={api} addTerminalLine={addTerminalLine} />;
      case "scanner":
        return <ScannerPage api={api} addTerminalLine={addTerminalLine} />;
      case "majlis":
        return <MajlisPage api={api} addTerminalLine={addTerminalLine} />;
      case "plugins":
        return <PluginsPage api={api} addTerminalLine={addTerminalLine} />;
      case "providers":
        return <ProvidersPage api={api} addTerminalLine={addTerminalLine} />;
      case "settings":
        return <SettingsPage api={api} />;
      case "developer":
        return <DeveloperPage api={api} />;
      case "integrations":
        return (
          <div className="flex-1 flex flex-col overflow-hidden">
            <div className="flex items-center justify-between px-5 py-3 border-b border-gray-200 dark:border-zinc-800">
              <div>
                <h2 className="page-title">Integrations</h2>
                <p className="page-description">Connect external services and APIs</p>
              </div>
            </div>
            <div className="flex-1 overflow-y-auto p-4 space-y-2">
              {integrations.length === 0 && (
                <div className="flex flex-col items-center justify-center py-20 text-gray-400 dark:text-gray-500">
                  <Icons.Globe />
                  <p className="mt-3 font-medium">No integrations configured</p>
                  <p className="text-sm mt-1">Use the Providers page to connect AI models, or Channels for messaging platforms.</p>
                </div>
              )}
              {integrations.map(int => (
                <div key={int.id} className="card flex items-center gap-3">
                  <span className={`badge ${int.enabled ? "badge-success" : "badge-error"}`}>{int.type}</span>
                  <span className="font-medium text-sm text-gray-900 dark:text-gray-100">{int.name}</span>
                  <span className={`ml-auto text-xs ${int.enabled ? "text-emerald-600 dark:text-emerald-400" : "text-red-500"}`}>
                    {int.enabled ? "Enabled" : "Disabled"}
                  </span>
                  <button
                    className="p-1.5 rounded-lg text-gray-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-500/10 transition-colors"
                    onClick={async () => {
                      await fetch(`${config.API_URL}/integrations/${int.id}`, { method: "DELETE" });
                      loadIntegrations();
                    }}
                  >
                    <Icons.Trash />
                  </button>
                </div>
              ))}
            </div>
          </div>
        );

      default:
        return null;
    }
  };

  return (
    <div className="h-screen flex flex-col overflow-hidden bg-gray-50 dark:bg-zinc-950 text-gray-900 dark:text-gray-100">
      {/* Connection banner */}
      <ConnectionBanner status={wsStatus} attempts={reconnectAttempts} />

      {/* Header */}
      <header className="flex items-center gap-4 px-4 py-2.5 bg-white dark:bg-zinc-900 border-b border-gray-200 dark:border-zinc-800 z-50 shrink-0">
        <div className="flex items-center gap-2.5">
          <div className="text-2xl leading-none select-none text-mizan-gold" style={{ fontFamily: "Georgia, serif" }}>&#1605;&#1610;&#1586;&#1575;&#1606;</div>
          <div className="flex flex-col">
            <span className="text-sm font-semibold text-gray-900 dark:text-gray-100 tracking-wide">MIZAN</span>
            <span className="text-xs text-gray-400 dark:text-gray-500 tracking-widest">v{appVersion}</span>
          </div>
        </div>

        <div className="flex-1" />

        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-gray-100 dark:bg-zinc-800 border border-gray-200 dark:border-zinc-700">
            <div className={`w-2 h-2 rounded-full ${statusDot}`} />
            <span className="text-xs font-mono text-gray-600 dark:text-gray-400">{statusLabel}</span>
          </div>
          {agents.length > 0 && (
            <span className="text-xs text-gray-500 dark:text-gray-400 hidden sm:inline">
              {agents.length} agent{agents.length !== 1 ? "s" : ""}
            </span>
          )}
          <ThemeToggle />
        </div>
      </header>

      {/* Main layout */}
      <div className="flex-1 flex overflow-hidden">
        {/* Sidebar */}
        <nav className="w-56 shrink-0 bg-white dark:bg-zinc-900 border-r border-gray-200 dark:border-zinc-800 flex flex-col overflow-y-auto">
          <div className="flex-1 py-2">
            {navSections.map(section => (
              <div key={section.label} className="px-2 mb-1">
                <div className="text-sm font-semibold uppercase tracking-widest text-gray-400 dark:text-gray-500 px-3 py-2">
                  {section.label}
                </div>
                {section.items.map(item => (
                  <button
                    key={item.id}
                    className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-left transition-colors mb-0.5 ${
                      activeTab === item.id
                        ? "bg-mizan-gold/10 text-mizan-gold border border-mizan-gold/20"
                        : "text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-zinc-800 hover:text-gray-900 dark:hover:text-gray-200 border border-transparent"
                    }`}
                    onClick={() => setActiveTab(item.id)}
                    title={item.desc}
                  >
                    <span className="shrink-0">{item.icon}</span>
                    <span className="text-sm">{item.label}</span>
                  </button>
                ))}
              </div>
            ))}
          </div>

          {selectedAgent && (
            <div className="px-3 py-3 border-t border-gray-200 dark:border-zinc-800">
              <div className="text-sm uppercase tracking-widest text-gray-400 dark:text-gray-500 mb-1.5">Active Agent</div>
              <div className="flex items-center gap-2">
                <div className="w-7 h-7 rounded-full bg-gray-100 dark:bg-zinc-800 border border-gray-200 dark:border-zinc-700 flex items-center justify-center text-mizan-gold text-xs font-semibold">
                  {selectedAgent.name[0]?.toUpperCase()}
                </div>
                <div className="min-w-0">
                  <div className="text-xs font-medium text-gray-900 dark:text-gray-100 truncate">{selectedAgent.name}</div>
                  <div className="text-xs text-gray-400 dark:text-gray-500 font-mono">
                    Level {selectedAgent.nafs_level} — {NAFS_LEVELS[selectedAgent.nafs_level]?.latin}
                  </div>
                </div>
              </div>
            </div>
          )}
        </nav>

        {/* Content */}
        <main className="flex-1 overflow-hidden flex flex-col bg-gray-50 dark:bg-zinc-950">
          <ErrorBoundary>
            {renderContent()}
          </ErrorBoundary>
        </main>
      </div>

      {/* Create Agent Modal */}
      {showCreateAgent && (
        <div className="modal-backdrop" onClick={() => setShowCreateAgent(false)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-5">Create New Agent</h3>

            <div className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-1.5">Agent Name</label>
                <input className="input w-full" placeholder="e.g., Research Assistant, Code Helper..."
                  value={newAgent.name} onChange={e => setNewAgent({...newAgent, name: e.target.value})}/>
              </div>

              <div>
                <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-1.5">Agent Type</label>
                <select className="input w-full" value={newAgent.type}
                  onChange={e => setNewAgent({...newAgent, type: e.target.value})}>
                  <option value="general">General Purpose</option>
                  <option value="browser">Browser / Web Research</option>
                  <option value="research">Deep Research</option>
                  <option value="code">Code Generation</option>
                  <option value="communication">Communication</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-1.5">AI Model</label>
                <select className="input w-full" value={newAgent.model}
                  onChange={e => setNewAgent({...newAgent, model: e.target.value})}>
                  <option value="claude-opus-4-6">Claude Opus 4.6</option>
                  <option value="claude-sonnet-4-6">Claude Sonnet 4.6</option>
                  <option value="claude-haiku-4-5-20251001">Claude Haiku 4.5</option>
                  <option value="gpt-4o">GPT-4o</option>
                  <option value="ollama/llama3">Ollama Llama 3</option>
                </select>
              </div>
            </div>

            <div className="flex justify-end gap-2 mt-6">
              <button className="btn-secondary" onClick={() => setShowCreateAgent(false)}>Cancel</button>
              <button className="btn-gold" onClick={createAgent} disabled={!newAgent.name}>Create Agent</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ===== APP ROOT (with providers) =====
export default function App() {
  return (
    <ToastProvider>
      <AppInner />
    </ToastProvider>
  );
}

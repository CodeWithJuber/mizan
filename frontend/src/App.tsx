/**
 * MIZAN — Main Application
 * Clean, accessible UI with light/dark/system theme support.
 */

import {
  useState,
  useEffect,
  useRef,
  useCallback,
  Component,
  lazy,
  Suspense,
} from "react";
import type { ErrorInfo, ReactNode } from "react";
import type {
  Agent,
  ChatMessage,
  CognitiveMetadata,
  TerminalLine,
  Memory,
  Integration,
  SystemStatus,
} from "./types";
import { config } from "./config";
import { useApi } from "./hooks/useApi";
import { ToastProvider, useToast } from "./components/Toast";
import { Icons } from "./components/Icons";
import { ThemeToggle } from "./components/ThemeToggle";
import { ConnectionBanner } from "./components/ConnectionBanner";
import { AgentCard, NAFS_LEVELS } from "./components/AgentCard";
import {
  ChatMessageContent,
  ChatMessageBubble,
} from "./components/ChatMessage";
import { Sidebar } from "./components/Sidebar";
import { MobileNav } from "./components/MobileNav";
import { AgentModal } from "./components/AgentModal";
import { SkeletonCard } from "./components/Skeleton";

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
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.5"
                className="w-8 h-8 text-red-600 dark:text-red-400"
              >
                <path
                  d="M12 9v4m0 4h.01M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0z"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </div>
            <div>
              <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                Something went wrong
              </h2>
              <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">
                An unexpected error occurred while rendering this page. You can
                try again or refresh the browser.
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
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                className="w-4 h-4"
              >
                <path
                  d="M1 4v6h6M23 20v-6h-6"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
                <path
                  d="M20.49 9A9 9 0 0 0 5.64 5.64L1 10m22 4-4.64 4.36A9 9 0 0 1 3.51 15"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
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

const ChannelsPage = lazy(() => import("./pages/ChannelsPage"));
const SkillsPage = lazy(() => import("./pages/SkillsPage"));
const SecurityPage = lazy(() => import("./pages/SecurityPage"));
const AutomationPage = lazy(() => import("./pages/AutomationPage"));
const NotebookPage = lazy(() => import("./pages/NotebookPage"));
const ScannerPage = lazy(() => import("./pages/ScannerPage"));
const MajlisPage = lazy(() => import("./pages/MajlisPage"));
const PluginsPage = lazy(() => import("./pages/PluginsPage"));
const ProvidersPage = lazy(() => import("./pages/ProvidersPage"));
const DeveloperPage = lazy(() => import("./pages/DeveloperPage"));
const WelcomePage = lazy(() => import("./pages/WelcomePage"));
const SettingsPage = lazy(() => import("./pages/SettingsPage"));

// ===== MAIN APP INNER =====
function AppInner() {
  const { addToast } = useToast();

  const [showWelcome, setShowWelcome] = useState(() => {
    return !localStorage.getItem("mizan_setup_complete");
  });

  const [activeTab, setActiveTabState] = useState(() => {
    return localStorage.getItem("mizan_active_tab") || "chat";
  });
  const setActiveTab = useCallback((tab: string) => {
    setActiveTabState(tab);
    localStorage.setItem("mizan_active_tab", tab);
  }, []);
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
  const [sessionId, setSessionId] = useState(() => {
    return localStorage.getItem("mizan_session_id") || `session_${Date.now()}`;
  });
  const [typingIndicator, setTypingIndicator] = useState(false);
  const [toolStatus, setToolStatus] = useState("");
  const [showCreateAgent, setShowCreateAgent] = useState(false);
  const [memories, setMemories] = useState<Memory[]>([]);
  const [memoryQuery, setMemoryQuery] = useState("");
  const [memoryTypeFilter, setMemoryTypeFilter] = useState("all");
  const [showAddMemory, setShowAddMemory] = useState(false);
  const [newMemory, setNewMemory] = useState({
    content: "",
    memory_type: "semantic",
    importance: 0.7,
    tags: "",
  });
  const [knowledgeUrl, setKnowledgeUrl] = useState("");
  const [knowledgeLoading, setKnowledgeLoading] = useState(false);
  const [knowledgeSources, setKnowledgeSources] = useState<
    { title: string; type: string; chunks: number; last_updated: string }[]
  >([]);
  const [knowledgeResult, setKnowledgeResult] = useState<string | null>(null);
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [integrations, setIntegrations] = useState<Integration[]>([]);
  const [newAgent, setNewAgent] = useState({
    name: "",
    type: "general",
    model: "claude-opus-4-6",
    system_prompt: "",
  });
  const [editingAgent, setEditingAgent] = useState<Agent | null>(null);
  const [appVersion, setAppVersion] = useState("...");
  const [showCommandMenu, setShowCommandMenu] = useState(false);
  const [commandMenuIndex, setCommandMenuIndex] = useState(0);
  const [showAgentPicker, setShowAgentPicker] = useState(false);
  const [chatModelOverride, setChatModelOverride] = useState("");
  const [chatSessions, setChatSessions] = useState<
    {
      session_id: string;
      started_at: string;
      last_message_at: string;
      message_count: number;
      first_message?: string;
    }[]
  >([]);
  const [showSessionHistory, setShowSessionHistory] = useState(false);

  const CHAT_COMMANDS = [
    { name: "/help", description: "Show available commands" },
    { name: "/status", description: "Show system status" },
    { name: "/new", description: "Start a new chat session" },
    { name: "/reset", description: "Reset agent state" },
    {
      name: "/model",
      description: "Switch AI model (e.g. /model claude-sonnet-4-6)",
    },
    { name: "/agents", description: "List available agents" },
    {
      name: "/compact",
      description: "Summarize older messages to save context",
    },
  ];

  const filteredCommands = CHAT_COMMANDS.filter(
    (cmd) =>
      input.startsWith("/") &&
      cmd.name.startsWith(input.split(" ")[0].toLowerCase()),
  );

  const api = useApi();
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const commandMenuRef = useRef<HTMLDivElement>(null);
  const clientId = useRef(`client_${Date.now()}`);

  const addTerminalLine = useCallback((text: string, type: string = "") => {
    setTerminalLines((prev) => [
      ...prev.slice(-100),
      { text, type: type as TerminalLine["type"], ts: Date.now() },
    ]);
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

  const handleWsMessage = useCallback(
    (data: Record<string, unknown>) => {
      switch (data.type) {
        case "connected":
          addTerminalLine(
            `${data.message} — ${data.agents} agents online`,
            "gold",
          );
          loadAgents();
          loadStatus();
          break;
        case "stream":
        case "chat_stream":
          setTypingIndicator(false);
          setStreamingText((prev) => prev + (data.chunk as string));
          break;
        case "response":
          setStreamingText("");
          setStreaming(false);
          setTypingIndicator(false);
          setToolStatus("");
          setMessages((prev) => [
            ...prev,
            {
              id: Date.now(),
              role: "assistant" as const,
              content: data.content as string,
              agent: data.agent as string,
              ts: new Date().toLocaleTimeString(),
            },
          ]);
          addTerminalLine(`Response from ${data.agent}`, "info");
          break;
        case "chat_complete":
          setStreamingText("");
          setStreaming(false);
          setTypingIndicator(false);
          setToolStatus("");
          setMessages((prev) => [
            ...prev,
            {
              id: Date.now(),
              role: "assistant" as const,
              content:
                (data.response as string) || (data.content as string) || "",
              agent: data.agent as string,
              ts: new Date().toLocaleTimeString(),
              cognitive: data.cognitive as CognitiveMetadata | undefined,
            },
          ]);
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
          const cmdContent =
            (data.content as string) || (data.result as string) || "done";
          // Handle /new — clear messages and start fresh session
          if ((data.command as string) === "/new") {
            startNewSession();
          } else {
            setMessages((prev) => [
              ...prev,
              {
                id: Date.now(),
                role: "system" as const,
                content: cmdContent,
                agent: "system",
                ts: new Date().toLocaleTimeString(),
              },
            ]);
          }
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
          addTerminalLine(
            `Agent created: ${(data.agent as Record<string, unknown>).name}`,
            "gold",
          );
          loadAgents();
          break;
      }
    },
    [addTerminalLine],
  );

  const loadAgents = async () => {
    try {
      const res = await fetch(`${config.API_URL}/agents`);
      const data = await res.json();
      setAgents(data.agents || []);
      if (!selectedAgent && data.agents?.length > 0) {
        const savedAgentId = localStorage.getItem("mizan_selected_agent");
        const restored = savedAgentId
          ? data.agents.find((a: Agent) => a.id === savedAgentId)
          : null;
        setSelectedAgent(restored || data.agents[0]);
      }
    } catch (e: unknown) {
      addTerminalLine(
        `Failed to load agents: ${(e as Error).message}`,
        "error",
      );
    }
  };

  const loadStatus = async () => {
    try {
      const res = await fetch(`${config.API_URL}/status`);
      const data = await res.json();
      setStatus(data);
    } catch {
      /* ignore */
    }
  };

  const loadMemories = async (query: string = "", typeFilter?: string) => {
    try {
      let data;
      if (query.trim()) {
        const res = await fetch(`${config.API_URL}/memory/query`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            query,
            limit: 30,
            ...(typeFilter && typeFilter !== "all"
              ? { memory_type: typeFilter }
              : {}),
          }),
        });
        data = await res.json();
      } else {
        const params = new URLSearchParams({ limit: "30" });
        if (typeFilter && typeFilter !== "all") {
          params.set("memory_type", typeFilter);
        }
        const res = await fetch(
          `${config.API_URL}/memory/list?${params.toString()}`,
        );
        data = await res.json();
      }
      setMemories(data.results || []);
    } catch {
      /* ignore */
    }
  };

  const loadKnowledgeSources = async () => {
    try {
      const res = await fetch(`${config.API_URL}/knowledge/sources`);
      const data = await res.json();
      setKnowledgeSources(data.sources || []);
    } catch {
      /* ignore */
    }
  };

  const ingestKnowledge = async () => {
    if (!knowledgeUrl.trim()) return;
    setKnowledgeLoading(true);
    setKnowledgeResult(null);
    try {
      const res = await fetch(`${config.API_URL}/knowledge/ingest`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source: knowledgeUrl.trim() }),
      });
      const data = await res.json();
      if (res.ok) {
        setKnowledgeResult(
          `Ingested "${data.title}" — ${data.chunks_stored} chunks stored (${data.char_count?.toLocaleString()} chars)`,
        );
        setKnowledgeUrl("");
        loadKnowledgeSources();
      } else {
        setKnowledgeResult(`Error: ${data.detail || "Failed to ingest"}`);
      }
    } catch (err) {
      setKnowledgeResult(
        `Error: ${err instanceof Error ? err.message : "Network error"}`,
      );
    } finally {
      setKnowledgeLoading(false);
    }
  };

  const uploadKnowledgePdf = async (file: File) => {
    setKnowledgeLoading(true);
    setKnowledgeResult(null);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const res = await fetch(`${config.API_URL}/knowledge/upload`, {
        method: "POST",
        body: formData,
      });
      const data = await res.json();
      if (res.ok) {
        setKnowledgeResult(
          `Uploaded "${data.title}" — ${data.page_count} pages, ${data.chunks_stored} chunks stored`,
        );
        loadKnowledgeSources();
      } else {
        setKnowledgeResult(`Error: ${data.detail || "Upload failed"}`);
      }
    } catch (err) {
      setKnowledgeResult(
        `Error: ${err instanceof Error ? err.message : "Network error"}`,
      );
    } finally {
      setKnowledgeLoading(false);
    }
  };

  const loadIntegrations = async () => {
    try {
      const res = await fetch(`${config.API_URL}/integrations`);
      const data = await res.json();
      setIntegrations(data.integrations || []);
    } catch {
      /* ignore */
    }
  };

  const loadChatHistory = useCallback(async (sid: string) => {
    try {
      const res = await fetch(`${config.API_URL}/chat/${sid}`);
      if (!res.ok) return;
      const data = await res.json();
      const history = (data.messages || []).map(
        (
          m: {
            id?: number;
            role: string;
            content: string;
            agent_id?: string;
            created_at?: string;
          },
          idx: number,
        ) => ({
          id: m.id || idx,
          role: m.role as "user" | "assistant" | "system",
          content: m.content,
          agent: m.agent_id,
          ts: m.created_at ? new Date(m.created_at).toLocaleTimeString() : "",
        }),
      );
      if (history.length > 0) {
        setMessages(history);
      }
    } catch {
      // No history available — start fresh
    }
  }, []);

  const loadChatSessions = useCallback(async () => {
    try {
      const res = await fetch(`${config.API_URL}/chat/sessions/list`);
      if (!res.ok) return;
      const data = await res.json();
      setChatSessions(data.sessions || []);
    } catch {
      // ignore
    }
  }, []);

  const switchSession = useCallback(
    async (sid: string) => {
      setSessionId(sid);
      setMessages([]);
      setShowSessionHistory(false);
      await loadChatHistory(sid);
    },
    [loadChatHistory],
  );

  useEffect(() => {
    loadAgents();
    loadChatHistory(sessionId);
    loadChatSessions();
    // Fetch version from backend
    fetch(`${config.API_URL}/version`)
      .then((r) => r.json())
      .then((data) => {
        if (data.version) setAppVersion(data.version);
      })
      .catch(() => {});
    const interval = setInterval(() => {
      loadAgents();
      loadStatus();
    }, 5000);
    return () => clearInterval(interval);
  }, []);

  // Persist sessionId to localStorage
  useEffect(() => {
    localStorage.setItem("mizan_session_id", sessionId);
  }, [sessionId]);

  // Persist selected agent ID
  useEffect(() => {
    if (selectedAgent) {
      localStorage.setItem("mizan_selected_agent", selectedAgent.id);
    }
  }, [selectedAgent]);

  useEffect(() => {
    if (activeTab === "memory") loadMemories(memoryQuery, memoryTypeFilter);
    if (activeTab === "knowledge") loadKnowledgeSources();
    if (activeTab === "integrations") loadIntegrations();
  }, [activeTab]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingText]);

  const startNewSession = useCallback(() => {
    const newId = `session_${Date.now()}`;
    setSessionId(newId);
    setMessages([]);
    setStreamingText("");
    addTerminalLine("New chat session started", "gold");
  }, []);

  const sendMessage = async () => {
    if (!input.trim() || streaming) return;
    const content = input;
    const userMsg: ChatMessage = {
      id: Date.now(),
      role: "user",
      content,
      ts: new Date().toLocaleTimeString(),
    };
    setMessages((prev) => [...prev, userMsg]);
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
          ...(chatModelOverride ? { model_override: chatModelOverride } : {}),
        }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      if (chatModelOverride) setChatModelOverride("");
    } catch {
      // Fallback: send via WebSocket directly
      if (ws) {
        ws.send(
          JSON.stringify({
            type: "chat",
            session_id: sessionId,
            content,
            agent_id: selectedAgent?.id,
          }),
        );
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
    ws.send(
      JSON.stringify({
        type: "task",
        task: taskInput,
        agent_id: selectedAgent?.id,
      }),
    );
    setTaskInput("");
  };

  const createAgent = async () => {
    try {
      const payload = {
        ...newAgent,
        system_prompt: newAgent.system_prompt || undefined,
      };
      await api.post("/agents", payload);
      setShowCreateAgent(false);
      setNewAgent({
        name: "",
        type: "general",
        model: "claude-opus-4-6",
        system_prompt: "",
      });
      loadAgents();
      addToast({
        type: "success",
        title: "Agent created",
        description: `${newAgent.name} is ready`,
      });
    } catch (e: unknown) {
      addToast({
        type: "error",
        title: "Failed to create agent",
        description: (e as Error).message,
      });
    }
  };

  const updateAgent = async () => {
    if (!editingAgent) return;
    try {
      const payload: Record<string, unknown> = {};
      if (newAgent.name !== editingAgent.name) payload.name = newAgent.name;
      if (newAgent.model !== (editingAgent.model || ""))
        payload.model = newAgent.model;
      if (newAgent.system_prompt !== (editingAgent.system_prompt || ""))
        payload.system_prompt = newAgent.system_prompt;

      await api.put(`/agents/${editingAgent.id}`, payload);
      setShowCreateAgent(false);
      setEditingAgent(null);
      setNewAgent({
        name: "",
        type: "general",
        model: "claude-opus-4-6",
        system_prompt: "",
      });
      loadAgents();
      addToast({ type: "success", title: "Agent updated" });
    } catch (e: unknown) {
      addToast({
        type: "error",
        title: "Failed to update agent",
        description: (e as Error).message,
      });
    }
  };

  const openEditAgent = (agent: Agent) => {
    setEditingAgent(agent);
    setNewAgent({
      name: agent.name,
      type: agent.role,
      model: agent.model || "claude-opus-4-6",
      system_prompt: agent.system_prompt || "",
    });
    setShowCreateAgent(true);
  };

  const deleteAgent = async (agentId: string) => {
    if (!confirm("Delete this agent?")) return;
    try {
      await fetch(`${config.API_URL}/agents/${agentId}`, { method: "DELETE" });
      if (selectedAgent?.id === agentId) setSelectedAgent(null);
      loadAgents();
      addToast({ type: "success", title: "Agent deleted" });
    } catch {
      /* ignore */
    }
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
        {
          id: "chat",
          label: "Chat",
          desc: "Talk to your AI",
          icon: <Icons.Chat />,
        },
        {
          id: "agents",
          label: "Agents",
          desc: "Your AI team",
          icon: <Icons.Agent />,
        },
        {
          id: "terminal",
          label: "Tasks",
          desc: "Run background jobs",
          icon: <Icons.Terminal />,
        },
      ],
    },
    {
      label: "Tools",
      items: [
        {
          id: "memory",
          label: "Memory",
          desc: "What your AI remembers",
          icon: <Icons.Memory />,
        },
        {
          id: "knowledge",
          label: "Knowledge",
          desc: "Feed URLs, PDFs, YouTube",
          icon: <Icons.Book />,
        },
        {
          id: "notebooks",
          label: "Notebooks",
          desc: "Code scratchpad",
          icon: <Icons.Notebook />,
        },
        {
          id: "skills",
          label: "Skills",
          desc: "AI abilities",
          icon: <Icons.Skill />,
        },
        {
          id: "plugins",
          label: "Plugins",
          desc: "Extend with add-ons",
          icon: <Icons.Plugin />,
        },
      ],
    },
    {
      label: "System",
      items: [
        {
          id: "providers",
          label: "Providers",
          desc: "AI model settings",
          icon: <Icons.Zap />,
        },
        {
          id: "channels",
          label: "Channels",
          desc: "Telegram, Discord, etc.",
          icon: <Icons.Channel />,
        },
        {
          id: "automation",
          label: "Automation",
          desc: "Scheduled tasks",
          icon: <Icons.Clock />,
        },
        {
          id: "security",
          label: "Security",
          desc: "Login & permissions",
          icon: <Icons.Shield />,
        },
        {
          id: "settings",
          label: "Settings",
          desc: "Configure MIZAN",
          icon: <Icons.Settings />,
        },
        {
          id: "developer",
          label: "Developer",
          desc: "Build extensions",
          icon: <Icons.Brain />,
        },
      ],
    },
  ];

  // ===== STATUS =====
  const statusDot =
    wsStatus === "connected"
      ? "bg-emerald-500"
      : wsStatus === "connecting" || wsStatus === "reconnecting"
        ? "bg-amber-500 animate-pulse"
        : "bg-red-500";

  const statusLabel =
    wsStatus === "connected"
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
          <div className="flex-1 flex flex-col overflow-hidden relative">
            <div className="flex items-center justify-between px-6 py-4 border-b border-white/50 dark:border-white/5 bg-white/50 dark:bg-mizan-dark-surface/30 backdrop-blur-md z-10">
              <div>
                <h2 className="page-title">Agents</h2>
                <p className="page-description">
                  Your AI team — create and manage intelligent agents
                </p>
              </div>
              <button
                className="btn-gold flex items-center gap-2"
                onClick={() => {
                  setEditingAgent(null);
                  setNewAgent({
                    name: "",
                    type: "general",
                    model: "claude-opus-4-6",
                    system_prompt: "",
                  });
                  setShowCreateAgent(true);
                }}
              >
                <Icons.Plus /> New Agent
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-6">
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
                {agents.map((agent) => (
                  <div key={agent.id} className="relative">
                    <AgentCard
                      agent={agent}
                      selected={selectedAgent?.id === agent.id}
                      onClick={() => setSelectedAgent(agent)}
                    />
                    <div className="absolute top-3 right-3 flex items-center gap-1">
                      <button
                        className="p-1.5 rounded-lg text-gray-400 hover:text-mizan-gold hover:bg-mizan-gold/10 transition-colors"
                        onClick={(e) => {
                          e.stopPropagation();
                          openEditAgent(agent);
                        }}
                        title="Edit agent"
                      >
                        <Icons.Settings />
                      </button>
                      <button
                        className="p-1.5 rounded-lg text-gray-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-500/10 transition-colors"
                        onClick={(e) => {
                          e.stopPropagation();
                          deleteAgent(agent.id);
                        }}
                        title="Delete agent"
                      >
                        <Icons.Trash />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
              {agents.length === 0 && (
                <div className="flex-1 flex flex-col items-center justify-center py-20 text-gray-400 dark:text-gray-500">
                  <Icons.Agent />
                  <p className="mt-3 font-medium">No agents yet</p>
                  <p className="text-sm mt-1">
                    Create your first agent to get started, or make sure the
                    backend is running.
                  </p>
                </div>
              )}
            </div>
          </div>
        );

      case "chat":
        return (
          <div className="flex-1 flex flex-col overflow-hidden relative">
            <div className="flex items-center gap-3 px-6 py-3.5 border-b border-white/50 dark:border-white/5 bg-white/60 dark:bg-mizan-dark-surface/40 backdrop-blur-md z-10 shadow-sm transition-all duration-300">
              <Icons.Chat />
              <span className="font-semibold text-sm text-gray-900 dark:text-gray-100">
                Chat
              </span>

              {/* Agent picker pill */}
              <div className="relative">
                <button
                  className={`flex items-center gap-2 px-3 py-1.5 rounded-xl border backdrop-blur-md shadow-sm transition-all duration-300 ${
                    showAgentPicker
                      ? "bg-mizan-gold/10 border-mizan-gold/30 text-mizan-gold shadow-md"
                      : "bg-white/60 dark:bg-mizan-dark-surface/40 border-white/50 dark:border-white/10 hover:border-mizan-gold/40 hover:shadow-md hover:-translate-y-0.5"
                  }`}
                  onClick={() => setShowAgentPicker(!showAgentPicker)}
                >
                  <div className="w-6 h-6 rounded-full bg-mizan-gold/10 border border-mizan-gold/30 flex items-center justify-center text-xs text-mizan-gold font-semibold">
                    {selectedAgent?.name?.[0]?.toUpperCase() || "?"}
                  </div>
                  <span className="text-sm font-medium text-gray-900 dark:text-gray-100">
                    {selectedAgent?.name || "Select Agent"}
                  </span>
                  <span className="text-xs text-gray-400 dark:text-gray-500">
                    {selectedAgent?.role || ""}
                  </span>
                  <svg
                    viewBox="0 0 20 20"
                    fill="currentColor"
                    className="w-3.5 h-3.5 text-gray-400"
                  >
                    <path
                      fillRule="evenodd"
                      d="M5.23 7.21a.75.75 0 011.06.02L10 11.168l3.71-3.938a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z"
                      clipRule="evenodd"
                    />
                  </svg>
                </button>

                {/* Agent picker dropdown */}
                {showAgentPicker && (
                  <div className="absolute top-full left-0 mt-2 w-72 bg-white/90 dark:bg-mizan-dark-surface/90 backdrop-blur-xl border border-white/50 dark:border-white/10 rounded-2xl shadow-xl overflow-hidden z-50 animate-fade-in-up">
                    {agents.map((agent) => {
                      const roleLabels: Record<string, string> = {
                        general: "General Purpose",
                        hafiz: "General Purpose",
                        wakil: "General Purpose",
                        browser: "Web Browsing",
                        mubashir: "Web Browsing",
                        research: "Deep Research",
                        mundhir: "Deep Research",
                        code: "Code Generation",
                        katib: "Code Generation",
                        communication: "Communication",
                        rasul: "Communication",
                      };
                      return (
                        <button
                          key={agent.id}
                          className={`w-full flex items-center gap-3 px-3 py-2.5 text-left transition-colors ${
                            selectedAgent?.id === agent.id
                              ? "bg-mizan-gold/10 text-mizan-gold"
                              : "text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-zinc-700/50"
                          }`}
                          onClick={() => {
                            setSelectedAgent(agent);
                            setShowAgentPicker(false);
                          }}
                        >
                          <div className="w-7 h-7 rounded-full bg-gray-100 dark:bg-zinc-700 border border-gray-200 dark:border-zinc-600 flex items-center justify-center text-xs font-semibold text-mizan-gold shrink-0">
                            {agent.name[0]?.toUpperCase()}
                          </div>
                          <div className="min-w-0 flex-1">
                            <div className="text-sm font-medium truncate">
                              {agent.name}
                            </div>
                            <div className="text-xs text-gray-400 dark:text-gray-500">
                              {roleLabels[agent.role] || agent.role}
                            </div>
                          </div>
                          {selectedAgent?.id === agent.id && (
                            <span className="text-xs text-mizan-gold font-mono">
                              ACTIVE
                            </span>
                          )}
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>

              <div className="ml-auto flex items-center gap-2">
                {selectedAgent && (
                  <span className="text-xs text-gray-500 dark:text-gray-400 hidden sm:inline">
                    Level {selectedAgent.nafs_level} —{" "}
                    {NAFS_LEVELS[selectedAgent.nafs_level]?.latin}
                  </span>
                )}

                {/* Session history dropdown */}
                <div className="relative">
                  <button
                    className="p-1.5 rounded-md text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-zinc-800 transition-colors"
                    onClick={() => {
                      setShowSessionHistory(!showSessionHistory);
                      if (!showSessionHistory) loadChatSessions();
                    }}
                    title="Chat history"
                  >
                    <svg
                      viewBox="0 0 20 20"
                      fill="currentColor"
                      className="w-4 h-4"
                    >
                      <path
                        fillRule="evenodd"
                        d="M10 18a8 8 0 100-16 8 8 0 000 16zm.75-13a.75.75 0 00-1.5 0v5c0 .414.336.75.75.75h4a.75.75 0 000-1.5h-3.25V5z"
                        clipRule="evenodd"
                      />
                    </svg>
                  </button>
                  {showSessionHistory && (
                    <div className="absolute top-full right-0 mt-2 w-80 bg-white/90 dark:bg-mizan-dark-surface/90 backdrop-blur-xl border border-white/50 dark:border-white/10 rounded-2xl shadow-xl overflow-hidden z-50 animate-fade-in-up">
                      <div className="px-4 py-3 border-b border-white/50 dark:border-white/10 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-widest bg-gray-50/50 dark:bg-mizan-dark/50">
                        Recent Sessions
                      </div>
                      <div className="max-h-64 overflow-y-auto">
                        {chatSessions.length === 0 && (
                          <div className="px-3 py-4 text-center text-xs text-gray-400">
                            No previous sessions
                          </div>
                        )}
                        {chatSessions.map((s) => (
                          <button
                            key={s.session_id}
                            className={`w-full flex items-center gap-2 px-3 py-2 text-left transition-colors ${
                              sessionId === s.session_id
                                ? "bg-mizan-gold/10 text-mizan-gold"
                                : "text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-zinc-700/50"
                            }`}
                            onClick={() => switchSession(s.session_id)}
                          >
                            <div className="min-w-0 flex-1">
                              <div className="text-xs font-medium truncate">
                                {s.first_message ||
                                  s.session_id.slice(0, 24) + "..."}
                              </div>
                              <div className="text-micro text-gray-400 dark:text-gray-500">
                                {s.message_count} msgs
                                {s.last_message_at &&
                                  ` · ${new Date(s.last_message_at).toLocaleDateString()}`}
                              </div>
                            </div>
                            {sessionId === s.session_id && (
                              <span className="text-micro text-mizan-gold font-mono shrink-0">
                                CURRENT
                              </span>
                            )}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                </div>

                {/* New chat button */}
                <button
                  className="flex items-center gap-1 px-2.5 py-1.5 rounded-md text-xs font-medium text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-zinc-800 border border-gray-200 dark:border-zinc-700 transition-colors"
                  onClick={startNewSession}
                  title="New chat"
                >
                  <svg
                    viewBox="0 0 20 20"
                    fill="currentColor"
                    className="w-3.5 h-3.5"
                  >
                    <path d="M10.75 4.75a.75.75 0 00-1.5 0v4.5h-4.5a.75.75 0 000 1.5h4.5v4.5a.75.75 0 001.5 0v-4.5h4.5a.75.75 0 000-1.5h-4.5v-4.5z" />
                  </svg>
                  New
                </button>
              </div>
            </div>

            <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
              {messages.length === 0 && !streaming && (
                <div className="flex-1 flex flex-col items-center justify-center py-12 gap-8">
                  <div className="text-center space-y-3">
                    <div
                      className="text-5xl text-mizan-gold/30 select-none"
                      style={{ fontFamily: "Amiri, Georgia, serif" }}
                    >
                      &#1605;&#1610;&#1586;&#1575;&#1606;
                    </div>
                    <h2 className="text-xl font-display font-semibold text-gray-900 dark:text-gray-100">
                      How can I help?
                    </h2>
                    <p className="text-sm text-gray-500 dark:text-gray-400 max-w-md">
                      Start a conversation, ask a question, or try one of these
                      suggestions.
                    </p>
                  </div>
                  <div className="grid grid-cols-2 gap-3 max-w-lg w-full px-4">
                    {[
                      {
                        label: "Write code",
                        desc: "Generate, debug, or refactor",
                        prompt: "Help me write a Python script that ",
                      },
                      {
                        label: "Analyze data",
                        desc: "Explore patterns and insights",
                        prompt: "Analyze this data and help me understand ",
                      },
                      {
                        label: "Research topic",
                        desc: "Deep dive into any subject",
                        prompt: "Research and summarize the key points about ",
                      },
                      {
                        label: "Brainstorm ideas",
                        desc: "Creative thinking together",
                        prompt: "Help me brainstorm ideas for ",
                      },
                    ].map((action) => (
                      <button
                        key={action.label}
                        className="card-hover text-left p-4 group cursor-pointer"
                        onClick={() => {
                          setInput(action.prompt);
                        }}
                      >
                        <div className="text-sm font-medium text-gray-900 dark:text-gray-100 group-hover:text-mizan-gold transition-colors">
                          {action.label}
                        </div>
                        <div className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
                          {action.desc}
                        </div>
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {messages.map((msg) => (
                <div
                  key={msg.id}
                  className={`flex gap-4 ${
                    msg.role === "user"
                      ? "flex-row-reverse"
                      : msg.role === "system"
                        ? "justify-center"
                        : ""
                  } animate-fade-in`}
                >
                  {msg.role === "system" ? (
                    <div className="max-w-[85%] w-full">
                      <div
                        className="px-4 py-3 rounded-lg text-sm leading-relaxed italic
                        bg-amber-50/60 dark:bg-amber-500/5 border border-amber-200/60 dark:border-amber-500/15
                        text-amber-900 dark:text-amber-200/90"
                        style={{
                          fontFamily:
                            "'SF Mono', 'Fira Code', 'Cascadia Code', 'Consolas', monospace",
                        }}
                      >
                        <div className="flex items-center gap-2 mb-1.5 not-italic">
                          <svg
                            viewBox="0 0 24 24"
                            fill="none"
                            stroke="currentColor"
                            strokeWidth="1.5"
                            className="w-3.5 h-3.5 text-amber-500 dark:text-amber-400"
                          >
                            <path d="M7 9l3 3-3 3M13 15h4" />
                            <rect x="3" y="4" width="18" height="16" rx="2" />
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
                      <div
                        className={`w-8 h-8 rounded-full shrink-0 flex items-center justify-center text-xs font-medium ${
                          msg.role === "user"
                            ? "bg-blue-100 dark:bg-blue-500/15 text-blue-600 dark:text-blue-400 border border-blue-200 dark:border-blue-500/30"
                            : "bg-gray-100 dark:bg-zinc-800 text-mizan-gold border border-gray-200 dark:border-zinc-700"
                        }`}
                      >
                        {msg.role === "user" ? "You" : msg.agent?.[0] || "AI"}
                      </div>
                      <div
                        className={
                          msg.role === "assistant"
                            ? "max-w-[85%]"
                            : "max-w-[75%]"
                        }
                      >
                        {msg.role === "assistant" ? (
                          <div className="prose px-5 py-3.5 rounded-2xl text-sm leading-relaxed bg-white/80 dark:bg-mizan-dark-surface/80 backdrop-blur-md border border-white/50 dark:border-white/5 text-gray-800 dark:text-gray-200 rounded-tl-sm shadow-sm transition-all hover:shadow-md">
                            <ChatMessageContent content={msg.content} />
                          </div>
                        ) : (
                          <div className="px-5 py-3.5 rounded-2xl text-sm leading-relaxed bg-gradient-to-br from-blue-500 to-blue-600 border border-blue-400/50 text-white rounded-tr-sm shadow-md">
                            {msg.content}
                          </div>
                        )}
                        <div className="text-xs text-gray-400 dark:text-gray-500 mt-1 px-1 font-mono">
                          {msg.role === "assistant" ? msg.agent : "You"}{" "}
                          &middot; {msg.ts}
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
                        <span
                          className="w-1.5 h-1.5 rounded-full bg-gray-400 dark:bg-gray-500 animate-bounce"
                          style={{ animationDelay: "0ms" }}
                        />
                        <span
                          className="w-1.5 h-1.5 rounded-full bg-gray-400 dark:bg-gray-500 animate-bounce"
                          style={{ animationDelay: "150ms" }}
                        />
                        <span
                          className="w-1.5 h-1.5 rounded-full bg-gray-400 dark:bg-gray-500 animate-bounce"
                          style={{ animationDelay: "300ms" }}
                        />
                      </span>
                    </div>
                  </div>
                </div>
              )}

              {/* Tool status indicator */}
              {streaming && toolStatus && (
                <div className="flex gap-3 items-center">
                  <div className="w-8 h-8 shrink-0" />
                  <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-blue-50 dark:bg-blue-500/10 border border-blue-200/60 dark:border-blue-500/20 animate-pulse">
                    <svg
                      className="w-3.5 h-3.5 text-blue-500 animate-spin"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                    >
                      <path d="M12 2v4m0 12v4m-7.07-3.93l2.83-2.83m8.48-8.48l2.83-2.83M2 12h4m12 0h4m-3.93 7.07l-2.83-2.83M7.76 7.76L4.93 4.93" />
                    </svg>
                    <span className="text-xs font-medium text-blue-600 dark:text-blue-400">
                      {toolStatus}
                    </span>
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
                      <ChatMessageContent content={streamingText} />
                      <span className="inline-block w-0.5 h-4 bg-mizan-gold ml-0.5 align-middle animate-pulse" />
                    </div>
                  </div>
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>

            <div className="relative px-6 py-4 border-t border-white/50 dark:border-white/5 bg-white/70 dark:bg-mizan-dark-surface/60 backdrop-blur-xl shadow-[0_-4px_24px_rgba(0,0,0,0.02)] z-dropdown transition-all duration-200 focus-within:shadow-[0_-4px_24px_rgba(212,175,55,0.08)]">
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
                      <span className="font-mono font-semibold text-amber-600 dark:text-amber-400 shrink-0">
                        {cmd.name}
                      </span>
                      <span className="text-gray-500 dark:text-gray-400 text-xs truncate">
                        {cmd.description}
                      </span>
                    </button>
                  ))}
                </div>
              )}
              <div className="flex gap-2 items-end">
                <textarea
                  className="input flex-1 resize-none min-h-[38px] max-h-[120px]"
                  placeholder="Type your message... (/ for commands, Enter to send)"
                  value={input}
                  onChange={(e) => {
                    const val = e.target.value;
                    setInput(val);
                    if (val.startsWith("/") && !val.includes(" ")) {
                      setShowCommandMenu(true);
                      setCommandMenuIndex(0);
                    } else {
                      setShowCommandMenu(false);
                    }
                  }}
                  onKeyDown={(e) => {
                    if (showCommandMenu && filteredCommands.length > 0) {
                      if (e.key === "ArrowDown") {
                        e.preventDefault();
                        setCommandMenuIndex(
                          (prev) => (prev + 1) % filteredCommands.length,
                        );
                        return;
                      }
                      if (e.key === "ArrowUp") {
                        e.preventDefault();
                        setCommandMenuIndex(
                          (prev) =>
                            (prev - 1 + filteredCommands.length) %
                            filteredCommands.length,
                        );
                        return;
                      }
                      if (
                        e.key === "Tab" ||
                        (e.key === "Enter" && !e.shiftKey)
                      ) {
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
              <p className="page-description">
                Execute tasks through your AI agents
              </p>
            </div>

            <div className="flex-1 bg-gray-900 dark:bg-black rounded-xl border border-gray-200 dark:border-zinc-800 overflow-hidden flex flex-col">
              <div className="flex items-center gap-2 px-4 py-2.5 bg-gray-800 dark:bg-zinc-900 border-b border-gray-700 dark:border-zinc-800">
                <div className="flex gap-1.5">
                  <div className="w-3 h-3 rounded-full bg-red-500" />
                  <div className="w-3 h-3 rounded-full bg-amber-500" />
                  <div className="w-3 h-3 rounded-full bg-emerald-500" />
                </div>
                <span className="text-xs font-mono text-gray-400 ml-2">
                  mizan ~ %
                </span>
                <span className="ml-auto text-xs text-gray-500">
                  Agent: {selectedAgent?.name || "None"}
                </span>
              </div>

              <div className="flex-1 overflow-y-auto p-4 font-mono text-xs leading-relaxed text-emerald-400 min-h-[120px] max-h-[400px]">
                {terminalLines.map((line, i) => (
                  <div
                    key={i}
                    className={`mb-0.5 ${
                      line.type === "error"
                        ? "text-red-400"
                        : line.type === "warn"
                          ? "text-amber-400"
                          : line.type === "info"
                            ? "text-blue-400"
                            : line.type === "gold"
                              ? "text-mizan-gold"
                              : "text-emerald-400"
                    }`}
                  >
                    {line.type === "gold" && (
                      <span className="text-mizan-gold font-semibold">
                        {"> "}
                      </span>
                    )}
                    {line.text}
                  </div>
                ))}
              </div>

              <div className="flex items-center border-t border-gray-700 dark:border-zinc-800 px-2 py-1">
                <span className="text-mizan-gold font-mono text-xs px-2 font-semibold">
                  {">"}
                </span>
                <input
                  className="flex-1 bg-transparent border-none text-emerald-400 font-mono text-xs outline-none py-2 px-1"
                  placeholder="Enter task for agent... (e.g., 'search for latest AI papers')"
                  value={taskInput}
                  onChange={(e) => setTaskInput(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && runTask()}
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
            {/* Header */}
            <div className="flex items-center justify-between px-5 py-3 border-b border-gray-200 dark:border-zinc-800">
              <div>
                <h2 className="page-title">Memory</h2>
                <p className="page-description">
                  What your AI remembers from past interactions
                </p>
              </div>
              <div className="flex items-center gap-2">
                <input
                  className="input text-sm py-1.5 w-48"
                  placeholder="Search memories..."
                  value={memoryQuery}
                  onChange={(e) => setMemoryQuery(e.target.value)}
                  onKeyDown={(e) =>
                    e.key === "Enter" &&
                    loadMemories(memoryQuery, memoryTypeFilter)
                  }
                />
                <button
                  className="btn-secondary text-sm"
                  onClick={() => loadMemories(memoryQuery, memoryTypeFilter)}
                >
                  Search
                </button>
                <button
                  className="btn-secondary text-sm"
                  onClick={async () => {
                    await fetch(`${config.API_URL}/memory/consolidate`, {
                      method: "POST",
                    });
                    addToast({
                      type: "success",
                      title: "Memory consolidated",
                    });
                    loadMemories("", memoryTypeFilter);
                  }}
                >
                  Consolidate
                </button>
                <button
                  className="btn-gold text-sm"
                  onClick={() => setShowAddMemory(!showAddMemory)}
                >
                  <Icons.Plus /> Add
                </button>
              </div>
            </div>

            {/* Add Memory Form */}
            {showAddMemory && (
              <div className="mx-5 mt-3 p-4 bg-white dark:bg-zinc-900 border border-gray-200 dark:border-zinc-700 rounded-lg">
                <textarea
                  className="input w-full h-20 resize-none text-sm"
                  placeholder="What should your AI remember?"
                  value={newMemory.content}
                  onChange={(e) =>
                    setNewMemory({ ...newMemory, content: e.target.value })
                  }
                />
                <div className="flex items-center gap-3 mt-2">
                  <select
                    className="input text-sm py-1.5"
                    value={newMemory.memory_type}
                    onChange={(e) =>
                      setNewMemory({
                        ...newMemory,
                        memory_type: e.target.value,
                      })
                    }
                  >
                    <option value="semantic">Knowledge / Fact</option>
                    <option value="episodic">Experience / Event</option>
                    <option value="procedural">How-to / Process</option>
                  </select>
                  <input
                    className="input text-sm py-1.5 w-40"
                    placeholder="Tags (comma-separated)"
                    value={newMemory.tags}
                    onChange={(e) =>
                      setNewMemory({ ...newMemory, tags: e.target.value })
                    }
                  />
                  <button
                    className="btn-secondary text-sm"
                    onClick={() => setShowAddMemory(false)}
                  >
                    Cancel
                  </button>
                  <button
                    className="btn-gold text-sm ml-auto"
                    disabled={!newMemory.content.trim()}
                    onClick={async () => {
                      await fetch(`${config.API_URL}/memory/store`, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({
                          content: newMemory.content,
                          memory_type: newMemory.memory_type,
                          importance: newMemory.importance,
                          tags: newMemory.tags
                            .split(",")
                            .map((t) => t.trim())
                            .filter(Boolean),
                        }),
                      });
                      setNewMemory({
                        content: "",
                        memory_type: "semantic",
                        importance: 0.7,
                        tags: "",
                      });
                      setShowAddMemory(false);
                      loadMemories("", memoryTypeFilter);
                      addToast({ type: "success", title: "Memory saved" });
                    }}
                  >
                    Save Memory
                  </button>
                </div>
              </div>
            )}

            {/* Type filter tabs */}
            <div className="flex gap-1 px-5 pt-3">
              {(
                [
                  { key: "all", label: "All" },
                  { key: "semantic", label: "Knowledge" },
                  { key: "episodic", label: "Events" },
                  { key: "procedural", label: "How-to" },
                ] as const
              ).map((tab) => (
                <button
                  key={tab.key}
                  className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-colors ${
                    memoryTypeFilter === tab.key
                      ? "bg-mizan-gold/10 text-mizan-gold border border-mizan-gold/20"
                      : "text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-zinc-800 border border-transparent"
                  }`}
                  onClick={() => {
                    setMemoryTypeFilter(tab.key);
                    loadMemories(memoryQuery, tab.key);
                  }}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            {/* Memory list */}
            <div className="flex-1 overflow-y-auto p-4 space-y-2">
              {memories.length === 0 && (
                <div className="flex flex-col items-center justify-center py-20 text-gray-400 dark:text-gray-500">
                  <Icons.Memory />
                  <p className="mt-3 font-medium">No memories stored yet</p>
                  <p className="text-sm mt-1 text-center max-w-sm">
                    Add memories manually, or start chatting — your AI will
                    remember important details automatically.
                  </p>
                  <button
                    className="btn-gold btn-sm mt-4"
                    onClick={() => setShowAddMemory(true)}
                  >
                    <Icons.Plus /> Add Your First Memory
                  </button>
                </div>
              )}
              {memories.map((mem) => (
                <div key={mem.id} className="card">
                  <div className="flex items-center gap-2 mb-2">
                    <span
                      className={`badge ${
                        mem.type === "episodic"
                          ? "badge-info"
                          : mem.type === "semantic"
                            ? "badge-warning"
                            : "badge-success"
                      }`}
                    >
                      {mem.type === "semantic"
                        ? "knowledge"
                        : mem.type === "procedural"
                          ? "how-to"
                          : mem.type}
                    </span>
                    <span className="text-xs font-mono text-gray-400 dark:text-gray-500">
                      {mem.agent_id
                        ? `Agent: ${mem.agent_id.substring(0, 8)}`
                        : "System"}
                    </span>
                    <span className="ml-auto text-xs text-gray-400 dark:text-gray-500">
                      Importance: {(mem.importance * 100).toFixed(0)}%
                    </span>
                  </div>
                  <div className="text-sm text-gray-700 dark:text-gray-300 leading-relaxed">
                    {typeof mem.content === "string"
                      ? mem.content
                      : JSON.stringify(mem.content)}
                  </div>
                  {(mem.tags?.length ?? 0) > 0 && (
                    <div className="flex flex-wrap gap-1 mt-2">
                      {mem.tags!.map((t) => (
                        <span
                          key={t}
                          className="text-xs px-1.5 py-0.5 bg-gray-100 dark:bg-zinc-800 border border-gray-200 dark:border-zinc-700 rounded text-gray-500 dark:text-gray-400 font-mono"
                        >
                          {t}
                        </span>
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

      case "knowledge":
        return (
          <div className="flex-1 flex flex-col overflow-hidden">
            <div className="flex items-center justify-between px-5 py-3 border-b border-gray-200 dark:border-zinc-800">
              <div>
                <h2 className="page-title">Knowledge</h2>
                <p className="page-description">
                  Feed URLs, PDFs, and YouTube videos to your AI
                </p>
              </div>
            </div>
            <div className="flex-1 overflow-y-auto p-5 space-y-5">
              {/* Ingest URL / YouTube */}
              <div className="detail-panel">
                <h3 className="text-base font-semibold text-gray-900 dark:text-gray-100 mb-3">
                  Ingest from URL
                </h3>
                <p className="text-sm text-gray-500 dark:text-gray-400 mb-3">
                  Paste a website URL or YouTube link to extract and store its
                  content as knowledge.
                </p>
                <div className="flex gap-2">
                  <input
                    className="input flex-1 text-sm"
                    placeholder="https://example.com or YouTube URL..."
                    value={knowledgeUrl}
                    onChange={(e) => setKnowledgeUrl(e.target.value)}
                    onKeyDown={(e) =>
                      e.key === "Enter" &&
                      !knowledgeLoading &&
                      ingestKnowledge()
                    }
                    disabled={knowledgeLoading}
                  />
                  <button
                    className="btn btn-primary text-sm px-4"
                    onClick={ingestKnowledge}
                    disabled={knowledgeLoading || !knowledgeUrl.trim()}
                  >
                    {knowledgeLoading ? "Ingesting..." : "Ingest"}
                  </button>
                </div>
                {knowledgeResult && (
                  <div
                    className={`mt-3 text-sm px-3 py-2 rounded-lg ${
                      knowledgeResult.startsWith("Error")
                        ? "bg-red-50 dark:bg-red-500/10 text-red-600 dark:text-red-400"
                        : "bg-emerald-50 dark:bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                    }`}
                  >
                    {knowledgeResult}
                  </div>
                )}
              </div>

              {/* Upload PDF */}
              <div className="detail-panel">
                <h3 className="text-base font-semibold text-gray-900 dark:text-gray-100 mb-3">
                  Upload PDF
                </h3>
                <p className="text-sm text-gray-500 dark:text-gray-400 mb-3">
                  Upload a PDF document to extract its text into knowledge.
                </p>
                <label
                  className={`flex items-center justify-center border-2 border-dashed rounded-xl p-6 cursor-pointer transition-colors ${
                    knowledgeLoading
                      ? "opacity-50 pointer-events-none"
                      : "border-gray-300 dark:border-zinc-600 hover:border-mizan-gold/50 hover:bg-gray-50 dark:hover:bg-zinc-800/50"
                  }`}
                >
                  <input
                    type="file"
                    accept=".pdf"
                    className="hidden"
                    onChange={(e) => {
                      const file = e.target.files?.[0];
                      if (file) uploadKnowledgePdf(file);
                      e.target.value = "";
                    }}
                    disabled={knowledgeLoading}
                  />
                  <span className="text-sm text-gray-500 dark:text-gray-400">
                    {knowledgeLoading
                      ? "Uploading..."
                      : "Click to select a PDF (max 20MB)"}
                  </span>
                </label>
              </div>

              {/* Sources List */}
              <div className="detail-panel">
                <h3 className="text-base font-semibold text-gray-900 dark:text-gray-100 mb-3">
                  Ingested Sources ({knowledgeSources.length})
                </h3>
                {knowledgeSources.length === 0 ? (
                  <p className="text-sm text-gray-400 dark:text-gray-500">
                    No knowledge ingested yet. Paste a URL or upload a PDF
                    above.
                  </p>
                ) : (
                  <div className="space-y-2">
                    {knowledgeSources.map((source, idx) => (
                      <div
                        key={idx}
                        className="flex items-center justify-between py-2 px-3 rounded-lg bg-gray-50 dark:bg-zinc-800/50"
                      >
                        <div className="flex items-center gap-2 min-w-0">
                          <span
                            className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                              source.type === "youtube"
                                ? "bg-red-100 dark:bg-red-500/15 text-red-600 dark:text-red-400"
                                : source.type === "pdf"
                                  ? "bg-blue-100 dark:bg-blue-500/15 text-blue-600 dark:text-blue-400"
                                  : "bg-emerald-100 dark:bg-emerald-500/15 text-emerald-600 dark:text-emerald-400"
                            }`}
                          >
                            {source.type}
                          </span>
                          <span className="text-sm text-gray-700 dark:text-gray-300 truncate">
                            {source.title}
                          </span>
                        </div>
                        <span className="text-xs text-gray-400 dark:text-gray-500 shrink-0 ml-2">
                          {source.chunks} chunks
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        );

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
                <p className="page-description">
                  Connect external services and APIs
                </p>
              </div>
            </div>
            <div className="flex-1 overflow-y-auto p-4 space-y-2">
              {integrations.length === 0 && (
                <div className="flex flex-col items-center justify-center py-20 text-gray-400 dark:text-gray-500">
                  <Icons.Globe />
                  <p className="mt-3 font-medium">No integrations configured</p>
                  <p className="text-sm mt-1">
                    Use the Providers page to connect AI models, or Channels for
                    messaging platforms.
                  </p>
                </div>
              )}
              {integrations.map((int) => (
                <div key={int.id} className="card flex items-center gap-3">
                  <span
                    className={`badge ${int.enabled ? "badge-success" : "badge-error"}`}
                  >
                    {int.type}
                  </span>
                  <span className="font-medium text-sm text-gray-900 dark:text-gray-100">
                    {int.name}
                  </span>
                  <span
                    className={`ml-auto text-xs ${int.enabled ? "text-emerald-600 dark:text-emerald-400" : "text-red-500"}`}
                  >
                    {int.enabled ? "Enabled" : "Disabled"}
                  </span>
                  <button
                    className="p-1.5 rounded-lg text-gray-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-500/10 transition-colors"
                    onClick={async () => {
                      await fetch(`${config.API_URL}/integrations/${int.id}`, {
                        method: "DELETE",
                      });
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
    <div className="h-screen flex flex-col overflow-hidden bg-transparent text-gray-900 dark:text-gray-100 font-body transition-colors duration-500">
      {/* Connection banner */}
      <ConnectionBanner status={wsStatus} attempts={reconnectAttempts} />

      {/* Header */}
      <header className="flex items-center gap-4 px-6 py-3 bg-white/70 dark:bg-mizan-dark-surface/60 backdrop-blur-xl border-b border-white/50 dark:border-white/10 z-50 shrink-0 shadow-[0_1px_12px_rgba(0,0,0,0.03)] transition-all">
        <div className="flex items-center gap-2.5">
          <div className="text-2xl leading-none select-none text-mizan-gold font-arabic">
            &#1605;&#1610;&#1586;&#1575;&#1606;
          </div>
          <div className="flex flex-col">
            <span className="text-sm font-display font-semibold text-gray-900 dark:text-gray-100 tracking-wide">
              MIZAN
            </span>
            <span className="text-xs text-gray-400 dark:text-gray-500 tracking-widest">
              v{appVersion}
            </span>
          </div>
        </div>

        <div className="flex-1" />

        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-gray-100 dark:bg-zinc-800 border border-gray-200 dark:border-zinc-700">
            <div className={`w-2 h-2 rounded-full ${statusDot}`} />
            <span className="text-xs font-mono text-gray-600 dark:text-gray-400">
              {statusLabel}
            </span>
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
        <Sidebar
          navSections={navSections}
          activeTab={activeTab}
          setActiveTab={setActiveTab}
          selectedAgent={selectedAgent}
        />

        {/* Content */}
        <main className="flex-1 overflow-hidden flex flex-col bg-transparent relative z-0 pb-16 md:pb-0">
          <ErrorBoundary>
            <Suspense
              fallback={
                <div className="p-5">
                  <div className="card-grid">
                    <SkeletonCard count={3} />
                  </div>
                </div>
              }
            >
              {renderContent()}
            </Suspense>
          </ErrorBoundary>
        </main>
      </div>

      {/* Mobile bottom nav */}
      <MobileNav activeTab={activeTab} setActiveTab={setActiveTab} />

      {/* Create / Edit Agent Modal */}
      {showCreateAgent && (
        <AgentModal
          editingAgent={editingAgent}
          initialData={newAgent}
          onSave={(data) => {
            setNewAgent(data);
            if (editingAgent) {
              updateAgent();
            } else {
              createAgent();
            }
          }}
          onClose={() => {
            setShowCreateAgent(false);
            setEditingAgent(null);
          }}
        />
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

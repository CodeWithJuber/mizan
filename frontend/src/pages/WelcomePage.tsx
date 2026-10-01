/**
 * Welcome / Setup Wizard for MIZAN
 * Shows on first visit. Guides users through initial setup:
 * login -> welcome -> provider -> ready.
 */

import { useState, useEffect } from "react";
import type { ApiClient } from "../types";
import { PasswordInput } from "../components/PasswordInput";
import { useToast } from "../components/Toast";

interface WelcomePageProps {
  api: ApiClient;
  wsStatus: string;
  onComplete: () => void;
  onOpenSettings?: () => void;
}

type Step = "login" | "welcome" | "provider" | "ready";

interface ProviderOption {
  id: string;
  name: string;
  description: string;
  configured: boolean;
  link: string;
  badge?: string;
}

export default function WelcomePage({
  api,
  wsStatus,
  onComplete,
  onOpenSettings,
}: WelcomePageProps) {
  const { addToast } = useToast();
  const [step, setStep] = useState<Step>(() =>
    localStorage.getItem("mizan_token") ? "welcome" : "login",
  );
  const [providers, setProviders] = useState<ProviderOption[]>([]);
  const [testing, setTesting] = useState<string | null>(null);
  const [healthResult, setHealthResult] = useState<Record<string, boolean>>({});

  // Login form state
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loginLoading, setLoginLoading] = useState(false);
  const [loginError, setLoginError] = useState<string | null>(null);

  useEffect(() => {
    if (localStorage.getItem("mizan_token")) void loadProviders();
  }, []);

  const loadProviders = async () => {
    try {
      const res = (await api.get("/providers")) as {
        providers?: Array<{
          name: string;
          configured: boolean;
          display: string;
        }>;
      };
      const list = res.providers || [];
      setProviders([
        {
          id: "ruh",
          name: "Ruh",
          description:
            "Your Arabic model. Chat and tool capabilities depend on the deployed checkpoint.",
          configured: list.some(
            (provider) =>
              provider.name.startsWith("ruh") && provider.configured,
          ),
          link: "https://github.com/CodeWithJuber/ruh-serverless",
        },
        {
          id: "anthropic",
          name: "Anthropic Claude",
          description:
            "Best for reasoning and coding. Claude Opus, Sonnet, Haiku.",
          configured:
            list.find((p) => p.name === "anthropic")?.configured || false,
          link: "https://console.anthropic.com/",
          badge: "Recommended",
        },
        {
          id: "openrouter",
          name: "OpenRouter",
          description: "Access 300+ models: Gemini, Llama, Mistral, and more.",
          configured:
            list.find((p) => p.name === "openrouter")?.configured || false,
          link: "https://openrouter.ai/",
          badge: "300+ models",
        },
        {
          id: "openai",
          name: "OpenAI",
          description: "GPT-4o, o3 and other OpenAI models.",
          configured:
            list.find((p) => p.name === "openai")?.configured || false,
          link: "https://platform.openai.com/",
        },
        {
          id: "ollama",
          name: "Ollama (Local)",
          description:
            "Run AI models on your own machine. Free, fully private.",
          configured:
            list.find((p) => p.name === "ollama")?.configured || false,
          link: "https://ollama.ai/",
          badge: "Free",
        },
      ]);
    } catch {
      // Use defaults
      setProviders([
        {
          id: "anthropic",
          name: "Anthropic Claude",
          description: "Best for reasoning and coding.",
          configured: false,
          link: "https://console.anthropic.com/",
          badge: "Recommended",
        },
        {
          id: "openrouter",
          name: "OpenRouter",
          description: "Access 300+ models.",
          configured: false,
          link: "https://openrouter.ai/",
          badge: "300+ models",
        },
        {
          id: "openai",
          name: "OpenAI",
          description: "GPT-4o and other models.",
          configured: false,
          link: "https://platform.openai.com/",
        },
        {
          id: "ollama",
          name: "Ollama (Local)",
          description: "Free, private, runs locally.",
          configured: false,
          link: "https://ollama.ai/",
          badge: "Free",
        },
      ]);
    }
  };

  const handleLogin = async () => {
    if (!username.trim() || !password) {
      setLoginError("Username aur password dono chahiye");
      return;
    }
    setLoginLoading(true);
    setLoginError(null);
    try {
      const data = (await api.post("/auth/login", {
        username: username.trim(),
        password,
      })) as {
        token?: string;
        error?: string;
      };
      if (data.token) {
        localStorage.setItem("mizan_token", data.token);
        window.dispatchEvent(new CustomEvent("mizan:authchanged"));
        void loadProviders();
        setStep("welcome");
      } else {
        setLoginError(
          data.error || "Login failed — username/password check karo",
        );
      }
    } catch {
      setLoginError("Server se connect nahi ho paya — backend chal raha hai?");
    }
    setLoginLoading(false);
  };

  const testProvider = async (name: string) => {
    setTesting(name);
    try {
      const res = (await api.get(`/providers/${name}/health`)) as {
        healthy?: boolean;
      };
      setHealthResult((prev) => ({ ...prev, [name]: !!res.healthy }));
      if (!res.healthy) {
        addToast({
          type: "warning",
          title: `${name} not healthy`,
          description: "API key check karo ya provider ka status dekho.",
        });
      }
    } catch {
      setHealthResult((prev) => ({ ...prev, [name]: false }));
      addToast({
        type: "error",
        title: `${name} test failed`,
        description: "Server se connect nahi ho paya.",
      });
    }
    setTesting(null);
  };

  const finishSetup = () => {
    localStorage.setItem("mizan_setup_complete", "true");
    onComplete();
  };

  const anyConfigured = providers.some(
    (p) => p.configured || healthResult[p.id],
  );

  const wsLabel =
    wsStatus === "connected"
      ? "Live notifications connected"
      : wsStatus === "connecting" || wsStatus === "reconnecting"
        ? "Connecting live notifications..."
        : wsStatus === "auth_required"
          ? "Login required"
          : "Live notifications unavailable";
  const wsDot =
    wsStatus === "connected"
      ? "bg-emerald-500"
      : wsStatus === "connecting" || wsStatus === "reconnecting"
        ? "bg-amber-500 animate-pulse"
        : wsStatus === "auth_required"
          ? "bg-amber-500"
          : "bg-red-500";

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-zinc-950 flex items-center justify-center p-4">
      <div className="max-w-2xl w-full">
        {/* Step 0: Login (first visit) */}
        {step === "login" && (
          <div className="max-w-sm mx-auto text-center space-y-6">
            <div className="space-y-3">
              <div className="text-5xl font-arabic text-mizan-gold">
                &#1605;&#1610;&#1586;&#1575;&#1606;
              </div>
              <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                Welcome to MIZAN
              </h1>
              <p className="text-gray-600 dark:text-gray-400">
                Pehle login karo, phir setup karenge.
              </p>
              <p className="text-xs text-gray-500 dark:text-gray-500">
                Ask the person who set up Mizan for the admin login.
              </p>
            </div>

            <form
              className="bg-white dark:bg-zinc-900 border border-gray-200 dark:border-zinc-800 rounded-xl p-6 space-y-4 text-left"
              onSubmit={(e) => {
                e.preventDefault();
                handleLogin();
              }}
            >
              <div>
                <label
                  htmlFor="welcome-username"
                  className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1"
                >
                  Username
                </label>
                <input
                  id="welcome-username"
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleLogin()}
                  className="w-full px-4 py-2.5 border border-gray-300 dark:border-zinc-700 rounded-lg bg-white dark:bg-zinc-800 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-mizan-gold/50"
                  placeholder="admin"
                  autoComplete="username"
                />
              </div>
              <div>
                <label
                  htmlFor="welcome-password"
                  className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1"
                >
                  Password
                </label>
                <PasswordInput
                  id="welcome-password"
                  value={password}
                  onChange={setPassword}
                  placeholder="••••••••"
                  autoComplete="current-password"
                  className="w-full px-4 py-2.5 border border-gray-300 dark:border-zinc-700 rounded-lg bg-white dark:bg-zinc-800 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-mizan-gold/50"
                />
              </div>
              {loginError && (
                <p className="text-sm text-red-600 dark:text-red-400">
                  {loginError}
                </p>
              )}
              <button
                type="submit"
                disabled={loginLoading}
                className="w-full px-8 py-3 bg-mizan-gold hover:bg-mizan-gold-light text-black font-semibold rounded-lg transition shadow-md disabled:opacity-50"
              >
                {loginLoading ? "Logging in..." : "Log in"}
              </button>
            </form>
          </div>
        )}

        {/* Step 1: Welcome */}
        {step === "welcome" && (
          <div className="text-center space-y-8">
            {/* Logo */}
            <div className="space-y-3">
              <div className="text-5xl font-arabic text-mizan-gold">
                &#1605;&#1610;&#1586;&#1575;&#1606;
              </div>
              <h1 className="text-3xl font-bold text-gray-900 dark:text-gray-100">
                Welcome to MIZAN
              </h1>
              <p className="text-lg text-gray-600 dark:text-gray-400 max-w-md mx-auto">
                Your personal AI assistant that can chat, browse the web, run
                code, and much more.
              </p>
            </div>

            {/* Connection status */}
            <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-white dark:bg-zinc-900 border border-gray-200 dark:border-zinc-800 shadow-sm">
              <div className={`w-2.5 h-2.5 rounded-full ${wsDot}`} />
              <span className="text-sm text-gray-600 dark:text-gray-400">
                {wsLabel}
              </span>
            </div>

            {wsStatus !== "connected" && (
              <p className="text-sm text-gray-500 dark:text-gray-400">
                Text chat uses a separate connection. Live notifications can
                reconnect in the background.
              </p>
            )}

            <div className="flex justify-center pt-4">
              <button
                onClick={() => setStep("provider")}
                className="px-8 py-3 bg-mizan-gold hover:bg-mizan-gold-light text-black font-semibold rounded-lg transition shadow-md"
              >
                Get Started
              </button>
            </div>
          </div>
        )}

        {/* Step 2: Provider Setup */}
        {step === "provider" && (
          <div className="space-y-6">
            <div className="text-center space-y-2">
              <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                Choose Your AI Provider
              </h2>
              <p className="text-gray-600 dark:text-gray-400">
                You need at least one AI provider. Add your key in{" "}
                <span className="font-medium text-gray-900 dark:text-gray-100">
                  Settings → AI Providers
                </span>
                .
              </p>
              <button
                onClick={() => {
                  // Deep-link to Settings → AI Providers section
                  localStorage.setItem("mizan_settings_section", "providers");
                  if (onOpenSettings) {
                    onOpenSettings();
                  } else {
                    onComplete();
                  }
                }}
                className="text-sm text-mizan-gold hover:underline min-h-[44px] px-3"
              >
                Open Settings → AI Providers
              </button>
            </div>

            <div className="grid gap-3">
              {providers.map((p) => (
                <div
                  key={p.id}
                  className={`bg-white dark:bg-zinc-900 border rounded-xl p-4 transition ${
                    p.configured || healthResult[p.id]
                      ? "border-emerald-300 dark:border-emerald-500/30 ring-1 ring-emerald-200 dark:ring-emerald-500/20"
                      : "border-gray-200 dark:border-zinc-800"
                  }`}
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <h3 className="font-semibold text-gray-900 dark:text-gray-100">
                          {p.name}
                        </h3>
                        {p.badge && (
                          <span className="text-xs bg-mizan-gold/10 text-mizan-gold px-2 py-0.5 rounded-full font-medium">
                            {p.badge}
                          </span>
                        )}
                        {(p.configured || healthResult[p.id]) && (
                          <span className="text-xs bg-emerald-100 dark:bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 px-2 py-0.5 rounded-full">
                            Ready
                          </span>
                        )}
                      </div>
                      <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                        {p.description}
                      </p>
                    </div>
                    <div className="flex items-center gap-2 ml-4 shrink-0">
                      <a
                        href={p.link}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-xs text-blue-600 dark:text-blue-400 hover:underline min-h-[44px] flex items-center px-2"
                      >
                        Get key
                      </a>
                      <button
                        onClick={() => testProvider(p.id)}
                        disabled={testing !== null}
                        className="text-xs px-4 py-2.5 min-h-[44px] bg-gray-100 dark:bg-zinc-800 hover:bg-gray-200 dark:hover:bg-zinc-700 text-gray-700 dark:text-gray-300 rounded-lg transition disabled:opacity-50"
                      >
                        {testing === p.id ? "Testing..." : "Test key"}
                      </button>
                    </div>
                  </div>
                  {healthResult[p.id] === false && (
                    <p className="text-xs text-red-500 mt-2">
                      Not configured yet — add your key in Settings → AI
                      Providers, then test again.
                    </p>
                  )}
                </div>
              ))}
            </div>

            <div className="flex justify-between items-center pt-4">
              <button
                onClick={() => setStep("welcome")}
                className="px-4 py-2 min-h-[44px] text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 text-sm transition"
              >
                Back
              </button>
              <button
                onClick={() => setStep("ready")}
                disabled={!anyConfigured}
                className="px-8 py-3 min-h-[44px] bg-mizan-gold hover:bg-mizan-gold-light text-black font-semibold rounded-lg transition shadow-md disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Continue
              </button>
            </div>
            {!anyConfigured && (
              <p className="text-xs text-center text-gray-500 dark:text-gray-400">
                Add at least one provider key to continue.
              </p>
            )}
          </div>
        )}

        {/* Step 3: Ready */}
        {step === "ready" && (
          <div className="text-center space-y-8">
            <div className="space-y-3">
              <div className="text-5xl">&#10024;</div>
              <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                You're All Set!
              </h2>
              <p className="text-gray-600 dark:text-gray-400 max-w-md mx-auto">
                Start chatting with your AI, explore the agents, or build
                plugins to extend it.
              </p>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 max-w-lg mx-auto">
              {[
                {
                  label: "Start Chatting",
                  desc: "Talk to your AI",
                  icon: "\uD83D\uDCAC",
                },
                {
                  label: "Meet Your Agents",
                  desc: "See your AI team",
                  icon: "\uD83E\uDD16",
                },
                {
                  label: "Read the Docs",
                  desc: "Learn to extend",
                  icon: "\uD83D\uDCD6",
                },
              ].map((item) => (
                <div
                  key={item.label}
                  className="bg-white dark:bg-zinc-900 border border-gray-200 dark:border-zinc-800 rounded-xl p-4 text-center"
                >
                  <div className="text-2xl mb-2">{item.icon}</div>
                  <div className="font-medium text-sm text-gray-900 dark:text-gray-100">
                    {item.label}
                  </div>
                  <div className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                    {item.desc}
                  </div>
                </div>
              ))}
            </div>

            <button
              onClick={finishSetup}
              className="px-8 py-3 bg-mizan-gold hover:bg-mizan-gold-light text-black font-semibold rounded-lg transition shadow-md"
            >
              Enter MIZAN
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
